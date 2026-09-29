#!/usr/bin/env python3
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request

CONTRACT = ".claude/acceptance.json"
EVIDENCE = os.path.join(".claude", "evidence")
CANNOT_RUN, NOT_FOUND = 75, (126, 127)
FULL_SHA, HEX_RUN = re.compile(r"\b[0-9a-f]{40}\b"), re.compile(r"\b[0-9a-f]{7,39}\b")
SERVERS, LIVE = [], set()
limit = lambda name, default: float(os.environ.get(name) or default)
clean = lambda text: re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")

def kill_group(pgid, sig=signal.SIGKILL):
    try:
        os.killpg(pgid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def sh(cmd, cwd, extra=None, timeout=None):
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=dict(os.environ, **(extra or {})), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    LIVE.add(p.pid)
    try:
        out, _ = p.communicate(timeout=limit("ACCEPT_TIMEOUT", 120) if timeout is None else timeout)
        code = p.returncode
    except subprocess.TimeoutExpired:
        kill_group(p.pid)
        code = None
        try:
            out, _ = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out = b""
    LIVE.discard(p.pid)
    return code, out.decode("utf-8", "replace")

def tail(text, n=3):
    lines = [l.strip()[:200] for l in text.splitlines() if l.strip() and not re.match(r"\s*shot\s", l)]
    return "; it said: " + " | ".join(lines[-n:]) if lines else ""

def res(verdict, detail, **more):
    return dict(more, verdict=verdict, detail=detail)

def load(root):
    path = os.path.join(root, CONTRACT)
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, ["%s exists but will not parse (%s) - that is not a pass" % (CONTRACT, exc)]
    if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list):
        return None, ["%s has no 'outcomes' list" % CONTRACT]
    return data, []

def substitute(cmd, values):
    for k, v in values.items():
        cmd = cmd.replace("{{%s}}" % k, str(v).rstrip("/"))
    return cmd

def revision(out, head=""):
    if FULL_SHA.search(out):
        return FULL_SHA.search(out).group(0)
    runs = HEX_RUN.findall(out)
    lone = runs[0] if len(runs) == 1 else ""
    return lone if lone and (re.search("[a-f]", lone) or head.lower().startswith(lone.lower())) else None

def provenance(env, root, extra=None):
    spec = env.get("provenance")
    if not spec:
        return True, ""
    head = sh("git rev-parse HEAD", root, timeout=30)[1].strip()
    if not head or not spec.get("cmd"):
        return False, "provenance needs a readable local HEAD and a `cmd` that prints the running revision"
    code, out = sh(spec["cmd"], root, extra)
    if code != 0:
        return False, "the provenance probe %s" % ("never finished" if code is None else "exited %d" % code)
    m = re.search(spec["pattern"], out) if spec.get("pattern") else None
    sha = (m and m.group(1 if m.groups() else 0)) if spec.get("pattern") else revision(out, head)
    if not sha or len(sha) < 7:
        return False, "no unambiguous revision (%r) in the probe output: print the full 40-character sha, or declare a `pattern`" % sha
    n = min(len(sha), len(head))
    if sha[:n].lower() != head[:n].lower():
        return False, ("it is running %s, not the %s under test - anything that passed here would be "
                       "evidence about a different build" % (sha[:12], head[:12]))
    return True, "running %s, the revision under test" % sha[:12]

def started_at(pid):
    return sh("ps -o lstart= -p %d" % pid, None, timeout=5)[1].strip()

def record_servers(root):
    path = os.path.join(root, EVIDENCE, ".servers")
    if not SERVERS:
        return os.path.exists(path) and os.remove(path)
    with open(path, "w") as fh:
        fh.writelines("%d|%s\n" % (p.pid, started_at(p.pid)) for p in SERVERS)

def reap_stale(root):
    path = os.path.join(root, EVIDENCE, ".servers")
    try:
        with open(path) as fh:
            lines = fh.read().splitlines()
        os.remove(path)
    except OSError:
        return
    for line in lines:
        pgid, _, when = line.partition("|")
        if pgid.isdigit() and int(pgid) > 1 and started_at(int(pgid)) in (when, "") and kill_group(int(pgid), signal.SIGTERM):
            time.sleep(0.5)
            kill_group(int(pgid))
            print("reaped a server an earlier run left behind (process group %s)" % pgid)

def stop_servers():
    while SERVERS:
        p = SERVERS.pop()
        kill_group(p.pid, signal.SIGTERM)
        end = time.time() + 10
        while time.time() < end and (p.poll() is None or kill_group(p.pid, 0)):
            time.sleep(0.1)
        kill_group(p.pid)
        p.wait()
        LIVE.discard(p.pid)

def interrupted(signum, _frame):
    stop_servers()
    for pgid in list(LIVE):
        kill_group(pgid)
    sys.exit(128 + signum)

def answering(port):
    for host in ("localhost", "127.0.0.1"):
        try:
            socket.create_connection((host, int(port)), timeout=1).close()
            return "http://%s:%s" % (host, port)
        except OSError:
            pass
    return None

def is_ready(ready, root, extra):
    if not ready.startswith("/"):
        return sh(ready, root, extra, timeout=10)[0] == 0
    base = answering(extra["PORT"])
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base + ready, timeout=3).close()
        return True
    except Exception:
        return False

def boot(env, root, name, extra, left):
    if not env.get("start"):
        return True, ""
    if not env.get("ready"):
        return False, "declares `start` with no `ready` probe, so nothing says when it is up"
    values = dict(env.get("vars") or {}, port=extra["PORT"], base_url=extra["BASE_URL"])
    start, ready = substitute(env["start"], values), substitute(env["ready"], values)
    if is_ready(ready, root, extra):
        if env.get("reuse"):
            return True, "already up, reused as declared"
        return False, ("`ready` passes before `start` ran, so something else is already serving there and would "
                       "be checked instead of this build. Stop it, or declare \"reuse\": true if that is this build")
    with open(os.path.join(root, EVIDENCE, "server-%s.log" % clean(name)), "w") as log:
        p = subprocess.Popen(start, shell=True, cwd=root, stdin=subprocess.DEVNULL, stdout=log,
                             stderr=subprocess.STDOUT, env=dict(os.environ, **extra), start_new_session=True)
    SERVERS.append(p)
    LIVE.add(p.pid)
    record_servers(root)
    wait = min(limit("ACCEPT_READY_TIMEOUT", 120), left())
    deadline = time.time() + wait
    while time.time() < deadline:
        if p.poll() is not None:
            return False, "`start` exited %d before `ready` passed (see %s)" % (p.returncode, log.name)
        if is_ready(ready, root, extra):
            return True, "started, ready"
        time.sleep(0.5)
    return False, "`ready` never passed in %ds (see %s)" % (wait, log.name)

def bring_up(name, env, ctx):
    extra = {}
    if env.get("start") or env.get("port"):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = int(env.get("port") or s.getsockname()[1])
        extra = {"PORT": str(port), "BASE_URL": "http://localhost:%d" % port}
    up = boot(env, ctx["root"], name, extra, ctx["left"])
    if extra and up[0]:
        extra = dict(extra, BASE_URL=answering(extra["PORT"]) or extra["BASE_URL"])
    ctx["resolved"][name] = (up, provenance(env, ctx["root"], extra) if up[0] else None, extra)

def malformed(o):
    if not isinstance(o, dict):
        return "outcome is not an object"
    bad = [f for f in ("name", "expect", "check") if not (isinstance(o.get(f), str) and o[f].strip())]
    if bad:
        return "missing required field(s): %s" % ", ".join(bad)
    needs = o.get("needs", [])
    if not isinstance(needs, list) or not all(isinstance(n, str) for n in needs):
        return "`needs` must be a list of environment variable names"

def judge(o, ctx, shot, log):
    if malformed(o):
        return res("REFUSED", malformed(o))
    name, env = o.get("env"), {}
    if name:
        env = ctx["envs"].get(name)
        if not isinstance(env, dict):
            return res("REFUSED", "names environment '%s', which the contract does not declare" % name)
    if not isinstance(env.get("needs", []), list):
        return res("REFUSED", "environment '%s': `needs` must be a list of environment variable names" % name)
    absent = list(dict.fromkeys(n for n in list(o.get("needs", [])) + list(env.get("needs") or []) if not os.environ.get(n)))
    if absent:
        return res("BLOCKED", "needs %s (not set)" % ", ".join(absent), blocked=absent)
    if ctx["left"]() <= 0:
        return res("NO VERDICT", "the %ds run budget was spent before this outcome ran" % ctx["budget"])
    if name not in ctx["resolved"]:
        bring_up(name, env, ctx)
    up, prov, extra = ctx["resolved"][name]
    if not up[0]:
        return res("CANNOT RUN", "environment '%s' did not come up: %s" % (name, up[1]))
    if not prov[0]:
        return res("WRONG BUILD", "environment '%s': %s" % (name, prov[1]))
    values = dict(env.get("vars") or {}, port=extra.get("PORT", ""), base_url=extra.get("BASE_URL", ""))
    used = [0]

    def attempt(kind, cmd, extras=None):
        used[0] = max(1, min(limit("ACCEPT_TIMEOUT", 120), ctx["left"]()))
        code, out = sh(substitute(cmd, values), ctx["root"], dict(extra, **(extras or {})), used[0])
        log.append("$ %s\n%s\n[%s exit %s]\n\n" % (cmd, out, kind, "timeout" if code is None else code))
        return code, tail(out)

    code, said = attempt("check", o["check"], {"ACCEPT_SHOT": shot})
    if code is None:
        return res("NO VERDICT", "check still running at %ds" % used[0])
    if code == CANNOT_RUN:
        return res("CANNOT RUN", "the check exited %d (could not run), so nothing was learned about the deliverable%s" % (code, said))
    if code != 0:
        return res("FAILS", "check exited %d%s" % (code, said))
    if not o.get("control"):
        return res("holds", "check exit 0 (no control declared)")
    code, said = attempt("control", o["control"])
    if code is None:
        return res("NO VERDICT", "control still running at %ds" % used[0])
    if code == CANNOT_RUN:
        return res("CANNOT RUN", "the control exited %d (could not run), so the check is not shown able to fail%s" % (code, said))
    if code == 0 or code in NOT_FOUND:
        why = "the control passed (exit 0)" if code == 0 else "the control did not run (exit %d)" % code
        return res("NOT PROVEN", "%s - this check is not shown able to tell a broken artifact from a whole one%s" % (why, said))
    return res("holds", "check exit 0, control exit %d" % code)

def slugs(outcomes, envs):
    seen, out = {"server-" + clean(e) for e in envs}, []
    for i, o in enumerate(outcomes):
        s = clean(o.get("name") or "" if isinstance(o, dict) else "")[:60] or "outcome-%d" % i
        while s in seen:
            s = "%s-%d" % (s, i)
        seen.add(s)
        out.append(s)
    return out

def save(path, status, results, error=None):
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"contract": status, "outcomes": results, **({"error": error} if error else {})}, fh, indent=2)

def report(root, results_path=None):
    try:
        if results_path and os.path.exists(results_path):
            os.remove(results_path)
        return report_run(root, results_path)
    except Exception as exc:
        text = "%s: %s" % (type(exc).__name__, exc)
        print("FINDING: acceptance.py crashed (%s), so nothing is established" % text)
        save(results_path, "crashed", [], text)
        return 1
    finally:
        stop_servers()
        record_servers(root)

def report_run(root, results_path):
    contract, findings = load(root)
    if findings or contract is None or not contract["outcomes"]:
        state = "invalid" if findings else "absent" if contract is None else "empty"
        save(results_path, state, [])
        print("\n".join("FINDING: %s" % f for f in findings) if findings else
              "no deliverable contract (%s absent).\nNothing is claimed about whether this deliverable does what was "
              "asked.\nDeclare outcomes there to make this gate binding." % CONTRACT if contract is None else
              "FINDING: %s declares zero outcomes - an empty contract certifies everything" % CONTRACT)
        return 0 if state == "absent" else 1
    outcomes = contract["outcomes"]
    envs = contract.get("environments") if isinstance(contract.get("environments"), dict) else {}
    os.makedirs(os.path.join(root, EVIDENCE, "shots"), exist_ok=True)
    reap_stale(root)
    budget, began = limit("ACCEPT_BUDGET", 600), time.time()
    ctx = {"envs": envs, "root": root, "resolved": {}, "budget": int(budget), "left": lambda: began + budget - time.time()}
    print("deliverable contract: %d outcome(s)\n" % len(outcomes))
    results = []
    for o, slug in zip(outcomes, slugs(outcomes, envs)):
        log, shot = [], os.path.join(root, EVIDENCE, "shots", slug + ".png")
        if os.path.exists(shot):
            os.remove(shot)
        try:
            r = judge(o, ctx, shot, log)
        except Exception as exc:
            r = res("CANNOT RUN", "harness error: %s: %s" % (type(exc).__name__, exc))
        o = o if isinstance(o, dict) else {}
        if log:
            r["log"] = os.path.join(EVIDENCE, slug + ".log")
            with open(os.path.join(root, r["log"]), "w", encoding="utf-8") as fh:
                fh.write("".join(log))
        results.append(dict(r, name=o.get("name"), expect=o.get("expect"), controlled=bool(o.get("control")),
                            shot=shot if os.path.exists(shot) else None))
        print("  %-11s [%s] %s\n              expected: %s\n              %s%s" % (
            r["verdict"], o.get("env") or "here", o.get("name") or "(unnamed)", o.get("expect") or "(not stated)",
            r["detail"], "\n              full output: %s" % r["log"] if r.get("log") else ""))
    save(results_path, "ok", results)
    bad = [r for r in results if r["verdict"] != "holds"]
    count = lambda verdict: sum(1 for r in results if r["verdict"] == verdict)
    print("\n%s" % ("%d of %d outcome(s) not established." % (len(bad), len(results)) if bad
                    else "All %d declared outcome(s) hold." % len(results)))
    if count("CANNOT RUN"):
        print("%d could not be checked: an environment problem, not a code problem." % count("CANNOT RUN"))
    if blocked_on(results):
        print("blocked on: %s" % ", ".join(blocked_on(results)))
    loose = sum(1 for r in results if not r["controlled"])
    if loose and not bad:
        print("%d uncontrolled: no control shows them able to fail. Add one where a silent pass would be costly." % loose)
    return 1 if bad else 0

blocked_on = lambda results: list(dict.fromkeys(n for r in results for n in r.get("blocked", [])))

ABSENT = """product : NOT PROVEN - no product expectations are declared (.claude/acceptance.json is absent).
  Green engineering gates say the code is consistent, not that the product does what was asked.
  Before claiming done, write .claude/acceptance.json: one outcome per thing the user must be able
  to do or see, each checked against the running product.
    {"outcomes": [{"name": "...", "expect": "<what the user observes, in their words>",
                   "check": "<command that exercises the product: drive.mjs, curl, the CLI>"}]}
  A check exits 0 when the outcome holds, non-zero when it does not, and 75 when it could not run.
  Run the verified-autonomy:setup skill: it maps the product, writes the contract, starts the
  app and proves every outcome. Expectations often live somewhere the request does not point."""

def summarize(path):
    try:
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
    except (OSError, ValueError):
        return "open", ["product : acceptance.py wrote no results, so nothing is established"]
    status, outs = (r.get("contract"), r.get("outcomes")) if isinstance(r, dict) else (None, None)
    if status == "absent":
        return "absent", ABSENT.splitlines()
    if status == "crashed":
        return "open", ["product : acceptance.py crashed (%s) - nothing is established" % r.get("error")]
    if status != "ok":
        return "open", ["product : .claude/acceptance.json is %s - that is not a pass" % status]
    if not outs or not isinstance(outs, list) or not all(isinstance(o, dict) for o in outs):
        return "open", ["product : acceptance.py wrote malformed results - that is not a pass"]
    bad = [o for o in outs if o.get("verdict") != "holds"]
    if not bad:
        loose = sum(1 for o in outs if not o.get("controlled"))
        return "held", ["%d product expectation(s) hold%s" % (len(outs), ", %d uncontrolled" % loose if loose else "")]
    lines = ["product : %d of %d expectation(s) not established. Still open:" % (len(bad), len(outs))]
    lines += ["  - %s: %s  (%s: %s)" % (o.get("name"), o.get("expect"), o.get("verdict"), o.get("detail")) for o in bad]
    if blocked_on(bad):
        lines.append("blocked on: %s" % ", ".join(blocked_on(bad)))
    return "open", lines + ["Continue with them. If one is blocked, say what is blocking it."]

def selftest():
    import io
    import shutil
    import tempfile
    from contextlib import redirect_stdout
    from unittest.mock import patch

    tmp, me, passed, ran = tempfile.mkdtemp(prefix="acceptance-selftest-"), sys.modules[__name__], 0, 0

    def chk(label, cond):
        nonlocal passed, ran
        ran, passed = ran + 1, passed + bool(cond)
        print("  %s  %s" % ("ok  " if cond else "FAIL", label))

    def repo(name, contract=None):
        d = os.path.join(tmp, name)
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        if not os.path.exists(os.path.join(d, ".git")):
            sh("git init -q . && git config user.email h@h && git config user.name h && echo %s > seed && "
               "git add -A && git commit -qm seed" % name, d)
        if contract is not None:
            with open(os.path.join(d, CONTRACT), "w") as fh:
                fh.write(contract if isinstance(contract, str) else json.dumps(contract))
        return d

    def go(name, contract, env=None):
        d, rp, buf = repo(name, contract), os.path.join(tmp, name + ".json"), io.StringIO()
        with patch.dict(os.environ, env or {}), redirect_stdout(buf):
            code = report(d, rp)
        return code, buf.getvalue(), d, rp

    def out(check, control=None, **extra):
        return dict({"name": "o", "expect": "e", "check": check}, **({"control": control} if control else {}), **extra)

    def verdicts(run):
        return [r["verdict"] for r in json.load(open(run[3]))["outcomes"]]

    def one(check, control=None, env=None):
        run = go("one%d" % ran, {"outcomes": [out(check, control)]}, env)
        return verdicts(run)[0], run[1]

    for label, check, control, want, env in [
        ("a holding outcome with a failing control holds", "exit 0", "exit 1", "holds", None),
        ("a failing check FAILS", "exit 1", "exit 1", "FAILS", None),
        ("a control that passes is NOT PROVEN", "exit 0", "exit 0", "NOT PROVEN", None),
        ("exit 2 is a real failure (argparse, grep, pytest), not CANNOT RUN", "exit 2", None, "FAILS", None),
        ("a check that exits 75 is CANNOT RUN", "exit 75", "exit 1", "CANNOT RUN", None),
        ("a control that exits 75 is CANNOT RUN, not able to fail", "exit 0", "exit 75", "CANNOT RUN", None),
        ("a control not found (127) is NOT PROVEN, never able to fail", "exit 0", "exit 127", "NOT PROVEN", None),
        ("a control not executable (126) is NOT PROVEN", "exit 0", "exit 126", "NOT PROVEN", None),
        ("a check outliving ACCEPT_TIMEOUT is NO VERDICT", "sleep 5", None, "NO VERDICT", {"ACCEPT_TIMEOUT": "1"}),
        ("without a control a check still decides, reported uncontrolled", "exit 0", None, "holds", None),
    ]:
        chk(label, one(check, control, env)[0] == want)
    chk("the uncontrolled pass is named in the report", "1 uncontrolled" in one("exit 0")[1])

    run = go("malformed", {"outcomes": [{"name": "o", "check": "exit 0"}, "text", None, 7, ["x"],
                                        out("exit 0", "exit 1", env="ghost"), out("exit 0", needs="A")]})
    chk("a missing expectation, a non-object outcome, an undeclared env or bad `needs` is REFUSED, never holds",
        run[0] == 1 and verdicts(run) == ["REFUSED"] * 7)
    chk("no contract reports and does not block; an unreadable or empty one fails closed",
        go("none", None)[0] == 0 and go("bad", "{not json")[0] == 1 and go("empty", {"outcomes": []})[0] == 1)

    head = sh("git rev-parse HEAD", repo("prov"), timeout=30)[1].strip()
    echo = lambda s, **spec: {"provenance": dict(cmd="echo '%s'" % s, **spec)}
    envs = {"e1": {"vars": {"base": "https://x.test/"}}, "wrong": echo("0" * 40), "noprov": {"provenance": {"cmd": "exit 7"}},
            "tiny": echo(head, pattern=r"(\w)"), "dated": echo('{"built":"20260928","commit":"%s"}' % head),
            "dateonly": echo('{"built":"20260928"}'), "short": echo(head[:7]), "twohex": echo("20260928 " + head[:7])}
    run = go("prov", {"environments": envs, "outcomes": [dict(out("test '{{base}}' = 'https://x.test'", "exit 1"), env="e1")] +
                      [out("exit 0", "exit 1", env=e, name=e) for e in list(envs)[1:]]})
    chk("vars are substituted; a different, unestablishable or 1-char-captured build is WRONG BUILD",
        verdicts(run)[:4] == ["holds", "WRONG BUILD", "WRONG BUILD", "WRONG BUILD"])
    fake = "1234567" + "a" * 33
    chk("a lone all-digit short sha that prefixes HEAD is a revision; a lone date is not",
        revision("running 1234567", fake) == "1234567" and revision('{"built":"20260928"}', fake) is None)
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0)); srv.listen(1)
        base, ok = answering(srv.getsockname()[1]), False
        if base:
            host, port = base[len("http://"):].rsplit(":", 1)
            try:
                socket.create_connection((host, int(port)), timeout=1).close(); ok = True
            except OSError:
                ok = False
    chk("BASE_URL names a host the app actually answers on", ok)
    chk("a 40-hex sha beats a JSON date; a lone date or two hex runs is no revision; a lone 7-hex sha is",
        verdicts(run)[4:] == ["holds", "WRONG BUILD", "holds", "WRONG BUILD"])

    run = go("said", {"outcomes": [out("echo one; echo two; echo 'shot /x.png'; echo three; echo four; exit 1", "exit 1"), out("exit 1", "exit 1")]})
    rs = json.load(open(run[3]))["outcomes"]
    chk("a detail quotes the last 3 meaningful lines and skips drive's shot line",
        "two | three | four" in rs[0]["detail"] and "one" not in rs[0]["detail"] and "shot" not in rs[0]["detail"])
    chk("full output lands in .claude/evidence/<slug>.log; duplicate names get unique slugs",
        "one\ntwo" in open(os.path.join(run[2], rs[0]["log"])).read() and rs[0]["log"] != rs[1]["log"]
        and os.path.exists(os.path.join(run[2], rs[1]["log"])))

    run = go("needs", {"environments": {"cred": {"start": "touch started", "ready": "exit 1", "needs": ["VA_T_A"]}},
                       "outcomes": [out("touch ran", "exit 1", needs=["VA_T_A", "VA_T_B"]), out("touch ran", "exit 1", env="cred", name="p")]})
    chk("an unset `needs` is BLOCKED: nothing runs or starts, the summary says what blocks",
        verdicts(run) == ["BLOCKED"] * 2 and not any(os.path.exists(os.path.join(run[2], f)) for f in ("ran", "started"))
        and "needs VA_T_A, VA_T_B (not set)" in run[1] and "blocked on: VA_T_A, VA_T_B" in summarize(run[3])[1])
    chk("a `needs` that is set lets the check run",
        go("needsset", {"outcomes": [out('test -n "$VA_T_A"', "exit 1", needs=["VA_T_A"])]}, {"VA_T_A": "x"})[0] == 0)

    d, rp = repo("stale", {"outcomes": [out("exit 0", "exit 1")]}), os.path.join(tmp, "stale.json")
    with redirect_stdout(io.StringIO()):
        report(d, rp)
        first = summarize(rp)[0]
        with patch.object(me, "load", side_effect=RuntimeError("boom")):
            code = report(d, rp)
        crashed = summarize(rp)
        with patch.object(me, "judge", side_effect=RuntimeError("kaput")):
            report(d, rp)
        guarded = json.load(open(rp))["outcomes"][0]["verdict"]
        with patch.object(me, "load", side_effect=KeyboardInterrupt):
            try:
                report(d, rp)
            except KeyboardInterrupt:
                pass
        gone = not os.path.exists(rp)
    chk("a harness exception never leaves a stale green: the run is open, with the exception text",
        first == "held" and code == 1 and crashed[0] == "open" and "boom" in crashed[1][0] and gone
        and guarded == "CANNOT RUN")
    states = []
    for text in ('[1]', '{"contract":"ok","outcomes":["x"]}', '{"contract":"ok","outcomes":[]}', '{oops'):
        with open(rp, "w") as fh:
            fh.write(text)
        states.append(summarize(rp)[0])
    chk("results that are missing, malformed or not objects are never held", states + [summarize(rp + "x")[0]] == ["open"] * 5)

    run = go("group", {"outcomes": [out("sleep 30 & echo $! > pid; wait", "exit 1")]}, {"ACCEPT_TIMEOUT": "1"})
    time.sleep(0.3)
    chk("a check that times out has its whole process group killed, not just the shell",
        verdicts(run) == ["NO VERDICT"] and sh("kill -0 $(cat pid)", run[2], timeout=5)[0] != 0)
    began = time.time()
    run = go("budget", {"outcomes": [out("sleep 3"), out("exit 0", name="b"), out("exit 0", name="c")]}, {"ACCEPT_BUDGET": "1"})
    chk("a spent run budget makes the remaining outcomes NO VERDICT without running them",
        verdicts(run) == ["NO VERDICT"] * 3 and time.time() - began < 3 and "run budget" in run[1])

    same = 'test "$BASE_URL" = http://localhost:$PORT'
    run = go("ports", {"environments": {
        "a": {"start": "echo $PORT > a.port; touch up; exec sleep 60", "ready": "test -f up && " + same},
        "b": {"start": "echo {{port}} > b.port; exec sleep 60", "ready": "test -s b.port", "port": 45911}},
        "outcomes": [out(same + " && echo $PORT >> ports && test '{{port}}' = \"$PORT\"", "exit 1", env="a"),
                     out(same + " && echo $PORT >> ports", "exit 1", env="b", name="p")]})
    ports = open(os.path.join(run[2], "ports")).read().split()
    chk("each environment gets its own free $PORT and $BASE_URL in start, ready, check and {{port}}; a pinned port is kept",
        run[0] == 0 and ports == [open(os.path.join(run[2], f)).read().strip() for f in ("a.port", "b.port")]
        and ports[1] == "45911" and ports[0].isdigit() and ports[0] != ports[1])

    def local(start, ready, env=None, count=1):
        return go("local%d" % ran, {"environments": {"local": {"start": start, "ready": ready}},
                                    "outcomes": [out("exit 0", "exit 1", env="local", name="o%d" % i) for i in range(count)]}, env)

    run = local("echo run >> hits; echo $$ > pid; touch up; exec sleep 60", "test -f up", count=3)
    chk("a declared start is launched once, awaited, and stopped afterwards",
        run[0] == 0 and open(os.path.join(run[2], "hits")).read().count("run") == 1 and sh("kill -0 $(cat pid)", run[2], timeout=5)[0] != 0)
    chk("an app that will not start is CANNOT RUN, never FAILS or holds", verdicts(local("exit 3", "exit 1")) == ["CANNOT RUN"])
    run = local("exec sleep 60", "exit 1", {"ACCEPT_READY_TIMEOUT": "1"})
    chk("a `ready` that never passes is bounded by ACCEPT_READY_TIMEOUT", verdicts(run) == ["CANNOT RUN"] and "never passed in 1s" in run[1])
    run = local("touch started", "exit 0")
    chk("something already serving is CANNOT RUN unless reuse is declared, and is never restarted",
        verdicts(run) == ["CANNOT RUN"] and "already serving" in run[1] and not os.path.exists(os.path.join(run[2], "started")))

    run = go("evidence", {"outcomes": [out('test -n "$ACCEPT_SHOT" && touch "$ACCEPT_SHOT"', "exit 1"),
                                       out("exit 1", "exit 1", name="Search results", expect="lists only matches")]})
    rs, st = json.load(open(run[3]))["outcomes"], summarize(run[3])
    chk("each check is told where to save a screenshot; the summary names what is open; absence is never held",
        rs[0]["shot"].endswith(".claude/evidence/shots/o.png") and os.path.exists(rs[0]["shot"]) and st[0] == "open"
        and any("Search results: lists only matches" in l for l in st[1]) and summarize(go("absent", None)[3])[0] == "absent")

    shutil.rmtree(tmp, ignore_errors=True)
    expected = 31
    print("\nSELF-TEST %s" % ("PASSED  (%d checks)" % expected if passed == ran == expected else "FAILED  (%d of %d checks)" % (passed, expected)))
    return 0 if passed == ran == expected else 1

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
            return 2
        results, args = args[i + 1], args[:i] + args[i + 2:]
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    return report(args[0] if args else os.getcwd(), results)

if __name__ == "__main__":
    sys.exit(main())
