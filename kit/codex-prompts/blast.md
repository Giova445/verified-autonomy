Compute the blast radius of $1 BEFORE changing anything.

```
codegraph query "$1"
codegraph context "callers of $1"
```

Then state:
- Direct callers, with file:line.
- Whether this crosses a module or language boundary.
- Whether DI/reflection could hide callers. This repo has 106 `Depends()` sites — FastAPI
  passes functions by reference, so `calls` edges under-report. Union with references.
- Which tests cover those call sites (`./bin/verify tests`).

Zero callers is a HYPOTHESIS, not permission to delete. Confirm with grep before acting on it.

Do not edit yet. Report the impact set, then wait.
