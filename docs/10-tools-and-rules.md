# 10 — Tools and Rules

The agent-computer interface, and the rules layer that governs it. This is where Anthropic
spends more engineering effort than on prompts — and where most setups quietly lose the
most performance.

---

## 1. Tools are the highest-leverage surface

Anthropic has stated that on their SWE-bench agent they spent **more time optimizing tools
than the overall prompt**. Their framing: agents are *non-deterministic users of
deterministic tools* — the same tool must work whether the model calls it once or fifty
times, in any order, with any prior context.

The canonical example is not a prompt fix. Their SWE-bench agent kept mis-resolving
relative paths after `cd`-ing out of the repo root. The fix was changing the tool's
parameter contract to **require absolute paths**. That failure mode went to zero — because
the interface removed the ambiguity, not because the model improved.

**Fix the interface before you fix the prompt.** That sentence is most of this document.

### Design principles, with specifics

| Principle | Specifics |
|---|---|
| **Consolidate, don't wrap** | Replace `list_users` + `list_events` + `create_event` with one `schedule_event`. Push aggregation into the tool; agent context is scarce, server memory is cheap. |
| **Cap responses** | Claude Code defaults to **25,000 tokens** per tool response. Paginate, filter, offer range params — and truncate *with instructions on how to get more*, never silently. |
| **Offer a terse mode** | Anthropic's Slack tool shipped a `ResponseFormat` enum: concise responses ran **~72 tokens vs 206** (~⅓) while preserving what the agent needed to act. |
| **Namespacing is not cosmetic** | Prefix (`asana_search`) vs resource-style (`asana_projects_search`) had "non-trivial effects" on eval accuracy. A/B test it like any other prompt surface. |
| **Semantic identifiers, not UUIDs** | Return `name`/`file_type`, not `uuid`/`mime_type`. Every opaque token is a hallucination surface with nothing to reason over. |
| **Errors are the next action** | Not a stack trace. *"Try filters like `status:active`, or paginate with `limit=10, offset=20`."* |
| **Unambiguous parameters** | `user_id` not `user`. Absolute not relative. |
| **Descriptions onboard a new hire** | Spell out query syntax, term definitions, resource relationships. When Claude's web search appended "2025" to queries unnecessarily, the fix was the *tool description*, not the prompt. |

### The evaluation loop

**Prototype → Evaluate → Collaborate.** Build the tool, wire it into a real agent, then
write evals that are realistically ambiguous. Anthropic's contrast:

- Good eval: *"Schedule a meeting with Jane next week to discuss the Acme Corp project,
  attach the notes from our last planning meeting, and reserve a room."* (forces
  multi-tool chaining and ambiguity resolution)
- Weak eval: *"Schedule a meeting with jane@acme.corp"* (everything pre-resolved)

Track task accuracy, tool-call count, runtime, tokens, and error rate. Then **have an agent
refactor the tool definitions against those evals** — closing the loop with measurement
rather than taste.

## 2. What tool surface to give a coding agent

Two harnesses made opposite-looking bets, and both were right about different layers.

**SWE-agent's ACI** argues a tuned interface beats raw bash for the same model, and the
specifics are instructive:

- File viewer shows **exactly 100 lines** per turn with scroll and in-file search, instead
  of `cat`. Bounding the window keeps attention on a tractable slice.
- Directory search returns **only file paths with match counts, not surrounding context** —
  the paper states plainly that more context per match "proved to be too confusing for the
  model." A direct data point against *more information can only help*.
- The edit command **runs a linter and refuses to apply syntactically invalid changes** —
  an error guardrail inside the tool rather than a failure caught downstream.
- Even a successful no-output command returns *"Your command ran successfully and did not
  produce any output"* rather than blank, removing an ambiguous signal.

**OpenHands' CodeAct** takes the opposite bet: give bash + Python + a browser DSL and let
the agent express actions as code, which "generalizes far better and dramatically reduces
parsing errors" than 20 JSON-schema tools — code composition is more expressive than tool
composition, and the model has strong code priors.

**These are not in conflict.** The converged pattern, Claude Code included:

> **A few broad execution primitives (bash, code exec) + a small set of heavily-guarded
> tools for the highest-frequency, highest-error-cost operations (read, edit, search).**

That is exactly why Claude Code prefers `Read`/`Edit`/`Grep` over `cat`/`sed`/`grep`: those
operations have known failure modes — line-offset errors, encoding issues, silent overwrite
— that a dedicated tool can structurally prevent.

## 3. Edit application — the underrated failure source

This is a real, measured loop-killer independent of model quality, and it was missing from
the first draft of this architecture entirely.

| Strategy | Failure mode | Measured |
|---|---|---|
| Search/replace (`str_replace`) | Requires exact character match incl. whitespace | The default nearly everywhere; "String to replace not found" is common enough to have its own megathread |
| Unified diff | Model must emit valid diff syntax | Aider: switching GPT-4 Turbo from SEARCH/REPLACE to unified diff took its benchmark score **26% → 59%**, and made it "3x less lazy" (stopped eliding code with `...rest of code...`) |
| Patch format | Syntax corruption under weaker models | **Worst performer for most models** — Grok 4 **50.7%** failure, GLM-4.7 **46.2%** |
| Whole-file rewrite | Token-expensive; elision on long files | 39–46% on Aider's benchmark; simplest for weak models, scales badly |
| Hashline (line-hash addressed) | — | Matches or beats plain search/replace; **weaker models benefit most** |
| AST/semantic edit | Needs parseable structure, more tooling | Best isolated result: **98% vs 70%** for git-merge-style blocks |
| Fast-apply model (Cursor, Morph) | Adds a second model hop | 9–13x faster than full regen; Morph reports 50–60% fewer tokens, 1.3s vs 10–12s on a 1,000-line file |

**Two independent problems, often conflated:**

1. *Correctness* of the edit — solved by moving up the structure ladder (string match →
   diff → hashline → AST).
2. *Cost/latency* of materializing it — solved by decoupling "decide the edit" (main model)
   from "apply the edit" (small fast-apply model).

**Practical rule: match edit format to model tier.** Weaker models need whole-file or
hashline; strong models do better with diff (fewer tokens, comparable success). Picking one
format for all tiers is itself a bug.

## 4. The rules layer — and the arithmetic nobody applies

### The curse of instructions

If a model follows any single instruction with 95% reliability, the probability it
satisfies **all N simultaneously** is roughly `0.95^N`:

| Rules | P(all followed) |
|---|---|
| 10 | ~60% |
| 20 | ~36% |
| 28 | **~24%** |

Separately, attention-dilution research finds instruction adherence measurably declining
from around **~3,000 tokens** of input — well below any advertised context window — with a
negative correlation between total input length and system-prompt adherence specifically.

**So a long rules corpus does not merely cost tokens. It actively degrades compliance with
every rule in it, including the ones at the top.**

### Applied to this environment

Measured on this machine:

| Source | Size |
|---|---|
| `~/CLAUDE.md` (project) | ~1,700 tokens |
| `~/.claude/CLAUDE.md` (user global) | ~640 tokens |
| `~/.claude/rules/common/*.md` (9 files) | ~1,870 tokens |
| **Always-on total** | **~4,200 tokens, 28 ALWAYS/NEVER/MUST directives** |

That is **above the ~3,000-token dilution threshold**, and at 28 imperatives the
curse-of-instructions estimate is **~24%** probability that all are followed in any given
session.

And the content compounds it. This, from the global rules, is the archetype of a rule that
will not be followed:

```markdown
# Code Quality Checklist
- Code is readable and well-named
- Functions are small
- No deep nesting
- Proper error handling
- No hardcoded values
```

Every bullet is a soft judgment with no falsifiable check, no scoping, and it competes with
27 siblings for a finite compliance budget. It documents intent; it does not constrain
behavior.

**This indicts these documents too.** [06-guardrails.md](06-guardrails.md) proposes a long
rubric. That rubric belongs in a *verifier's checklist* (invoked, scoped, one task at a
time), not in always-on context. Which is exactly what §5 is for.

### What correlates with compliance

| Factor | Why |
|---|---|
| **Scoped** | `paths:` / `globs:` frontmatter so the rule loads only for relevant files |
| **Short** | Compliance ≈ per-rule-rate^N. Every rule you add taxes every other rule. |
| **Falsifiable** | A bad/good code pair beats an adjective like "readable" |
| **Example-anchored** | Models imitate the structural pattern of examples more reliably than they generalize prose |
| **Prior-aligned** | A rule fighting a strong pretraining prior ("never add a docstring") shows measurably worse compliance than one going with the grain |

**Likely followed:**

```markdown
---
paths: ["src/api/**/*.ts"]
---
# API error handling
Every route handler returns errors via `ApiError(code, message)` —
never throw a raw Error or return a bare string.

Bad:  throw new Error("not found")
Good: throw new ApiError("NOT_FOUND", "Widget 123 not found")
```

Scoped, binary, example-anchored, one rule.

### The mechanism to use

- **`.claude/rules/*.md` with `paths:` frontmatter** loads a rule only when the agent
  touches matching files. Known caveat: path-scoped rules under the *user-global*
  `~/.claude/rules/` are reportedly ignored (issues #16853 / #21858) — scoping works
  reliably at **project** level only. Which is precisely where this environment's 1,870
  tokens of rules currently sit *globally*.
- **`AGENTS.md`** for anything that should outlive one harness — cross-tool, Linux
  Foundation stewarded, read by Claude Code, Codex, Cursor, Aider, Devin, Gemini CLI,
  Windsurf, Amazon Q.
- **Skills** for procedural knowledge: ~50-token metadata by default, full instructions
  only on match.

### The rewrite rule

> **If it is enforceable, make it a hook. If it is contextual, scope it with `paths:`. If
> it is procedural, make it a skill. Only genuinely universal, falsifiable constraints
> belong in always-on context — and there should be fewer than ten.**

## 5. Policy as code

Prose rules are advisory: ignorable, misreadable, and overridable by prompt injection. The
2026 direction is a **Policy Decision Point in front of every tool call**, making an
auditable allow/deny the agent cannot argue with — structurally different from *"the agent
decided not to."*

- **Cedar** (AWS) and **OPA/Rego** are the two engines being applied to agent actions.
  Cedar is reported **42–60x faster** than Rego and supports formal verification of policies
  ("this policy provably never grants X"). AWS shipped Cedar inside **Bedrock AgentCore
  Policy** (March 2026), intercepting every agent-tool call at the gateway.
- **Microsoft's Agent Governance Toolkit** (open-sourced April 2026) is a stateless engine
  that accepts YAML, Rego, or Cedar through one `evaluate()` call — deliberately
  engine-agnostic.
- The claim across all of them: *the agent does not decide what is allowed; the policy
  engine does.* A successfully injected agent that **attempts** a prohibited action is
  blocked at the PDP before it reaches the target system.

**Claude Code's hooks are a lighter instance of the same architecture** — `PreToolUse` sees
the full command including pipes and subshells, evaluates deny → ask → allow, and a hook
deny applies even in `bypassPermissions`. For most projects that is sufficient, and
[`kit/hooks/deny-dangerous.sh`](kit/hooks/deny-dangerous.sh) is that PDP. Reach for
Cedar/OPA when you need policies that are themselves reviewable, versioned, and formally
checkable across many agents.

## 6. Tool surface size

The other quiet performance leak.

| Tools in context | Effect |
|---|---|
| 10–20 | Safe zone |
| >20 | Selection accuracy declines |
| 40–50+ | Unreliable; needs architectural intervention |

Measured: a RAG-MCP benchmark found tool-selection accuracy of **13.62%** with a full
catalog exposed, rising to **43.13%** (>3x) with retrieval-filtered selection, while cutting
prompt tokens over 50%. Reported degradation across studies spans 7–85% accuracy loss as
catalogs grow.

More precisely, a chance-corrected study across BFCL/MetaTool/ToolBench (20–3,251 tools)
found **adaptive per-query depth strictly dominates fixed-K**: 90.3% coverage at K≈7.4
versus K=50 for the same coverage, and downstream accuracy *higher* with the shorter list
(93.1% vs 87.1% at fixed K=5). The dominant failure is **distractor confusion between
similar tools**, not list length as such.

**This environment has 400+ MCP tools available** — deep in the unreliable zone if they were
all resident. They are not: the harness defers them behind `ToolSearch`, loading schemas on
demand. That *is* the mitigation, and it is already working. The lesson generalizes: when
adding an MCP server, ask whether its tools should be resident or deferred, and prefer a
CLI the agent calls over a resident MCP server for single-project capabilities — fewer
tools in context, and no tool-poisoning surface.

### MCP notes for 2026

- **Tool poisoning ranks #3 on the OWASP MCP Top 10**: malicious instructions embedded in
  tool *metadata* — names, descriptions, parameter docs — which the agent reads and a human
  reviewer never sees. Mitigations are defense-in-depth: signed manifests, metadata
  scanning, session-scoped tool restriction, allowlisting, human checkpoints on
  irreversible actions.
- **The spec changed on 2026-07-28**: stateless protocol core (version and capabilities move
  into per-request `_meta`), multi-round-trip requests, header routing, cacheable list
  results, hardened auth. **Not backward compatible** without explicit fallback — version
  skew is now a real deployment concern.

### MCP server vs CLI vs skill

| Build a… | When |
|---|---|
| **MCP server** | The capability is reusable across agents/sessions/tools and benefits from a discoverable schema |
| **CLI the agent calls** | Single project, single agent — cheaper, just as effective, no protocol overhead and no tool-poisoning surface |
| **Skill** | The "capability" is procedural knowledge, not a callable function — progressive disclosure makes it nearly free until invoked |

## 7. Checklist

**Tools**
- [ ] Consolidated around workflows, not mirroring an API
- [ ] Response size capped with pagination/filtering; truncation explains how to get more
- [ ] A terse response mode exists for high-frequency calls
- [ ] Namespacing A/B tested, not assumed
- [ ] Responses use semantic identifiers, not raw UUIDs
- [ ] Errors suggest the next action
- [ ] Parameters unambiguous (absolute paths; `user_id` not `user`)
- [ ] Descriptions written as if onboarding a new hire
- [ ] ≤20 tools resident; the rest deferred behind search
- [ ] Highest-frequency, highest-cost operations have dedicated guarded tools
- [ ] Evals exist with realistic ambiguity; tool defs refactored against them

**Rules**
- [ ] Always-on instruction budget under ~3,000 tokens
- [ ] Fewer than ten always-on imperatives
- [ ] Everything else scoped with `paths:` — at **project** level, since user-level scoping is unreliable
- [ ] Every rule falsifiable, with a bad/good example
- [ ] Anything enforceable moved to a hook
- [ ] Anything procedural moved to a skill
- [ ] Cross-harness content in `AGENTS.md`

**Edits**
- [ ] Edit format matched to model tier
- [ ] Edits linted before application; invalid changes refused at the tool
- [ ] Fast-apply considered if large-file edits dominate the loop
