# Verified Autonomy

**A complete architecture for autonomous coding agents** — 14 workflow skills, mechanical
enforcement, and an adjudication layer. The agent cannot claim completion while the code's
gates are red or the product does not do what was asked: a `Stop` hook exits 2 and refuses
the turn.

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

## What "done" means

`./bin/verify done` exits 0. It has two halves, and both must pass:

| Half | Source | Passes when |
|---|---|---|
| Engineering | `.claude/gates.json` | every gate command exits 0 |
| Product | `.claude/acceptance.json` | every outcome holds against the running product |

Green engineering gates say the code is consistent. They do not say the product does what
was asked, so a project with no product contract is never done. When `done` refuses, it
names each open expectation in the user's words, and the agent continues with those or says
what blocks one. After three refusals in a row it asks for a blocked report, then lets the
turn end so a person can review it.

## Setup

### 1. Install the plugin, once per machine

In Claude Code:

```
/plugin marketplace add Giova445/verified-autonomy
/plugin install verified-autonomy@verified-autonomy
```

Restart Claude Code. The plugin is safe to install globally. In a repo it has not armed, no
gate runs and nothing blocks; the session only learns that the `setup` skill exists.

### 2. Arm a repo: say one sentence

In Claude Code, inside the repo:

> set up verified-autonomy

The `setup` skill does the rest on a branch, with no manual steps:

| Step | What happens |
|---|---|
| Engineering gates | installs the runner and hooks, runs every lint, typecheck and test command it finds at the root and one directory down, and keeps only the ones that pass today. A subdirectory's gates get a `surface`, so they run only when the diff touches that app |
| Map the product | `bin/discover` lists how to serve each app (command, port, readiness probe), its pages, endpoints, CLIs, existing e2e specs and docs. The agent also reads the README, specs, issues and recent PRs |
| Write the contract | `.claude/acceptance.json`: the three to eight journeys a user would call the product, in the user's words, each checked against the running product and paired with a control that must fail |
| Prove it | `./bin/verify product` starts the app, waits for it, runs every check in a real browser or over HTTP, saves a screenshot per outcome, and stops the app |
| Commit | runs the self-test and commits on `chore/arm-verified-autonomy`, with no co-author trailer. It pushes and opens a PR where it may; it never merges |

It stops to ask only when a credential is needed and the repo has none, when more than one
environment could be authoritative, or when an outcome fails because the product itself is
broken.

The same happens without the sentence: when `done` refuses because no contract exists, the
refusal points the agent at `setup`.

### What it writes

`.claude/gates.json`, every entry already passing once in the repo:

```json
{ "full": [
  { "name": "unit",         "cmd": "npm test --silent" },
  { "name": "api-js-test",  "cmd": "cd api && pytest -q", "surface": ["api/**"] }
] }
```

`.claude/acceptance.json`, the product contract:

```json
{
  "environments": {
    "local": {
      "start": "cd web && npm run dev",
      "ready": "curl -fsS -o /dev/null http://localhost:3000/"
    }
  },
  "outcomes": [
    {
      "name": "search finds a customer",
      "expect": "Typing a customer's name lists that customer and no one else",
      "env": "local",
      "check": "node .claude/gates/drive.mjs http://localhost:3000/customers .claude/checks/search.json",
      "control": "node .claude/gates/drive.mjs http://localhost:3000/customers .claude/checks/search-wrong-name.json"
    }
  ]
}
```

- **`start` / `ready`**: the harness runs `start`, polls `ready` until it passes (default
  180s, `ACCEPT_READY_TIMEOUT`), runs the outcomes, then stops the app. Its output goes to
  `.claude/evidence/server-<env>.log`. If `ready` already passes before `start`, something
  else is serving there and would be checked instead of this build, so the outcomes read
  CANNOT RUN. Declare `"reuse": true` only when that process is this build.
- **`check`** exits 0 when the outcome holds, 1 when it does not, and 2 when it cannot run
  at all. Exit 2 reads as CANNOT RUN, never as a failure of the code.
- **`control`** is a variant that must fail, proving the check can tell a broken product
  from a working one. It is optional, and outcomes without one are reported as such.
- **`drive.mjs`** drives a real browser from a JSON list of steps: `fill`, `click`,
  `visible`, `hidden`, `enabled`, `disabled`, `text`, `count`, `consoleClean`,
  `noOverflow`, `focusable`. It finds Playwright at the root or one directory down (a monorepo's
  web app), or at `PLAYWRIGHT_PATH`. A page it cannot reach because the app is not running
  exits 2 (CANNOT RUN); a missing local file fails, because the artifact itself is missing.
- **Remote environments** such as staging add `vars` for the base URL and a `provenance`
  probe that prints the deployed commit. A deployment running a different commit reads as
  WRONG BUILD, not as a pass.

### Optional settings

| File or variable | Effect |
|---|---|
| `.claude/protected-branches` | branches agents may not push or merge into (default `main`, `master`) |
| `VERIFIED_AUTONOMY_UNATTENDED=1` | adds guidance against stopping early, for runs nobody is watching |
| `GATE_MAX_BLOCKS` | refusals before the blocked report (default 3) |
| `kit/ci/verify.yml` | copy to `.github/workflows/` so CI runs the same `./bin/verify done` |

### By hand, if you want to

```bash
bash "$(ls -d ~/.claude/plugins/cache/verified-autonomy/verified-autonomy/*/ | sort -V | tail -1)kit/install.sh" .
python3 bin/discover .          # the product map
./bin/verify product            # the contract alone
bash .claude/hooks/selftest.sh  # prove the hooks fire
```

## The loop an agent runs

```bash
./bin/verify preflight        # graph health, open assumptions
./bin/verify blast <symbol>   # who calls this, before changing it
./bin/verify fast             # after each edit
./bin/verify product          # the product half alone
./bin/verify done             # exit 0 or it is not done
```

## Updating

```bash
claude plugin marketplace update verified-autonomy
claude plugin update verified-autonomy@verified-autonomy
```

Restart Claude Code, then re-run step 2 in each project to refresh its copies. Existing
`gates.json` and `AGENTS.md` are left alone.

## Troubleshooting

| You see | Meaning | Do |
|---|---|---|
| `no product expectations are declared` | the project has no `.claude/acceptance.json` | say "set up verified-autonomy", or run the `setup` skill |
| `NOT PROVEN` on an outcome | its control passed too, so the check cannot tell broken from working | make the check stricter |
| `CANNOT RUN` | the check exited 2: environment, not code | read `.claude/evidence/server-<env>.log`, fix `start`/`ready`, or provide the credential it names |
| `WRONG BUILD` | the environment runs a different commit | deploy this commit, then re-run |
| `CIRCUIT BREAKER` | three refusals in a row, each after a change | the agent writes a blocked report; the next stop is allowed |
| `NO PROGRESS` | refused before, and nothing in the repo changed since | the stop is allowed without re-running the gates; the agent writes a blocked report |
| `STALLED` | a later stop on that same unchanged state | allowed at once; the gates run again as soon as the repo changes |
| `UNCHANGED since the last green run` | nothing changed since the gates last passed | allowed at once, reusing that verdict; `VERIFY_CACHE=0` forces a full run |
| `has not changed this repo` | no contract, and this session changed nothing here | allowed; arm the repo with `setup` when you work in it |
| a hook blocks a routine command | a deny rule matched | the message names the rule; push to a feature branch, not a protected one |

## What the hooks do

| Hook | Behavior |
|---|---|
| `Stop` / `SubagentStop` | Runs `bin/verify done`. **Exit 2 while the engineering or the product half is red**; the reason returns to the agent, naming each open expectation. It never loops: a refusal on an unchanged repo is allowed through as NO PROGRESS, and a stop on a repo unchanged since the last green run returns at once. "Unchanged" compares HEAD, the diff, untracked contents, the gate config, the contract and the runner itself, and ignores agent-tooling output such as `.claude-flow/` and `.agents/`. Time limit 15 minutes. |
| `PreToolUse` | Blocks pushes and merges into protected branches, `reset --hard`, `clean -f`, destructive SQL, self-approval, credential reads, exit-code suppression on a test command, and commits carrying a `Co-Authored-By` trailer. Force-pushing your own branch is allowed. |
| `SessionStart` | Injects the contract in armed repos and records the repo's state for this session; in an unarmed git repo, one line pointing at `setup`. |

Plus: a cheat scanner that diffs for the documented ways agents fake green (skipped tests,
deleted assertions, `|| true`, retry-to-green, snapshot re-recording), a never-worse-than-
baseline ratchet for turning gates on against a codebase that fails them today, and a
`co-author` gate that refuses unpushed commits carrying a trailer.

## Skills, and what backs each one

A skill is a request; a mechanism is a guarantee.

| Skill | Mechanically backed by |
|---|---|
| `setup` | arms only commands that pass; the contract must reach `holds` with failing controls before it is committed |
| `brainstorming` | open assumptions block `verify preflight`; criteria become contract outcomes |
| `writing-plans` | judgment |
| `using-worktrees` | pushes to protected branches are blocked |
| `test-driven-development` | the product outcome fails first; cheat scanner on the tests |
| `executing-plans` | progress ledger on disk, survives compaction |
| `orchestrating` | ledger claims file scope before a worker writes |
| `systematic-debugging` | flaky detection against a clean base commit |
| `dispatching-agents` | judgment |
| `gate` | **`Stop` hook exit 2 while either half is red** |
| `blast` | graph query; fails loudly when no index exists |
| `requesting-review` | the reviewer cannot clear a red gate; compares screenshots with expectations |
| `finishing-a-branch` | merges into protected branches are blocked; CI re-runs every gate |
| `pressure-testing` | deterministic scoring, not an LLM judge |
| `verified-autonomy` | bootstrap, injected only in repos that opted in |

Where the second column says "judgment", that is deliberate: those are decisions a machine
cannot make.

## Cross-harness

Enforcement lives in `bin/verify`, a plain CLI — **not** in a hook. Claude Code's `Stop`
hook, Codex via `AGENTS.md`, and CI all call the same command, so "done" cannot mean
different things in different places. Codex has no blocking hook, so CI is its real gate.

## Documentation

Sixteen documents in [`docs/`](docs/INDEX.md) — evidence base, architecture, definition of
done, gate ladder, test scenario catalog, guardrails, autonomy levels, adoption playbook,
graph engineering, tools and rules, operationalization, PR lifecycle, operator guide, a
comparison with [obra/superpowers](https://github.com/obra/superpowers), a premise audit and
a verification checklist.

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
