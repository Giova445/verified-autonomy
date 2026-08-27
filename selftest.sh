#!/usr/bin/env bash
# selftest.sh — prove the enforcement actually fires. Run after install, in the target repo.
#
# An unverified gate is worse than no gate, because you will trust it. This exists so that
# "I installed it" and "it works" are different claims with different evidence.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-46s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-46s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }

echo "self-test: $ROOT"

# 1. safe when the project opts out
tmp="$(mktemp -d)"; ( cd "$tmp" && git init -q . )
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "no gates.json -> stop hook stays out of the way" "$?" "0"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
chk "no gates.json -> no context injected" "${out:+nonempty}" ""

# 2. red gate must refuse the turn
mkdir -p "$tmp/.claude"
printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "red gate -> Stop hook exit 2 (refuses)" "$?" "2"

# 3. green gate must allow it
rm -f "$tmp/.claude/.gate-attempts"
printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "green gate -> Stop hook exit 0 (allows)" "$?" "0"

# 4. context injected once the project opts in
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
printf '%s' "$out" | grep -q "verified-autonomy" && r=yes || r=no
chk "gates.json present -> context injected" "$r" "yes"

# 5. deny-list
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' \
  | bash "$PLUGIN/hooks/deny-dangerous.sh" >/dev/null 2>&1
chk "force push blocked" "$?" "2"
echo '{"tool_name":"Edit","tool_input":{"file_path":"/r/.claude/gates.json"}}' \
  | bash "$PLUGIN/hooks/deny-dangerous.sh" >/dev/null 2>&1
chk "editing own guardrails blocked" "$?" "2"
echo '{"tool_name":"Bash","tool_input":{"command":"npm test"}}' \
  | bash "$PLUGIN/hooks/deny-dangerous.sh" >/dev/null 2>&1
chk "ordinary command allowed" "$?" "0"

rm -rf "$tmp"
echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
