# Recipe for a built-in /verify: outcomes with controls that must fail

For maintainers of a built-in `/verify`. Seven rules, each with the Gate 0 check or fix that showed it was needed. The measurements are on [results.md](results.md); tags in brackets (R, P, G9R, PLAN, C) are defined there.

One rule of reading first. These rules make a verifier that is sound: it does not pass a broken app, and it does not blame the change for a failure of the machine. They do not make it catch real escaped defects. Outcomes written from the descriptions of real pull requests caught 0 of 10 such defects, and 0 of 4 when the ticket also carried a data contract [PLAN, Gate 1 results and Gate 1b]. Do not read the rules below as evidence that they do.

## The loop

```
declare   an outcome, in the user's words
run       its check against the running app
control   run a control that must fail
report    holds, FAILS, NOT PROVEN, or CANNOT RUN with a reason
```

A minimal outcome (taken from the shape of `tests/gate0/spec/nextjs/.claude/acceptance.json`):

```json
{
  "environments": {"local": {"build": "npm run build", "start": "npm run start -- --port $PORT", "ready": "/"}},
  "outcomes": [{
    "name": "search narrows the list",
    "env": "local",
    "expect": "the user's request, quoted",
    "check": "a command that exits 0 when the app does what the user asked",
    "control": "the same check against an input that must make it fail"
  }]
}
```

| Verdict | Meaning |
|---|---|
| `holds` | the check passed and its control failed |
| `FAILS` | the check failed: the app does not do what the user asked |
| `NOT PROVEN` | the control passed too, so the check cannot tell broken from working |
| `CANNOT RUN` | it could not be checked; carries a reason label |
| `BLOCKED`, `NO VERDICT` | a needed credential is not set; the run ran out of time |

## 1. Declare an outcome in the user's words

State each outcome as the user would, quote the request in `expect`, and write one outcome for each state the request implies: loading, empty, error, filled. A search or filter outcome types an input that matches exactly one field, and its control uses an input that must match nothing.

Evidence. Hand-written contracts caught 84 of 155 planted faults (54.2%), and missed every wrong sort (0 of 8 caught), every wrong field displayed (0 of 6) and most loading, empty and error states (5 of 13) [R, G9R]. Contracts written by a separate agent from the ticket alone, following the state list and the one-field rule, caught 128 of 138 behaviour faults (92.8%, Wilson 95% 87.2 to 96.0), including 8 of 8 wrong sorts and 13 of 13 loading, empty and error faults [G9R].

Limit. The words must come from the person or the ticket. Outcomes written from PR descriptions held at the buggy commit in 4 of 10 real defects, because they checked what the PR promised, not the failure that happened [PLAN, Gate 1 results].

## 2. Run its check against the running app

Build and start the project's own production build, wait for it to be ready, and drive it as a user would: a browser, HTTP or the command line. Check the app this change started, not whatever answers on the port.

Evidence.
- G2 ran 27 checks on four fixtures against live servers; every control failed and no server was left [PLAN, Gate 0 results].
- A port that already accepts connections just before `start` now refuses the run as `environment` instead of checking whatever answers there (`d89238e`) [C].
- G7: two worktrees at once held on separate ports in 10 of 10 rounds [PLAN, Gate 0 results].
- Check the production build, not the dev server. "Works in dev but not on the production build" is a planted fault category (7 faults); the spec contracts caught 5 of 7 [G9R]. A `next dev` server alone was 481 MB, against about 335 MB and 8.9 s for one product check on a built tree [PLAN, Cost per PR].
- Limit: stale deploy or wrong build faults were caught 3 of 8 times, the weakest behavioural category [G9R].

## 3. Run a control that must fail

Every check has a control: the same check pointed at a state that must be rejected. An outcome holds only when the check passes and the control fails. The control also needs a live app: a control that fails because the app died shows nothing.

Evidence.
- G2: every control fails, 27 of 27 checks [PLAN, Gate 0 results]. Gate 1: every `holds` had an exercised control [PLAN, Gate 1 results].
- A server that died during the control left the outcome `holds`. The liveness test now also runs after the control, and an outcome whose app stopped during its check or its control is never `holds` (`3c078b3`) [C].
- The hand-written fastapi contract missed `fa-24` and `fa-30` because its only zero-match request was the control, which is expected to fail, so it absorbed the changed behaviour [R, Why column]. A control must not be the only place a state is exercised.

## 4. NOT PROVEN when the control passes

If the control passes, exits 126 or 127 (not executable, not found), the check is not shown able to fail. Report `NOT PROVEN`, never `holds`, and tell the author to sharpen the check.

Evidence. `acceptance.py` self-test cases "a control that passes is NOT PROVEN" and "a control not found (127) is NOT PROVEN, never able to fail" [C, `benchmark/gates/acceptance.py`]. G2 requires every control to fail [PLAN, Gate 0 results]. A `NOT PROVEN` counts as a catch in the fault runs [R]. How often a control passed in the fault runs is not in the sources used here (NOT MEASURED).

## 5. CANNOT RUN, with a reason, when the app cannot be checked

When the app cannot be checked, say `CANNOT RUN`, never `FAILS` and never `holds`, and name the step that could not run:

| Reason | Meaning |
|---|---|
| `build_failed` | the project's own build exited non-zero or gave no answer in time |
| `start_failed` | `start` exited by itself before `ready`, or `ready` never passed |
| `environment` | the machine or the port: the app stopped or lost its port mid-run, a signal ended `start`, something else already serves there, a reset connection |
| `check_cannot_run` | the check or control exited 75: its own dependency (a browser, a tool) is missing |

The label names the step that could not run, not a proven cause. `contract_invalid` (a `start` with no `ready`) and `harness_error` (the harness raised) also exist. An app that exits by itself with status 0 to 128 during a check is `FAILS`; one ended by a signal, or with a status above 128, is `CANNOT RUN` [C, `3c078b3`].

Evidence.
- G5: a server killed mid-run read `FAILS` or `holds`. It now reads CANNOT RUN, 12 checks; the self-test grew from 40 to 48 checks, 8 of which fail on the old code (`d89238e`, `3c078b3`) [PLAN, Gate 0 results; C].
- A bare CANNOT RUN could mean the change broke the build or the machine failed, so each result now carries a reason (`5c5e194`) and the run log records it (`b02dd52`) [C].
- Chromium on Linux CI reported a reset connection as `ERR_SOCKET_NOT_CONNECTED` about one run in six, which read as a product failure (`1fe8d68`) [C].
- Build or start breaks are mostly CANNOT RUN: 14 of 16 in the G9 rerun. The preregistered rule does not count that as a catch, and the secondary line reads 15 of 16, NOT MET [G9R, P]. The label lets a reader tell a broken build from a broken machine; it does not turn the report into a catch.

## 6. Any HTTP answer means the server is up

A ready URL passes on any HTTP status from 100 to 599, with redirects unfollowed. A refused, reset or unanswered connection is not ready. A 404 home page or a 405 on the sign-in address is a user-visible defect for the outcomes to see, not a reason to refuse to check.

Evidence. In the first G9 run, `mr-08` (a 404 home page) and `si-21` (a 405 on the sign-in address) read CANNOT RUN after the ready timeout on every outcome. After `f588d5e` both read FAILS on every outcome (9 of 9 and 6 of 6) [G9R, "verdict changed"; C]. `d48f9d2` changed the "a ready that never passes" test to a command ready, because a URL that answers 404 now counts as up [C].

## 7. Memory is metered, and NOT MEASURED when it cannot be

Meter the whole process tree (the app, the check runner, the browser) against a budget, print the peak and name the phase that goes over it. This repository's default is 600 MB, set by `VERIFY_MEMORY_MB`. If the meter cannot list child processes or read their footprints, print `memory  : NOT MEASURED` with the reason and record a null peak. Never record 0, and never report only the parent process. If some samples fail, print "peak at least N MB".

Evidence.
- Inside macOS `sandbox-exec` the setuid `/bin/ps` cannot run. The meter returned an empty child list without a word and reported a peak of 13 MB for a tree of 321 MB, a false pass on the memory budget (`59aca69`) [C].
- The first figures summed RSS, which counts Chromium's shared pages several times. On physical footprint, a `next dev` server was 481 MB and an uncapped `next build` 829 MB; one worker brought the build to 401 MB [PLAN, Cost per PR].
- The budget matters: harness peaks ran 400 to 660 MB, and document-parsing checks exceeded 600 MB, and two of the four Gate 1b pairs lost a run to the 600 MB cap [PLAN, Plan v2; Gate 1b].
- G8: the Next.js fixture ran at 430 to 490 MB cold and 320 MB warm [PLAN, Gate 0 results].

## What this recipe does not cover

It does not say where outcomes should come from for real escaped defects. The one hypothesis the data does not rule out is outcomes written before the work, by the person who owns the ticket, with the data contract attached. The plan lists it as an optional prospective test (Phase B), and no result for it exists in the sources used here [PLAN, Plan v2].
