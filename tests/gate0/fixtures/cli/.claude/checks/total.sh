#!/bin/sh
command -v node >/dev/null 2>&1 || { echo "CANNOT RUN  node is not installed"; exit 75; }
query="$1"
want="$2"
got="$(node bin/orders.mjs total ${query:+--search "$query"})" || { echo "FAIL  orders total exited $?"; exit 1; }
if [ "$got" != "$want" ]; then
  echo "FAIL  total ${query:+--search $query }printed '$got', wanted '$want'"
  exit 1
fi
echo "ok  total ${query:+--search $query }printed '$got'"
