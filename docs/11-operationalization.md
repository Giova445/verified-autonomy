# 11 — Operationalization

How this runs, given agents dispatched from **both Codex and Claude Code**.

---

## 1. The constraint that determines the design

**Hooks are Claude Code only. Codex has no `Stop` hook.**

If enforcement lives in a hook, half your fleet is ungoverned. So enforcement moves into a
plain CLI, and every harness becomes a thin adapter over it.

```
                    ┌───────────────────────┐
                    │      ./bin/verify     │   ← single source of truth
                    │   reads gates.json    │      gate defs live here, once
                    └───────────┬───────────┘
             ┌──────────────────┼──────────────────┐
             │                  │                  │
     Claude Code            Codex                 CI
     Stop hook:          AGENTS.md:          workflow:
     verify done --hook   verify done        verify done
     (exit 2 blocks)      (exit 1 = not      (exit 1 fails
                           done)              the build)
```

Three properties this buys:

1. **No definition drift.** Local and CI cannot disagree about what "done" means; they run
   the same file.
2. **Harness-portable.** Adding Cursor, Aider, or a cron runner is one more caller.
3. **CI stays the backstop.** Codex's compliance is softer than a hook (it's an instruction,
   not a block) — CI catches what the instruction misses.

## 2. Capability matrix

| Capability | Claude Code | Codex | CI |
|---|---|---|---|
| Block a tool call before it runs | ✅ `PreToolUse` exit 2 | ❌ sandbox/approvals only | n/a |
| Refuse to let the turn end | ✅ `Stop` exit 2 | ❌ — instruction only | n/a |
| Read `AGENTS.md` | ✅ | ✅ | n/a |
| Path-scoped rules | ✅ `.claude/rules` `paths:` | ⚠️ AGENTS.md is global | n/a |
| Graph access | MCP + CLI | CLI (`codegraph`) | CLI |
| Non-interactive dispatch | `claude -p` | `codex exec` | native |
| Independent re-verification | ❌ same trust boundary | ❌ same trust boundary | ✅ |

**Read this honestly:** Codex enforcement is weaker. It follows `./bin/verify done` because
`AGENTS.md` says to, not because anything stops it. That is exactly the layer-1 persuasion
problem from [02](02-architecture.md). Mitigations: keep `AGENTS.md` short so the rule
survives the compliance budget, and treat CI as the real gate for Codex-authored work.

## 3. Install

```bash
# 1. spine
mkdir -p bin .claude/hooks .claude/agents
cp docs/autonomous-agent-architecture/kit/bin/verify        bin/
cp docs/autonomous-agent-architecture/kit/hooks/*.sh        .claude/hooks/
cp docs/autonomous-agent-architecture/kit/agents/verifier.md .claude/agents/
cp docs/autonomous-agent-architecture/kit/gates.json        .claude/gates.json
chmod +x bin/verify .claude/hooks/*.sh

# 2. portable rules — merge into your existing AGENTS.md, don't clobber it
cat docs/autonomous-agent-architecture/kit/AGENTS.md.template

# 3. Claude Code adapter
#    merge kit/adapters/claude-code.settings.json into .claude/settings.json

# 4. CI adapter
cp docs/autonomous-agent-architecture/kit/ci/verify.yml .github/workflows/

# 5. graph
codegraph init -i && codegraph index

# 6. ignore generated state
printf '.claude/evidence/\n.claude/.gate-attempts\n' >> .gitignore
```

Then edit `.claude/gates.json` so every command passes on a clean checkout **today**.
Aspirational gates get disabled within a week.

### Verify the enforcement actually fires

```bash
./bin/verify done          # expect exit 1 on a red gate
./bin/verify done --hook   # expect exit 2
```

Then the real test: break a test on purpose, ask each harness to finish, watch it refuse.
**An unverified gate is worse than no gate, because you will trust it.**

## 4. Dispatch patterns

### Claude Code

```bash
# interactive, gates enforced by the Stop hook
claude

# headless, one task — same hook fires
claude -p "Fix the null-email crash in user registration. Follow AGENTS.md." \
       --output-format stream-json

# isolated worktree for parallel work (one writer per worktree, always)
git worktree add ../wt-auth -b feat/auth && cd ../wt-auth && claude
```

Subagents: dispatch **read-only Explorers** freely — they cannot conflict. Dispatch exactly
**one writer** per worktree. The `verifier` agent runs after gates are green, on a different
model than the implementer.

### Codex

```bash
# non-interactive
codex exec "Fix the null-email crash in user registration. \
Run ./bin/verify done before claiming completion. Do not edit gates."

# independent review pass — different model family than the author
codex review

# apply a produced diff to the working tree
codex apply
```

Because Codex will not be blocked by a hook, put the verify instruction in the **prompt** as
well as `AGENTS.md`. Redundancy is cheap; a missed gate is not.

### The cross-harness play worth doing

Use **different model families for author and verifier.** Same-lineage judges show
self-enhancement bias, and self-verification sits below generation accuracy
([01 §1](01-evidence-base.md)). So:

| Role | Harness |
|---|---|
| Implementer | Claude Code (hook-enforced gates while it works) |
| Adversarial verifier | `codex review` (different model family, no shared blind spot) |
| Adjudicator | CI (outside both trust boundaries) |

This is the cheapest real win available from running both.

## 5. Portable work item

The handoff format between harnesses. One file per task at
`.claude/work/<task-id>.json`, checked in with the branch, so a Codex session can pick up
where a Claude Code session stopped.

```json
{
  "id": "GRF-142",
  "state": "PLAN",
  "spec": {
    "description": "Reject null email at registration",
    "acceptance_criteria": ["POST /register with email=null returns 422"],
    "out_of_scope": ["email verification flow"]
  },
  "blast_radius": {
    "queried": "register_user",
    "callers": ["routers/auth.py:88", "services/onboarding.py:23"],
    "note": "106 Depends() sites repo-wide; DI edges under-reported by callers alone"
  },
  "ownership": { "worktree": "../wt-auth", "branch": "feat/reject-null-email",
                 "file_scope": ["src/api/routers/auth.py", "tests/auth/**"] },
  "attempts": { "count": 0, "max": 3 },
  "assumptions": [],
  "evidence": ".claude/evidence/latest.json"
}
```

`file_scope` is the parallel-safety contract. Two work items may run concurrently only when
their scopes are disjoint and the module graph shows no edge between them
([09 §4](09-graph-engineering.md)).

## 6. Rollout order

Do not install everything at once.

| Week | Do | Done when |
|---|---|---|
| **1** | `bin/verify` + `gates.json` + Stop hook + deny-list | A deliberately broken test makes both harnesses refuse to finish |
| **2** | `AGENTS.md` rewrite to <10 imperatives; cheat scanner; deny guardrail edits | `scan-diff-cheats.sh` flags a planted `.skip` |
| **3** | `codegraph init`; blast radius as a PLAN exit criterion; graph-scoped test selection | Test time drops measurably; selection fails open on renames |
| **4** | CI runs the same `verify`; branch protection; CODEOWNERS | CI-after-local-green failure rate < 2% |
| **5+** | Verifier on a different model family; mutation testing; metrics | First-pass gate rate > 70% |

## 7. First three things, for this repo specifically

1. **Fix `AGENTS.md`.** It says *"Flask backend"*; the backend is FastAPI
   (`fastapi>=0.115`). A wrong rule actively misleads every agent in both harnesses. This
   is the cheapest fix on the list and it is currently costing you on every run.
2. **Cut the always-on instruction budget.** ~4,200 tokens and 28 imperatives across
   `CLAUDE.md` + `~/.claude/rules/common/` puts `0.95^28 ≈ 24%`, above the ~3,000-token
   dilution threshold. Move enforceable items into `bin/verify` and the deny hook; scope the
   rest with `paths:` at **project** level (user-level scoping is unreliable).
3. **Wire `bin/verify` to the real Make targets.** The backend already has
   `make lint` / `make typecheck` / `make test-unit`; the frontend has `next lint`, `jest`,
   `playwright`. The four CI workflows already implement the tiering. `gates.json` mostly
   just needs to name what exists.

## 8. What stays hard

- **Codex compliance is advisory.** No hook. CI is the real gate for its output.
- **Test selection can silently under-run.** Fail open on renames, config, and migrations —
  already implemented in `verify tests`, but re-check it whenever the repo layout changes.
- **The graph misses DI and reflection.** 106 `Depends()` sites here. Union callers with
  references before trusting a blast radius on FastAPI routes.
- **Two harnesses, two rule files.** `AGENTS.md` is the shared one. Anything in
  `CLAUDE.md` that Codex also needs is a portability bug.
