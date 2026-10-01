# Results

This page reports what was measured about verified-autonomy: what was tested, how, what the numbers are, what worked, what did not, and what is not known.

The plain reading:

- The checker is mechanically sound on the apps and faults it was built against.
- Outcomes written by a spec agent from a ticket caught most planted faults in small fixture apps.
- Outcomes written from the descriptions of real pull requests did not catch any of the real defects that later fixes addressed (0 of 10), and adding a data contract to the ticket did not change that (0 of 4).
- The measured evidence therefore does not show ticket-sourced outcomes catching real escaped defects.

Every number below carries a source tag. The tags are listed in the next section. A number marked "computed here" is derived from counts in the source with the Wilson score interval (z = 1.96) and does not appear in the source itself.

## Sources

| Tag | Source | Public |
|---|---|---|
| R | `tests/gate0/faults/RESULTS.md`, one full sequential run of `bash tests/gate0/g4.sh` on 2026-09-29 (g4.sh at commit `8cb0d60`) | yes, in this repo |
| P | `tests/gate0/G9-PREREGISTRATION.md`, committed before the G9 rerun (`f99fd00`) | yes, in this repo |
| G9R | aggregate report of the G9 rerun, pass 1 (`report.txt`, produced by `tests/gate0/g9_report.py`) | no, kept with the run output |
| PLAN | the owner's test plan document, section named in the row (Gate 0 results, Gate 1 results, Gate 1b, Plan v2, Cost per PR) | no, not published |
| C | a commit in this repo, named by its hash | yes |

Gate 1 and Gate 1b were run on the history of one private production web app. That data stays private. This page uses only counts, rates, intervals and generic descriptions from those runs, and takes every Gate 1 and Gate 1b number from PLAN.

## Summary

| Question | Result | Source |
|---|---|---|
| Is the checker mechanically sound? | supported: Gate 0 G1 to G3 and G5 to G8 met | PLAN, Gate 0 results |
| Do a spec agent's outcomes catch planted faults in small apps? | yes: 128 of 138 behaviour faults (92.8%, Wilson 95% 87.2 to 96.0), under a rule committed before the run | G9R, P |
| Do hand-written outcomes? | no: 84 of 155 faults (54.2%), G4 NOT MET | R |
| Do outcomes written from real PR descriptions catch the defects later fixes addressed? | no: 0 of 10 (Wilson 95% 0 to 28%) | PLAN, Gate 1 results |
| Does adding a data contract to the ticket change that? | no: 0 of 4 (Wilson 95% 0 to 49%, computed here) | PLAN, Gate 1b |
| Does it fit the memory budget? | partly: harness peaks 400 to 660 MB against a 600 MB budget | PLAN, Plan v2 |

## What was tested and how

### Fixtures and planted faults

Five small apps stand in for common project shapes: a Next.js client page, a FastAPI service, a monorepo, a command-line tool and a signed-in page (`tests/gate0/fixtures`). Each is a small orders app, so the same kinds of defect can be planted in each.

155 user-visible faults were planted across the five (`tests/gate0/faults`): cli 32, fastapi 32, monorepo 30, nextjs 30, signin 31 [R]. Each is a patch with a category, for example wrong sort, wrong field displayed, dead handler, loading/empty/error state wrong, works in dev but not on the production build, build or start breaks. The faults were written and committed (`ee389a7`) before any contract was read [R].

A fault is caught when at least one outcome is FAILS, NOT PROVEN or WRONG BUILD. It is missed when every outcome holds (a false PASS). CANNOT RUN and NO VERDICT are reported separately and count as not caught [R].

### Two kinds of contract

- G4 hand-written contracts: one per fixture.
- G9 spec-agent contracts: a separate agent that sees only the fixture's ticket (`tests/gate0/tickets`), never the code, and writes each outcome in the user's words with a check and a control that must fail (`tests/gate0/spec`). It followed a state checklist (loading, empty, error, filled) and a one-field rule (a search or filter outcome types an input that matches exactly one field) [PLAN, Gate 0 results; Cost per PR].

### Preregistration before every scored run

The G9 rerun's rule was committed on its own, before the run, and the run's receipt is compared against that commit [P]. It fixed the population (138 behaviour faults, the 16 build or start breaks scored on a separate line, `nj-29` listed but counted in no rate), the primary metric (pooled catch rate of at least 80%), three clauses every fixture must meet (each seeded state has a caught fault, a wrong-field fault is caught, the fixture's Wilson upper bound is not below 80%), and the verdict line [P]. Gate 1 and Gate 1b were also governed by a preregistration plus addenda committed to a local timestamped repo before the results they govern [PLAN, Gate 1 results].

### Mechanical defect confirmation from history

Gate 1 replays real history instead of planted faults. A merged pull request that a later change fixed counts as a confirmed defect only when it is confirmed mechanically: the fix's own test fails at the PR merge and holds at the fix, on lines the PR wrote [PLAN, Gate 1 results]. No model judges whether the defect existed. 215 merged PRs were mined and 16 incomplete deliverables confirmed this way; 12 were frontend and 10 were in scope [PLAN, Gate 1 results].

### Ticket-only spec agents

For each confirmed defect, a spec agent wrote outcomes from the original ticket alone, at the commit before the PR, and the product check was run at the PR merge and at the fix [PLAN, Gate 1 results].

### Data-contract variant

Gate 1b re-ran the four pairs that Gate 1 could not reach, with the ticket plus a data-contract appendix describing the backend data shapes. Appendices were written from code at the commit before each change only. The leak check found 0 identifiers absent at that commit; one pair's appendix was rewritten after its first writer saw the PR's diff [PLAN, Gate 1b].

## Gate 0: harness readiness, no agent runs except G9

| # | Test | Result | Numbers | Source |
|---|---|---|---|---|
| G1 | self-test on macOS and Linux | MET | green on macOS and Ubuntu, 3 CI runs; fixed a test backlog race, a reap race and a 35 s `getfqdn` stall | PLAN, Gate 0 results |
| G2 | fixtures hold, controls fail | MET | Next.js, FastAPI, monorepo, CLI: 27 checks, every control fails, no server left | PLAN, Gate 0 results |
| G3 | flakiness | MET | 150 of 150 runs held, 30 per fixture, load 5 to 16 (Wilson 95% 97.5 to 100, computed here) | PLAN, Gate 0 results |
| G4 | seeded faults, hand-written contracts | NOT MET | 84 of 155 caught (54.2%), 56 missed (36.1%), 15 no signal; mark was at least 80% caught and at most 10% false PASS per fixture | R |
| G5 | environment failures | MET after a fix | a server that died mid-run read FAILS or holds; now CANNOT RUN (12 checks) | PLAN, Gate 0 results |
| G6 | signed-in page | MET | holds with the test account, BLOCKED without it | PLAN, Gate 0 results |
| G7 | two worktrees at once | MET | 10 of 10 rounds (50 of 50 extended) | PLAN, Gate 0 results |
| G8 | cost | MET | Next.js fixture 430 to 490 MB cold, 320 MB warm, under 15 s | PLAN, Gate 0 results |
| G9 | seeded faults, spec-agent contracts | first run MET corpus-wide, NOT MET per fixture; rerun MET under a preregistered rule | see below | PLAN, G9R, P |

The plan's Gate 0 results table is dated 2026-09-29 and macOS; the G9 rerun came after it. This page does not claim G1 to G3 and G5 to G8 were re-run at v0.13.0.

### G4 per fixture (hand-written contracts)

| Fixture | Faults | Caught | Missed | No signal | Catch rate | False-PASS rate | Mark |
|---|---|---|---|---|---|---|---|
| cli | 32 | 21 | 11 | 0 | 65.6% | 34.4% | NOT MET |
| fastapi | 32 | 16 | 15 | 1 | 50.0% | 46.9% | NOT MET |
| monorepo | 30 | 15 | 10 | 5 | 50.0% | 33.3% | NOT MET |
| nextjs | 30 | 12 | 11 | 7 | 40.0% | 36.7% | NOT MET |
| signin | 31 | 20 | 9 | 2 | 64.5% | 29.0% | NOT MET |
| all | 155 | 84 | 56 | 15 | 54.2% | 36.1% | |

Source: R, "Per fixture". On the 138 behaviour faults the same run caught 83, which is 60.1% (G9R, "G4 hand-written contracts", pooled BEFORE row; Wilson 95% 51.8 to 67.9, computed here).

### G9 per fixture (spec-agent contracts), first run and rerun

All faults, caught / n:

| Fixture | First run | Rerun (pass 1) |
|---|---|---|
| cli | 30 / 32 (93.8%) | 30 / 32 (93.8%) |
| fastapi | 29 / 32 (90.6%) | 29 / 32 (90.6%) |
| monorepo | 21 / 30 (70.0%) | 22 / 30 (73.3%) |
| nextjs | 21 / 30 (70.0%) | 21 / 30 (70.0%) |
| signin | 26 / 31 (83.9%) | 27 / 31 (87.1%) |
| all | 127 / 155 (81.9%), missed 11 (7.1%) | 129 / 155 (83.2%), missed 11 |

Source: G9R, "first run vs rerun: per fixture". The first-run row also appears in PLAN, Gate 0 results.

Preregistered primary population, behaviour faults only (breaks_run false, without `nj-29`), rerun pass 1 [G9R, PREREGISTERED section; rule in P]:

| Fixture | Caught | Rate | Wilson 95% |
|---|---|---|---|
| cli | 29 / 31 | 93.5% | 79.3 to 98.2 |
| fastapi | 29 / 30 | 96.7% | 83.3 to 99.4 |
| monorepo | 22 / 25 | 88.0% | 70.0 to 95.8 |
| nextjs | 21 / 23 | 91.3% | 73.2 to 97.6 |
| signin | 27 / 29 | 93.1% | 78.0 to 98.1 |
| pooled | 128 / 138 | 92.8% | 87.2 to 96.0 |

The report's verdict line: `PREREGISTERED VERDICT: MET`, with all five fixtures satisfying the state, wrong-field and rate clauses [G9R].

Two statements that qualify that verdict:

- The primary-rate rule was written after the first G9 run's results were known. Run over the saved first-run results it gives 126 of 138 (91.3%, Wilson 95% 85.4 to 95.0), so the rule does not depend on the later harness fix [P, Disclosures]. It was committed before the rerun.
- Under the original G9 mark (80% of all planted faults, per fixture) the rerun still falls short on two fixtures: monorepo 22 of 30 (73.3%) and nextjs 21 of 30 (70.0%) [G9R]. Those totals include the break faults, which the preregistered rule scores on a separate line.

Secondary line, build or start broken and not passed: 15 of 16 break faults, NOT MET. The split is FAILS-type 1, CANNOT RUN 14, holds 1 (`fa-21`, a stale version pin the harness never installs) [G9R; R, notes on individual faults]. Under the rule a CANNOT RUN on a build or start break is not a catch [P]. 14 of the 15 no-signal faults in the rerun are build or start breaks [G9R, "no signal"]; the remaining one is `nj-29`, a harness artifact (Turbopack rejects a symlinked `node_modules`), listed and counted in no rate [P].

Verdicts that changed between the first run and the rerun: 2 faults, `mr-08` (a 404 home page) and `si-21` (a 405 on the sign-in address), both from CANNOT RUN to FAILS on every outcome [G9R, "verdict changed"]. The change is attributed to the probe fix in `f588d5e`, which counts any HTTP answer as the server being up [C]. The preregistration's unfixed-harness comparison and the repeat runs of changed faults are not in the files used for this page (NOT MEASURED here).

What is still missed by the spec contracts, rerun: 11 faults, cli-11, cli-18, fa-15, fa-21, mr-09, mr-10, mr-23, nj-20, nj-26, si-04, si-13 [G9R, "missed"]. By category (all fixtures, rerun): stale deploy or wrong build 3 of 8 caught, crash on edge case 4 of 6, works in dev but not on the production build 5 of 7, wrong field displayed 5 of 6; build or start breaks 1 of 15 (14 no signal) [G9R, per category, all fixtures].

## Gate 1: replay of real escaped defects

Result: 0 of 10 confirmed frontend defects caught (Wilson 95% 0 to 28%). The mark was at least 7 of 10: NOT MET [PLAN, Gate 1 results].

| What happened | Pairs | Why | Source |
|---|---|---|---|
| Every outcome CANNOT RUN at the buggy and at the fix commit | 4 | the defect sits behind backend data (a realtime socket, a streaming endpoint) that a ticket-only, black-box outcome cannot reach | PLAN, Gate 1 results |
| Every outcome holds at the buggy commit | 4 | outcomes checked what the PR description promised, not the specific defect the later fix's tests exposed | PLAN, Gate 1 results |
| Not run | 2 | owner decision; counted as not caught | PLAN, Gate 1 results |

The clean side (outcomes run on PRs with no defect, to measure false FAILs) was not scored: 4 of 12 contracts were written and none were scored, because the catch mark had already failed [PLAN, Gate 1 results]. The plan's false-FAIL mark for Gate 1 (upper 95% bound at most 15% on clean PRs) is therefore NOT MEASURED.

## Gate 1b: the same four unreachable pairs, ticket plus data contract

Result: 0 of 4 caught (Wilson 95% 0 to 49%, computed here). The reading was fixed in advance for 0: the approach does not catch these defects even with the data contract [PLAN, Gate 1b]. The pairs are lettered here; the plan identifies them by private unit numbers.

| Pair | At the PR merge | At the fix | Counted | Source |
|---|---|---|---|---|
| A | NO RESULT, harness 621 MB, over the 600 MB cap | NO RESULT (601 MB) | not caught | PLAN, Gate 1b |
| B | 4 hold | 2 FAIL | not caught; false FAIL on the fix | PLAN, Gate 1b |
| C | 2 FAIL | NO RESULT (640 MB) | not caught; fix unconfirmed | PLAN, Gate 1b |
| D | 1 FAILS | the same FAILS | not caught | PLAN, Gate 1b |

What changed with the data contract: every unit reached its real screens, which Gate 1 could not. What did not change: the catches. Two units were lost to the harness memory cap (the agents' document-parsing checks peak at 601 to 661 MB), a measurement failure that still counts as not caught. Of the two units that were measured, neither caught the defect [PLAN, Gate 1b].

## What worked

- The checker is mechanically sound. Gate 0 G1 to G3 and G5 to G8 are met [PLAN, Gate 0 results]. The plan summarises this as 0 false FAILs on 16 fix-commit runs, with every holds backed by an exercised control [PLAN, Plan v2]. For a count of 0 in 16, the Wilson 95% upper bound is 19.4% (computed here).
- Gate 1 recorded 0 false FAILs on fix commits and an exercised control behind every holds, with memory inside the owner's split cap (harness at most 507 MB, app at most 265 MB) [PLAN, Gate 1 results]. Gate 1b recorded one false FAIL on a fix commit (pair B) [PLAN, Gate 1b]. The plan's "16 fix-commit runs" line does not say whether Gate 1b is included, so this page keeps the two gates apart.
- Controls: every Gate 0 G2 control fails [PLAN, Gate 0 results]. A control that passes is reported NOT PROVEN, not holds, and the self-test checks it (`benchmark/gates/acceptance.py`, self-test case "a control that passes is NOT PROVEN").
- Spec-agent outcomes caught planted faults in small apps: 128 of 138 behaviour faults [G9R]. Against the hand-written contracts on the same corpus, the spec contracts caught all 13 faults in the loading, empty and error category (hand-written: 5 of 13) and all 8 wrong-sort faults (hand-written: 0 of 8) [G9R, per category, all fixtures].
- Environment failures are separated from product failures. A server that dies mid-run now reads CANNOT RUN (G5, fixes `d89238e` and `3c078b3`), and a CANNOT RUN names its reason (`5c5e194`, `b02dd52`) [C].

## What did not work, and the measured reasons

- Gate 1, 0 of 10. Four pairs could not be reached at all (CANNOT RUN at both commits): the defect sits behind backend data that a black-box outcome written from a ticket cannot reach. Four pairs held at the buggy commit: the outcomes checked what the PR description promised, not the failure that later happened. Two were not run [PLAN, Gate 1 results].
- Gate 1b, 0 of 4. Reachability was fixed by the data contract and catches were not. One pair gave a false FAIL on the fix, one failed identically before and after the fix, and two lost a run to the harness memory cap (pair A both runs, pair C the fix run) [PLAN, Gate 1b].
- The plan's reading: the gap is not the checker but the source of the expectations. A PR description says what was intended, not the failure that later happened, and a model writing outcomes from it tests the intent it was given [PLAN, Plan v2].
- G4, hand-written contracts, NOT MET. Typical reasons the contract did not see a fault, from the Why column of R: only a line count and a substring are checked, never the row order (wrong sort); the query typed is already lowercase, so removing the lowercase step never changes a match; an environment variable such as `NODE_ENV` is never set, so the production branch never runs; a control absorbs the one state that would reveal the fault (`fa-24`, `fa-30`).
- Build or start breaks are rarely a catch. 14 of 16 reported CANNOT RUN, which the preregistered rule does not count as a catch [G9R, P].
- Memory. The harness's own peaks run 400 to 660 MB, and the document-parsing checks exceed the 600 MB budget [PLAN, Plan v2]. The build of the private app peaked at up to 1,490 MB [PLAN, Plan v2, Costs so far].

## Limits

- The fault runs used one machine (macOS), one run per fault; repeats exist only for the faults the preregistration names [P, Disclosures]. CI on macOS and Ubuntu covers the self-test only.
- The fixtures are five small apps. The faults were written and committed before any contract was read [R], but they are planted, not escaped production defects.
- The spec agents' state checklist and one-field rule came from the two hand-broken versions of the Next.js fixture that the contract missed in an earlier live test: a "no orders yet" message that flashes while the list loads, and a search filter that matched the total instead of the order id [PLAN, Cost per PR]. The corpus contains faults of those kinds, so G9 measures contracts written with those defect kinds in mind, not an agent blind to them.
- The first-run and rerun G9 figures differ by more than the probe fix: `acceptance.py`, `drive.mjs` and `hooks/state.py` changed between `72b3b52` and `5871de2` [P, Reported, not scored].
- Gate 1 and Gate 1b used one private codebase, 10 and 4 pairs. The intervals are wide: 0 to 28% and 0 to 49%. The plan wanted two repos [PLAN, Gate 1].
- Gate 1 outcomes were written from PR descriptions, not by the person who owns the ticket before work starts. The plan proposes a prospective test with person-written outcomes (Phase B). No result for it is in the sources used here.
- The built-in `/verify` was meant as the comparison arm. The Gate 1 and Gate 1b results in the plan report no such arm, so this page makes no comparison with it (NOT MEASURED).
- The paired pilot (Gate 2) was not run. The plan recommends against running it [PLAN, Plan v2].
- The cost and memory figures are from the versions the plan names (v0.9.0 for the production-build figures). Releases through v0.13.0 changed the harness, so those figures are not claimed for the current version.

## Cost

| Figure | Value | Source |
|---|---|---|
| One `verify product` run on a built tree (v0.9.0) | 8.9 s and about 335 MB | PLAN, Cost per PR |
| Full `verify done` (typecheck, tests, build, product check) | 361 MB and 18.5 s | PLAN, Cost per PR |
| Next.js dev server alone | 481 MB | PLAN, Cost per PR |
| Uncapped `next build` against one worker | 829 MB against 401 MB | PLAN, Cost per PR |
| Live A/B on the Next.js fixture: 2 tasks, 2 repeats, 8 headless runs, Sonnet 5.5 | $0.84 in total | PLAN, Cost per PR |
| Cost per run, with the check minus without | -$0.02 median (range -$0.03 to +$0.06), within run-to-run noise | PLAN, Cost per PR |
| Minutes per run, with minus without | +0.03 median (range -0.13 to +0.24) | PLAN, Cost per PR |
| Defects caught in that A/B | 0: no run shipped a broken app, with or without the check | PLAN, Cost per PR |
| Hand-broken versions of the same app (8) | contract caught 6, hidden suite caught 8 | PLAN, Cost per PR |
| Spec agent, per ticket, Gate 0 | 131k to 182k tokens, 7 to 35 minutes; dollar cost not measured | PLAN, Gate 0 results |
| Spec agent, per ticket, Gate 1 | 131k to 306k tokens | PLAN, Plan v2 |
| Gate 1b in total | about 2.5 million agent tokens | PLAN, Gate 1b |
| G9 rerun | wall time 6,200 s (baseline plus faults), summed verify time 5,828 s, peak memory of any run 513 MB | G9R |
| Baseline, 67 real pull-request tasks on one machine, Aug 27 to Sep 29, 2026, API list prices | median $14, p75 $50, p90 $109; median 16 active minutes, p75 33, p90 160 | PLAN, Cost per PR |
| Proposed budget added by the product check, per PR (a proposal, not a result) | target up to $3, 4 active minutes, under 600 MB per run; ceiling $7, 7 minutes, 800 MB | PLAN, Cost per PR |

Not measured: the spec agent's dollar cost, and a cold start on a real repository, which the plan expects to be slower than the fixture [PLAN, Cost per PR].

## Not measured, collected

- The built-in `/verify` comparison arm (Gate 1, Gate 1b).
- The Gate 1 clean-PR false-FAIL rate.
- Repeat runs and the unfixed-harness comparison for the G9 rerun.
- Gate 0 figures at v0.13.0, other than the self-test.
- Phase B (person-written outcomes) and Gate 2 (paired pilot).
- Spec-agent dollar cost; cold-start cost on a real repository.

## Reproduce the public parts

These are taken from the scripts and were not re-run to write this page.

```bash
bash selftest.sh
G4_OUT=/path/for/output bash tests/gate0/g4.sh
G9_OUT=/path/for/output bash tests/gate0/g9.sh
```

`g9.sh` refuses to start without `G9_OUT`. `tests/gate0/g9_report.py` computes the preregistered verdict from that directory. Gate 1 and Gate 1b cannot be reproduced from this repository.
