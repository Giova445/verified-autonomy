---
name: prove
description: Prove a change works for its user before opening a PR. Runs the repo's declared product outcomes against the running app, once, and reports each verdict. Use before a PR, or when asked to verify or prove a change.
---

# Prove

Run once, before you open a PR. Not after every edit.

```bash
./bin/verify done      # tests that passed when the repo was armed, then the product outcomes
./bin/verify product   # the product outcomes only
```

Report each outcome's verdict and the exit code as they are. Do not loop: if something fails,
fix it once and re-run; if it still fails, say what failed and hand it back.

| Verdict | Meaning | Do |
|---|---|---|
| `holds` | the check passed, and its control failed | nothing |
| `FAILS` | the app did not do what the user expects | fix the code, not the check or the expectation |
| `NOT PROVEN` | the control passed too | the check cannot tell broken from working; sharpen it |
| `CANNOT RUN` | it could not be checked; the line's `reason=` says why | act on the reason below |
| `BLOCKED` | a credential in `needs` is not set | say which; a person supplies it |
| `NO VERDICT` | it ran out of time | say so; do not raise the timeout to get a pass |

A `reason` names the step that could not run, not a proven cause. The fix-once rule applies to all of them.

| `reason` | Do |
|---|---|
| `build_failed`, `start_failed` | the change broke the project's own build or start: read `.claude/evidence/build-*.log` or `server-*.log`, fix the code, never retry blindly |
| `environment` | the machine or the port, not the change: report it, rerun once |
| `check_cannot_run` | the check's own dependency is missing (a browser, a tool): install it or report it |
| `contract_invalid` | fix `.claude/acceptance.json` |
| `harness_error` | report the exception in its detail line |
| `unspecified` | the harness named no known reason: read the detail line, report it |

## Where expectations come from

From the person or the ticket, never invented. If the change adds behaviour a user will see,
add one outcome for it in `.claude/acceptance.json`, quoting the request in `expect`, and say
in your report that you added it. Evidence per check is in `.claude/evidence/<name>.log`;
browser checks leave a screenshot in `.claude/evidence/shots/`. Look at it.
