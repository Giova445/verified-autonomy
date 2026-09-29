#!/usr/bin/env bash
set -uo pipefail

PLUGIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACC="${ACCEPT_PY:-$PLUGIN/benchmark/gates/acceptance.py}"
DRIVE="${DRIVE_MJS:-$PLUGIN/benchmark/gates/drive.mjs}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/product-live.XXXXXX")"
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %s\n' "$1"; pass=$((pass+1));
       else printf '  FAIL  %s\n        got  %s\n        want %s\n' "$1" "$2" "$3"; fail=$((fail+1)); fi; }
cleanup(){ pkill -f "$(basename "$TMP")" 2>/dev/null; pkill -f "sleep 617[0-9]" 2>/dev/null; find "$TMP" -maxdepth 0 -exec rm -rf {} +; }
trap cleanup EXIT

repo(){ local d; d="$(mktemp -d "$TMP/repo.XXXXXX")"; mkdir -p "$d/.claude"
  ( cd "$d" && git init -q . && git config user.email t@t && git config user.name t && echo x > seed && git add -A && git commit -qm seed ) >/dev/null 2>&1
  printf '%s' "$d"; }
contract(){ printf '%s' "$2" > "$1/.claude/acceptance.json"; }
run(){ ( cd "$1" && python3 "$ACC" . --results "$1/r.json" ) > "$1/out.txt" 2>&1; }
verdicts(){ python3 -c 'import json,sys; print(" ".join(o["verdict"] for o in json.load(open(sys.argv[1]))["outcomes"]))' "$1/r.json"; }
listening(){ python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)' "$1"; }
free_port(){ python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }
wait_for_file(){ local i; for i in $(seq 1 100); do [ -s "$1" ] && return 0; sleep 0.2; done; return 1; }
gone(){ local i; for i in $(seq 1 50); do "$@" || return 0; sleep 0.2; done; return 1; }
SERVE='python3 -m http.server $PORT --bind 127.0.0.1'
TRIVIAL='{"outcomes":[{"name":"o","expect":"e","check":"exit 0","control":"exit 1"}]}'

d="$(repo)"
contract "$d" '{"environments":{"local":{"start":"echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"served","expect":"the app answers on its own port","env":"local",
   "check":"curl -fsS \"$BASE_URL/seed\" | grep -q x","control":"curl -fsS \"$BASE_URL/absent\""}]}'
run "$d"
chk "a server on a free \$PORT, ready as the URL path /, is started, checked and stopped" \
  "$(verdicts "$d") $(gone listening "$(cat "$d/port")" && echo stopped)" "holds stopped"

a="$(repo)"; b="$(repo)"
for x in "$a" "$b"; do
  contract "$x" '{"environments":{"one":{"start":"echo $PORT > one.port; exec '"$SERVE"'","ready":"/"},
    "two":{"start":"echo $PORT > two.port; exec '"$SERVE"'","ready":"/"}},
   "outcomes":[{"name":"first","expect":"e","env":"one","check":"curl -fsS \"$BASE_URL/seed\"","control":"exit 1"},
               {"name":"second","expect":"e","env":"two","check":"curl -fsS \"$BASE_URL/seed\"","control":"exit 1"}]}'
done
run "$a" & run "$b" & wait
ports="$(sort "$a/one.port" "$a/two.port" "$b/one.port" "$b/two.port" | uniq | wc -l | tr -d ' ')"
chk "two environments in two concurrent runs get four distinct free ports and all hold" \
  "$(verdicts "$a") $(verdicts "$b") $ports" "holds holds holds holds 4"

pin="$(free_port)"; d="$(repo)"
contract "$d" '{"environments":{"pinned":{"port":'"$pin"',"start":"'"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"pinned","expect":"e","env":"pinned","check":"test \"$PORT\" = '"$pin"' && curl -fsS http://127.0.0.1:'"$pin"'/seed","control":"exit 1"}]}'
run "$d"
chk "a contract may still pin a port" "$(verdicts "$d")" "holds"

d="$(repo)"
contract "$d" '{"environments":{"never":{"start":"echo $PORT > port; exec '"$SERVE"'","ready":"/nope"}},
 "outcomes":[{"name":"o","expect":"e","env":"never","check":"exit 0","control":"exit 1"}]}'
began=$SECONDS
( cd "$d" && ACCEPT_READY_TIMEOUT=2 python3 "$ACC" . --results "$d/r.json" ) > "$d/out.txt" 2>&1
chk "a URL ready that never answers 2xx is CANNOT RUN within ACCEPT_READY_TIMEOUT, and the server is stopped" \
  "$(verdicts "$d") $([ $((SECONDS - began)) -lt 12 ] && echo bounded) $(gone listening "$(cat "$d/port")" && echo stopped)" \
  "CANNOT RUN bounded stopped"

d="$(repo)"
contract "$d" '{"environments":{"local":{"start":"echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"long","expect":"e","env":"local","check":"sleep 6171","control":"exit 1"}]}'
( cd "$d" && ACCEPT_TIMEOUT=20 exec python3 "$ACC" . --results "$d/r.json" ) > "$d/out.txt" 2>&1 &
pid=$!
wait_for_file "$d/port"; sleep 1.5
kill -TERM "$pid"; wait "$pid"; rc=$?
chk "SIGTERM stops the server and the running check, and exits 143" \
  "$rc $(gone listening "$(cat "$d/port")" && echo server-gone) $(gone pgrep -f 'sleep 6171' >/dev/null && echo check-gone)" \
  "143 server-gone check-gone"

d="$(repo)"
contract "$d" '{"environments":{"local":{"start":"echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"long","expect":"e","env":"local","check":"sleep 6172","control":"exit 1"}]}'
( cd "$d" && ACCEPT_TIMEOUT=20 exec python3 "$ACC" . --results "$d/r.json" ) > "$d/out.txt" 2>&1 &
pid=$!
wait_for_file "$d/port"; sleep 1.5
kill -9 "$pid"; wait "$pid" 2>/dev/null
port="$(cat "$d/port")"
survived="$(listening "$port" && echo orphaned)"
recorded="$([ -s "$d/.claude/evidence/.servers" ] && echo recorded)"
pkill -f 'sleep 6172'
contract "$d" "$TRIVIAL"
run "$d"
chk "a server orphaned by a killed run is recorded, then reaped at the next run start" \
  "$survived $recorded $(grep -c 'reaped a server' "$d/out.txt") $(gone listening "$port" && echo stopped) $([ ! -e "$d/.claude/evidence/.servers" ] && echo forgotten)" \
  "orphaned recorded 1 stopped forgotten"

d="$(repo)"
sleep_pid="$(python3 -c 'import subprocess as s; print(s.Popen(["sleep","6173"], start_new_session=True, stdin=s.DEVNULL, stdout=s.DEVNULL, stderr=s.DEVNULL).pid)')"
mkdir -p "$d/.claude/evidence"
printf '%s|Mon Jan  1 00:00:00 2001\n' "$sleep_pid" > "$d/.claude/evidence/.servers"
contract "$d" "$TRIVIAL"
run "$d"
chk "a recorded group whose start time differs (a reused pid) is left alone, not killed" \
  "$(kill -0 "$sleep_pid" 2>/dev/null && echo alive) $(grep -c 'reaped a server' "$d/out.txt")" "alive 0"
kill "$sleep_pid" 2>/dev/null

d="$(repo)"
cat > "$d/server.js" <<'EOF'
const http = require("http");
const { fork } = require("child_process");
if (process.argv[2] === "worker") setInterval(() => {}, 1000);
else {
  fork(__filename, ["worker"]);
  setTimeout(() => http.createServer((q, r) => r.end("ok")).listen(process.env.PORT, "127.0.0.1"), 1500);
}
EOF
contract "$d" '{"environments":{"local":{"start":"exec node '"$d"'/server.js","ready":"/"}},
 "outcomes":[{"name":"nextlike","expect":"a server that starts slowly and forks a worker answers","env":"local",
   "check":"curl -fsS \"$BASE_URL/\" | grep -q ok","control":"curl -fsS \"$BASE_URL/absent-\" | grep -q nothing"}]}'
report="$TMP/time.txt"; timer=""
for flag in -l -v; do /usr/bin/time "$flag" true >/dev/null 2>&1 && { timer="/usr/bin/time $flag"; break; }; done
( cd "$d" && $timer python3 "$ACC" . --results "$d/r.json" ) > "$d/out.txt" 2> "$report"
chk "a slow-starting server that forks a worker holds, and no worker outlives the run" \
  "$(verdicts "$d") $(gone pgrep -f "$(basename "$d")/server.js worker" >/dev/null && echo no-orphans)" "holds no-orphans"
rss="$(awk '/maximum resident set size/{printf "%.1f MB", $1/1048576} /Maximum resident set size/{printf "%.1f MB", $NF/1024}' "$report")"
printf '        harness peak memory for that run: %s\n' "${rss:-not measured}"

[ -z "${PLAYWRIGHT_PATH:-}" ] && [ -d "$PLUGIN/node_modules/playwright" ] && export PLAYWRIGHT_PATH="$PLUGIN/node_modules/playwright"
if [ -n "${LIVE_SKIP_BROWSER:-}" ]; then
  printf '  skip  browser checks (LIVE_SKIP_BROWSER is set)\n'
elif ! PLAYWRIGHT_PATH="${PLAYWRIGHT_PATH:-}" node -e 'require(process.env.PLAYWRIGHT_PATH || "playwright")' 2>/dev/null; then
  printf '\nCANNOT RUN the browser checks: Playwright is not resolvable. Set PLAYWRIGHT_PATH or install it.\n'
  printf 'product-live (%d checks ran before that, %d failed)\n' "$((pass + fail))" "$fail"
  [ "$fail" -eq 0 ] && exit 75 || exit 1
else
  mkdir -p "$TMP/demo/benchmark/gates/fixtures"
  cp "$DRIVE" "$TMP/demo/benchmark/gates/drive.mjs"
  cp -R "$PLUGIN/benchmark/gates/fixtures/acceptance-demo" "$TMP/demo/benchmark/gates/fixtures/acceptance-demo"
  d="$TMP/demo/benchmark/gates/fixtures/acceptance-demo"
  ( cd "$d" && git init -q . && git config user.email t@t && git config user.name t && git add -A && git commit -qm seed ) >/dev/null 2>&1
  began=$SECONDS
  run "$d"
  chk "the demo contract holds end to end: a served page, waiting assertions, controls that fail" \
    "$(verdicts "$d")" "holds holds"
  [ "$(verdicts "$d")" = "holds holds" ] || { sed 's/^/        | /' "$d/out.txt"; tail -5 "$d"/.claude/evidence/server-*.log 2>/dev/null | sed 's/^/        | /'; }
  printf '        demo run: %ss\n' "$((SECONDS - began))"
  chk "each outcome leaves a log and a screenshot in .claude/evidence" \
    "$(ls "$d/.claude/evidence/shots" | wc -l | tr -d ' ') $(ls "$d/.claude/evidence"/*.log | wc -l | tr -d ' ')" "2 3"

  mkdir -p "$TMP/site"
  printf '<h1>shop</h1><script>setTimeout(()=>document.body.insertAdjacentHTML("beforeend","<p class=\\"error\\">boom</p>"),400)</script>' > "$TMP/site/late-error.html"
  printf '<ul id=l></ul><script>setTimeout(()=>{l.innerHTML="<li class=item>a</li>"},400)</script>' > "$TMP/site/late-list.html"
  printf '[{"hidden":".error","timeout":1500}]' > "$TMP/site/no-error.json"
  printf '[{"visible":".item","timeout":1500},{"count":{"selector":".item","equals":1}}]' > "$TMP/site/has-item.json"
  printf '[{"visible":"body"}]' > "$TMP/site/any.json"
  d="$(repo)"
  contract "$d" '{"environments":{"site":{"start":"exec python3 -m http.server $PORT --bind 127.0.0.1 --directory '"$TMP"'/site","ready":"/"}},
   "outcomes":[
    {"name":"late list","expect":"the list appears after a 400 ms load","env":"site",
     "check":"node '"$DRIVE"' \"$BASE_URL/late-list.html\" '"$TMP"'/site/has-item.json","control":"node '"$DRIVE"' \"$BASE_URL/late-error.html\" '"$TMP"'/site/has-item.json"},
    {"name":"late error","expect":"no error ever appears","env":"site",
     "check":"node '"$DRIVE"' \"$BASE_URL/late-error.html\" '"$TMP"'/site/no-error.json","control":"exit 1"},
    {"name":"dead server","expect":"e","check":"node '"$DRIVE"' http://127.0.0.1:'"$(free_port)"'/ '"$TMP"'/site/any.json","control":"exit 1"}]}'
  ACCEPT_TIMEOUT=60 run "$d"
  chk "through the harness: a late list holds, a late error FAILS, a dead server is CANNOT RUN (exit 75)" \
    "$(verdicts "$d")" "holds FAILS CANNOT RUN"
fi

echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass + fail)) checks)"; exit 1; fi
