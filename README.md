# Verified Autonomy

A Claude Code plugin that makes "done" something the harness proves, not something the agent
claims. When an agent tries to end a turn in a repo it changed, a `Stop` hook runs the repo's
engineering gates and its product contract, and refuses while either is red. The refusal names
each open expectation in the user's words. A turn that only read code, or changed nothing, is
not judged: no gate runs and no app starts. What it does and does not protect against is in
[docs/how-it-works.md](docs/how-it-works.md).

## Install

In Claude Code:

```
/plugin marketplace add Giova445/verified-autonomy
/plugin install verified-autonomy@verified-autonomy
```

Restart Claude Code. In a repo that is not armed no gate runs, though the deny rules still
apply. Then, in the repo, say:

> set up verified-autonomy

The `setup` skill works on a branch. It arms only lint, typecheck and test commands that pass
today, writes `.claude/acceptance.json` (the journeys a user would call the product), proves
each against the running product, and commits. It never merges.

## What the agent sees

The `Stop` hook runs `./bin/verify done`. A failed gate prints its command, exit code and last
lines. Each product outcome gets one verdict:

| Verdict | Meaning |
|---|---|
| `holds` | the check passed, and its control, if any, failed |
| `FAILS` | the check ran and the product did not do it |
| `NOT PROVEN` | the control passed too, so the check cannot tell broken from working |
| `CANNOT RUN` | the check exited 75, or the app would not start |
| `BLOCKED` | an outcome declares a credential in `needs` and it is not set |
| `NO VERDICT` | the check ran out of time |
| `WRONG BUILD` | the environment runs another commit |
| `REFUSED` | the outcome lacks a name, an `expect` or a `check` |

After three refusals in a row the agent is asked for a blocked report, then the stop is allowed.

## What it writes

`.claude/gates.json` lists the engineering gates, each already passing once in the repo. A gate
with a `surface` (a list of globs) runs only when the diff touches it.

`.claude/acceptance.json`, the product contract:

```json
{
  "environments": {
    "local": { "start": "npm run dev -- --port $PORT", "ready": "/" }
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

- `start`, `ready`: the harness starts the app on a free `$PORT`, waits for `ready`, runs the
  outcomes, and stops the app. Its log is `.claude/evidence/server-<env>.log`.
- `check` exits 0 when the outcome holds and 75 when it cannot run. Any other exit is a failure.
- `control` (optional) is a variant that must fail, proving the check can tell broken from
  working.
- `needs` lists environment variables an outcome or environment requires.
- `drive.mjs` drives a real browser from a JSON list of steps and saves a screenshot to
  `.claude/evidence/shots/`.
- A remote environment can declare a `provenance` probe that prints the deployed commit.

## Optional settings

| Setting | Effect |
|---|---|
| `.claude/protected-branches` | branches agents may not push or merge into (default `main`, `master`) |
| `GATE_MAX_BLOCKS` | refusals before the blocked report (default 3) |
| `ACCEPT_TIMEOUT`, `ACCEPT_READY_TIMEOUT` | seconds allowed for one check, and for the app to become ready |
| `VERIFY_CACHE=0` | judge even when nothing changed since the last verdict |
| `VERIFY_SCOPE=0` | run gates whose surface the diff does not touch |
| `PLAYWRIGHT_PATH` | where `drive.mjs` finds Playwright when it is not in the repo |
| `VERIFIED_AUTONOMY_UNATTENDED=1` | adds guidance against ending a turn early |

## Updating

```bash
for d in ~/.claude*/; do
  [ -d "$d/plugins" ] || continue
  CLAUDE_CONFIG_DIR="$d" claude plugin marketplace update verified-autonomy
  CLAUDE_CONFIG_DIR="$d" claude plugin update verified-autonomy@verified-autonomy
done
```

Restart Claude Code. To refresh a repo's copy of the runner, say "set up verified-autonomy"
again. It keeps every existing gate and outcome.

## Troubleshooting

| You see | Meaning | Do |
|---|---|---|
| `no product expectations are declared` | the repo has no `.claude/acceptance.json` | say "set up verified-autonomy" |
| `REFUSING TO CERTIFY` | `.claude/gates.json` is unreadable, empty, or holds a placeholder command | fix the file |
| `CANNOT RUN` | the check exited 75 or the app never became ready | read `.claude/evidence/server-<env>.log`; fix `start` and `ready` |
| `BLOCKED` | a variable named in `needs` is not set | set it |
| `WRONG BUILD` | the environment runs a different commit | deploy this commit, then re-run |
| asked for a blocked report | three refusals in a row | the agent writes it; the next stop is allowed |
| a stop is allowed and no gate ran | nothing changed since the turn began or since the last verdict | none; gates run again when the repo changes |
| `BLOCKED by deny-dangerous.sh` | a deny rule matched | the message names the rule; push a feature branch, not a protected one |

Superpowers teaches an agent good process. This plugin only checks the result. Run both.

## License

MIT
