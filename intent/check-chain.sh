#!/usr/bin/env bash
# check-chain — assert an intent/spec/plan chain carries its declared fields and that its
# work order is machine-consumable.
#
#   check-chain.sh <chain-dir> [<chain-dir> ...]   validate chains
#   check-chain.sh selftest                        run the positive controls
#
# Exit: 0 clean | 1 findings | 2 bad usage or a broken helper
#
# WHAT THIS CHECKS, AND WHAT IT CANNOT
#
# It checks that the five/four/five headings exist, that the frontmatter links each hop to
# the one before it, and that `- [ ]` checkboxes in the work order parse into tasks. It
# says NOTHING about whether the content under a heading is true, sufficient, or honest.
# A chain of five empty headings passes this. That is not a defect to fix later: field
# presence is the part that is mechanically decidable, and pretending the rest is decidable
# is how a check becomes theatre.
#
# WHY THE EXPECTED SETS ARE WRITTEN OUT LITERALLY
#
# They are NOT read from intent/templates/. If they were, deleting a heading from a template
# would delete the expectation along with it and every chain would keep passing while the
# standard quietly shrank. Same defect recorded in commit a25e83d, where a sibling gate's
# control derived a fixture count from len(RULES): removing a rule removed the detector and
# its expectation together, and the suite stayed green having tested less. The selftest
# asserts the SIZE of each set as a literal for the same reason.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# Overridable so the checker can run from a copy of intent/ that has been lifted out of
# this repo. Unset and absent is a FINDING, never a skip — see CONTROL 6.
LEDGER="${CHAIN_LEDGER:-$ROOT/bin/ledger}"

# --- the field sets. Declared here, never derived from the templates. -------------------
INTENT_FIELDS=("Problem" "Proposed outcome" "Affected users and systems" "Constraints" "Open questions")
SPEC_FIELDS=("Requirements" "Design" "Policy validation" "Flagged concerns")
PLAN_FIELDS=("Files changing" "Work order" "Tests needed" "Risks" "Proof statements")

findings=0
note() { printf '  %s\n' "$*" >&2; findings=$((findings+1)); }
ok()   { printf '  ok    %s\n' "$*"; }

# A file that cannot be read is a finding, never a pass.
readable() {
  local f="$1" label="$2"
  [ -f "$f" ]  || { note "MISSING  $label — $f"; return 1; }
  [ -r "$f" ]  || { note "UNREADABLE  $label — $f"; return 1; }
  [ -s "$f" ]  || { note "EMPTY  $label — $f"; return 1; }
  return 0
}

has_heading() {
  # Exact "## <name>" at the start of a line. Substring matching would let "## Risks and
  # mitigations" satisfy "Risks", which is a different section.
  grep -qE "^## ${2//\//\\/}[[:space:]]*$" "$1"
}

check_fields() {
  local f="$1" label="$2"; shift 2
  local bad=0 name
  for name in "$@"; do
    has_heading "$f" "$name" || { note "$label: missing section '## $name'"; bad=1; }
  done
  [ "$bad" -eq 0 ] && ok "$label — all $# section(s) present"
  return $bad
}

check_link() {
  # Frontmatter must point at the previous hop. A plan whose `spec:` line is blank is a
  # plan with no approved ancestor, which is the hop this chain exists to make visible.
  local f="$1" key="$2" want="$3" label="$4"
  local val
  val="$(sed -n "1,/^---[[:space:]]*$/p" "$f" | sed -n "s/^${key}:[[:space:]]*//p" \
        | head -1 | sed 's/[[:space:]]*#.*$//' | tr -d '[:space:]')"
  if [ -z "$val" ]; then
    note "$label: frontmatter '$key:' is empty — no link to the previous stage"; return 1
  fi
  case "$val" in
    *"$want") ok "$label — $key -> $val" ;;
    *) note "$label: frontmatter '$key: $val' does not reference $want"; return 1 ;;
  esac
}

check_workorder() {
  # The work order is machine-read: bin/ledger parses "- [ ]" checkboxes into tasks and
  # REFUSES a plan containing none, so this delegates rather than reimplementing the parser.
  # A second parser would drift from the one that actually runs.
  local plan="$1" label="$2"
  [ -x "$LEDGER" ] || { note "$label: $LEDGER missing or not executable — cannot verify the "\
"work order parses. Refusing to report this chain clean."; return 1; }
  local tmp out rc
  tmp="$(mktemp -d)" || { note "$label: mktemp failed"; return 1; }
  out="$(CLAUDE_PROJECT_DIR="$tmp" "$LEDGER" init chk --plan "$plan" 2>&1)"; rc=$?
  rm -rf "$tmp"
  if [ "$rc" -ne 0 ]; then
    note "$label: work order does not parse into tasks (ledger exit $rc)"
    printf '%s\n' "$out" | sed 's/^/          /' >&2
    return 1
  fi
  ok "$label — work order parses ($(printf '%s' "$out" | sed -n 's/.*: \([0-9]*\) task(s).*/\1/p') task(s))"
}

check_chain() {
  local d="$1"
  local before=$findings
  echo "chain: ${d#$ROOT/}"
  [ -d "$d" ] || { note "not a directory: $d"; return 1; }
  local i="$d/intent.md" s="$d/spec.md" p="$d/plan.md"
  readable "$i" "intent.md" && check_fields "$i" "intent.md" "${INTENT_FIELDS[@]}"
  readable "$s" "spec.md"   && { check_fields "$s" "spec.md" "${SPEC_FIELDS[@]}"; check_link "$s" "intent" "intent.md" "spec.md"; }
  readable "$p" "plan.md"   && { check_fields "$p" "plan.md" "${PLAN_FIELDS[@]}"; check_link "$p" "spec" "spec.md" "plan.md"; check_workorder "$p" "plan.md"; }
  [ "$findings" -eq "$before" ]
}

# ------------------------------------------------------------------ positive controls
# Every control below holds everything constant EXCEPT the property under test. The clean
# fixture is built once; each control mutates exactly one thing in a copy of it. A control
# that built its own broken fixture from scratch would not prove the checker discriminates —
# only that it dislikes that particular file.
pass=0; fail=0
chk() {
  local label="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then printf '  ok    %-52s (%s)\n' "$label" "$got"; pass=$((pass+1))
  else printf '  FAIL  %-52s got=%s want=%s\n' "$label" "$got" "$want"; fail=$((fail+1)); fi
}

fixture() {
  local d="$1"; mkdir -p "$d"
  { echo "---"; echo "status: draft"; echo "---"; echo
    echo "# Fixture — Intent"; echo
    local h; for h in "${INTENT_FIELDS[@]}"; do echo "## $h"; echo; echo "content"; echo; done
  } > "$d/intent.md"
  { echo "---"; echo "intent: ./intent.md"; echo "---"; echo
    echo "# Fixture — Spec"; echo
    local h; for h in "${SPEC_FIELDS[@]}"; do echo "## $h"; echo; echo "content"; echo; done
  } > "$d/spec.md"
  { echo "---"; echo "spec: ./spec.md"; echo "---"; echo
    echo "# Fixture — Plan"; echo
    local h
    for h in "${PLAN_FIELDS[@]}"; do
      echo "## $h"; echo
      [ "$h" = "Work order" ] && { echo "- [ ] Task 1 — do the thing"; echo "- [ ] Task 2 — do the other thing"; echo; } || { echo "content"; echo; }
    done
  } > "$d/plan.md"
}

run_quiet() { findings=0; check_chain "$1" >/dev/null 2>&1; echo "$findings"; }

selftest() {
  echo "intent chain checker — controls"
  echo

  # The expected sets are the standard. Asserting their SIZE as a literal is what stops a
  # future edit from deleting a required field and taking its expectation with it.
  chk "intent field set is still 5 fields" "${#INTENT_FIELDS[@]}" "5"
  chk "spec field set is still 4 fields"   "${#SPEC_FIELDS[@]}"   "4"
  chk "plan field set is still 5 fields"   "${#PLAN_FIELDS[@]}"   "5"

  local t; t="$(mktemp -d)" || { echo "mktemp failed"; return 2; }
  fixture "$t/clean"

  # CONTROL 0 — the baseline. Without this every control below is satisfiable by a checker
  # that fails everything.
  chk "clean fixture -> 0 findings" "$(run_quiet "$t/clean")" "0"

  # CONTROL 1 — one missing heading, one file, nothing else changed.
  local f
  for f in intent spec plan; do
    local victim
    case "$f" in
      intent) victim="${INTENT_FIELDS[2]}" ;;   # Affected users and systems
      spec)   victim="${SPEC_FIELDS[2]}"   ;;   # Policy validation
      plan)   victim="${PLAN_FIELDS[4]}"   ;;   # Proof statements
    esac
    cp -R "$t/clean" "$t/no-$f"
    grep -v "^## ${victim}\$" "$t/clean/$f.md" > "$t/no-$f/$f.md"
    chk "$f.md without '## $victim' -> flagged" "$(run_quiet "$t/no-$f")" "1"
  done

  # CONTROL 2 — a heading that CONTAINS a required name must not satisfy it. Substring
  # matching is the obvious implementation and it is wrong: '## Risks and mitigations' is
  # a different section from '## Risks'.
  cp -R "$t/clean" "$t/widened"
  sed 's/^## Risks$/## Risks and mitigations/' "$t/clean/plan.md" > "$t/widened/plan.md"
  chk "'## Risks and mitigations' does not satisfy 'Risks'" "$(run_quiet "$t/widened")" "1"

  # CONTROL 3 — the work order. A plan whose boxes are all checked yields zero tasks; the
  # ledger refuses it, and so must this.
  cp -R "$t/clean" "$t/checked"
  sed 's/^- \[ \]/- [x]/' "$t/clean/plan.md" > "$t/checked/plan.md"
  chk "plan with every box already checked -> flagged" "$(run_quiet "$t/checked")" "1"

  cp -R "$t/clean" "$t/noboxes"
  sed 's/^- \[ \] //' "$t/clean/plan.md" > "$t/noboxes/plan.md"
  chk "work order with no checkboxes -> flagged" "$(run_quiet "$t/noboxes")" "1"

  # CONTROL 4 — chain linkage. A plan with no ancestor is the failure the chain exists to
  # surface, and it is invisible to a field-presence check alone.
  cp -R "$t/clean" "$t/unlinked"
  sed 's|^spec: ./spec.md|spec:|' "$t/clean/plan.md" > "$t/unlinked/plan.md"
  chk "plan.md with an empty 'spec:' -> flagged" "$(run_quiet "$t/unlinked")" "1"

  cp -R "$t/clean" "$t/wronglink"
  sed 's|^intent: ./intent.md|intent: ./somewhere-else.txt|' "$t/clean/spec.md" > "$t/wronglink/spec.md"
  chk "spec.md pointing at a non-intent file -> flagged" "$(run_quiet "$t/wronglink")" "1"

  # CONTROL 5 — fail closed. Absent, empty and unreadable are each a finding, not a pass.
  cp -R "$t/clean" "$t/gone";   rm "$t/gone/spec.md"
  chk "missing spec.md -> flagged"  "$(run_quiet "$t/gone")"  "1"
  cp -R "$t/clean" "$t/empty";  : > "$t/empty/intent.md"
  chk "empty intent.md -> flagged"  "$(run_quiet "$t/empty")" "1"
  cp -R "$t/clean" "$t/nodir"; rm -rf "$t/nodir"
  chk "missing chain directory -> flagged" "$(run_quiet "$t/nodir")" "1"

  # CONTROL 6 — a broken helper must not read as clean. If bin/ledger cannot run, the work
  # order was never parsed, and reporting the chain clean would certify an unmeasured thing.
  cp -R "$t/clean" "$t/noledger"
  local keep="$LEDGER"; LEDGER="$t/definitely-not-here"
  chk "ledger unavailable -> flagged, not skipped" "$(run_quiet "$t/noledger")" "1"
  LEDGER="$keep"

  rm -rf "$t"
  echo
  if [ "$fail" -eq 0 ]; then echo "  intent chain checker ($((pass+fail)) checks)"; return 0
  else echo "  intent chain checker FAILED ($fail of $((pass+fail)) checks)"; return 1; fi
}

# ------------------------------------------------------------------ main
case "${1:-}" in
  selftest) selftest; exit $? ;;
  "" ) printf 'usage: %s <chain-dir> [...] | selftest\n' "${0##*/}" >&2; exit 2 ;;
esac

rc=0
for d in "$@"; do
  check_chain "$(cd "$d" 2>/dev/null && pwd || echo "$d")" || rc=1
  echo
done
if [ "$rc" -eq 0 ]; then echo "CHAIN OK"; else echo "CHAIN: $findings finding(s)"; fi
exit $rc
