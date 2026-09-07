#!/usr/bin/env bash
# harness.sh — measure a PINNED detector against third-party-labeled transitions.
#
#   harness.sh <detector-path> <transitions.jsonl> [max]
#
# Runs the REAL detector on a REAL git repo per case. An earlier version of this measurement
# approximated the detector with a Python regex copied out of it; that measures the copy, not
# the tool, and any drift between them is invisible. Each case here is a two-commit repo and
# the hook is invoked exactly as it is in production.
#
# CANARIES RUN FIRST AND THE SCRIPT REFUSES WITHOUT THEM. A harness stuck on "detected"
# reports 100% recall; one stuck on "not detected" reports 0%. Both look like findings. This
# codebase has produced five vacuous-green measurements already, including the immediately
# preceding version of this very file, so the canaries are not ceremony.
set -uo pipefail
DET="${1:?usage: harness.sh <detector> <transitions.jsonl> [max]}"
TRANS="${2:?}"
MAX="${3:-100000}"
[ -x "$DET" ] || chmod +x "$DET" 2>/dev/null
[ -s "$DET" ] || { echo "harness: detector is missing or empty — refusing" >&2; exit 1; }

# Build a two-commit repo from a before/after pair and run the detector on the diff.
# Echoes: DETECTED | CLEAN | ERROR
probe() { # before after relpath
  local before="$1" after="$2" rel="$3"
  local d; d="$(mktemp -d)"
  ( cd "$d" && git init -q . && git config user.email h@h && git config user.name h ) || { echo ERROR; return; }
  mkdir -p "$d/$(dirname "$rel")"
  printf '%s\n' "$before" > "$d/$rel"
  ( cd "$d" && git add -A >/dev/null 2>&1 && git commit -qm before >/dev/null 2>&1 )
  printf '%s\n' "$after" > "$d/$rel"
  ( cd "$d" && git add -A >/dev/null 2>&1 && git commit -qm after >/dev/null 2>&1 )
  local out rc
  out="$( cd "$d" && CLAUDE_PROJECT_DIR="$d" bash "$DET" HEAD~1 2>&1 )"; rc=$?
  rm -rf "$d"
  # Only the skip/disable rule counts here. Another rule firing is not evidence that THIS
  # detector saw a disabled test, and folding it in would inflate recall.
  if printf '%s' "$out" | grep -q 'CHEAT-FLAG \[skip-added\]'; then echo DETECTED
  elif [ "$rc" -le 1 ]; then echo CLEAN
  else echo ERROR; fi
}

echo "detector : $DET"
echo "sha256   : $(shasum -a 256 "$DET" | cut -c1-16)"
echo

# ---------------------------------------------------------------- canaries
echo "canaries (both directions — the run aborts if either fails):"
CAN_POS_B='public class T {
    @Test
    public void aTest() { assertEquals(1, f()); }
}'
CAN_POS_A='public class T {
    @Disabled
    @Test
    public void aTest() { assertEquals(1, f()); }
}'
CAN_NEG_A='public class T {
    @Test
    public void aTest() { assertEquals(2, f()); }
}'
r1="$(probe "$CAN_POS_B" "$CAN_POS_A" "src/test/java/T.java")"
r2="$(probe "$CAN_POS_B" "$CAN_NEG_A" "src/test/java/T.java")"
printf '  %-46s %s\n' "known-disabling (@Disabled added) -> DETECTED" "$r1"
printf '  %-46s %s\n' "known-neutral (assert value changed) -> CLEAN" "$r2"
if [ "$r1" != "DETECTED" ] || [ "$r2" != "CLEAN" ]; then
  echo
  echo "CANARY FAILED. The harness cannot distinguish the two answers, so every number it"
  echo "would produce is meaningless. Refusing to report a recall figure." >&2
  exit 1
fi
echo "  canaries ok — the harness can report both answers"
echo

# ---------------------------------------------------------------- measure
TP=0; FN=0; FP=0; TN=0; ERR=0

# Materialise each case as three plain files before the loop. An earlier draft passed the
# JSON fields through `eval` of an inline python one-liner; the nested quoting broke, every
# variable came back unbound, and the loop scored nothing. The canaries above still passed,
# which is exactly why they are not sufficient on their own -- they exercise probe(), not the
# case reader. Plain files have no quoting problem to get wrong.
CASES="$(mktemp -d)"
python3 - "$TRANS" "$CASES" "$MAX" <<'PY'
import json, os, sys
trans, out, mx = sys.argv[1], sys.argv[2], int(sys.argv[3])
i = 0
for line in open(trans):
    if i >= mx: break
    try: t = json.loads(line)
    except Exception: continue
    d = os.path.join(out, f"{i:06d}"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "before"), "w").write(t.get("before") or "")
    open(os.path.join(d, "after"),  "w").write(t.get("after")  or "")
    open(os.path.join(d, "label"),  "w").write(t.get("label")  or "")
    i += 1
print(i)
PY
NCASES="$(ls "$CASES" | wc -l | tr -d ' ')"
[ "${NCASES:-0}" -eq 0 ] && { echo "harness: no cases materialised — refusing" >&2; rm -rf "$CASES"; exit 1; }
echo "cases: $NCASES"
echo

for d in "$CASES"/*/; do
  CASE_BEFORE="$(cat "$d/before")"
  CASE_AFTER="$(cat "$d/after")"
  CASE_LABEL="$(cat "$d/label")"
  [ -z "$CASE_LABEL" ] && { ERR=$((ERR+1)); continue; }
  v="$(probe "$CASE_BEFORE" "$CASE_AFTER" "src/test/java/T.java")"
  case "$CASE_LABEL:$v" in
    disabling:DETECTED) TP=$((TP+1)) ;;
    disabling:CLEAN)    FN=$((FN+1)) ;;
    neutral:DETECTED)   FP=$((FP+1)) ;;
    neutral:CLEAN)      TN=$((TN+1)) ;;
    *)                  ERR=$((ERR+1)) ;;
  esac
done
rm -rf "$CASES"

# A run that classified nothing must not print a matrix of zeros as if it were a result.
if [ $((TP+FN+FP+TN)) -eq 0 ]; then
  echo "harness: every case errored — refusing to report a matrix" >&2; exit 1
fi

python3 - "$TP" "$FN" "$FP" "$TN" "$ERR" <<'PY'
import sys, math
tp,fn,fp,tn,err = map(int, sys.argv[1:6])
def wilson(k,n,z=1.96):
    if n==0: return None
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (max(0.0,c-h), min(1.0,c+h))
pos, neg = tp+fn, fp+tn
print("confusion matrix (labels from the corpus, not from me):")
print(f"                  detected   clean")
print(f"  disabling  (P)   {tp:>6}   {fn:>6}     n={pos}")
print(f"  neutral    (N)   {fp:>6}   {tn:>6}     n={neg}")
if err: print(f"  harness errors: {err}")
print()
if pos:
    lo,hi = wilson(tp,pos)
    print(f"  RECALL      {tp}/{pos} = {tp/pos*100:.1f}%   95% Wilson CI [{lo*100:.1f}%, {hi*100:.1f}%]")
if neg:
    lo,hi = wilson(tn,neg)
    print(f"  SPECIFICITY {tn}/{neg} = {tn/neg*100:.1f}%   95% Wilson CI [{lo*100:.1f}%, {hi*100:.1f}%]")
else:
    print("  SPECIFICITY not measured — no negatives in this corpus slice")
PY
