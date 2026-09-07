---
# intent/<YYYY-MM-DD>-<slug>/plan.md
# Stage 3 of the chain. Requires an approved spec.md in the same directory.
#
# NOTE ON THE OTHER PLAN TEMPLATE. templates/plan.md at the repo root is a different,
# longer document (interfaces, pre-flight, per-task TDD checklists) and is the one
# skills/writing-plans names. See intent/README.md, "Two spec templates", which covers
# both pairs.
#
# The "Work order" section below is MACHINE-READ. `bin/ledger init <id> --plan <this file>`
# parses "- [ ]" checkboxes into numbered tasks and refuses a plan containing none.
spec: ./spec.md        # required — no approved spec, no plan
status: draft          # draft | approved | superseded
approved_by:           # a human. No approval, no branch.
date:
---

# <Title> — Plan

**Goal:** one sentence, taken from the spec's proposed outcome.

## Files changing

Declared before the first write, because this is also the ownership claim: `bin/worktree-guard
claim <id> --scope '<glob>'` refuses a path another writer already holds.

| Path | Create / Modify / Delete | Why |
|---|---|---|
| | | |

Name the files you will **not** touch that a reader would expect you to, and why. In a
repo with concurrent writers that sentence is what stops two agents editing one manifest.

## Work order

Each task independently dispatchable, each 2–5 minutes, each a `- [ ]` checkbox because
that is the syntax `bin/ledger` parses. Ordering is a dependency claim: task N may assume
tasks 1..N-1 landed and nothing else.

- [ ] Task 1 — <verb the implementer can execute without asking a question>
- [ ] Task 2 —
- [ ] Task 3 —

"TBD", "handle errors appropriately", "similar to task 2", and "etc." are plan defects, not
shorthand. `bin/ledger done` refuses a task with no evidence artifact, so a task that
produces nothing inspectable cannot be closed.

## Tests needed

One row per behaviour, not one row per file. The control column is the load-bearing one:
a test that passes on a clean tree proves nothing unless something makes it fail.

| # | What it proves | Positive control — what makes it fail |
|---|---|---|
| T1 | | |

If a check's expected value is computed from the thing it checks, say so here and fix it.
Deleting a rule must fail the check; when the expectation is derived from the rule set,
removing a rule removes its expectation too and the suite stays green having tested less.

## Risks

| # | Risk | Likelihood | If it happens | Detected by |
|---|---|---|---|---|
| K1 | | | | |

Include the risk that this plan is wrong. The mitigation for that one is usually "the
work order is ordered so the cheapest disconfirming task runs first".

## Proof statements

The claims this work will be allowed to make when it is finished, each bound to a command
someone else can run and an expected exit code. Write them **now**, before the work — a
proof statement composed after the result is a description of what happened, not a test of
it.

| # | Claim | Command | Expected |
|---|---|---|---|
| P1 | | | exit 0 |

Rules:

- A claim with no command is not a proof statement. Delete it or find the command.
- "The suite passes" is not a claim; name the check and what its failure would have meant.
- If a command cannot exist — the thing is unreachable from inside this repo, needs
  credentials nobody has, or is a judgment — write **NOT PROVABLE HERE** and the reason.
  That row is the honest output. A stub command that always exits 0 is not.
