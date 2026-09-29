#!/usr/bin/env bash
GATE=g7
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
ROUNDS="${G7_ROUNDS:-10}"
SPIN=300

pair_contract(){
  local pin=""; [ -n "${5:-}" ] && pin='"port":'"$5"','
  contract "$1" '{"environments":{"local":{'"$pin"'"start":"echo $PORT > port; exec '"$SERVE"'","ready":"/"}},
 "outcomes":[{"name":"serves its own worktree beside the other","expect":"e","env":"local",
   "check":"./pair-check.sh '"$3"' '"$2"' '"$4"' '"$SPIN"'","control":"curl -fsS $BASE_URL/absent"}]}'
}

worktrees(){
  local tag="$1" a b
  a="$(repo)"; b="$TMP/wt.$tag"
  git -C "$a" worktree add -q -b "wt$tag" "$b" >/dev/null 2>&1
  echo a > "$a/id"; echo b > "$b/id"
  cp "$HERE/pair-check.sh" "$a/"; cp "$HERE/pair-check.sh" "$b/"
  printf '%s %s' "$a" "$b"
}

side_by_side(){
  local a="$1" b="$2" gun="$TMP/go.$$.$RANDOM"
  ( until [ -e "$gun" ]; do sleep 0.005; done; run "$a" ) &
  ( until [ -e "$gun" ]; do sleep 0.005; done; run "$b" ) &
  sleep 0.3; touch "$gun"; wait
}

both_hold=0; distinct=0; clean=0
for r in $(seq 1 "$ROUNDS"); do
  set -- $(worktrees "$r"); a="$1"; b="$2"
  pair_contract "$a" "$b" a b; pair_contract "$b" "$a" b a
  side_by_side "$a" "$b"
  va="$(verdicts "$a")"; vb="$(verdicts "$b")"; pa="$(portof "$a")"; pb="$(portof "$b")"
  PORTS="$PORTS $pa $pb"
  same="same"; [ -n "$pa" ] && [ -n "$pb" ] && [ "$pa" != "$pb" ] && same="distinct"
  quiet="clean"
  { [ "$(closed "${pa:-1}")" = closed ] && [ "$(closed "${pb:-1}")" = closed ] && ! pgrep -f -- "$a" >/dev/null && ! pgrep -f -- "$b" >/dev/null; } || quiet="leftovers"
  [ "$va $vb" = "holds holds" ] && both_hold=$((both_hold+1))
  [ "$same" = distinct ] && distinct=$((distinct+1))
  [ "$quiet" = clean ] && clean=$((clean+1))
  chk "round $r: two worktrees at once both hold, on separate ports ($pa, $pb), and nothing is left running" \
    "$va $vb $same $quiet" "holds holds distinct clean"
  [ "$va $vb $same $quiet" = "holds holds distinct clean" ] || { show "$a"; show "$b"; }
done
printf '        rounds %d: both hold %d, distinct ports %d, clean shutdown %d\n' "$ROUNDS" "$both_hold" "$distinct" "$clean"

SPIN=30
pin="$(free_port)"; PORTS="$PORTS $pin"
set -- $(worktrees control); a="$1"; b="$2"
pair_contract "$a" "$b" a b "$pin"; pair_contract "$b" "$a" b a "$pin"
side_by_side "$a" "$b"
got="$(verdicts "$a") $(verdicts "$b")"
chk "control: two contracts pinned to the same port do not both hold, so the pair check can tell a collision" \
  "$([ "$got" = "holds holds" ] && echo both-hold || echo not-both-hold) $(closed "$pin")" "not-both-hold closed"
show "$a"; show "$b"

echo
sweep
finish G7
