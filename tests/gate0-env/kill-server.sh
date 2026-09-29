#!/usr/bin/env bash
kill -9 "$(cat "${1:-server.pid}")" || exit 1
for _ in $(seq 1 50); do
  curl -s -o /dev/null --max-time 1 "$BASE_URL/" || exit 0
  sleep 0.1
done
exit 1
