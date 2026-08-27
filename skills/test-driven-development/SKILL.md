---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code. Enforces that the test is written first and proven to fail for the right reason.
---

# Test-Driven Development

## The law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Wrote the code first? Delete it. Not "keep it as reference", not "adapt it while writing the
test" — delete, then implement fresh from the test. Code you are looking at while writing a
test contaminates the test into describing what you built rather than what you need.

## RED must be proven, not asserted

The value of test-first collapses if the test would have passed anyway. So:

1. Write the test.
2. **Run it at the pre-implementation state.**
3. Confirm it fails **for an assertion reason.** An `ImportError` or collection error proves
   the file does not parse — it proves nothing about the test.
4. Confirm it fails for the *right* reason. A test failing on a typo you then "fix" taught
   you nothing.

Only then write implementation.

## Why the third step matters more than it looks

A hook can prove a test failed. It cannot prove it failed for the intended reason. That gap
is real and unclosable by tooling — it is why mutation testing and adversarial review exist
downstream. Do not treat a red test as self-evidently a good test.

## Rationalizations, answered

| Excuse | Reality |
|---|---|
| "I'll test after" | Tests written after pass immediately. You never watched it fail, so you never learned whether it can. |
| "It's too simple to test" | Then the test is one line. Write it. |
| "I already know it works" | Confidence is not evidence. |
| "The test is hard to write" | That is the design telling you something. Listen to it. |
| "I'll delete the code and rewrite from the test" *(while looking at it)* | Delete means delete. |

## Test quality, not test count

A test that passes whether or not the code is correct is worse than no test: it is a false
signal that costs runtime forever. Before accepting your own test, name one mutation to the
production code that would survive it. If you can, the test is too weak.

## Mechanically backed

`./bin/verify` runs the suite; the `Stop` hook refuses the turn while it is red. The cheat
scanner diffs for skipped tests, deleted assertions, `|| true`, and retry-to-green — the
documented ways a failing test gets made to disappear instead of fixed.
