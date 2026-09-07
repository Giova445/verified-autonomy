# The artifact chain — intent → spec → plan → PR

Four artifacts, three approval hops, one audit trail. This directory holds the templates,
a checker, and one worked example reconstructed from work this repo actually did.

```
intent.md ──approve──► spec.md ──approve──► plan.md ──approve──► branch ──► PR ──review──► merge
   │                      │                    │                                             │
 what and why        how, and what           tasks, tests,                            the audit trail:
 we are not doing    policy says             proof statements                    who, when, what changed
```

Each hop exists because the artifact before it is cheaper to be wrong in. A wrong intent
costs a conversation. A wrong spec costs a plan. A wrong plan costs a branch. A wrong
branch costs a review cycle and everything downstream of the merge.

## Who approves each hop

| Hop | Approver | Recorded as | Enforced by |
|---|---|---|---|
| → `intent.md` | The person who wants the change writes it; **a second human** approves | `approved_by:` in the frontmatter | nothing — layer 1 |
| `intent.md` → `spec.md` | A human. Every blocking open question must be resolved first | `approved_by:` in `spec.md`; the resolutions land in the intent's question table | nothing — layer 1 |
| `spec.md` → `plan.md` | A human. Proof statements must exist before the branch does | `approved_by:` in `plan.md` | nothing — layer 1 |
| `plan.md` → branch | The implementer claims file scope | `bin/worktree-guard claim <id> --scope '<glob>'`, exit 2 on collision | **opt-in** — refuses a second writer *when it is run*; nothing runs it |
| branch → PR | Gates green | `./bin/verify done`; the `Stop` hook exits 2 while red | **enforced only where the kit's hooks are installed** — not installed here |
| PR → merge | A human reviewer, **never the agent and never another bot** | GitHub review + required status checks | **not configured in this repo** — no CODEOWNERS, no recorded branch protection |

**Not one of these six rows is enforced in this repository today.** An earlier draft of this
table marked the last three "enforced", which was the fabricated receipt this file spends the
rest of its length warning about. Corrected on 2026-09-03, with the measurement for each row:

| Row | What was checked | Result |
|---|---|---|
| 1–3, `approved_by:` | is the field read by anything? | No. `approved_by:` is a line of text an agent can write. No hook reads it, no CI job checks it, `bin/verify` does not know these files exist. |
| 4, `worktree-guard` | is the claim ever *required*? | No. `grep -rl worktree-guard hooks/ kit/hooks/ .github/workflows/ .claude/settings.json` → nothing (only `selftest.sh`, which runs its selftest). An agent that never claims is never refused. The refusal is real; invoking it is voluntary. |
| 5, the `Stop` hook | is the hook registered here? | No. `.claude/settings.json` in this repo has a `sandbox` block and **no `hooks` key**, and there is no `.claude/gates.json`. Registration is `kit/settings.hooks.json`, merged by hand as step 2 of `kit/install.sh`. In a project where that merge has happened the hook is genuine layer 2 and fires unconditionally; here it does not fire at all. |
| 6, branch protection | is it configured? | No. `ls CODEOWNERS .github/CODEOWNERS` exits 1. [`REVIEW.md`](../REVIEW.md) records the same gap in its own §0 and §"limitations". Where branch protection *is* configured it is the strongest link in the chain, because it sits outside the agent's trust boundary — that is a property of the mechanism, not a description of this repo. |

Row 5 is the one worth reading twice: the mechanism is real and the wiring is absent, and
those two facts together are indistinguishable from "we have a gate" unless someone states
them separately. What makes an approval real is the git record described below, not the
frontmatter, and not this table.

## What git records, and why that is the audit trail

The frontmatter is a claim. Git history is the evidence, because the agent does not author
it:

| Question | Answered by | Why it is trustworthy |
|---|---|---|
| Who wrote this? | commit **author** (`git log --format='%an <%ae>'`) | Set by the committer's configured identity, not by the file's contents |
| When? | **author and commit dates** (`%aI`, `%cI`) | Two timestamps; a rebase moves one and not the other |
| What actually changed? | `git show <sha>` | The diff, not the summary of it |
| Was it approved? | the **merge commit**, and the PR review attached to it | Recorded by the forge, on the far side of the trust boundary |
| By whom? | the reviewer on the closed review, and CODEOWNERS | The agent cannot approve its own PR under branch protection |

So the durable chain of custody is: *intent, spec and plan committed as files* → *a branch
whose commits carry author and timestamp* → *a PR whose approval is a review event the
agent cannot write* → *a merge commit that ties all of it to a SHA*.

Two consequences worth stating plainly:

- **Commit the artifacts before the code, in separate commits.** A single commit
  containing plan and implementation proves only that both existed at push time. Separate
  commits put the ordering in the record, and ordering is the entire claim.
- **A squash merge collapses that ordering.** If the chain's provenance matters to you,
  merge with a merge commit or keep the artifact commits on the trunk. This repo's own
  history has the artifact commits and implementation commits interleaved, which is why
  the worked example had to be reconstructed rather than read off.

## Using the templates

```bash
mkdir -p intent/$(date +%F)-my-change
cp intent/templates/intent.md intent/$(date +%F)-my-change/intent.md
# ... get it approved, then:
cp intent/templates/spec.md   intent/$(date +%F)-my-change/spec.md
cp intent/templates/plan.md   intent/$(date +%F)-my-change/plan.md
```

The templates live two directories deep and their relative links assume it, so a chain
directory placed directly under `intent/` inherits working links.

## The checker

```bash
bash intent/check-chain.sh intent/2026-09-03-my-change    # validate a chain
bash intent/check-chain.sh selftest                       # 16 positive controls
```

It asserts that each file carries its declared sections, that the frontmatter links each
hop to the one before it, and that the plan's work order parses into tasks via
`bin/ledger`. It fails closed: a missing file, an empty file, a chain directory that does
not exist, and an unavailable `bin/ledger` are all findings, never skips.

**What it does not check:** whether anything under a heading is true, sufficient, or
honest. A chain of five empty headings passes. Field presence is the mechanically decidable
part; the rest is judgment, and a check that pretended otherwise would be worse than none
because you would trust it.

The expected field sets are written out literally inside the checker and are never read
from `intent/templates/`. If they were derived from the templates, deleting a heading from
a template would delete its expectation too and every chain would keep passing while the
standard shrank — the defect recorded in commit `a25e83d`, where a sibling gate's control
computed a fixture count from `len(RULES)`. The selftest asserts each set's size as a
literal for the same reason.

The checker is **not wired into `selftest.sh` or CI** — those files belong to other work in
this change set. See [docs/sdlc-playbook.md](../docs/sdlc-playbook.md), "Not wired up yet",
for the exact lines to add.

## Two spec templates, and two plan templates

This is a real duplication and pretending otherwise would just make it harder to find.

| File | Field set | Named by |
|---|---|---|
| [`templates/spec.md`](../templates/spec.md) | problem, path classification, approach, blast radius, acceptance criteria, out of scope, open questions | [`skills/brainstorming`](../skills/brainstorming/SKILL.md) |
| `intent/templates/spec.md` | requirements, design, policy validation, flagged concerns | this directory, and `intent/check-chain.sh` |
| [`templates/plan.md`](../templates/plan.md) | file structure, interfaces, pre-flight, per-task TDD checklists, definition of done | [`skills/writing-plans`](../skills/writing-plans/SKILL.md) |
| `intent/templates/plan.md` | files changing, work order, tests needed, risks, proof statements | this directory, and `intent/check-chain.sh` |

They overlap heavily and neither is a superset of the other: the root templates have blast
radius and interface contracts, which these do not; these have policy validation and proof
statements, which the root ones do not. Both plan templates emit `- [ ]` checkboxes, so
`bin/ledger init --plan` consumes either.

**Use the root templates** when you are following `skills/brainstorming` and
`skills/writing-plans` — that is the path the skills describe and the one the repo has
used to date.

**Use these** when the chain itself is the deliverable: when a reviewer needs the policy
check and the proof statements in a fixed place, or when `check-chain.sh` is going to run
over the result.

Two standards for one document is a drift hazard, and this note is not a fix for it.
Reconciling them means editing `templates/`, `skills/brainstorming` and
`skills/writing-plans`, which are outside the scope of the change that created this
directory. It is recorded as an open defect in
[docs/sdlc-playbook.md](../docs/sdlc-playbook.md).

## The worked example

[`examples/2026-09-01-mcp-collision-detector/`](examples/2026-09-01-mcp-collision-detector/README.md)
reconstructs the chain for gate N3, the MCP name-collision detector, from commits
`ab99b87`, `d434d3c` and `a25e83d`.

**It was written on 2026-09-03, after the fact, and it says so on every page.** No chain
existed when that work was done. It is included because a filled-in dummy teaches nothing,
and because the honest labelling is itself the lesson: a back-formed planning artifact
presented as contemporaneous would be a forged receipt, and this repository is about not
producing those.
