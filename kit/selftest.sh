#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/stop-gate.sh" ]; then
  HOOKS="$HERE"; BIN="$HERE/../bin"; GATES="$HERE/../gates"
else
  HOOKS="$HERE/../hooks"; BIN="$HERE/../bin"; GATES="$HERE/../benchmark/gates"
fi
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-50s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-50s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
stop(){ rm -f "$tmp/.claude/.gate-attempts"; CLAUDE_PROJECT_DIR="$tmp" bash "$HOOKS/stop-gate.sh" </dev/null 2>&1; }
deny(){ printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.stdin.read()}}))' \
  | CLAUDE_PROJECT_DIR="$tmp" bash "$HOOKS/deny-dangerous.sh" >/dev/null 2>&1; echo $?; }
held='{"outcomes":[{"name":"search","expect":"searching a name lists only matching items","check":"exit 0","control":"exit 1"}]}'

echo "self-test: hooks in $HOOKS"
tmp="$(mktemp -d)"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t && git commit -q --allow-empty -m init )

stop >/dev/null; chk "no gates.json -> stop hook stays out of the way" "$?" "0"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$HOOKS/session-start.sh" 2>/dev/null)"
printf '%s' "$out" | grep -q "verified-autonomy:setup" && r=hint || r="${out:+other}"
chk "unarmed repo -> one hint pointing at setup" "$r" "hint"

mkdir -p "$tmp/.claude"
printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
stop >/dev/null; chk "red gate -> refuses" "$?" "2"

printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
out="$(stop)"; rc=$?
printf '%s' "$out" | grep -q "no product expectations" && r="$rc named" || r="$rc silent"
chk "green gates, no contract -> refuses, says why" "$r" "2 named"

printf '{"outcomes":[{"name":"search","expect":"searching a name lists only matching items","check":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
out="$(stop)"; rc=$?
printf '%s' "$out" | grep -q "search: searching a name lists only matching items" && r="$rc named" || r="$rc silent"
chk "open expectation -> refuses, names it" "$r" "2 named"

printf '%s' "$held" > "$tmp/.claude/acceptance.json"
stop >/dev/null; chk "gates green, expectations hold -> allows" "$?" "0"
out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$HOOKS/session-start.sh" 2>/dev/null)"
printf '%s' "$out" | grep -q "verified-autonomy" && r=yes || r=no
chk "gates.json present -> context injected" "$r" "yes"

fc(){ printf '%s' "$2" > "$tmp/.claude/gates.json"; rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts"
      CLAUDE_PROJECT_DIR="$tmp" bash "$BIN/verify" done >/dev/null 2>&1; chk "$1" "$?" "1"; }
fc "unparseable config -> refuses"  '{"full":[{"name":"u","cmd":"exit 0"},]}'
fc "empty full tier -> refuses"     '{"full":[]}'
fc "mis-keyed tier -> refuses"      '{"ful":[{"name":"u","cmd":"exit 0"}]}'
fc "placeholder gate -> refuses"    '{"full":[{"name":"u","cmd":"echo TODO"}]}'

printf '{"full":[{"name":"u","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
( cd "$tmp" && git add -A && git commit -qm gates ) >/dev/null 2>&1
mv "$tmp/.claude/gates.json" "$tmp/.claude/gates.bak"
stop >/dev/null; chk "tracked config deleted -> refuses" "$?" "2"
mv "$tmp/.claude/gates.bak" "$tmp/.claude/gates.json"
mkdir -p "$tmp/bin"; printf '#!/bin/sh\nexit 0\n' > "$tmp/bin/verify"; chmod +x "$tmp/bin/verify"
stop >/dev/null; chk "a stub bin/verify in the repo is ignored" "$?" "2"

chk "push to main blocked"               "$(deny 'git push origin main')" "2"
chk "force push to own branch allowed"   "$(deny 'git push --force-with-lease origin feature/x')" "0"
chk "exit-code suppression on tests blocked" "$(deny 'pytest -q || true')" "2"
chk "commit with a co-author blocked"    "$(deny 'git commit -m x -m "Co-Authored-By: a <a@b>"')" "2"
chk "ordinary command allowed"           "$(deny 'npm test')" "0"

python3 "$GATES/trailer-check.py" --self-test >/dev/null 2>&1; chk "co-author gate controls" "$?" "0"
python3 "$GATES/acceptance.py" --self-test >/dev/null 2>&1;   chk "product contract controls" "$?" "0"

find "$tmp" -maxdepth 0 -exec rm -rf {} +
echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
