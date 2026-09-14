# Enforcement across agents — what is built, what is armed, and where

Companion to [cross-account-learning-audit.md](cross-account-learning-audit.md), which asked
what the sessions taught. This one asks a narrower question with a worse answer: **of the
enforcement this repository has built and measured, how much is actually switched on, and
for which agent?**

Date: 2026-09-13. Every number below is reproducible from the commands named beside it.

## 1. Corpus and method

| | Claude Code | Codex |
|---|---|---|
| top-level sessions | 326 | 584 |
| subagent transcripts (excluded) | 2,008 | — |
| bytes | 1.99 GB | 0.89 GB |
| correction signals | 15,015 | 10,756 |
| user messages | 52,148 | 7,409 |

Indexed with `scratchpad/index_sessions.py`, ranking on correction signals rather than size.
The method's limits are stated in full in the companion audit and have not changed: the
signal is a proxy, it is matched against raw transcript text, and it scales with file size.

Project roots were derived by collapsing `.claude/worktrees/<name>` back to the parent repo,
then testing each root on disk for `.claude/gates.json`, `AGENTS.md` and `CLAUDE.md`.

**One instrument defect found and fixed during this pass.** The first index run was launched
with `nohup … &`; the harness reported exit 0 for the wrapper while the Python process was
killed at 1,000 of 2,918 files with its output buffer unflushed. The resulting file showed
`codex sessions = 0`, which is wrong and is not reproduced here. Re-run in the foreground to
completion. A background job's exit code is the wrapper's, not the work's.

## 2. Findings

### G1 — Layer 2 is armed in 0 of 242 project roots. Including this one.

`hooks/hooks.json` registers `stop-gate.sh` on `Stop` and `SubagentStop`, and the plugin is
installed globally, so the hook runs on every turn of every project. It then does this:

```
if [ ! -s "$ROOT/.claude/gates.json" ]; then
  … exit 0    # the project has not opted in
fi
```

Across the 242 project roots seen in the corpus:

| | count |
|---|---|
| `.claude/gates.json` present (layer 2 armed) | **0** |
| `AGENTS.md` present (layer 1, Codex-readable) | 71 |
| `CLAUDE.md` present (layer 1, Claude-readable) | 60 |

Including `~/verified-autonomy` itself. Its `.claude/settings.json` carries `sandbox` and
`attribution` keys and no `hooks` block; `git ls-files | grep gates.json` returns exactly one
path, `kit/gates.json`, which is the template and whose commands are `echo 'TODO'`.

The top four projects by correction count — Griffin (15,770 corrections, 471 sessions), Cocoa
Asante (1,793), tdi-international (1,102), OpenMontage (1,028) — have none.

**Control.** A scratch repo was built carrying `{"full":[{"name":"always-red","cmd":"exit 1"}]}`.
The same `stop-gate.sh` returned **exit 2** there and printed its refusal. Without the config
it returns 0. So this is not a broken hook; it is a working hook with its switch off
everywhere. That control ships as control 1 of `benchmark/gates/agent-matrix.sh`.

### G2 — One layer-2 control *is* live, and it fired three times unprompted

`deny-dangerous.sh` runs on `PreToolUse` with matcher `Bash|Write|Edit|NotebookEdit` and needs
no per-project opt-in. In this session alone it blocked, without being asked to:

- `gh pr merge 7` — *"an agent may not merge a pull request"*
- a diagnostic ending `|| true` — *"exit-code suppression — this hides a failing gate"*
- `rm -rf "$d"` inside a probe script — *"rm -rf against an unresolved shell variable"*

That is the difference between the two mechanisms. One needs a file nobody creates; the other
needs nothing and works.

### G3 — Codex has the same enforcement contract. None of this is installed in it.

The assumption worth testing was that Codex is unreachable. It is false.

`~/.codex/hooks.json` already registers eight event types:

```
PermissionRequest  PreToolUse  PostToolUse  SessionStart
Stop               SubagentStart  SubagentStop  UserPromptSubmit
```

with third-party hooks already wired into them (orca, impeccable, caveman). The Codex binary
carries a JSON schema with `BlockDecisionWire` (`enum: ["block"]`), referenced by several hook
output types, and a `PreToolUsePermissionDecisionWire` carrying `"deny"`. The same block
semantics this repository depends on.

```
grep -rl "verified-autonomy" ~/.codex/hooks.json ~/.codex/config.toml ~/.codex/AGENTS.md ~/.codex/skills
→ (no matches)
```

584 Codex sessions, 10,756 correction signals, and not one line of this enforcement present.

**Stated limit:** whether Codex's `Stop` hook honours a blocking decision the way Claude Code's
exit 2 does was **not** measured. The wire type exists and `Stop` is a registered event; that
is evidence the port is possible, not proof it works. Measuring it requires running a real
Codex turn, which spends against a shared credential. It is task T2 below, not a claim here.

### G4 — The gates themselves are agent-portable. Measured, with a discriminating control.

If the port is a rewrite, none of this is worth planning. It is not.

`benchmark/gates/agent-matrix.sh` runs each unit's own selftest twice — once with
`CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` set, once with every `CLAUDE_*` variable unset,
which is the shape a Codex hook or a CI step sees.

**13 of 13 declared units are portable: identical exit codes in both environments.**
`scan-diff-cheats`, `inert-mask`, `ambiguity`, `escalate`, `holdout`, `ledger`,
`mutate-changed`, `test-delta`, `worktree-guard`, `identity-preflight`, `pin-check`,
`playbook-coverage`, `trailer-check`.

A table of identical numbers is exactly what a probe measuring nothing produces, so the matrix
refuses to print unless three controls discriminate first:

| control | result |
|---|---|
| 1 — a red gate refuses the turn under Claude env | PASS (exit 2) |
| 2 — same script, bare env, outside the repo: differs | PASS (2 vs 0) |
| 3 — a synthetic `CLAUDE_`-coupled unit is detected as coupled | PASS (0 vs 7) |

Control 2 is the load-bearing one: it proves the probe can see coupling, using a real unit
rather than a fixture. `bin/verify` is deliberately excluded from the unit list — it has no
`selftest` subcommand, so probing it that way measures its usage message. Control 1 drives it
through `stop-gate.sh`, which is the path that runs it in production.

The unit list is a literal, and `EXPECTED_UNITS` is declared beside it. A declared unit whose
file disappears is reported as `MISSING` and raises a finding. Globbing `bin/` would have meant
deleting a unit also deletes its own requirement to be portable — the
expectation-derived-from-subject defect this repository has now hit six times.

## 3. The plan

The shape of the problem: **the enforcement is built, measured, and deployed nowhere.** Not a
capability gap. A distribution gap. So the plan is ordered by how many real sessions each step
would have covered, not by how interesting it is.

### T1 — Arm layer 2 where the corrections actually are. Evidence: G1

`.claude/gates.json` in the top projects by correction count, each holding commands that pass
today. Griffin first: 15,770 correction signals and 471 sessions behind a hook that exits 0.

Not a template copy. `kit/gates.json` ships `echo 'TODO'` in every slot, and a gate whose
command is `echo` is worse than no gate — it reports green. Each project needs its real lint,
typecheck and test commands, verified to pass before being written down.

**Done when:** `stop-gate.sh` returns exit 2 on a deliberately broken tree in each armed
project, and 0 on a clean one. Both arms, per project, or it is not armed.

### T2 — Measure whether Codex honours a blocking hook. Evidence: G3

The single fact the whole Codex port rests on, and it is currently an inference from a schema.
Install a trivial `Stop` hook in `~/.codex/hooks.json` that emits
`{"decision":"block","reason":"…"}`, run one throwaway Codex turn, observe whether the turn is
refused.

**Done when:** the answer is written down either way. If Codex ignores it, T3 shrinks to
`PreToolUse` only — still worth doing, since `PreToolUsePermissionDecisionWire` carries `deny`
and `deny-dangerous.sh` is the one control proven to fire (G2).

**Cost note:** one Codex turn against a shared credential. See the host-scoped memory on the
shared spend cap before running it.

### T3 — Port `deny-dangerous.sh` to Codex. Evidence: G2, G3, G4

Highest value per line of work. It needs no per-project opt-in, it is proven to fire, and G4
shows it runs identically with no Claude environment. Register it on Codex `PreToolUse`,
translating the exit-2 convention to `{"decision":"block"}` on the wire.

**Done when:** the same three commands it blocked in this session — `gh pr merge`, a trailing
`|| true`, `rm -rf` on an unresolved variable — are blocked in a Codex turn, and an ordinary
command in the same shape is not. Both arms, or it is a hook that blocks everything.

### T4 — `ledger open` as a gate. Evidence: the loop gap

`grep -n "ledger" bin/verify hooks/` returns nothing: no gate consults the task ledger, so a
turn can end with every gate green and every task pending. One entry in `gates.json` wires the
durable task list into the layer that can actually refuse.

**Done when:** a turn with a pending ledger task is refused, and the same turn with the task
closed is not.

### T5 — Evidence relevance in `ledger done`. Evidence: measured

`ledger done` validates that the evidence file exists, is non-empty, and hashes it. It does not
check that it is about the task. Demonstrated live: a file reading `grocery list / milk / eggs`
closed the task *"Implement OAuth token refresh"*, exit 0.

**Control already exists and discriminates:** the same command refuses a missing file (exit 2)
and a zero-byte file (exit 2), asserted in its own selftest. The check is live; it measures the
wrong property.

**Done when:** the grocery list is refused and a real gate-run receipt is accepted.

### T6 — Deliverable-scoped acceptance gate. Evidence: the product gap

Every gate here is process-facing. `bin/mutate-changed` says so in its own header: *"it assesses
whether an algorithm is implemented correctly, not whether it is the CORRECT algorithm — the
spec-level failure that dominates in practice is out of its reach."*

The shape already exists in `evals/`: a plausible request that would damage the deliverable,
plus deterministic acceptance checks, plus positive controls, and zero model calls. Thirty of
them, aimed at this repository's configuration because that is this repository's product. Point
the same shape at a real deliverable.

Acceptance outcomes must be **declared independently**, not read from the artifact, or deleting
a deliverable deletes its own check.

**Blocked on:** which deliverable. The CEB product-imagery failure is the strongest candidate —
`brand_contract` read by no code, no `reference_images` passed, and a product-fidelity failure
no gate here could have caught.

### T7 — Carry-over from the companion audit

P2 (host-scoped memory tier), P4 (Codex memory bridge, evidence: 10,756 discarded corrections),
P6 (distil the five uncovered projects) are unchanged and still open. P4 gets cheaper if T2
succeeds, since a Codex `SessionStart` hook is the natural place to inject recalled memory.

## 4. What this did not do

- **No Codex turn was run.** Everything about Codex here is read from its configuration and its
  binary's schema. T2 exists because that is not the same as measuring it.
- **`.claude/gates.json` presence was tested on the current disk state**, not at the time each
  session ran. A project could have been armed and later disarmed; the corpus does not say.
- **Correction counts rank projects, they do not size the harm.** A project with 15,770 signals
  is where to look first, not a project with 15,770 defects.
- **No claim that armed gates would have prevented the corrections.** That would need the
  counterfactual, and nobody has it. The claim is narrower and sufficient: the mechanism was
  built, it demonstrably fires, and it was switched on in none of the places the work happened.
