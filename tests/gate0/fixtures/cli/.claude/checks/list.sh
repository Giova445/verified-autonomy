#!/bin/sh
command -v node >/dev/null 2>&1 || { echo "CANNOT RUN  node is not installed"; exit 75; }
query="$1"
want="$2"
out="$(node bin/orders.mjs list --search "$query")" || { echo "FAIL  orders list exited $?"; exit 1; }
rows="$(printf '%s\n' "$out" | grep -c .)"
strangers="$(printf '%s\n' "$out" | grep -vic "$query")"
if [ "$rows" != "$want" ] || [ "$strangers" != "0" ]; then
  echo "FAIL  list --search $query printed $rows row(s) with $strangers not matching, wanted $want"
  exit 1
fi
echo "ok  list --search $query printed $rows row(s), all matching"
