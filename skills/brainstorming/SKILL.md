---
name: brainstorming
description: Use before ANY creative work — new features, components, behavior changes, refactors. Forces intent and approach to be settled and approved before implementation starts.
---

# Brainstorming

**Nothing gets built before it is understood.** Jumping to code is the most expensive
failure mode available, because everything downstream inherits the mistake.

## Classify the path, out loud

| Path | When | Artifact |
|---|---|---|
| **spike** | A feasibility question. "Can this even work?" | None kept. Throw it away. |
| **bounded** | A scoped change to code that already exists | Short in-chat design |
| **architectural** | New subsystem, new boundary, new dependency | Written spec file |

Say which one you chose and why, so your human can override it.

**One-way.** Hidden complexity discovered mid-task *upgrades* the path. Nothing downgrades.
Discovering that a "bounded" change touches four modules means you are now architectural.

## Hard gate

> Do not write code, scaffold, or take any implementation action until you have stated what
> you intend to do and your human partner has approved it.

For the architectural path, write `docs/specs/YYYY-MM-DD-<topic>-design.md` using
`templates/spec.md`. Then **stop and get sign-off.** A spec nobody approved is a guess with
formatting.

## What a real spec contains

- The problem in the user's terms, not the solution.
- The chosen approach **and the alternatives you rejected, with why.** A spec with no
  rejected alternatives did not make a decision.
- Blast radius from the graph (`./bin/verify blast <symbol>`), not from reading.
- Acceptance criteria that are **observable and falsifiable** — each with the check that
  would prove it false.
- Explicit out-of-scope. This is what stops scope creep at review time.

## Mechanically backed

Open questions block the plan. `./bin/verify preflight` fails while
`.claude/evidence/assumptions.jsonl` holds an entry with `"status": "open"` — so
"I'll figure that out later" is a gate failure, not a note to self.
