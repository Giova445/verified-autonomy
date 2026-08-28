# CLAUDE.md premise vs mechanical enforcement — audit 2026-08-28
# Reviewed against the Aug 2026 literature. Every citation below names the model generation
# or tool version it was measured on; see docs/01-evidence-base.md for the audit trail.

Legend: **M** = mechanically enforced (a hook or CLI refuses)
        **P** = prose only (an instruction the agent can ignore)
        **~** = partial

## The 12-step implementation loop

| # | Step | State | What actually enforces it |
|---|---|---|---|
| 1 | Recall memory and ADR constraints | **P** | skills/ text; nothing refuses on skipping it |
| 2 | Inspect source, runtime, deps, policy, health | **~** | `verify preflight`, `bin/blast`; advisory |
| 3 | Route to smallest capable topology | **P** | skills/dispatching-agents |
| 4 | Plan acceptance criteria, safety envelope, ownership | **~** | `bin/ledger` holds tasks; criteria not required |
| 5 | Execute in isolated scopes | **M** | `bin/worktree-guard` refuses overlapping ownership |
| 6 | Test focused, regression, failure paths | **~** | `verify` runs configured gates; `test-delta` (reporting) |
| 7 | Validate types, security, policy, compatibility | **~** | whatever `gates.json` declares; not inherent |
| 8 | Benchmark candidate vs source-bound baseline | **P** | `bin/ratchet` exists but benchmarks are not gated |
| 9 | Optimize measured bottlenecks without weakening safety | **P** | nothing measures this |
| 10 | Bind claims and evidence to exact source/build receipts | **~** | `verify` writes `.claude/evidence/latest.json` with a SHA — **agent-writable** |
| 11 | Reconcile concurrent handoffs, disclose limitations | **~** | `bin/ledger` handoffs; disclosure is prose |
| 12 | Publish only through a separately authorized release gate | **~** | `deny-dangerous` blocks `gh pr merge` — same-machine, same-trust |

**Score: 1 of 12 fully mechanical.** Nine are partial or prose.

## Concurrency and authority rules

| Rule | State | Gap |
|---|---|---|
| Never two writers in one worktree | **M** | `worktree-guard` glob+prefix overlap refusal, 39 checks |
| Read-only research may run concurrently | **P** | nothing enforces read-only |
| Only the integration owner edits shared manifests | **P** | no ownership check on manifests |
| **Child may drop capabilities, never add** | **P** | nothing prevents a subagent requesting more tools |
| A lease coordinates ownership, does not authorize a side effect | **P** | confused-deputy risk is unmitigated |
| Systems may propose but not self-promote | **P** | no separation between proposer and promoter |
| Bind evidence to an exact commit | **~** | SHA recorded, but the record is forgeable |

**Score: 1 of 7 mechanical.**

## The honest summary

The harness is strong exactly where a hook can say no on this machine — turn refusal,
worktree ownership, dangerous commands, gate config integrity. It is prose everywhere the
guarantee needs an authority the agent does not hold: capability attenuation, proposer/
promoter separation, and unforgeable receipts.

That is not a gap in discipline. It is the trust-boundary limit: layer 2 runs on the
agent's own machine with the agent's own privileges. Closing 10 and 12 needs a mechanism
outside that boundary, which is what the research is for.
