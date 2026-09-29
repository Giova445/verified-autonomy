# How it works

verified-autonomy runs no hooks. Nothing happens until you or the agent run it, normally once
before opening a PR (the `prove` skill), and in CI.

## Why on demand

Measured on real sessions, a Stop hook that re-ran every gate on every turn cost hours, looped,
and refused agents for work they did not own, while its product half caught no real defect. The
checks are kept; the automatic enforcement is not.

## Commands

- `./bin/verify done`: the engineering gates, then the product contract. Exit 0 only when both pass.
- `./bin/verify product`: the product contract alone.
- `./bin/verify full`: the engineering gates alone.

Every run executes. The one exception is an environment's `build`, which is skipped when a gate
in the same run passed with the same command, or when the tree's fingerprint matches the last
successful build.

## Engineering gates

`.claude/gates.json` holds a `full` list of `{name, cmd}`. Each command runs from the repo root
and passes on exit 0. `bin/arm` writes the list from commands that passed when the repo was
armed. A gate with a `surface` (globs) is skipped, and reported as skipped, when the diff does
not touch it. An unreadable file, an empty list or a placeholder command refuses.

## Product contract

`.claude/acceptance.json` holds what a user must be able to do or see, as the person or the
ticket states it.

- `environments`: `start` and `ready`, and optionally `build`. The harness picks a free `$PORT`,
  exports `BASE_URL=http://localhost:$PORT`, runs `build` unless this tree is already built,
  starts the app, waits for `ready`, runs every outcome, and stops the app. A failed build is
  CANNOT RUN.
- `outcomes`: `name`, `expect` (the user's words), `check`, and optionally `control`, `needs`
  and `env`. A check exits 0 when the outcome holds and 75 when it cannot run. Any other exit
  fails. A control is a variant that must fail. If it passes, the check proves nothing.
  `needs` names environment variables that must be set.

Verdicts: `holds`, `FAILS`, `NOT PROVEN`, `CANNOT RUN`, `BLOCKED` (a `needs` variable is unset,
so nothing runs), `NO VERDICT` (timeout), `WRONG BUILD` (an environment's `provenance` probe
prints a commit other than HEAD), `REFUSED` (an outcome lacks `name`, `expect` or `check`).
Only `holds` passes.

## Evidence

`.claude/evidence/latest.json` records the commit, each gate's command and exit code, and the
product status. Each check's output is in `.claude/evidence/<name>.log`; browser checks save
screenshots to `.claude/evidence/shots/`.

## Limits

- The contract proves what was declared. What nobody declared is unchecked.
- The evidence files are written by the process they describe: a record, not a receipt.
- Checks written by the same agent that wrote the code are weaker evidence than expectations a
  person wrote.
