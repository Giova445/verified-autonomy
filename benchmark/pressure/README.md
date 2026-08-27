# Pressure Testing — does this rule earn its tokens?

Stolen from Superpowers' `writing-skills`, which applies TDD to documentation:

> **Core principle:** If you didn't watch an agent fail without the skill, you don't know
> if the skill teaches the right thing.

| TDD | Rule testing |
|---|---|
| Test case | Pressure scenario |
| Production code | The rule text |
| RED | Agent violates the rule **without** it present (baseline) |
| GREEN | Agent complies **with** it present |
| Refactor | Close the loopholes the agent found |

**What we changed:** they judge compliance with an LLM verifier. Per
[01 §1](../../01-evidence-base.md) LLM judges detect false success at AUROC ≤0.65 while
cheap deterministic detectors reach 0.83–0.95. Scoring here is a script.

## Why this matters more than the arm benchmark

[10 §4](../../10-tools-and-rules.md) established that compliance decays as `0.95^N` and
adherence degrades past ~3,000 tokens of always-on context. That makes every rule a cost.
This harness answers the only question that justifies one:

> **Does the agent behave differently with this rule than without it?**

Three outcomes, and two of them mean delete the rule:

| Result | Meaning | Action |
|---|---|---|
| RED without, GREEN with | The rule works | **Keep it** |
| GREEN without, GREEN with | Model already does this | **Delete — pure token tax** |
| RED without, RED with | Rule is ignored under pressure | **Delete or move to layer 2** |

That third row is the important one. A rule that does not survive pressure is not a weak
rule, it is a **false sense of control** — and per Superpowers' own guidance, the correct
response is to stop documenting it and enforce it mechanically instead:

> Mechanical constraints (if it's enforceable with regex/validation, automate it — save
> documentation for judgment calls)

## Applied to this architecture's own rules

`AGENTS.md` currently carries 6 imperatives. Each is a hypothesis until pressure-tested.
Rules under test live in `rules/`, one file per rule, so a rule can be included or omitted
without touching anything else.

## Running

```bash
./run-pressure.sh <rule-name> <trials>
```

Dispatches `trials` runs with the rule and `trials` without, into disposable scratch repos,
scores each deterministically, and prints the delta. Requires a `claude` CLI on PATH.

## Run log

**2026-08-17 — first attempt, INCONCLUSIVE. No results.**

Two defects found, both in this harness rather than in any rule:

1. **Prompt delivery.** `claude -p --bare --allowedTools ... "prompt"` does not consume the
   positional prompt — the CLI answers *"Input must be provided either through stdin or as a
   prompt argument"*. Fixed: prompt is piped on stdin.
2. **The harness manufactured a verdict from zero data.** Every trial scored `NO_ATTEMPT`
   because the agent never ran, and the aggregator reported
   **"DELETE — model already complies without it; pure token tax."**

The second is the one worth recording. A harness that converts *"the agent never executed"*
into a confident recommendation to delete a safety rule is the same false-success failure
mode this architecture exists to prevent — reproduced inside the measurement tool. Had this
gone unchecked it would have produced a plausible, citable, entirely fabricated finding.

Two guards added:

- **Preflight.** Prove the CLI can complete a headless turn before spending trials; abort
  with exit 2 otherwise.
- **Degenerate-data refusal.** If every trial is `NO_ATTEMPT`/`SCORER_ERROR`, print
  `INCONCLUSIVE` and issue no verdict.

The poisoned results file was deleted rather than kept.

**Blocker:** the `claude` CLI in this environment is not authenticated for headless use
(`Not logged in · Please run /login`). Trials cannot run until that is resolved. The
scenario scorers are independently validated (17/17 synthetic discriminations) and do not
depend on this.
