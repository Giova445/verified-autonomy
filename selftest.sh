#!/usr/bin/env bash
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-52s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-52s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
verify(){ CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" "$@" 2>&1; }

echo "self-test: $ROOT"

chk "the plugin registers no hooks" "$(ls "$PLUGIN/hooks" | tr '\n' ' ')" "state.py "

tmp="$(mktemp -d)"
( cd "$tmp" && git init -q . && git config user.email t@t && git config user.name t && mkdir -p .claude \
  && echo a > app.txt && git add -A && git commit -qm init ) >/dev/null 2>&1

out="$(verify product)"; rc=$?
printf '%s' "$out" | grep -q "no product expectations are declared" && r="$rc named" || r="$rc silent"
chk "no contract -> product check fails and says why" "$r" "1 named"

printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > "$tmp/.claude/gates.json"
out="$(verify done)"; rc=$?
printf '%s' "$out" | grep -q "probe" && r="$rc named" || r="$rc silent"
chk "red gate -> done fails and names the gate" "$r" "1 named"

printf '{"full":[{"name":"probe","cmd":"true"}]}' > "$tmp/.claude/gates.json"
printf '{"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","check":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
out="$(verify done)"; rc=$?
printf '%s' "$out" | grep -q "Search results: searching a name lists only matching items" && r="$rc named" || r="$rc silent"
chk "open expectation -> done fails and names it" "$r" "1 named"

printf '{"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","check":"exit 0","control":"exit 1"}]}' > "$tmp/.claude/acceptance.json"
out="$(verify done)"; rc=$?
printf '%s' "$out" | grep -q "1 product expectation(s) hold" && r="$rc reported" || r="$rc silent"
chk "expectations hold -> done passes and reports it" "$r" "0 reported"

printf 'printf "run\\n" >> .claude/runs\n' > "$tmp/.claude/count.sh"
printf '{"full":[{"name":"count","cmd":"sh .claude/count.sh"}]}' > "$tmp/.claude/gates.json"
for i in 1 2 3; do verify done >/dev/null; done
chk "every run executes: nothing is cached" "$(grep -c run "$tmp/.claude/runs")" "3"

fc(){ printf '%s' "$2" > "$tmp/.claude/gates.json"; verify done >/dev/null; chk "$1" "$?" "1"; }
fc "unparseable config -> refuse"   '{"full":[{"name":"u","cmd":"exit 0"},]}'
fc "empty full tier -> refuse"      '{"full":[]}'
fc "placeholder gate -> refuse"     '{"full":[{"name":"u","cmd":"echo TODO"}]}'

sc="$(mktemp -d)"; mkdir -p "$sc/.claude" "$sc/web" "$sc/api"
( cd "$sc" && git init -q . && git config user.email t@t && git config user.name t )
printf '%s' '{"full":[{"name":"fe","cmd":"true","surface":["web/**"]},{"name":"be","cmd":"true","surface":["api/**"]}]}' > "$sc/.claude/gates.json"
printf '{"outcomes":[{"name":"o","expect":"e","check":"exit 0","control":"exit 1"}]}' > "$sc/.claude/acceptance.json"
echo x > "$sc/web/a.txt"; echo y > "$sc/api/b.txt"
( cd "$sc" && git add -A >/dev/null 2>&1 && git commit -qm init >/dev/null 2>&1 )
echo c >> "$sc/web/a.txt"
o="$(CLAUDE_PROJECT_DIR="$sc" bash "$PLUGIN/bin/verify" done 2>&1)"
printf '%s' "$o" | grep -q "scoped out" && r=yes || r=no
chk "scope: a gate whose surface is untouched is skipped" "$r" "yes"
printf '%s' "$o" | grep -q "ALL GATES GREEN" && r=yes || r=no
chk "scope: a scoped pass is not ALL GATES GREEN" "$r" "no"
find "$sc" -maxdepth 0 -exec rm -rf {} +

inst="$tmp/inst"; mkdir -p "$inst"
( cd "$inst" && git init -q . && git config user.email t@t && git config user.name t \
  && printf '.claude/*\n' > .gitignore && git add -A && git commit -qm init ) >/dev/null 2>&1
( cd "$inst" && ARM_TIMEOUT=30 bash "$PLUGIN/kit/install.sh" . ) >/dev/null 2>&1
chk "installer adds only .gitignore lines not already ignored" "$(tail -n +2 "$inst/.gitignore" | tr '\n' ' ')" ""
bash "$inst/.claude/selftest.sh" >/dev/null 2>&1
chk "the installed self-test passes in the installed layout" "$?" "0"
find "$tmp" -maxdepth 0 -exec rm -rf {} +

suite() {
  local label="$1"; shift
  local out rc n
  out="$("$@" 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | grep -oE '\([0-9]+ checks' | tail -1 | tr -dc '0-9')"
  if [ "$rc" -eq 0 ] && [ -n "$n" ]; then
    printf '  ok    %-52s (%s checks)\n' "$label" "$n"; pass=$((pass+1))
  elif [ "$rc" -eq 2 ] || [ "$rc" -eq 75 ]; then
    printf '  NOTRUN %-51s exit=%s - could not run; nothing verified\n' "$label" "$rc"; fail=$((fail+1))
    printf '%s\n' "$out" | head -2 | sed 's/^/          /'
  else
    printf '  FAIL  %-52s exit=%s counted=%s\n' "$label" "$rc" "${n:-none}"; fail=$((fail+1))
    printf '%s\n' "$out" | grep -E 'FAIL|NOT RUN' | sed 's/^/          /'
  fi
}

leak="$(git -C "$PLUGIN" grep -n -I -E '(/Users/|/home/)[A-Za-z0-9_.-]+/' -- . ':!selftest.sh' 2>/dev/null | head -3)"
chk "no absolute machine paths in tracked files" "${leak:-none}" "none"
chk "skills: only prove and setup ship" "$(ls "$PLUGIN/skills" | tr '\n' ' ')" "prove setup "
chk "docs: only how-it-works ships" "$(ls "$PLUGIN/docs" | tr '\n' ' ')" "how-it-works.md "
missing=""; for v in $(sed -n '/^## Optional settings/,/^## Updating/p' "$PLUGIN/README.md" | grep -oE '`[A-Z][A-Z_]+' | tr -d '`' | sort -u); do grep -rqw "$v" "$PLUGIN/bin" "$PLUGIN/hooks" "$PLUGIN/benchmark/gates" || missing="$missing $v"; done
chk "every setting the README names exists in the code" "${missing:-none}" "none"

echo
suite "arm"             bash    "$PLUGIN/bin/arm"             selftest
suite "install"         bash    "$PLUGIN/kit/install.sh"      --self-test
suite "discover"        python3 "$PLUGIN/bin/discover"        selftest
suite "scope"           python3 "$PLUGIN/bin/scope"           selftest
suite "pin-check"       python3 "$PLUGIN/.github/ci/pin-check.py"               --self-test
suite "trailer-check"   python3 "$PLUGIN/benchmark/gates/trailer-check.py"      --self-test
suite "acceptance"      python3 "$PLUGIN/benchmark/gates/acceptance.py"         --self-test
suite "drive"           node    "$PLUGIN/benchmark/gates/drive.mjs"             --self-test
suite "product-live"    bash    "$PLUGIN/tests/product-live.sh"
suite "kit self-test"   bash    "$PLUGIN/kit/selftest.sh"

echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
