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

# Fail CLOSED when a tracked gate config goes missing. Deleting .claude/gates.json used to
# silently disarm the whole layer: the hook exited 0 and completion was certified with no
# gates at all. If the file is tracked in git and is now absent or empty, that is tampering
# or a mistake — either way it is not a pass. If it was never tracked, the project has not
# opted in and the hook correctly stays out of the way.
if [ ! -s "$ROOT/.claude/gates.json" ]; then
  if git -C "$ROOT" ls-files --error-unmatch .claude/gates.json >/dev/null 2>&1; then
    echo "Gate config .claude/gates.json is tracked but missing or empty. Restore it — removing the gate config is not a way to pass." >&2
    exit 2
  fi
  exit 0
fi

# Prefer the plugin's own copy. Preferring $ROOT/bin/verify let a 17-byte stub committed
# into the repo replace the runner: the gate then certified whatever the stub said.
# ${CLAUDE_PLUGIN_ROOT:-} is deliberate — bare ${CLAUDE_PLUGIN_ROOT} under `set -u` aborts
# the hook with exit 1, and exit 1 does NOT block, so the gate failed open when the env var
# was absent.
# Resolve the runner from THIS SCRIPT'S OWN LOCATION, not from an env var and not from the
# repo. An earlier fix preferred ${CLAUDE_PLUGIN_ROOT}/bin/verify and fell back to
# $ROOT/bin/verify — but with the env var unset that fallback is a repo-committed path, so a
# 17-byte stub checked into the target repo became the gate runner and certified a red gate
# green (verified: exit 0). BASH_SOURCE cannot be spoofed by repo content.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
VERIFY="$SELF_DIR/../bin/verify"
[ -x "$VERIFY" ] || VERIFY="${CLAUDE_PLUGIN_ROOT:-/nonexistent}/bin/verify"
# Deliberately NO fallback to $ROOT/bin/verify: the repo is the untrusted side here.
if [ ! -x "$VERIFY" ]; then
  echo "No usable gate runner found (checked plugin and $ROOT/bin/verify). Refusing to certify." >&2
  exit 2
fi

cat >/dev/null 2>&1 || true      # drain hook stdin
CLAUDE_PROJECT_DIR="$ROOT" exec "$VERIFY" done --hook
