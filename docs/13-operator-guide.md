# 13 — Operator's Guide

What you are actually running, what to expect from it, where it breaks, and how it wires
into Codex delegation.

---

## 1. The mental model

**Autonomy here is not the agent being smart. It is three loops being closed.**

The agent is assumed unreliable about its own completion — measurably so
([01 §1](01-evidence-base.md)). So nothing depends on its judgment about whether work is
finished. Three nested loops each have an exit condition the agent does not control.

```
┌─ HUMAN LOOP ─ escalation triggers, risk tiers, merge ─── you decide ──┐
│  ┌─ PR LOOP ─ push → CI → fix → push ──── budget lives on the PR ───┐ │
│  │  ┌─ BUILD LOOP ─ edit → gate → edit ── Stop hook / verify ────┐  │ │
│  │  │  agent works here                                          │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

| Loop | Closed by | Exhausts after |
|---|---|---|
| Build | `./bin/verify done` — exit 0 or you are not done | 6 blocked stop attempts → circuit breaker |
| PR | Labels + commit trailers on the PR itself | 3 fix attempts / 5 pushes → `autofix:blocked` |
| Human | Risk tier + escalation triggers | never — this is the terminal authority |

Each loop can only *hand up*, never bypass. The agent cannot mark its own gate green, the
PR loop cannot merge a critical-tier change, and nothing merges without a human.

**One sentence:** the system converts *"the agent says it's done"* into *"the agent is done,
or it is stuck loudly and specifically."* That is the whole product.

## 2. What to keep in mind

Operator discipline, in rough order of how often it bites.

1. **Verify the gate fires before you trust it.** Break a test on purpose, ask the agent to
   finish, watch it refuse. An unverified gate is worse than no gate, because you will rely
   on it. Re-do this whenever `gates.json` changes.
2. **Never let the agent edit its own governance.** `bin/verify`, `gates.json`, `hooks/**`,
   `.github/workflows/**`. This is the one rule that voids all the others if it slips.
3. **The cheat-flag rate is a thermostat, not an alarm.** Rising usually means the gates
   became unreasonable, not that the model got worse. Investigate the gate first.
4. **Watch CI-after-local-green.** Target <2%. Higher means your local ladder does not
   mirror CI, and the agent is learning that local green is meaningless.
5. **Keep the rules budget small.** Under ~3,000 always-on tokens, under ten imperatives.
   Compliance decays as `0.95^N` ([10 §4](10-tools-and-rules.md)).
6. **Watch review depth, not approval count.** Time-on-diff and comment rate falling is the
   rubber-stamping signal, and approvals will look fine while it happens.
7. **A wrong rule is worse than a missing rule.** It misleads confidently, in every harness,
   on every run.
8. **One writer per worktree.** Always. Parallel readers are free; parallel writers are a
   merge incident waiting to happen.

## 3. Expectations — what this does and does not buy

### What it reliably buys

| Effect | Basis |
|---|---|
| False "done" claims mostly stop reaching you | Gate is deterministic and agent-controlled paths to green are detected |
| Grader-gaming drops ~50x | 28.57% → 0.56% under active monitoring (arXiv:2606.26300) |
| Blast radius stops being a guess | Verified here: 17 real callers returned for one symbol across 8 files |
| Test time falls | 50–80% typical for impact-based selection |
| Failures become specific | Blocked reports carry command, exit code, what was tried |
| Irreversible actions need a human | Risk tiers + escalation triggers + deny-list |

### What it does not buy

**It does not make the code good.** It makes the code *pass the gates you wrote*. Those are
different, and the gap is measured: roughly half of test-passing agent patches were rejected
by real maintainers ([01 §3](01-evidence-base.md)) for broken adjacent functionality and
quality problems no harness checked.

**It does not settle whether you go faster.** METR's only clean RCT found a 19% slowdown on
early-2025 tools; their 2026 re-run collapsed under selection bias. Unresolved, wide error
bars ([01 §4](01-evidence-base.md)). What survived is the perception gap — developers
misjudged their own speed by ~40 points, favorably. So measure, don't feel.

**It does not reduce review burden by itself.** Production telemetry under high AI adoption:
incidents per PR +242.7%, review time +441%, and 31.3% of PRs merging with zero human
review. This architecture is a response to that, not immunity from it.

### Realistic first-90-days

| Metric | Target |
|---|---|
| First-pass gate rate | >70% |
| Rework loops per item | <2 |
| Escalation rate | <15% |
| CI-red-after-local-green | <2% |
| Same-signature PR repeats | 0 |
| Human-decision rate | <10% |

## 4. Limits — the honest list

| Limit | Consequence |
|---|---|
| **Green CI ≠ correct** | Verifier and human review still carry design quality. Nothing here replaces that. |
| **Codex enforcement is advisory** | No `Stop` hook. It follows `verify done` because `AGENTS.md` says so. CI is its real gate. |
| **RED proof can pass for the wrong reason** | A hook proves a test fails, not that it fails for the intended reason. Mutation testing narrows it; nothing closes it. |
| **Graph is blind to DI and reflection** | 106 `Depends()` sites here. Union callers with references, or under-report impact. |
| **Test selection can silently under-run** | Fails open on renames/config/migrations — re-check after any layout change. |
| **Detectors decay per model generation** | False-success detectors transfer at only AUROC 0.68–0.73 across generations. Recalibrate. |
| **Path-based risk tiering misses relocated sensitivity** | Verified: `share_service.py` handles `auth_token` and rates *standard*. |
| **Reward hacking is not eliminable by better tests** | Held-out gap grows ~28 points per 10× LOC. Monitoring helps; it does not close it. |
| **Costs more per task** | More tokens, more CI minutes, more wall-clock. Track cost per merged item. |
| **Two harnesses, two rule files** | `AGENTS.md` is shared. Anything Codex needs that lives only in `CLAUDE.md` is a portability bug. |

## 5. Codex delegation

### Already in place

Your `~/.codex/config.toml` has `codegraph` wired as an MCP server, so **Codex has graph
access natively** — not just via the CLI. Model `gpt-5.6-terra`,
`approvals_reviewer = "auto_review"`.

That last setting matters: Codex already routes approvals through automatic review with a
workspace-write sandbox. It is a weaker gate than a `Stop` hook, but it is not nothing.

### Install the slash commands

```bash
mkdir -p ~/.codex/prompts
cp docs/autonomous-agent-architecture/kit/codex-prompts/*.md ~/.codex/prompts/
```

Gives `/gate`, `/blast`, `/review` inside any Codex session.

| Command | Does |
|---|---|
| `/gate` | Runs `verify preflight` + `verify done`, reports exact command and exit code, refuses to paraphrase a pass |
| `/blast <symbol>` | Impact set before editing, with the DI caveat baked in; reports and waits |
| `/review` | Adversarial verification against the evidence bundle; refutation-framed, cannot clear a red gate |

### Delegating a task

```bash
# scoped, non-interactive, sandboxed
codex exec -C ../wt-auth --sandbox workspace-write \
  "Reject null email at registration. Follow AGENTS.md. \
   Run ./bin/verify done before claiming completion."
```

**Force a machine-checkable result** rather than trusting prose — this is the single most
valuable Codex flag for this architecture:

```bash
codex exec --output-schema docs/autonomous-agent-architecture/kit/schemas/evidence.schema.json \
  --json "Fix the failing pricing test. Run ./bin/verify done."
```

The schema requires `done`, `verify_command`, and `verify_exit_code`. The agent cannot
return `done: true` without also returning the exit code that justifies it — the evidence
bundle contract from [03](03-definition-of-done.md), enforced at the API boundary instead of
by a hook. This is how you close the enforcement gap Codex has.

### The cross-harness play

Different model families for author and verifier. Same-lineage judges share blind spots, and
self-verification sits *below* generation accuracy.

| Role | Runs on | Why |
|---|---|---|
| Implementer | Claude Code | `Stop` hook blocks it while working — strongest enforcement |
| Adversarial verifier | `codex review` or `/review` on `gpt-5.6-terra` | Different family, no shared blind spot |
| Adjudicator | CI | Outside both trust boundaries |

This is the cheapest real quality win available from running both, and it costs one extra
command.

### Handoff between harnesses

State lives in files, not context. A Codex session picks up where Claude Code stopped
because both read:

| File | Carries |
|---|---|
| `AGENTS.md` | The contract both obey |
| `.claude/work/<id>.json` | Task state, blast radius, file scope, attempts |
| `.claude/evidence/latest.json` | What ran, exit codes, output hashes. **Self-reported** — written by the process under test, on its own machine. A hint, not a receipt (`"verified_by": "producer"`). |
| `.claude/evidence/assumptions.jsonl` | Open questions — non-empty blocks completion |
| The PR itself | Labels, attempt counters, risk tier |

## 6. Do this first

1. **Fix `AGENTS.md`** — it says "Flask backend"; it is FastAPI. Wrong rule, both harnesses,
   every run. Free.
2. **Point `gates.json` at the real targets** — `make lint`, `make typecheck`,
   `make test-unit`, `next lint`, `jest`.
3. **Wire the `Stop` hook**, then break a test and confirm both harnesses refuse.
4. **Install the Codex prompts** and delegate one real task with `--output-schema`.
5. **Cut the rules budget** from ~4,200 tokens / 28 imperatives to under ten.

Everything after that — mutation testing, risk tiering, the PR loop — is refinement on a
loop that already closes.
