# Cross-account learning audit — 2026-09-13

Audit of every Claude Code and Codex session on this machine, across the Cadre AI, Orchid
and personal accounts, to answer one question: **what has been learned, and what stops it
from being lost or re-learned?**

## 1. Corpus and method

| | Claude Code | Codex |
|---|---|---|
| top-level sessions | 326 | 584 |
| subagent transcripts (excluded) | 1,992 | — |
| bytes | 1.98 GB | 0.89 GB |
| distilled memory notes | 62 | **0** |

Total on disk across both, including subagent transcripts: **7.3 GB, 5,519 files.**

Sessions were indexed rather than read: `scratchpad/index_sessions.py` records per session
its cwd, mtime, size, first user message, and a count of **correction signals** — phrases a
person types when correcting an agent (`that's wrong`, `I already told you`, `never do`,
`don't do that`, `revert`, `why did you`…).

**Why rank on corrections.** A durable lesson is almost never in the part that went well.
It is in the moment the user said no. Ranking by size surfaces the longest sessions;
ranking by corrections surfaces the ones that taught something.

### What this method cannot do — stated before the numbers

- **The signal is a proxy, not a count of lessons.** A session can teach without a
  correction, and a matched phrase can be the user quoting someone else.
- **It is matched against raw transcript text**, not parsed messages, so a phrase inside a
  tool result or a pasted file counts. The alternative was parsing gigabytes to gain a
  little precision on a proxy.
- **It scales with file size.** The top Codex session (162 MB) scores 2,000 purely because
  it is enormous. Rank within a size band, never across.
- **Two instrument defects were found and fixed mid-audit**, both of which had produced
  wrong output first: the index swept `*/subagents/` transcripts into the session count
  (2,318 → 326 real Claude sessions, and every per-project total shrank), and the Codex
  extractor looked for `type: "text"` content blocks where Codex emits `input_text`,
  reporting 0 user intents for all 584 sessions. Numbers published before those fixes were
  wrong and are not reproduced here.

## 2. Findings

### F1 — Written rules do not hold. Measured.

`Co-Authored-By` is prohibited in Griffin by three independent statements: the project
`CLAUDE.md`, a memory note (`feedback-no-commit-co-author`), and the user directly
("explicit prohibited").

```
commits since 2026-08-01:        369
carrying Co-Authored-By:          37   (10.0%)
.claude/settings.json attribution: {"commit": ""}
```

The memory note names two of them (`2e8aa71`, `59b6a44`) and both still carry the trailer.
The rule is stated in three places, is mechanically decidable from one JSON field, and
fails one commit in ten. **This is the whole audit in one statistic:** every learning on
this machine is Layer 1 — prose that works only if it is read and obeyed.

### F2 — Codex learns nothing, structurally

`~/.codex/memories_1.sqlite` exists and is **empty**: `jobs` 0 rows, `stage1_outputs`
0 rows. Across 584 Codex sessions carrying 10,756 correction signals, nothing is retained.
`logs_2.sqlite` holds 143,994 rows but is runtime telemetry spanning 11 days, not content.

Claude Code has `~/.claude/projects/<slug>/memory/`. Codex has no equivalent in use. Every
correction in a Codex session is discarded when it ends.

### F3 — Memory is project-siloed, but the most expensive lessons are host-scoped

| org | project dirs | with memory |
|---|---|---|
| Orchid | 21 | 7 |
| Cadre AI | 26 | 1 |
| personal | 9 | 2 |

`no-render-vercel-cli` records that the `render` and `vercel` CLIs on this machine are
logged in as **Cadre** identities, so anything they create lands in a Cadre account — found
when a Vercel project was filed under a Cadre org and a Siigo access key went with it
(*"wait, im getting this on the cadre account!!!"*). That is a fact about the **host**, true
in all 21 Orchid projects and all 26 Cadre ones. It is stored in exactly one: PetMindful.

The same shape applies to `orca-claude-spend-cap-blocks-workers` (one Claude credential per
host, so a hit cap kills every worker — filed under Griffin), `dot-env-is-off-limits`, and
`feedback-dispatch-agents-on-sonnet`.

### F4 — 3,300 corrections sit in projects with no memory at all

Top-level sessions only, memory presence verified by prefix-matching the project slug:

| corrections | frustration | sessions | GB | project |
|---:|---:|---:|---:|---|
| 1,028 | 36 | 6 | 0.30 | OpenMontage |
| 892 | **92** | 6 | 0.35 | ComfyUI_Ad_Engine |
| 510 | 6 | 10 | 0.07 | Orchid/vitality |
| 391 | 0 | 2 | 0.01 | Orchid/Lunt-Optics-Website |
| 390 | 1 | 5 | 0.03 | Personal Gio |

ComfyUI_Ad_Engine has the highest frustration density in the entire corpus and not one
distilled note. Its 203 MB session is the largest single transcript on the machine.

### F5 — The distilled 62 cluster into five repeating classes

Counting the notes that already exist, the same failures recur in repos that never shared
context:

| class | notes | examples |
|---|---|---|
| identity / credential / tenancy | 6 | `no-render-vercel-cli`, `env-main-checkout-points-to-prod`, `ruflo-global-mcp-cwd-fix`, `lia-lendingpad-credentials-on-a-different-tenant` |
| deploy / environment drift | 5 | `tdi-live-theme-flip`, `shopify-sync-validation-gotchas`, `render-staging-worker-two-bugs`, `shopify-deploy-preserve-merchant-values` |
| the surface lied | 7 | `embedded-clicks-need-server-proof`, `browser-pane-emulated-viewport-clicks`, `blurry-images-css-compositing`, `lia-processing-queue-150-row-scan-cap` |
| evidence discipline | 4 | `lia-grid-extraction-verbatim-is-not-evidence`, `verify-research-currency`, `feedback-codex-job-verification`, `dont-call-a-mismatch-drift` |
| policy / authority | 4 | `feedback-never-merge-to-main`, `feedback-no-commit-co-author`, `flat-book-restart-rule`, `loop-247-standing-order` |

`ruflo-global-mcp-cwd-fix` is the sharpest instance of F3: a global MCP fallback silently
pointed **every unconfigured project** at HookBrand's memory. Cross-account contamination
of the learning store itself.

## 3. The plan

Ordered by evidence strength, not ambition. Each item names the layer it moves a learning
to, and the control that proves it works — a gate with no control is the failure mode this
repository exists to prevent.

### P1 — Commit-trailer gate (Layer 2). Evidence: F1, 37 real violations

A pre-commit check reading `.claude/settings.json`: if `attribution.commit` is falsy and
the message carries `Co-Authored-By`, block. If truthy and the trailer is missing, block.

Both directions matter — Griffin prohibits it and verified-autonomy requires it, so a
one-way check is wrong in one of the two repos.

*Control:* run it over the last 369 Griffin commits. It must flag exactly the 37 known
violations, and 0 of the 332 clean ones. That is a labelled corpus that already exists, so
this gate can be measured rather than asserted on the day it is written.

### P2 — Host-scoped memory tier (Layer 1, but correctly placed). Evidence: F3

Promote host facts out of project memory into `~/.claude/CLAUDE.md` or a memory tier that
loads everywhere: which CLIs carry which identity, one-credential-per-host spend coupling,
`.env` permission denials, default model on worker dispatch.

*Control:* start a session in an Orchid project with no memory (14 of 21 qualify) and
confirm the host rules are present in context. If they are not, the promotion did not work
— which is exactly the state today.

### P3 — Identity preflight (Layer 2). Evidence: F3, F5 — the costliest class

Before any command that creates a remote resource (`render`, `vercel`, `gh`, `shopify`,
`supabase`), assert the authenticated identity matches the project's expected org. Refuse
on mismatch.

This is the only class in the audit that has already leaked a credential into the wrong
company's account. It is also mechanically decidable: each CLI can report its identity.

*Control:* a fixture where the expected org and the logged-in identity disagree must be
refused; one where they agree must pass. Both arms, or the check proves nothing.

### P4 — Codex memory bridge. Evidence: F2, 10,756 discarded corrections

Codex sessions are structured JSONL at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` with
`response_item` / `payload.role` / `input_text`. They are parseable today — this audit
parsed them. Write correction-dense Codex sessions into the same memory notes Claude reads,
so the two agents stop learning separately.

*Control:* a known Codex session containing a known correction must produce a note; a
session with none must produce nothing. Absent the second arm, a bridge that emits a note
for every session would look successful.

### P5 — WITHDRAWN. The precedent it was based on already exists, and works.

This item originally read: *"`README-gates.md` still reports 56 cases / 95.2% specificity /
4.8% FPR while the live suite is 142 cases at 100%/100% — stale, and nothing checks it."*

**That was wrong, and the way it was wrong is worth keeping.** `README-gates.md` is
current: 142 cases, 69/69 recall, 73/73 specificity, 0% FPR, seven gates including
`pin-check`. A `bench-readme-current` eval in `evals/evals_docs.py` checks those numbers
against a live `bench.sh` run, and it passes. The stale table was real once — the file's own
HTML comment records it stating *98* cases for a suite that had grown to 142 — and a later
session fixed it and built the checker.

So the finding was a misread of a historical passage as a current claim, which is precisely
the `dont-call-a-mismatch-drift` failure from the Cocoa Asante notes: *a value that
contradicts a note is ambiguous evidence; the repository records what is true now.* Caught
here by running the eval instead of trusting the read.

**It strengthens the rest of the plan rather than weakening it.** `bench-readme-current` is
the existing proof that P1–P4 are buildable: a numeric claim in prose, pinned to a live
command, checked on every eval run. Build P1 in its image.

### P6 — Distil the five uncovered projects. Evidence: F4

OpenMontage and ComfyUI_Ad_Engine first, by correction and frustration density. This is
reading work, not gate work, and it is listed last deliberately: **a note is Layer 1, and
F1 shows Layer 1 does not hold.** Distilling more prose without P1–P3 produces more of what
is already being ignored.

## 4. What this audit did not do

- **It did not read the transcripts.** 2.87 GB of top-level sessions cannot enter a context
  window. Every finding above comes from the index, the 62 distilled notes read in full, or
  a direct check against git. Findings F4 and F6 name where to read, not what is there.
- **It did not verify the other four classes in F5 the way F1 was verified.** F1 has a
  count against real commits. The rest are patterns across notes, which is weaker evidence.
- **P5 was published wrong and then withdrawn in place.** It claimed a stale results table
  that a later session had already fixed. Kept visible rather than deleted, because a plan
  that silently drops its own bad item is not auditable.
- **It did not locate an "org environment / account setup" session.** The pattern matched
  0 top-level intents; content-wide matches landed only inside `subagents/workflows/` dirs.
  Either the session is named something else, or it is on a host this audit cannot see.
  Recorded as unresolved rather than quietly dropped.
