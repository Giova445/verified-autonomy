#!/usr/bin/env bash
set -uo pipefail
SUITE=g4
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

need_browser
ensure_python_deps
ensure_node_deps nextjs

ACCOUNT_EMAIL="tester@example.test"
ACCOUNT_PASSWORD="fixture-only-pw-1"

FAULTS_DIR="$GATE0/faults"

FIXTURE_LIST="cli fastapi monorepo nextjs signin"
if [ -n "${G4_ONLY:-}" ]; then FIXTURE_LIST="$G4_ONLY"; fi

ensure_tmp
OUT_DIR="${G4_OUT:-$TMP}"
mkdir -p "$OUT_DIR" || { echo "cannot create G4_OUT=$OUT_DIR"; exit 2; }
OUT_DIR="$(cd "$OUT_DIR" && pwd -P)"
MISSED_LOG="$OUT_DIR/missed.tsv"
NOSIGNAL_LOG="$OUT_DIR/nosignal.tsv"
RESULTS_LOG="$OUT_DIR/results.tsv"
: > "$MISSED_LOG"
: > "$NOSIGNAL_LOG"
printf 'fixture\tid\tkind\tmarked\tpeak_mb\tcategory\tdetail\n' > "$RESULTS_LOG"

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

echo "G4: planted faults per fixture (>=30 each), catch rate >=80%, false-PASS rate <=10%"

grand_total=0
grand_caught=0
grand_missed=0
grand_nosignal=0

for fixture in $FIXTURE_LIST; do
  manifest="$FAULTS_DIR/$fixture/manifest.json"
  [ -f "$manifest" ] || { echo "SKIP $fixture: no manifest at $manifest"; continue; }

  echo
  echo "== $fixture =="

  ids="$(python3 -c "import json; print(' '.join(e['id'] for e in json.load(open('$manifest'))))")"

  f_total=0
  f_caught=0
  f_missed=0
  f_nosignal=0
  f_applyfail=0
  f_peak=0
  f_stray=0
  f_guarded=0
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
      rm -rf "$repo"
      continue
    fi

    if [ "$fixture" = "signin" ]; then
      ( export TEST_ACCOUNT_EMAIL="$ACCOUNT_EMAIL" TEST_ACCOUNT_PASSWORD="$ACCOUNT_PASSWORD"
        run_verify "$repo" "$out" )
    else
      run_verify "$repo" "$out"
    fi

    classify_out="$(classify "$repo")"
    kind="$(printf '%s\n' "$classify_out" | sed -n '1p')"
    detail="$(printf '%s\n' "$classify_out" | sed -n '2p')"

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
    printf '  %-8s %-9s %-6s peak %s MB\n' "$id" "$kind" "$marked" "$peak"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$fixture" "$id" "$kind" "$marked" "$peak" "$category" "$detail" >> "$RESULTS_LOG"

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
  catch_pct="$(awk -v c="$f_caught" -v t="$f_total" 'BEGIN{ if (t>0) printf "%.1f", c*100.0/t; else print "0.0" }')"
  miss_pct="$(awk -v m="$f_missed" -v t="$f_total" 'BEGIN{ if (t>0) printf "%.1f", m*100.0/t; else print "0.0" }')"
  echo "  catch_rate: ${catch_pct}%  miss_rate: ${miss_pct}%"
  echo "  peak memory of any run: ${f_peak} MB (verify meter, whole process tree; line is ${KILL_MB} MB)"

  echo "  by category:"
  awk -F'\t' '
    { total[$1]++; if ($2 == "caught") caught[$1]++; else if ($2 == "missed") missed[$1]++; else nosig[$1]++ }
    END {
      for (c in total) {
        pct = total[c] > 0 ? caught[c] * 100.0 / total[c] : 0
        printf "    %-40s faults=%-3d caught=%-3d missed=%-3d no_signal=%-3d catch_rate=%.0f%%\n", \
          c, total[c], caught[c]+0, missed[c]+0, nosig[c]+0, pct
      }
    }' "$cat_log" | sort

  chk "$fixture: at least 30 faults planted" "$([ "$f_total" -ge 30 ] && echo yes || echo "no ($f_total)")" "yes"
  chk "$fixture: catch rate at least 80%" \
    "$(awk -v c="$f_caught" -v t="$f_total" 'BEGIN{ print (t>0 && c*100.0/t >= 80.0) ? "yes" : "no" }')" "yes"
  chk "$fixture: false-PASS (missed) rate at most 10%" \
    "$(awk -v m="$f_missed" -v t="$f_total" 'BEGIN{ print (t==0 || m*100.0/t <= 10.0) ? "yes" : "no" }')" "yes"

  chk "$fixture: no run's process tree went over ${KILL_MB} MB, none was killed by the guard" \
    "$([ "$f_peak" -le "$KILL_MB" ] && [ "$f_guarded" -eq 0 ] && echo yes || echo "no (peak $f_peak MB, $f_guarded guarded)")" "yes"
  chk "$fixture: nothing left listening or running after any run" "$f_stray run(s) left something" "0 run(s) left something"

  grand_total=$((grand_total+f_total))
  grand_caught=$((grand_caught+f_caught))
  grand_missed=$((grand_missed+f_missed))
  grand_nosignal=$((grand_nosignal+f_nosignal))
done

echo
echo "== overall =="
echo "  faults: $grand_total  caught: $grand_caught  missed: $grand_missed  no_signal: $grand_nosignal"

if [ -s "$MISSED_LOG" ]; then
  echo
  echo "missed faults (false PASS):"
  while IFS=$'\t' read -r fixture id category statement detail marked; do
    printf '  %-10s %-8s %-5s [%s] %s\n' "$fixture" "$id" "$marked" "$category" "$statement"
  done < "$MISSED_LOG"
fi

if [ -s "$NOSIGNAL_LOG" ]; then
  echo
  echo "no signal (CANNOT RUN / NO VERDICT, reported separately, counted as not caught):"
  while IFS=$'\t' read -r fixture id category statement detail marked; do
    printf '  %-10s %-8s %-5s [%s] %s -- %s\n' "$fixture" "$id" "$marked" "$category" "$statement" "$detail"
  done < "$NOSIGNAL_LOG"
fi

if [ -n "${G4_OUT:-}" ]; then
  echo
  echo "per-fault results kept in $OUT_DIR (results.tsv, missed.tsv, nosignal.tsv)"
fi

finish "G4 FAULTS"
