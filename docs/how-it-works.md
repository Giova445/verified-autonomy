# How it works

## The Stop hook

`hooks/stop-gate.sh` runs on `Stop`. It calls the plugin's own `bin/verify done --hook`, never a
copy in the repo. Exit 2 refuses the stop and returns the reason to the agent. A repo with no
`.claude/gates.json` is not gated. If it is tracked in git but missing or empty, the stop is
refused.

## Which turns are judged

In an armed repo, the harness records a fingerprint of HEAD, the diff, untracked files,
`gates.json`, `acceptance.json` and the runner before the agent works. At a stop:

- same as that fingerprint: the turn changed nothing. Allowed at once.
- same as the last verdict's: that verdict is reused. Allowed at once.
- anything else: the gates run.

Neither shortcut runs a gate or starts the app.

## Engineering gates

`.claude/gates.json` holds a `full` list of `{name, cmd}`. Each command runs from the repo root
and passes on exit 0. `bin/arm` writes the list from commands that passed when the repo was
armed. A gate with a `surface` (globs) is skipped, and reported as skipped, when the diff does
not touch it. An unreadable file, an empty list or a placeholder command refuses.

## Product contract

`.claude/acceptance.json` holds what a user must be able to do or see.

- `environments`: `start` and `ready`. The harness picks a free `$PORT`, starts the app, waits
  for `ready`, runs every outcome, and stops the app.
- `outcomes`: `name`, `expect` (the user's words), `check`, and optionally `control`, `needs`
  and `env`. A check exits 0 when the outcome holds and 75 when it cannot run. Any other exit
  fails. A control is a variant that must fail. If it passes, the check proves nothing.
  `needs` names environment variables that must be set.

Verdicts: `holds`, `FAILS`, `NOT PROVEN`, `CANNOT RUN`, `BLOCKED` (a `needs` variable is unset,
so nothing runs), `NO VERDICT` (timeout), `WRONG BUILD` (an environment's `provenance` probe
prints a commit other than HEAD), `REFUSED` (an outcome lacks `name`, `expect` or `check`).
Only `holds` passes. A missing or unreadable contract is refused too: green gates do not say
the product does what was asked.

## Refusals

Each refusal adds one to a counter. At `GATE_MAX_BLOCKS` (default 3) the next stop is refused
with an instruction to write a blocked report, and the stop after that is allowed. A stop with
nothing changed since a refusal is allowed at once: a refusal is never repeated.

## Evidence

`.claude/evidence/latest.json` records the commit, each gate's command and exit code, and the
product status. Browser checks save screenshots to `.claude/evidence/shots/`.

## The deny hook

`hooks/deny-dangerous.sh` inspects Bash commands only, wherever the plugin is enabled, and
blocks: pushes and merges into protected branches (`.claude/protected-branches`, default `main`
and `master`); approving a pull request; recursive force deletes of `/`, `~` or an unset
variable; `git reset --hard`; `git clean -f`; destructive SQL; `sudo`; `chmod 777`;
`terraform destroy`; `|| true` or `--exit-zero` on a test or lint command; snapshot
re-recording; and reading secret files such as `~/.aws/credentials`.

## What it does not protect against

- Hooks run on the client. An agent set on getting around them can edit the hook
  configuration, write a check that always passes, or use a file tool or a command the deny
  patterns miss. Remote branch protection is the real boundary.
- The evidence files are written by the process they describe: a record, not a receipt.
- A holding contract shows that what was declared works. What nobody declared is unchecked.

Gates defend against a sincere but wrong "done", not against an adversary.
