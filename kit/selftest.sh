#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/bin/verify" ]; then
  VERIFY="$HERE/bin/verify"; GATES="$HERE/gates"
else
  VERIFY="$HERE/../bin/verify"; GATES="$HERE/../benchmark/gates"
fi

EXPECTED_CONTROLS=11
pass=0; fail=0; OUT=""; RC=0
chk() {
  if [ "$2" = "$3" ]; then printf '  ok    %-62s (%s)\n' "$1" "$3"; pass=$((pass + 1))
  else printf '  FAIL  %-62s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail + 1)); fi
}

tmp="$(mktemp -d)/with space"
mkdir -p "$tmp/.claude"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t && git commit -q --allow-empty -m init )

run() {
  rm -rf "$tmp/.claude/evidence" "$tmp/.claude/.gate-attempts" "$tmp/.claude/.gate-judged"
  OUT="$(CLAUDE_PROJECT_DIR="$tmp" VERIFY_CACHE=0 bash "$VERIFY" "$@" 2>&1)"; RC=$?
}
gates() { printf '%s' "$1" > "$tmp/.claude/gates.json"; }

echo "self-test: runner $VERIFY"

gates '{"full":[{"name":"probe","cmd":"exit 1"}]}'
run full; chk "a red gate fails the run" "$RC" "1"

gates '{"full":[{"name":"probe","cmd":"exit 0"}]}'
run full; chk "a green gate passes the run" "$RC" "0"

bad() { gates "$2"; run done; chk "$1" "$RC" "1"; }
bad "an unparseable config is refused" '{"full":[{"name":"u","cmd":"exit 0"},]}'
bad "an empty full tier is refused"    '{"full":[]}'
bad "a mis-keyed tier is refused"      '{"ful":[{"name":"u","cmd":"exit 0"}]}'
bad "a placeholder gate is refused"    '{"full":[{"name":"u","cmd":"echo TODO"}]}'

gates '{"full":[{"name":"probe","cmd":"exit 0"}]}'
rm -f "$tmp/.claude/acceptance.json"
run done; chk "green gates and no product contract is not done" "$RC" "1"

printf '{"outcomes":[{"name":"search","expect":"searching a name lists only matching items","check":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
run done
printf '%s' "$OUT" | grep -q "searching a name lists only matching items" && named=named || named=silent
chk "an open expectation is not done, and is named" "$RC $named" "1 named"

printf '{"outcomes":[{"name":"search","expect":"searching a name lists only matching items","check":"exit 0","control":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
run done; chk "green gates and a held expectation is done" "$RC" "0"

suite() {
  local out rc n
  out="$(python3 "$2" --self-test 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | grep -oE '\([0-9]+ checks' | tail -1 | tr -dc '0-9')"
  chk "$1" "$rc ${n:+counted}" "0 counted"
}
suite "trailer gate controls" "$GATES/trailer-check.py"
suite "product contract controls" "$GATES/acceptance.py"

find "$(dirname "$tmp")" -maxdepth 0 -exec rm -rf {} +
echo
[ $((pass + fail)) -eq "$EXPECTED_CONTROLS" ] || { echo "  FAIL  ran $((pass + fail)) controls, expected $EXPECTED_CONTROLS"; fail=$((fail + 1)); }
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass + fail)) checks)"; exit 1; fi
