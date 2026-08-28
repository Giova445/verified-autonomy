#!/usr/bin/env bash
# scan-diff-cheats.sh — detects the documented ways an agent fakes a green gate.
# See 03-definition-of-done.md §3. Run as a gate, and again in CI.
#
# Usage: scan-diff-cheats.sh [base-ref]      (default: origin/main, falls back to HEAD~1)
set -uo pipefail

BASE="${1:-origin/main}"
git rev-parse --verify "$BASE" >/dev/null 2>&1 || BASE="$(git rev-parse --verify HEAD~1 2>/dev/null || echo HEAD)"

DIFF="$(git diff "$BASE"...HEAD 2>/dev/null || git diff "$BASE" 2>/dev/null)"
[ -z "$DIFF" ] && { echo "scan-diff-cheats: empty diff vs $BASE"; exit 0; }

# Exclude files that legitimately contain cheat patterns AS DATA: the detectors themselves,
# benchmark fixtures that plant cheats on purpose, and prose that quotes them. Without this
# the scanner reads its own regex literals and self-flags — observed live: "net +7 skipped
# tests" on a change whose tracked diff contained zero skip additions.
SELF_RE='(hooks/scan-diff-cheats\.sh|hooks/deny-dangerous\.sh|benchmark/(scenarios|pressure)/|/selftest\.sh|\.md$)'
DIFF="$(printf '%s' "$DIFF" | awk -v re="$SELF_RE" '
  /^diff --git/ { skip = ($0 ~ re) }
  !skip { print }
')"

ADDED="$(printf '%s' "$DIFF" | grep '^+' | grep -v '^+++' || true)"
REMOVED="$(printf '%s' "$DIFF" | grep '^-' | grep -v '^---' || true)"
FLAGS=0

flag() { echo "CHEAT-FLAG [$1] $2"; FLAGS=$((FLAGS + 1)); }

# 1 — tests skipped or disabled
n_skip_add=$(printf '%s' "$ADDED"   | grep -cE '(\.skip\(|\bxit\(|\bxdescribe\(|@Disabled|@pytest\.mark\.skip|@unittest\.skip|t\.Skip\(|#\[ignore\])' || true)
n_skip_rem=$(printf '%s' "$REMOVED" | grep -cE '(\.skip\(|\bxit\(|\bxdescribe\(|@Disabled|@pytest\.mark\.skip|@unittest\.skip|t\.Skip\(|#\[ignore\])' || true)
[ "$n_skip_add" -gt "$n_skip_rem" ] && flag skip-added "net +$((n_skip_add - n_skip_rem)) skipped/disabled tests"

# 2 — assertions removed on net
n_as_add=$(printf '%s' "$ADDED"   | grep -cE '(\bassert\b|\bexpect\(|assertEqual|assertTrue|assertRaises|\.should\b|require\.|assert_eq!)' || true)
n_as_rem=$(printf '%s' "$REMOVED" | grep -cE '(\bassert\b|\bexpect\(|assertEqual|assertTrue|assertRaises|\.should\b|require\.|assert_eq!)' || true)
[ "$n_as_rem" -gt "$n_as_add" ] && flag assertion-removed "net -$((n_as_rem - n_as_add)) assertions"

# 3 — exit-code suppression
printf '%s' "$ADDED" | grep -qE '(\|\|[[:space:]]*true|set \+e|--exit-zero|continue-on-error:[[:space:]]*true|--passWithNoTests)' \
  && flag exit-suppression "exit-code suppression added"

# 4 — retry / timeout inflation presented as a fix
printf '%s' "$ADDED" | grep -qE '(@flaky|\bretries?[[:space:]]*[:=][[:space:]]*[1-9]|--retries[[:space:]]*[1-9]|\.retry\(|reruns[[:space:]]*=)' \
  && flag retry-added "retry or rerun added — quarantine the flake, do not retry it to green"

# 5 — sleep-based waits (flake factory)
printf '%s' "$ADDED" | grep -qE '(waitForTimeout\(|time\.sleep\(|Thread\.sleep\(|setTimeout\([^,]*,[[:space:]]*[0-9]{3,})' \
  && flag hard-wait "hard-coded wait added — use auto-waiting assertions"

# 6 — snapshot / contract baselines rewritten
SNAP="$(printf '%s' "$DIFF" | grep -E '^\+\+\+ b/.*(__snapshots__|\.snap|\.pact\.json|approved\.txt|__approvals__)' || true)"
if [ -n "$SNAP" ]; then
  SRC="$(git diff --name-only "$BASE"...HEAD 2>/dev/null | grep -vE '(__snapshots__|\.snap$|\.pact\.json$|approved\.txt$|test|spec)' || true)"
  [ -z "$SRC" ] && flag snapshot-rubber-stamp "baseline files rewritten with no corresponding source change"
fi

# 7 — bug fix that only touched tests
CHANGED="$(git diff --name-only "$BASE"...HEAD 2>/dev/null || true)"
NONTEST="$(printf '%s\n' "$CHANGED" | grep -vE '(^|/)(tests?|spec|__tests__|e2e)/|\.(test|spec)\.[a-z]+$|_test\.(py|go|rs)$' | grep -v '^$' || true)"
if [ -n "$CHANGED" ] && [ -z "$NONTEST" ]; then
  MSG="$(git log -1 --pretty=%B 2>/dev/null || true)"
  printf '%s' "$MSG" | grep -qiE '(^fix|bug|regression|broken)' \
    && flag test-only-bugfix "commit claims a fix but changed only test files"
fi

# 8 — silently swallowed errors (multi-line aware: the handler body is its own
#     diff line, so a line-by-line grep misses the most common form)
printf '%s' "$ADDED" | python3 -c '
import re, sys
lines = [l[1:] for l in sys.stdin.read().splitlines()]
body  = "\n".join(lines)
hits  = []
if re.search(r"except[^:\n]*:\s*\n\s*pass\b", body):     hits.append("except: pass")
if re.search(r"except[^:\n]*:\s*pass\b", body):            hits.append("except: pass")
if re.search(r"catch\s*(\([^)]*\))?\s*\{\s*\}", body):    hits.append("empty catch block")
if re.search(r"catch\s*(\([^)]*\))?\s*\{\s*\n\s*\}", body): hits.append("empty catch block")
if re.search(r"^\s*_\s*=\s*err\b", body, re.M):            hits.append("discarded Go error")
if re.search(r"\.unwrap_or_default\(\)\s*;?\s*//\s*ignore", body): hits.append("ignored Result")
sys.exit(0 if not hits else 1)
' || flag swallowed-error "empty catch or discarded error — log with context or rethrow"

# 9 — guardrail tampering
printf '%s\n' "$CHANGED" | grep -qE '(\.claude/(hooks|gates\.json|settings\.json)|\.github/workflows/)' \
  && flag guardrail-edit "gate config, hooks, or CI modified inside a feature change"

echo "---"
if [ "$FLAGS" -gt 0 ]; then
  echo "scan-diff-cheats: $FLAGS flag(s). Each needs a fix or a written justification."
  exit 1
fi
echo "scan-diff-cheats: clean"
exit 0
