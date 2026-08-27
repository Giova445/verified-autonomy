# 06 — Guardrails: Clean Architecture Made Mechanical

Uncle Bob's canon translated into things a machine checks, plus an honest account of
where his advice is contested and should not be enforced.

---

## 1. The translation

Martin's professionalism argument is the right frame for autonomous agents — arguably
more apt for them than for humans, since an agent has no reputation to protect. But
"be professional" is layer-1 persuasion. Here is the layer-2 form:

| Martin's principle | Mechanical enforcement |
|---|---|
| "Professionals never ship code they haven't verified" | `Stop` hook — the turn cannot end while a gate is red (02, 03) |
| Three Laws of TDD | RED proof gate: new test must fail at pre-implementation HEAD, for an assertion reason (04 gate 3) |
| "QA should find nothing" | CI re-runs the full ladder. A CI failure after local green is an incident, not a normal outcome |
| The Dependency Rule | Architecture fitness function, 0 violations (§3) |
| Boy Scout Rule | Complexity/duplication ratchet — never-worse-than-baseline (§4) |
| SRP ("one actor") | Not mechanically checkable. Verifier checklist item. |
| "Every comment is a failure" | **Not enforced.** See §2. |
| Small functions | Enforced at 50/80 lines, not at his 2–4. See §2. |

## 2. Where Uncle Bob is contested

An autonomous system must not cargo-cult. Two of Martin's positions are widely rejected
and should not become gates:

**Function length dogma (2–4 lines).** Martin's own examples run this short, and blocks
inside `if`/`while` should ideally be a single call. The counter-argument, which we
accept: extreme decomposition produces jump-to-definition fatigue — deep call chains
where each function is trivial but the whole is harder to trace than one linear 20-line
function. We gate at 50 soft / 80 hard.

**Comments as failure.** Broadly rejected for *why*-comments. "Good naming replaces all
comments" does not cover a regulatory constraint, a deliberate workaround, or a
performance trade-off. We enforce nothing about comment density; the Verifier checks
whether comments explain *why* rather than restate *what*.

**Clean Architecture itself is over-applied.** The indirection tax is real: Controller →
Command → Handler → Repository interface → Repository impl → ORM, each a pass-through,
turns a two-hour feature into a day. DTO explosion gives you five representations of six
fields. An agent should choose, not default:

| Signal | Lean toward |
|---|---|
| Multiple real (not hypothetical) backends exist or are roadmapped | Ports & adapters, full Clean Architecture |
| Single team, single deployable, CRUD-dominant | Vertical slice or simple layered |
| Genuinely complex, long-lived domain logic | Clean Architecture + DDD tactical patterns |
| Prototype, spike, or under ~200 LOC | No ceremony |
| An interface has exactly one implementation and no test-double need | **Delete the interface** |

## 3. Architecture fitness functions

The highest-leverage guardrail. A fitness function is an objective, automated check of an
architectural characteristic, run in the pipeline so erosion is caught mechanically
instead of in review — where nobody catches it.

**Java — ArchUnit** (the Dependency Rule as a JUnit test):

```java
@AnalyzeClasses(packages = "com.example.app")
class ArchitectureTest {
    @ArchTest
    static final ArchRule dependency_rule = layeredArchitecture()
        .consideringAllDependencies()
        .layer("Controllers").definedBy("..adapter.web..")
        .layer("UseCases").definedBy("..usecase..")
        .layer("Entities").definedBy("..domain..")
        .layer("Persistence").definedBy("..adapter.persistence..")
        .whereLayer("Controllers").mayNotBeAccessedByAnyLayer()
        .whereLayer("UseCases").mayOnlyBeAccessedByLayers("Controllers")
        .whereLayer("Entities").mayOnlyBeAccessedByLayers("UseCases", "Persistence");
}
```

Fails the build the moment a `domain` class imports from `adapter.web`. Bytecode
analysis, no runtime cost.

**TypeScript — dependency-cruiser** (`.dependency-cruiser.cjs`):

```js
module.exports = {
  forbidden: [
    { name: 'no-domain-to-infra', severity: 'error',
      from: { path: '^src/domain' }, to: { path: '^src/infrastructure' } },
    { name: 'no-circular', severity: 'error', from: {}, to: { circular: true } },
  ],
};
```

**Python — Import Linter** (`.importlinter`):

```ini
[importlinter]
root_package = myapp

[importlinter:contract:layers]
name = Domain must not depend on infrastructure
type = layers
layers =
    myapp.interface_adapters
    myapp.use_cases
    myapp.domain
```

Others: NetArchTest (.NET), pytest-archon (Python, inline with pytest), go-arch-lint
(Go), `eslint-plugin-boundaries` / `import/no-restricted-paths` (lint-time TS),
`cargo-deny [bans]` (Rust, crate-edge level).

## 4. Budgets and the ratchet

| Metric | Tool | Threshold |
|---|---|---|
| Cyclomatic complexity | SonarQube, ESLint `complexity`, gocyclo, lizard | warn >10, fail >20 |
| Cognitive complexity | SonarQube | fail >15/function |
| Python complexity | `radon cc --min C` | grade B target for new code |
| Function length | lizard, custom lint | 50 soft / 80 hard |
| File length | wc / custom | 400 typical / 800 hard |
| Parameter count | ESLint `max-params`, PMD | ≤4; parameter object beyond 3 |
| Nesting depth | ESLint `max-depth` | ≤4 |
| Duplication | jscpd, PMD-CPD | project %, ratcheted |
| Dead code | knip (TS), vulture (Py), `cargo udeps` | 0 new dead exports |

**Always ratchet on an existing codebase.** Baseline the current count, fail only on
increase, lower the baseline opportunistically. Without this, turning on gates in a
legacy repo blocks the agent on debt it didn't create, and the pragmatic response is to
turn the gates off — which is the worst outcome.

## 5. Type strictness — the cheapest high-yield gate

Static typing catches the two most characteristic LLM defects **before a test runs**:
hallucinated APIs and silent nullability gaps.

| Language | Setting | Catches |
|---|---|---|
| TypeScript | `strict` + **`noUncheckedIndexedAccess`** + `exactOptionalPropertyTypes` | Indexing into a possibly-empty array or missing key — the single highest-value flag for LLM code. Invented fields fail at compile time. |
| Python | `mypy --strict` / pyright strict | Hallucinated attributes, wrong returns, `Any` leakage hiding an invented API surface |
| Go | `go vet` + `staticcheck` | Dropped `err` returns — Go's #1 LLM defect |
| Rust | `clippy::pedantic` | `unwrap`/panic where `Result` propagation belongs |
| JS/TS | `eslint-plugin-import` | Import of a nonexistent export — the direct signature of a hallucinated API |

## 6. Security guardrails

| Concern | Tool | Gate |
|---|---|---|
| Secrets in diff | gitleaks (pre-commit + `PreToolUse`) | 0 findings, hard block |
| Live-credential sweep | trufflehog `--only-verified` | scheduled, 0 verified |
| SAST | Semgrep (+ custom rules for project invariants), CodeQL | 0 high |
| Dependency vulns | osv-scanner, `pip-audit --strict`, `npm audit` | 0 high/critical |
| **Dependency existence** | registry resolution + typosquat distance | **0 unresolvable** |
| Licenses | cargo-deny, license-checker, pip-licenses | policy-conformant |
| IaC | Checkov, tfsec | 0 high |

### The five things an agent may never do

1. **Add a dependency without verifying it resolves on the real registry**, and scanning
   it. On the 2026 frontier cohort the hallucination rate has narrowed to **4.62%–6.10%**
   (down from the 5.2%–21.7% range across 2025 models) — but the risk got *sharper*, not
   milder: researchers found **127 package names that all five tested frontier models
   hallucinate identically**, of which **53 remained registrable after disclosure**. One
   malicious registration now threatens users of every major provider simultaneously.
   Registry verification stays a hard gate.
2. **Weaken a security control** — disable TLS verification, widen CORS, remove an auth
   check — without explicit human-reviewed justification.
3. **Commit a secret.** A gitleaks hit is stop-the-line: rotate the credential, don't
   just delete the line.
4. **Silently swallow an exception.** Bare `except: pass` / `catch {}` is a defect, not a
   style choice. Every catch logs with context or rethrows.
5. **Add a package whose name is within typosquat distance of a well-known one** without
   human confirmation.

## 7. Structural defaults

**Functional core, imperative shell.** Pure, deterministic domain logic isolated from
I/O, mutation, and time; a thin shell does all side effects. Pure functions are trivially
unit-testable without mocks and cannot have hidden state-dependent bugs — which makes
agent-written core logic verifiable with plain input/output assertions.

**Errors as values in the core.** Exceptions are invisible control flow, and an LLM
forgets to catch them. The core returns `Result`/`Either`/tagged unions; the shell
translates outside-world exceptions into the core's error type at the boundary.

**Validate at every boundary.** Zod, Pydantic, ajv. Reject malformed shapes immediately
rather than letting an `undefined` propagate into the core.

**Immutability.** New objects, never in-place mutation. Prevents the hidden side effects
that are hardest to catch in review.

## 8. Design pattern decision table

Knowing the pattern matters less than knowing when *not* to reach for it. Agents
over-apply patterns because pattern-shaped code is well-represented in training data.

| Pattern | Motivating smell | Overuse anti-pattern |
|---|---|---|
| Strategy | ≥3 algorithm variants that will grow | Wrapping one `if/else` in an interface |
| Adapter | Genuine external boundary (3rd-party SDK vs domain) | Wrapping your own code "for consistency" |
| Repository | Real swap risk or real test-double need | One repo per table, pure ORM pass-through |
| Factory | Nontrivial, reused construction branching | A factory that always returns its one type |
| Observer | Multiple decoupled listeners, possibly runtime-added | Two-party callback dressed as pub/sub |
| Command | Queue, log, undo, or retry as first-class | Every function call as a "command" object |
| Decorator | Cross-cutting wrapping (cache, retry, log) | Five-deep chains for one function's worth of behavior |
| State | True state machine with transition rules | A boolean's two branches as two classes |
| Ports & Adapters | Multiple real integrations | A single-integration CRUD app |
| CQRS | Genuinely divergent read/write shape or scale | Low-traffic admin CRUD |
| Saga | Cross-service transaction needing compensation | Multi-step function inside one service |

## 9. The Verifier's rubric

What the adversarial reviewer checks — everything static analysis structurally cannot.
Grounded in Google's code-review standard (design → functionality → complexity → tests →
naming → comments → style → docs), extended for LLM-authored code.

- [ ] **Requirement coverage** — every acceptance criterion, not just the happy path.
- [ ] **Name/behavior match** — does `validateUser` only validate, or also persist? Name
      drift is a top LLM tell.
- [ ] **Abstraction-level consistency** — does one function mix domain policy with byte
      manipulation?
- [ ] **Error paths** — every new external call has a failure-path test, and the failure
      is loud.
- [ ] **Concurrency hazards** — shared mutable state from >1 async path without a lock or
      immutable copy.
- [ ] **Backward compatibility** — public API, schema, or CLI flag changed without a
      migration path?
- [ ] **Observability** — can a new failure path fail invisibly in production?
- [ ] **Dependency justification** — smallest reasonable solution, registry-verified,
      scan-clean.
- [ ] **Scope discipline** — does the diff touch only what the task required? Unrelated
      formatting churn hides the real change.
- [ ] **Simplest thing that works** — or did the model reach for the first pattern it
      recalled? (§8)

Verdict rules: the Verifier may only *add* findings. It cannot clear a red gate. Its
model should differ from the implementer's — same-lineage judges exhibit
self-enhancement bias.
