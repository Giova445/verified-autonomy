# 14 — Verified Autonomy vs Superpowers

Comparison against **obra/superpowers v6.3.0** (released 2026-08-12). Primary sources: the
installed plugin on this machine, its `hooks/hooks.json`, all 14 `SKILL.md` files, and 34
plans/specs of real usage in this repo under `docs/superpowers/`.

---

## 1. The finding

**They share a thesis and differ entirely in enforcement layer.**

Superpowers' `verification-before-completion` states:

> **NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE**
> If you haven't run the verification command in this message, you cannot claim it passes.
> Skip any step = lying, not verifying

That is this architecture's [Stop gate](03-definition-of-done.md), expressed as discipline
rather than as an exit code.

**Superpowers ships exactly one hook: `SessionStart`.** Verified in `hooks/hooks.json`. Its
only job is to read `using-superpowers/SKILL.md` and inject it as `additionalContext`.
`SessionStart` cannot block. There is no `PreToolUse`, no `Stop`, no script anywhere in the
plugin that inspects or gates a tool call. Every bundled non-SKILL file is markdown
reference material.

In this architecture's terms ([02 §1](02-architecture.md)), **Superpowers is layer 1 —
persuasion — executed about as well as layer 1 can be, and deliberately so.** Its own
contributor docs concede the fragility: *"Without [the SessionStart bootstrap], the skills
are dead weight — present on disk but never invoked."*

## 2. Layer map

| Layer | Superpowers | This architecture |
|---|---|---|
| **1 — Persuasion** | **14 skills, pressure-tested, rationalization tables.** Far better than mine. | `AGENTS.md`, ≤10 imperatives |
| **2 — Enforcement** | None. One non-blocking hook. | `bin/verify`, `Stop` exit 2, `PreToolUse` deny, cheat scanner |
| **3 — Adjudication** | None shipped | CI re-run, branch protection, risk tiers, PR loop |

Neither covers all three. They compose cleanly, because they occupy different layers.

## 3. Where Superpowers is straightforwardly better

**Spec and plan artifacts.** My FSM names SPEC and PLAN as states and never says what they
produce. Superpowers specifies both: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
and `plans/YYYY-MM-DD-<feature>.md`, with a mandated header (Goal, Architecture, Tech Stack,
Spec pointer, Constraints) and a per-task template carrying exact file paths, an
`Interfaces:` block naming function signatures across tasks, and 2–5 minute checkbox steps.
A "No Placeholders" rule makes "TBD" or "add appropriate error handling" a **plan failure**.
This repo has 16 plans and 18 specs in that format. It works, and I should adopt it.

**Brainstorming as a hard gate before code.** A `<HARD-GATE>` blocks any implementation
action until the human approves an approach, with a one-way path classification
(spike / bounded / architectural). My architecture starts at INTAKE and assumes the task is
already well-formed.

**Skill authoring as a tested discipline.** `writing-skills` is TDD applied to process
docs: run a pressure scenario against a subagent *without* the skill (RED — record the exact
rationalizations), write the skill to close those specific rationalizations, re-run (GREEN).
The rationalization tables are the tested artifact, not padding.

**Cross-harness distribution.** Seven manifests ship in the plugin — `.claude-plugin`,
`.codex-plugin`, `.cursor-plugin`, `.devin-plugin`, `.hermes-plugin`, `.kimi-plugin`,
`gemini-extension.json`. My [doc 11](11-operationalization.md) solved cross-harness
*enforcement* with a CLI spine; Superpowers solved cross-harness *distribution*. Both are
needed and I only did one.

**Fix-loop escalation with model tiering.** `subagent-driven-development` runs a five-round
circuit breaker: rounds 1–3 resume the original implementer, rounds 4–5 dispatch a fresh one
on a more capable model. My retry budget just stops.

**Progress ledger.** `.superpowers/sdd/<plan>/progress.md`, git-ignored, because
*"conversation memory does not survive compaction"* — re-dispatching completed tasks was
their most expensive observed failure. Same conclusion as my "disk is the source of truth"
([02 §5](02-architecture.md)), arrived at independently from production pain.

## 4. Where this architecture is better

**Everything can be ignored in theirs.** That is the whole gap. `NO PRODUCTION CODE WITHOUT
A FAILING TEST FIRST` is capitalized prose in a markdown file. Nothing verifies the test was
written first; nothing counts fix attempts; nothing blocks a completion claim. Against
measured false-success rates of 45–48% on frontier models ([01 §1](01-evidence-base.md)),
instruction alone is a bet, not a control.

**Their circuit breakers are counted in prose.** "≥3 failed fixes ⇒ question the
architecture" and the five-round limit both rely on the model counting its own attempts.
Mine is a file on disk that the model cannot write to.

**No deny-list.** Nothing stops `rm -rf`, a force push, a self-merge, or an agent editing
its own skill files.

**No adjudication layer.** No CI re-verification, no risk tiering, no PR-loop convergence,
no evidence bundle. Their `verification-before-completion` does say *"Agent said success" →
"Verify independently"* — the right instinct, with no mechanism behind it.

**Their verifier is an LLM.** The `superpowers-evals` harness judges skill compliance with
an LLM verifier. Per [01 §1](01-evidence-base.md), LLM judges detect false success at
AUROC ≤0.65 while a cheap TF-IDF detector reaches 0.83–0.95. Deterministic scoring is a
methodological improvement available to them today.

## 5. Their eval methodology — worth stealing

They run genuine A/B evals, and publish results. From v6.2.0 release notes: a
prose-compression change was **reverted** because it *"measurably degraded test-first
behavior under pressure (control 8/10 → treatment 5/10)."*

That is a documentation change validated by measurement — rare, and exactly the
"[measure the harness, don't vibe it](08-adoption-playbook.md)" discipline I argued for
without implementing. Adopt the pressure-scenario method; replace the LLM judge with
deterministic scoring.

## 6. Honest critique of both

**Superpowers:** token overhead is real and task-size dependent — reported ~9% cheaper with
14% fewer tokens on non-trivial tasks, but *more* expensive on trivial ones, because
brainstorm→plan→TDD→verify applies uniformly. Issue #832 demonstrated a 69% line reduction
across all 14 skills (3,150 → 977 lines); maintainers ran their own compression campaign and
reverted one cut on eval evidence. So "the verbosity is load-bearing" is partly proven and
partly not. 278k stars, 24.9k forks, 94% PR rejection rate (their own figure).

**This architecture:** gates only catch cheats they enumerate, detectors decay across model
generations (AUROC 0.68–0.73 transfer), the RED proof cannot verify a test failed for the
*right* reason, and it says nothing about design quality or how to reach a good plan — which
is most of what Superpowers is about.

## 7. Recommended composition

Run both. They are not competitors.

| Concern | Use |
|---|---|
| Reaching a good plan | Superpowers `brainstorming` → `writing-plans` |
| Spec/plan artifact format | Superpowers, verbatim |
| Executing a plan with review | Superpowers `subagent-driven-development` |
| Debugging methodology | Superpowers `systematic-debugging` |
| **Whether "done" is true** | **`bin/verify` + Stop hook** |
| **Blocking destructive actions** | **`deny-dangerous.sh`** |
| **Detecting cheats in the diff** | **`scan-diff-cheats.sh`** |
| **Independent re-verification** | **CI running the same `verify`** |
| Cross-harness distribution | Superpowers' per-harness manifests |
| Cross-harness enforcement | This architecture's CLI spine |

The one-line version: **Superpowers makes the agent want to do the right thing. This makes
it unable to do otherwise.** Neither substitutes for the other, and the failure mode of
running only Superpowers is precisely the one the false-success literature measures.

## 8. Benchmark

Harness at [`experiment/benchmark/`](experiment/benchmark/README.md). Five adversarial
scenarios, four arms (bare / superpowers / gates / both), deterministic scoring.

**Status: harness built and validated; agent trials not yet run.** Scorers were validated
against synthetic outcomes — 17/17 discriminations correct across scenarios 01–04, plus the
LIA scenario validated in both directions. Two real scorer bugs were caught during that
validation and fixed: a pattern-matcher that flagged its own pristine baseline as a cheat
(would have made every arm score identically), and a `$400` fixture expanding as shell `$4`
under `set -u`. Both are the kind of defect that produces confident, meaningless numbers.

No cross-arm results are reported here because none have been produced.

### Pressure testing — the better experiment

Superpowers' `writing-skills` method, with their LLM verifier replaced by deterministic
scoring, at [`experiment/benchmark/pressure/`](experiment/benchmark/pressure/README.md).
It tests a **rule**, not a config: run the scenario with the rule present and absent, and
compare violation rates.

This matters more than the arm benchmark, because it is the only thing that justifies a
rule's token cost given `0.95^N` compliance decay ([10 §4](10-tools-and-rules.md)):

| Result | Action |
|---|---|
| RED without, GREEN with | Keep the rule |
| GREEN without, GREEN with | Delete — the model already complies |
| RED without, RED with | Delete, or **move it to layer 2** |

That last row is where the two architectures meet. Superpowers' own guidance already says
it: *"Mechanical constraints (if it's enforceable with regex/validation, automate it — save
documentation for judgment calls)."* A rule that fails pressure testing is not a weak rule;
it is a rule that belongs in `bin/verify`.

**First run: INCONCLUSIVE, and instructive.** The harness produced
*"DELETE — model already complies"* from four trials in which the agent never executed at
all (the CLI is unauthenticated for headless use here). A measurement tool that turns
"nothing happened" into a confident recommendation to delete a safety rule is this
architecture's own thesis, reproduced in its own instrumentation. Preflight and
degenerate-data guards added; the fabricated result deleted. See the run log.
