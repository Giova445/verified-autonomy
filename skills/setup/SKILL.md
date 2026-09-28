---
name: setup
description: Arms verified-autonomy in the current repo end to end, with no manual steps. Use when the repo has no .claude/gates.json or no .claude/acceptance.json, when the Stop hook says "no product expectations are declared", or when the user asks to set up, arm, install or "make this autonomous".
---

# Setup

Take the repo from nothing to a proven gate set and a proven product contract, then commit
it on a branch. Do every step yourself. Stop only for the decisions listed at the end.

## 0. Locate the plugin and branch off

```bash
VA="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/verified-autonomy/verified-autonomy/*/ | sort -V | tail -1)}"
git switch -c chore/arm-verified-autonomy   # skip if already on a non-protected branch
```

## 1. Install and arm the engineering gates

```bash
bash "$VA/kit/install.sh" .
```

The installer copies the runner and hooks, then runs every lint, typecheck and test command
it can find, at the root and one directory down, and writes `.claude/gates.json` from the
ones that passed. Gates for an app in a subdirectory get a `surface`, so they run only when
the diff touches that app.

- If `.claude/gates.json` already existed, it wrote `.claude/gates.json.new`. Merge: keep
  every existing gate, add the new ones that are not already covered, delete the `.new`.
- If it armed nothing, find the project's real commands yourself (CI workflow, Makefile,
  package scripts), run each, and add only the ones that exit 0 today. A command that fails
  on a clean checkout is inherited debt: leave it out and list it in your report.
- If `AGENTS.md.new` was written, merge its rules into `AGENTS.md` and delete it.

## 2. Map the product

```bash
python3 bin/discover . > .claude/evidence/discover.json
```

It lists how to serve each app (command, port, readiness probe), its pages, its endpoints,
its CLIs, existing end-to-end specs and docs. Then read what it points to, plus what it
cannot see: the README, specs and PRDs under `docs/`, open issues and recent PRs, existing
e2e specs, and project memory. Expectations usually live there, not in the code.

## 3. Write the contract

Write `.claude/acceptance.json`. Start with the three to eight journeys a user would call
the product: the ones that, if broken, mean the product is broken. Not one per route.
If a contract already exists, keep every outcome and add only journeys it does not cover:
re-running setup refreshes the kit and never discards a decision already made.

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
      "name": "orders list",
      "expect": "Opening Orders shows the customer's orders, newest first",
      "env": "local",
      "check": "node .claude/gates/drive.mjs http://localhost:3000/orders .claude/checks/orders.json",
      "control": "node .claude/gates/drive.mjs http://localhost:3000/orders .claude/checks/orders-control.json"
    }
  ]
}
```

- `start` and `ready` come from `discover`. The harness starts the app, waits for
  `ready`, runs every outcome, and stops it. Never ask the user to start a server.
- `expect` is what a user sees or does, in their words. Never "works" or "renders".
- `check` exercises the running product: `drive.mjs` with a steps file in `.claude/checks/`
  for pages, `curl -fsS` for endpoints, the real command for CLIs.
- `control` is the same check aimed at something that must fail: text that must not be
  there, a wrong value, a missing element. Give every outcome one.
- A backend endpoint the UI depends on is covered through the UI outcome, not separately,
  unless it is itself a product surface (a public API).

## 4. Prove it

```bash
./bin/verify product
```

Every outcome must read `holds` and every control must fail. Work each verdict:

| Verdict | Meaning | Do |
|---|---|---|
| `NOT PROVEN` | the control passed | the check cannot tell broken from working; sharpen it |
| `CANNOT RUN` | the app did not start, or a credential is missing | fix `start`/`ready`, read `.claude/evidence/server-*.log`; a missing secret is a human decision |
| `FAILS` | the check ran and the product did not do it | open the screenshot in `.claude/evidence/shots/`. If the check is wrong, fix the check. If the product is wrong, keep the outcome: that is a real defect, and it goes in your report |

Never weaken an `expect` to get a pass.

## 5. Commit

```bash
bash .claude/hooks/selftest.sh
git add -f .claude/gates.json .claude/acceptance.json .claude/checks AGENTS.md   # -f: many repos ignore .claude/
git commit -m "chore: arm verified-autonomy"
```

No `Co-Authored-By` trailer. Push and open a PR if you may; never merge it.

## 6. Report

State: the gates armed and the ones left out as inherited debt; each outcome with its
verdict; screenshots; defects found in the product; and the decisions below, if any.

## The only reasons to stop and ask

- A credential or test account is needed to reach a surface and none exists in the repo's
  seed, fixture or example-config files.
- More than one environment could be authoritative (local, staging, production) and nothing
  in the repo says which.
- An outcome `FAILS` because the product is broken: the user decides whether to fix it now.

## After setup

Each new task adds its outcomes before code: see `test-driven-development`. The contract
grows with the product; `./bin/verify done` holds every task to it.
