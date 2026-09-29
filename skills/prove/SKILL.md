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
| `CANNOT RUN` | the app would not start, or the check exited 75 | read `.claude/evidence/server-*.log` |
| `BLOCKED` | a credential in `needs` is not set | say which; a person supplies it |
| `NO VERDICT` | it ran out of time | say so; do not raise the timeout to get a pass |

## Where expectations come from

From the person or the ticket, never invented. If the change adds behaviour a user will see,
add one outcome for it in `.claude/acceptance.json`, quoting the request in `expect`, and say
in your report that you added it. Evidence per check is in `.claude/evidence/<name>.log`;
browser checks leave a screenshot in `.claude/evidence/shots/`. Look at it.
