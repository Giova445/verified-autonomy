---
# docs/plans/YYYY-MM-DD-<feature>.md
# Format adapted from obra/superpowers `writing-plans`.
spec: docs/specs/YYYY-MM-DD-<topic>-design.md    # required — no spec, no plan
ledger: .claude/work/<task-id>.progress.md
---

# <Feature> — Implementation Plan

**Goal:** one sentence.
**Architecture:** how the pieces fit; name the pure core and the I/O shell.
**Tech stack:**
**Constraints:** anything global that applies to every task below.

## File structure

- **Create** `path` — one responsibility, stated.
- **Modify** `path:line-range` — what changes and why.
- **Test** `path` — what it proves.

## Interfaces

Exact signatures produced and consumed across tasks. This is what lets tasks be dispatched
independently without the implementer guessing a contract.

```
compute_x(rows: list[Row]) -> Funnel        # produced by Task 1, consumed by Task 3
```

## Pre-flight

Run once before Task 1. Anything that must be confirmed against reality — a column name, an
API shape, a credential's existence — belongs here, not inside a task.

## Tasks

Each step 2–5 minutes. Each task independently dispatchable.

### Task 1 — <name>

- [ ] Write the failing test
- [ ] **Run it. Confirm it fails, and fails for an assertion reason** — not an import error
- [ ] Write the minimal code to pass
- [ ] Run it. Confirm it passes
- [ ] `./bin/verify fast`
- [ ] Commit

## No placeholders

"TBD", "add appropriate error handling", "similar to Task 2", "etc." are **plan failures**,
not shorthand. A task an implementer cannot execute without asking you a question is not
finished being planned.

## Definition of done

`./bin/verify done` exits 0, every acceptance criterion in the spec has a passing check, and
the evidence bundle is attached. Nothing else counts.
