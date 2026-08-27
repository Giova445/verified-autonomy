---
name: finishing-a-branch
description: Use when implementation is complete and gates are green, to decide how the work gets integrated.
---

# Finishing a Branch

## Precondition

`./bin/verify done` exits 0. If it does not, you are not finishing anything.

## Deliver by PR

Branch and pull request. Never push to main. Never merge or approve your own PR — the
review is the point, and a bot approving a bot is not review.

Every hosted coding agent converged on this independently: PR is the write surface, human
review is the structural checkpoint rather than a policy one.

## Keep the diff reviewable

Review quality collapses with size. One task per PR. If the diff is over a few hundred
lines, split it — the reviewer's attention is a real budget and you are spending it.

## The PR body

- What changed and why.
- **The commands you ran and their results.** Not "tests pass" — the command and the exit
  code.
- Blast radius: what else reaches this code.
- Anything you decided under ambiguity (from the ledger's Rulings).
- Migration or env requirements.

## Then it is not over

CI re-runs the same gates independently. Your local green is a claim made inside a trust
boundary; CI's green is the fact. If CI fails after your local green, that gap is the
finding — investigate it rather than re-running.

## Cleanup

Once merged: remove the worktree, delete the branch. Stale worktrees with uncommitted work
are where changes go to be lost.
