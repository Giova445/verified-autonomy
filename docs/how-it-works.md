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
- The environment can fail under a run, and none of these is a product verdict. A port that
  already accepts connections just before `start` (taken during `build`, say) is CANNOT RUN,
  and `start` is not run beside it. The harness watches the `start` process itself: if it has
  exited before an outcome, or by the time that outcome's check returns, the outcome is CANNOT
  RUN ("the app stopped during the check"), never FAILS or holds. What it cannot see: an
  environment with no `start`, or with `"reuse": true` (that app is not the harness's to
  watch, and `reuse` also skips the port check); a `start` wrapper that stays alive after the
  app inside it died; an app that stops during a control or after the last outcome (a control
  may take the app down on purpose, so the outcome keeps its verdict and the next outcome
  reports the stop); and an app that crashes because of the check, which reads CANNOT RUN with
  the exit status and `server-<env>.log` named. `start` must stay in the foreground.
- `outcomes`: `name`, `expect` (the user's words), `check`, and optionally `control`, `needs`
  and `env`. A check exits 0 when the outcome holds and 75 when it cannot run. Any other exit
  fails. A control is a variant that must fail. If it passes, the check proves nothing.
  `needs` names environment variables that must be set.

Verdicts: `holds`, `FAILS`, `NOT PROVEN`, `CANNOT RUN`, `BLOCKED` (a `needs` variable is unset,
so nothing runs), `NO VERDICT` (timeout), `WRONG BUILD` (an environment's `provenance` probe
prints a commit other than HEAD), `REFUSED` (an outcome lacks `name`, `expect` or `check`).
Only `holds` passes.

## Memory

Each `verify` run samples the physical memory of its whole process tree twice a second (macOS
`footprint`, Linux PSS, so pages shared between processes count once), prints the highest sample
and logs it. Above `VERIFY_MEMORY_MB` (600 by default) it names the step that peaked. It warns;
it does not fail the run. Measured on a Next.js app: a full `verify done` (typecheck, tests, a
one-worker build, the product check on the production server) peaks near 360 MB; a `next dev`
server alone is about 480 MB and an uncapped `next build` about 830 MB.

## Evidence

`.claude/evidence/latest.json` records the commit, each gate's command and exit code, and the
product status. Each check's output is in `.claude/evidence/<name>.log`; browser checks save
screenshots to `.claude/evidence/shots/`.

`.claude/evidence/runs.jsonl` gets one line per `done`, `product`, `full` or `fast` run:
`started_at` (UTC), `subcommand`, `commit` (HEAD), `tree` (the fingerprint when the run began),
`wall_ms`, `peak_memory_mb` (the highest sample; `null` when the meter is off or cannot measure),
`exit_code`, `verdict` (`green`, `red`, `config`, `noverdict`, `product` or `empty`), `gates`
(`name`, `exit_code`, `duration_ms`, `skipped` for each; `null` where a gate did not run or gave
no answer) and `product` (`status`, and each outcome's `name` and `verdict` when the product
check ran). Every value is measured by the run. A run killed by a signal writes no line, and a
log that cannot be written warns and does not change the run.

## Limits

- The contract proves what was declared. What nobody declared is unchecked.
- The evidence files are written by the process they describe: a record, not a receipt.
- Checks written by the same agent that wrote the code are weaker evidence than expectations a
  person wrote.
