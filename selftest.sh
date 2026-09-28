#!/usr/bin/env bash
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-46s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-46s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
deny(){ printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1" \
  | CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/deny-dangerous.sh" >/dev/null 2>&1; echo $?; }

echo "self-test: $ROOT"

tmp="$(mktemp -d)"; ( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t )
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "no gates.json -> stop hook stays out of the way" "$?" "0"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
chk "no gates.json -> no context injected" "${out:+nonempty}" ""

mkdir -p "$tmp/.claude"
printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "red gate -> Stop hook exit 2 (refuses)" "$?" "2"

rm -f "$tmp/.claude/.gate-attempts"
printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null 2>&1)"; rc=$?
printf '%s' "$out" | grep -q "no product expectations are declared" && r="$rc named" || r="$rc silent"
chk "green gates, no contract -> refuses, says why" "$r" "2 named"

rm -f "$tmp/.claude/.gate-attempts"
printf '{"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","check":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null 2>&1)"; rc=$?
printf '%s' "$out" | grep -q "Search results: searching a name lists only matching items" && r="$rc named" || r="$rc silent"
chk "green gates, open expectation -> refuses, names it" "$r" "2 named"

rm -f "$tmp/.claude/.gate-attempts"
printf '{"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","check":"exit 0","control":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null 2>&1)"; rc=$?
printf '%s' "$out" | grep -q "1 product expectation(s) hold" && r="$rc reported" || r="$rc silent"
chk "green gates, expectations hold -> allows" "$r" "0 reported"

rm -f "$tmp/.claude/.gate-attempts"
printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
for i in 1 2 3; do CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1; done
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null 2>&1)"
printf '%s' "$out" | grep -q "CIRCUIT BREAKER after 3" && r=yes || r=no
chk "three blocked stops -> blocked report, not a fourth retry" "$r" "yes"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1; a=$?
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1; b=$?
chk "after the report the stop is allowed, then gating resumes" "$a $b" "0 2"
rm -f "$tmp/.claude/.gate-attempts"
printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
printf '%s' "$out" | grep -q "verified-autonomy" && r=yes || r=no
chk "gates.json present -> context injected" "$r" "yes"

fc(){ printf '%s' "$2" > "$tmp/.claude/gates.json"; rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts"
      CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" done >/dev/null 2>&1
      chk "$1" "$?" "1"; }
fc "unparseable config -> refuse"   '{"full":[{"name":"u","cmd":"exit 0"},]}'
fc "empty full tier -> refuse"      '{"full":[]}'
fc "placeholder gate -> refuse"     '{"full":[{"name":"u","cmd":"echo TODO"}]}'
printf '{"full":[{"name":"u","cmd":"exit 0"}]}' > "$tmp/.claude/gates.json"
rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" done >/dev/null 2>&1
chk "valid green config -> certifies" "$?" "0"

( cd "$tmp" && git add -A >/dev/null 2>&1 && git commit -qm gates >/dev/null 2>&1 )
mv "$tmp/.claude/gates.json" "$tmp/.claude/gates.bak"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "tracked config deleted -> blocks" "$?" "2"
mv "$tmp/.claude/gates.bak" "$tmp/.claude/gates.json"
printf '{"full":[{"name":"u","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
mkdir -p "$tmp/bin"; printf '#!/bin/sh\nexit 0\n' > "$tmp/bin/verify"; chmod +x "$tmp/bin/verify"
rm -f "$tmp/.claude/.gate-attempts"
CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/stop-gate.sh" </dev/null >/dev/null 2>&1
chk "stubbed bin/verify ignored" "$?" "2"
rm -rf "$tmp/bin"

sc="$(mktemp -d)"; mkdir -p "$sc/.claude" "$sc/web" "$sc/api"
( cd "$sc" && git init -q . && git config user.email t@t && git config user.name t )
printf '%s' '{"full":[{"name":"fe","cmd":"true","surface":["web/**"]},{"name":"be","cmd":"true","surface":["api/**"]}]}' > "$sc/.claude/gates.json"
echo x > "$sc/web/a.txt"; echo y > "$sc/api/b.txt"
( cd "$sc" && git add -A >/dev/null 2>&1 && git commit -qm init >/dev/null 2>&1 )
echo c >> "$sc/web/a.txt"
o="$(CLAUDE_PROJECT_DIR="$sc" bash "$PLUGIN/bin/verify" done 2>&1)"
printf '%s' "$o" | grep -q "scoped out" && r=yes || r=no
chk "scope: untouched gate is skipped" "$r" "yes"
printf '%s' "$o" | grep -q "ALL GATES GREEN" && r=yes || r=no
chk "scope: a scoped pass is not ALL GATES GREEN" "$r" "no"
find "$sc" -maxdepth 0 -exec rm -rf {} +

chk "deny: push to main"                   "$(deny 'git push origin main')" "2"
chk "deny: force push own branch allowed"  "$(deny 'git push --force origin feature/x')" "0"
chk "deny: pytest || true blocked"         "$(deny 'pytest -q || true')" "2"
chk "deny: grep || true allowed"           "$(deny 'grep -c x f || true')" "0"
chk "deny: reset --hard blocked"           "$(deny 'git reset --hard HEAD')" "2"
chk "deny: ordinary command allowed"       "$(deny 'npm test')" "0"
chk "deny: commit with a co-author blocked"  "$(deny 'git commit -m x -m Co-Authored-By: a <a@b>')" "2"
chk "deny: plain commit allowed"            "$(deny 'git commit -m fix')" "0"
( cd "$tmp" && git commit -q --allow-empty -m init )
o="$(bash "$PLUGIN/bin/arm" detect "$tmp" 2>&1)"
printf '%s' "$o" | grep -q 'co-author .*passes' && r=yes || r=no
chk "arm: co-author gate armed in a git repo"  "$r" "yes"

out="$(VERIFIED_AUTONOMY_UNATTENDED=1 CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
a="$(printf '%s' "$out" | grep -c '<unattended>')"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/hooks/session-start.sh" 2>/dev/null)"
b="$(printf '%s' "$out" | grep -c '<unattended>')"
chk "unattended guidance only when opted in" "$a $b" "1 0"

inst="$tmp/inst"; mkdir -p "$inst"
( cd "$inst" && git init -q . && git config user.email t@t && git config user.name t \
  && printf '.claude/*\n' > .gitignore && git add -A && git commit -qm init ) >/dev/null 2>&1
( cd "$inst" && ARM_TIMEOUT=30 bash "$PLUGIN/kit/install.sh" . ) >/dev/null 2>&1
chk "installer adds only .gitignore lines not already ignored" "$(tail -n +2 "$inst/.gitignore" | tr '\n' ' ')" "AGENTS.md.new "
bash "$inst/.claude/hooks/selftest.sh" >/dev/null 2>&1
chk "the installed self-test passes in the installed layout" "$?" "0"

find "$tmp" -maxdepth 0 -exec rm -rf {} +

suite() {
  local label="$1"; shift
  local out rc n
  out="$("$@" 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | grep -oE '\([0-9]+ checks' | tail -1 | tr -dc '0-9')"
  if [ "$rc" -eq 0 ] && [ -n "$n" ]; then
    printf '  ok    %-46s (%s checks)\n' "$label" "$n"; pass=$((pass+1))
  elif [ "$rc" -eq 2 ]; then
    printf '  NOTRUN %-45s exit=2 — could not run; nothing verified\n' "$label"; fail=$((fail+1))
    printf '%s\n' "$out" | head -2 | sed 's/^/          /'
  else
    printf '  FAIL  %-46s exit=%s counted=%s\n' "$label" "$rc" "${n:-none}"; fail=$((fail+1))
    printf '%s\n' "$out" | grep -E 'FAIL|NOT RUN' | sed 's/^/          /'
  fi
}

leak="$(git -C "$PLUGIN" grep -n -I -E '(/Users/|/home/)[A-Za-z0-9_.-]+/' -- . ':!selftest.sh' 2>/dev/null | head -3)"
chk "no absolute machine paths in tracked files" "${leak:-none}" "none"

echo
suite "ledger"          bash    "$PLUGIN/bin/ledger"          selftest
suite "escalate"        bash    "$PLUGIN/bin/escalate"        selftest
suite "worktree-guard"  bash    "$PLUGIN/bin/worktree-guard"  selftest
suite "orchestration"   bash    "$PLUGIN/tests/orchestration-test.sh"
suite "test-delta"      bash    "$PLUGIN/bin/test-delta"      selftest
suite "holdout"         bash    "$PLUGIN/bin/holdout"         selftest
suite "mutate-changed"  bash    "$PLUGIN/bin/mutate-changed"  selftest
suite "ambiguity"       bash    "$PLUGIN/bin/ambiguity"       selftest
suite "arm"             bash    "$PLUGIN/bin/arm"             selftest
suite "arm-surface"     python3 "$PLUGIN/bin/arm-surface.py"  --self-test
suite "scope"           python3 "$PLUGIN/bin/scope"           selftest
suite "inert-mask"      python3 "$PLUGIN/hooks/inert-mask.py" --self-test
suite "pin-check"       python3 "$PLUGIN/benchmark/gates/pin-check.py"          --self-test
suite "trailer-check"   python3 "$PLUGIN/benchmark/gates/trailer-check.py"      --self-test
suite "identity"        python3 "$PLUGIN/benchmark/gates/identity-preflight.py" --self-test
suite "acceptance"      python3 "$PLUGIN/benchmark/gates/acceptance.py"         --self-test
suite "drive"           node    "$PLUGIN/benchmark/gates/drive.mjs"             --self-test
suite "kit self-test"    bash    "$PLUGIN/kit/selftest.sh"

echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
