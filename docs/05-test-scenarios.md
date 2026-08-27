# 05 — Test Scenario Derivation Catalog

A procedure an agent executes to derive test cases from a requirement, rather than
writing whatever cases occur to it. This is the antidote to the specific failure where
the agent tests the happy path it just implemented and stops.

Designed to be copied verbatim into a project skill. See
[`kit/agents/`](kit/) for the packaged form.

---

## Why a checklist and not judgment

Unit tests written by the agent that wrote the code share the agent's blind spots. If it
didn't think of the empty-array case while implementing, it won't think of it while
testing. A mechanical derivation procedure surfaces cases the agent never considered —
which is exactly the class of defect that survives to production.

Property-based testing works for the same reason, and the same caveat applies: **derive
properties from the requirement text, not from the implementation**, and preferably in a
separate pass from the one that wrote the code.

---

## Part A — Systematic derivation

Run all seven for each requirement. Recording "not applicable, because X" is a valid
outcome and is itself evidence of deliberate coverage.

### A1. Equivalence partitioning
Identify each input's valid and invalid classes. One representative per class. Not
exhaustive enumeration — one value per partition is the whole point.

### A2. Boundary value analysis
For every bounded input: `min-1, min, min+1, max-1, max, max+1`.

First, extract the constraints explicitly from the requirement: type, range, length,
format, required/optional, and **whether the boundary is inclusive or exclusive**.
Ambiguity there is a documented off-by-one source — and an assumption-register entry,
not a guess.

### A3. Decision tables
For logic driven by 2+ independent conditions, build the full condition/action table and
write one test per row. Including the rows nobody thinks about.

### A4. State-transition testing
For anything with a lifecycle (`draft → published → archived`): every valid transition,
every **invalid** transition attempt, and transitions attempted from terminal states.

### A5. Pairwise / combinatorial
With 3+ independent multi-valued parameters, generate an all-pairs matrix rather than the
full Cartesian product. Tools: PICT, AllPairs. Keeps case count tractable while covering
pairwise interaction bugs.

### A6. Error guessing
What would a careless caller pass? What did the spec forget to mention?

### A7. CRUD matrix
For any resource, cross `{Create, Read, Update, Delete, List}` against
`{valid data, invalid data, missing resource, unauthorized actor, concurrent actor}`.
Twenty-five cells; not all relevant, all considered.

---

## Part B — The edge-case checklist

Apply to **every parameter of every function and endpoint** under test.

| Category | Cases |
|---|---|
| **Emptiness** | empty string, empty array, empty object, empty file, zero rows |
| **Absence** | `null`, `undefined`, missing key, missing required field, omitted optional |
| **Numeric extremes** | zero, negative, `MAX_INT` (2³¹-1, 2⁵³-1 in JS), `MIN_INT`, overflow, float precision (`0.1 + 0.2`), `NaN`, `Infinity`, division by zero |
| **Text extremes** | longer than the DB column, unicode, emoji, combining characters, RTL script, whitespace-only, leading/trailing whitespace, control characters, null bytes |
| **Duplication** | duplicate collection entries, double submit, duplicate key insert |
| **Concurrency** | concurrent writes to one resource, create race, lost update, deadlock ordering |
| **Timing / network** | timeout, slow response, partial response, mid-request connection drop, retry storm |
| **Partial failure** | multi-step operation fails halfway — does it roll back, or leave inconsistent state? |
| **Authorization** | permission denied, expired token, wrong tenant/org scope, privilege escalation attempt, IDOR |
| **Idempotency** | request replayed with and without an idempotency key; retry after timeout causing a double effect |
| **Temporal** | timezone boundary, DST transition, leap year, leap second, past/far-future dates, clock skew between services |
| **Locale** | non-US date and number formats, currency, collation-dependent sort order |
| **Injection** | SQL/NoSQL, command injection, path traversal (`../../`), XSS, template injection, oversized payload |

---

## Part C — Property derivation

For any function with a documented contract, mechanically consider these property
classes before writing example-based tests:

| Property | Form | Typical fit |
|---|---|---|
| Round-trip | `decode(encode(x)) == x` | Serializers, parsers, codecs |
| Idempotency | `f(f(x)) == f(x)` | Normalizers, upserts, migrations |
| Invariant preservation | `len(sort(xs)) == len(xs)`, multiset equality | Transformations |
| Metamorphic | `f(x + k)` relates predictably to `f(x)` | Numeric, search, ranking |
| Commutativity / associativity | `f(a,b) == f(b,a)` | Merges, set operations |
| Oracle comparison | matches a slow reference implementation | Optimizations, rewrites |

Tools: Hypothesis (Python), fast-check (TS/JS), jqwik (JVM), proptest (Rust).
For HTTP surfaces, `schemathesis run openapi.yaml --checks all` is the API-boundary
analog and should run against every new or changed endpoint automatically.

---

## Part D — Layer selection

Which layer catches which failure. Put the test where it will actually catch the bug.

| Defect class | Catching layer |
|---|---|
| Off-by-one, wrong operator, boundary miss | Unit **+ mutation testing** (unit alone often survives these) |
| Hallucinated API, wrong signature | Typecheck / static analysis — before any test runs |
| Wrong assumption about a collaborator's contract | Integration test with the real collaborator; contract test |
| Silently swallowed error, half-built error path | Unit test targeting the catch block explicitly |
| Regression in a distant module | E2E / full-stack smoke |
| UI wiring drift | Playwright, visual regression |
| Edge case the agent never considered | **Property-based testing, BVA** — Part B is the mitigation |
| Test that passes without verifying anything | Mutation testing, assertion-density lint |

Suggested distribution: ~70% unit/component, 20% integration, 8% E2E, 2% contract/visual
by count — but weight the *time budget* toward integration, which catches the most
regressions per test for agent-written code.

---

## Part E — E2E determinism rules

Flaky E2E is worse than no E2E: it trains everyone, human and agent, to re-run until
green. Non-negotiables:

1. **Locator priority:** `getByRole` (doubles as an a11y check) → `getByLabel` →
   `getByText` → `getByTestId` → CSS/XPath last.
2. **Never `sleep`.** Playwright's actions and `expect()` already auto-retry against the
   live DOM. A hard wait in a test file is a lint failure.
3. **Hermetic data.** Seeded DB per run; one schema or transaction-rollback per parallel
   worker; never share mutable state across workers.
4. **Stub only true third parties.** Never stub your own backend — that turns an E2E test
   into a mocked integration test wearing an E2E costume.
5. **`testcontainers`** for real Postgres/Redis/Kafka rather than mocks at the
   integration tier.
6. **Artifacts are evidence.** `trace: 'on-first-retry'`, video, screenshots — attach the
   paths to the evidence bundle (03). A pass/fail boolean is not evidence; a trace is.

---

## Part F — Test smell detectors

What to run against the agent's own tests.

| Smell | Detector |
|---|---|
| Assertion-free / vacuous test | `eslint-plugin-jest` `expect-expect`; pytest-smell; grep for zero-assertion bodies |
| Eager test (many unrelated assertions) | tsDetect, PyNose |
| Conditional logic inside a test | ESLint custom rule; tsDetect |
| Sleep-based wait | grep `sleep(`, `setTimeout`, `waitForTimeout` in test files |
| Duplicate / near-duplicate test | AST or embedding similarity clustering |
| Mutation-blind test | Stryker / PIT / mutmut / cargo-mutants survived-mutant report |
| Skipped test left behind | Skip-count trend in CI |
| Snapshot rubber-stamping | Snapshot diff with no corresponding source change |

Note the framework trap that makes this necessary: **an empty test body reports as
passing** in JUnit, pytest, and Jest alike. Silent false confidence, by default.
