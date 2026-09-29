#!/usr/bin/env bash
GATE=g5
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
unset VA_G5_TOKEN

LOCAL='"local":{"start":"echo $$ > server.pid; echo $PORT > port; exec '"$SERVE"'","ready":"/"}'
SEED='curl -fsS $BASE_URL/seed'
ABSENT='curl -fsS $BASE_URL/absent'
KILL='./kill-server.sh server.pid'

dead_server_repo(){ local d; d="$(repo)"; cp "$HERE/kill-server.sh" "$d/"; printf '%s' "$d"; }
occupy_http(){ mkdir -p "$TMP/other"; echo other > "$TMP/other/other-app"
  python3 -m http.server "$1" --bind 127.0.0.1 --directory "$TMP/other" >/dev/null 2>&1 & OCC=$!; disown "$OCC"
  PIDS="$PIDS $OCC"; PORTS="$PORTS $1"; until listening "$1"; do sleep 0.1; done; }
occupy_silent(){ python3 -c 'import socket,sys,time
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(128); time.sleep(600)' "$1" & OCC=$!; disown "$OCC"
  PIDS="$PIDS $OCC"; PORTS="$PORTS $1"; until listening "$1"; do sleep 0.1; done; }
release(){ kill "$1" 2>/dev/null; gone listening "$2"; }
untouched(){ kill -0 "$1" 2>/dev/null && listening "$2" && echo occupier-untouched; }

echo "kill the server mid-run"

d="$(dead_server_repo)"
contract "$d" '{"environments":{'"$LOCAL"'},"outcomes":[
 {"name":"first","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$ABSENT"'"},
 {"name":"second","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$ABSENT"'"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "sanity: the same contract with the server left alone holds twice, and the server is stopped" \
  "$(verdicts "$d") $(closed "$(portof "$d")")" "holds holds closed"
show "$d"

d="$(dead_server_repo)"
contract "$d" '{"environments":{'"$LOCAL"'},"outcomes":[
 {"name":"first","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$KILL"'; exit 1"},
 {"name":"second","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$ABSENT"'"},
 {"name":"third","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$ABSENT"'"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the server dies between outcomes: the first holds, the next two are CANNOT RUN, never FAILS" \
  "$(verdicts "$d") $(closed "$(portof "$d")")" "holds CANNOT RUN CANNOT RUN closed"
show "$d"

d="$(dead_server_repo)"
contract "$d" '{"environments":{'"$LOCAL"'},"outcomes":[
 {"name":"dies during its check","expect":"e","env":"local","check":"'"$SEED"' && '"$KILL"' && '"$SEED"'","control":"exit 1"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the server dies during a check (between its two requests): CANNOT RUN, never FAILS" \
  "$(verdicts "$d") $(closed "$(portof "$d")")" "CANNOT RUN closed"
show "$d"

d="$(dead_server_repo)"
contract "$d" '{"environments":{'"$LOCAL"'},"outcomes":[
 {"name":"dies after its check","expect":"e","env":"local","check":"'"$SEED"' && '"$KILL"'","control":"'"$ABSENT"'"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the server dies after the check passed, before its control: CANNOT RUN, never holds" \
  "$(verdicts "$d") rc$(cat "$d/rc") $(closed "$(portof "$d")")" "CANNOT RUN rc1 closed"
show "$d"

echo "occupy the port"

pin="$(free_port)"; d="$(repo)"; occupy_http "$pin"
contract "$d" '{"environments":{"pinned":{"port":'"$pin"',"start":"touch started; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"pinned port already serving","expect":"e","env":"pinned","check":"touch ran; '"$SEED"'","control":"exit 1"}]}'
run "$d"
held="$(untouched "$OCC" "$pin")"
chk "a pinned port already answering ready is CANNOT RUN; start and check never ran; the occupier is left alone" \
  "$(verdicts "$d") $([ ! -e "$d/started" ] && [ ! -e "$d/ran" ] && echo nothing-ran) $held" "CANNOT RUN nothing-ran occupier-untouched"
show "$d"
release "$OCC" "$pin"

pin="$(free_port)"; d="$(repo)"; occupy_silent "$pin"
contract "$d" '{"environments":{"pinned":{"port":'"$pin"',"start":"touch started; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"pinned port held by a listener that never answers","expect":"e","env":"pinned","check":"touch ran; '"$SEED"'","control":"exit 1"}]}'
run "$d"
held="$(untouched "$OCC" "$pin")"
chk "a pinned port held by a silent listener is CANNOT RUN (start dies on the bind); the check never ran" \
  "$(verdicts "$d") $([ ! -e "$d/ran" ] && echo check-never-ran) $held" "CANNOT RUN check-never-ran occupier-untouched"
show "$d"
release "$OCC" "$pin"

mkdir -p "$TMP/other"; echo other > "$TMP/other/other-app"
d="$(repo)"; echo built > "$d/id"
contract "$d" '{"environments":{"local":{
  "build":"python3 -m http.server $PORT --bind 127.0.0.1 --directory '"$TMP"'/other >/dev/null 2>&1 & echo $! > occupier.pid; until curl -fsS -o /dev/null $BASE_URL/; do sleep 0.1; done",
  "start":"echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[
  {"name":"page loads","expect":"e","env":"local","check":"curl -fsS $BASE_URL/ >/dev/null","control":"'"$ABSENT"'"},
  {"name":"is the built app","expect":"e","env":"local","check":"curl -fsS $BASE_URL/id | grep -qx built","control":"exit 1"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
kill "$(cat "$d/occupier.pid")" 2>/dev/null; gone listening "$(portof "$d")"
chk "the port is taken after the harness picked it (during build): the app cannot bind, both CANNOT RUN" \
  "$(verdicts "$d")" "CANNOT RUN CANNOT RUN"
show "$d"

echo "unset a needs variable"

d="$(repo)"
contract "$d" '{"environments":{"local":{"start":"touch started; echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"needs a token","expect":"e","env":"local","needs":["VA_G5_TOKEN"],"check":"touch ran","control":"exit 1"}]}'
run "$d"
chk "an outcome whose needs variable is unset is BLOCKED, exits 1, starts nothing, runs nothing, and names the variable" \
  "$(verdicts "$d") rc$(cat "$d/rc") $([ ! -e "$d/started" ] && [ ! -e "$d/ran" ] && echo nothing-ran) $(grep -c 'blocked on: VA_G5_TOKEN' "$d/out.txt")" \
  "BLOCKED rc1 nothing-ran 1"
show "$d"

d="$(repo)"
contract "$d" '{"environments":{"cred":{"needs":["VA_G5_TOKEN"],"start":"touch started; echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"environment needs a token","expect":"e","env":"cred","check":"touch ran","control":"exit 1"}]}'
run "$d"
chk "an environment whose needs variable is unset is BLOCKED for its outcomes; the app is never started" \
  "$(verdicts "$d") rc$(cat "$d/rc") $([ ! -e "$d/started" ] && [ ! -e "$d/ran" ] && echo nothing-ran)" "BLOCKED rc1 nothing-ran"
show "$d"

d="$(repo)"
contract "$d" '{"environments":{"local":{"start":"touch started; echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"needs a token","expect":"e","env":"local","needs":["VA_G5_TOKEN"],"check":"touch ran","control":"exit 1"}]}'
run "$d" VA_G5_TOKEN=x; PORTS="$PORTS $(portof "$d")"
chk "sanity: with the variable set the same contract runs and holds, so the variable was the only blocker" \
  "$(verdicts "$d") $([ -e "$d/started" ] && [ -e "$d/ran" ] && echo ran) $(closed "$(portof "$d")")" "holds ran closed"
show "$d"

echo
sweep
finish G5
