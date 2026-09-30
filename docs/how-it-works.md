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
- `ready` is a URL path (`/health`) or a command. A URL path passes as soon as the server
  answers it with any HTTP status, 100 to 599, a 404, 405 or 500 included: a server that answers
  is up, and whether that page is right is for the outcome's check. A refused or reset
  connection, or no answer in 3 s, is not ready. Before this change only a 2xx passed, so a
  ready page that answered 404 or 405 was CANNOT RUN after `ACCEPT_READY_TIMEOUT`; now the
  check runs against it and FAILS. A redirect is an answer and is not followed. A command passes
  when it exits 0.
- The environment can fail under a run. A port that already accepts connections just before
  `start` (taken during `build`, say) is CANNOT RUN, and `start` is not run beside it. The harness
  watches the `start` process and the port it answered on. An outcome whose app is gone before
  it runs, or by the time its check or its control returns, is never `holds`: a control that
  fails against a dead app shows nothing. If the process was ended by a signal, or a shell
  wrapper reports one (exit 128 plus the signal), or the port stopped accepting connections,
  the outcome is CANNOT RUN ("the app stopped during the check", or "control"). If the process
  exited by itself with a status, the product crashed and the outcome FAILS ("the app exited
  with status N during the check", with `server-<env>.log` named). The outcomes after it are
  CANNOT RUN, because there was no app to check. A port is watched once it has been seen
  answering in this run, so `reuse` and port-only environments are covered, and an app that
  never listens on `$PORT` is not.
- What it cannot tell. A crash by a fault signal (SIGSEGV, SIGABRT) reads CANNOT RUN like any
  signal. A wrapper that stays alive while its server dies by itself reads CANNOT RUN, because
  only the port shows it. An app that exits by itself for a cause outside the product reads
  FAILS, and one that exits on SIGTERM with status 0 after a control stopped it on purpose reads
  FAILS too. A shell wrapper that reports 128 plus a signal for a product that called
  `exit(137)` itself reads CANNOT RUN. A `reuse` or port-only app that never answered has
  nothing to watch, and if another process takes over its port it looks alive. A crash that
  comes after the request was answered is blamed on the outcome running then, and one that
  comes after the last check or control has returned is not seen. `start` must stay in the
  foreground.
- Why a CANNOT RUN. Each one carries a `reason` in `.claude/evidence/product.json`, on its
  printed line (`reason=build_failed`) and in a count (`2 could not be checked: 1 build_failed,
  1 environment`), so a broken build reads differently from a broken machine. `build_failed`: the
  environment's `build` exited non-zero, or gave no answer in time (`command` and `status` or
  `timeout` are recorded). `start_failed`: `start` exited before `ready` passed, or `ready` never
  passed (`status` or `timeout`). `environment`: the port was already served or taken, the app was
  ended by a signal (before `ready`, between outcomes, or during a check or control), or its port
  stopped answering. `check_cannot_run`: the check or the control exited 75 (`stage` says which).
  `contract_invalid`: `start` is declared with no `ready`. `harness_error`: `acceptance.py` itself
  raised. The reason names the step that could not run, not a proven cause: a signal can be an
  out-of-memory kill or a crash, and a `start` that dies binding a port taken a moment earlier
  reads `start_failed`. It changes no verdict and no exit code.
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
check ran; a `CANNOT RUN` outcome also carries its `reason`, `unspecified` when the harness named
none, and its `status` when the step exited with one; no other verdict carries either). Every
value is measured by the run: an older `product.json` is never read into it. A run killed by a
signal writes no line, and a log that cannot be written warns and does not change the run.

## Limits

- The contract proves what was declared. What nobody declared is unchecked.
- The evidence files are written by the process they describe: a record, not a receipt.
- Checks written by the same agent that wrote the code are weaker evidence than expectations a
  person wrote.
