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
| Diff coverage | **≥80% on changed lines** | 2026 industry baseline. Repo-wide coverage is the wrong gate for an agent — its blast radius is the diff. Exclude generated code from the denominator explicitly, or codegen commits will tank it (or, worse, an agent will "fix" a low number by generating boilerplate). |
| Mutation score (diff-scoped) | **≥75%**, ratchet upward | Practical band is 70–85%; 90%+ for auth/payments; 100% is impractical. Start at 70 against legacy code. |
| Cyclomatic complexity | warn >10, fail >20 | ESLint default is 20; MS CA1502 default is 25 |
| Cognitive complexity | fail >15/function | SonarQube default; better predictor of review pain than cyclomatic |
| Function length | 50 soft / 80 hard | Martin argues far shorter; see 06 §2 for why we don't enforce his number |
| File length | 400 typical / 800 hard | Matches the existing project convention |
| Nesting depth | ≤4 | |
| Flaky rate | <1–2% healthy, >5% systemic | Google: ~1 in 7 tests shows flakiness at some point |
| Quarantine dwell | ≤30 days, owner assigned | Growing quarantine = decay signal |
| Perf regression | fail >10–15% vs rolling baseline | Absolute thresholds drift with runner hardware |

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
| Diff coverage | `diff-cover coverage/cobertura-coverage.xml --compare-branch=origin/main --fail-under=80` | 80% |
| Mutation | `stryker run --incremental` | break ≥75% |
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
| Diff coverage | `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` | 80% |
| Mutation | `mutmut run --paths-to-mutate=src/<changed>` | ≥75% |
| Architecture | `lint-imports` (Import Linter) or `pytest-archon` | 0 violations |
| Complexity | `radon cc --min C src` | grade B target |
| Dead code | `vulture src` | 0 new |
| Security | `gitleaks` · `pip-audit --strict` · `semgrep --config auto` | 0 findings |

### Go

| Gate | Command | Threshold |
|---|---|---|
| Vet + lint | `go vet ./... && golangci-lint run` | 0 |
| Unit + race | `go test ./... -race -cover` | race-clean, ≥75% |
| Architecture | `go-arch-lint check` | 0 violations |
| Mutation | `gremlins unleash` | ≥60–70% (ecosystem less mature) |
| Benchmark | `go test -bench=. -benchtime=3x` | <10–15% regression |

### Rust

| Gate | Command | Threshold |
|---|---|---|
| Lint | `cargo clippy -- -D warnings` | 0 |
| Unit | `cargo test` | ≥75–80% (tarpaulin) |
| Mutation | `cargo mutants --in-diff` | ≥75% |
| Supply chain | `cargo deny check` | licenses + advisories + bans clean |

### JVM

| Gate | Command | Threshold |
|---|---|---|
| Static | `mvn checkstyle:check spotbugs:check` | 0 blockers |
| Unit | `mvn test jacoco:report` | ≥80% line/branch |
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

A real monorepo we wired this into already implemented the tiering. Mapping:

| Ladder | Example repo |
|---|---|
| 1–2 fast | backend `make lint` / `make typecheck` / `make test-unit`; frontend `next lint`, `jest` |
| 4 full suite | `commit-tests.yml` (push, non-main) + `integration-tests.yml` |
| 10 E2E | `e2e-tests.yml` — live FastAPI + Celery + Redis + Playwright, PR-to-main only, 40-min cap |
| Release | `release-tests.yml` on main |

Gaps to close: diff coverage (5), cheat scan (6), architecture fitness (7), mutation (9),
and the local `Stop` gate that makes any of it binding before CI.
