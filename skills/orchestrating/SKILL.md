---
name: orchestrating
description: Drive a multi-task plan through the durable ledger, claim file scope before writing, and obey the fix-loop budget. Use when executing a written plan, running a fan-out, or resuming after a compaction.
---

# Orchestrating

**State machines, not orchestrators** — no script here can dispatch you. You ask what to do
next, do the work, report back. Disk is the truth; this conversation is a cache, and it will
be compacted away.

## The loop

0. `ledger init <id> --plan <plan.md>` — once per plan; parses its `- [ ]` checkboxes.
1. `ledger next <id>` prints `<n>\t<text>` — never pick a task yourself, and never trust
   your memory of one.
2. `worktree-guard claim <id> --scope '<glob>'` — **before the first write.** Exit 2 means
   another writer owns that path: take another task, do not edit it anyway.
3. `ledger start <id> <n>`, then do the work.
4. Gate it with `./bin/verify done`. Green is a file, not a feeling.
5. `ledger done <id> <n> --evidence .claude/evidence/latest.json`
6. `worktree-guard release <id>`, and loop.

## When it fails

```bash
./bin/escalate record <id> <n> --gate <name>     # log the attempt; computes the signature
./bin/escalate advise <id> <n>                   # ROUND= ACTION= MODEL= REASON=
./bin/ledger   fail   <id> <n> --reason '<what broke>'
```

Obey `ACTION` verbatim. `retry-same` means try again. `fresh-implementer` means hand off to a
new agent one model tier up, carrying the failure reasons — not the same context again. It
also stops early when the failure *signature* repeats: the same error twice means you are not
learning, and a fourth attempt will not beat the third.

**`ACTION=stop` (exit 1) is not advice.** Stop, and write a BLOCKED report: the failing gate,
its command and exit code, what you tried and why each attempt failed, the decision that
needs a human, and your recommendation.

## Reading the exits

| exit | meaning |
|---|---|
| 0 | proceed |
| 1 | `ledger next`: nothing to hand out. `escalate advise`: stop. |
| 2 | refused — bad request, missing evidence, or a scope collision |
| 3 | **state unreadable.** This does not mean "done". Stop and repair it by hand. |

`ledger next` exits 1 both when the plan is finished and when every remaining task is BLOCKED.
The code does not separate those: run `ledger status <id>` before reporting completion.

## Never

- Never `ledger done` without an artifact you produced. It refuses a missing or empty file.
- Never delete or reinitialize a ledger to get past exit 3: that erases the record of
  finished work, the exact failure this tool exists to prevent.
- Never write outside your claimed scope: confirm with `worktree-guard check <id> <path>`.
