#!/usr/bin/env bash
if [[ ${BASH_SOURCE[0]} == */* ]]; then HERE="${BASH_SOURCE[0]%/*}"; else HERE="."; fi
RULES="$HERE/deny-rules.py"

if [ ! -f "$RULES" ]; then
  echo "deny hook error: $RULES is missing, so no command can be judged. The command was not run." >&2
  exit 2
fi

python3 -I -S -B "$RULES"
rc=$?
case "$rc" in
  0) exit 0 ;;
  2) exit 2 ;;
  *)
    echo "deny hook error: the rules engine failed (exit $rc, is python3 installed?). The command was not run." >&2
    exit 2
    ;;
esac
