---
name: requesting-review
description: Use after gates are green and before opening a PR. Dispatches adversarial review that can only add findings, never clear a gate.
---

# Requesting Review

Run this **after** `./bin/verify done` exits 0. A reviewer looking at red gates is wasting
its context on something the machine already knows.

## Dispatch clean

The reviewer gets:
- The diff range.
- The evidence bundle (`.claude/evidence/latest.json`).
- The acceptance criteria from the spec.

The reviewer does **not** get your session history. Your reasoning contaminates the review —
you will have already explained away the thing they should catch.

Use a **different model family** than the implementer where you can. Same-lineage judges
share blind spots and exhibit self-enhancement bias, and self-verification measurably
performs *below* generation accuracy.

## The reviewer's mandate

Refute, don't ratify. Default to "not proven" when uncertain. A review that finds nothing is
a failed review unless it can show specifically what was checked and why each risk is absent.

Findings need a concrete failing input. A specific counterexample beats a general concern.

## Hard rule

**A reviewer cannot clear a failing gate.** Deterministic results are facts; model judgment
only ever *adds* findings. If a review says "this is fine" and a gate is red, the gate wins.

## Receiving feedback

- Verify each point against the actual code before implementing it. Reviewers are wrong
  sometimes, including automated ones.
- Ambiguous feedback gets **one** clarifying question, then you wait.
- No performative agreement. "You're absolutely right!" before checking is not a response,
  it is a reflex.
