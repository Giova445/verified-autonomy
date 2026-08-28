# 04 — The Gate Ladder

Ordered cheapest-and-most-deterministic first, so a doomed change dies before it burns
the expensive stages. Every gate is a command with an exit code. No gate is a judgment.

---

## 1. The ladder

| # | Gate | When | Blocking | Budget | Rationale |
|---|---|---|---|---|---|
| **0** | Pre-write: assumption register clean, acceptance criteria exist, **graph index healthy** | Before any edit | Hard | <1s | Stops guessing before it becomes code |
| **1** | Format + lint + typecheck | Every edit | Hard | <30s | Catches hallucinated APIs and nullability gaps cheapest |
| **2** | Unit tests (**graph-selected from the impact set**) | Every edit | Hard | <60s | 50–80% less CI time than running everything — see [09 §3.2](09-graph-engineering.md). Must fail *open* on renames, config changes, or a stale index |
| **3** | RED proof | Before implementation edits unlock | Hard | <10s | Proves the test can fail (02 §3) |
| **4** | Full unit + integration suite | Before any "done" claim | Hard | 2–5 min | Regression surface |
| **4a** | **Test-existence delta** (`bin/test-delta`) | Before any "done" claim | Hard | <2s | Production code that arrives with no committed tests is a failed run. Needs only git, so it works where diff coverage is not wired up yet — see §2.1 |
| **5** | Diff coverage | Before "done" | Hard | <10s | Coverage of *the agent's lines*, not the repo's |
| **6** | Cheat-flag scan | Before "done" | Hard | <5s | The catalog in 03 §3 |
| **7** | Architecture fitness + complexity ratchet | Before "done" | Hard | <30s | Dependency Rule, budgets (06) |
| **8** | Security: secrets, SAST, SCA, dependency existence | Before PR | Hard | 1–3 min | Slopsquatting and leaked-credential defense |
| **9** | Mutation (diff-scoped) | Before PR | Soft-block, logged override | <2 min | The anti-fake-test layer |
| **10** | E2E / contract | Before merge | Hard | 3–15 min sharded | Real-stack truth |
| **11** | Performance / benchmark | Pre-merge-to-main or nightly | Soft-block, human sign-off | Variable | Too noisy to gate per-commit |

Gates 1–7 run locally under the `Stop` hook. Gates 8–11 run in CI. **CI re-runs 1–7
too** — the agent's local green is a claim, CI's green is the fact.

**Scope every gate to the affected set, not the repo.** Compute affected packages once
(`nx affected`, `turbo --filter=...[base]`, `bazel rdeps`) and run all gates against that
set. This is what keeps the ladder affordable as a repo grows: gate cost tracks the size of
the change, not the size of the codebase ([09 §3.3](09-graph-engineering.md)).

## 2. Thresholds, and why these numbers

| Metric | Threshold | Justification |
|---|---|---|
| Diff coverage | **no threshold; report the number** | **The 80% figure previously stated here was unsupported and has been withdrawn — see 2.2.** Google's own mutation-testing researchers (ICSE 2021) write that coverage thresholds are "inherently arbitrary," and across 1,502 high-priority Google bugs *every* bug-introducing change was already covered by existing tests. Diff-scoping is still right — an agent's blast radius is the diff — but scope the measurement, do not threshold it. Exclude generated code from the denominator. |
| Mutation score (diff-scoped) | **no threshold; ≤1 mutant per line; dismissible** | **The ≥75% threshold previously stated here was unsupported and has been withdrawn — see 2.2.** Google runs mutation testing across >24,000 developers with no score threshold at all: findings surface in review with a "Not useful" button. Unfiltered mutation testing was rated **85% unproductive** by developers; arid-node suppression raised the productive ratio to 89%. Median 2 live mutants per changelist. |
| Cyclomatic complexity | warn >10, fail >20 | ESLint default is 20; MS CA1502 default is 25 |
| Cognitive complexity | fail >15/function | SonarQube default; better predictor of review pain than cyclomatic |
| Function length | 50 soft / 80 hard | Martin argues far shorter; see 06 §2 for why we don't enforce his number |
| File length | 400 typical / 800 hard | Matches the existing project convention |
| Nesting depth | ≤4 | |
| Flaky rate | <1–2% healthy, >5% systemic | Google: ~1 in 7 tests shows flakiness at some point |
| Quarantine dwell | ≤30 days, owner assigned | Growing quarantine = decay signal |
| Perf regression | fail >10–15% vs rolling baseline | Absolute thresholds drift with runner hardware |

### 2.1 Why a crude test-existence gate sits below diff coverage

Gate 5 subsumes gate 4a on paper: 80% coverage of changed lines is impossible without tests.
Gate 4a exists because of what happened when the ladder was actually run.

In a head-to-head benchmark, one arm implemented a complete dependency-resolving scheduler
and its gate reported `ALL GATES GREEN`. The gate was telling the truth. Its configured
suite — four tests the arm had been handed at the start — passed. The arm had verified its
own work carefully, by hand, in scratch files it never committed. It wrote zero durable
tests. The competing arm wrote sixteen.

Diff coverage was listed in this document at the time. It was not in that repo's
`gates.json`, because wiring it needs a coverage runner, a report format, a base ref, and an
exclusion list — four chances to defer it to later. A gate that is documented but not
configured enforces nothing, and the ladder happily reported green without it.

So gate 4a is deliberately the crudest possible version of the question, with one dependency
(git) and no configuration. It cannot tell a good test from a bad one; diff coverage and
mutation testing above it exist for that. What it can do is make *zero tests* an unambiguous
red — the failure mode that actually occurred — and it does so in every repo, on day one,
before anyone has budget to configure anything else.

> **Read 2.3 before adopting gate 4a.** A later literature audit falsified the reasoning in
> this section — requiring tests does not improve correctness on current models, and the
> gate has been demoted out of the blocking tier as a result. The section is kept as written
> because the *observation* (a green receipt over a suite that tested nothing) was real; the
> *inference* drawn from it was not.

The general lesson is worth more than the gate: **the gap between the documented ladder and
the configured ladder is where fabricated green lives.** Audit `gates.json` against this
table, per repo. A rung described here and absent there is not a rung.

### 2.2 Claims withdrawn after a literature audit (2026-08-28)

A structured audit of the current literature contradicted several numbers this document
asserted. They are withdrawn here rather than quietly edited, because a silently corrected
threshold is indistinguishable from one that was never wrong.

**Withdrawn: "diff coverage ≥80%, 2026 industry baseline."** No primary source establishes
80%. Google's own mutation-testing researchers state in ICSE 2021 that coverage thresholds
are "inherently arbitrary," and — the datum that should end the argument — across **1,502
high-priority Google bug fixes, every single bug-introducing change was already covered by
the existing tests.** Coverage was green on 100% of the real bugs studied. Diff-scoping the
*measurement* remains correct; thresholding it was cargo cult.

**Withdrawn: "mutation score ≥75%, ratchet upward."** Google runs mutation testing across
>24,000 developers and >1,000 projects with **no score threshold anywhere**. Findings appear
in code review with "Please Fix" / "Not useful" links and can be dismissed. Unfiltered
mutation testing was rated **85% unproductive** by developers; suppression heuristics raised
the productive ratio from 15% to 89%. Diff-scoping is mandatory (median 2 live mutants per
changelist, 99th percentile 43), and one mutant per line is sufficient because >90% of lines
have a uniform mutant fate. The gate is well-evidenced. The threshold was invented.

**Withdrawn: compliance decays as `0.95^N`, with a ~3,000-token always-on budget.** The only
controlled factorial test of exactly these practitioner beliefs — **1,650 Claude Code CLI
sessions, 16,050 function-level observations, on Sonnet 4.6** — manipulated instruction-file
size (25→500 lines), rule position, single-vs-split files, and the presence of contradictory
instructions in adjacent files. **None of the four produced a detectable effect**, and size
and conflict carry *affirmative* Bayesian evidence for the null (BF₁₀ 0.02–0.22 across every
prior tested). The `0.95^N` figure was an illustration presented as a measurement.

The instruction-count literature that does exist does not rescue it. IFScale's "150–200
instruction headroom" is **keyword inclusion in a business report**, on mid-2025 models, with
**non-conflicting** instructions. Where instructions can conflict — which is exactly what a
rule file is — follow rate collapses from ~96% to as low as **20% by twenty instructions**.

What replaces it, from the same study: the real effect is **within-session**, not rule-count.
Each additional function generated in a session carries roughly **5.6% lower odds of
compliance**. Shorter sessions and re-anchoring beat rewriting the rule file. And
acknowledgement is not compliance: **28% of functions where the agent explicitly restated the
rule still violated it**, while 63% of unacknowledged functions complied silently.

### 2.3 The evidence against gate 4a, including against my own reasoning for building it

Gate 4a (`bin/test-delta`) was added in this repo after a head-to-head benchmark in which one
arm implemented a complete dependency-resolving scheduler, wrote **zero** durable tests, and
received `ALL GATES GREEN`. The implied reasoning was: missing tests indicate worse work, so
requiring tests will produce better work.

**That reasoning is falsified on current models.** arXiv:2602.07900 (Apr 2026) ran SWE-bench
Verified across Claude Opus 4.5, Gemini 3 Pro, GPT-5.2, Kimi K2 Thinking, MiniMax M2 and
DeepSeek v3.2 with testing optional:

| model | writes tests | resolves |
|---|---|---|
| Claude Opus 4.5 | **83.0%** of tasks | 74.4% |
| GPT-5.2 | **0.6%** of tasks | 71.8% |

A **138×** difference in test-writing produced a **2.6 pp** difference in resolution. Within a
single model, resolved and unresolved tasks show *similar* test-writing frequencies. Forcing
it changes nothing: an encourage-prompt on GPT-5.2 produced a net change of **0** successes; a
discourage-prompt flipped 68.4% of Kimi K2-T's tasks away from testing for a net of **−13**.
**All McNemar tests p > 0.05.**

Our own duel is *consistent with this*, not with the rationale: the arm that wrote zero tests
scored **20/20** on the held-out suite, identical to the arm that wrote sixteen.

**There is also a specific reason to distrust this gate's metric.** `test-delta` counts
assertions, so an agent under it maximises assertion count. Agent-written tests already skew
that way: across 179,732 agent test files vs 24,941 human ones (arXiv:2607.12068, Jul 2026),
agents produce weak assertions at 14.30% vs 11.92% for humans, and **unknown or non-standard
assertion methods at 10.93% vs 1.46% — roughly 8×**. Agents invent and misspell assertion
APIs. A gate that rewards assertion count points directly at the behaviour that is already
over-represented.

**What this does and does not retire.**

- **Retired:** any claim that requiring tests improves correctness. It does not, on current
  models, and prompting for it does nothing.
- **Not retired, but unmeasured:** the claim that committed tests protect *future* changes.
  That is a different question about regression insurance over time, and the study above
  measures single-task resolution, not maintenance. Nobody has measured it. It is a bet, and
  it should be labelled as one.
- **Consequence:** gate 4a is **demoted out of the blocking `full` tier in the shipped
  template.** It remains available and an operator can promote it deliberately, with the
  reasoning above in view. It must not be described as a correctness gate.

### 2.4 What the evidence does support, ranked

1. **Isolate the verifier from the agent's execution environment.** A Berkeley RDI red-team
   scored **100% on SWE-bench Verified and 100% on SWE-bench Pro without solving anything**,
   via a `conftest.py` pytest hook and a parser overwrite inside the container; 100% on
   Terminal-Bench via dependency-chain trojans. *Isolation of the verifier, not hiddenness of
   the tests, is what makes a gate a gate.*
2. **Hold out tests the agent never sees, and treat the visible-vs-held-out gap as the
   signal.** Every frontier agent saturates visible suites (~95%+) while held-out diverges by
   **43–48 pp**; one run produced a 2,900-line hash table memorising test inputs for
   **97% visible / 0% held-out**. The gap grows ~28 pp per tenfold increase in code size.
3. **Diff-scoped mutation testing, ≤1 mutant per line, dismissible, no threshold.** The only
   gate with a bug-coupling number behind it: **70%** of 1,502 high-priority Google bugs would
   have had a live, fault-coupled mutant surfaced on the bug-introducing change. Note the
   caveat the citations usually drop — that is a *counterfactual coupling rate*, not a measured
   prevention rate; mutation testing was actually enabled on only 10.8% of those changes.
4. **Reduce task ambiguity.** Hack rates run **10–20× higher on ambiguous problems** than
   unambiguous ones. The cheapest intervention with the largest measured lever.
5. **Enforce completion claims at the harness, not by prompting.** Harness enforcement moved
   security-practice skipping from 89/97/82% down to **12%**. Asking a model not to hack moved
   it 80% → 70%. Self-reflection is worse: in 20,574 real sessions only **2.99%** of
   resolutions were self-corrections and **91.49%** required explicit human pushback.
6. **Keep any lint/static-analysis gate under ~10% effective false positives.** Above that,
   developers route around it regardless of what it catches — which is precisely why
   `benchmark/gates/bench.sh` measures the false-positive column at all.

### 2.5 Gates aimed at the wrong behaviour

**Blocking test-file edits targets the rarest failure.** At inference time, direct test-file
editing runs **0–2.1%** across Codex/GPT-5, Claude Code/Sonnet 4 and Gemini CLI. **Special-casing
the implementation to known inputs is 10–30× more common — 20.7% for Claude Code.** The gate
everyone builds first is aimed at the behaviour that almost never happens.

**And the widely-quoted hacking rates do not apply to a deployed agent.** METR measured
**30.4%** on RE-Bench — score-maximisation tasks with a visible numeric objective — and
**0.7%** on ordinary SWE tasks in the *same report, on the same models*. Anthropic's
"90% hacking / 12% sabotage" figures come from a **pretrained base model deliberately taught
specific hacks and then RL'd exclusively on environments known to be vulnerable to them**; the
same paper reports **production Claude Sonnet 3.7 and Sonnet 4 at exactly 0%** on every one of
those evaluations. Reward hacking at the rates usually cited is a *training-time* artifact.
Designing inference-time gates around it is designing for the wrong threat.

### The ratchet pattern

Essential for adopting gates on an existing codebase. Record current violations as a
baseline; **CI fails only if the count increases**; ratchet the baseline down whenever a
PR happens to improve it.

```bash
# fail only on regression, not on inherited debt
eslint . --max-warnings "$(cat .quality-baseline/eslint)"
```

This lets you turn on strict gates on day one without being blocked by debt the agent
didn't create, while guaranteeing monotonic improvement.

## 3. Commands by ecosystem

Fill these into `.claude/gates.json`. These are defaults — replace with your project's real targets.

### TypeScript / JavaScript

| Gate | Command | Threshold |
|---|---|---|
| Typecheck | `tsc --noEmit` | 0 errors. Enable `strict` + `noUncheckedIndexedAccess` |
| Lint | `eslint . --max-warnings 0` | + `eslint-plugin-jest` `expect-expect`, `prefer-expect-assertions` |
| Unit | `vitest run --coverage` (or `jest`) | — |
| Diff coverage | `diff-cover coverage/cobertura-coverage.xml --compare-branch=origin/main` | report only — see 2.2 |
| Mutation | `stryker run --incremental` | report only, dismissible — see 2.2 |
| Architecture | `depcruise src --config .dependency-cruiser.cjs` | 0 violations |
| Dead code | `knip` | 0 new |
| Duplication | `jscpd src --threshold 5` | ratchet |
| E2E | `playwright test --shard=$SHARD` | 0 fails, `trace: 'on-first-retry'` |
| Security | `gitleaks git --staged --redact` · `osv-scanner -r .` | 0 findings / 0 high+ |

### Python

| Gate | Command | Threshold |
|---|---|---|
| Lint + format | `ruff check . && ruff format --check .` | 0 |
| Typecheck | `mypy --strict .` (or `pyright`) | 0 errors |
| Unit | `pytest -m "not integration" -q` | — |
| Diff coverage | `diff-cover coverage.xml --compare-branch=origin/main` | report only — see 2.2 |
| Mutation | `mutmut run --paths-to-mutate=src/<changed>` | report only, dismissible — see 2.2 |
| Architecture | `lint-imports` (Import Linter) or `pytest-archon` | 0 violations |
| Complexity | `radon cc --min C src` | grade B target |
| Dead code | `vulture src` | 0 new |
| Security | `gitleaks` · `pip-audit --strict` · `semgrep --config auto` | 0 findings |

### Go

| Gate | Command | Threshold |
|---|---|---|
| Vet + lint | `go vet ./... && golangci-lint run` | 0 |
| Unit + race | `go test ./... -race -cover` | race-clean; coverage reported, not thresholded |
| Architecture | `go-arch-lint check` | 0 violations |
| Mutation | `gremlins unleash` | ≥60–70% (ecosystem less mature) |
| Benchmark | `go test -bench=. -benchtime=3x` | <10–15% regression |

### Rust

| Gate | Command | Threshold |
|---|---|---|
| Lint | `cargo clippy -- -D warnings` | 0 |
| Unit | `cargo test` | coverage reported, not thresholded |
| Mutation | `cargo mutants --in-diff` | report only, dismissible — see 2.2 |
| Supply chain | `cargo deny check` | licenses + advisories + bans clean |

### JVM

| Gate | Command | Threshold |
|---|---|---|
| Static | `mvn checkstyle:check spotbugs:check` | 0 blockers |
| Unit | `mvn test jacoco:report` | coverage reported, not thresholded |
| Architecture | ArchUnit `@ArchTest` in the normal test run | 0 violations |
| Mutation | `mvn org.pitest:pitest-maven:scmMutationCoverage -DwithHistory` | 70 → ratchet to 80–85 |
| Contract | `mvn pact:verify` | 0 broken pacts |

## 4. Flaky test policy

Retry-until-green is not a fix. *"A test that needs three retries to pass should be
called what it is: failing, with extra steps."* Retries mask real race conditions.

| Situation | Correct action |
|---|---|
| Test that the agent's change broke | **Fix the code.** Not flake. Self-quarantine here is forbidden. |
| Pre-existing flaky test | Quarantine: move out of the gating suite, keep it running on a schedule, assign an owner, 30-day fix SLA, require N consecutive passes to exit |
| Agent adds a `retry()` or raises a timeout | Cheat-flag #11. Blocked. |

Monitor quarantine size and entry/exit balance. Growing faster than it drains is a decay
signal that no individual gate will catch.

## 5. Suite health under autonomous operation

Agents produce tests at a rate humans never did. Without these, you get 1,000 useless
tests and a 40-minute suite.

| Metric | Detects |
|---|---|
| Suite runtime growth vs LOC growth | Duplication and redundant setup |
| Assertion-per-test ratio trend | Agents padding count over substance |
| Near-duplicate test clustering (AST or embedding similarity) | Regenerated tests instead of reused fixtures |
| Mutation contribution per test | Tests whose removal changes zero kill outcomes — pure runtime tax |
| Skip-count trend | Slow accumulation of disabled tests |

Run a **test deletion audit** every N sessions: mutation-test the existing suite and
flag tests that kill nothing a sibling doesn't already kill.

## 6. Worked example — this repository

Griffin's CI already implements the tiering. Mapping:

| Ladder | Griffin |
|---|---|
| 1–2 fast | backend `make lint` / `make typecheck` / `make test-unit`; frontend `next lint`, `jest` |
| 4 full suite | `commit-tests.yml` (push, non-main) + `integration-tests.yml` |
| 10 E2E | `e2e-tests.yml` — live FastAPI + Celery + Redis + Playwright, PR-to-main only, 40-min cap |
| Release | `release-tests.yml` on main |

Gaps to close: diff coverage (5), cheat scan (6), architecture fitness (7), mutation (9),
and the local `Stop` gate that makes any of it binding before CI.
