#!/usr/bin/env python3
"""feedback-audit — is every piece of operator feedback still mechanically enforced?

    feedback-audit.py [root]     audit the tree
    feedback-audit.py --self-test  run the positive controls

WHY THIS EXISTS

Feedback gets applied in a commit and un-applied in a refactor six weeks later, and nobody
notices because no test was ever attached to the INSTRUCTION — only to the code that
happened to implement it. This repository has already watched that happen to a detector fix
that reached `hooks/` and never `kit/hooks/`.

So each item below pairs the operator's actual words with two probes:

  applied  — a probe that passes only while the instruction is honoured
  control  — a probe that must FAIL, proving the first one can tell the difference

An item whose control passes is reported NOT PROVEN and never credited, for the same reason
a gate whose control cannot fail is not a gate. The distinction matters more here than
anywhere else, because "all feedback applied" is precisely the claim nobody audits.

WHAT THIS CANNOT DO

It cannot tell you the feedback was applied WELL, or that the operator would agree the
implementation matches what they meant. It checks that the mechanism named in each row is
present and still discriminates. Where an item is prose rather than mechanism, it says so
rather than inventing a check.
"""
import json
import os
import re
import subprocess
import sys

EXPECTED_ITEMS = 8
EXPECTED_CONTROLS = 6


def run(cmd, cwd, stdin=None):
    """(exit_code, output). Never raises."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, input=stdin, timeout=600,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# --------------------------------------------------------------------- probes
def f1(root):
    """Quoted-literal false positives, without opening the bypass."""
    hook = os.path.join(root, "hooks", "deny-dangerous.sh")
    if not os.path.isfile(hook):
        return None, None, "hooks/deny-dangerous.sh is gone"
    inert = json.dumps({"tool_name": "Bash",
                        "tool_input": {"command": 'echo "rm -rf /"'}})
    real = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    a, _ = run("bash %s" % hook, root, stdin=inert)
    c, _ = run("bash %s" % hook, root, stdin=real)
    return a == 0, c != 0, "a quoted literal is allowed (%s); a real one is blocked (%s)" % (a, c)


def f2(root):
    """Guardrail self-protection removed — a tool may edit the hooks."""
    hook = os.path.join(root, "hooks", "deny-dangerous.sh")
    if not os.path.isfile(hook):
        return None, None, "hooks/deny-dangerous.sh is gone"
    edit = json.dumps({"tool_name": "Edit",
                       "tool_input": {"file_path": "/r/.claude/hooks/deny-dangerous.sh"}})
    push = json.dumps({"tool_name": "Bash",
                       "tool_input": {"command": "git push --force origin main"}})
    a, _ = run("bash %s" % hook, root, stdin=edit)
    c, _ = run("bash %s" % hook, root, stdin=push)
    return a == 0, c != 0, "editing a hook is allowed (%s); the hook still blocks a force push (%s)" % (a, c)


PRODUCTS = ("Griffin", "CEB", "Cocoa Asante", "tdi-international", "HookBrand",
            "OpenMontage", "brand_contract", "reference_images")


def f3(root):
    """Nothing in the plan is product-specific."""
    doc = read(root, "docs/agent-enforcement-matrix.md")
    if not doc:
        return None, None, "docs/agent-enforcement-matrix.md is gone"
    m = re.search(r"^## 3\. The plan(.*?)(^## 4\.|\Z)", doc, re.S | re.M)
    if not m:
        return None, None, "the plan section is gone"
    section = m.group(1)
    hits = [p for p in PRODUCTS if p in section]
    # Control: the same scan over text that DOES name a product must flag it. Without this,
    # a scanner with a broken pattern list reports clean on everything.
    ctl_hits = [p for p in PRODUCTS if p in "arm the gates in Griffin first"]
    return not hits, bool(ctl_hits), \
        "plan names %s; the scanner detects a planted name (%s)" % (hits or "no product", ctl_hits)


def f4(root):
    """A gate that opens the deliverable, not only the code."""
    acc = os.path.join(root, "benchmark", "gates", "acceptance.py")
    if not os.path.isfile(acc):
        return None, None, "benchmark/gates/acceptance.py is gone"
    a, _ = run("python3 %s --self-test" % acc, root)
    # Control: a contract whose check passes but whose control also passes must NOT be
    # credited. That is the vacuous-green case and the whole reason this gate exists.
    import tempfile
    d = tempfile.mkdtemp(prefix="fb-f4-")
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    with open(os.path.join(d, ".claude", "acceptance.json"), "w") as fh:
        json.dump({"outcomes": [{"name": "o", "expect": "e",
                                 "check": "exit 0", "control": "exit 0"}]}, fh)
    c, out = run("python3 %s %s" % (acc, d), root)
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return a == 0, (c != 0 and "NOT PROVEN" in out), \
        "acceptance controls pass (%s); a non-discriminating contract is refused (%s)" % (a, c)


def f5(root):
    """Pursue the goal until everything is done — and evidence must be about the task."""
    led = os.path.join(root, "bin", "ledger")
    if not os.path.isfile(led):
        return None, None, "bin/ledger is gone"
    import tempfile
    d = tempfile.mkdtemp(prefix="fb-f5-")
    run("git init -q . && git config user.email h@h && git config user.name h", d)
    with open(os.path.join(d, "plan.md"), "w") as fh:
        fh.write("- [ ] Implement OAuth token refresh\n")
    env = "CLAUDE_PROJECT_DIR=%s " % d
    run("%sbash %s init t1 --plan plan.md" % (env, led), d)
    open_rc, _ = run("%sbash %s open t1" % (env, led), d)
    with open(os.path.join(d, "groceries.txt"), "w") as fh:
        fh.write("grocery list\nmilk\neggs\n")
    ev_rc, _ = run("%sbash %s done t1 1 --evidence groceries.txt" % (env, led), d)
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    # applied: an open ledger refuses. control: irrelevant evidence cannot close a task.
    return open_rc == 1, ev_rc != 0, \
        "an open ledger exits %s; a grocery list cannot close an OAuth task (%s)" % (open_rc, ev_rc)


def f6(root):
    """A red flag must say the true thing: could-not-run is not the same as failed."""
    acc = os.path.join(root, "benchmark", "gates", "acceptance.py")
    if not os.path.isfile(acc):
        return None, None, "benchmark/gates/acceptance.py is gone"
    import tempfile, shutil
    def verdict(check, control):
        d = tempfile.mkdtemp(prefix="fb-f6-")
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        with open(os.path.join(d, ".claude", "acceptance.json"), "w") as fh:
            json.dump({"outcomes": [{"name": "o", "expect": "e",
                                     "check": check, "control": control}]}, fh)
        _rc, out = run("python3 %s %s" % (acc, d), root)
        shutil.rmtree(d, ignore_errors=True)
        return out
    cannot = verdict("exit 2", "exit 1")
    fails = verdict("exit 1", "exit 2")
    # applied: exit 2 reads as CANNOT RUN and never as FAILS.
    # control: the gate can still say FAILS — it has not simply stopped failing anything.
    return ("CANNOT RUN" in cannot and "FAILS" not in cannot), \
           ("CANNOT RUN" in fails or "FAILS" in fails), \
           "a harness error reads CANNOT RUN, not FAILS; the gate can still report a failure"


def f7(root):
    """Don't run the whole ladder for a one-line change."""
    sc = os.path.join(root, "bin", "scope")
    if not os.path.isfile(sc):
        return None, None, "bin/scope is gone"
    a, _ = run("python3 %s selftest" % sc, root)
    # Control: verify must actually CONSULT it. A perfect planner nothing calls is prose.
    wired = "scope" in read(root, "bin/verify")
    return a == 0 and wired, not ("scope" in read(root, "bin/ratchet")), \
        "scope controls pass (%s) and bin/verify consults it (%s)" % (a, wired)


def f8(root):
    """Both CI workflows install what the suite needs."""
    v = read(root, ".github/workflows/verify.yml")
    e = read(root, ".github/workflows/agent-evals.yml")
    if not v or not e:
        return None, None, "a workflow file is gone"
    both = "playwright@" in v and "playwright@" in e
    # Control: the same scan over a workflow that lacks it must come back false, so a
    # substring that matches everything cannot report success.
    ctl = "playwright@" not in read(root, ".github/workflows/README.md")
    return both, ctl, "verify.yml and agent-evals.yml both install the driver (%s)" % both


ITEMS = [
    ("F1", "fix the deny-dangerous literal FPs with the same _is_inert logic", f1),
    ("F2", "if any tool wants to modify the hooks, let them", f2),
    ("F3", "this must not be product specific, must apply for every new project", f3),
    ("F4", "the gates are not looking for a product — one gate that attacks the deliverable", f4),
    ("F5", "how will it pursue the goal until everything is done", f5),
    ("F6", "why is triggering that a red flag — noisy, and wrong from a product standpoint", f6),
    ("F7", "every little request runs the full suite, which is a waste of time", f7),
    ("F8", "fix those (the two items blocked on the operator)", f8),
]


def report(root):
    if len(ITEMS) != EXPECTED_ITEMS:
        print("FINDING: ITEMS holds %d rows, expected %d" % (len(ITEMS), EXPECTED_ITEMS))
        return 1
    print("operator feedback: %d item(s)" % len(ITEMS))
    print()
    bad = 0
    for ident, said, probe in ITEMS:
        try:
            applied, control, detail = probe(root)
        except Exception as exc:                          # noqa: BLE001
            applied, control, detail = None, None, "probe raised: %s" % exc
        if applied is None:
            verdict = "CANNOT RUN"
        elif not control:
            verdict = "NOT PROVEN"
        elif applied:
            verdict = "applied"
        else:
            verdict = "REGRESSED"
        if verdict != "applied":
            bad += 1
        print("  %-11s %s  “%s”" % (verdict, ident, said))
        print("              %s" % detail)
    print()
    if bad:
        print("%d of %d item(s) not established." % (bad, len(ITEMS)))
        return 1
    print("All %d item(s) still enforced, each by a probe shown able to fail." % len(ITEMS))
    return 0


# ----------------------------------------------------------------- controls
def selftest():
    passed = ran = 0
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def chk(label, cond):
        nonlocal passed, ran
        ran += 1
        if cond:
            passed += 1
            print("  ok    %s" % label)
        else:
            print("  FAIL  %s" % label)

    # 1 — the row count is declared, so deleting an item is a finding, not a shorter audit.
    chk("the item list is a declared literal", len(ITEMS) == EXPECTED_ITEMS)

    # 2/3 — the two probes most likely to rot silently, each shown to discriminate.
    a, c, _ = f1(root)
    chk("F1 probe separates a quoted literal from a real command", a is True and c is True)
    a, c, _ = f6(root)
    chk("F6 probe separates CANNOT RUN from FAILS", a is True and c is True)

    # 4 — the product-name scanner detects a planted name. A scanner with an empty pattern
    # list reports every document clean, which is the failure mode that matters.
    chk("the product-name scanner can see a planted name",
        any(p in "arm the gates in Griffin first" for p in PRODUCTS))

    # 5 — a probe pointed at a missing artifact yields CANNOT RUN, never "applied".
    import tempfile
    empty = tempfile.mkdtemp(prefix="fb-ctl-")
    applied, control, _ = f1(empty)
    chk("a missing artifact yields CANNOT RUN, not a pass", applied is None and control is None)

    # 6 — and report() turns that into a non-zero exit rather than crediting it.
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = report(empty)
    import shutil
    shutil.rmtree(empty, ignore_errors=True)
    chk("an empty tree fails the audit", rc == 1 and "CANNOT RUN" in buf.getvalue())

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
    root = args[0] if args else os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    return report(root)


if __name__ == "__main__":
    sys.exit(main())
