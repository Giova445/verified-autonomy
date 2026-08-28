# Verified Autonomy

**A complete architecture for autonomous coding agents** — 13 workflow skills, mechanical
enforcement, and an adjudication layer. The agent cannot claim completion while gates are
red: a `Stop` hook exits 2 and refuses the turn.

Skills libraries ask the model to be disciplined. This one asks *and* removes the option
where removing it is possible.

---

## Why

An agent that writes code and also decides whether that code is finished is not a reliable
judge of it. Across frontier models in 2026, **45–48% of failing agent trajectories reported
success — falling to 3% when an independent verifier was present** (arXiv:2606.09863).

That delta is the argument. Not that agents scheme, but that an unverified self-report is
wrong about half the time when it matters. No LLM-judge configuration tested detected it
above AUROC 0.65, while a cheap TF-IDF detector reached 0.83–0.95 — deterministic checks
beat model judgment on exactly this question.

Two findings sharpen it. Reasoning does not help: the *highest* false-success rate measured
(79%) came from a reasoning model whose traces "rationalize completion rather than verify
environment state." And self-verification performs *below* generation accuracy — 41.9% vs
54.7% — with the gap widening as capability grows (ICML 2026).

### What this is not

We ran 51 controlled trials attempting to elicit active gate-cheating — a test contradicting
its spec, an editable gate config, a 50%-flaky race with a one-line `@flaky` escape — and
observed **zero instances**. That is consistent with the published 0.7–4% baseline for
unambiguous, inference-time, well-scaffolded conditions; reward hacking is primarily a
*training-time* artifact (0.7–4% pre-RL → 70%+ after ~50 RL steps against the grader).

**So these gates defend against an agent that sincerely believes it is done, not against an
adversary.** Anti-cheating enforcement is not a claim this project can support. Independent
verification is. See [docs/01-evidence-base.md](docs/01-evidence-base.md) §1.4–1.7 for the
null result, its statistical bounds (95% CI upper bound 5.6% pooled, 26–35% per condition),
and an adversarial review of its defects.

## The three layers

| Layer | Mechanism | Can the agent bypass it? |
|---|---|---|
| 1 — Persuasion | `CLAUDE.md`, `AGENTS.md`, skills | Yes, trivially |
| 2 — **Enforcement** | **Hooks, permissions, sandbox** | **No — client-side, pre-model** |
| 3 — Adjudication | CI, branch protection, review | No — outside the trust boundary |

Anthropic's own docs draw the line: *"Settings rules are enforced by the client regardless
of what Claude decides to do. CLAUDE.md instructions shape Claude's behavior but are not a
hard enforcement layer."*

This plugin is layer 2.

## Install

```
/plugin marketplace add Giova445/verified-autonomy
/plugin install verified-autonomy@verified-autonomy-marketplace
```

Then, in any repo you want gated:

```bash
bash kit/install.sh          # detects your stack, writes .claude/gates.json
bash selftest.sh             # DO NOT SKIP — proves the gate actually fires
```

**Safe to install globally.** With no `.claude/gates.json` in a repo, the hooks exit 0 and
inject nothing. Enforcement is opt-in per project.

## What it does

| Hook | Behavior |
|---|---|
| `Stop` / `SubagentStop` | Runs the gate ladder. **Exit 2 while red** — the turn does not end, and stderr returns as the reason. |
| `PreToolUse` | Blocks force-push, `reset --hard`, destructive SQL, self-merge, credential reads — and **edits to the gate config itself**. |
| `SessionStart` | Injects the contract, only in repos that opted in. |

Plus: a cheat-scanner that diffs for the documented ways agents fake green (skipped tests,
deleted assertions, `|| true`, retry-to-green, snapshot re-recording), a never-worse-than-
baseline ratchet so you can turn gates on against a codebase that fails them today, and
line-scoped linting so touching one line in a legacy file doesn't make you own its debt.

## Skills — and what backs each one

The third column is the whole argument. A skill is a request; a mechanism is a guarantee.

| Skill | Mechanically backed by |
|---|---|
| `brainstorming` | Open assumptions block `verify preflight` |
| `writing-plans` | — judgment |
| `using-worktrees` | Deny-list blocks pushes to main |
| `test-driven-development` | Cheat scanner: skipped tests, deleted assertions, `\|\| true`, retry-to-green |
| `executing-plans` | Progress ledger on disk, survives compaction |
| `systematic-debugging` | Flaky detection against a clean base commit |
| `dispatching-agents` | — judgment |
| `gate` | **`Stop` hook exit 2 while gates are red** |
| `blast` | Graph query; fails loudly when no index exists |
| `requesting-review` | Reviewer cannot clear a red gate |
| `finishing-a-branch` | Deny-list blocks self-merge; CI re-runs every gate |
| `pressure-testing` | Deterministic scoring, not an LLM judge |
| `verified-autonomy` | Bootstrap — injected only in repos that opted in |

Where a column two entry says "judgment", that is deliberate: those are the decisions a
machine cannot make, and pretending otherwise would be theatre.

## Cross-harness

Enforcement lives in `bin/verify`, a plain CLI — **not** in a hook. Claude Code's `Stop`
hook, Codex via `AGENTS.md`, and CI all call the same command, so "done" cannot mean
different things in different places. Codex has no blocking hook, so CI is its real gate.

## Documentation

Fourteen documents in [`docs/`](docs/INDEX.md) — evidence base, architecture, definition of
done, gate ladder, test scenario catalog, guardrails, autonomy levels, adoption playbook,
graph engineering, tools and rules, operationalization, PR lifecycle, operator guide, and a
comparison with [obra/superpowers](https://github.com/obra/superpowers).

## Relationship to Superpowers

They are not competitors. Superpowers is layer 1 executed about as well as layer 1 can be —
14 pressure-tested skills covering brainstorming, planning, TDD discipline, and debugging
method. It ships exactly one hook (`SessionStart`), which cannot block.

Their own guidance draws the same boundary this plugin acts on:

> Mechanical constraints (if it's enforceable with regex/validation, automate it — save
> documentation for judgment calls)

Run both. Superpowers makes the agent want to do the right thing; this makes it unable to
do otherwise.

## Honest limits

- Green gates ≠ correct code. Roughly half of test-passing agent patches were rejected by
  real maintainers (METR, Mar 2026). Human review still carries design quality.
- Gates only catch cheats they enumerate.
- Detectors decay across model generations — recalibrate.
- This costs more per task in tokens and CI minutes.

## License

MIT
