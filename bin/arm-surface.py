#!/usr/bin/env python3
import json
import os
import re
import sys

CD = re.compile(r"\bcd\s+([A-Za-z0-9._/-]+)\s*(?:&&|;|$)")

EXPECTED_CONTROLS = 9

def plan(root, gates):
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

    g, _n, c = plan(tmp, [{"name": "fe", "cmd": "cd web && npm test"}])
    chk("a gate naming its directory gets that surface",
        c == 1 and g[0]["surface"] == ["web/**"])

    g, _n, c = plan(tmp, [{"name": "scan", "cmd": "./hooks/scan.sh"}])
    chk("a gate naming no directory is left always-running", c == 0 and "surface" not in g[0])

    g, _n, c = plan(tmp, [{"name": "be", "cmd": "cd nope && pytest"}])
    chk("a cd to a missing directory is skipped", c == 0 and "surface" not in g[0])

    g, _n, c = plan(tmp, [{"name": "root", "cmd": "cd . && make"}])
    chk("'cd .' is refused as a surface", c == 0 and "surface" not in g[0])

    g, _n, c = plan(tmp, [{"name": "fe", "cmd": "cd web && npm test", "surface": ["src/**"]}])
    chk("an existing surface is left alone", c == 0 and g[0]["surface"] == ["src/**"])

    g, _n, c = plan(tmp, [{"name": "tsc", "cmd": "./bin/ratchet t bash -c 'cd web && tsc'"}])
    chk("a directory named inside a wrapper is still read", c == 1 and g[0]["surface"] == ["web/**"])

    original = [{"name": "fe", "cmd": "cd web && npm test"}]
    plan(tmp, original)
    chk("planning does not mutate the input", "surface" not in original[0])

    os.makedirs(os.path.join(tmp, "fixtures"), exist_ok=True)
    bad = ['grep -r "cd fixtures" .', "pytest -k 'not cd fixtures'"]
    ok = all(plan(tmp, [{"name": "t", "cmd": c}])[2] == 0 for c in bad)
    chk("a cd inside quoted data is not read as a declaration", ok)

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
