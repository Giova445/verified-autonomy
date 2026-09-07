---
# RECONSTRUCTED 2026-09-03 from git history. Not written at the time.
# See README.md in this directory before treating any of it as a record.
intent: ./intent.md
status: reconstructed
approved_by: NOBODY — no approval existed; this hop was not gated in September 2026
date: 2026-09-01 (implementation) / 2026-09-03 (this document)
---

# MCP name-collision visibility — Spec

> **Reconstructed after the fact.** The Design section is close to the record: the reasoning
> was written into the module docstring and the commit message on the day. The Requirements
> numbering and the Flagged concerns are mine, written on 2026-09-03 with the outcome in
> hand. Read the numbering as a presentation, not as a plan that existed.

## Requirements

| # | Requirement | How it is proven false |
|---|---|---|
| R1 | Report a server name declared in more than one config scope where the definitions **differ**, as HIGH | Feed it a config pair that shadows a name with a different command; a silent run falsifies it |
| R2 | Report identical duplicate declarations as **LOW**, not HIGH | Feed it two identical definitions; a HIGH falsifies it |
| R3 | Stay silent on a config that differs from the shadowing one **only by the removal of the shadow** | Present both arms; a finding on the clean arm falsifies it |
| R4 | Detect the same **tool** name advertised by two different servers, which requires launching them | Configure two servers whose `tools/list` overlaps; silence falsifies it |
| R5 | Stay silent when the two servers' tool names differ | Same fixture with the names changed; a finding falsifies it |
| R6 | Never treat "no findings" as clean when nothing was actually measured | Break both server launches; the run must not report a clean result |
| R7 | Do not launch anything unless explicitly asked | Run without `--probe`; any subprocess falsifies it |

R1–R5 trace to the intent's proposed outcome. R6 traces to constraint 2 by way of the
failure it implies: a probe that cannot start a server produces an empty tool set, and an
empty tool set collides with nothing. R7 traces to constraint 3.

**R6 is the requirement that matters most and would have been easiest to omit.** Every
other requirement is about detecting something. R6 is about not reporting silence as
safety, which is this repository's whole subject.

## Design

Two collision kinds, found two different ways, because only one of them is in the config.

| Kind | Source | Severity rule |
|---|---|---|
| **Server name** | Read statically from every scope a `claude.json` defines (the user block plus each `projects` entry) and from `.mcp.json` files | Differing definitions **HIGH** — one is silently discarded and the operator is running something other than what they configured. Identical ones **LOW**. |
| **Tool name** | Not in any config. `--probe` speaks real MCP over stdio — `initialize`, then `tools/list` — and compares what comes back | Reported on overlap |

**Rejected alternative 1 — config-only checking.** Simpler, no subprocesses, no timeout
handling, safe to run anywhere. Rejected because it would miss the exact attack K1
demonstrated *while appearing to check for it*, which is worse than not checking: it
produces a green run that an operator would reasonably read as "no impostor".

**Rejected alternative 2 — patch or wrap the harness.** Rejected as unavailable, not as
undesirable. Claude Code is a closed client (intent constraint 1). This is the reason the
outcome is a mitigation rather than a fix.

**Rejected alternative 3 — probe on by default.** Rejected under intent constraint 3.
Executing every server an operator has configured, as a side effect of running a checker,
is a worse failure than the one being detected.

**Layer placement.** This is neither layer 2 nor layer 3
([docs/02-architecture.md](../../../docs/02-architecture.md) §1). It is an out-of-band
detector an operator chooses to run: it blocks nothing, and an agent that does not run it
is unaffected by it. Saying so here is the difference between this spec and one that lets
the plan's proof statements imply an enforcement that does not exist.

## Policy validation

| Policy source | Question | Answer |
|---|---|---|
| [kit/governance.yaml](../../../kit/governance.yaml) `risk_tiers` | Which tier do the changed paths fall in? | `benchmark/verification/mcp/collision-detect.py` → **standard**. But the wiring that followed touched `.github/workflows/verify.yml`, which is **critical** (`autonomy: none`, `require: [human_review, security_reviewer]`). |
| [kit/governance.yaml](../../../kit/governance.yaml) `escalate_always` | Does this hit an always-escalate class? | No. No new dependency, no migration, no auth change, no IaC. The detector deliberately has zero third-party imports. |
| [.claude/settings.json](../../../.claude/settings.json) `denyWrite` | Does this need a write the sandbox denies? | **Yes, for the wiring step.** `**/.github/workflows/**` is on the deny list. The detector itself needs no denied write. |
| [docs/07-safety-and-autonomy-levels.md](../../../docs/07-safety-and-autonomy-levels.md) §1 | What autonomy level does this assume? | L1 at most — a local edit under human commit. Nothing here justifies more. |

Two honest notes on that table:

- `kit/governance.yaml` is read by no script in this repo (`grep -rl governance bin/
  kit/bin/ hooks/ kit/hooks/` returns nothing). Rows 1 and 2 are a human checking a written
  policy. Nothing enforced them on 2026-09-01 and nothing enforces them now.
- Row 3 is different in kind — `denyWrite` is enforced by the sandbox when it is active.
  Whether it was active during the wiring commit is **not recorded**, so this row states
  what the policy says, not what the machine did. That gap is itself a finding.

## Flagged concerns

| # | Concern | Severity | Disposition |
|---|---|---|---|
| C1 | The probe executes operator-configured commands. A hostile or merely careless server does work on startup. | high | **Mitigated** — opt-in flag, 10s default timeout, never runs against the real config unless asked. Not eliminated. |
| C2 | If neither server launches, both tool sets are empty, they collide with nothing, and silence reads as cleanliness. | high | **Mitigated** — the probe controls carry a guard asserting both configs were actually probed. This is R6, and it is the concern the design is most likely to have gotten wrong. |
| C3 | The severity split (HIGH for differing, LOW for identical) is a judgment, not a measurement. Nobody has shown that identical duplicates are harmless. | med | **Accepted and recorded.** It is defensible — nothing is silently discarded — but it is taste. |
| C4 | Detecting the collision does not stop it. An operator who never runs the detector is exactly as exposed as before. | high | **Accepted.** This is what `mitigated_by` means in the manifest and why K1 stays `FAILS`. |
| C5 | The static half parses config formats that Anthropic can change without notice. A format change would silently reduce the scope set and therefore the findings. | med | **Open.** Nothing detects that today. Manifest `trigger_rules` covers `claude_code.minor_or_major → mcp`, which flags the gate for re-run but does not test the parser. |
