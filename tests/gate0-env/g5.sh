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
chk "the server dies during the first outcome's control: that outcome never holds, and the next two are CANNOT RUN, never FAILS" \
  "$(verdicts "$d") $(closed "$(portof "$d")")" "CANNOT RUN CANNOT RUN CANNOT RUN closed"
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

d="$(dead_server_repo)"
contract "$d" '{"environments":{'"$LOCAL"'},"outcomes":[
 {"name":"dies during its control","expect":"e","env":"local","check":"'"$SEED"'","control":"'"$KILL"'; exit 1"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the server dies during the control, the only outcome: CANNOT RUN, never holds, and the run is not green" \
  "$(verdicts "$d") rc$(cat "$d/rc") $(closed "$(portof "$d")")" "CANNOT RUN rc1 closed"
show "$d"

WRAPPED='"wrapped":{"start":"echo $PORT > port; '"$SERVE"' & echo $! > server.pid; wait $!; sleep 60","ready":"/"}'
wrapper_case(){ local kind="$1" check="$2" ctl="$3" d; d="$(dead_server_repo)"
  contract "$d" '{"environments":{'"$WRAPPED"'},"outcomes":[
   {"name":"wrapper outlives the server, killed in the '"$kind"'","expect":"e","env":"wrapped","check":"'"$check"'","control":"'"$ctl"'"}]}'
  run "$d"; PORTS="$PORTS $(portof "$d")"
  chk "a start wrapper stays alive after its killed server, killed during the $kind: the port stops answering, CANNOT RUN, never FAILS or holds" \
    "$(verdicts "$d") $(grep -c "stopped during the $kind" "$d/out.txt") $(closed "$(portof "$d")")" "CANNOT RUN 1 closed"
  show "$d"; }
wrapper_case check "$SEED && $KILL && $SEED" "exit 1"
wrapper_case control "$SEED" "$KILL; exit 1"

for shape in adopted:'"reuse":true,"start":"touch started","ready":"/",' bare:''; do
  pin="$(free_port)"; d="$(dead_server_repo)"; occupy_http "$pin"; echo "$OCC" > "$d/server.pid"
  contract "$d" '{"environments":{"ext":{"port":'"$pin"','"${shape#*:}"'"vars":{}}},
   "outcomes":[{"name":"'"${shape%%:*}"' app killed mid-check","expect":"e","env":"ext","check":"curl -fsS $BASE_URL/other-app && '"$KILL"' && curl -fsS $BASE_URL/other-app","control":"exit 1"}]}'
  run "$d"
  chk "an app the harness did not start (${shape%%:*}) is killed during its check: CANNOT RUN, never FAILS, and nothing was started" \
    "$(verdicts "$d") $([ ! -e "$d/started" ] && echo nothing-started) $(closed "$pin")" "CANNOT RUN nothing-started closed"
  show "$d"
done

echo "the app crashes by itself"

CRASHY='import http.server, os
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/crash":
            os._exit(1)
        super().do_GET()
    def log_message(self, *a):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()'
CRASHER='"local":{"start":"echo $PORT > port; exec python3 crashy.py","ready":"/"}'
CRASH='curl -sS $BASE_URL/crash'
crashy_repo(){ local d; d="$(repo)"; printf '%s' "$CRASHY" > "$d/crashy.py"; printf '%s' "$d"; }

d="$(crashy_repo)"
contract "$d" '{"environments":{'"$CRASHER"'},"outcomes":[
 {"name":"crashes on a request during its check","expect":"e","env":"local","check":"'"$SEED"'; '"$CRASH"'","control":"exit 1"},
 {"name":"next","expect":"e","env":"local","check":"'"$SEED"'","control":"exit 1"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the product exits by itself on a request during the check: FAILS, not CANNOT RUN; the outcome after it did not run" \
  "$(verdicts "$d") $(closed "$(portof "$d")") $(grep -c 'exited with status 1 during the check' "$d/out.txt")" "FAILS CANNOT RUN closed 1"
show "$d"

d="$(crashy_repo)"
contract "$d" '{"environments":{'"$CRASHER"'},"outcomes":[
 {"name":"crashes on a request during its control","expect":"e","env":"local","check":"curl -fsS $BASE_URL/crashy.py >/dev/null","control":"'"$CRASH"'; exit 1"}]}'
run "$d"; PORTS="$PORTS $(portof "$d")"
chk "the product exits by itself on a request during the control: FAILS, never holds" \
  "$(verdicts "$d") rc$(cat "$d/rc") $(closed "$(portof "$d")") $(grep -c 'exited with status 1 during the control' "$d/out.txt")" "FAILS rc1 closed 1"
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
  "build":"echo $PORT > port; python3 -m http.server $PORT --bind 127.0.0.1 --directory '"$TMP"'/other >/dev/null 2>&1 & echo $! > occupier.pid; until curl -fsS -o /dev/null $BASE_URL/; do sleep 0.1; done",
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
