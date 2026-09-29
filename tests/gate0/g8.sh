#!/usr/bin/env bash
set -uo pipefail
SUITE=g8
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

BUDGET_MB="${VERIFY_MEMORY_MB:-600}"
COLD_LIMIT_S="${GATE0_COLD_LIMIT_S:-180}"

need_browser
ensure_node_deps nextjs

mtime(){ stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null; }
below(){ if [ -n "$1" ] && [ "$1" -lt "$2" ]; then echo within; else echo "${1:-not measured}"; fi; }

measure(){
  local label="$1" repo="$2" out="$TMP/$1.out" before after began ended rc peak wall
  before="$(mtime "$repo/.claude/evidence/build-local.log")"
  began="$(now)"
  run_verify "$repo" "$out"; rc=$?
  ended="$(now)"
  after="$(mtime "$repo/.claude/evidence/build-local.log")"
  wall="$(span "$began" "$ended")"
  peak="$(peak_mb "$out")"
  guard_said "$out" | sed 's/^/        /'
  RUN_WALL="$wall"; RUN_BUILT="$([ "$before" = "$after" ] && echo skipped || echo ran)"
  chk "$label: verify product exits 0 and both outcomes hold" "$rc $(verdicts "$repo")" "0 holds holds"
  chk "$label: peak memory of the whole process tree ($(peak_mb "$out" || true) MB) is under $BUDGET_MB MB" "$(below "$peak" "$BUDGET_MB")" "within"
  chk "$label: nothing left listening or running" "$(left_behind "$repo")" "nothing"
  note "$label: ${wall} s wall, build $RUN_BUILT, peak $peak MB (verify meter, 0.5 s samples), largest single process $(largest_rss_mb "$out") MB RSS"
}

echo "G8: cost on the Next.js fixture (budget: under $BUDGET_MB MB for the whole process tree, under $COLD_LIMIT_S s cold)"
report_cache nextjs
note "machine: $(sysctl -n hw.ncpu 2>/dev/null || echo '?') cpus, load average $(uptime | sed 's/.*load averages*: //')"

repo="$(make_repo nextjs)"
chk "only sources are committed; node_modules is a link to the cache" \
  "$(tracked_sources_only "$repo") $([ -L "$repo/node_modules" ] && echo linked)" "0 dirty, 0 generated files tracked linked"
chk "no .next directory exists before the cold run" "$([ -e "$repo/.next" ] && echo present || echo absent)" "absent"

echo
echo "cold: fresh copy, no .next, no build stamp"
measure cold "$repo"
COLD_S="$RUN_WALL"; COLD_BUILT="$RUN_BUILT"
chk "cold: the build ran" "$COLD_BUILT" "ran"
chk "cold: wall time ${COLD_S} s is under $COLD_LIMIT_S s" "$([ "$COLD_S" -lt "$COLD_LIMIT_S" ] && echo within || echo "$COLD_S s")" "within"
note ".next is $(du -sk "$repo/.next" 2>/dev/null | awk '{ printf "%.0f MB", $1 / 1024 }') after the build"

echo
echo "warm: same tree again, so the build is skipped by its stamp"
measure warm "$repo"
chk "warm: the build was skipped for the exact tree it was built from" "$RUN_BUILT" "skipped"

echo
echo "warm rebuild: stamp removed, the build reruns with .next/cache present"
rm -f "$repo/.claude/evidence/build-local.stamp"
measure warm-rebuild "$repo"
chk "warm-rebuild: the build ran again" "$RUN_BUILT" "ran"

finish "G8 COST"
