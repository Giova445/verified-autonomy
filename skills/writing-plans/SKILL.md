---
name: writing-plans
description: Use after a spec is approved and before implementation. Turns a design into tasks small enough to dispatch independently and verify individually.
---

# Writing Plans

A plan is not a summary of the spec. It is the thing an implementer executes **without
asking you a question.**

Write to `docs/plans/YYYY-MM-DD-<feature>.md` using `templates/plan.md`.

## The test of a finished plan

> Could an enthusiastic junior engineer with no project context follow this exactly and
> produce the right result?

If they would have to ask you anything, the plan is not finished.

## Required structure

- **Header:** Goal (one sentence), Architecture, Tech stack, Spec pointer, Constraints.
- **File structure:** every `Create` / `Modify path:line-range` / `Test`, each with the one
  responsibility it carries.
- **Interfaces:** exact signatures produced and consumed *across* tasks. This is what makes
  tasks independently dispatchable — without it every implementer invents its own contract.
- **Pre-flight:** anything that must be confirmed against reality before Task 1 — a column
  name, an API shape, a credential's existence.
- **Tasks:** 2–5 minutes each, as checkboxes, each following RED → GREEN → verify → commit.

## No placeholders

"TBD", "add appropriate error handling", "similar to Task 2", "etc." are **plan failures**,
not shorthand. Each one is a decision you deferred onto someone with less context than you.

## Definition of done, per task

`./bin/verify fast` after each task. `./bin/verify done` before the plan is closed. Exit 0
or it is not done.
