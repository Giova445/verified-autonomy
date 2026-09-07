# SDLC playbook — stage map

Which playbook stage each artifact in this repo implements, which enforcement layer it lands
in, and the stages that are **not** implemented, with the reason each one is not.

Written 2026-09-03.

---

## Where the stage numbering comes from — read this first

**No document in this repository defines the stage numbering.** `grep -rn "Stage 5c" docs/
README.md skills/` returns nothing but this file. The numbering arrived with the brief that
commissioned these artifacts.

Four labels are nevertheless **attested inside the repo**, because sibling artifacts written
in the same change set carry them in their own headers:

| Label | Attested by | Line |
|---|---|---|
| **4b** | [`evals/model.py`](../evals/model.py), [`evals/lib.py`](../evals/lib.py) | "An EVAL is a task+check pair, in the Stage 4b sense" |
| **5a** | [`REVIEW.md`](../REVIEW.md) | "REVIEW.md — Stage 5a: PR review policy" |
| **5c** | the brief only | "deployment via MCP, tiered per-environment autonomy" |
| **6a** | [`bands.yaml`](../bands.yaml), [`monitoring/detect.py`](../monitoring/detect.py) | "Stage 6a control bands" |

Everything else below — the labels 1, 2, 3, 4 and 5b — is **inferred by position and
elimination**, and 5b is the weakest of them: nothing in or out of the repo tells me what
letter adjudication carries, only that 5a is review and 5c is deploy. Where a section's
label is inferred it says so. The artifact rows are correct regardless of what the labels
turn out to be.

The nearest in-repo equivalents to a stage list are two state machines, cited per stage:

- [`02-architecture.md`](02-architecture.md) §3 — build FSM:
  `INTAKE → SPEC → PLAN → RED → GREEN → REFACTOR → VERIFY → REVIEW → INTEGRATE → DONE`
- [`12-pr-lifecycle.md`](12-pr-lifecycle.md) §3 — PR FSM:
  `PR_OPEN → CI_RUNNING → CI_GREEN → REVIEW_WAIT → APPROVED → MERGED`

## Layer, throughout

From [`02-architecture.md`](02-architecture.md) §1:

| Layer | Meaning | Agent can bypass? |
|---|---|---|
| **1** | Persuasion — skills, templates, `CLAUDE.md` | Yes, trivially |
| **2** | Enforcement — hooks, permissions, sandbox | No |
| **3** | Adjudication — CI, branch protection, review | No |

A row tagged layer 1 is a request. Reading it as a guarantee is the mistake this table is
arranged to prevent.

---

## The map

### Stage 1 — Intent · *label inferred*

| | |
|---|---|
| **Artifact** | [`intent/templates/intent.md`](../intent/templates/intent.md) — problem, proposed outcome, affected users/systems, constraints, open questions |
| **Also** | [`skills/brainstorming`](../skills/brainstorming/SKILL.md) — path classification, and the "no code before approval" gate |
| **Layer** | **1.** Nothing reads the file. `approved_by:` is text an agent can write. |
| **Nearest layer 2** | `bin/verify preflight` refuses while `.claude/evidence/assumptions.jsonl` holds any `"status": "open"` entry. That is the assumption register, not the intent — related, not the same. |
| **Verify** | `bash intent/check-chain.sh <chain-dir>` — sections present, not sections true |
| **FSM** | `INTAKE` |

Until this change set, `intent.md` did not exist in any form. Stage 1 was a conversation.

### Stage 2 — Spec · *label inferred*

| | |
|---|---|
| **Artifact** | [`intent/templates/spec.md`](../intent/templates/spec.md) — requirements, design, policy validation, flagged concerns |
| **And** | [`templates/spec.md`](../templates/spec.md), the older and longer one `skills/brainstorming` names. See the duplication note below. |
| **Layer** | **1** for the document; **2** for one property of it |
| **Layer 2 part** | `bin/ambiguity` answers a narrower, mechanically decidable question — *which decisions does this diff make that the spec never mentions?* Every new branch, default, caught error and magic constant is a decision; if its concept appears nowhere in the spec, nobody recorded the choice. `AG_STRICT=1` makes findings blocking. |
| **Verify** | `bash bin/ambiguity selftest` → 12 checks, exit 0 |
| **FSM** | `SPEC`; `SPEC → PLAN` requires acceptance criteria written as executable tests |

`bin/ambiguity` is the only mechanism here that reads a spec at all, and it reads it as a bag
of words to compare a diff against. It deliberately contains no lexicon of "vague words" —
that would be someone's taste dressed as a measurement.

### Stage 3 — Plan · *label inferred*

| | |
|---|---|
| **Artifact** | [`intent/templates/plan.md`](../intent/templates/plan.md) — files changing, work order, tests needed, risks, proof statements |
| **And** | [`templates/plan.md`](../templates/plan.md), [`skills/writing-plans`](../skills/writing-plans/SKILL.md), [`skills/orchestrating`](../skills/orchestrating/SKILL.md) |
| **Layer** | **2 when invoked, 1 otherwise.** The first stage whose mechanisms *refuse* things — but every one of them is opt-in. See the row below before reading this as a gate. |
| **Wiring, measured** | `grep -rl 'ledger\|worktree-guard' hooks/ kit/hooks/ .github/workflows/ .claude/settings.json` returns **nothing** — only `selftest.sh` names them, and it runs their selftests, not the tools on real work. Nothing requires a ledger to exist before a branch does, and nothing requires a scope claim before a write. An agent that never runs these commands is never refused by them. That is a weaker property than Stage 4's `Stop` hook, which fires on every turn wherever it is registered, and the two should not share the word "enforced" unqualified. |
| **Mechanism** | `bin/ledger init <id> --plan <plan.md>` parses `- [ ]` checkboxes into numbered tasks and **refuses a plan with none** — an empty ledger would report "nothing to do" and certify completion. `ledger done` refuses a task with no evidence artifact. Corrupt state is exit 3, never a silent re-init. |
| **Mechanism** | `bin/worktree-guard claim <id> --scope '<glob>'` — exit 2 if another writer holds the path. One writer per worktree, enforced rather than asked. |
| **Mechanism** | `bin/escalate advise <id> <n>` — fix-loop budget; stops early when a failure *signature* repeats. |
| **Verify** | `bash bin/ledger selftest` (43), `bash bin/worktree-guard selftest` (39), `bash bin/escalate selftest` (25), `bash tests/orchestration-test.sh` (80) |
| **FSM** | `PLAN → RED` requires the impact set computed from the code graph, and file scope recorded |

This is the hop where the chain stops being paperwork: the plan's work order is **parsed**,
not read. A plan whose tasks are prose produces no ledger and the run has nowhere to start.

### Stage 4 — Implement and gate · *label inferred*

| | |
|---|---|
| **Artifacts** | [`skills/test-driven-development`](../skills/test-driven-development/SKILL.md), [`skills/systematic-debugging`](../skills/systematic-debugging/SKILL.md), [`skills/using-worktrees`](../skills/using-worktrees/SKILL.md), [`skills/gate`](../skills/gate/SKILL.md), `bin/verify` |
| **Layer** | **2** |
| **Mechanism** | `hooks/deny-dangerous.sh` on `PreToolUse` — blocks force-push, `reset --hard`, self-merge, credential reads, **and edits to the gate config itself** |
| **Mechanism** | `hooks/scan-diff-cheats.sh` — skipped tests, deleted assertions, `\|\| true`, retry-to-green, snapshot re-recording |
| **Mechanism** | `bin/test-delta` — production code changed, so tests must have **grown**. Built because a gate enforcing tests *pass* never enforced tests *exist*, and reported ALL GATES GREEN over four pre-existing tests. |
| **Mechanism** | `bin/mutate-changed`, `bin/holdout` — mutation on the diff; a suite in a directory the agent cannot reach |
| **Mechanism** | `hooks/stop-gate.sh` on `Stop`/`SubagentStop` — **exit 2 while red**, so the turn does not end and stderr returns as the reason. Exit 2 blocks even against a JSON `permissionDecision: "allow"`. Fails closed: an unparseable `.claude/gates.json` is `REFUSING TO CERTIFY`; a stubbed `bin/verify` is detected. |
| **Verify** | `bash selftest.sh` → 31 checks, exit 0 (~40s) |
| **FSM** | `RED → GREEN → REFACTOR → VERIFY` |

Whether the playbook puts the gate ladder in stage 4 or stage 5 is not knowable from here.
It is grouped with implementation because the `Stop` hook fires inside the build loop, not
after it.

### Stage 4b — Configuration evals · *label attested*

| | |
|---|---|
| **Artifact** | [`evals/`](../evals/) — `model.py`, `lib.py`, `evals_config.py`, `evals_suites.py`, `evals_hooks.py`, `evals_ci.py`, `expected.json` |
| **Owner** | Concurrent work by another agent in this same change set |
| **Verified by this document** | **Presence and self-description only.** The files exist and `evals/model.py` states "An EVAL is a task+check pair, in the Stage 4b sense". **I did not run them and make no claim about whether they pass.** |

### Stage 5a — Review · *label attested*

| | |
|---|---|
| **Artifact** | [`REVIEW.md`](../REVIEW.md) — PR review policy, written as concurrent work by another agent |
| **And** | [`skills/requesting-review`](../skills/requesting-review/SKILL.md), [`skills/finishing-a-branch`](../skills/finishing-a-branch/SKILL.md), [`agents/verifier.md`](../agents/verifier.md) |
| **Layer** | **1** — model judgment. `REVIEW.md` states the boundary itself: a review "cannot clear a red gate", findings never approve and never block, and merge authority sits with a human code owner under branch protection and CODEOWNERS. |
| **Verified by this document** | Presence, and the quoted lines above, read from the file. Nothing more. |
| **FSM** | `REVIEW`, and `REVIEW_WAIT → APPROVED` in the PR FSM |

### Stage 5b — Adjudication · *label INFERRED BY ELIMINATION — the least certain label here*

| | |
|---|---|
| **Artifact** | [`.github/workflows/verify.yml`](../.github/workflows/verify.yml) — three jobs: `structure`, `selftest`, `bench` |
| **Layer** | **3** |
| **Mechanism** | CI re-runs every gate with `permissions: contents: read` — **no write scope, so CI cannot edit the guardrails it runs** |
| **Mechanism** | Every control runs **before** the check it belongs to. A validator that has silently stopped discriminating passes a clean tree exactly like a working one, so controls-after-checks would let the workflow report green over a suite that had stopped testing anything. |
| **Mechanism** | The pin gate runs against the **PR's own diff**, not the tree — a tree scan reports every pre-existing offence on every run, which trains people to ignore it |
| **Verify** | read `.github/workflows/verify.yml`; the ordering is the load-bearing part |
| **FSM** | `CI_RUNNING → CI_GREEN`, `APPROVED → MERGED` |

I am confident about the artifact and unconfident about the number. If the playbook's 5b is
something else, this section is still the repo's adjudication layer; only its heading is wrong.

### Stage 5c — Deployment via MCP, tiered per-environment autonomy

**NOT IMPLEMENTED. Not implementable from inside this repository.** See below.

### Stage 6a — Operate and monitor · *label attested*

| | |
|---|---|
| **Artifact** | [`bands.yaml`](../bands.yaml) + [`monitoring/`](../monitoring/) — `detect.py`, `collect.py`, `bandconf.py`, `yamlsub.py`, `selftest.py`, `history/`, `intents/`, `invocations/`. Concurrent work by another agent. |
| **Self-described mechanism** | A deterministic detector watches a metric against a rolling baseline: ≥1σ logs, ≥2σ invokes Claude **read-only** to write a diagnosis as an `intent.md`, ≥3σ permits action via PR or a pre-approved runbook. Below `min_samples` it **refuses to return a verdict** rather than firing on noise. |
| **Verified by this document** | **Presence and self-description only. I did not run `monitoring/selftest.py`** and make no claim about whether its controls pass. |
| **Also** | [`benchmark/manifest/gate-manifest.json`](../benchmark/manifest/gate-manifest.json) — 30 gate rows with status, `verified_on`, pinned versions, and `trigger_rules` naming which subsystem changes invalidate which gate |
| **Layer 2 part** | `benchmark/structure/validate.py` checks manifest↔script correspondence in **both** directions: a row's script must exist, the script's own `# gate:` header must name the row claiming it, and a verification script no row claims is flagged as an orphan. Unbacked rows and dead links are ratcheted against a recorded baseline. |
| **Not implemented** | Nothing collects the [`08-adoption-playbook.md`](08-adoption-playbook.md) §3 metrics — first-pass gate rate, rework loops, CI-after-local-green failure rate. No telemetry, no run history for those. That table is a specification of what to measure. |
| **Verify** | `python3 benchmark/structure/validate.py --self-test`, then `python3 benchmark/structure/validate.py` |

Note the interesting seam: `bands.yaml`'s 2σ tier writes its diagnosis **as an `intent.md`**,
which feeds Stage 1. That closes the loop, and it is the one place a stage boundary in this
repo is crossed by an artifact rather than by a person.

---

## Not implemented, and why

### Stage 5c — deployment via MCP, tiered per-environment autonomy

**Not implementable from inside this repository, at any level of effort.**

This repo is a plugin. It has no deployment target, no environments, no infrastructure and no
MCP server that deploys anything. There is nothing here to promote from staging to production,
so "tiered per-environment autonomy" has no environments to tier over. A stub printing
`deploy: ok` would be a fabricated receipt of exactly the kind the rest of this repo exists to
detect — and worse, one that would pass CI.

What exists instead, and what it actually is:

| Artifact | What it is |
|---|---|
| [`07-safety-and-autonomy-levels.md`](07-safety-and-autonomy-levels.md) §1 | The L0–L4 autonomy model, written. Prose. No code reads a level and nothing assigns one. |
| [`kit/governance.yaml`](../kit/governance.yaml) | Risk tiers with per-tier `autonomy:` values (`none` / `fix_only` / `fix_and_request_review`), `escalate_always`, PR-loop budgets. **Read by no script in this repo** — `grep -rl governance bin/ kit/bin/ hooks/ kit/hooks/` returns nothing. |
| [`12-pr-lifecycle.md`](12-pr-lifecycle.md) §5 | The design for path-based risk tiering driving per-PR autonomy. A design, not an implementation. |
| [`bands.yaml`](../bands.yaml) | Tiers a *monitoring* response by sigma, not a *deployment* by environment. Adjacent, not the same thing. Its 3σ tier is the only place in the repo where "Claude may act" is gated by a threshold at all. |

The honest status: **the policy for tiered autonomy is written and unenforced.** The gap
between `governance.yaml` and any code that reads it is the whole of Stage 5c minus the
deployment substrate, and closing it needs a substrate that does not exist here. Anyone wiring
this into a real pipeline should treat `governance.yaml` as a specification to implement
against, not as a control that is running.

### The managed-settings admin path

**BLOCKED-PENDING-CREDENTIALS.** Recorded in full at
[`benchmark/manifest/BLOCKED.md`](../benchmark/manifest/BLOCKED.md).

Gate B1 asks whether a child agent can grant itself capability its parent withheld, enforced
by a layer the agent does not control. The only layer with that property is managed settings
at `/Library/Application Support/ClaudeCode/managed-settings.json`. The directory does not
exist on the measurement machine and creating it requires admin.

Both lower-privilege routes were measured and both fail, so a substitute would only repeat a
known result:

| Route | Result |
|---|---|
| project-scoped `disableBypassPermissionsMode` | **does not bind** — control and treatment both started in bypass mode |
| `CLAUDE_CODE_MANAGED_SETTINGS_PATH` env var | **not honoured** — a managed deny for `Bash(echo:*)` still ran, while the identical rule in project settings blocked (positive control) |

The env-var result cuts favourably: it is not an escape hatch, so an agent that can set
environment variables cannot redirect the policy file to one it controls.

Unblocking requires a human with admin to write that file and re-run the probe. It needs a
password, and it is not something an agent should do on an operator's behalf. That is a
standing limitation, not a task waiting for a spare afternoon.

### Approval gating on Stages 1–3

The `approved_by:` frontmatter field in all three templates is **layer 1 and nothing else**.
No hook reads it, no CI job checks it, and `bin/verify` does not know these files exist. An
agent can write `approved_by: alice` in the same commit that writes the plan.

What is real is the git record: commit author, author and commit timestamps, and the PR review
event on the far side of the trust boundary. See [`intent/README.md`](../intent/README.md),
"What git records, and why that is the audit trail".

Making the frontmatter mechanical is possible — a `PreToolUse` deny on branch creation without
an approved plan, or a CI job matching `approved_by:` against the PR's reviewers — and neither
is built. Saying "the chain requires approval" today describes a convention.

### Two competing template pairs

`templates/spec.md` + `templates/plan.md` (named by `skills/brainstorming` and
`skills/writing-plans`) and `intent/templates/spec.md` + `intent/templates/plan.md` (named by
`intent/check-chain.sh`) have different field sets, and neither is a superset of the other.

Two standards for one document is a drift hazard. Reconciling them means editing `templates/`
and two skill files, outside the scope of the change that created `intent/`. **Recorded as an
open defect, not fixed.** Details in [`intent/README.md`](../intent/README.md), "Two spec
templates".

---

## Not wired up yet

`intent/check-chain.sh` runs and passes 16 controls, but nothing runs it for you. `selftest.sh`
and `.github/workflows/verify.yml` belong to other work in this change set, so the wiring is
written here rather than applied.

In `selftest.sh`, in the `structure & supply chain` block:

```bash
suite "intent chain checker"     bash "$PLUGIN/intent/check-chain.sh" selftest
```

In `.github/workflows/verify.yml`, in the `structure` job, controls before the check:

```yaml
      - name: Intent chain checker — CONTROLS FIRST
        run: bash intent/check-chain.sh selftest

      - name: Intent chain checker
        run: bash intent/check-chain.sh intent/templates intent/examples/*/
```

Until those land, the checker is a command a human remembers to run — the honour system this
repo's own CI was introduced to replace.

## Verification

Every command below was run in this repo on 2026-09-03 at the stated result.

| Command | Result |
|---|---|
| `bash selftest.sh` | exit 0 — 31 checks |
| `bash intent/check-chain.sh selftest` | exit 0 — 16 checks |
| `bash intent/check-chain.sh intent/templates intent/examples/2026-09-01-mcp-collision-detector` | exit 0 — `CHAIN OK` |
| `python3 benchmark/structure/validate.py` | exit 0 — frontmatter 0, links 8 (baseline, unchanged by this change), manifest 0, duplicates 0 |
| `python3 benchmark/verification/mcp/collision-detect.py --self-test` | exit 0 — 6 checks |
| `bash bin/ambiguity selftest` | exit 0 — 12 checks |
| `bash bin/ledger init <id> --plan intent/templates/plan.md` | exit 0 — 3 tasks parsed |
| `grep -rl governance bin/ kit/bin/ hooks/ kit/hooks/` | no output — `governance.yaml` is read by nothing |
| `grep -rn "Stage 5c" docs/ README.md skills/` | matches **this file only** — the numbering is defined nowhere else in the repo |

**Not run, and therefore not claimed:** `evals/`, `monitoring/selftest.py`, and any check
inside `REVIEW.md`. Those are concurrent work by other agents; this document verified that the
files exist and quoted what they say about themselves, which is not the same as verifying they
work.
