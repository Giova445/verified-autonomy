#!/usr/bin/env bash
set -uo pipefail
SUITE=g2
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

need_browser
ensure_python_deps
ensure_node_deps nextjs

prove(){
  local name="$1" serves="$2" want="$3" repo out began ended rc peak ports
  repo="$(make_repo "$name")"
  out="$TMP/$name.out"
  echo
  echo "$name"
  chk "$name: only sources are committed" "$(tracked_sources_only "$repo")" "0 dirty, 0 generated files tracked"
  began="$(now)"
  run_verify "$repo" "$out"; rc=$?
  ended="$(now)"
  guard_said "$out" | sed 's/^/        /'
  chk "$name: verify product exits 0" "$rc" "0"
  chk "$name: every outcome holds" "$(verdicts "$repo")" "$want"
  while IFS=$'\t' read -r title verdict check control code reason; do
    chk "$name: '$title' holds with its control failing" "$verdict, $check, $control" "holds, check passed, control failed"
    note "control: $code${reason:+; $reason}"
  done < <(outcome_rows "$repo")
  ports="$(logged_ports "$repo" | wc -l | tr -d ' ')"
  if [ "$serves" = "yes" ]; then
    chk "$name: the server's own log names the port it listened on" "$([ "$ports" -ge 1 ] && echo yes || echo no)" "yes"
  fi
  chk "$name: server stopped, nothing left listening or running" "$(left_behind "$repo")" "nothing"
  note "$(span "$began" "$ended") s wall, $(peak_mb "$out" || true) MB peak (whole process tree, verify meter), largest single process $(largest_rss_mb "$out") MB RSS"
}

echo "G2: fixtures (each outcome holds, control fails, server stopped)"
report_cache nextjs
prove cli no "holds holds"
prove fastapi yes "holds holds"
prove monorepo yes "holds holds"
prove nextjs yes "holds holds"

finish "G2 FIXTURES"
