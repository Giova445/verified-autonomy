#!/usr/bin/env bash
# Announce the contract only where it applies. Silent in projects with no gates.json,
# so a globally-installed plugin does not tax every unrelated session with context.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -f "$ROOT/.claude/gates.json" ] || exit 0

python3 - <<'PY'
import json
msg = """<verified-autonomy>
This project has mechanical gates. `./bin/verify done` must exit 0 before you may claim
completion — a Stop hook enforces this and will refuse to let the turn end while gates are red.

- Fix the CODE. Never weaken, skip, or delete a test; never add `|| true`, raise a timeout,
  or add a retry to force green.
- Never edit bin/verify, .claude/gates.json, .claude/hooks/**, or .github/workflows/**.
  If a gate is wrong, say so and stop.
- Before editing a symbol, run `./bin/verify blast <symbol>`. Zero callers is a hypothesis,
  not permission to delete.
- Retry budget is 3 per failing gate. On exhaustion write a blocked report: failing gate +
  command + exit code, what you tried and why each attempt failed, the decision needing a
  human, and a recommendation.
</verified-autonomy>"""
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": msg}}))
PY
