# <task-id> — progress ledger

Stolen from superpowers `subagent-driven-development`. It exists for one measured reason:

> conversation memory does not survive compaction

Re-dispatching already-completed tasks was their single most expensive observed failure.
This file is the source of truth for what is done; the context window is a cache.

Git-ignore it. Update it after **every** task, before starting the next.

## Tasks

| # | Task | State | Attempts | Evidence | Ruling |
|---|---|---|---|---|---|
| 1 | | pending / in-progress / done / blocked | 0 | `.claude/evidence/…` | |

## Rulings

When the plan is ambiguous but a reasonable path exists, **make the call, log it here, and
continue.** Do not stop. Only these force a stop:

1. Irreversible or destructive operations
2. Security-sensitive actions
3. Side effects outside the worktree
4. The plan is broken enough that every path forward is a guess

| Date | Ambiguity | Ruling | Rationale |
|---|---|---|---|

## Fix-loop escalation

Per failing task, not globally:

| Round | Action |
|---|---|
| 1–3 | Resume the same implementer |
| 4–5 | Fresh implementer, **one model tier up** |
| 6 | Stop. Blocked report. Human decision required. |
