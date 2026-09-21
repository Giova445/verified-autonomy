#!/usr/bin/env python3
"""acceptance — does the deliverable satisfy what was asked, or only what was built?

    acceptance.py [dir]        run the contract in <dir>/.claude/acceptance.json
    acceptance.py --self-test  run the positive controls

WHY THIS EXISTS

`verify done` certifies exactly one thing: the commands in .claude/gates.json exited 0.
Those commands are lint, typecheck and the unit suite. An agent asked to "build the login
page" builds it, writes tests for what it built, and those tests pass. The acceptance
criteria are a FUNCTION OF THE IMPLEMENTATION, so deleting a requirement deletes its own
check, and a human doing five minutes of QA finds what every gate missed.

That is expectation-derived-from-subject, the defect this repository has now hit seven
times. The six earlier ones were inside individual gates. This one is the definition of
done.

WHAT A CONTRACT LOOKS LIKE

.claude/acceptance.json is written from the REQUEST, before the code, by hand:

    {
      "surface": ["src/app/login/**"],
      "outcomes": [
        {
          "name": "sign-in button is disabled until both fields are filled",
          "expect": "Button[type=submit] is disabled on an empty form.",
          "check":   "node benchmark/gates/drive.mjs fixtures/login.html checks/disabled.json",
          "control": "node benchmark/gates/drive.mjs fixtures/login-broken.html checks/disabled.json"
        }
      ]
    }

Three fields are mandatory and an outcome missing any of them is REFUSED, never skipped:

  expect   the expectation, stated in the declaration. Not read from the artifact. This is
           the field that makes the contract independent of the code; without it the whole
           file is just tests with extra steps.
  check    a command that drives the REAL artifact. Exit 0 means the outcome holds.
  control  the same check against something genuinely broken. It MUST fail. If it passes,
           the check cannot tell the two apart and the outcome is NOT PROVEN — never
           credited, because a check that cannot fail is not evidence.

BINDING VS REPORTING, AND WHY THAT IS NOT A COMPROMISE

With a contract present this gate is binding: a failed or unproven outcome exits non-zero.
With no contract it reports "no deliverable contract" and exits 0. It does NOT claim a
pass, and it does not block a repository that has not written one yet. Blocking every repo
on a file none of them have is how a gate gets deleted in week one; silently passing a repo
that HAS declared outcomes is how a gate becomes theatre. Fail closed where there is
something to check, honest where there is not.

WHAT IT CANNOT DO

It cannot tell you the contract describes what the user actually wanted. Nothing mechanical
can. It can only guarantee that whatever was written down before the code is still true of
the artifact afterwards, and that each such claim was made by a check able to fail.
"""
import json
import os
import re
import subprocess
import sys

CONTRACT = ".claude/acceptance.json"
REQUIRED = ("name", "expect", "check", "control")
TIMEOUT = int(os.environ.get("ACCEPT_TIMEOUT", "300"))

# The kit-wide convention for "the harness could not do its job", distinct from "the thing
# under test is wrong". drive.mjs, verify and ledger all use it. Kept as a named constant so
# the distinction is a decision rather than a magic number somebody normalises away.
HARNESS_ERROR = 2

# Declared independently of the control bodies below. Deriving this from the list of
# controls would mean deleting a control also deletes the expectation that it ran.
EXPECTED_CONTROLS = 18


def run(cmd, cwd):
    """Exit code of cmd, or None if it never produced one."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode
    except subprocess.TimeoutExpired:
        return None


def run_out(cmd, cwd):
    """(exit_code, output). Used where the output itself is the evidence."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return None, ""
    except OSError as exc:
        return HARNESS_ERROR, str(exc)


def load(root):
    """(contract, findings). A missing file is not a finding; an unreadable one is."""
    path = os.path.join(root, CONTRACT)
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        # Unreadable is never a pass. A contract that will not parse is indistinguishable
        # from one that was deleted, and both mean nothing is being checked.
        return None, ["%s exists but will not parse (%s) — that is not a pass" % (CONTRACT, exc)]
    if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list):
        return None, ["%s has no 'outcomes' list" % CONTRACT]
    return data, []


# ------------------------------------------------------------------ environments
#
# An outcome is a product expectation, and a product expectation is only meaningful WHERE
# the user meets it. That place is not always a staging URL: it is a running server, a built
# binary, a published package, a rendered asset, a CLI's real output. So the contract names
# ENVIRONMENTS and an outcome says which one it belongs to. Nothing here knows what staging
# is, and that is the point — an earlier version of this gate hard-coded it and could only
# express one shape of product.
#
#   "environments": {
#     "built":   {"vars": {"bin": "./dist/app"}},
#     "staging": {"vars": {"base": "https://app-staging.example.com"},
#                 "provenance": {"cmd": "curl -fsS https://.../version", "pattern": "..."}}
#   }
#
# `vars` are substituted into check and control as {{name}}, so one outcome declaration can
# read against a fixture locally and the real thing elsewhere.
#
# PROVENANCE is the half worth keeping from that earlier version, and it generalises cleanly.
# Verifying an artifact proves nothing unless the artifact is the one you just built. Point a
# browser at a deployment still serving last week's build, assert the button enables, go
# green — you verified somebody else's code and filed it as your own evidence. Same for a
# stale binary, a cached package, an asset regenerated from an older prompt. So an
# environment may declare a probe for the revision it is running, and an outcome in an
# environment whose provenance does not match is never credited.
REVISION = re.compile(r"\b([0-9a-f]{7,40})\b")


def substitute(cmd, env_vars):
    for k, v in (env_vars or {}).items():
        cmd = cmd.replace("{{%s}}" % k, str(v).rstrip("/"))
    return cmd


def provenance(env, root):
    """(ok, detail). True means this environment runs the revision under test."""
    spec = env.get("provenance")
    if not spec:
        return True, ""                       # not claimed, so nothing to contradict
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
    n = min(len(sha), len(head))
    if sha[:n].lower() != head[:n].lower():
        return False, ("it is running %s, not the %s under test — anything that passed here "
                       "would be evidence about a different build" % (sha[:12], head[:12]))
    return True, "running %s, the revision under test" % sha[:12]


def judge(outcome, root, environments=None):
    """(verdict, detail) for one declared outcome."""
    environments = environments or {}
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
        ok, detail = provenance(env, root)
        if not ok:
            # NOT "FAILS". The product may be perfectly fine; what is wrong is that this
            # environment is not the thing under test. Those send a reader to opposite places.
            return "WRONG BUILD", "environment '%s': %s" % (name, detail)

    env_vars = env.get("vars") or {}
    rc_check = run(substitute(outcome["check"], env_vars), root)
    if rc_check is None:
        return "NO VERDICT", "check still running at %ss" % TIMEOUT
    rc_control = run(substitute(outcome["control"], env_vars), root)
    if rc_control is None:
        return "NO VERDICT", "control still running at %ss" % TIMEOUT

    # CANNOT RUN comes before every other verdict, because saying "FAILS" about a deliverable
    # nobody looked at is a false statement about the product, and it is the one that gets a
    # gate deleted. Exit 2 is the convention across this kit for "the harness could not do its
    # job" — drive.mjs uses it for an unresolvable browser or an unreadable checks file, verify
    # uses it to refuse to certify, ledger uses it for a refused request. An earlier version
    # collapsed it into FAILS and reported "check exited 2; control discriminates (exit 2)"
    # about a login page that was perfectly fine. Both halves of that sentence were untrue.
    if rc_check == HARNESS_ERROR or rc_control == HARNESS_ERROR:
        which = "check" if rc_check == HARNESS_ERROR else "control"
        return "CANNOT RUN", ("the %s exited %d — the harness could not do its job, so nothing "
                              "was learned about the deliverable. Fix the environment, not the "
                              "code." % (which, HARNESS_ERROR))

    # NOT a rule here: "check and control exited the same code, so nothing was discriminated".
    # That was added and removed in the same sitting, because control 2 below refutes it.
    # check=1 with control=1 is a legitimate FAILS — the control demonstrated the check CAN
    # fail, and the real artifact failed too. The only same-code case that means nothing is a
    # harness error, and the branch above already owns it.
    #
    # The control runs regardless of how the check went. A failing check with a
    # non-discriminating control is two problems, and reporting only the first sends
    # someone to fix code when the check itself cannot see anything.
    if rc_control == 0:
        return "NOT PROVEN", ("the control passed (exit 0) — this check cannot tell a broken "
                              "artifact from a whole one, so its verdict means nothing")
    if rc_check != 0:
        return "FAILS", "check exited %d; control discriminates (exit %d)" % (rc_check, rc_control)
    return "holds", "check exit 0, control exit %d" % rc_control


def report(root):
    contract, findings = load(root)
    if findings:
        for f in findings:
            print("FINDING: %s" % f)
        return 1
    if contract is None:
        print("no deliverable contract (%s absent)." % CONTRACT)
        print("Nothing is claimed about whether this deliverable does what was asked.")
        print("Declare outcomes there to make this gate binding.")
        return 0

    outcomes = contract["outcomes"]
    if not outcomes:
        print("FINDING: %s declares zero outcomes — an empty contract certifies everything"
              % CONTRACT)
        return 1
    environments = contract.get("environments") or {}

    where = lambda o: o.get("env") or "here"
    print("deliverable contract: %d outcome(s) across %d environment(s)"
          % (len(outcomes), len(set(where(o) for o in outcomes))))
    print()
    bad = unrunnable = wrong_build = 0
    for o in outcomes:
        verdict, detail = judge(o, root, environments)
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
    if bad:
        print("%d of %d outcome(s) not established." % (bad, len(outcomes)))
        if unrunnable:
            # Said plainly and separately, because "your deliverable is broken" and "this
            # machine cannot open a browser" call for completely different actions, and a
            # reader who cannot tell them apart stops trusting the gate.
            print("%d could not be checked at all — the deliverable may be perfectly fine. "
                  "That is an environment problem, not a code problem." % unrunnable)
        if wrong_build:
            # The third population, and the one that looks most like success. Everything may
            # work in that environment; it is simply not running what you built.
            print("%d ran against an environment that is not the build under test. Nothing is "
                  "claimed about them either way — deploy this revision there first."
                  % wrong_build)
        return 1
    print("All %d declared outcome(s) hold, each proven by a check that can fail."
          % len(outcomes))
    return 0


# ----------------------------------------------------------------- controls
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

    # 1 — a satisfied outcome with a discriminating control is credited.
    rc, out = rc_of(repo("good", {"outcomes": [ok_outcome]}))
    chk("a holding outcome with a failing control passes", rc == 0 and "holds" in out)

    # 2 — a broken deliverable fails. Without this the gate is decoration.
    rc, out = rc_of(repo("broken", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 1", "control": "exit 1"}]}))
    chk("a failing check fails the gate", rc == 1 and "FAILS" in out)

    # 3 — a control that PASSES means the check cannot discriminate, so the outcome is not
    # credited even though the check itself exited 0. This is the vacuous-green case and
    # the single most important row here.
    rc, out = rc_of(repo("vacuous", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 0", "control": "exit 0"}]}))
    chk("a non-discriminating control yields NOT PROVEN, not a pass",
        rc == 1 and "NOT PROVEN" in out)

    # 4 — an outcome missing a required field is refused rather than skipped.
    rc, out = rc_of(repo("partial", {"outcomes": [
        {"name": "o", "check": "exit 0", "control": "exit 1"}]}))
    chk("an outcome with no stated expectation is REFUSED", rc == 1 and "REFUSED" in out)

    # 5 — no contract is reported honestly and does not block.
    rc, out = rc_of(repo("none", None))
    chk("a repo with no contract reports it and does not block",
        rc == 0 and "no deliverable contract" in out)

    # 6 — an unparseable contract is never a pass. Deleting the file and corrupting it must
    # not have opposite consequences by accident.
    rc, out = rc_of(repo("corrupt", "{not json"))
    chk("an unparseable contract fails closed", rc == 1 and "will not parse" in out)

    # 7 — an empty outcome list certifies everything, so it is a finding.
    rc, out = rc_of(repo("empty", {"outcomes": []}))
    chk("an empty contract is a finding, not a green run", rc == 1 and "zero outcomes" in out)

    # 9 — the verdict that started all this. A harness that cannot run must never produce a
    # sentence about the product. Saying "FAILS: submit enables once both fields are filled"
    # when no browser was available is a false claim, and it is the one that makes someone
    # delete the gate rather than install the dependency.
    rc, out = rc_of(repo("cannotrun", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 2", "control": "exit 1"}]}))
    chk("a check that could not run is CANNOT RUN, never FAILS",
        rc == 1 and "CANNOT RUN" in out and "FAILS" not in out)

    # 10 — same when it is the CONTROL that could not run. The check may have exited 0, but
    # with no working control there is no evidence it could have failed, so crediting the
    # outcome would be the vacuous green this gate exists to prevent.
    rc, out = rc_of(repo("ctlcannotrun", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 0", "control": "exit 2"}]}))
    chk("a control that could not run is CANNOT RUN, never a pass",
        rc == 1 and "CANNOT RUN" in out and "holds" not in out)

    # 11 — and it stays distinct in the summary. A reader who cannot tell "your page is
    # broken" from "this machine has no browser" takes the wrong action either way.
    chk("the summary separates unrunnable outcomes from failing ones",
        "environment problem, not a code problem" in out)

    # 8 — the three-field rule is enforced on `control` specifically. Control 4 removed
    # `expect`; an outcome can just as easily ship with no control at all, which would be
    # the natural way to write one and would silently disable the discrimination rule.
    rc, out = rc_of(repo("nocontrol", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 0"}]}))
    chk("an outcome with no control is REFUSED", rc == 1 and "REFUSED" in out)

    # 12 — BACKWARD COMPATIBILITY. A contract with no `environments` and no `env` on its
    # outcomes must behave exactly as it did before environments existed. Asserted, not
    # assumed: a project that never heard of this must not change behaviour under it.
    rc, out = rc_of(repo("plain", {"outcomes": [ok_outcome]}))
    chk("a contract with no environments behaves as before", rc == 0 and "holds" in out)

    # 13 — an outcome naming an environment the contract never declared is REFUSED, not run
    # against nothing. A typo in `env` would otherwise silently run the check unsubstituted.
    rc, out = rc_of(repo("unknownenv", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 0", "control": "exit 1", "env": "ghost"}]}))
    chk("an undeclared environment is REFUSED", rc == 1 and "REFUSED" in out)

    # 14 — {{vars}} are substituted, so ONE outcome declaration can read against a fixture
    # here and against the real thing wherever the user meets it.
    rc, out = rc_of(repo("vars", {
        "environments": {"e1": {"vars": {"base": "https://x.test/"}}},
        "outcomes": [{"name": "o", "expect": "e", "env": "e1",
                      "check": "test '{{base}}' = 'https://x.test'", "control": "exit 1"}]}))
    chk("environment vars are substituted, trailing slash trimmed",
        rc == 0 and "holds" in out)

    # 15 — THE LOAD-BEARING ONE. The environment is not running the build under test, and the
    # outcome WOULD pass there. It must not be credited: a green check about somebody else's
    # build is worse than a red one, because it gets filed as evidence.
    d = repo("wrongbuild", {
        "environments": {"e1": {"provenance": {"cmd": "echo 0000000000000000"}}},
        "outcomes": [{"name": "o", "expect": "e", "env": "e1",
                      "check": "exit 0", "control": "exit 1"}]})
    rc, out = rc_of(d)
    chk("an environment on a different build is refused though the check passes",
        rc == 1 and "WRONG BUILD" in out and "holds" not in out)

    # 16 — and it is NOT reported as a product failure. "Your feature is broken" and "you are
    # looking at a different build" send a reader to opposite places.
    chk("a different build is not reported as FAILS", "FAILS" not in out)

    # 17 — provenance that cannot be established is refused, never assumed good. An
    # unreachable probe must not read as "probably fine".
    rc, out = rc_of(repo("noprov", {
        "environments": {"e1": {"provenance": {"cmd": "exit 7"}}},
        "outcomes": [{"name": "o", "expect": "e", "env": "e1",
                      "check": "exit 0", "control": "exit 1"}]}))
    chk("unestablishable provenance is refused", rc == 1 and "WRONG BUILD" in out)

    # 18 — an environment that declares no provenance is NOT blocked. Not every product has a
    # revision to report, and demanding one would make the whole idea unusable for a built
    # binary or a rendered asset.
    rc, out = rc_of(repo("noclaim", {
        "environments": {"e1": {"vars": {"x": "1"}}},
        "outcomes": [{"name": "o", "expect": "e", "env": "e1",
                      "check": "exit 0", "control": "exit 1"}]}))
    chk("an environment claiming no provenance still runs", rc == 0 and "holds" in out)

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
    root = args[0] if args else os.getcwd()
    return report(root)


if __name__ == "__main__":
    sys.exit(main())
