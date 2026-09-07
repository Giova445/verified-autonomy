#!/usr/bin/env bash
# check-drift.sh — E1/E2: which gate results are stale for the CURRENT environment?
#
# E1 says a version-pinned finding must expire rather than be cited indefinitely. D1 is the
# canonical case: "subagents inherit PreToolUse hooks" was true on 2.1.250 and an open issue
# claimed otherwise, so the result is only meaningful next to the version it was measured on.
#
# This does NOT re-run anything. It compares the live environment to the manifest and prints
# which gates are invalidated, so a version bump has something concrete to check against.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
M="$HERE/gate-manifest.json"
[ -s "$M" ] || { echo "manifest missing" >&2; exit 1; }
python3 - "$M" <<'PY'
import json, subprocess, sys
m = json.load(open(sys.argv[1]))
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: return ""
live = {
 "claude_code": sh("claude --version 2>/dev/null | awk '{print $1}'"),
 "python": sh("python3 -V 2>&1 | awk '{print $2}'"),
 "node": sh("node --version 2>/dev/null"),
 "pytest": sh("pytest --version 2>&1 | head -1 | awk '{print $2}'"),
 "git": sh("git --version | awk '{print $3}'"),
}
rec = m["environment"]
changed = {k: (rec.get(k), v) for k, v in live.items() if v and rec.get(k) and rec[k] != v}
print(f"manifest generated {m['generated']}  gates: {len(m['gates'])}")
if not changed:
    print("environment matches the manifest — no gate invalidated by version drift.")
else:
    print("ENVIRONMENT DRIFT:")
    for k,(was,now) in changed.items(): print(f"  {k}: {was} -> {now}")

# map drift to affected subsystems
subs = set()
rules = m["trigger_rules"]
if "claude_code" in changed:
    was, now = changed["claude_code"]
    same_minor = was.split(".")[:2] == now.split(".")[:2]
    subs |= set(rules["claude_code.patch" if same_minor else "claude_code.minor_or_major"])
if "python" in changed or "pytest" in changed: subs |= set(rules["python_or_pytest"])
if "node" in changed: subs |= set(rules["node_or_jest"])
if "git" in changed: subs |= set(rules["git"])

stale = [g for g in m["gates"] if subs & set(g["subsystems"])]
judgment = [g for g in m["gates"] if "judgment" in g["subsystems"]]
if stale:
    print(f"\nINVALIDATED — re-run before trusting ({len(stale)}):")
    for g in stale: print(f"  [{g['status']:<12}] {g['gate']}")
print(f"\nMODEL-JUDGMENT DEPENDENT — re-run on ANY model change ({len(judgment)}):")
for g in judgment: print(f"  [{g['status']:<12}] {g['gate']}")
print("\nThese produced their result because the MODEL declined, not because a mechanism")
print("refused. This project measured three such cases; a model change can silently flip them.")
PY
