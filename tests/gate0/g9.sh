#!/usr/bin/env bash
set -uo pipefail
SUITE=g9
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

export G4_CONTRACTS=spec

need_browser
ensure_python_deps
ensure_node_deps nextjs

ACCOUNT_EMAIL="tester@example.test"
ACCOUNT_PASSWORD="fixture-only-pw-1"

FAULTS_DIR="$GATE0/faults"
SPEC_DIR="$GATE0/spec"

FIXTURE_LIST="cli fastapi monorepo nextjs signin"
if [ -n "${G9_ONLY:-}" ]; then FIXTURE_LIST="$G9_ONLY"; fi

OUT_DIR="${G9_OUT:-${G4_OUT:-}}"
[ -n "$OUT_DIR" ] || { echo "set G9_OUT (or G4_OUT) to a directory that survives this run"; exit 2; }
mkdir -p "$OUT_DIR" || { echo "cannot create $OUT_DIR"; exit 2; }
OUT_DIR="$(cd "$OUT_DIR" && pwd -P)"
case "$OUT_DIR" in "$TMP"|"$TMP"/*) echo "G9_OUT must not be inside the run's temp dir $TMP"; exit 2 ;; esac

RESULTS_LOG="$OUT_DIR/results.tsv"
BASELINE_LOG="$OUT_DIR/baseline.tsv"
MISSED_LOG="$OUT_DIR/missed.tsv"
NOSIGNAL_LOG="$OUT_DIR/nosignal.tsv"
TIMING_LOG="$OUT_DIR/timing.txt"
RECEIPT="$OUT_DIR/receipt.txt"

for fixture in $FIXTURE_LIST; do
  [ -d "$SPEC_DIR/$fixture/.claude" ] || { echo "no spec contract at $SPEC_DIR/$fixture/.claude"; exit 2; }
done

classify(){
  python3 - "$1" <<'PY'
import json, sys
path = sys.argv[1] + "/.claude/evidence/product.json"
try:
    outs = json.load(open(path))["outcomes"]
except Exception as exc:
    print("no_signal")
    print("could not read product.json: %s" % exc)
    sys.exit(0)
verdicts = [o.get("verdict") for o in outs]
if any(v in ("FAILS", "NOT PROVEN", "WRONG BUILD") for v in verdicts):
    print("caught")
elif verdicts and all(v == "holds" for v in verdicts):
    print("missed")
else:
    print("no_signal")
print(" | ".join("%s=%s" % (o.get("name"), o.get("verdict")) for o in outs))
PY
}

verify_repo(){
  local fixture="$1" repo="$2" out="$3"
  if [ "$fixture" = "signin" ]; then
    ( export TEST_ACCOUNT_EMAIL="$ACCOUNT_EMAIL" TEST_ACCOUNT_PASSWORD="$ACCOUNT_PASSWORD"
      run_verify "$repo" "$out" )
  else
    run_verify "$repo" "$out"
  fi
}

keep_run(){
  local repo="$1" out="$2" dest="$3"
  mkdir -p "$dest"
  cp "$out" "$dest/verify.out" 2>/dev/null
  cp "$out.time" "$dest/verify.time" 2>/dev/null
  cp "$out.guard" "$dest/verify.guard" 2>/dev/null
  cp "$repo/.claude/evidence/product.json" "$dest/product.json" 2>/dev/null
  return 0
}

write_receipt(){
  {
    echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "commit: $(git -C "$PLUGIN" rev-parse HEAD)"
    echo "branch: $(git -C "$PLUGIN" rev-parse --abbrev-ref HEAD)"
    echo "dirty paths under tests/gate0, bin, hooks, benchmark: $(git -C "$PLUGIN" status --porcelain -- tests/gate0 bin hooks benchmark | wc -l | tr -d ' ')"
    git -C "$PLUGIN" status --porcelain -- tests/gate0 bin hooks benchmark | sed 's/^/  /'
    for path in tests/gate0/spec tests/gate0/faults tests/gate0/fixtures tests/gate0/tickets bin hooks; do
      echo "tree $path: $(git -C "$PLUGIN" rev-parse "HEAD:$path" 2>/dev/null || echo unknown)"
    done
    echo "sha256 g9.sh: $(shasum -a 256 "$GATE0/g9.sh" | cut -d' ' -f1)"
    echo "sha256 lib.sh: $(shasum -a 256 "$GATE0/lib.sh" | cut -d' ' -f1)"
    echo "sha256 drive.mjs: $(shasum -a 256 "$DRIVE" | cut -d' ' -f1)"
    echo "sha256 g9_report.py: $(shasum -a 256 "$GATE0/g9_report.py" | cut -d' ' -f1)"
    echo "sha256 G9-PREREGISTRATION.md: $(shasum -a 256 "$GATE0/G9-PREREGISTRATION.md" 2>/dev/null | cut -d' ' -f1)"
    echo "sha256 acceptance.py: $(shasum -a 256 "$PLUGIN/benchmark/gates/acceptance.py" | cut -d' ' -f1)"
    echo "last commit touching G9-PREREGISTRATION.md: $(git -C "$PLUGIN" log -1 --format='%H %cI' -- tests/gate0/G9-PREREGISTRATION.md 2>/dev/null)"
    echo "kill line MB: $KILL_MB"
    echo "fixtures: $FIXTURE_LIST"
    echo "PLAYWRIGHT_PATH: ${PLAYWRIGHT_PATH:-}"
    echo "TMPDIR: ${TMPDIR:-}"
    echo "python: $(python3 --version 2>&1)  node: $(node --version 2>&1)  uvicorn: $(command -v uvicorn || echo none)"
  } > "$RECEIPT"
}

wall_start="$(now)"
write_receipt

echo "G9: the spec agent's contracts against the seeded-fault corpus (preregistered: pooled catch rate >=80% on behaviour faults, state and wrong-field clauses per fixture)"
echo "contracts: $SPEC_DIR/<fixture>/.claude replaces each fixture's hand-written .claude"
echo "results kept in $OUT_DIR"

printf 'fixture\tok\tpeak_mb\tsecs\tverdicts\n' > "$BASELINE_LOG"
echo
echo "== baseline: the spec contract on each unpatched fixture must hold every outcome =="
baseline_bad=0
for fixture in $FIXTURE_LIST; do
  repo="$(make_repo "$fixture")"
  out="$TMP/baseline-$fixture.out"
  began="$(now)"
  verify_repo "$fixture" "$repo" "$out"; rc=$?
  ended="$(now)"
  keep_run "$repo" "$out" "$OUT_DIR/baseline/$fixture"
  got="$(verdicts "$repo")"
  peak="$(peak_mb "$out" || true)"; peak="${peak:-0}"
  n_out="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]+"/.claude/evidence/product.json"))["outcomes"]))' "$repo" 2>/dev/null || echo 0)"
  want="$(python3 -c 'import sys; print(" ".join(["holds"]*int(sys.argv[1])))' "$n_out")"
  if [ "$n_out" -gt 0 ] && [ "$got" = "$want" ] && [ "$rc" -eq 0 ]; then ok=yes; else ok=no; baseline_bad=$((baseline_bad+1)); fi
  chk "$fixture: spec contract holds every outcome on the unpatched app ($n_out outcomes, exit $rc)" "$ok" "yes"
  printf '  %s\n' "$got"
  if [ "$ok" = "no" ]; then
    outcome_rows "$repo" | awk -F'\t' '{ printf "        %-70s %-12s %s | %s | %s\n", substr($1,1,70), $2, $3, $4, $6 }'
    [ -s "$out.guard" ] && sed 's/^/        /' "$out.guard"
  fi
  stray="$(left_behind "$repo")"
  chk "$fixture: baseline left nothing listening or running" "$stray" "nothing"
  printf '%s\t%s\t%s\t%s\t%s\n' "$fixture" "$ok" "$peak" "$(span "$began" "$ended")" "$got" >> "$BASELINE_LOG"
  rm -rf "$repo"
done

if [ "$baseline_bad" -gt 0 ]; then
  echo
  echo "STOP: $baseline_bad spec contract(s) do not hold every outcome on the correct app."
  echo "A contract that fails on the correct app would inflate the catch rate; no fault was run."
  finish "G9 SPEC CONTRACTS"
fi
if [ -n "${G9_BASELINE_ONLY:-}" ]; then
  echo
  echo "baseline only: no fault was run"
  finish "G9 SPEC CONTRACTS"
fi

: > "$MISSED_LOG"
: > "$NOSIGNAL_LOG"
printf 'fixture\tid\tkind\tmarked\tpeak_mb\tsecs\tcategory\tdetail\n' > "$RESULTS_LOG"

grand_total=0; grand_caught=0; grand_missed=0; grand_nosignal=0; grand_applyfail=0
grand_peak=0; grand_stray=0; grand_guarded=0

for fixture in $FIXTURE_LIST; do
  manifest="$FAULTS_DIR/$fixture/manifest.json"
  [ -f "$manifest" ] || { echo "SKIP $fixture: no manifest at $manifest"; continue; }

  echo
  echo "== $fixture =="

  ids="$(python3 -c "import json; print(' '.join(e['id'] for e in json.load(open('$manifest'))))")"
  if [ -n "${G9_FAULTS:-}" ]; then
    picked=""
    for id in $ids; do
      if [[ " $G9_FAULTS " == *" $id "* ]]; then picked="$picked $id"; fi
    done
    ids="$picked"
  fi

  f_total=0; f_caught=0; f_missed=0; f_nosignal=0; f_applyfail=0; f_peak=0; f_stray=0; f_guarded=0
  cat_log="$TMP/$fixture-cats.tsv"
  : > "$cat_log"

  for id in $ids; do
    row="$(python3 -c "
import json
m = json.load(open('$manifest'))
e = next(x for x in m if x['id'] == '$id')
print(e['category'] + '\t' + e['statement'] + '\t' + ('break' if e['breaks_run'] else 'live'))
")"
    category="$(printf '%s' "$row" | cut -f1)"
    statement="$(printf '%s' "$row" | cut -f2)"
    marked="$(printf '%s' "$row" | cut -f3)"

    repo="$(make_repo "$fixture")"
    out="$TMP/$fixture-$id.out"

    if ! ( cd "$repo" && git apply "$FAULTS_DIR/$fixture/$id.patch" ) >"$TMP/$fixture-$id.apply.log" 2>&1; then
      f_applyfail=$((f_applyfail+1))
      echo "  APPLY-FAIL $id: $(tail -1 "$TMP/$fixture-$id.apply.log")"
      mkdir -p "$OUT_DIR/runs/$fixture/$id"; cp "$TMP/$fixture-$id.apply.log" "$OUT_DIR/runs/$fixture/$id/apply.log"
      rm -rf "$repo"
      continue
    fi

    began="$(now)"
    verify_repo "$fixture" "$repo" "$out"
    ended="$(now)"
    secs="$(span "$began" "$ended")"

    classify_out="$(classify "$repo")"
    kind="$(printf '%s\n' "$classify_out" | sed -n '1p')"
    detail="$(printf '%s\n' "$classify_out" | sed -n '2p')"
    keep_run "$repo" "$out" "$OUT_DIR/runs/$fixture/$id"

    stray="$(left_behind "$repo")"
    if [ "$stray" != "nothing" ]; then
      f_stray=$((f_stray+1))
      echo "  WARN $id: left behind: $stray"
    fi
    peak="$(peak_mb "$out" || true)"
    peak="${peak:-0}"
    [ "$peak" -gt "$f_peak" ] && f_peak="$peak"
    if [ -s "$out.guard" ]; then
      f_guarded=$((f_guarded+1))
      echo "  WARN $id: $(head -1 "$out.guard")"
    fi
    printf '  %-8s %-9s %-6s peak %s MB  %s s\n' "$id" "$kind" "$marked" "$peak" "$secs"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$fixture" "$id" "$kind" "$marked" "$peak" "$secs" "$category" "$detail" >> "$RESULTS_LOG"

    f_total=$((f_total+1))
    printf '%s\t%s\n' "$category" "$kind" >> "$cat_log"
    case "$kind" in
      caught) f_caught=$((f_caught+1)) ;;
      missed) f_missed=$((f_missed+1))
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$fixture" "$id" "$category" "$statement" "$detail" "$marked" >> "$MISSED_LOG" ;;
      no_signal) f_nosignal=$((f_nosignal+1))
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$fixture" "$id" "$category" "$statement" "$detail" "$marked" >> "$NOSIGNAL_LOG" ;;
    esac

    rm -rf "$repo"
  done

  echo "  faults: $f_total  caught: $f_caught  missed: $f_missed  no_signal: $f_nosignal  apply_fail: $f_applyfail"
  echo "  peak memory of any run: ${f_peak} MB (line is ${KILL_MB} MB)"

  chk "$fixture: every patch applied" "$f_applyfail" "0"
  chk "$fixture: no run's process tree went over ${KILL_MB} MB, none was killed by the guard" \
    "$([ "$f_peak" -le "$KILL_MB" ] && [ "$f_guarded" -eq 0 ] && echo yes || echo "no (peak $f_peak MB, $f_guarded guarded)")" "yes"
  chk "$fixture: nothing left listening or running after any run" "$f_stray run(s) left something" "0 run(s) left something"

  grand_total=$((grand_total+f_total))
  grand_caught=$((grand_caught+f_caught))
  grand_missed=$((grand_missed+f_missed))
  grand_nosignal=$((grand_nosignal+f_nosignal))
  grand_applyfail=$((grand_applyfail+f_applyfail))
  [ "$f_peak" -gt "$grand_peak" ] && grand_peak="$f_peak"
done

wall_end="$(now)"
{
  echo "faults_run: $grand_total"
  echo "wall_seconds_total: $(span "$wall_start" "$wall_end")"
  echo "peak_mb_any_run: $grand_peak"
  echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$TIMING_LOG"

echo
echo "== overall =="
echo "  faults: $grand_total  caught: $grand_caught  missed: $grand_missed  no_signal: $grand_nosignal  apply_fail: $grand_applyfail"
echo "  wall time of the run: $(span "$wall_start" "$wall_end") s"

echo
python3 "$GATE0/g9_report.py" "$OUT_DIR" ${G9_FIRST:+--first "$G9_FIRST"} ${G9_REPEAT:+--repeat "$G9_REPEAT"} ${G9_HAND_AFTER:+--hand-after "$G9_HAND_AFTER"} | tee "$OUT_DIR/report.txt"
if [ -n "${G9_FAULTS:-}" ]; then
  echo
  echo "partial run (G9_FAULTS is set): no verdict is drawn from a subset of the corpus"
else
  verdict="$(awk '/^PREREGISTERED VERDICT: / { v = $0; sub(/^PREREGISTERED VERDICT: /, "", v); sub(/ \(.*/, "", v); print v; exit }' "$OUT_DIR/report.txt")"
  chk "G9 preregistered verdict: pooled catch rate on behaviour faults at least 80%, each fixture's state and wrong-field clauses, no fixture rate bound below 80%" "${verdict:-unknown}" "MET"
fi

finish "G9 SPEC CONTRACTS"
