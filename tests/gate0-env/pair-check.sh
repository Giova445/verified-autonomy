#!/usr/bin/env bash
mine="$1"; peer_dir="$2"; peer_id="$3"; spin="${4:-300}"
await(){ local n=0; until [ -e "$1" ] || [ "$n" -ge "$spin" ]; do n=$((n+1)); sleep 0.1; done; [ -e "$1" ]; }
touch up
await "$peer_dir/up" || { echo "the peer never came up"; exit 1; }
peer_port="$(cat "$peer_dir/port")"
[ "$(cat port)" = "$PORT" ] || { echo "this tree's port file disagrees with PORT=$PORT"; exit 1; }
[ "$peer_port" != "$PORT" ] || { echo "both trees are on port $PORT"; exit 1; }
[ "$(curl -fsS "$BASE_URL/id")" = "$mine" ] || { echo "the server at $BASE_URL is not this tree's ($mine)"; exit 1; }
[ "$(curl -fsS "http://127.0.0.1:$peer_port/id")" = "$peer_id" ] || { echo "the peer's server at port $peer_port is not answering as $peer_id"; exit 1; }
touch seen
await "$peer_dir/seen"
