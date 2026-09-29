#!/usr/bin/env bash
set -uo pipefail
SUITE=g3
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

RUNS="${G3_RUNS:-30}"
MAX_FALSE_FAILS="${G3_MAX_FALSE_FAILS:-1}"
BUDGET_MB="${VERIFY_MEMORY_MB:-600}"
OUT="${G3_OUT:-${TMPDIR:-/tmp}/g3-out}"
STATS="$GATE0/g3_stats.py"
TSV="$OUT/runs.tsv"
ACCOUNT_EMAIL="tester@example.test"
ACCOUNT_PASSWORD="fixture-only-pw-1"

case "$RUNS" in ''|*[!0-9]*|0) echo "G3_RUNS must be a positive integer, got '$RUNS'"; exit 2 ;; esac

need_browser
ensure_python_deps
ensure_node_deps nextjs

mtime(){ stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null; }
load_now(){ uptime | sed 's/.*load averages*: //'; }
load_first(){ load_now | tr -d ',' | awk '{ print $1 }'; }
wall_of(){ awk -v a="$1" -v b="$2" 'BEGIN { printf "%.1f", b - a }'; }

drive_verify(){
  local name="$1" repo="$2" out="$3"
  if [ "$name" = "signin" ]; then
    ( export TEST_ACCOUNT_EMAIL="$ACCOUNT_EMAIL" TEST_ACCOUNT_PASSWORD="$ACCOUNT_PASSWORD"; run_verify "$repo" "$out" )
  else
    run_verify "$repo" "$out"
  fi
}

keep_evidence(){
  local name="$1" repo="$2" n="$3" out="$4" dest
  dest="$OUT/$name-run$(printf '%02d' "$n")"
  mkdir -p "$dest"
  cp -R "$repo/.claude/evidence/." "$dest/" 2>/dev/null
  cp "$out" "$dest/verify-output.txt" 2>/dev/null
  printf '%s' "$dest"
}

one_run(){
  local name="$1" repo="$2" n="$3" out="$4" builds="$5"
  local load began ended rc wall peak before after built cols verdicts bad left kept
  load="$(load_first)"
  before="$(mtime "$repo/.claude/evidence/build-local.log")"
  began="$(now)"
  drive_verify "$name" "$repo" "$out"; rc=$?
  ended="$(now)"
  after="$(mtime "$repo/.claude/evidence/build-local.log")"
  wall="$(wall_of "$began" "$ended")"
  peak="$(peak_mb "$out")"; peak="${peak:--}"
  built="n/a"; [ "$builds" = "yes" ] && built="$([ "$before" = "$after" ] && echo skipped || echo ran)"
  cols="$(python3 "$STATS" classify "$repo" "$rc")" || cols="-"$'\t'"CLASSIFY ERROR"
  verdicts="${cols%%$'\t'*}"; bad="${cols#*$'\t'}"
  left="$(left_behind "$repo")"
  logged_ports "$repo" >> "$TMP/$name.ports"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$n" "$rc" "$wall" "$peak" "$built" "$load" "$verdicts" "$bad" "$left" >> "$TSV"
  printf '  run %02d  %-24s exit %-3s %6s s  %5s MB  load %5s  build %-7s' "$n" "$verdicts" "$rc" "$wall" "$peak" "$load" "$built"
  if [ "$bad" != "-" ]; then
    printf '  NOT holds: %s\n' "$bad"
    kept="$(keep_evidence "$name" "$repo" "$n" "$out")"
    note "evidence kept in $kept"
    python3 "$STATS" excerpt "$repo" "$out"
  else
    printf '\n'
  fi
  [ "$left" = "nothing" ] || note "left behind after run $n: $left"
  guard_said "$out" | sed 's/^/        /'
}

ports_still_listening(){
  local name="$1" port found=""
  for port in $(sort -u "$TMP/$name.ports" 2>/dev/null); do
    listening "$port" && found="$found $port"
  done
  found="${found:-none}"
  printf '%s' "${found# }"
}

prove(){
  local name="$1" repo out builds="no" began ended
  repo="$(make_repo "$name")"
  out="$TMP/$name.out"
  : > "$TMP/$name.ports"
  grep -q '"build"' "$repo/.claude/acceptance.json" && builds="yes"
  echo
  echo "$name: $RUNS consecutive runs of 'bin/verify product' on one unchanged copy"
  chk "$name: only sources are committed before the first run" "$(tracked_sources_only "$repo")" "0 dirty, 0 generated files tracked"
  note "load average at start of $name: $(load_now)"
  began="$(now)"
  for n in $(seq 1 "$RUNS"); do one_run "$name" "$repo" "$n" "$out" "$builds"; done
  ended="$(now)"
  note "load average at end of $name: $(load_now); $(wall_of "$began" "$ended") s for $RUNS runs"
  python3 "$STATS" summary "$TSV" "$name"
  chk "$name: all $RUNS runs were recorded" "$(python3 "$STATS" fact "$TSV" "$name" runs "$BUDGET_MB")" "$RUNS"
  chk "$name: at most $MAX_FALSE_FAILS false FAIL in $RUNS runs (a run with any outcome other than holds)" \
    "$(f="$(python3 "$STATS" fact "$TSV" "$name" false_runs "$BUDGET_MB")"; [ "$f" -le "$MAX_FALSE_FAILS" ] && echo "at most $MAX_FALSE_FAILS" || echo "$f false FAILs")" \
    "at most $MAX_FALSE_FAILS"
  chk "$name: every run's peak memory is under $BUDGET_MB MB" "$(python3 "$STATS" fact "$TSV" "$name" peak "$BUDGET_MB")" "within"
  chk "$name: nothing left listening or running after any run" "$(python3 "$STATS" fact "$TSV" "$name" leaks "$BUDGET_MB")" "nothing"
  chk "$name: no port from any run is still listening" "$(ports_still_listening "$name")" "none"
}

rm -rf "$OUT"; mkdir -p "$OUT"
: > "$TSV"

echo "G3: flake rate ($RUNS runs of the contract per fixture on unchanged code; at most $MAX_FALSE_FAILS false FAIL per fixture)"
note "commit: $(git -C "$PLUGIN" rev-parse --short HEAD 2>/dev/null || echo unknown), $(git -C "$PLUGIN" status --porcelain 2>/dev/null | wc -l | tr -d ' ') dirty path(s) in the tree"
note "machine: $(sysctl -n hw.ncpu 2>/dev/null || echo '?') cpus, load average at start $(load_now)"
note "per-run records and the evidence of every non-holds run: $OUT"
report_cache nextjs

prove cli
prove fastapi
prove monorepo
prove signin
prove nextjs

echo
note "load average at end of suite: $(load_now)"
finish "G3 FLAKE"
