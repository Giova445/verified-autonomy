# 02 — Architecture

The system design. Three enforcement layers, one task state machine, a small set of
roles, and explicit criteria for when to add agents (usually: don't).

---

## 1. The three-layer enforcement model

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — ADJUDICATION            outside the agent's trust boundary │
│ CI re-runs every gate · branch protection · CODEOWNERS · human review│
│ Converts the agent's claim into an organizational fact.              │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲  evidence bundle + PR
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 2 — ENFORCEMENT                    client-side, pre-model      │
│ PreToolUse deny · Stop gate · permissions · sandbox · egress allowlist│
│ Makes "I'm done" unsayable while any gate is red.                    │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲  tool calls
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 1 — PERSUASION                       shapes, never enforces    │
│ CLAUDE.md · AGENTS.md · skills · subagent prompts · plan mode        │
│ Raises the floor on default behavior. Assume it can be ignored.      │
└─────────────────────────────────────────────────────────────────────┘
```

**The rule:** if a constraint matters, it lives in layer 2 or 3. Anything written only
in layer 1 is a preference the agent may discard under pressure — and gate failure is
exactly the pressure that causes discarding.

### What each layer is made of

| Layer | Claude Code mechanism | Enforced by | Fails how |
|---|---|---|---|
| 1 | `CLAUDE.md`, `AGENTS.md`, `.claude/rules/*.md`, skills | The model's cooperation | Silently, under pressure |
| 2 | `PreToolUse` / `Stop` / `SubagentStop` hooks, `permissions.deny`, sandbox | The client, before the model sees anything | Loudly — tool call blocked, turn refused |
| 3 | GitHub required status checks, branch protection, CODEOWNERS | The forge | PR is structurally unmergeable |

Layer 2 is the innovation. `Stop` hook exit code 2 prevents the turn from ending and
re-injects stderr as the reason to keep working. Per the docs, **exit 2 blocks whether
or not you print JSON — even a JSON `permissionDecision: "allow"` cannot override it.**
That is the mechanical form of "you don't get to say done."

## 2. Roles

Deliberately few. Every role you add costs tokens (~4x per agent, ~15x for a full
multi-agent system) and adds a coordination failure mode.

| Role | Model | Context | Writes code? | Purpose |
|---|---|---|---|---|
| **Orchestrator** | Frontier | Main session | No | Owns the FSM, the work item, and integration. Never edits code directly. |
| **Implementer** | Frontier | Main session or worktree | **Yes — the only writer** | Spec → RED → GREEN → REFACTOR. |
| **Explorer** (0..N) | Cheap | Isolated, read-only | No | Parallel codebase reconnaissance. Returns a 1–2k token digest. Safe to fan out. |
| **Verifier** | **Different model** | Isolated, read-only | No | Adversarial. Graded on finding flaws, not on agreeing. Runs after gates are green. |
| **Integrator** | Human or lead | — | Merges only | Sole owner of shared manifests, lockfiles, and conflict resolution. |

Two hard constraints:

- **One writer per worktree.** Always. Parallel writers conflict; there is no
  coordination scheme that makes this safe enough to be worth it.
- **The Verifier must not be the Implementer.** A model checking its own work achieves
  roughly its own generation accuracy — it has no independent signal. Use a different
  model where you can; a different context is the minimum.

## 3. The task state machine

Task state lives in a **file on disk, not in the context window.** Context rot is real
and degrades recall well before the window fills; a compaction, crash, or session
restart must not lose the task's position.

```
INTAKE → SPEC → PLAN → RED → GREEN → REFACTOR → VERIFY → REVIEW → INTEGRATE → DONE
   │                    ↑______________│                             │
   │                    (gate failure, retry budget permitting)       │
   └──────────── any state ──→ BLOCKED ──→ (human decision) ──────────┘
```

| Transition | Exit criterion — all machine-checkable except where noted |
|---|---|
| INTAKE → SPEC | Work item created with an ID. Ambiguities enumerated, not guessed past. |
| SPEC → PLAN | Acceptance criteria written **as executable tests**. Assumption register has zero `open` entries. |
| PLAN → RED | Files/modules to touch declared. **Impact set computed from the code graph and recorded in the work item** ([09 §3.1](09-graph-engineering.md)) — not a courtesy, an exit criterion. Worktree + branch allocated. File scope recorded. |
| RED → GREEN | A new test exists, was run at pre-implementation HEAD, and **exited non-zero for an assertion reason** (not a collection/import error). |
| GREEN → REFACTOR | That test passes. No previously-passing test regressed. |
| REFACTOR → VERIFY | Complexity, duplication, and architecture fitness gates pass. Behavior unchanged. |
| VERIFY → REVIEW | Full gate ladder green (04). Evidence bundle emitted and schema-valid. |
| REVIEW → INTEGRATE | Adversarial Verifier returns pass. Zero unaddressed CRITICAL/HIGH findings. *(Model judgment — may raise the bar, never lower it.)* |
| INTEGRATE → *PR loop* | PR opened on a branch. Hands off to the **PR lifecycle loop** ([12](12-pr-lifecycle.md)) — CI-failure auto-fix, review-comment handling, risk tiering. That loop is stateless across CI runs, so its budget lives on the PR itself, not in a file. |
| *PR loop* → DONE | PR merged by the Integrator. CI green on the merge commit. Never merged by the agent that wrote it. |
| any → BLOCKED | Retry budget exhausted, thrash detected, escalation trigger hit, or an unresolved assumption. |

### Why RED must be proven, not asserted

This is Uncle Bob's first law of TDD made mechanical. The value of test-first collapses
if the test would have passed anyway. So the harness runs the new test at the
pre-implementation commit and requires a non-zero exit **for the right reason** — an
assertion failure, not an `ImportError`, which proves only that the file doesn't parse.

Known residual risk, stated honestly: a hook can prove a test fails, but not that it
fails for the *intended* reason. An agent can write a test that fails on a typo, then
"fix" the typo. This is why mutation testing (04) and the Verifier (§2) remain necessary
on top. No single gate is sufficient; the ladder is.

## 4. Topology: when to add agents

Default to **one agent**. Escalate only against this table.

| Topology | Use when | Avoid when | Cost | Main failure mode |
|---|---|---|---|---|
| **Single agent + tools** | Default. Task is scoped, path is mostly predictable. | Genuinely needs parallel independent exploration | 1x | Context rot on long sessions |
| **Pipeline** (spec→plan→impl→test→review) | Known-shape SDLC flow with clean handoff artifacts | Stages need to interleave or backtrack often | 1–2x | A bad SPEC silently corrupts everything downstream — needs exit-criteria gates |
| **Orchestrator + read-only Explorers** | Codebase recon across many files; context compression | Workers need to write | ~4x | Over-decomposition; duplicated work from vague instructions |
| **Generator–Critic** | A real verifier exists and criteria are checkable | No good verifier — the critic just invents plausible objections | 2–3x | Shared blind spot when both are the same model; infinite refinement without a stop condition |
| **Orchestrator + writing workers** | Rarely justified. Only with strict worktree + file-scope isolation. | Almost always | up to ~15x | Conflicting edits, lost updates |
| **Swarm / mesh** | Effectively never for coding | Always, for write tasks | Highest | No integration authority; non-deterministic and undebuggable |

**Read/write asymmetry is the governing rule.** Parallel readers cannot conflict, by
construction — fan out freely. Parallel writers conflict the moment they touch
overlapping files or a shared lockfile. If you must parallelize writes: one git worktree
per writer, declared non-overlapping file scope, and a single Integrator who owns all
shared manifests.

Give that rule a mechanical basis rather than a heuristic one: derive the task DAG from the
module dependency graph, and treat two subtasks as parallel-safe only when their write-sets
are disjoint *and* they create no dependency edge. If two subtasks in a wave want the same
file, the decomposition was wrong — re-split along the graph's real module boundaries
([09 §4](09-graph-engineering.md)).

### The escalation test

Before adding a second agent, answer: *what deterministic check would catch the failure
this agent is meant to catch?* If one exists, build the check instead. It will be
cheaper, faster, and more reliable.

### What the 2026 evidence actually says (corrected)

The first draft of this document argued "keep the topology simple" from the Dec 2024
Agentless result — a non-agentic pipeline matching agent frameworks on SWE-bench at ~10x
lower cost. That framing was too broad and rested on a 2024 benchmark that has since been
partly discredited ([01 §3](01-evidence-base.md)). The corrected version is narrower and
better supported:

1. **The Agentless finding still stands, scoped.** 2026 papers cite it approvingly rather
   than refuting it, and program-repair work (e.g. IssueExec, arXiv:2607.17286) builds *on
   top of* the pipeline — adding better localization and test-generation stages, not
   replacing it with an agent loop. Claim it only for **well-scoped, single-issue repo
   fixes**, where validated pipelines match agentic loops at a fraction of the cost.
2. **It does not generalize to open-ended work.** Long-horizon tasks — build a feature over
   six hours, debug a flaky CI failure of unknown cause, operate a codebase nobody scoped
   in advance — need agency a fixed pipeline cannot anticipate. That is where the whole
   commercial field went, and correctly so.
3. **But agency ≠ orchestration complexity, and this is the load-bearing distinction.**
   Anthropic's own March 2026 harness-engineering guidance for long-running agents
   independently arrives at this architecture: keep the loop simple (*"agents should work
   on only one feature at a time"*; the named failure mode is *"the agent tried to do too
   much at once"*), and spend the engineering effort on **validation gates** — a
   feature-list JSON tracking pass/fail, git commits as checkpoints, end-to-end browser
   tests, and an explicit rule that *"it is unacceptable to remove or edit tests."*
   Notably, their long-running coding harness uses a **sequential two-agent pattern**
   (initializer + coding agent sharing an identical harness), not parallel fan-out.
4. **Anthropic states the open question plainly:** it is still unclear whether a single
   general-purpose coding agent or a multi-agent architecture performs better *for coding
   specifically*. Anyone claiming otherwise is ahead of the evidence.

So the recommendation is unchanged but its justification is different: **simple loop,
heavy gates** is not "pipelines beat agents" — it is where production long-horizon agent
harnesses independently converged.

### On the 15x figure

Anthropic's ~4x (agent) and ~15x (multi-agent) token multipliers come from their June 2025
multi-agent *research* system post and **have not been revised as of August 2026**. Treat
them as a research-mode number rather than current coding-agent guidance — the same 2026
work above uses sequential agents precisely because coding tasks have tight
interdependencies that parallel fan-out handles badly. The economics still favor fan-out
only for high-value, genuinely parallelizable, read-heavy work.

## 5. Context strategy

Context is a degrading resource, not storage.

- **Disk is the source of truth.** Work-item state, assumption register, evidence
  bundle, and task log are files. The context window is a reconstructible cache.
- **Subagents are compression.** An Explorer can burn 50k tokens reading and return a
  2k-token digest. That is often the *primary* reason to spawn one, not parallelism.
- **Just-in-time over preloaded.** Pass file paths and identifiers; let the agent load
  on demand. Preload only what is cheap and certainly needed.
- **Compaction preserves decisions, discards tool output.** Keep architectural
  decisions and unresolved bugs; drop raw command output that is already summarized in
  the evidence bundle.
- **2026 platform mechanics worth using:** the Claude 5 family carries a 1M-token
  context at standard pricing with 128K max output, and a five-level `effort` control
  (low → max) rather than a binary thinking toggle — Opus 5 at lower effort can match
  Opus 4.8's max-effort coding results using fewer tokens, which materially changes the
  cost of an always-on loop. Claude Code's automatic compaction (`compact_20260112`) is
  near-instant and steerable via `/compact <focus>` or a Compact Instructions section in
  CLAUDE.md.
- **Watch the compaction gap:** root `CLAUDE.md` is re-read after `/compact`, but nested
  `CLAUDE.md` and path-scoped `.claude/rules/` are not automatically re-injected. Do not
  put load-bearing instructions only in a nested file. (Another reason gates belong in
  layer 2.)

## 6. Data flow

```
  Work item (JSON on disk)
        │
        ▼
  Implementer ──edits──► worktree
        │
        ▼
  Gate runner (harness-owned, agent cannot write to it)
        │  runs ladder, records command + exit code + output hash
        ▼
  Evidence bundle (JSON) ──► Stop hook reads it
        │                         │
        │                    all green? ──no──► exit 2, turn continues
        │                         │yes
        ▼                         ▼
  Verifier (different model, read-only) ──► findings
        │
        ▼
  PR + evidence bundle attached
        │
        ▼
  CI re-runs the entire ladder independently ──► required status checks
        │
        ▼
  Human review at escalation triggers ──► merge
```

> **CORRECTION (2026-08-28).** The paragraph below overclaimed and is kept only so the
> correction is legible. The gate runner and the evidence bundle do **not** live outside the
> agent's write scope. They live on the same machine, under the same user, and are protected
> by a hook that the agent's own runtime enforces. That is a convention inside the trust
> boundary, not a boundary. See `docs/15-premise-audit.md` and 5.1 below.

**The intent:** a `PreToolUse` hook denies `Write`/`Edit` targeting `.claude/hooks/**`,
`.claude/gates.json`, and CI configuration, so the agent cannot simply lower the bar — the
documented reward-hacking behavior.

**The reality:** a deny-list hook stops mistakes and casual shortcuts. It does not resist
intent. An agent running as your user can edit the hook, shadow the interpreter on `PATH`,
set `BASH_ENV`, or leave a background process that rewrites state between the check and the
run. Every guarantee in this section is worth exactly what the OS boundary underneath it is
worth, and by default there is none. Put the deciding check somewhere the agent holds no
credential — see 5.1.

## 7. Applying this to a real repo

Reference implementation from a real adoption: the repo already had the
adjudication layer largely built, which is the hard part.

| Architecture element | Existing equivalent |
|---|---|
| Gate ladder, tiered by cost | `.github/workflows/`: `commit-tests` → `integration-tests` → `e2e-tests` (PR only) → `release-tests` (main) |
| Fast gates | backend `make lint`, `make typecheck`, `make test-unit`; frontend `next lint`, `jest` |
| E2E with real stack | `e2e-tests.yml` — live FastAPI + Celery + Redis + Playwright, 40-min timeout, concurrency-grouped |
| Deny-list | `.claude/settings.json` `permissions.deny` already blocks `git push --force`, `git reset --hard`, pushes to main |
| Branch protection | `.github/BRANCH_PROTECTION.md` |

What is missing is **layer 2** — nothing currently stops the agent from declaring
success locally before any of that runs. That gap is exactly what `kit/hooks/gate.sh`
plus the `Stop` hook fills.
