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
#
# KNOWN FAILING when CLAUDE_PLUGIN_ROOT is unset, together with "stubbed bin/verify ignored"
# below. Both have one cause, and it is a real hole in hooks/stop-gate.sh, not a harness
# artifact: that hook resolves its runner as ${CLAUDE_PLUGIN_ROOT}/bin/verify and falls back
# to $ROOT/bin/verify — a REPO-COMMITTED path. With the env var absent there is no plugin
# copy to prefer, so a green gate finds no runner and blocks (this check), and a stub
# committed into the target repo becomes the gate runner (that check). The hook should
# resolve its own directory from BASH_SOURCE, which no repo content can spoof.
#
# Deliberately NOT masked by exporting CLAUDE_PLUGIN_ROOT here. A suite that sets up the one
# condition under which the code works, and calls that a pass, is the fabricated green
# receipt this project exists to stop. Left red until the hook is fixed.
rm -f "$tmp/.claude/.gate-attempts"
printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "green gate -> Stop hook exit 0 (allows)" "$?" "0"

# 4. context injected once the project opts in
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
printf '%s' "$out" | grep -q "verified-autonomy" && r=yes || r=no
chk "gates.json present -> context injected" "$r" "yes"

# --- fail-closed: a gate set that cannot be read is not a passing gate set -------------
# Every case below silently certified before this suite existed: verify emitted exit 0 and
# an evidence bundle reading {"gates": [], "all_green": true}. A trailing comma was enough.
mkdir -p "$tmp/.claude"
fc(){ printf '%s' "$2" > "$tmp/.claude/gates.json"; rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts"
      CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" done >/dev/null 2>&1
      chk "$1" "$?" "1"; }
fc "unparseable config -> refuse"      '{"full":[{"name":"u","cmd":"exit 0"},]}'
fc "empty full tier -> refuse"         '{"full":[]}'
fc "mis-keyed tier -> refuse"          '{"ful":[{"name":"u","cmd":"exit 1"}]}'
fc "zero-byte config -> refuse"        ''
fc "placeholder gate -> refuse"        '{"full":[{"name":"u","cmd":"echo TODO"}]}'
printf '{"full":[{"name":"u","cmd":"exit 0"}]}' > "$tmp/.claude/gates.json"
rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" done >/dev/null 2>&1
chk "valid green config -> certifies" "$?" "0"
ag="$(python3 -c "import json;print(json.load(open('$tmp/.claude/evidence/latest.json'))['all_green'])" 2>/dev/null || echo missing)"
chk "green run emits all_green=True" "$ag" "True"

# --- tampering: removing or stubbing the enforcement is not a way to pass ---------------
( cd "$tmp" && git add -A >/dev/null 2>&1 && git -c user.email=t@t -c user.name=t commit -qm gates >/dev/null 2>&1 )
printf '{"full":[{"name":"u","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
rm -f "$tmp/.claude/.gate-attempts"
CLAUDE_PROJECT_DIR="$tmp" env -u CLAUDE_PLUGIN_ROOT bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "unset CLAUDE_PLUGIN_ROOT -> blocks" "$?" "2"
mv "$tmp/.claude/gates.json" "$tmp/.claude/gates.bak"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "tracked config deleted -> blocks" "$?" "2"
mv "$tmp/.claude/gates.bak" "$tmp/.claude/gates.json"
mkdir -p "$tmp/bin"; printf '#!/bin/sh\nexit 0\n' > "$tmp/bin/verify"; chmod +x "$tmp/bin/verify"
rm -f "$tmp/.claude/.gate-attempts"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "stubbed bin/verify ignored" "$?" "2"
rm -rf "$tmp/bin"

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

# --- orchestration: the durable state machine the driving agent consults -----------------
# The gate answers "may I stop?". These answer "what next, who owns this file, and is this
# loop going anywhere?" — the state that used to live only in the context window, and so did
# not survive compaction. Each tool ships its own selftest and tests/ ships the cross-process
# suite; running them from HERE is the difference between "the gate works" and "the plugin
# works". A tool that is present but broken is worse than one that is missing, because the
# agent will trust it. So a missing or unrunnable sub-suite FAILS here; it never skips.
suite() {
  local label="$1"; shift
  local out rc n
  out="$("$@" 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | grep -oE '\([0-9]+ checks' | tail -1 | tr -dc '0-9')"
  if [ "$rc" -eq 0 ] && [ -n "$n" ]; then
    printf '  ok    %-46s (%s checks)\n' "$label" "$n"; pass=$((pass+1))
  else
    # A sub-suite that exits 0 having verified nothing is the fabricated receipt this whole
    # project exists to stop, so an unparseable count is a failure too, not a pass.
    printf '  FAIL  %-46s exit=%s counted=%s\n' "$label" "$rc" "${n:-none}"; fail=$((fail+1))
    printf '%s\n' "$out" | grep -E 'FAIL|NOT RUN|Nothing was verified' | sed 's/^/          /'
  fi
}

echo
echo "orchestration:"
suite "ledger selftest"         bash "$PLUGIN/bin/ledger"         selftest
suite "escalate selftest"       bash "$PLUGIN/bin/escalate"       selftest
suite "worktree-guard selftest" bash "$PLUGIN/bin/worktree-guard" selftest
suite "cross-process suite"     bash "$PLUGIN/tests/orchestration-test.sh"

echo
echo "coverage:"
suite "test-delta selftest"      bash "$PLUGIN/bin/test-delta"      selftest
suite "holdout selftest"         bash "$PLUGIN/bin/holdout"         selftest
suite "mutate-changed selftest"  bash "$PLUGIN/bin/mutate-changed"  selftest

echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
