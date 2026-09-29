---
name: gate
description: Run the repo's gates and product contract and read the verdict. Use before saying work is done, or when the Stop hook refuses.
---

# Gate

```bash
./bin/verify done
```

Report the command and its exit code as they are. A stop is refused while an engineering gate
fails or a product outcome is not established. The refusal names each open outcome in the
user's words.

| Verdict | Meaning | Do |
|---|---|---|
| `holds` | the check passed, and its control, if any, failed | nothing |
| `FAILS` | the check ran and the product did not do it | fix the code, not the check or the expectation |
| `NOT PROVEN` | the control passed too, so the check cannot tell broken from working | make the check stricter |
| `CANNOT RUN` | the check exited 75, or the app would not start | read `.claude/evidence/server-*.log`, fix `start` and `ready` |
| `BLOCKED` | a variable declared in `needs` is not set | name it in a blocked report; a person supplies it |
| `NO VERDICT` | the check ran out of time | make it faster, or raise `ACCEPT_TIMEOUT` |
| `WRONG BUILD` | the environment runs a different commit | deploy this commit, then re-run |
| `REFUSED` | the outcome lacks a name, an `expect` or a `check` | complete it |

After three refusals in a row, write a blocked report: the failing gate or outcome, the
command and exit code, what you tried, and the decision a person must make. Then stop.

## Write the expectation first

Before building, add what the user expects as an outcome in `.claude/acceptance.json`, in
their words, with a check that drives the running product and a control that must fail. Run
`./bin/verify product` and watch the outcome fail. That failure defines the work.

Add a unit test only where the product check cannot isolate the logic: a parser, a rounding
rule, a state machine.
