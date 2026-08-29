#!/usr/bin/env bash
# Does a subagent inherit the parent's PreToolUse hooks?
#
# There was a live contradiction: anthropics/claude-code#27661 reports that Task-tool
# subagents do NOT inherit PreToolUse hooks, permission rules, or CLAUDE.md, while the
# current documentation states they do. The entire mechanical story for capability
# attenuation rests on which is true, so it is settled by experiment rather than by reading
# either source.
#
# GROUND TRUTH IS THE HOOK'S OWN LOG, not the model's account. A model reporting "I was
# blocked" is a self-report, and unverified self-reports are the failure this project exists
# to stop. The hook appends a record every time it is invoked; if it never fires for the
# subagent's call, it did not inherit, whatever anyone says afterwards.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
EXP="$(mktemp -d)"
mkdir -p "$EXP/.claude/hooks"
cp "$HERE/deny-canary.sh" "$EXP/.claude/hooks/deny-canary.sh"
chmod +x "$EXP/.claude/hooks/deny-canary.sh"
python3 - "$EXP" <<'PY'
import json, os, sys
exp = sys.argv[1]
json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": f"{exp}/.claude/hooks/deny-canary.sh", "timeout": 5000}]}]}},
    open(os.path.join(exp, ".claude", "settings.json"), "w"), indent=2)
PY

# Prove the hook works standalone before drawing any conclusion from its silence.
echo '{"tool_name":"Bash","tool_input":{"command":"echo CANARY_SENTINEL_9f3a"}}' \
  | CLAUDE_PROJECT_DIR="$EXP" bash "$EXP/.claude/hooks/deny-canary.sh" >/dev/null 2>&1
[ $? -eq 2 ] || { echo "canary hook does not deny standalone — aborting" >&2; exit 1; }
rm -f "$EXP/hook-invocations.log"

echo "claude version: $(claude --version 2>/dev/null || echo unknown)"
CLAUDE_PROJECT_DIR="$EXP" timeout 300 claude -p "$(cat "$HERE/experiment-prompt.txt")" \
  --permission-mode acceptEdits > "$EXP/out.txt" 2>"$EXP/err.txt"

echo "--- hook invocation log (ground truth) ---"
[ -f "$EXP/hook-invocations.log" ] || { echo "hook NEVER fired — subagents do NOT inherit"; exit 0; }
python3 - "$EXP/hook-invocations.log" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
sub = [r for r in rows if r.get("agent_id")]
print(f"invocations: {len(rows)}   with agent_id (i.e. from a subagent): {len(sub)}")
for r in rows:
    if "CANARY_SENTINEL" in (r.get("cmd") or ""):
        print(f"  {r['cmd']!r}  agent_id={r.get('agent_id')!r} agent_type={r.get('agent_type')!r}")
print()
print("INHERITED" if sub else "NOT INHERITED")
PY
echo "artifacts: $EXP"
