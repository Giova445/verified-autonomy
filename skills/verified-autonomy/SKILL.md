---
name: verified-autonomy
description: Use when working in a repo that has .claude/gates.json — explains the mechanical gate contract, what "done" means, and why the Stop hook may refuse to let the turn end
---

# Verified Autonomy

This project enforces completion mechanically. You are not being asked to be careful; a
hook checks.

## Done

`./bin/verify done` exits 0. Nothing else counts. Not "tests look right", not "should work".

It needs two things. The engineering gates in `.claude/gates.json` are green, and every
outcome in `.claude/acceptance.json` holds against the running product. With no contract,
`done` refuses: green code is not a delivered product. When it refuses it names each open
expectation. Continue with those, or say what blocks one.

A `Stop` hook runs this. If any gate is red the hook exits 2, the turn does not end, and
stderr comes back to you as the reason. You cannot talk your way past it — deterministic
results are facts, and per the docs an exit-2 hook wins even over a JSON `allow`.

## The rules

1. **Fix the code, never the gate.** Never weaken, skip, or delete a test. Never add
   `|| true`, raise a timeout, or add a retry to force green. A cheat scanner diffs for
   exactly these.
2. **Never edit your own guardrails** — `bin/verify`, `.claude/gates.json`,
   `.claude/hooks/**`, `.github/workflows/**`. If a gate is
   wrong, say so and stop.
3. **Resolve unknowns, never infer them.** Read the code or ask.
4. **Know the blast radius first** — `./bin/verify blast <symbol>`. Zero callers is a
   hypothesis: DI and reflection are invisible to a static graph.
5. **Branch and PR only.** Never push to main, never merge or approve your own PR.
6. **No `Co-Authored-By` trailer on any commit.** The `co-author` gate refuses the branch.

## The workflow

Each phase has a skill. **Where a rule can be enforced by a machine, it is** — the third
column is what makes this different from a skills library.

| Phase | Skill | Mechanically backed by |
|---|---|---|
| Understand | `brainstorming` | open assumptions block `verify preflight` |
| Design | `writing-plans` | — (judgment) |
| Isolate | `using-worktrees` | deny-list blocks pushes to main |
| Implement | `test-driven-development` | cheat scanner: skips, deleted assertions, `\|\| true`, retries |
| Execute | `executing-plans` | ledger on disk survives compaction |
| Debug | `systematic-debugging` | flaky detection vs clean base commit |
| Delegate | `dispatching-agents` | — (judgment) |
| Verify | `gate` | **`Stop` hook exit 2 while red** |
| Impact | `blast` | graph query, fails loudly when no index |
| Review | `requesting-review` | reviewer cannot clear a red gate |
| Ship | `finishing-a-branch` | deny-list blocks self-merge; CI re-runs gates |
| Audit rules | `pressure-testing` | deterministic scoring, not an LLM judge |

## Loop

```bash
./bin/verify preflight        # graph health, open assumptions
./bin/verify blast <symbol>   # before editing
./bin/verify fast             # after each edit
./bin/verify done             # exit 0 or you are not done
```

## When blocked

Budget is 3 attempts per failing gate. On exhaustion, stop and report: the failing gate with
command and exit code, what you tried and why each attempt failed, the specific decision a
human must make, and a recommendation with trade-offs. A vague "I'm blocked" is just false
success wearing a different hat.
