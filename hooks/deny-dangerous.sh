#!/usr/bin/env bash
set -uo pipefail

INPUT="$(cat)"

eval "$(python3 - "$INPUT" <<'PY'
import json, shlex, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    d = {}
ti = d.get("tool_input") or {}
print("TOOL=" + shlex.quote(str(d.get("tool_name") or "")))
print("CMD="  + shlex.quote(str(ti.get("command")   or "")))
PY
)"

[ "$TOOL" != "Bash" ] && exit 0
[ -z "$CMD" ] && exit 0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

MASKED="$(python3 "$HERE/inert-mask.py" "$CMD" 2>/dev/null)" || MASKED="$CMD"
[ -z "$MASKED" ] && MASKED="$CMD"
# Quotes become spaces so anchored rules still see bash -c "rm -rf /"; ';' stays for the WHERE check.
SCAN="$(printf '%s' "$MASKED" | tr '"'"'"'`()' '      ')"

deny() { echo "BLOCKED by deny-dangerous.sh: $1" >&2; exit 2; }

protected_branches() {
  if [ -f "$ROOT/.claude/protected-branches" ]; then
    grep -Ev '^[[:space:]]*(#|$)' "$ROOT/.claude/protected-branches"
  else
    printf 'main\nmaster\n'
  fi
}
PROTECTED="$(protected_branches | tr '\n' ' ')"

echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+/([[:space:]]|$)' \
  && deny "recursive force delete of the filesystem root"
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+~/?([[:space:]]|$)' \
  && deny "recursive force delete of the home directory"
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+/\*' \
  && deny "recursive force delete of everything under root"
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[rf]{2}[[:space:]]+\$' \
  && deny "rm -rf against an unresolved shell variable"

echo "$SCAN" | grep -Eq 'git[[:space:]]+reset[[:space:]]+--hard' \
  && deny "git reset --hard discards uncommitted work"
echo "$SCAN" | grep -Eq 'git[[:space:]]+clean[[:space:]]+-[a-z]*f' \
  && deny "git clean -f destroys untracked files"

echo "$SCAN" | grep -Eq 'git[[:space:]]+commit([[:space:]]|$)' \
  && printf '%s' "$CMD" | grep -Eiq '(^|[^a-z])co-authored-by:' \
  && deny "Co-Authored-By trailers are not allowed on any commit"

if echo "$SCAN" | grep -Eq 'git[[:space:]]+push([[:space:]]|$)'; then
  [ -f "$HERE/push-targets.py" ] || deny "push-targets.py is missing beside this hook, so protected branches cannot be checked"
  TARGETS="$(python3 "$HERE/push-targets.py" "$SCAN" "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)")"
  for t in $TARGETS; do
    case " $PROTECTED " in *" $t "*) deny "push to protected branch '$t' — deliver via a PR" ;; esac
  done
fi

if echo "$SCAN" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+merge'; then
  PR="$(printf '%s' "$SCAN" | grep -Eo 'gh[[:space:]]+pr[[:space:]]+merge[[:space:]]+[0-9]+' | grep -Eo '[0-9]+$')"
  BASE="$(python3 "$HERE/push-targets.py" --pr-base "$ROOT" "$PR")"
  [ -z "$BASE" ] && deny "cannot determine the PR's base branch, so it may be protected — merge it yourself"
  case " $PROTECTED " in *" $BASE "*) deny "merging into protected branch '$BASE' is the operator's decision" ;; esac
fi
echo "$SCAN" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+review([[:space:]]|$)' \
  && echo "$SCAN" | grep -Eq '(--approve|-a([[:space:]]|$))' \
  && deny "an agent may not approve a pull request"

echo "$SCAN" | grep -Eiq '(DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE)' \
  && deny "destructive DDL"
echo "$SCAN" | grep -Eiq 'DELETE[[:space:]]+FROM[[:space:]]+[a-z_.\"]+[[:space:]]*(;|$)' \
  && deny "DELETE FROM without a WHERE clause"

echo "$SCAN" | grep -Eq '(^|[[:space:]])sudo([[:space:]]|$)' && deny "sudo"
echo "$SCAN" | grep -Eq 'chmod[[:space:]]+(-[a-zA-Z]+[[:space:]]+)?777' && deny "chmod 777"
echo "$SCAN" | grep -Eq '(terraform[[:space:]]+destroy|gh[[:space:]]+repo[[:space:]]+delete)' \
  && deny "infrastructure or repository destruction"
echo "$SCAN" | grep -Eq '(\.aws/credentials|\.ssh/id_|\.netrc|\.pypirc)' \
  && deny "reading credential files"
echo "$SCAN" | grep -Eq '(jest[[:space:]].*-u([[:space:]]|$)|--update-snapshots|--snapshot-update|pact-broker[[:space:]]+publish)' \
  && deny "an agent may not re-record snapshots or contracts — propose the diff for approval"

GATE_CMD='(pytest|py\.test|jest|vitest|mocha|npm[[:space:]]+(run[[:space:]]+)?test|yarn[[:space:]]+test|pnpm[[:space:]]+test|make[[:space:]]+(test|lint|check)[a-z-]*|go[[:space:]]+test|cargo[[:space:]]+(test|clippy)|tox|ruff|mypy|tsc|eslint|bin/verify|selftest|scan-diff-cheats)'
echo "$SCAN" | grep -Eq "${GATE_CMD}[^|;&]*\|\|[[:space:]]*(true|:)([[:space:]]|;|$)" \
  && deny "exit-code suppression on a gate command — fix the failure instead"
echo "$SCAN" | grep -Eq -- '--exit-zero' \
  && deny "exit-code suppression on a linter"

exit 0
