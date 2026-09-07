---
# intent/<YYYY-MM-DD>-<slug>/intent.md
# Stage 1 of the chain. Written BEFORE the spec, by the person who wants the change.
# The five headings below are the field set. intent/check-chain.sh asserts all five
# are present; it cannot assert they are answered honestly.
status: draft          # draft | approved | superseded
proposed_by:           # who wants this
approved_by:           # a human other than the proposer. No approval, no spec.
date:
---

# <Title> — Intent

## Problem

What is broken or missing, stated as an observation rather than a solution. If you cannot
name the observation — a failing run, a gate row, an incident, a user's sentence — you do
not have an intent yet, you have a preference.

Cite the evidence. A commit SHA, a gate id, a log line, a measurement. "It feels slow" is
admissible only with the number next to it.

## Proposed outcome

What is true after this lands, phrased so someone else could tell whether it happened.

Say what does **not** change too. In this repo the most common form of that sentence is
"the harness still behaves the same way; the change makes an existing failure visible from
outside it" — a mitigation is not a fix, and the intent is where that distinction gets
made rather than quietly lost by Stage 3.

## Affected users and systems

| Affected | How | Who owns it |
|---|---|---|
| | | |

Include the systems that only *read* the thing you are changing. A file nobody writes but
CI parses is affected.

## Constraints

Everything that is fixed before the design starts, and why. Budgets, deadlines, interfaces
you may not break, environments you cannot reach, credentials you do not have.

A constraint that turns out to be false is a finding, not an inconvenience: record the
correction here rather than silently designing past it.

## Open questions

| # | Question | Blocking? | Resolved by |
|---|---|---|---|
| Q1 | | yes / no | |

**A blocking open question stops the spec.** Resolve it by reading code, running something,
or asking a human — never by inference. Answering your own question from a plausible guess
is the step that makes every downstream artifact wrong in the same direction.
