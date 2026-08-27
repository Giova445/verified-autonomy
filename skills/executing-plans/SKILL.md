---
name: executing-plans
description: Use when implementing a written plan. Keeps progress on disk so the run survives compaction, and enforces per-task verification.
---

# Executing Plans

## Progress lives on disk, not in context

Maintain `.claude/work/<task-id>.progress.md` from `templates/progress-ledger.md`, updated
after **every** task, before starting the next.

This is not bookkeeping. **Conversation memory does not survive compaction**, and
re-dispatching already-completed tasks is the most expensive failure in long runs. The
ledger is the source of truth for what is done; the context window is a cache.

## Per task

1. Write the failing test.
2. **Run it. Confirm it fails for an assertion reason** — not an import error. An import
   error proves the file does not parse, not that the test exercises anything.
3. Write the minimal code to pass.
4. Run it. Confirm it passes.
5. `./bin/verify fast`.
6. Commit. Update the ledger.

## Rulings, not stalls

When the plan is ambiguous but a reasonable path exists: **make the call, log it in the
ledger under Rulings, and continue.** Stopping on every ambiguity makes autonomy useless.

Only four things force a stop:

1. Irreversible or destructive operations
2. Security-sensitive actions
3. Side effects outside the worktree
4. The plan is broken enough that every path forward is a guess

## Fix-loop escalation

Per failing task, not globally:

| Round | Action |
|---|---|
| 1–3 | Resume the same implementer |
| 4–5 | Fresh implementer, **one model tier up** |
| 6 | Stop. Blocked report. Human decision. |

Repeating the same fix shape is thrash, not persistence. If the diff looks the same twice
and the gate did not flip, stop at once — do not spend the remaining budget.
