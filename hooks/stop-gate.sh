#!/usr/bin/env bash
# Stop / SubagentStop gate. Exit 2 refuses the turn and feeds stderr back as the reason.
#
# Safe when installed globally: if the project has no .claude/gates.json there is nothing
# to enforce, so this exits 0 and stays out of the way. Enforcement is opt-in per project
# by adding that file.
#
# Prefers the project's own bin/verify (so a repo can pin its version); falls back to the
# copy bundled with the plugin.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -f "$ROOT/.claude/gates.json" ] || exit 0

VERIFY="$ROOT/bin/verify"
[ -x "$VERIFY" ] || VERIFY="${CLAUDE_PLUGIN_ROOT}/bin/verify"
[ -x "$VERIFY" ] || exit 0

cat >/dev/null 2>&1 || true      # drain hook stdin
CLAUDE_PROJECT_DIR="$ROOT" exec "$VERIFY" done --hook
