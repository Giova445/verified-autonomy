#!/usr/bin/env python3
import importlib.util
import json
import os
import random
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
HOOKS = os.environ.get("DENY_HOOKS_DIR") or os.path.join(PLUGIN, "hooks")
HOOK = os.path.join(HOOKS, "deny-dangerous.sh")
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import deny_audit_set
import deny_rule_cases

TRAILER = "Co-Authored-By: a <a@b>"
GH_MAP = {
    "99": "main", "9": "main", "https://github.com/o/r/pull/99": "main", "": "main",
    "77": "release/1.2", "12": "develop", "feature/y": "develop",
}
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    open(log, "a").write(json.dumps(a) + "\\n")
if a[:2] != ["pr", "view"]:
    sys.exit(1)
sel, i, rest = "", 2, a[2:]
while i < len(a):
    if a[i] in ("-R", "--json", "-q"):
        i += 2
    elif a[i].startswith("-"):
        i += 1
    else:
        sel = a[i]
        break
base = json.load(open(os.environ["FAKE_GH_MAP"])).get(sel)
if base is None:
    sys.exit(1)
print(base)
"""

REPO_FILES = {
    "feat": {".claude/protected-branches": "# protected\nmain\nmaster\nrelease/*\n"},
    "main": {".claude/protected-branches": "main\nmaster\nrelease/*\n", "README.md": "readme\n"},
    "plain": {},
    "trail": {".claude/protected-branches": "main\nmaster\n", ".claude/forbidden-trailers": "# no co-authors\n",
              "msg.txt": "fix\n\n" + TRAILER + "\n", "clean.txt": "fix: nothing to see\n"},
    "attr": {".claude/settings.json": '{"attribution": {"commit": ""}}'},
    "attr-off": {".claude/settings.json": '{"attribution": {"commit": "keep"}}', "msg.txt": "fix\n\n" + TRAILER + "\n"},
    "badjson": {".claude/settings.json": "{not json"},
    "custom": {".claude/forbidden-trailers": "Signed-off-by\n"},
    "nobranches": {".claude/protected-branches": "# nothing is protected here\n"},
}
REPO_BRANCH = {"main": "main"}


class Cases:
    def __init__(self):
        self.items = []

    def allow(self, cmd, *repos, gh=None, adjacent=False):
        self.items.append(dict(cmd=cmd, exit=0, reason="", repos=repos or ("feat",), gh=gh, adjacent=adjacent))

    def deny(self, cmd, reason, *repos, gh=None):
        self.items.append(dict(cmd=cmd, exit=2, reason=reason, repos=repos or ("feat",), gh=gh, adjacent=False))

    def adjacent(self, cmd, *repos):
        self.allow(cmd, *repos, adjacent=True)


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def make_repos(base):
    repos = {}
    for name, files in REPO_FILES.items():
        path = os.path.join(base, name)
        os.makedirs(path)
        sh(["git", "init", "-q", "."], path)
        sh(["git", "symbolic-ref", "HEAD", "refs/heads/" + REPO_BRANCH.get(name, "feature/t")], path)
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(path, rel)), exist_ok=True)
            with open(os.path.join(path, rel), "w") as f:
                f.write(text)
        repos[name] = path
    return repos


def hook_env(base, repo, gh):
    binp = os.path.join(base, "bin")
    mapping = os.path.join(base, "gh-map.json")
    with open(mapping, "w") as f:
        json.dump(gh if gh is not None else GH_MAP, f)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=repo, FAKE_GH_MAP=mapping, PATH=binp + os.pathsep + os.environ["PATH"])
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return env


def run_hook(payload, env, cwd, hook=None):
    start = time.perf_counter()
    p = subprocess.run(["bash", hook or HOOK], input=payload, text=True, capture_output=True, env=env, cwd=cwd, timeout=30)
    return p.returncode, p.stderr, (time.perf_counter() - start) * 1000


def bash_payload(cmd, cwd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})


class Tally:
    def __init__(self):
        self.checks, self.failures, self.times = 0, [], []

    def check(self, label, ok, detail=""):
        self.checks += 1
        if not ok:
            self.failures.append((label, detail))
            print("  FAIL  %s\n        %s" % (label, detail))


def judge_cases(cases, repos, base, tally):
    for c in cases.items:
        for repo in c["repos"]:
            code, err, ms = run_hook(bash_payload(c["cmd"], repos[repo]), hook_env(base, repos[repo], c["gh"]), repos[repo])
            tally.times.append(ms)
            label = "%s [%s] %r" % ("allow" if c["exit"] == 0 else "deny ", repo, c["cmd"][:90])
            ok = code == c["exit"] and (c["reason"] in err if c["exit"] == 2 else err == "")
            tally.check(label, ok, "want exit %d %r got exit %d stderr %r" % (c["exit"], c["reason"], code, err.strip()[:160]))


def robustness(repos, base, tally):
    repo = repos["feat"]
    env = hook_env(base, repo, None)
    other = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x", "command": "git push origin main"}})
    checks = [
        ("a non-Bash tool is not judged", other, 0, ""),
        ("an empty command is allowed", bash_payload("", repo), 0, ""),
        ("a missing command is allowed", json.dumps({"tool_name": "Bash", "tool_input": {}}), 0, ""),
        ("input that is not JSON fails closed", "not json", 2, "deny hook error"),
        ("a non-string command fails closed", json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}}), 2, "deny hook error"),
        ("no hook input at all fails closed", "", 2, "deny hook error"),
    ]
    for label, payload, want, reason in checks:
        code, err, _ = run_hook(payload, env, repo)
        tally.check(label, code == want and reason in err, "got exit %d stderr %r" % (code, err.strip()[:160]))
    huge = "echo " + "x" * 2_000_000
    code, err, ms = run_hook(bash_payload(huge, repo), env, repo)
    tally.check("a 2 MB command is judged, not rejected by an argv limit", code == 0 and ms < 8000, "exit %d in %.0f ms %r" % (code, ms, err[:100]))
    code, err, _ = run_hook(bash_payload(huge + "; git push origin main", repo), env, repo)
    tally.check("a danger after 2 MB of text is still found", code == 2 and "protected branch" in err, "exit %d %r" % (code, err[:100]))
    code, err, _ = run_hook(bash_payload("echo " + '"$(' * 400 + "x" + ')"' * 400, repo), env, repo)
    tally.check("absurd nesting fails closed with a reason", code == 2 and "deny hook error" in err, "exit %d %r" % (code, err[:100]))
    nested = "echo x"
    for _ in range(10):
        nested = "bash -c " + shlex.quote(nested)
    code, err, _ = run_hook(bash_payload(nested, repo), env, repo)
    tally.check("ten nested shells are refused as too deep to inspect", code == 2 and "too deeply" in err, "exit %d %r" % (code, err[:100]))
    code, err, _ = run_hook(bash_payload("bash -c \"bash -c 'echo x'\"", repo), env, repo)
    tally.check("a shell string inside a shell string is read", code == 0, "exit %d %r" % (code, err[:100]))
    broken = os.path.join(base, "broken-hooks")
    shutil.copytree(HOOKS, broken, ignore=shutil.ignore_patterns("__pycache__"))
    with open(os.path.join(broken, "inert-mask.py"), "a") as f:
        f.write("\nthis is not python\n")
    code, err, _ = run_hook(bash_payload("ls", repo), env, repo, os.path.join(broken, "deny-dangerous.sh"))
    tally.check("a broken rules file fails closed with a reason", code == 2 and "deny hook error" in err, "exit %d %r" % (code, err[:160]))
    code, err, _ = run_hook(other, env, repo, os.path.join(broken, "deny-dangerous.sh"))
    tally.check("a broken rules file never blocks a non-Bash tool", code == 0, "exit %d %r" % (code, err[:160]))
    code, err, _ = run_hook("not json", env, repo, os.path.join(broken, "deny-dangerous.sh"))
    tally.check("a broken rules file with unreadable input fails closed", code == 2 and "deny hook error" in err, "exit %d %r" % (code, err[:160]))
    os.remove(os.path.join(broken, "deny-rules.py"))
    code, err, _ = run_hook(bash_payload("ls", repo), env, repo, os.path.join(broken, "deny-dangerous.sh"))
    tally.check("a missing rules file fails closed with a reason", code == 2 and "deny hook error" in err, "exit %d %r" % (code, err[:160]))
    code, err, _ = run_hook(other, env, repo, os.path.join(broken, "deny-dangerous.sh"))
    tally.check("a missing rules file never blocks a non-Bash tool", code == 0 and err == "", "exit %d %r" % (code, err[:160]))
    empty = os.path.join(base, "no-python")
    os.makedirs(empty, exist_ok=True)
    for label, payload, want in (("Bash", bash_payload("ls", repo), 2), ("a non-Bash tool", other, 0)):
        p = subprocess.run([shutil.which("bash"), HOOK], input=payload, text=True, capture_output=True,
                           env=dict(env, PATH=empty), cwd=repo, timeout=30)
        tally.check("no python3 on PATH: %s exits %d" % (label, want), p.returncode == want and (want == 0 or "deny hook error" in p.stderr),
                    "exit %d %r" % (p.returncode, p.stderr[:160]))
    log = os.path.join(base, "gh.log")
    env_log = dict(env, FAKE_GH_LOG=log)
    for cmd in ("git push origin feature/x", "gh pr view 99", "gh pr create --title x", "ls"):
        run_hook(bash_payload(cmd, repo), env_log, repo)
    tally.check("gh is not consulted unless a merge is attempted", not os.path.exists(log), "gh was called")
    run_hook(bash_payload("gh pr merge 12 --squash", repo), env_log, repo)
    called = os.path.exists(log) and "12" in open(log).read()
    tally.check("gh is consulted for a merge, with the selector", called, "no gh call recorded")


def load_rules():
    spec = importlib.util.spec_from_file_location("deny_rules_under_test", os.path.join(HOOKS, "deny-rules.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Timeout(Exception):
    pass


def fuzz(base, tally, count=1500):
    rules = load_rules()
    alphabet = ["git", "push", "origin", "main", "rm", "-rf", "/", "'", '"', "`", "$(", ")", "(", "{", "}", ";", "&&", "||", "|", "&",
                "<<", "EOF", "\n", " ", "#", "\\", "$", "${", "<", ">", "<<<", "-c", "bash", "sh", "echo", "*", "~", "=", "$'", "))", "$(("]
    rng = random.Random(20260928)
    ctx_root = os.path.join(base, "feat")

    def alarm(*_):
        raise Timeout()

    signal.signal(signal.SIGALRM, alarm)
    bad = []
    for _ in range(count):
        text = "".join(rng.choice(alphabet) + rng.choice(["", " "]) for _ in range(rng.randint(1, 30)))
        signal.alarm(5)
        try:
            rules.check(text, rules.Ctx(ctx_root, ctx_root))
        except rules.Deny:
            pass
        except RecursionError:
            pass
        except Timeout:
            bad.append((text, "hung"))
        except Exception as e:
            bad.append((text, "%s: %s" % (type(e).__name__, e)))
        finally:
            signal.alarm(0)
    tally.check("%d random shell fragments never crash or hang the parser" % count, not bad, repr(bad[:3]))


def latency(tally):
    times = sorted(tally.times)
    p50 = statistics.median(times)
    p95 = times[int(len(times) * 0.95) - 1]
    print("\n  latency per call over %d runs: p50 %.0f ms  p95 %.0f ms  max %.0f ms" % (len(times), p50, p95, times[-1]))
    tally.check("median latency stays under 200 ms", p50 < 200, "p50 %.0f ms" % p50)


def main():
    if not shutil.which("git") or not shutil.which("bash") or not os.path.isfile(HOOK):
        print("CANNOT RUN: needs bash, git and %s" % HOOK)
        return 2
    base = tempfile.mkdtemp(prefix="deny-cases.", dir=os.environ.get("TMPDIR"))
    try:
        binp = os.path.join(base, "bin")
        os.makedirs(binp)
        with open(os.path.join(binp, "gh"), "w") as f:
            f.write(FAKE_GH.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        os.chmod(os.path.join(binp, "gh"), 0o755)
        repos = make_repos(base)
        cases, tally = Cases(), Tally()
        deny_audit_set.build(cases.allow, cases.deny, cases.adjacent)
        deny_rule_cases.build(cases.allow, cases.deny, cases.adjacent)
        judge_cases(cases, repos, base, tally)
        robustness(repos, base, tally)
        fuzz(base, tally)
        latency(tally)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    adjacent = [c["cmd"] for c in cases.items if c["adjacent"]]
    print("\n  %d adjacent commands are deliberately allowed (outside the rule list)" % len(adjacent))
    print("\ndeny-cases (%d checks)" % tally.checks)
    return 1 if tally.failures else 0


if __name__ == "__main__":
    sys.exit(main())
