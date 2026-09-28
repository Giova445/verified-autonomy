#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

CONTRACT = ".claude/acceptance.json"
REQUIRED = ("name", "expect", "check")
TIMEOUT = int(os.environ.get("ACCEPT_TIMEOUT", "300"))

HARNESS_ERROR = 2

EXPECTED_CONTROLS = 17

def run(cmd, cwd, extra=None):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           env={**os.environ, **(extra or {})},
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode
    except subprocess.TimeoutExpired:
        return None

def run_out(cmd, cwd):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return None, ""
    except OSError as exc:
        return HARNESS_ERROR, str(exc)

def load(root):
    path = os.path.join(root, CONTRACT)
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, ["%s exists but will not parse (%s) — that is not a pass" % (CONTRACT, exc)]
    if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list):
        return None, ["%s has no 'outcomes' list" % CONTRACT]
    return data, []

REVISION = re.compile(r"\b([0-9a-f]{7,40})\b")

MIN_REVISION = 7

def substitute(cmd, env_vars):
    for k, v in (env_vars or {}).items():
        cmd = cmd.replace("{{%s}}" % k, str(v).rstrip("/"))
    return cmd

def provenance(env, root):
    spec = env.get("provenance")
    if not spec:
        return True, ""
    rc, out = run_out("git rev-parse HEAD", root)
    head = out.strip() if rc == 0 else ""
    if not head:
        return False, "cannot read the local HEAD, so there is nothing to compare against"
    cmd = spec.get("cmd")
    if not cmd:
        return False, "provenance is declared with no `cmd` to establish it"
    rc, out = run_out(cmd, root)
    if rc is None:
        return False, "the provenance probe never finished (%ss)" % TIMEOUT
    if rc != 0:
        return False, "the provenance probe exited %d" % rc
    pattern = spec.get("pattern")
    try:
        m = re.search(pattern, out) if pattern else REVISION.search(out)
    except re.error as exc:
        return False, "the declared `pattern` is not a valid regex (%s)" % exc
    if not m:
        return False, "no revision found in the probe output"
    sha = m.group(1) if m.groups() else m.group(0)
    if len(sha) < MIN_REVISION:
        return False, ("the probe yielded %r, too short to identify a build (need %d+ "
                       "characters) — check the declared `pattern`" % (sha, MIN_REVISION))
    n = min(len(sha), len(head))
    if sha[:n].lower() != head[:n].lower():
        return False, ("it is running %s, not the %s under test — anything that passed here "
                       "would be evidence about a different build" % (sha[:12], head[:12]))
    return True, "running %s, the revision under test" % sha[:12]

def judge(outcome, root, environments=None, resolved=None, shot=None):
    environments = environments or {}
    resolved = {} if resolved is None else resolved
    missing = [f for f in REQUIRED if not outcome.get(f)]
    if missing:
        return "REFUSED", "missing required field(s): %s" % ", ".join(missing)

    name = outcome.get("env")
    env = {}
    if name:
        if name not in environments:
            return "REFUSED", ("names environment '%s', which the contract does not declare"
                               % name)
        env = environments[name]
        if name not in resolved:
            resolved[name] = provenance(env, root)
        ok, detail = resolved[name]
        if not ok:
            return "WRONG BUILD", "environment '%s': %s" % (name, detail)

    env_vars = env.get("vars") or {}
    rc_check = run(substitute(outcome["check"], env_vars), root,
                   {"ACCEPT_SHOT": shot} if shot else None)
    if rc_check is None:
        return "NO VERDICT", "check still running at %ss" % TIMEOUT
    if not outcome.get("control"):
        if rc_check == HARNESS_ERROR:
            return "CANNOT RUN", ("the check exited %d — the harness could not do its job, so "
                                  "nothing was learned about the deliverable" % HARNESS_ERROR)
        if rc_check != 0:
            return "FAILS", "check exited %d" % rc_check
        return "holds", "check exit 0 (no control declared)"
    rc_control = run(substitute(outcome["control"], env_vars), root)
    if rc_control is None:
        return "NO VERDICT", "control still running at %ss" % TIMEOUT

    if rc_check == HARNESS_ERROR or rc_control == HARNESS_ERROR:
        which = "check" if rc_check == HARNESS_ERROR else "control"
        return "CANNOT RUN", ("the %s exited %d — the harness could not do its job, so nothing "
                              "was learned about the deliverable. Fix the environment, not the "
                              "code." % (which, HARNESS_ERROR))

    if rc_control == 0:
        return "NOT PROVEN", ("the control passed (exit 0) — this check cannot tell a broken "
                              "artifact from a whole one, so its verdict means nothing")
    if rc_check != 0:
        return "FAILS", "check exited %d; control discriminates (exit %d)" % (rc_check, rc_control)
    return "holds", "check exit 0, control exit %d" % rc_control

def slug(name, i):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60] or "outcome-%d" % i

def save(path, status, results):
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"contract": status, "outcomes": results}, fh, indent=2)

def report(root, results_path=None):
    contract, findings = load(root)
    if findings:
        for f in findings:
            print("FINDING: %s" % f)
        save(results_path, "invalid", [])
        return 1
    if contract is None:
        save(results_path, "absent", [])
        print("no deliverable contract (%s absent)." % CONTRACT)
        print("Nothing is claimed about whether this deliverable does what was asked.")
        print("Declare outcomes there to make this gate binding.")
        return 0

    outcomes = contract["outcomes"]
    if not outcomes:
        save(results_path, "empty", [])
        print("FINDING: %s declares zero outcomes — an empty contract certifies everything"
              % CONTRACT)
        return 1
    environments = contract.get("environments") or {}

    where = lambda o: o.get("env") or "here"
    print("deliverable contract: %d outcome(s) across %d environment(s)"
          % (len(outcomes), len(set(where(o) for o in outcomes))))
    print()
    bad = unrunnable = wrong_build = 0
    resolved, results = {}, []
    shots = os.path.join(root, ".claude", "evidence", "shots")
    os.makedirs(shots, exist_ok=True)
    for i, o in enumerate(outcomes):
        shot = os.path.join(shots, slug(o.get("name"), i) + ".png")
        verdict, detail = judge(o, root, environments, resolved, shot)
        results.append({"name": o.get("name"), "expect": o.get("expect"), "verdict": verdict,
                        "detail": detail, "controlled": bool(o.get("control")),
                        "shot": shot if os.path.exists(shot) else None})
        if verdict != "holds":
            bad += 1
        if verdict == "CANNOT RUN":
            unrunnable += 1
        if verdict == "WRONG BUILD":
            wrong_build += 1
        print("  %-11s [%s] %s" % (verdict, where(o), o.get("name") or "(unnamed)"))
        print("              expected: %s" % (o.get("expect") or "(not stated)"))
        print("              %s" % detail)
    print()
    save(results_path, "ok", results)
    if bad:
        print("%d of %d outcome(s) not established." % (bad, len(outcomes)))
        if unrunnable:
            print("%d could not be checked at all — the deliverable may be perfectly fine. "
                  "That is an environment problem, not a code problem." % unrunnable)
        if wrong_build:
            print("%d ran against an environment that is not the build under test. Nothing is "
                  "claimed about them either way — deploy this revision there first."
                  % wrong_build)
        return 1
    uncontrolled = sum(1 for o in outcomes if not o.get("control"))
    print("All %d declared outcome(s) hold." % len(outcomes))
    if uncontrolled:
        print("%d have no control, so they are not shown able to fail — add one where a "
              "silent pass would be costly." % uncontrolled)
    return 0

ABSENT = """product : NOT PROVEN - no product expectations are declared (.claude/acceptance.json is absent).
  Green engineering gates say the code is consistent, not that the product does what was asked.
  Before claiming done, write .claude/acceptance.json: one outcome per thing the user must be able
  to do or see, each checked against the running product.
    {"outcomes": [{"name": "...", "expect": "<what the user observes, in their words>",
                   "check": "<command that exercises the product: drive.mjs, curl, the CLI>"}]}
  Read the spec, the linked issue or PR and earlier product decisions first. Expectations often
  live somewhere the request does not point."""

def summarize(path):
    try:
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
    except (OSError, ValueError):
        return "open", ["product : acceptance.py wrote no results, so nothing is established"]
    status, outs = r.get("contract"), r.get("outcomes") or []
    if status == "absent":
        return "absent", ABSENT.splitlines()
    if status != "ok":
        return "open", ["product : .claude/acceptance.json is %s - that is not a pass" % status]
    bad = [o for o in outs if o.get("verdict") != "holds"]
    if not bad:
        loose = sum(1 for o in outs if not o.get("controlled"))
        tail = ", %d without a control" % loose if loose else ""
        return "held", ["%d product expectation(s) hold%s" % (len(outs), tail)]
    lines = ["product : %d of %d expectation(s) not established. Still open:" % (len(bad), len(outs))]
    lines += ["  - %s: %s  (%s: %s)" % (o.get("name"), o.get("expect"), o.get("verdict"), o.get("detail"))
              for o in bad]
    lines.append("Continue with them. If one is blocked, say what is blocking it.")
    return "open", lines

def selftest():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="acceptance-selftest-")
    passed = ran = 0

    def chk(label, cond):
        nonlocal passed, ran
        ran += 1
        if cond:
            passed += 1
            print("  ok    %s" % label)
        else:
            print("  FAIL  %s" % label)

    def repo(name, contract):
        d = os.path.join(tmp, name)
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        run("git init -q . && git config user.email h@h && git config user.name h", d)
        with open(os.path.join(d, "seed.txt"), "w") as fh:
            fh.write(name)
        run("git add -A && git commit -qm seed", d)
        if contract is not None:
            with open(os.path.join(d, CONTRACT), "w", encoding="utf-8") as fh:
                fh.write(contract if isinstance(contract, str) else json.dumps(contract))
        return d

    def rc_of(d):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = report(d)
        return code, buf.getvalue()

    ok_outcome = {"name": "o", "expect": "e", "check": "exit 0", "control": "exit 1"}

    def outcome(check, control, **extra):
        return dict({"name": "o", "expect": "e", "check": check, "control": control}, **extra)

    rc, out = rc_of(repo("good", {"outcomes": [ok_outcome]}))
    chk("a holding outcome with a failing control passes", rc == 0 and "holds" in out)

    rc, out = rc_of(repo("broken", {"outcomes": [outcome("exit 1", "exit 1")]}))
    chk("a failing check fails the gate", rc == 1 and "FAILS" in out)

    rc, out = rc_of(repo("vacuous", {"outcomes": [outcome("exit 0", "exit 0")]}))
    chk("a control that passes yields NOT PROVEN", rc == 1 and "NOT PROVEN" in out)

    rc, out = rc_of(repo("noexpect", {"outcomes": [{"name": "o", "check": "exit 0", "control": "exit 1"}]}))
    chk("an outcome with no stated expectation is REFUSED", rc == 1 and "REFUSED" in out)

    a = rc_of(repo("nocontrol", {"outcomes": [{"name": "o", "expect": "e", "check": "exit 0"}]}))
    b = rc_of(repo("nocontrolred", {"outcomes": [{"name": "o", "expect": "e", "check": "exit 1"}]}))
    chk("without a control a check still decides, and the pass is reported uncontrolled",
        a[0] == 0 and "no control" in a[1] and b[0] == 1 and "FAILS" in b[1])

    rc, out = rc_of(repo("none", None))
    chk("no contract reports and does not block", rc == 0 and "no deliverable contract" in out)

    a = rc_of(repo("corrupt", "{not json"))
    b = rc_of(repo("empty", {"outcomes": []}))
    chk("an unreadable or empty contract fails closed", a[0] == 1 and b[0] == 1)

    a = rc_of(repo("cannotrun", {"outcomes": [outcome("exit 2", "exit 1")]}))
    b = rc_of(repo("ctlcannotrun", {"outcomes": [outcome("exit 0", "exit 2")]}))
    chk("a harness error is CANNOT RUN, never FAILS or holds",
        all(rc == 1 and "CANNOT RUN" in out and "FAILS" not in out and "holds" not in out
            for rc, out in (a, b)) and "environment problem" in b[1])

    rc, out = rc_of(repo("unknownenv", {"outcomes": [outcome("exit 0", "exit 1", env="ghost")]}))
    chk("an undeclared environment is REFUSED", rc == 1 and "REFUSED" in out)

    rc, out = rc_of(repo("vars", {
        "environments": {"e1": {"vars": {"base": "https://x.test/"}}},
        "outcomes": [outcome("test '{{base}}' = 'https://x.test'", "exit 1", env="e1")]}))
    chk("vars are substituted in an environment without provenance", rc == 0 and "holds" in out)

    rc, out = rc_of(repo("wrongbuild", {
        "environments": {"e1": {"provenance": {"cmd": "echo 0000000000000000"}}},
        "outcomes": [outcome("exit 0", "exit 1", env="e1")]}))
    chk("a different build is WRONG BUILD, not holds or FAILS",
        rc == 1 and "it is running " in out and "holds" not in out and "FAILS" not in out)

    rc, out = rc_of(repo("noprov", {
        "environments": {"e1": {"provenance": {"cmd": "exit 7"}}},
        "outcomes": [outcome("exit 0", "exit 1", env="e1")]}))
    chk("unestablishable provenance is refused", rc == 1 and "WRONG BUILD" in out)

    d = repo("shortcap", None)
    _rc, head = run_out("git rev-parse HEAD", d)
    head = head.strip()
    short, _ = provenance({"provenance": {"cmd": "echo " + head, "pattern": r"(\w)"}}, d)
    seven, _ = provenance({"provenance": {"cmd": "echo " + head[:7]}}, d)
    chk("a sub-7-char capture is refused and a 7-char sha accepted", short is False and seven is True)

    probe = os.path.join(d, "count.sh")
    with open(probe, "w") as fh:
        fh.write("#!/bin/sh\necho run >> %s/hits\necho %s\n" % (d, head))
    os.chmod(probe, 0o755)
    with open(os.path.join(d, CONTRACT), "w") as fh:
        json.dump({"environments": {"e1": {"provenance": {"cmd": probe}}},
                   "outcomes": [dict(outcome("exit 0", "exit 1", env="e1"), name="o%d" % i)
                                for i in range(5)]}, fh)
    rc_of(d)
    chk("provenance is probed once per environment", open(os.path.join(d, "hits")).read().count("run") == 1)

    d = repo("results", {"outcomes": [ok_outcome, dict(outcome("exit 1", "exit 1"), name="Search results",
                                                             expect="searching a name lists only matching items")]})
    rp = os.path.join(d, "r.json")
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        report(d, rp)
        r = json.load(open(rp))
        report(repo("results-absent", None), rp)
        absent = json.load(open(rp))
    chk("--results names each open outcome with its expectation",
        [(o["name"], o["verdict"], o["expect"]) for o in r["outcomes"] if o["verdict"] != "holds"]
        == [("Search results", "FAILS", "searching a name lists only matching items")]
        and absent == {"contract": "absent", "outcomes": []})

    d = repo("shot", {"outcomes": [outcome('test -n "$ACCEPT_SHOT" && touch "$ACCEPT_SHOT"', "exit 1")]})
    with redirect_stdout(io.StringIO()):
        report(d, rp)
    shot = json.load(open(rp))["outcomes"][0]["shot"]
    chk("each check is told where to save its screenshot, and a saved one is reported",
        bool(shot) and os.path.exists(shot) and shot.endswith(".claude/evidence/shots/o.png"))

    with redirect_stdout(io.StringIO()):
        report(repo("sum-open", {"outcomes": [ok_outcome, dict(outcome("exit 1", "exit 1"),
                                                                 name="Search results", expect="only matches")]}), rp)
    st, lines = summarize(rp)
    held = summarize(os.path.join(d, "missing.json"))
    with redirect_stdout(io.StringIO()):
        report(repo("sum-absent", None), rp)
    ab = summarize(rp)
    chk("the summary names what is open, and absence or no results is never held",
        st == "open" and any("Search results: only matches" in l for l in lines)
        and "Continue with them" in lines[-1] and held[0] == "open" and ab[0] == "absent")

    shutil.rmtree(tmp, ignore_errors=True)
    if ran != EXPECTED_CONTROLS:
        print("  FAIL  ran %d controls, expected %d" % (ran, EXPECTED_CONTROLS))
        passed = -1
    print()
    if passed == EXPECTED_CONTROLS:
        print("SELF-TEST PASSED  (%d checks)" % EXPECTED_CONTROLS)
        return 0
    print("SELF-TEST FAILED  (%d of %d checks)" % (passed, EXPECTED_CONTROLS))
    return 1

def main():
    args = sys.argv[1:]
    if args and args[0] in ("--self-test", "selftest"):
        return selftest()
    if args and args[0] == "--summarize":
        status, lines = summarize(args[1] if len(args) > 1 else "")
        print(status)
        print("\n".join(lines))
        return 0
    results = None
    if "--results" in args:
        i = args.index("--results")
        if i + 1 >= len(args):
            print("--results needs a path")
            return HARNESS_ERROR
        results, args = args[i + 1], args[:i] + args[i + 2:]
    root = args[0] if args else os.getcwd()
    return report(root, results)

if __name__ == "__main__":
    sys.exit(main())
