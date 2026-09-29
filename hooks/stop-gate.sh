#!/usr/bin/env bash
set -uo pipefail
export VERIFY_START="$(date +%s)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

if [ ! -s "$ROOT/.claude/gates.json" ]; then
  git -C "$ROOT" ls-files --error-unmatch .claude/gates.json >/dev/null 2>&1 || exit 0
fi

SID=""; EVENT=""
eval "$(python3 "$HERE/state.py" stdin 2>/dev/null)"
[ "$EVENT" = "SubagentStop" ] && exit 0

# Never $ROOT/bin/verify: a stub committed to the repo would become the runner and certify red as green.
VERIFY="$HERE/../bin/verify"
[ -x "$VERIFY" ] || VERIFY="${CLAUDE_PLUGIN_ROOT:-/nonexistent}/bin/verify"
if [ ! -x "$VERIFY" ]; then
  printf '%s\n' '{"systemMessage":"NO VERDICT: no gate runner was found beside the hook or in the plugin, so nothing was checked"}'
  exit 0
fi

export CLAUDE_PROJECT_DIR="$ROOT" VERIFY_SESSION_ID="$SID"
exec "$VERIFY" done --hook
