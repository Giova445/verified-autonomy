# Worked example — MCP name-collision detector (gate N3)

## This chain is RECONSTRUCTED. It was not written at the time.

The three artifacts in this directory were **back-formed on 2026-09-03 from git history**.
No `intent.md`, `spec.md` or `plan.md` existed when the work was done on 2026-09-01. The
commit came first; these documents were reverse-engineered from it afterwards.

That disclosure is not a formality. This repository exists to stop fabricated receipts, and
a back-formed planning artifact presented as contemporaneous is one — it would show a plan
matching its outcome perfectly, because the outcome was used to write the plan. Anyone
reading these files as evidence that the chain was followed would be reading a forgery.

They are here for one legitimate purpose: to show the templates carrying content dense
enough to argue with, using work that actually happened, rather than a filled-in dummy.

## What is load-bearing, and what is not

| Section | Source | Trust |
|---|---|---|
| Problem, constraints, the K1 result | commit `ab99b87` message + [gate-manifest.json](../../../benchmark/manifest/gate-manifest.json) row K1 | **Recorded at the time.** Quoted, not invented. |
| Design, the two-collision-kinds split, the probe rationale | commit `d434d3c` message + the module docstring in [collision-detect.py](../../../benchmark/verification/mcp/collision-detect.py) | **Recorded at the time.** The reasoning was written down, unusually. |
| The six controls, the live `ruflo` finding | `d434d3c` message + the passing self-test | **Recorded at the time**, and re-runnable today. |
| Requirement numbering, the risk table, the open questions, the ordering of the work order | **inferred by me on 2026-09-03** | **Invented.** Plausible, unverifiable, and shaped by knowing the answer. |
| Proof statements P1–P4 | commands that exist and pass today | Real commands, but **composed after** the results they predict. |

## Where a real chain would have looked worse

Two things in the record show what an honest contemporaneous plan would have missed, and
both are worth more than the tidy parts:

1. **The wiring commit (`a25e83d`, 17 minutes later) found that the control suite could be
   deleted without the suite noticing.** Deleting a rule from the sibling pin-check gate
   left `selftest.sh` green, because the control asserted a fixture count derived from
   `len(RULES)` — removing a rule removed its expectation too. The same flaw was then found
   in two more validators by sabotage, not by reading. No plan written on 2026-09-01
   contained that; it was discovered by attacking the work afterwards.

2. **`d434d3c` did not fix anything.** K1's status in the manifest is still `FAILS`, with
   `mitigated_by: N3`. The harness surfaces no collision today either. A plan written up
   front would have been tempted to write "K1 resolved" as its outcome. The record does
   not say that, so neither does this reconstruction.

Both are recorded below in the reconstruction rather than smoothed away, because a worked
example whose plan predicted everything is teaching the wrong lesson.

## Provenance

```bash
git -C . log -1 --format='%H %an %aI' d434d3c   # the implementation commit
git -C . log -1 --format='%H %an %aI' ab99b87   # the K1 measurement it answers
git -C . log -1 --format='%H %an %aI' a25e83d   # the wiring commit, 17 minutes later
python3 benchmark/verification/mcp/collision-detect.py --self-test   # 6 controls, exit 0
```
