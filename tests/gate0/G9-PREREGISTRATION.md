# G9 rerun: preregistration

This file is committed on its own, before the rerun starts. The commit's sha and time are what the
run's receipt (`receipt.txt` in `G9_OUT`) is compared against. Nothing below is changed after the
commit; a change would be a new commit, and the run must start after the last commit that touches
this file.

## What is run

- The spec agent's contracts, `tests/gate0/spec/<fixture>/.claude`, against the 155-fault corpus in
  `tests/gate0/faults`, through `bash tests/gate0/g9.sh` (`G4_CONTRACTS=spec`), sequential, on a
  harness whose `ready` probe treats any HTTP response as up (fix commit `f588d5e`). The report
  and `g9.sh` that compute and gate on the verdict below are commit `a723ace`.
- Baseline first: every spec contract must hold every outcome on its unpatched fixture. If one does
  not, no fault is run and the verdict is NOT MEASURED.
- Each fault is run once (pass 1). Pass 1 is the only run that is scored.
- Then a repeat of every fault whose verdict differs from the first G9 run (see Repeats).
- Also run once, for comparison and not scored: G4 (`tests/gate0/g4.sh`, the hand-written
  contracts) with the same harness and the same classification.

## Classification of one fault (unchanged from the first G9 run)

`g9.sh` reads `.claude/evidence/product.json` after `verify product`:

- caught: at least one outcome is FAILS, NOT PROVEN or WRONG BUILD.
- missed: every outcome holds (a false PASS).
- no signal: anything else (CANNOT RUN, NO VERDICT, BLOCKED, REFUSED, or an unreadable
  `product.json`).

Missed and no signal are both counted as not caught.

## Populations

- Behaviour faults: every fault whose manifest entry has `breaks_run: false`, except `nj-29`.
  138 faults: cli 31, fastapi 30, monorepo 25, nextjs 23, signin 29.
- `nj-29` is a harness artifact (Turbopack rejects a symlinked `node_modules`), not a defect. It is
  run and listed, and counted in no rate.
- Break faults: every fault whose manifest entry has `breaks_run: true`. 16 faults: cli-32, fa-21,
  fa-22, mr-12, mr-19, mr-20, mr-25, mr-28, nj-11, nj-16, nj-17, nj-19, nj-21, nj-30, si-19, si-30.
  They are excluded from the primary rate. A CANNOT RUN on a fault whose defect is a broken
  build or start is not a catch.

## Primary metric

Pooled across the five fixtures: the catch rate on behaviour faults, caught / 138. The pass mark is
a rate of at least 80% (caught * 100 >= 80 * 138, that is 111 or more caught). The Wilson 95%
score interval (z = 1.96) of the pooled rate is reported; the mark is on the rate, not on the
interval.

## Clauses per fixture

Every fixture must satisfy all three:

1. States. Each state the product has has at least one caught fault. The states a product has come
   from its ticket (`tests/gate0/tickets`), encoded in `PRODUCT_STATES`, and the faults seeded in
   each state are `STATE_FAULTS`, both in `tests/gate0/g9_report.py`, committed unchanged since
   `72b3b52` (before the first G9 run). Their sha256 (json, sorted keys) is
   `c47b9a607489395f6dbc931dde47f21a5fc35cd2812b6bd2a822392f44921082`; the report prints it.
   - cli: empty (cli-16, cli-31), error (cli-12).
   - fastapi: empty (fa-24, fa-30, fa-32), error (fa-05, fa-11, fa-15). fa-15 stays in the error
     state as the committed map assigns it. `fa-31` is labelled a response-shape fault, not a
     state, and is reported without being a clause.
   - monorepo: loading (mr-07, mr-14, mr-26), empty (mr-17).
   - nextjs: loading (nj-05, nj-13, nj-22, nj-31), empty (nj-06, nj-27).
   - signin: error (si-10, si-12).
2. Wrong field. At least one fault in the categories "wrong field displayed" or "wrong field in
   search/filter" is caught.
3. Rate. The fixture's own rate on its behaviour faults is reported with its Wilson 95% interval.
   A fixture fails on rate only if the upper bound of that interval is below 80%.

## Secondary line

"build/start broken, not passed": each of the 16 break faults must be not passed, meaning at least
one outcome is not `holds` (FAILS or CANNOT RUN; never every outcome holding). The line reports
n/16 with the split into FAILS-type, CANNOT RUN, other non-holds, holds and no result, and is MET
only at 16/16. It is printed as its own line and does not enter the PREREGISTERED VERDICT.

## The verdict

`g9_report.py` prints exactly one line beginning `PREREGISTERED VERDICT:`.

- MET: the pooled rate is at least 80% and all five fixtures satisfy clauses 1, 2 and 3.
- NOT MET: any of those fails.
- NOT MEASURED: a scored fault (a behaviour or break fault) has no pass-1 result, a clause has
  nothing seeded to test, or the baseline did not hold.

## Repeats

The repeat set is every fault whose per-outcome verdicts (the `detail` column of `results.tsv`,
for example `name=FAILS | name2=holds`) differ between the first G9 run and pass 1. The first G9
run ran at commit `72b3b52` on 2026-09-29 and saved 155 faults in `results.tsv`, sha256
`a3fbfaa5b548e698d08c7569a8fe71ad9e3393a442e8595771be913f5b5eb876`, kept at
`/private/tmp/claude-501/-Users-gio-Documents-Cadre-AI-Griffin--claude-worktrees-autonomous-agent-architecture-4b13de/b3f507f8-6657-4c26-9a04-94f36c5b52df/scratchpad/g9-out/results.tsv`.
Each fault in the repeat set is run once more in a separate output directory. Repeats
never replace a pass-1 verdict. A repeat whose outcome verdicts differ from pass 1 marks that fault
unstable; the report lists them and prints the pooled rate with every pass-1 catch that its
repeat did not reproduce as a catch counted as not caught, labelled a sensitivity and not the
verdict.

## Reported, not scored

Per fixture and per category tables for the first G9 run against pass 1, and for G4 before (the
committed `RESULTS.md`) against G4 after the probe fix; every fault whose verdict changed; wall
time and peak memory. The first G9 run and the rerun differ by more than the probe fix
(`acceptance.py`, `drive.mjs` and `hooks/state.py` changed between `72b3b52` and `5871de2`), so a
change is attributed to the probe fix only where the faults are also run on the unfixed harness
(`5871de2`); that check is additional and is not scored.

## Disclosures

- The rule was written after the first G9 run's results were known. Run over the saved first-run
  results, `g9_report.py` gives 126/138 (91.3%, Wilson 95% 85.4 to 95.0) and every fixture
  satisfying the clauses, so the rule does not depend on the probe fix to be met. Before this
  commit the only things run were the acceptance self-test and the regression suites (selftest.sh,
  g2, g5, g7), that report over the saved first-run results, and `g9.sh` over the cli fixture with
  no fault selected (baseline only). No fault of the rerun was run.
- The run uses one machine, one run per fault, and the fixtures' Chromium and Node as installed
  there; flakiness is measured only through the repeats above.
