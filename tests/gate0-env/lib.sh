#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
ACC="${ACCEPT_PY:-$PLUGIN/benchmark/gates/acceptance.py}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/${GATE:-gate0}.XXXXXX")"
pass=0; fail=0; PIDS=""; PORTS=""
SERVE='python3 -m http.server $PORT --bind 127.0.0.1 --directory $PWD'
unset VERIFY_TREE VERIFY_PASSED

chk(){ if [ "$2" = "$3" ]; then printf '  ok    %s\n' "$1"; pass=$((pass+1));
       else printf '  FAIL  %s\n        got  %s\n        want %s\n' "$1" "$2" "$3"; fail=$((fail+1)); fi; }
cleanup(){ local p; for p in $PIDS; do kill "$p" 2>/dev/null; done
  pkill -f "$(basename "$TMP")" 2>/dev/null; find "$TMP" -maxdepth 0 -exec rm -rf {} +; }
trap cleanup EXIT
trap 'exit 143' INT TERM

repo(){ local d; d="$(mktemp -d "$TMP/repo.XXXXXX")"; mkdir -p "$d/.claude"
  ( cd "$d" && git init -q . && git config user.email t@t && git config user.name t && echo x > seed && git add -A && git commit -qm seed ) >/dev/null 2>&1
  printf '%s' "$d"; }
contract(){ mkdir -p "$1/.claude"; printf '%s' "$2" > "$1/.claude/acceptance.json"; }
run(){ local d="$1"; shift; ( cd "$d" && env "$@" python3 "$ACC" . --results "$d/r.json" ) > "$d/out.txt" 2>&1; echo $? > "$d/rc"; }
verdicts(){ python3 -c 'import json,sys; print(" ".join(o["verdict"] for o in json.load(open(sys.argv[1]))["outcomes"]))' "$1/r.json" 2>/dev/null || echo no-results; }
show(){ python3 -c 'import json,sys
for o in json.load(open(sys.argv[1]))["outcomes"]:
    print("        | %s [%s]: %s" % (o["name"], o["verdict"], o["detail"]))' "$1/r.json" 2>/dev/null; }
portof(){ cat "$1/port" 2>/dev/null; }
listening(){ python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)' "$1"; }
free_port(){ python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }
gone(){ local i; for i in $(seq 1 50); do "$@" || return 0; sleep 0.2; done; return 1; }
closed(){ listening "$1" && echo LISTENING || echo closed; }

sweep(){
  local p left=""
  for p in $PORTS; do listening "$p" && left="$left $p"; done
  chk "no port is left listening ($(echo $PORTS | wc -w | tr -d ' ') ports used)" "${left:-none}" none
  chk "no process started under this run survives it" "$(pgrep -f "$(basename "$TMP")" | wc -l | tr -d ' ')" 0
}
finish(){
  echo
  if [ "$fail" -eq 0 ]; then echo "$1 PASSED  ($pass checks)"; exit 0
  else echo "$1 FAILED  ($fail of $((pass + fail)) checks)"; exit 1; fi
}
