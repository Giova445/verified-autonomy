---
name: dispatching-agents
description: Use when work can be split across multiple agents. Explains when parallelism pays, when it does not, and how to keep writers from colliding.
---

# Dispatching Agents

## Default to one agent

Anthropic's measurement: agents use ~4× the tokens of a chat interaction, multi-agent
systems ~15×. That is only worth paying when the task can absorb it.

Before adding a second agent, answer: **what deterministic check would catch the failure
this agent is meant to catch?** If one exists, build the check instead. It will be cheaper,
faster, and more reliable — cheap deterministic detectors beat LLM judges on exactly this
kind of question.

## The read/write asymmetry

| Work | Parallel? |
|---|---|
| Reading, searching, analysis | **Yes — cannot conflict by construction** |
| Writing | **One per worktree, non-overlapping file scope** |

Fan out readers freely. A read-only explorer that burns 50k tokens and returns a 2k-token
digest is often worth it for the *compression* alone, not the parallelism.

## Dispatching well

- Each agent gets a **self-contained brief** — never your session history, never the whole
  plan. Your context contaminates their judgment.
- Declare the file scope in the brief. It is the parallel-safety contract.
- Nested spawning is usually waste: a worker that spawns its own reviewer duplicates the
  review the coordinator already dispatched.
- Match the model tier to the work. Mechanical transcription does not need a frontier model;
  final review does.

## Never trust a completion report

An agent reporting success is a claim, not a fact. Verify independently: check the diff,
check the gates. Roughly half of failing agent trajectories report success — that number is
why this whole architecture exists.

```bash
git diff --stat            # did it actually change anything?
./bin/verify done          # is it actually green?
```
