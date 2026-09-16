#!/usr/bin/env python3
"""arm-surface — propose a `surface` for each gate that already names its own directory.

    arm surface [dir]        (this is the helper `bin/arm surface` calls)
    arm-surface.py --self-test

WHY THIS EXISTS

Scope selection is opt-in by declaration, and measured across this machine no gate anywhere
declares a `surface` — so `bin/scope` is installed, wired into the runner, and completely
inert. The planner was never the missing piece. The missing piece was that somebody had to
hand-edit a config, and nobody did, which is the same reason `.claude/gates.json` itself
existed in 1 of 270 project directories.

NOTHING HERE IS INFERRED

A gate whose command reads `cd griffin-chatbot-frontend && npx jest` has already told you
which directory it covers. This reads that back. A gate with no `cd` gets NO surface, which
means it always runs.

Both defaults point the same way. `bin/scope` treats a changed file matching no declared
surface as a coverage hole and escalates the entire ladder, so under-declaring costs time
and never coverage. Guessing a surface from file extensions, or from what a test happens to
import, would point the other way — and a wrong guess there silently stops running a gate.

It writes `.claude/gates.json.surfaced` beside the original and never over it, the same rule
`arm write` follows. Applying it is a decision, not a side effect of looking at it.
"""
import json
import os
import re
import sys

# A `cd` in COMMAND POSITION, not one appearing inside quoted data. The first version
# matched `cd` anywhere, so `grep -r "cd fixtures" .` proposed fixtures/** — and a wrong
# surface is the one failure this tool must not have: that gate would then run ONLY when
# fixtures/** changed, silently skipping every other change. Requiring a separator or end
# of string after the path rejects the data cases and still accepts a directory named
# inside a wrapper (`bash -c 'cd web && tsc'`), which real configs use.
CD = re.compile(r"\bcd\s+([A-Za-z0-9._/-]+)\s*(?:&&|;|$)")

EXPECTED_CONTROLS = 9


def plan(root, gates):
    """(gates_with_surfaces, notes, changed). Mutates copies, never the input."""
    out, notes, changed = [], [], 0
    for g in gates:
        g = dict(g)
        name = g.get("name", "?")
        if g.get("surface"):
            notes.append(("keep", name, "already declares %s" % g["surface"]))
            out.append(g)
            continue
        m = CD.search(g.get("cmd") or "")
        if not m:
            notes.append(("no cd", name, "names no directory — always runs"))
            out.append(g)
            continue
        path = m.group(1).rstrip("/")
        # `cd .` and `cd ..` describe the whole repo or its parent; neither narrows
        # anything, and claiming them would make every file "covered" and disable the
        # escalation that keeps this safe.
        if path in (".", "..") or path.startswith("/"):
            notes.append(("skip", name, "'%s' does not narrow anything" % path))
            out.append(g)
            continue
        if not os.path.isdir(os.path.join(root, path)):
            notes.append(("skip", name, "'%s' is not a directory here" % path))
            out.append(g)
            continue
        g["surface"] = [path + "/**"]
        changed += 1
        notes.append(("surface", name, path + "/**"))
        out.append(g)
    return out, notes, changed


def report(root):
    cfg = os.path.join(root, ".claude", "gates.json")
    try:
        with open(cfg, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as exc:
        print("REFUSED: cannot read %s (%s)" % (cfg, exc), file=sys.stderr)
        return 2
    gates = d.get("full") or []
    if not gates:
        print("REFUSED: the 'full' tier declares no gates", file=sys.stderr)
        return 2

    new, notes, changed = plan(root, gates)
    for kind, name, detail in notes:
        print("  %-9s %-18s %s" % (kind, name, detail), file=sys.stderr)
    print("", file=sys.stderr)
    if not changed:
        print("Nothing to propose: no gate names a directory this can read back.",
              file=sys.stderr)
        return 1
    d["full"] = new
    out = cfg + ".surfaced"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2)
        fh.write("\n")
    print("wrote %s — %d gate(s) given a surface, %d left always-running."
          % (out, changed, len(gates) - changed), file=sys.stderr)
    print("Review it, then replace .claude/gates.json with it to switch scope on.",
          file=sys.stderr)
    return 0


# ----------------------------------------------------------------- controls
def selftest():
    import shutil
    import tempfile

    passed = ran = 0

    def chk(label, cond):
        nonlocal passed, ran
        ran += 1
        if cond:
            passed += 1
            print("  ok    %s" % label)
        else:
            print("  FAIL  %s" % label)

    tmp = tempfile.mkdtemp(prefix="arm-surface-")
    os.makedirs(os.path.join(tmp, "web"), exist_ok=True)

    # 1 — the case this exists for: a gate that names its directory gets that surface.
    g, _n, c = plan(tmp, [{"name": "fe", "cmd": "cd web && npm test"}])
    chk("a gate naming its directory gets that surface",
        c == 1 and g[0]["surface"] == ["web/**"])

    # 2 — a gate naming nothing keeps no surface, so it always runs. The alternative would
    # be guessing, and a wrong guess here silently stops running a gate.
    g, _n, c = plan(tmp, [{"name": "scan", "cmd": "./hooks/scan.sh"}])
    chk("a gate naming no directory is left always-running", c == 0 and "surface" not in g[0])

    # 3 — a directory that is not there is not claimed. A surface pointing at nothing would
    # match no changed file, which means the gate would never run again.
    g, _n, c = plan(tmp, [{"name": "be", "cmd": "cd nope && pytest"}])
    chk("a cd to a missing directory is skipped", c == 0 and "surface" not in g[0])

    # 4 — `cd .` narrows nothing. Claiming it would mark every file covered and disable the
    # escalation that makes scope safe.
    g, _n, c = plan(tmp, [{"name": "root", "cmd": "cd . && make"}])
    chk("'cd .' is refused as a surface", c == 0 and "surface" not in g[0])

    # 5 — an existing surface is never overwritten. The operator's declaration wins.
    g, _n, c = plan(tmp, [{"name": "fe", "cmd": "cd web && npm test", "surface": ["src/**"]}])
    chk("an existing surface is left alone", c == 0 and g[0]["surface"] == ["src/**"])

    # 6 — nested `cd` inside a wrapper is still a declaration. Real configs wrap gates in
    # a ratchet or a bash -c and the directory is inside the quoted part.
    g, _n, c = plan(tmp, [{"name": "tsc", "cmd": "./bin/ratchet t bash -c 'cd web && tsc'"}])
    chk("a directory named inside a wrapper is still read", c == 1 and g[0]["surface"] == ["web/**"])

    # 7 — the input is never mutated. This runs against a live config; a tool that edits
    # the caller's data structure while "planning" has already applied itself.
    original = [{"name": "fe", "cmd": "cd web && npm test"}]
    plan(tmp, original)
    chk("planning does not mutate the input", "surface" not in original[0])

    # 8 — a `cd` inside quoted DATA is not a declaration. Measured before the fix:
    # `grep -r "cd fixtures" .` proposed fixtures/**, which would have made that gate run
    # only when fixtures/** changed and skip silently for everything else.
    os.makedirs(os.path.join(tmp, "fixtures"), exist_ok=True)
    bad = ['grep -r "cd fixtures" .', "pytest -k 'not cd fixtures'"]
    ok = all(plan(tmp, [{"name": "t", "cmd": c}])[2] == 0 for c in bad)
    chk("a cd inside quoted data is not read as a declaration", ok)

    # 9 — and the real forms still are, so control 8 did not simply break detection.
    good = ["cd fixtures && pytest", "./bin/ratchet t bash -c 'cd fixtures && tsc'",
            "cd fixtures"]
    ok = all(plan(tmp, [{"name": "t", "cmd": c}])[2] == 1 for c in good)
    chk("command-position cd, bare or wrapped, is still read", ok)

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


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("--self-test", "selftest"):
        sys.exit(selftest())
    sys.exit(report(args[0] if args else os.getcwd()))
