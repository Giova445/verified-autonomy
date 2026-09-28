#!/usr/bin/env bash
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
- No commit may carry a `Co-Authored-By` trailer.
- Retry budget is 3 per failing gate. On exhaustion write a blocked report: failing gate +
  command + exit code, what you tried and why each attempt failed, the decision needing a
  human, and a recommendation.
- Done also means the product: `.claude/acceptance.json` states what the user must be able to
  do or see, each checked against the running product, and every outcome holds. Write it
  before the code; `./bin/verify product` shows what is open.
</verified-autonomy>"""
import os
if os.environ.get("VERIFIED_AUTONOMY_UNATTENDED") == "1":
    msg += """
<unattended>
Nobody is watching this run, so ending a turn without a tool call stops the work. Do not end a
turn with a summary that names the next step instead of taking it, with an offer to continue,
with a list of decisions none of which blocks the rest, or because a milestone felt like a good
place to report. Put status notes and recommendations in the same message as your next tool
call. End a turn only when nothing can move without a person, or what blocks you is
deliberately protected from you. Risky or destructive actions still need confirmation.
</unattended>"""
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": msg}}))
PY
