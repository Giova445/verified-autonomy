#!/usr/bin/env bash
set -uo pipefail

BASE="${1:-origin/main}"
git rev-parse --verify "$BASE" >/dev/null 2>&1 || BASE="$(git rev-parse --verify HEAD~1 2>/dev/null || echo HEAD)"

BASE_SHA="$(git rev-parse "$BASE" 2>/dev/null || echo)"
HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || echo)"
DIFF="$( {
  [ -n "$BASE_SHA" ] && [ "$BASE_SHA" != "$HEAD_SHA" ] && git diff "$BASE"...HEAD 2>/dev/null
  git diff HEAD 2>/dev/null
  git diff --cached 2>/dev/null
  for f in $(git ls-files --others --exclude-standard 2>/dev/null); do
    git diff --no-index /dev/null "$f" 2>/dev/null
  done
} )"
[ -z "$DIFF" ] && { echo "scan-diff-cheats: empty diff vs $BASE"; exit 0; }

SELF_RE='(hooks/scan-diff-cheats\.sh|hooks/deny-dangerous\.sh|benchmark/(scenarios|pressure)/|/selftest\.sh|\.md$)'
DIFF="$(printf '%s' "$DIFF" | awk -v re="$SELF_RE" '
  /^diff --git/ { skip = ($0 ~ re) }
  !skip { print }
')"

ADDED="$(printf '%s' "$DIFF" | grep '^+' | grep -v '^+++' || true)"
REMOVED="$(printf '%s' "$DIFF" | grep '^-' | grep -v '^---' || true)"
FLAGS=0

FLAG_KINDS=""
flag() { echo "CHEAT-FLAG [$1] $2"; FLAGS=$((FLAGS + 1)); FLAG_KINDS="$(printf '%s\n%s' "$FLAG_KINDS" "$1")"; }

n_skip_add=$(printf '%s' "$ADDED"   | grep -cE '(\.skip\(|\bxit\(|\bxdescribe\(|@Disabled|@Ignore|@Test[[:space:]]*\([^)]*enabled[[:space:]]*=[[:space:]]*false|//[[:space:]]*@Test|@pytest\.mark\.skip|@unittest\.skip|t\.Skip\(|#\[ignore\])' || true)
n_skip_rem=$(printf '%s' "$REMOVED" | grep -cE '(\.skip\(|\bxit\(|\bxdescribe\(|@Disabled|@Ignore|@Test[[:space:]]*\([^)]*enabled[[:space:]]*=[[:space:]]*false|//[[:space:]]*@Test|@pytest\.mark\.skip|@unittest\.skip|t\.Skip\(|#\[ignore\])' || true)
if [ "$n_skip_add" -gt "$n_skip_rem" ]; then
  UNTRACKED=$(printf '%s' "$ADDED" | grep -E '(\.skip\(|\bxit\(|\bxdescribe\(|@Disabled|@Ignore|@Test[[:space:]]*\([^)]*enabled[[:space:]]*=[[:space:]]*false|//[[:space:]]*@Test|@pytest\.mark\.skip|@unittest\.skip|t\.Skip\(|#\[ignore\])' \
    | grep -vcE 'reason[[:space:]]*=.*(@[A-Za-z]|[A-Z]+-[0-9]+|[0-9]{4}-[0-9]{2}-[0-9]{2})' || true)
  if [ "${UNTRACKED:-0}" -gt 0 ]; then
    flag skip-added "net +$((n_skip_add - n_skip_rem)) skipped/disabled tests, $UNTRACKED without a tracked reason (need reason= with an owner, ticket or review date)"
  else
    echo "  note: skip(s) added, each carrying a tracked reason (owner/ticket/date) — treated as quarantine, not a cheat"
  fi
fi

n_as_add=$(printf '%s' "$ADDED"   | grep -cE '(\bassert\b|\bexpect\(|assertEqual|assertTrue|assertRaises|\.should\b|require\.|assert_eq!)' || true)
n_as_rem=$(printf '%s' "$REMOVED" | grep -cE '(\bassert\b|\bexpect\(|assertEqual|assertTrue|assertRaises|\.should\b|require\.|assert_eq!)' || true)
[ "$n_as_rem" -gt "$n_as_add" ] && flag assertion-removed "net -$((n_as_rem - n_as_add)) assertions"

printf '%s' "$ADDED" | grep -qE '(\|\|[[:space:]]*true|set \+e|--exit-zero|continue-on-error:[[:space:]]*true|--passWithNoTests)' \
  && flag exit-suppression "exit-code suppression added"

printf '%s' "$ADDED" | grep -qE '(@flaky|\bretries?[[:space:]]*[:=][[:space:]]*[1-9]|--retries[[:space:]]*[1-9]|\.retry\(|reruns[[:space:]]*=)' \
  && flag retry-added "retry or rerun added — quarantine the flake, do not retry it to green"

TEST_ADDED="$(printf '%s' "$DIFF" | awk '
  /^\+\+\+ / { p=$2; sub(/^b\//,"",p)
    keep = (p ~ /(^|\/)(tests?|spec|__tests__|e2e)\//) || (p ~ /(test|spec)_|_(test|spec)\.|\.(test|spec)\./) }
  keep && /^[+][^+]/ { print }')"
printf '%s' "$TEST_ADDED" | grep -qE '(waitForTimeout\(|time\.sleep\(|Thread\.sleep\(|setTimeout\([^,]*,[[:space:]]*[0-9]{3,})' \
  && flag hard-wait "hard-coded wait added in a test — use auto-waiting assertions"

SNAP="$(printf '%s' "$DIFF" | grep -E '^\+\+\+ b/.*(__snapshots__|\.snap|\.pact\.json|approved\.txt|__approvals__)' || true)"
if [ -n "$SNAP" ]; then
  SRC="$(git diff --name-only "$BASE"...HEAD 2>/dev/null | grep -vE '(__snapshots__|\.snap$|\.pact\.json$|approved\.txt$|test|spec)' || true)"
  [ -z "$SRC" ] && flag snapshot-rubber-stamp "baseline files rewritten with no corresponding source change"
fi

CHANGED="$(git diff --name-only "$BASE"...HEAD 2>/dev/null || true)"
NONTEST="$(printf '%s\n' "$CHANGED" | grep -vE '(^|/)(tests?|spec|__tests__|e2e)/|\.(test|spec)\.[a-z]+$|_test\.(py|go|rs)$' | grep -v '^$' || true)"
if [ -n "$CHANGED" ] && [ -z "$NONTEST" ]; then
  SUBJ="$(git log -1 --pretty=%s 2>/dev/null || true)"
  case "$SUBJ" in
    test:*|test\(*|chore\(test*|ci:*|ci\(*) ;;
    *)
      printf '%s' "$SUBJ" | grep -qiE '^(fix|bugfix)|(\bbug\b|\bregression\b|\bbroken\b)' \
        && flag test-only-bugfix "commit claims a fix but changed only test files" ;;
  esac
fi

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
if re.search(r"except[^:\n]*:\s*\n\s*return\s+(\{\}|\[\]|None|0|\"\"|''|False)\s*$", body, re.M):
    hits.append("except -> return default")
if re.search(r"catch\s*(\([^)]*\))?\s*\{\s*\n?\s*return\s+(\{\}|\[\]|null|undefined|0|false)\s*;?\s*\n?\s*\}", body):
    hits.append("catch -> return default")
if re.search(r"\.unwrap_or_default\(\)\s*;?\s*//\s*ignore", body): hits.append("ignored Result")
sys.exit(0 if not hits else 1)
' || flag swallowed-error "empty catch or discarded error — log with context or rethrow"

python3 - "$ADDED" "$REMOVED" <<'PYEOF' || flag assertion-weakened "assertion replaced with a weaker one — the count is flat but less is checked"
import re, sys
add, rem = sys.argv[1], sys.argv[2]
WEAK = re.compile(r"(is\s+(not\s+)?None|!=\s*None|==\s*None|assertIsNotNone|assertIsNone|"
                  r"toBeDefined\(\)|toBeTruthy\(\)|toBeFalsy\(\)|assertTrue\([^,)]*\)\s*$|"
                  r"\bassert\s+[A-Za-z_][A-Za-z0-9_.\[\]()]*\s*$)")
STRONG = re.compile(r"(==|!=|<=|>=|[^<>=!]<[^<]|[^<>=!]>[^>]|assertEqual|assertNotEqual|"
                    r"toEqual|toBe\(|assert_eq!|\bin\b|assertIn|pytest\.approx|assertAlmostEqual)")
def strong(block):
    n = 0
    for line in block.splitlines():
        t = line[1:] if line[:1] in "+-" else line
        if "assert" not in t and "expect" not in t: continue
        if WEAK.search(t) and not re.search(r"(==|!=|assertEqual|toEqual)\s*[^N]", t): continue
        if STRONG.search(t): n += 1
    return n
def proxy(block):
    return sum(1 for l in block.splitlines()
               if ("assert" in l or "expect" in l)
               and re.search(r"(len\(|\.length|\.count\(|\.size\(|type\()", l))
sa, sr = strong(add), strong(rem)
pa, pr = proxy(add), proxy(rem)
weakened = (sr > sa) or (pa > pr and sr >= sa and sr > 0)
sys.exit(1 if weakened else 0)
PYEOF

n_exc_add=$(printf '%s' "$ADDED"   | grep -cE '(pytest\.raises|assertRaises|toThrow|\.should\.throw|#\[should_panic\]|assert_panics)' || true)
n_exc_rem=$(printf '%s' "$REMOVED" | grep -cE '(pytest\.raises|assertRaises|toThrow|\.should\.throw|#\[should_panic\]|assert_panics)' || true)
[ "$n_exc_rem" -gt "$n_exc_add" ] \
  && flag exception-expectation-dropped "net -$((n_exc_rem - n_exc_add)) expected-exception checks — a contract that must raise now merely returns"

SRC_ADDED="$(printf '%s' "$DIFF" | awk '
  /^\+\+\+ / { p=$2; sub(/^b\//,"",p)
    skip = (p ~ /(^|\/)(tests?|spec|__tests__|e2e)\//) || (p ~ /(test|spec)_|_(test|spec)\./) }
  !skip && /^[+][^+]/ { print }')"
if [ -n "$SRC_ADDED" ]; then
  python3 - "$SRC_ADDED" <<'PYEOF' || flag special-cased "production branch keyed to a literal value — special-casing a known input is not a fix"
import re, sys
block = sys.argv[1]
lines = [l[1:] for l in block.splitlines()]
hits = []
for i, t in enumerate(lines):
    m = re.search(r"\bif\s+.*==\s*(-?\d{2,}|[\"'][^\"']+[\"'])\s*[:)]", t)
    if not m: continue
    lit = m.group(1)
    if re.search(r"(VERSION|STATUS|ERROR|HTTP|PORT|_CODE|CONST)", t.upper()): continue
    tail = " ".join(lines[i+1:i+3])
    if re.search(r"\breturn\s+(-?\d+|[\"'][^\"']*[\"']|True|False|\[\]|\{\})", tail):
        hits.append(f"literal {lit}")
sys.exit(1 if hits else 0)
PYEOF
fi

printf '%s\n' "$CHANGED" | grep -qE '(\.claude/(hooks|gates\.json|settings\.json)|\.github/workflows/)' \
  && flag guardrail-edit "gate config, hooks, or CI modified inside a feature change"

if [ "$FLAGS" -eq 1 ] && printf '%s' "$FLAG_KINDS" | grep -q '^guardrail-edit$'; then
  JUST="$(git log -1 --format='%B' 2>/dev/null | grep -iE '^Guardrail-Change:' || true)"
  if [ -n "$JUST" ]; then
    echo "  guardrail-edit is JUSTIFIED by the commit trailer:"
    printf '    %s\n' "$JUST"
    echo "  (recorded in git history; still requires human review on the PR)"
    echo "---"
    echo "scan-diff-cheats: 1 flag, justified"
    exit 0
  fi
  echo "  guardrail-edit has NO justification. If this change to the enforcement layer is"
  echo "  intentional, record why with a commit trailer:"
  echo "    Guardrail-Change: <why this edit to gates/hooks/CI is correct>"
fi

echo "---"
if [ "$FLAGS" -gt 0 ]; then
  echo "scan-diff-cheats: $FLAGS flag(s). Each needs a fix or a written justification."
  exit 1
fi
echo "scan-diff-cheats: clean"
exit 0
