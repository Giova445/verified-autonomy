# Second-harness pilot — Node 24 / Jest 30.4.2

The checklist claims its properties are harness-agnostic. That claim is worth nothing until
it is run somewhere genuinely different, so item 1 (verification integrity) was piloted on
Node/Jest against the source project's Python/pytest.

**The pilot found a real defect in the shipped gate.** That is the point of piloting.

## The attack, ported

The pytest attack monkeypatched `_pytest.runner.CallInfo.from_call` from a package
`__init__.py`. The Jest analogue is narrower and nastier: `setupFilesAfterEnv` in
`package.json` wraps `expect` in a Proxy whose every method is a no-op.

```js
const realExpect = global.expect;
global.expect = (...a) => {
  const e = realExpect(...a);
  return new Proxy(e, { get: (t, p) => (typeof t[p] === 'function' ? () => {} : t[p]) });
};
```

Confirmed live: `add(a,b) { return 999; }` with `expect(add(1,2)).toBe(3)` reports
**`Tests: 1 passed`, exit 0**. No file a denylist would name — it is referenced from
`package.json`, which every Node project must have.

## What transferred, and what did not

The **property** transferred exactly: break the artifact, re-run the identical verification,
it must now fail. The **implementation of the sabotage did not**, and the difference decides
whether the gate works.

Measured with a **correct** implementation and the attack active:

| sabotage style | sabotaged run | what the gate concludes |
|---|---|---|
| **throw** (`throw new Error(...)` / `raise AssertionError`) | exit 1 | "suite works" — **certifies a COMPROMISED harness. MISS.** |
| **value** (`return "__SABOTAGE_CONTROL__"`) | exit 0 | force-pass correctly detected |

**Why:** a thrown exception fails the test through a channel the neutered assertion never
touches. The runner catches it regardless of whether `expect` still works. A wrong *value*
only surfaces if the assertion is actually evaluated.

> **Sabotage must fail through the same channel the tests assert through.**

This is the transferable rule, and it is not obvious from the Python case alone — there the
throw happened to work because the attack sat at the *runner* level, so it swallowed the
raise too. An attack one layer lower would have walked straight past it.

## The fix, and a second bug it caused

`bin/holdout` was switched from `raise AssertionError` to returning a sentinel. The selftest
immediately caught a new bug: value-sabotage was rewriting `conftest.py` as well, **which
disabled the attack the control exists to detect** — the run then failed for an ordinary
reason and read as "suite works". Hook-hosting files (`__init__.py`, `conftest.py`,
`sitecustomize.py`, `usercustomize.py`) are now excluded from sabotage for the same reason
`__init__.py` already was.

After both changes: `bin/holdout selftest` 16/16, force-pass matrix 7 passed / 1 skipped.

## Pilot verdict on item 1

**The property holds across harnesses. The naive implementation does not.** A checklist that
says "sabotage the artifact" without saying *how* would have produced a gate that passes its
own tests and misses assertion-level neutering — which is exactly the failure the checklist
was written to prevent.

## Not piloted

Items 2–8 were not run against Jest. This pilot covers item 1 only, so the checklist remains
**provisional**, per its own step 4.
