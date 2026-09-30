# Verified Autonomy

A small tool that proves a change works for its user before you open a PR. It runs the repo's
tests that passed when the repo was armed, then the product outcomes a person declared, each
checked against the running app (a real browser, an HTTP call, or the CLI). It runs no hooks:
nothing happens until you or the agent run it, normally once before a PR and in CI.

It used to enforce this on every turn through a Stop hook. Measured on real sessions, that cost
hours, looped, refused agents for work they did not own, and caught no real product defect, so
it was removed. What is left is the part other tools do not do: declared, user-visible outcomes,
each with a control that must fail, checked against the running app. Details and limits:
[docs/how-it-works.md](docs/how-it-works.md).

## Install

```
/plugin marketplace add Giova445/verified-autonomy
/plugin install verified-autonomy@verified-autonomy
```

Then, in a repo, say "set up verified-autonomy". The `setup` skill arms the test commands that
pass today, writes `.claude/acceptance.json` from the outcomes you or the ticket state, proves
each against the running app, and commits on a branch. It never merges.

Before a PR, say "prove it" (the `prove` skill), or run:

```bash
./bin/verify done      # tests, then product outcomes
./bin/verify product   # product outcomes only
```

## Verdicts

| Verdict | Meaning |
|---|---|
| `holds` | the check passed, and its control, if any, failed |
| `FAILS` | the check ran and the product did not do it, or the app exited by itself with a status during the run |
| `NOT PROVEN` | the control passed too, so the check cannot tell broken from working |
| `CANNOT RUN` | the check exited 75, the app would not build or start, or the app was killed or lost its port during the run. Its `reason` says which |
| `BLOCKED` | an outcome declares a credential in `needs` and it is not set |
| `NO VERDICT` | the check ran out of time |
| `WRONG BUILD` | the environment runs another commit |
| `REFUSED` | the outcome lacks a name, an `expect` or a `check` |

Every `CANNOT RUN` carries a `reason` in `.claude/evidence/product.json`, on its printed line, and
in a count (`2 could not be checked: 1 build_failed, 1 environment`):

| `reason` | Meaning |
|---|---|
| `build_failed` | the environment's `build` exited non-zero (command and status recorded) or gave no answer in time |
| `start_failed` | `start` exited before `ready` passed, or `ready` never passed (status or timeout recorded) |
| `environment` | the port was already served or taken, the app was ended by a signal, or its port stopped answering |
| `check_cannot_run` | the check or its control exited 75 |
| `contract_invalid` | `start` is declared with no `ready` |
| `harness_error` | `acceptance.py` itself raised |

## The contract

```json
{
  "environments": {
    "local": { "build": "npm run build", "start": "npm run start -- --port $PORT", "ready": "/" }
  },
  "outcomes": [
    {
      "name": "search finds a customer",
      "expect": "Typing a customer's name lists that customer and no one else",
      "env": "local",
      "check": "node .claude/gates/drive.mjs $BASE_URL/customers .claude/checks/search.json",
      "control": "node .claude/gates/drive.mjs $BASE_URL/customers .claude/checks/search-wrong-name.json"
    }
  ]
}
```

- `start`, `ready`: the harness starts the app on a free `$PORT` (with
  `BASE_URL=http://localhost:$PORT`), waits for `ready`, runs the outcomes, and stops the app.
  `start` stays in the foreground: the harness watches that process, and an outcome it finds
  dead is CANNOT RUN, never FAILS or holds. A port already answering before `start` is CANNOT
  RUN too, unless the environment declares `"reuse": true`. Environments with no `start`, or
  with `reuse`, are not watched.
- `build`: optional, run before `start`. It is skipped when a gate that just passed ran the same
  command, or when this exact tree was already built. A production build (`build`, then the
  production `start`) uses a fraction of a dev server's memory; prefer it.
- `check` exits 0 when the outcome holds and 75 when it cannot run. Any other exit is a failure.
- `control` is a variant that must fail, proving the check can tell broken from working.
- `needs` lists environment variables an outcome or environment requires.
- `drive.mjs` drives a real browser from a JSON list of steps that wait for the page; a plain
  Playwright test or `curl -fsS` works just as well.

## Optional settings

| Setting | Effect |
|---|---|
| `GATE_TIMEOUT` | seconds for one test gate (default 300); past it the verdict is NO VERDICT |
| `ACCEPT_TIMEOUT`, `ACCEPT_READY_TIMEOUT`, `ACCEPT_BUDGET` | seconds for one check (120), for the app to become ready (120), for the whole contract (600) |
| `ACCEPT_BUILD_TIMEOUT` | seconds for an environment's `build` (default 600) |
| `VERIFY_MEMORY_MB` | memory budget for one run (default 600). Each run prints its peak and names the step that went over; `0` turns the meter off |
| `ACCEPT_NAV_TIMEOUT` | milliseconds `drive.mjs` waits for a page to load (default 30000) |
| `VERIFY_SCOPE=0` | run gates whose surface the diff does not touch |
| `PLAYWRIGHT_PATH` | where `drive.mjs` finds Playwright when it is not in the repo |
| `.claude/forbidden-trailers` | opt-in: commit trailers the `co-author` gate refuses, one per line |

## Updating

```bash
for d in ~/.claude*/; do
  [ -d "$d/plugins" ] || continue
  CLAUDE_CONFIG_DIR="$d" claude plugin marketplace update verified-autonomy
  CLAUDE_CONFIG_DIR="$d" claude plugin update verified-autonomy@verified-autonomy
done
```

## License

MIT
