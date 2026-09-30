#!/usr/bin/env bash
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-52s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-52s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
verify(){ CLAUDE_PROJECT_DIR="$tmp" bash "$PLUGIN/bin/verify" "$@" 2>&1; }

echo "self-test: $ROOT"

chk "the plugin registers no hooks" "$(ls "$PLUGIN/hooks" | grep -v '^__pycache__$' | tr '\n' ' ')" "state.py "

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

printf '{"full":[{"name":"hog","cmd":"python3 -c \\"b=b\x27x\x27*(300<<20); import time; time.sleep(2)\\""}]}' > "$tmp/.claude/gates.json"
rm -f "$tmp/.claude/acceptance.json"
out="$(VERIFY_MEMORY_MB=100 verify full)"
printf '%s' "$out" | grep -q "during gate 'hog', over the 100 MB budget" && r=named || r="silent: $(printf '%s' "$out" | grep memory)"
chk "memory: a step over VERIFY_MEMORY_MB is named" "$r" "named"

rl="$(mktemp -d)"; mkdir -p "$rl/.claude"
( cd "$rl" && git init -q . && git config user.email t@t && git config user.name t && echo a > app.txt && git add -A && git commit -qm init ) >/dev/null 2>&1
printf '{"full":[{"name":"nap","cmd":"sleep 1"}]}' > "$rl/.claude/gates.json"
printf '{"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","check":"exit 0","control":"exit 1"}]}' > "$rl/.claude/acceptance.json"
rverify(){ CLAUDE_PROJECT_DIR="$rl" bash "$PLUGIN/bin/verify" "$@" 2>&1; }
runlog="$rl/.claude/evidence/runs.jsonl"
rec(){ python3 - "$runlog" "$1" "$2" <<'PY'
import datetime, json, sys
rec = json.loads(open(sys.argv[1]).read().splitlines()[int(sys.argv[2])])
print(eval(sys.argv[3]))
PY
}
rverify done >/dev/null; rc=$?
chk "run log: one run appends exactly one line" "$(wc -l < "$runlog" | tr -d ' ')" "1"
chk "run log: the line holds the declared fields" "$(rec 0 '" ".join(sorted(rec))')" "commit exit_code gates peak_memory_mb product started_at subcommand tree verdict wall_ms"
chk "run log: it records the exit code, verdict and subcommand" "$rc $(rec 0 'rec["verdict"] + " " + rec["subcommand"]')" "0 green done"
chk "run log: commit is HEAD and tree is the fingerprint" "$(rec 0 'rec["commit"] + " " + rec["tree"]')" "$(git -C "$rl" rev-parse HEAD) $(rverify fingerprint)"
chk "run log: started_at is a UTC ISO time" "$(rec 0 'datetime.datetime.fromisoformat(rec["started_at"]).utcoffset() == datetime.timedelta(0)')" "True"
chk "run log: the gate and the product verdicts are this run's" "$(rec 0 '"%s %s %s | %s %s" % (rec["gates"][0]["name"], rec["gates"][0]["exit_code"], rec["gates"][0]["skipped"], rec["product"]["status"], [(o["name"], o["verdict"]) for o in rec["product"]["outcomes"]])')" "nap 0 False | held [('Search results', 'holds')]"
chk "run log: wall_ms is plausible for a gate that sleeps 1 s" "$(rec 0 '1000 <= rec["gates"][0]["duration_ms"] <= rec["wall_ms"] < 10000')" "True"
chk "run log: peak memory is a measured number" "$(rec 0 'type(rec["peak_memory_mb"]).__name__ + " " + str(rec["peak_memory_mb"] > 0)')" "int True"
first="$(head -1 "$runlog")"
printf '{"full":[{"name":"nap","cmd":"exit 3"}]}' > "$rl/.claude/gates.json"
rverify done >/dev/null; rc=$?
chk "run log: a second run appends a second line and keeps the first" "$(wc -l < "$runlog" | tr -d ' ') $([ "$(head -1 "$runlog")" = "$first" ] && echo kept)" "2 kept"
chk "run log: a red run logs exit code 1, verdict red and the gate's exit 3" "$rc $(rec 1 '"%s %s %s" % (rec["exit_code"], rec["verdict"], rec["gates"][0]["exit_code"])')" "1 1 red 3"
chk "run log: a run that skips the product check logs none, not an older product.json" "$(rec 1 'rec["product"]')" "{'status': 'not run', 'outcomes': []}"
VERIFY_MEMORY_MB=0 rverify full >/dev/null
chk "run log: with the meter off, peak memory is null" "$(rec 2 'rec["peak_memory_mb"]')" "None"
printf '{"full":[{"name":"nap","cmd":"true"}]}' > "$rl/.claude/gates.json"
bare="$(mktemp -d)"; mkdir "$bare/bin" "$bare/hooks"
cp "$PLUGIN/bin/verify" "$bare/bin/"; cp "$PLUGIN/hooks/state.py" "$bare/hooks/"
CLAUDE_PROJECT_DIR="$rl" bash "$bare/bin/verify" done >/dev/null 2>&1
chk "run log: a product check that could not run logs no outcomes, not an older product.json" "$(rec 3 '"%s %s" % (rec["product"]["status"], rec["product"]["outcomes"])')" "open []"
chk "run log: a run that held logs its outcome with a name and a verdict and no reason" "$(rec 0 '[sorted(o) for o in rec["product"]["outcomes"]]')" "[['name', 'verdict']]"
printf '{"environments":{"local":{"build":"echo boom; exit 3","start":"exec sleep 60","ready":"/"}},"outcomes":[{"name":"Search results","expect":"searching a name lists only matching items","env":"local","check":"exit 0","control":"exit 1"}]}' > "$rl/.claude/acceptance.json"
rverify product >/dev/null; rc=$?
chk "run log: a build that exits 3 logs outcome CANNOT RUN, reason build_failed, status 3" "$rc $(rec 4 'rec["product"]["outcomes"]')" "1 [{'name': 'Search results', 'verdict': 'CANNOT RUN', 'reason': 'build_failed', 'status': 3}]"
printf '{"full":[{"name":"nap","cmd":"exit 3"}]}' > "$rl/.claude/gates.json"
rverify done >/dev/null
chk "run log: a run that skips the product check logs no reason, though product.json holds an older CANNOT RUN" "$(grep -c build_failed "$rl/.claude/evidence/product.json") $(rec 5 'rec["product"]')" "1 {'status': 'not run', 'outcomes': []}"
printf '{"full":[{"name":"nap","cmd":"true"}]}' > "$rl/.claude/gates.json"
CLAUDE_PROJECT_DIR="$rl" bash "$bare/bin/verify" done >/dev/null 2>&1
chk "run log: a product check that could not run logs no reason, though product.json holds an older CANNOT RUN" "$(grep -c build_failed "$rl/.claude/evidence/product.json") $(rec 6 'rec["product"]')" "1 {'status': 'open', 'outcomes': []}"
printf '{"outcomes":[{"name":"a","expect":"e","check":"exit 0","control":"exit 1"},{"name":"b","expect":"e","check":"exit 1","control":"exit 1"},{"name":"c","expect":"e","check":"exit 75"},{"name":"d","expect":"e","check":"exit 0","control":"exit 0"}]}' > "$rl/.claude/acceptance.json"
rverify product >/dev/null
chk "run log: only a CANNOT RUN outcome carries a reason, and a check that exits 75 has no status to log" "$(rec 7 'rec["product"]["outcomes"]')" "[{'name': 'a', 'verdict': 'holds'}, {'name': 'b', 'verdict': 'FAILS'}, {'name': 'c', 'verdict': 'CANNOT RUN', 'reason': 'check_cannot_run'}, {'name': 'd', 'verdict': 'NOT PROVEN'}]"
mkdir -p "$bare/benchmark/gates"
cat > "$bare/benchmark/gates/acceptance.py" <<'PY'
import json, sys
if "--summarize" in sys.argv:
    print("open"); print("product : stand-in")
else:
    path = sys.argv[sys.argv.index("--results") + 1]
    json.dump({"contract": "ok", "outcomes": [{"name": "old", "verdict": "CANNOT RUN", "detail": "d"}]}, open(path, "w"))
PY
CLAUDE_PROJECT_DIR="$rl" bash "$bare/bin/verify" product >/dev/null 2>&1
chk "run log: a CANNOT RUN that names no reason is logged as unspecified" "$(rec 8 'rec["product"]["outcomes"]')" "[{'name': 'old', 'verdict': 'CANNOT RUN', 'reason': 'unspecified'}]"
find "$bare" -maxdepth 0 -exec rm -rf {} +
rm -f "$runlog"; mkdir "$runlog"
printf '{"full":[{"name":"ok","cmd":"true"}]}' > "$rl/.claude/gates.json"
out="$(rverify full)"; rc=$?
chk "run log: an unwritable log warns in one line and does not change the run" "$rc $(printf '%s\n' "$out" | grep -c 'run log not written')" "0 1"
find "$rl" -maxdepth 0 -exec rm -rf {} +

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
runlog="$sc/.claude/evidence/runs.jsonl"
chk "run log: a scoped-out gate is logged as skipped, with no exit code" "$(rec 0 '" | ".join("%s %s %s" % (g["name"], g["exit_code"], g["skipped"]) for g in rec["gates"])')" "fe 0 False | be None True"
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
undocumented=""; for v in $(python3 -B -c 'import importlib.util, sys
spec = importlib.util.spec_from_file_location("acceptance", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print(" ".join(mod.REASONS))' "$PLUGIN/benchmark/gates/acceptance.py"); do grep -q "\`$v\`" "$PLUGIN/README.md" && grep -q "\`$v\`" "$PLUGIN/docs/how-it-works.md" || undocumented="$undocumented $v"; done
chk "every CANNOT RUN reason the code sets is documented in the README and the docs" "${undocumented:-none}" "none"

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
