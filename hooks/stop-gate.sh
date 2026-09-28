#!/usr/bin/env bash
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

if [ ! -s "$ROOT/.claude/gates.json" ]; then
  if git -C "$ROOT" ls-files --error-unmatch .claude/gates.json >/dev/null 2>&1; then
    echo "Gate config .claude/gates.json is tracked but missing or empty. Restore it — removing the gate config is not a way to pass." >&2
    exit 2
  fi
  exit 0
fi

# Never $ROOT/bin/verify: a stub committed to the repo would become the runner and certify red as green.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
VERIFY="$SELF_DIR/../bin/verify"
[ -x "$VERIFY" ] || VERIFY="${CLAUDE_PLUGIN_ROOT:-/nonexistent}/bin/verify"
if [ ! -x "$VERIFY" ]; then
  echo "No usable gate runner found (checked plugin and $ROOT/bin/verify). Refusing to certify." >&2
  exit 2
fi

cat >/dev/null 2>&1 || true
CLAUDE_PROJECT_DIR="$ROOT" exec "$VERIFY" done --hook
