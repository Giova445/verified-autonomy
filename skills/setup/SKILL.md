---
name: setup
description: Arms verified-autonomy in the current repo: installs the runner, arms the tests that pass, and writes the product outcomes the person or ticket states. Use when the user asks to set up or arm verified-autonomy, or when `./bin/verify` says "no product expectations are declared".
---

# Setup

Take the repo to proven gates and a proven product contract, committed on a branch. Do every step
yourself. Stop only when a credential is needed and the repo provides none, when more than one
environment could be authoritative, or when an outcome `FAILS` because the product is broken.

## 1. Install

```bash
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
VA="${CLAUDE_PLUGIN_ROOT:-$(python3 -c 'import glob,json,os,sys
c,k=sys.argv[1],"verified-autonomy"
try: e=[x["installPath"] for x in json.load(open(c+"/plugins/installed_plugins.json"))["plugins"][k+"@"+k] if os.path.isdir(x["installPath"])]
except Exception: e=[]
print((e or sorted(glob.glob(c+"/plugins/cache/%s/%s/*"%(k,k)),key=lambda p:[int(n) for n in os.path.basename(p).split(".") if n.isdigit()]))[-1])' "$CFG")}"
git switch -c chore/arm-verified-autonomy && bash "$VA/kit/install.sh" .
```

`$VA` is the installed version (`installPath` in `installed_plugins.json`), else the
highest cached. The installer arms gates from the commands that pass today; a `.new` beside an
existing `gates.json` or `bin/verify` is merged by hand (keep every existing entry, then delete it).
A command that fails on a clean checkout is inherited debt: leave it out, report it.

## 2. Discover

`mkdir -p .claude/evidence && python3 "$VA/bin/discover" . > .claude/evidence/discover.json` prints facts
only (scripts, Makefile/Procfile/compose commands, frameworks, pages, endpoints, e2e specs, docs);
choose the start command yourself. Expectations come from the person and the ticket, not from
you: take them from the user's request, open issues and the README, quote the source in each
`expect`, and if none states what users must see, ask one question listing the journeys you propose.

## 3. Write the contract

`.claude/acceptance.json`: three to eight journeys a user would call the product. Keep existing outcomes.

```json
{ "environments": { "local": { "build": "cd web && npm run build",
                                "start": "cd web && npm run start -- -p $PORT", "ready": "/" } },
  "outcomes": [ { "name": "orders list", "env": "local", "needs": ["API_TOKEN"],
    "expect": "Opening Orders shows the customer's orders, newest first",
    "check": "node .claude/gates/drive.mjs \"$BASE_URL/orders\" .claude/checks/orders.json",
    "control": "node .claude/gates/drive.mjs \"$BASE_URL/orders\" .claude/checks/orders-bad.json" } ] }
```

- The harness picks a free port, exports `$PORT` and `$BASE_URL` to `start`, `ready`, `check` and
  `control`, waits for `ready` (a URL path like `/`, or a command) and stops the app after.
- Serve a production build (`build` plus the production `start`), not a dev server: it is what
  users get, and a dev server compiles on demand, costing about 5x the memory and a slower first
  page. When a passing gate runs the same `build` command, or this exact tree was built already,
  the build is not repeated. Use a dev server only when the repo has no production build.
- Keep a run under 600 MB: `verify` prints its peak and names the step over budget. Cap that
  step's workers in the command, identically in the gate and in `build` so it is built once.
  Next.js: `CIRCLE_NODE_TOTAL=1 npm run build` (one build worker: 830 to 400 MB). Jest:
  `--maxWorkers=2`.
- `expect` is what a user sees or does, in their words. Never "works" or "renders".
- `check` exits 0 when it holds, non-zero when it does not, 75 when it could not run. `drive.mjs`
  steps (they wait for each assertion) are quick; `curl -fsS`, the real CLI and plain Playwright
  scripts (`npx playwright test e2e/orders.spec.ts`) are first-class.
- `control` is the same check aimed at something that must fail. Give every outcome one.
- `needs` lists credentials. Unset means BLOCKED, nothing runs, report it once. Never invent one.

## 4. Browser, then prove

Page outcomes need `npm i -D playwright` (if missing) and `npx playwright install chromium`, else they
read CANNOT RUN. Then `./bin/verify product`: every outcome must read `holds`, every control must fail.
Each check's output is `.claude/evidence/<name>.log`. `NOT PROVEN`: sharpen the control. `CANNOT RUN`:
app, browser or network; fix `start`/`ready`, read `evidence/server-*.log`. `BLOCKED`: a `needs`
variable is unset. `FAILS`: fix a wrong check; a real defect stays and goes in your report. Never
weaken an `expect` to pass.

## 5. Commit

Run `bash .claude/selftest.sh`, then `git add -f bin/verify .claude/bin .claude/hooks/state.py
.claude/gates .claude/gates.json .claude/acceptance.json .claude/checks` and commit
`chore: arm verified-autonomy`.
Commit what CI needs to run the contract too: the Playwright dev dependency and a CI step
`npx playwright install chromium`. Never merge.
