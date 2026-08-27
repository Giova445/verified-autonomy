---
name: gate
description: Run the project gate ladder and report the exact command and exit code. Use before claiming any work is complete.
disable-model-invocation: false
---

# Gate

```bash
./bin/verify preflight
./bin/verify done
```

Report the **exact command and exit code**. Do not paraphrase a pass.

If the graph is unavailable, say so — you are at grep precision and every downstream claim
is weaker.

If red: fix the code. Never the test, never the gate, never a retry. Three attempts, then a
blocked report.
