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
import subprocess
import sys

CONTRACT = ".claude/acceptance.json"
REQUIRED = ("name", "expect", "check", "control")
TIMEOUT = int(os.environ.get("ACCEPT_TIMEOUT", "300"))

# Declared independently of the control bodies below. Deriving this from the list of
# controls would mean deleting a control also deletes the expectation that it ran.
EXPECTED_CONTROLS = 8


def run(cmd, cwd):
    """Exit code of cmd, or None if it never produced one."""
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, timeout=TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode
    except subprocess.TimeoutExpired:
        return None


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


def judge(outcome, root):
    """(verdict, detail) for one declared outcome."""
    missing = [f for f in REQUIRED if not outcome.get(f)]
    if missing:
        return "REFUSED", "missing required field(s): %s" % ", ".join(missing)

    rc_check = run(outcome["check"], root)
    if rc_check is None:
        return "NO VERDICT", "check still running at %ss" % TIMEOUT
    rc_control = run(outcome["control"], root)
    if rc_control is None:
        return "NO VERDICT", "control still running at %ss" % TIMEOUT

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

    print("deliverable contract: %d outcome(s)" % len(outcomes))
    print()
    bad = 0
    for o in outcomes:
        verdict, detail = judge(o, root)
        if verdict != "holds":
            bad += 1
        print("  %-11s %s" % (verdict, o.get("name") or "(unnamed)"))
        print("              expected: %s" % (o.get("expect") or "(not stated)"))
        print("              %s" % detail)
    print()
    if bad:
        print("%d of %d outcome(s) not established." % (bad, len(outcomes)))
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

    # 8 — the three-field rule is enforced on `control` specifically. Control 4 removed
    # `expect`; an outcome can just as easily ship with no control at all, which would be
    # the natural way to write one and would silently disable the discrimination rule.
    rc, out = rc_of(repo("nocontrol", {"outcomes": [
        {"name": "o", "expect": "e", "check": "exit 0"}]}))
    chk("an outcome with no control is REFUSED", rc == 1 and "REFUSED" in out)

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
