---
# intent/<YYYY-MM-DD>-<slug>/spec.md
# Stage 2 of the chain. Requires an approved intent.md in the same directory.
#
# NOTE ON THE OTHER SPEC TEMPLATE. templates/spec.md at the repo root is a different,
# longer document with a different field set (path classification, blast radius,
# acceptance-criteria table, out of scope). It is the one skills/brainstorming names, and
# it is not superseded by this file. See intent/README.md, "Two spec templates", for which
# to use and why both exist.
intent: ./intent.md    # required — no approved intent, no spec
status: draft          # draft | approved | superseded
approved_by:           # a human. No approval, no plan.
date:
---

# <Title> — Spec

## Requirements

Numbered, each one independently checkable. A requirement nobody can falsify is a wish.

| # | Requirement | How it is proven false |
|---|---|---|
| R1 | | |
| R2 | | |

Trace every requirement back to a line in `intent.md`. A requirement with no ancestor in
the intent is scope that arrived without approval — either amend the intent or drop it.

## Design

The approach chosen, and the alternatives rejected with the reason each was rejected. A
design with no rejected alternative did not involve a decision, and there is nothing here
for a reviewer to disagree with.

State where the change lives relative to the enforcement layers
([docs/02-architecture.md](../../docs/02-architecture.md) §1). Layer 1 shapes behaviour and
can be ignored; layer 2 and 3 cannot. If the design lands in layer 1, say so plainly here
rather than letting the plan's proof statements imply otherwise.

## Policy validation

Check the design against the policy that already exists, and name the file you checked it
against. In this repo:

| Policy source | Question | Answer |
|---|---|---|
| [kit/governance.yaml](../../kit/governance.yaml) `risk_tiers` | Which tier do the changed paths fall in? | |
| [kit/governance.yaml](../../kit/governance.yaml) `escalate_always` | Does this hit an always-escalate class? | |
| [.claude/settings.json](../../.claude/settings.json) `denyWrite` | Does this need a write the sandbox denies? | |
| [docs/07-safety-and-autonomy-levels.md](../../docs/07-safety-and-autonomy-levels.md) §1 | What autonomy level does this assume? | |

Two honest notes about that table, so nobody reads it as more than it is:

- `kit/governance.yaml` is **read by no script in this repo** (verified: `grep -rl
  governance bin/ kit/bin/ hooks/ kit/hooks/` returns nothing). Filling this section is a
  human checking a written policy, not a machine enforcing one.
- The `denyWrite` row is different — that one is enforced by the sandbox, so a "yes" there
  predicts a real refusal at Stage 4 rather than a reviewer's objection.

## Flagged concerns

Anything you want a reviewer to look at specifically, including the parts you are least
sure of. This section exists so that "I had a bad feeling about the probe timeout" is on
the record before the incident rather than after it.

| # | Concern | Severity | Disposition |
|---|---|---|---|
| C1 | | high / med / low | accepted / mitigated / open |

An **open** concern at approval time is allowed. An *unwritten* one is the failure this
section is for.
