---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing a fix. Forces root cause before remedy.
---

# Systematic Debugging

```
NO FIXES WITHOUT ROOT CAUSE FIRST
```

A fix that works without a understood cause is a coincidence you will pay for later.

## Phase 1 — Investigate

- Read the **entire** error. Not the first line. The stack, the cause chain, the exit code.
- **Reproduce it reliably.** A bug you cannot trigger on demand is not yet a bug, it is a
  rumor.
- Check what changed recently. `git log`, `git diff` against the last known-good state.
- Trace the data backward from the symptom to its source.
- Use the graph: `./bin/verify blast <symbol>` tells you what actually reaches this code.

## Phase 2 — Compare against working

Find a case that works. Diff it against the failing one. The difference is your suspect
list, and it is usually short.

## Phase 3 — One hypothesis at a time

State the hypothesis. Design the **smallest** test that distinguishes it from the
alternatives. Run it.

Do not bundle fixes. Changing three things and seeing green tells you nothing about which
one mattered — and leaves two unexplained changes in the diff.

## Phase 4 — Fix

Write a failing test that reproduces the bug. Fix. Verify. `./bin/verify done`.

## The three-strike rule

**If three fixes have failed, stop and question the architecture.**

Three failed fixes is not a hard bug; it is evidence your model of the system is wrong.
A fourth attempt from the same wrong model will also fail. Go back to Phase 1 with the
assumption that something you "know" is false.

## Flaky is a diagnosis, not a fix target

If a test fails intermittently: reproduce it against a clean base commit. If it fails there
too, **your change did not cause it** — quarantine it, open an issue, name the race. Never
add a retry, never raise a timeout, never shorten a sleep to dodge it. *A test that needs
three retries to pass is failing, with extra steps.*
