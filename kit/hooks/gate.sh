#!/usr/bin/env bash
# gate.sh — Stop / SubagentStop hook.
#
# Refuses to let the turn end while any gate is red. This is the mechanical form of
# "you don't get to say done." Exit 2 blocks the stop and feeds stderr back to the
# agent as the reason to keep working.
#
# Per Claude Code docs: exit 2 blocks whether or not JSON is printed — even a JSON
# permissionDecision of "allow" cannot override it.
#
# Install:
#   "hooks": { "Stop": [ { "hooks": [
#       { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/gate.sh",
#         "timeout": 600000 } ] } ] }
#
# NOTE: deliberately not `set -e` — we must capture gate failures, not die on them.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
CONFIG="$ROOT/.claude/gates.json"
EVIDENCE_DIR="$ROOT/.claude/evidence"
STATE="$ROOT/.claude/.gate-attempts"
TIER="${GATE_TIER:-full}"
MAX_BLOCKS="${GATE_MAX_BLOCKS:-6}"

mkdir -p "$EVIDENCE_DIR"

# Consume hook stdin (unused today, but the contract says read it).
HOOK_INPUT="$(cat 2>/dev/null || true)"
: "${HOOK_INPUT:=}"

[ -f "$CONFIG" ] || exit 0   # no gate config: nothing to enforce, stay out of the way

# --- circuit breaker -------------------------------------------------------
# Without this, a permanently-red gate blocks the turn forever. After MAX_BLOCKS
# we stop blocking and require a BLOCKED report instead (see 03 §5).
ATTEMPTS=0
[ -f "$STATE" ] && ATTEMPTS="$(cat "$STATE" 2>/dev/null || echo 0)"

if [ "$ATTEMPTS" -ge "$MAX_BLOCKS" ]; then
  rm -f "$STATE"
  cat >&2 <<EOF
GATE CIRCUIT BREAKER TRIPPED after $ATTEMPTS blocked attempts.

Stop retrying. Write a BLOCKED report containing:
  1. The exact failing gate: command, exit code, stderr excerpt.
  2. What you tried, and why each attempt failed. Not "I tried a few things."
  3. The specific unknown or decision that requires a human.
  4. A recommendation with trade-offs.
Then hand off. Do not attempt another fix.
EOF
  exit 2
fi

# --- run the gates ---------------------------------------------------------
GATES_JSON="$(python3 - "$CONFIG" "$TIER" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
print(json.dumps(cfg.get(sys.argv[2], [])))
PY
)" || { echo "gate.sh: cannot parse $CONFIG" >&2; exit 1; }

COUNT="$(python3 -c 'import json,sys;print(len(json.loads(sys.argv[1])))' "$GATES_JSON")"
[ "$COUNT" -eq 0 ] && exit 0

FAILED=""
RESULTS="[]"

for i in $(seq 0 $((COUNT - 1))); do
  NAME="$(python3 -c 'import json,sys;print(json.loads(sys.argv[1])[int(sys.argv[2])]["name"])' "$GATES_JSON" "$i")"
  CMD="$(python3 -c 'import json,sys;print(json.loads(sys.argv[1])[int(sys.argv[2])]["cmd"])' "$GATES_JSON" "$i")"

  START=$(date +%s)
  OUT="$(cd "$ROOT" && eval "$CMD" 2>&1)"
  CODE=$?
  DUR=$(( ($(date +%s) - START) * 1000 ))

  HASH="$(printf '%s' "$OUT" | shasum -a 256 2>/dev/null | cut -d' ' -f1)"
  [ -z "$HASH" ] && HASH="$(printf '%s' "$OUT" | sha256sum | cut -d' ' -f1)"

  RESULTS="$(python3 - "$RESULTS" "$NAME" "$CMD" "$CODE" "$HASH" "$DUR" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
r.append({
    "gate": sys.argv[2], "command": sys.argv[3], "exit_code": int(sys.argv[4]),
    "stdout_sha256": sys.argv[5], "duration_ms": int(sys.argv[6]),
    "executed_by": "harness",
})
print(json.dumps(r))
PY
)"

  if [ "$CODE" -ne 0 ]; then
    FAILED="${FAILED}
── GATE FAILED: ${NAME}
   command : ${CMD}
   exit    : ${CODE}
$(printf '%s' "$OUT" | tail -40 | sed 's/^/   │ /')
"
  fi
done

# --- write the evidence bundle --------------------------------------------
SHA="$(cd "$ROOT" && git rev-parse HEAD 2>/dev/null || echo unknown)"
BUNDLE="$EVIDENCE_DIR/latest.json"
python3 - "$RESULTS" "$SHA" "$TIER" > "$BUNDLE" <<'PY'
import json, sys, datetime
gates = json.loads(sys.argv[1])
print(json.dumps({
    "commit_sha": sys.argv[2],
    "tier": sys.argv[3],
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "gates": gates,
    "all_green": all(g["exit_code"] == 0 for g in gates),
}, indent=2))
PY

# --- verdict ---------------------------------------------------------------
if [ -n "$FAILED" ]; then
  echo $((ATTEMPTS + 1)) > "$STATE"
  cat >&2 <<EOF
You cannot finish. ${TIER} gates are RED.
$FAILED
Rules:
  - Fix the CODE. Do not weaken, skip, or delete the test.
  - Do not add '|| true', raise a timeout, or add a retry to force green.
  - Do not edit gate config, hooks, or CI files.
  - Evidence bundle: .claude/evidence/latest.json
Attempt $((ATTEMPTS + 1))/${MAX_BLOCKS} before escalation is required.
EOF
  exit 2
fi

rm -f "$STATE"
exit 0
