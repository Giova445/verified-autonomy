---
name: pressure-testing
description: Test whether a rule or instruction actually changes agent behavior before keeping it. Use when adding, auditing, or deleting rules in AGENTS.md, CLAUDE.md, or a skill.
---

# Pressure Testing

Adapted from obra/superpowers `writing-skills`, which applies TDD to documentation:

> If you didn't watch an agent fail without the skill, you don't know if the skill teaches
> the right thing.

We replace their LLM verifier with deterministic scoring: LLM judges detect false success at
AUROC ≤0.65; cheap deterministic detectors reach 0.83–0.95.

## Why any rule needs this

Compliance decays roughly as `0.95^N` across N instructions, and adherence degrades past
~3,000 tokens of always-on context. Every rule taxes every other rule. So a rule must earn
its tokens.

## Method

1. Build a scenario that **tempts** violating the rule — the cheat must be the path of least
   resistance.
2. Run it **without** the rule. Record what the agent does (RED).
3. Write or keep the rule.
4. Run it **with** the rule (GREEN).
5. Score deterministically — a script inspecting final state, never a judge.

## Reading the result

| Without | With | Verdict |
|---|---|---|
| violates | complies | **Keep the rule** |
| complies | complies | **Delete** — the model already does this; pure token tax |
| violates | violates | **Delete, or move it to layer 2** |

That last row is the important one. A rule that does not survive pressure is not weak — it
is a false sense of control. Superpowers' own guidance agrees:

> Mechanical constraints (if it's enforceable with regex/validation, automate it — save
> documentation for judgment calls)

If it can be a hook or a gate, make it one and delete the prose.

## Guard against your own harness

Verify the agent actually executed before believing any verdict. A harness that scores
"agent never ran" as "model already complies" will confidently tell you to delete a safety
rule. Require a preflight that proves the runner can complete a turn, and refuse to issue a
verdict when every trial is degenerate.
