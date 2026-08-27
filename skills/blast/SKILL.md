---
name: blast
description: Compute the blast radius of a symbol from the code graph before changing it. Use before editing any shared function, class, or endpoint.
---

# Blast Radius

```bash
./bin/verify blast <symbol>
```

Report before editing:

- Direct callers, with `file:line`.
- Whether the change crosses a module or language boundary.
- **Whether DI or reflection could hide callers.** Frameworks that pass functions by
  reference (FastAPI `Depends`, NestJS providers, Spring injection) produce *reference*
  edges, not *call* edges — a callers query under-reports them. Union both before trusting
  the set.
- Which tests cover those call sites: `./bin/verify tests`.

**Zero callers is a hypothesis, not permission to delete.** Confirm with grep before acting.

Report the impact set, then wait. Do not edit in the same step.
