#!/usr/bin/env python3
"""kit-sync — is what the kit SHIPS the same as what this repository TESTS?

    kit-sync.py [root]        report drift between kit/ and the tree it mirrors
    kit-sync.py --self-test   run the positive controls

WHY THIS EXISTS

This repository has hit the same failure twice and recorded it once:

  "hooks/scan-diff-cheats.sh: the recall fix landed in hooks/ and never reached
   kit/hooks/, so every number published about the detector described a file nobody
   installed."                                    — evals/evals_suites.py

That note treated it as one file's accident. It is not. Measured on 2026-09-15, before
this gate existed, `kit/bin/verify` was 25 lines behind `bin/verify` and missing the
`attempts` hoist — the fix whose absence, in its own words, made the runner "certify GREEN
on exactly the unreadable configs the branch exists to refuse". `kit/bin/holdout` was 27
lines behind. Three tools had no kit copy at all.

Everything this repository proves about a gate, it proves about the root copy. Every project
that installs the kit runs the kit copy. When those differ, the evidence describes a file
nobody has.

WHAT IS CHECKED, IN THREE DIRECTIONS

  1. a declared pair whose two files DIFFER        — the kit ships something untested
  2. a declared pair whose kit file is MISSING     — the kit ships nothing at all
  3. a file under a mirrored directory that is NOT declared — drift the other way: something
     appeared in the kit that nothing here knows to keep in sync

Direction 3 is the one a simpler gate would omit, and it is the one that lets a stale copy
live in the kit indefinitely without ever being compared to anything.

WHY THE PAIR LIST IS A LITERAL

It is NOT produced by walking kit/. If it were, deleting a file from the kit would delete
its own requirement to match, and the gate would go green having checked less — the
expectation-derived-from-subject defect this repository has now hit seven times. The list
below is the declaration of what the kit is supposed to ship. A file that vanishes from the
kit is a FINDING against this list, not a shorter list.
"""
import filecmp
import os
import sys

# (path under kit/, path under the repo root). Declared, never derived.
PAIRS = [
    ("bin/ambiguity", "bin/ambiguity"),
    ("bin/holdout", "bin/holdout"),
    ("bin/ledger", "bin/ledger"),
    ("bin/mutate-changed", "bin/mutate-changed"),
    ("bin/ratchet", "bin/ratchet"),
    ("bin/ruff-changed", "bin/ruff-changed"),
    ("bin/test-delta", "bin/test-delta"),
    ("bin/verify", "bin/verify"),
    ("bin/arm", "bin/arm"),
    ("hooks/deny-dangerous.sh", "hooks/deny-dangerous.sh"),
    ("hooks/inert-mask.py", "hooks/inert-mask.py"),
    ("hooks/scan-diff-cheats.sh", "hooks/scan-diff-cheats.sh"),
    ("hooks/session-start.sh", "hooks/session-start.sh"),
    ("hooks/stop-gate.sh", "hooks/stop-gate.sh"),
    ("gates/acceptance.py", "benchmark/gates/acceptance.py"),
    ("gates/drive.mjs", "benchmark/gates/drive.mjs"),
]

# Files that legitimately exist only in the kit, with the reason. Anything under a mirrored
# directory that is neither in PAIRS nor here is drift and is reported.
KIT_ONLY = {
    "hooks/gate.sh": "the Codex-side wrapper; it has no root counterpart by design",
}

# Directories whose contents are mirrored. Used only for direction 3.
MIRRORED = ("bin", "hooks", "gates")

EXPECTED_PAIRS = 16
EXPECTED_CONTROLS = 7


def audit(root, pairs=None, kit_only=None, mirrored=None):
    """Return a list of findings. Empty means the kit ships what this repo tests."""
    pairs = PAIRS if pairs is None else pairs
    kit_only = KIT_ONLY if kit_only is None else kit_only
    mirrored = MIRRORED if mirrored is None else mirrored
    findings = []
    declared = set()

    for kit_rel, root_rel in pairs:
        declared.add(kit_rel)
        kit_path = os.path.join(root, "kit", kit_rel)
        root_path = os.path.join(root, root_rel)
        if not os.path.isfile(root_path):
            findings.append("%s is declared but absent from the repository" % root_rel)
            continue
        if not os.path.isfile(kit_path):
            findings.append("kit/%s is missing — the kit ships nothing for %s"
                            % (kit_rel, root_rel))
            continue
        # shallow=False: same size and mtime is not same content, and a copy made by
        # `install -m` preserves neither reliably.
        if not filecmp.cmp(kit_path, root_path, shallow=False):
            findings.append("kit/%s differs from %s — installed projects run the kit copy, "
                            "and nothing here tests it" % (kit_rel, root_rel))

    # Direction 4: the shipped config and contract name tools by path. Every one of them
    # has to be a file the kit actually ships, or an agent that follows the instructions it
    # was given hits "command not found" — and the gate ladder reports a failure whose cause
    # is that the tool was never installed, not that the code is wrong.
    referenced = set()
    for rel in ("gates.json", "AGENTS.md.template"):
        path = os.path.join(root, "kit", rel)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            findings.append("kit/%s is unreadable — cannot tell which tools it names" % rel)
            continue
        for m in __import__("re").findall(r"\bbin/([a-z][a-z0-9-]*)", text):
            referenced.add(m)
    shipped = {k.split("/", 1)[1] for k, _ in pairs if k.startswith("bin/")}
    for tool in sorted(referenced - shipped):
        findings.append("the shipped config names bin/%s but the kit does not ship it — an "
                        "agent following those instructions gets command-not-found" % tool)

    # Direction 3: something in a mirrored directory that nothing is keeping in sync.
    for d in mirrored:
        base = os.path.join(root, "kit", d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            rel = "%s/%s" % (d, name)
            if not os.path.isfile(os.path.join(base, name)):
                continue
            if rel in declared or rel in kit_only:
                continue
            findings.append("kit/%s is shipped but undeclared — nothing compares it to "
                            "anything, so it can go stale silently" % rel)
    return findings


def report(root):
    if len(PAIRS) != EXPECTED_PAIRS:
        print("FINDING: PAIRS holds %d entries, expected %d — update both deliberately"
              % (len(PAIRS), EXPECTED_PAIRS))
        return 1
    findings = audit(root)
    print("kit sync: %d declared pair(s), %d kit-only file(s)" % (len(PAIRS), len(KIT_ONLY)))
    print()
    if not findings:
        print("The kit ships exactly what this repository tests.")
        return 0
    for f in findings:
        print("FINDING: %s" % f)
    print()
    print("%d finding(s). Every project installed from this kit runs these files; the "
          "evidence in this repository describes the other copies." % len(findings))
    return 1


# ----------------------------------------------------------------- controls
def selftest():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="kit-sync-selftest-")
    passed = ran = 0

    def chk(label, cond):
        nonlocal passed, ran
        ran += 1
        if cond:
            passed += 1
            print("  ok    %s" % label)
        else:
            print("  FAIL  %s" % label)

    def build(name, kit_body, root_body, extra_kit=None):
        d = os.path.join(tmp, name)
        os.makedirs(os.path.join(d, "kit", "bin"), exist_ok=True)
        os.makedirs(os.path.join(d, "bin"), exist_ok=True)
        if kit_body is not None:
            open(os.path.join(d, "kit", "bin", "tool"), "w").write(kit_body)
        if root_body is not None:
            open(os.path.join(d, "bin", "tool"), "w").write(root_body)
        for n, b in (extra_kit or {}).items():
            open(os.path.join(d, "kit", "bin", n), "w").write(b)
        return d

    p = [("bin/tool", "bin/tool")]

    # 1 — identical copies are clean. Without this the gate could be stuck on "drift".
    d = build("same", "same\n", "same\n")
    chk("identical kit and root copies produce no finding",
        audit(d, p, {}, ("bin",)) == [])

    # 2 — the real failure: the kit copy is behind. This is what shipped a verify missing
    # its fail-closed fix to every installed project.
    d = build("drift", "old\n", "new\n")
    f = audit(d, p, {}, ("bin",))
    chk("a kit copy that differs is caught", len(f) == 1 and "differs from" in f[0])

    # 3 — declared but the kit has no copy at all.
    d = build("missing", None, "new\n")
    f = audit(d, p, {}, ("bin",))
    chk("a declared file missing from the kit is caught",
        len(f) == 1 and "ships nothing" in f[0])

    # 4 — direction 3. A file in the kit that nothing declares can go stale forever, and a
    # gate built only from the declared list would never look at it.
    d = build("undeclared", "x\n", "x\n", extra_kit={"stowaway": "y\n"})
    f = audit(d, p, {}, ("bin",))
    chk("an undeclared file in the kit is caught",
        len(f) == 1 and "undeclared" in f[0])

    # 5 — the pair is declared but the ROOT file is gone. Silently dropping the pair would
    # let a deleted tool keep a stale kit copy alive with nothing to compare against.
    d = build("norootfile", "x\n", None)
    f = audit(d, p, {}, ("bin",))
    chk("a declared pair with no root file is caught",
        len(f) == 1 and "absent from the repository" in f[0])

    # 6 — content, not metadata. Two files of equal size whose bytes differ must be caught;
    # a shallow comparison passes this and would miss a one-character sabotage.
    d = build("samesize", "aaaa\n", "aaab\n")
    f = audit(d, p, {}, ("bin",))
    chk("equal-size files with different bytes are caught",
        len(f) == 1 and "differs from" in f[0])

    # 7 — direction 4. The shipped gate config names a tool the kit does not ship. Measured
    # on the real tree before this existed: kit/gates.json named bin/test-delta, bin/holdout,
    # bin/mutate-changed and bin/ambiguity, and install.sh installed none of them.
    d = build("names", "x\n", "x\n")
    open(os.path.join(d, "kit", "gates.json"), "w").write(
        '{"deferred":[{"name":"t","cmd":"bin/never-shipped"}]}')
    f = audit(d, p, {}, ("bin",))
    chk("a config naming a tool the kit does not ship is caught",
        len(f) == 1 and "command-not-found" in f[0])

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
    root = args[0] if args else os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    return report(root)


if __name__ == "__main__":
    sys.exit(main())
