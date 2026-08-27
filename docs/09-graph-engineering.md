# 09 — Graph Engineering

The substrate layer. Gates catch a bad change *after* it is written; a graph prevents it
from being written blind.

---

## 1. Why this is the substrate question

An autonomous agent's characteristic failure is rarely bad syntax. It is:

- changed a function whose fourth-order caller broke
- ran 4,000 tests to validate a two-line diff
- grepped for a name and missed the seven call sites that route through an interface

All three are **graph problems wearing agent costumes.** Text search tells you where a
string appears. A graph tells you what depends on what. An agent without one is guessing
at consequences it cannot see — and, per [01](01-evidence-base.md), it will report that
guess as a completed task.

This reframes the architecture. The gate ladder is a **detection** layer. The graph is the
**prevention** layer, and it is cheaper: preventing an edit that breaks 40 call sites costs
one query; detecting it costs a full CI run plus a rework loop.

> **Status in this repo (verified 2026-08-17):** CodeGraph is live — 854 files, 9,009
> nodes, 16,582 edges, 19.7 MB. Python 404 / tsx 231 / ts 219. Edge kinds: `contains` 8136,
> `calls` 4998, `imports` 2746, `references` 395, `instantiates` 280, `extends` 27.
>
> Still make `codegraph_status` a gate-0 precondition: graph tooling is per-project and not
> ambient, and **an agent that does not check first silently falls back to grep precision
> without knowing it lost anything.**

## 2. Tool landscape

| Tool | Indexes | Query | Languages | Incremental | Local agent use |
|---|---|---|---|---|---|
| **tree-sitter** | Syntax trees, error-tolerant | S-expression patterns | 100+ | Per-file reparse | Yes — the substrate under most of the rest |
| **ast-grep** | AST pattern matches, rewrites | CLI pattern lang, YAML rules | tree-sitter set | Stateless | Yes — structural grep/codemod. Not a graph. |
| **CodeGraph** (MCP) | Symbols, call edges, files → SQLite+FTS5 | MCP: search/callers/callees/impact/context | Multi via tree-sitter | Watcher, ~500ms debounce | **Yes — purpose-built for agent loops** |
| **SCIP** (Sourcegraph) | Symbols, defs/refs/occurrences | Sourcegraph server or raw protobuf | Java/Scala/Kotlin, TS/JS, Rust, C/C++, Ruby, Python, .NET, Dart, PHP | Per-indexer | Indexers run locally (scip-typescript ~1k–5k LOC/s); cross-file query wants a server |
| **stack-graphs** (GitHub) | Name-binding graph, path-based resolution | Path-finding | Per-language DSL | **Incremental by design** | Yes for navigation precision; more accurate on scoping/shadowing than tree-sitter alone |
| **Glean** (Meta) | Typed facts: defs, refs, types, calls, inheritance | Angle (Datalog-ish) | C++, Hack, Python, Haskell, Flow + SCIP/LSIF-derived | Yes | Org-scale infra; heavy to stand up solo |
| **Kythe** (Google) | Cross-ref graph from instrumented builds | GraphStore + serving API | C++, Java, partial Go | Build-coupled | Low — needs a hooked build system |
| **Joern** | Code Property Graph: AST+CFG+PDG+calls | CPGQL (Scala/Gremlin) | C/C++, Java, binary, JS, Python, Kotlin | Per-module | Yes for taint/dataflow security work; JVM+Scala setup |
| **CodeQL** | Relational DB from build: AST+CFG+dataflow | QL | C/C++, C#, Java, JS/TS, Python, Go, Ruby, Swift | Full rebuild typically | One-shot deep queries; too slow per agent turn |
| **Nx project graph** | Package/project deps | `nx affected`, `nx graph` | JS/TS monorepo + plugins | Hash-based | **Yes — this is the gate-scoping graph** |
| **Bazel / Turborepo** | Build target DAG | `bazel query rdeps(...)`, `turbo --filter=...[base]` | Polyglot / JS-centric | Content-hash | Yes — purpose-built affected-set computation |

**No single tool covers all three needs.** Real setups compose: a symbol graph for impact
and context, a build/project graph for gate scoping, and optionally CodeQL or Joern for
one-off deep security queries.

## 3. The applications

### 3.1 Blast radius before editing

The question is not "where does this text appear" but "what is the transitive closure of
things that call this, including through interfaces." That is a reverse-call-graph
traversal.

```
codegraph_search(query="get_settings")            # locate: kind, file, signature
codegraph_callers(symbol="get_settings", limit=50)  # ← THE blast-radius query
```

**Measured correction — do not use `codegraph_impact` for blast radius.** Tested against
this repo's live index: `codegraph_impact` returns *contained* symbols (class members, file
children), not the reverse-dependency closure. `get_current_user` at depth=2 returned 2
same-file symbols. `codegraph_callers` on `get_settings` returned **17 real callers across
8 files** — app.py, jwt.py, session.py, sync_session.py, rag/service.py, share_service.py,
telemetry.py, product_ranking.py. Callers is the reverse-dep query; impact is a containment
walk. Iterate `callers` yourself for depth > 1.

The Bazel analogue at build-target granularity:

```bash
bazel query --keep_going 'kind(rule, rdeps(//..., set(//services/pricing:rate_calc)))'
```

`rdeps(universe, x)` inverts the normal `deps()` direction — which is exactly the direction
an agent needs *before* it edits.

**Make this a state transition, not an optional courtesy.** In the FSM
([02 §3](02-architecture.md)), PLAN should not complete without an impact set recorded in
the work item. That impact set then drives test selection (§3.2) and the reviewer's
attention.

### 3.2 Test selection — the biggest wall-clock win

Naive agent behavior is "run everything": safe, and at scale it makes the loop unusable.
Test Impact Analysis maps changed symbols/lines → covering tests.

| Tool | Mechanism | Measured effect |
|---|---|---|
| Azure Pipelines TIA | Coverage map from prior runs, diffed against changeset; falls back to full run when it can't reason (renames, config, new files) | Microsoft, Google, Datadog each report **50–80% CI time saved** |
| `pytest-testmon` | `coverage.py` fingerprints which lines each test executed; selects tests whose fingerprint intersects the diff | 4,000 tests → the ~30 that touch the change |
| `jest --findRelatedTests` | Walks the **static import graph** from changed files | Misses dynamic `require()` |
| `nx affected --target=test --base=main` | Project graph + input hashing | One team: CI **12 min → 3 min**; another **12 min → 1 min** |
| `bazel query 'tests(rdeps(//..., set($CHANGED)))'` | Reverse deps filtered to tests | — |
| `turbo run test --filter=...[HEAD^]` | Workspace graph + git diff | Mercari: ~50% task duration, ~30% job duration reduction. One study found **affected-only execution was the single biggest lever** — running 4 packages instead of 45 beat any caching optimization |

Two mechanisms, both graph queries: **coverage↔test map joined on the diff**, or
**import/call-graph reachability from the diff**.

**Safety rule:** selection must fail *open*. If the graph is stale, the change is a rename,
or the diff touches config, run everything. A test-selection bug is indistinguishable from
a passing test suite — which makes it exactly the kind of silent gate failure this
architecture exists to prevent.

### 3.3 Gate scoping

Test selection generalized. Compute the affected-package set **once**, then run every gate
(lint, typecheck, build, test) against that set rather than re-deriving per gate type.

```bash
nx affected --target=lint,typecheck,test,build --base=origin/main
turbo run lint typecheck test --filter=...[origin/main]
```

This is what makes the [gate ladder](04-gate-ladder.md) affordable in a monorepo: gate cost
scales with the size of the change, not the size of the repo.

### 3.4 Context retrieval — and an honest answer

Walk the graph from a seed symbol to assemble minimal precise context, rather than grep or
embedding similarity. The evidence is genuinely mixed and worth stating rather than
picking a side:

- **Relational queries:** graph wins clearly. One benchmark, 0.96 context precision for
  GraphRAG vs 0.84 for vector RAG; another found vector accuracy collapsing to ~0% on
  schema-heavy 10+-entity queries while graph held 70–90%.
- **Plain snippet retrieval** ("find the function that does X"): vanilla vector RAG beat
  GraphRAG in at least one code study. And notably, **Claude Code moved away from vector
  RAG toward agentic grep** (glob → grep → read), because iterative keyword search with
  course-correction outperformed static embedding retrieval on SWE-bench-style tasks.
  Augment reported similar.

**The reconciliation:** route by question type.

| Question shape | Right primitive |
|---|---|
| "Where does this identifier/string appear?" | Lexical — grep |
| "Where does this *pattern* appear?" | Structural — ast-grep |
| "What depends on this / what breaks / what's reachable?" | Graph traversal |

Give the agent all three as distinct tools. Do not replace one with another — embedding
RAG is the weakest of the three for code specifically, because embedding-space similarity
correlates poorly with call-graph and type relationships.

### 3.5 Architecture fitness as reachability

The Dependency Rule is a reachability question: *is there any path from `domain/` to
`infra/`?* That is strictly stronger than the filename-pattern lint proposed in
[06 §3](06-guardrails.md) — a path-pattern rule misses violations that route through an
intermediate module. Where you have a real graph, assert reachability; keep the
dependency-cruiser/import-linter rules as the cheap always-available fallback.

### 3.6 Dead code as mark-and-sweep

Start from entry points (exported APIs, route handlers, CLI mains, tests), mark everything
reachable, flag the rest. **Knip** does this for JS/TS; Vercel reportedly deleted ~300,000
lines with it. `ts-prune` is the maintenance-mode predecessor — it couldn't reason about
unused dependencies or mutually-recursive dead code, which are precisely the cases a real
graph handles.

## 4. Graphs for orchestration

The same graph that answers "what breaks" answers "what can run in parallel."

A coordinator decomposing a spec should derive the task DAG from **real structural
dependencies** — which modules each subtask touches, and what depends on those — not from
the model's intuition about ordering. Then:

- Subtasks whose **write-sets are disjoint** and that create no dependency edge in the
  module graph may run in the same wave.
- A subtask cannot start until everything producing its inputs has completed.
- **One writer per file, always.** If two subtasks in a wave touch the same file, that is
  not a scheduling problem to solve cleverly — it is a signal the decomposition was wrong
  and should be re-split along the graph's actual module boundaries.
- Read-only subtasks are always safe to run concurrently; they have no write-set.

This is exactly what Bazel/Nx/Turborepo already compute for builds, repurposed as a wave
scheduler for agents. It also gives the read/write asymmetry rule from
[02 §4](02-architecture.md) a mechanical basis instead of a heuristic.

## 5. Graph memory across sessions

For agent memory (not code structure), there is reasonable head-to-head evidence:

| Benchmark | Graph memory | Vector memory |
|---|---|---|
| LongMemEval | Zep/Graphiti **63.8%** | Mem0 49.0% |
| Deep Memory Retrieval | Zep/Graphiti **94.8%** | MemGPT 93.4% (with ~90% lower latency vs full-context stuffing) |

The mechanism: bi-temporal edges (facts carry validity intervals and are *invalidated*
rather than deleted) support "what did we conclude, and does it still hold" queries that
nearest-neighbor recall cannot express. Graphiti's retrieval path is hybrid semantic +
BM25 + graph traversal with no LLM call at retrieval time, ~300ms P95 — graph memory need
not be slower.

Mapped to coding: *"does module X still use pattern Y as of last session"* is a graph
question. *"find notes about caching"* is a vector question. Run hybrid; don't pick.

## 6. Failure modes — and when to skip the graph

**Staleness is structural, not incidental.** Every graph is a snapshot. CodeGraph's watcher
debounces ~500ms behind edits — querying in the same turn as an edit risks reading
pre-edit structure. Tools without a fast incremental path (Kythe, most CodeQL workflows)
need full re-extraction, which means agents end up trusting a graph that is meaningfully
behind the working tree — worst precisely mid-refactor, when renames and moves are the norm
and correct impact analysis matters most.

**Static analysis cannot see dynamic behavior.** Reflection, runtime dispatch, string-based
routing, monkey-patching, generated code. A Java method invoked reflectively by a
runtime-computed string shows **zero static callers** while real callers exist. This is the
dangerous case: the graph looks authoritative and is wrong, which is arguably worse than no
graph. Treat "zero callers" as a hypothesis to verify, never as license to delete.

*Measured here:* this repo has **106 `Depends()` sites** — FastAPI dependency injection
passes a function as a reference, not a call. Those land on `references` edges (395 total)
rather than `calls` (4998). A blast-radius query using `callers` alone **under-reports DI
wiring**. For a FastAPI/NestJS/Spring-style codebase, union callers with references before
trusting an impact set. Confirming the flip side: `PricingService` and `run_pricing`
returned zero callers and grep agreed — one definition, no uses. Genuine dead code, found
in a single query.

**Cross-language edges are approximate.** A Python service calling Go over gRPC, or a TS
frontend hitting a route defined in another repo, needs runtime tracing or confidence-scored
heuristics. Treat cross-language edges as *probably*, not *certainly*.

**Setup cost is real.** Glean and Kythe assume a dedicated indexing pipeline hooked into
the build. Even lightweight tools have friction — as this repo demonstrates, a configured
MCP server with no index produces a failed first query, not a graceful degradation.

**Skip the graph when:**

- The codebase is small, or the task is a one-off script — agentic grep finds it in two
  calls faster than any index builds.
- The codebase is heavily dynamic (Ruby metaprogramming, pervasive Python `getattr`
  dispatch, widespread dynamic `require`) — false negatives on callers create unearned
  confidence.
- Churn outpaces the reindex cadence, so the graph is stale more often than fresh.
- The question is lexical, not relational — "where does this config key appear" wants grep.
- The engagement is short enough that index build cost exceeds what it saves.

## 7. Integration into the architecture

| Where | Graph's job |
|---|---|
| **Gate 0** | `codegraph_status` — if not initialized, say so and degrade *explicitly*. Never silently fall back to grep precision. |
| **PLAN → RED** | Impact set computed and recorded in the work item. Exit criterion, not a courtesy. |
| **Gate 2 / 4** | Test selection from the impact set — failing open on renames, config changes, stale index. |
| **Gates 1–7** | Affected-package scoping so gate cost tracks change size, not repo size. |
| **Gate 7** | Dependency Rule as reachability, with path-pattern lint as fallback. |
| **Verifier** | Impact set is the reviewer's attention map — "you changed X; here are the 12 call sites; which did you check?" |
| **Orchestration** | Task DAG and parallel-safety from module boundaries, not from model intuition. |
| **Memory** | Structural facts in the graph; prose notes in vector memory. Hybrid retrieval. |

## 8. Getting started here

```bash
codegraph init -i          # build the index for this project
```

Then make `codegraph_status` a precondition in gate 0, and add the impact query to the
PLAN → RED exit criteria. The `nx affected` / `turbo --filter` equivalent for gate scoping
depends on whether the frontend and backend get unified into a workspace — currently they
are separate trees, so per-tree gate scoping is the practical first step.
