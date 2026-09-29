#!/usr/bin/env bash
if [[ ${BASH_SOURCE[0]} == */* ]]; then HERE="${BASH_SOURCE[0]%/*}"; else HERE="."; fi
IFS= read -r -d '' INPUT

fail_closed() {
  if [[ $INPUT =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" && ${BASH_REMATCH[1]} != Bash ]]; then
    exit 0
  fi
  echo "deny hook error: $1. The command was not run." >&2
  exit 2
}

[ -f "$HERE/deny-rules.py" ] || fail_closed "$HERE/deny-rules.py is missing, so no command can be judged"

printf '%s' "$INPUT" | python3 -I -S -B "$HERE/deny-rules.py"
rc=$?
case "$rc" in
  0) exit 0 ;;
  2) exit 2 ;;
  *) fail_closed "the rules engine failed (exit $rc, is python3 installed?)" ;;
esac
