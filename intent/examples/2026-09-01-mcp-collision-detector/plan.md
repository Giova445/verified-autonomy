---
# RECONSTRUCTED 2026-09-03 from git history. Not written at the time.
# See README.md in this directory before treating any of it as a record.
spec: ./spec.md
status: reconstructed
approved_by: NOBODY — no approval existed; this hop was not gated in September 2026
date: 2026-09-01 (implementation) / 2026-09-03 (this document)
---

# MCP name-collision visibility — Plan

> **Reconstructed after the fact.** The real work landed as a single 252-line commit
> (`d434d3c`) and was wired in a second commit 17 minutes later (`a25e83d`). The task
> decomposition below is **invented on 2026-09-03**: no such breakdown existed. The
> Proof statements are real commands that pass today, but they were composed after the
> results they predict, which is the opposite of the order the template asks for.

**Goal:** make an MCP name collision visible to an operator from outside the harness,
without claiming the harness was fixed.

## Files changing

| Path | Create / Modify / Delete | Why |
|---|---|---|
| `benchmark/verification/mcp/collision-detect.py` | Create | The detector and its six controls |
| `benchmark/verification/mcp/impostor_server.py` | Modify (1 line) | Add the `# gate: K1,N3` declaration the structural validator checks the manifest row against |
| `benchmark/manifest/gate-manifest.json` | Modify | New N3 row; K1's row gains `mitigated_by` |
| `selftest.sh` | Modify | Run the controls locally |
| `.github/workflows/verify.yml` | Modify | Run the controls in CI, **before** the check |

Not touched, deliberately: `hooks/`, `kit/hooks/`, `bin/verify`. This detector blocks
nothing. Putting it on the `Stop` path would turn an opt-in operator check into a gate
that launches subprocesses on every turn, which spec concern C1 rules out.

## Work order

- [ ] Task 1 — Read every scope a `claude.json` defines: the user-level `mcpServers` block plus each entry under `projects`, plus any `.mcp.json` given on the command line
- [ ] Task 2 — Group server names across scopes; classify differing definitions HIGH and identical ones LOW
- [ ] Task 3 — Write controls 1 and 2: fires on a shadowing config, silent on the same config with the shadow removed, LOW not HIGH for identical definitions
- [ ] Task 4 — Implement `--probe`: spawn each configured server over stdio, send `initialize` then `tools/list`, collect the advertised tool names under a timeout
- [ ] Task 5 — Group tool names across servers and report overlaps
- [ ] Task 6 — Write control 3 with two arms: a duplicated tool name fires, differing tool names stay silent
- [ ] Task 7 — Add the launch guard to control 3, asserting both configs were actually probed before believing either result
- [ ] Task 8 — Run it against the real config and record whatever it finds, including a finding against the author's own machine
- [ ] Task 9 — Add the `# gate: N3` declaration and the manifest rows; leave K1 at `FAILS` with `mitigated_by`
- [ ] Task 10 — Wire into `selftest.sh` and CI, controls ordered before the check

Task 7 is not a refinement of task 6. Without it, a run in which nothing launches produces
two empty tool sets, no overlap, and a clean report — the vacuous green this whole
repository is about. It is listed separately so it cannot be quietly folded into "task 6
done".

## Tests needed

| # | What it proves | Positive control — what makes it fail |
|---|---|---|
| T1 | The static half detects a shadowed server name | A config pair differing **only** by the presence of the shadow. The clean arm must be silent; if both arms fire, the detector is reporting on something else. |
| T2 | Severity is graded, not binary | Two identical definitions must come back `['LOW']`. A HIGH here means the rule collapsed. |
| T3 | The probe detects a duplicated tool name | Two servers advertising `search_code`. Expected finding: `['search_code']`. |
| T4 | The probe does not fire on non-collisions | The same fixture with the tool names changed. Expected: 0 findings. |
| T5 | Silence is only trusted when something was measured | Guard asserting both configs launched. **This is the control on the controls**: without it T4's silence and a total launch failure are indistinguishable. |

The expected values above are written as literals (`['LOW']`, `['search_code']`, `0`) rather
than computed from the detector's own output, for the reason recorded in `a25e83d`: a sibling
gate's control asserted a fixture count derived from `len(RULES)`, so deleting a rule deleted
its expectation too and the suite stayed green having tested less.

## Risks

| # | Risk | Likelihood | If it happens | Detected by |
|---|---|---|---|---|
| K-a | The probe hangs on a server that never answers `initialize` | med | The check wedges instead of failing | 10s default timeout, `--timeout` to override |
| K-b | Someone reads N3 VERIFIED as K1 fixed | **high** | A false receipt of exactly the kind this repo exists to stop | Only by the manifest note saying so in words. **Nothing mechanical prevents this misreading.** |
| K-c | Claude Code changes its config layout; the parser silently sees fewer scopes and reports fewer collisions | med | Detector degrades to silence, which looks like cleanliness | Partially — manifest `trigger_rules` flags `mcp` for re-run on a minor/major bump, but nothing tests the parser against a new layout |
| K-d | The probe is run against a real config containing a server that does work on startup | low | Side effects from running a checker | Opt-in flag only. Not eliminated. |

K-b is the risk this plan is least able to manage, and the reason the wording of the
manifest note was worth as much attention as the code.

## Proof statements

Every command below was run in this repo on 2026-09-03 at the stated exit code.

| # | Claim | Command | Expected |
|---|---|---|---|
| P1 | The detector's six controls pass, and the count is printed so a shrunken suite is visible | `python3 benchmark/verification/mcp/collision-detect.py --self-test` | exit 0, prints `MCP collision detector (6 checks)` |
| P2 | K1 is still FAILS and is only mitigated, not resolved | `python3 -c "import json,sys; g={r['gate'].split()[0]:r for r in json.load(open('benchmark/manifest/gate-manifest.json'))['gates']}; k=g['K1']; sys.exit(0 if k['status']=='FAILS' and k.get('mitigated_by','').startswith('N3') else 1)"` | exit 0 |
| P3 | The manifest row and the script agree in both directions via the `# gate:` declaration | `python3 benchmark/structure/validate.py` | exit 0, `manifest 0 finding(s)` |
| P4 | The controls run in the local suite, not only by hand | `bash selftest.sh` | exit 0, `MCP collision detector (6 checks)` in the `structure & supply chain` block |
| P5 | The controls run in CI **before** the check they belong to | `.github/workflows/verify.yml`, step `MCP name-collision detector — CONTROLS FIRST` precedes any use of the detector | read, not executed — no local command runs GitHub Actions |
| P6 | The harness now surfaces the collision itself | — | **NOT PROVABLE HERE.** It does not. K1 stays FAILS. Proving it would require a change to a closed client, which is intent constraint 1. |

P6 is the row that makes this table honest. A proof-statement section with no
NOT-PROVABLE row, on work that mitigated rather than fixed, would be describing a
different outcome than the one that happened.
