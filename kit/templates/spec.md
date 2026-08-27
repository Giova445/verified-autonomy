---
# docs/specs/YYYY-MM-DD-<topic>-design.md
# Format adapted from obra/superpowers `brainstorming` + `writing-plans`.
# Written BEFORE any code. Requires explicit human approval before a plan is written.
status: draft            # draft | approved | superseded
approved_by:             # required before PLAN state — no approval, no plan
date:
---

# <Topic> — Design

## Problem

What is actually broken or missing, in the user's terms. Not the solution.

## Path classification

`spike` | `bounded` | `architectural` — and why.

> One-way: hidden complexity discovered mid-task **upgrades** the path. Nothing downgrades.

## Approach

The chosen design, and the two or three alternatives rejected with the reason each was
rejected. A spec with no rejected alternatives was not a decision.

## Blast radius

Filled from the graph ([09](../09-graph-engineering.md)), not from reading:

```
./bin/verify blast <primary-symbol>
```

- Symbols touched:
- Direct callers:
- Cross-boundary or cross-language edges:
- DI/reflection risk (callers the graph cannot see):

## Acceptance criteria

Each one **observable and falsifiable**. Write the failing check next to it.

| # | Criterion | How it is proven false |
|---|---|---|
| AC-1 | | |

Generic closure criteria ("demo recorded", "subtasks closed") are necessary, never
sufficient. They do not belong here.

## Out of scope

Explicit. This is what stops scope creep at review time.

## Open questions

Anything unresolved. **An open question blocks the plan** — resolve by reading code or
asking, never by inference.
