---
name: using-worktrees
description: Use before starting feature work that needs isolation, or before running agents in parallel. One writer per worktree, always.
---

# Using Worktrees

## The rule

**One writer per worktree. Always.**

Parallel readers cannot conflict — fan them out freely. Parallel writers conflict the moment
they touch overlapping files or a shared lockfile, and there is no coordination scheme that
makes it worth the debugging.

## Check for existing isolation first

You may already be in one. `git rev-parse --git-dir` differing from `--git-common-dir` means
you are in a worktree. Do not nest.

## Create

```bash
git worktree add ../wt-<feature> -b feat/<feature>
cd ../wt-<feature>
# install deps, then establish a clean baseline BEFORE touching anything:
./bin/verify done
```

**Baseline first.** If gates are already red on arrival you need to know that now, not after
your change, or you will spend the session debugging someone else's failure.

## Parallel-safety is a graph question

Two tasks may run concurrently only when their **write-sets are disjoint** *and* the module
dependency graph shows no edge between them. Derive this from the graph, not from intuition:

```bash
./bin/verify blast <symbol>
```

If two tasks in a wave want the same file, the decomposition was wrong. Re-split along the
graph's real module boundaries rather than coordinating access.

## One integrator

Exactly one actor merges branches, resolves conflicts, and touches shared manifests and
lockfiles. A lease coordinates *intent*; it does not authorize a side effect.
