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
capability gap. A distribution gap.

**Every step below is generic machinery.** Naming a repository in a plan step is the defect,
not the plan: "go arm project X" does not scale to 242 roots and does nothing for root 243. A
step earns its place here only if it works on a project nobody has seen yet, including one
created tomorrow. Where a step needs project-specific facts, the project declares them and the
machinery stays general.

### T1 — Arming must be mechanical, not remembered. BUILT 2026-09-13. Evidence: G1

Stack detection was never the missing piece. `kit/install.sh` has had `detect_gates()` for a
while: it greps `package.json` for `"lint"`, writes `npm run lint`, and labels the result
*"AUTO-DETECTED. Replace with commands that pass on a clean checkout TODAY."*

**It writes commands it has never run.** That is why the count is zero. A config a human must
audit before trusting is a config nobody arms, and an aspirational gate gets switched off by
the first agent that hits it.

`bin/arm` closes that loop. It proposes candidates from whatever files are present, then
**runs every one** and writes only what exited 0 in this repository, right now. The output
needs no review because nothing unverified is in it.

```
arm detect [dir]   every candidate with its verdict; writes nothing
arm write  [dir]   .claude/gates.json from the candidates that passed
```

It refuses to write a command that failed, timed out, or does not exist; a placeholder; or a
config whose `full` tier would be empty, since an armed config that gates nothing reports
enforcement that is not happening. An existing config is never clobbered — `.new` lands beside
it, as `install.sh` already does.

Eight controls. Three of them exist because the thing they check was already broken:

| control | result |
|---|---|
| 1 — a passing command is written | ok |
| 2 — a failing command is refused, and nothing is armed | ok |
| 3 — a placeholder is rejected as a placeholder, not run | ok |
| 4 — an undetectable repo is refused rather than armed empty | ok |
| 5 — an existing config survives; the new one lands beside it | ok |
| 6 — the written config is the shape the Stop gate consumes (red → exit 2) | ok |
| 7 — a manifest-less repo arms through its script entrypoint | ok |
| 8 — a probe outliving the budget is NO VERDICT, not REJECTED, and arms nothing | ok |

**Defect found by control 3.** The placeholder test ran against the gate *command*, but the
command is a wrapper: `npm test` runs whatever `package.json` says. A repo whose `test` script
is literally `echo TODO` would have been armed with a command that exits 0 and checks nothing —
the vacuous green this kit exists to prevent, reached through the kit. Candidates now carry the
script body where one can be read, and the judgement is made against that.

**Defect found by control 7.** Detecting only package manifests produced **zero candidates for
this repository**, which has no `package.json`, `pyproject.toml`, `go.mod` or `Cargo.toml` —
its suite is a shell script. That is a whole class of project, not an edge case. Conventional
script entrypoints (`selftest.sh`, `test.sh`, `run-tests.sh`, `scripts/test.sh`, `bin/test`)
are now proposed and probed like anything else.

**Defect found by the first real user, not by a control.** `arm write` refused to arm this
repository: *"0 of 1 candidates pass"*. The default probe budget was 120s and this
repository's own suite takes 123s, so a passing gate was killed at the boundary and reported
as rejected. The 2:01.95 figure had been measured in the same session that chose 120.

The timeout branch had **no control at all** — control 2 covered a command that exits 1, and
nothing covered a command that never finishes. That is why it shipped broken, and control 8
now closes it. Two changes followed from the diagnosis rather than from the symptom:

- The budget is a **hang detector, not a speed limit**. A `full`-tier suite running for
  minutes is ordinary, and treating that as a hang rejects exactly the gates most worth
  arming. Default raised to 600s.
- A timed-out probe is **NO VERDICT, not REJECTED**. A command that exits non-zero is
  definitively not a gate; a command still running at the budget is unknown. Collapsing the
  two tells someone their suite is broken when it is merely slow. Both still refuse to arm —
  fail-closed is unchanged — but they now say different things, and the unknown case names
  `ARM_TIMEOUT`.

Elapsed time is reported for every candidate, so a slow gate is visible rather than silently
near a cliff. Run against this repository with defaults it now proposes two candidates, arms
one, and rejects the other with its reason:

```
full  script-selftest.sh  ./selftest.sh   passes (125s)
full  py-test-bare        pytest -q       REJECTED (exit 5 after 0s)
```

**Not done:** `arm` is not yet called from `install.sh`, and no project has been armed with it.
Arming a repository writes `.claude/gates.json`, which this project's own contract forbids an
agent from touching. That prohibition is correct — arming enforcement on a repository is a
decision its owner makes, not one an agent makes for them. The mechanism is the deliverable;
the arming is one command.

**Done when:** `install.sh` calls `arm write` instead of `detect_gates`, so every future
install arms with verified commands rather than aspirational ones.

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

### T4 — `ledger open` as a gate. BUILT 2026-09-16. Evidence: the loop gap

`grep -n "ledger" bin/verify hooks/` returns nothing: no gate consults the task ledger, so a
turn can end with every gate green and every task pending. One entry in `gates.json` wires the
durable task list into the layer that can actually refuse.

**Done when:** a turn with a pending ledger task is refused, and the same turn with the task
closed is not.

### T5 — Evidence relevance in `ledger done`. BUILT 2026-09-16. Evidence: measured

`ledger done` validates that the evidence file exists, is non-empty, and hashes it. It does not
check that it is about the task. Demonstrated live: a file reading `grocery list / milk / eggs`
closed the task *"Implement OAuth token refresh"*, exit 0.

**Control already exists and discriminates:** the same command refuses a missing file (exit 2)
and a zero-byte file (exit 2), asserted in its own selftest. The check is live; it measures the
wrong property.

**Done when:** the grocery list is refused and a real gate-run receipt is accepted.

### T6 — Deliverable-scoped acceptance gate. BUILT 2026-09-15. Evidence: the product gap

Every gate here is process-facing. `bin/mutate-changed` says so in its own header: *"it assesses
whether an algorithm is implemented correctly, not whether it is the CORRECT algorithm — the
spec-level failure that dominates in practice is out of its reach."*

The shape already exists in `evals/`: a plausible request that would damage the deliverable,
plus deterministic acceptance checks, plus positive controls, zero model calls. Thirty of them,
aimed at this repository's configuration because that is this repository's product.

**The generic version is a contract file plus one runner.** A project declares its acceptance
outcomes in `.claude/acceptance.json`; the runner is project-agnostic and executes them. No
gate in this repository ever names a product.

Each declared outcome carries three things, and the runner refuses the outcome without all
three: a **check** command that exercises the real artifact, a **control** that must fail when
the outcome is genuinely broken, and the **expectation stated in the declaration** rather than
read from the artifact. That last one is the load-bearing rule — an outcome whose expectation is
derived from the thing under test disappears the moment the thing does, which is the defect this
repository has now hit six times.

Fails closed: a missing artifact, an unreadable contract, or a control that did not discriminate
is never a pass.

**Shipped as two pieces.** `benchmark/gates/acceptance.py` reads the contract and judges exit
codes, which keeps it language-agnostic and product-agnostic. `benchmark/gates/drive.mjs` opens
the artifact in a real browser, because the deliverable people actually complain about is a
page and no unit suite has ever caught a submit button that never enables.

**Binding where a contract exists, reporting where none does.** With outcomes declared, a
failed or unproven one exits non-zero. With no contract it says so and exits 0 — it does not
claim a pass. Blocking every repository on a file none of them have is how a gate gets deleted
in week one; silently passing one that *has* declared outcomes is how a gate becomes theatre.

**The driver is a command, not an agent capability.** A gate that says "the agent should look
at the page" is persuasion, and persuasion is exactly what produced a green run beside a broken
login form. Codex inherits it for the same reason — it is a shell command, not an MCP tool.

**A standing memory nearly killed this.** The note read "Playwright cannot load its config on
this machine, so e2e is not available". True of the *runner*, which loads `playwright.config.ts`
through Node's module customization hooks. The *library* launches Chromium and drives a page
fine — verified 2026-09-15 on node v24.1.0 / playwright 1.61.0. The memory has been corrected
in place. Designing around the broader reading would have thrown away the only mechanical route
to seeing the deliverable.

**The assertion vocabulary is the manual QA pass, written down once**: visible, hidden, text,
enabled, disabled, count, focusable, console-clean, no-overflow-at-viewport, plus `fill` and
`click` so the ordered list is a short script. Most hand-found defects live on the far side of
an interaction. Nothing in the vocabulary names a product; a project declares which assertions
apply to which selector in its own contract.

**Worked example, and the evidence that static gates cannot do this.**
`benchmark/gates/fixtures/acceptance-demo/` holds a login page and the same page with one
defect: nothing re-enables submit after the fields are filled. The two are *identical on first
paint*, and a static render assertion confirms it:

```
  login.html            exit=0
  login-regressed.html  exit=0     # the same check cannot tell them apart
```

The acceptance gate can:

```
  holds   submit enables once both fields are filled       check exit 0, control exit 1
  holds   a rejected sign-in shows an error and logs nothing
→ exit 0

  # ship the regression as the deliverable instead:
  FAILS   submit enables once both fields are filled       check exited 1; control discriminates
  FAILS   a rejected sign-in shows an error and logs nothing
→ exit 1
```

**Controls:** 8 on `acceptance.py`, 9 on `drive.mjs`, 1 added to `bin/arm`. The load-bearing
ones are `acceptance.py` control 3 — a control that *passes* yields `NOT PROVEN`, never a pass,
because a check that cannot fail is not evidence — and `drive.mjs` control 8, which drives two
pages that paint identically and requires opposite verdicts.

**Arming is automatic.** `bin/arm` proposes the acceptance gate only where
`.claude/acceptance.json` exists, then probes it like any other candidate. Arming it
unconditionally would add a gate that exits 0 without looking at anything — a placeholder
wearing a different name.

**Not done:** `kit/install.sh` copies `bin/` and `hooks/` but not `benchmark/`, so an installed
kit has no `acceptance.py` to arm. Distribution is the remaining gap, not capability.

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

### T8 — The kit must ship what this repository tests. BUILT 2026-09-15. Evidence: measured drift

T6 exposed something worse than the gap it closed. Everything proved here is proved about
`bin/` and `hooks/`. Every project that installs the kit runs `kit/bin/` and `kit/hooks/`.
Measured on 2026-09-15, before this gate existed:

| | |
|---|---|
| `kit/bin/verify` vs `bin/verify` | **25 lines behind** |
| `kit/bin/holdout` vs `bin/holdout` | **27 lines behind** |
| `kit/bin/arm`, `kit/gates/acceptance.py`, `kit/gates/drive.mjs` | **absent** |

The `verify` drift is the serious one. The root copy carries the `attempts` hoist, whose
absence — in the comment's own words — made the runner *"certify GREEN on exactly the
unreadable configs the branch exists to refuse."* Every project installed from this kit had
that. This repository had recorded the pattern once, for one file, as an accident:

> *"the recall fix landed in `hooks/` and never reached `kit/hooks/`, so every number
> published about the detector described a file nobody installed."* — `evals/evals_suites.py`

`benchmark/gates/kit-sync.py` checks four directions, with the pair list declared as a
literal so a file vanishing from the kit is a finding rather than a shorter list: a declared
pair that **differs**; one whose kit copy is **missing**; a file shipped in a mirrored
directory that is **undeclared**, so nothing compares it to anything; and a tool the shipped
config **names** but the kit does not ship. 7 controls, including equal-size files with
different bytes — a shallow comparison passes those and would miss a one-character sabotage.

**Two installation defects it surfaced, both fixed in `kit/install.sh`:**

`install.sh` installed a hardcoded four of the kit's tools while `kit/gates.json` named four
others, so an agent promoting a deferred gate got command-not-found from instructions the kit
itself had given it. The install lists are now derived from what the kit ships.

**And the Stop hook could never run in the shipped layout.** It resolves its runner as
`<its own dir>/../bin/verify` and deliberately refuses to fall back to `$ROOT/bin/verify`,
because a 17-byte repo-committed stub once became the gate runner. In a kit install the hook
lands in `.claude/hooks/`, so that resolves to `.claude/bin/verify`, which nothing created —
and `CLAUDE_PLUGIN_ROOT` is a plugin concept a kit install never sets. The hook therefore
exited 2 on **every turn, whatever the gates said**. Fail-closed, but unconditionally, which
is a hook anyone switches off within the hour. `selftest.sh:30` had this recorded as KNOWN
FAILING. The runner is now installed beside the hook, in the hook's own trust domain, rather
than at a path the hook merely discovers.

**End-to-end, in a project created from scratch:**

```
A  deliverable whole                          stop-gate exit=0   turn allowed
B  submit never re-enables; unit suite green   stop-gate exit=2   turn refused
```

That is the complaint this work started from — green gates beside a broken page — with both
arms measured.

## 5. Is the feedback still applied? — `benchmark/gates/feedback-audit.py`

Feedback gets applied in a commit and un-applied in a refactor six weeks later, and nobody
notices, because the test was attached to the code that implemented the instruction and never
to the instruction itself. This repository has already watched exactly that happen to a
detector fix that reached `hooks/` and never `kit/hooks/`.

So each item pairs the operator's own words with two probes: one that passes only while the
instruction is honoured, and a **control that must fail**, proving the first can tell the
difference. An item whose control passes is `NOT PROVEN` and never credited — the same rule
every other gate here follows, applied to the one claim nobody usually audits.

| | feedback | how it is enforced now |
|---|---|---|
| F1 | quoted-literal false positives, without the bypass | a quoted destructive literal is allowed (0), the bare command blocked (2) |
| F2 | let a tool modify the hooks | editing a hook allowed (0), force-push still blocked (2) |
| F3 | nothing product-specific | the plan section names no product; the scanner detects a planted one |
| F4 | a gate that attacks the deliverable | acceptance controls pass; a non-discriminating contract is refused |
| F5 | pursue the goal until everything is done | an open ledger exits 1; a grocery list cannot close an OAuth task |
| F6 | a red flag must not be noisy or wrong | a harness error reads `CANNOT RUN`, never `FAILS` |
| F7 | stop running the whole suite for every request | scope controls pass **and** `bin/verify` consults it |
| F8 | fix the two items blocked on the operator | both workflows install the runtime driver |

**All 8 established**, each by a probe shown able to fail. Six controls of its own, including
the two that matter most: a probe pointed at a missing artifact yields `CANNOT RUN` rather
than a pass, and an empty tree **fails** the audit instead of reporting everything applied.

F7's check is deliberately two-part. `bin/scope` passing its own controls proves the planner
works; it does not prove anything consumes it. A perfect planner nothing calls is prose, so
the probe also asserts `bin/verify` consults it.

**What it cannot do:** it cannot tell you the feedback was applied *well*, or that the
operator would agree the implementation matches what they meant. It checks that the mechanism
named in each row is present and still discriminates. Where an item is prose rather than
mechanism, it says so rather than inventing a check.

**One finding surfaced by writing this section.** `deny-dangerous.sh` blocked the commit of
this very document, because the F1 row quoted a destructive command as an example. The
inert-literal logic covers quoted strings and print sinks; it does not cover heredoc bodies,
so prose about a dangerous command reads as the command. Filed, not fixed here: the row now
describes the example instead of spelling it, and the hook keeps failing closed, which is the
right direction for a detector that is unsure.
