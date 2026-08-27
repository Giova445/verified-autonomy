Run the project gate ladder and report honestly.

1. `./bin/verify preflight` — if the graph is unavailable, say so explicitly. You are at
   grep precision and every downstream claim is weaker.
2. `./bin/verify done`

Exit 0 is the ONLY thing that counts as done. Not "tests look right." Not "should work."

If red:
- Fix the CODE. Never weaken, skip, or delete a test. Never add `|| true`, raise a timeout,
  or add a retry.
- Never edit `bin/verify`, `.claude/gates.json`, `.claude/hooks/**`, `.github/workflows/**`.
- Max 3 attempts. On exhaustion STOP and report: failing gate + command + exit code, what
  you tried and why each attempt failed, the decision needing a human, a recommendation
  with trade-offs.

Report the exact command and exit code. Do not paraphrase a pass.
