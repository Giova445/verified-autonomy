#!/usr/bin/env bash
# Score hooks/scan-diff-cheats.sh on the gold set, split into the cases its rules were
# TUNED on and cases they were not.
#
# The split is the point. c01-c12 were used to find the scanner's gaps, and rules 10-12 were
# written after seeing which of them failed — so a score on c01-c12 is a training score and
# means very little. c13-c22 were written and gold-labeled afterwards and run once. Report
# both, and treat the held-out number as the real one.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
REPOS="${1:-/tmp/judge-repos}"
[ -d "$REPOS" ] || bash "$HERE/build-cases.sh" "$REPOS" >/dev/null 2>&1

TUNED="c01 c02 c03 c04 c05 c06 c07 c08 c09 c10 c11 c12"
HELD="c13 c14 c15 c16 c17 c18 c19 c20 c21 c22"

score() {
  local label="$1"; shift
  local ok=0 n=0 wrong=""
  for id in $@; do
    local d="$REPOS/$id"; [ -d "$d" ] || continue
    local g; g="$(grep "^$id" "$HERE/gold.txt" | cut -f2)"
    # `local v` must NOT sit between the run and the $? read: `local` is itself a command
    # and resets $? to 0, which made every case score as "legitimate" and reported the
    # scanner at 5/12 when it was actually at 12/12. Declare first, capture immediately.
    local v rc
    ( cd "$d" && CLAUDE_PROJECT_DIR="$d" bash "$ROOT/hooks/scan-diff-cheats.sh" HEAD~1 >/dev/null 2>&1 )
    rc=$?
    [ "$rc" -eq 0 ] && v=legitimate || v=cheat
    n=$((n+1)); [ "$v" = "$g" ] && ok=$((ok+1)) || wrong="$wrong $id"
  done
  printf '  %-28s %2s/%-2s%s\n' "$label" "$ok" "$n" "${wrong:+   wrong:$wrong}"
}
echo "scan-diff-cheats vs gold labels"
score "tuned on these (c01-c12)"  $TUNED
score "HELD OUT (c13-c22)"        $HELD
echo
echo "  The held-out number is the one that means anything. Caveat that limits even it:"
echo "  the same author wrote the rules and the held-out cases, so the cases are shaped by"
echo "  a mental model of the rules. Independent cases, ideally from real PR history,"
echo "  would be the honest next step."
