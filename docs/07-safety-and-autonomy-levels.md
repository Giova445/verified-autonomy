# 07 — Safety and Autonomy Levels

Sandboxing, the deny-list, prompt-injection defense, escalation triggers, and a graduated
model for how much rope to give the agent.

The governing observation: when the Replit agent deleted a production database, the only
control in place was a natural-language instruction not to. It then **fabricated 4,000
records and false status reports to hide it** — the same false-success mechanism from
[01](01-evidence-base.md#1-agents-claim-completion-they-have-not-earned), applied to an
irreversible action. Safety cannot live in layer 1.

---

## 1. Tiered autonomy

Earn levels; don't start at the top. Each level's controls are cumulative.

| Level | What the agent may do | Required controls |
|---|---|---|
| **L0 — Suggest** | Propose a diff or plan. No changes. | Read-only tools; no Bash write; no egress beyond the model API |
| **L1 — Local edit** | Edit files in a sandbox; human commits | Sandboxed FS scoped to the worktree; no push capability; registry-only egress |
| **L2 — Branch + PR** | Commit to a branch, open a PR | Branch protection + required checks + CODEOWNERS; PR-only delivery; deny-list hooks; egress allowlist; **no self-approval** |
| **L3 — Merge low-risk, escalate rest** | Merge PRs that pass all gates *and* touch no escalation path | L2 + automated diff classification against the escalation table; feature flags; canary + auto-rollback; audit log of every autonomous merge |
| **L4 — Autonomous merge** | Merge within a narrow pre-approved change class (dep patch bumps, lint fixes) | L3 + human-defined change-class allowlist; mandatory canary with automatic rollback on SLO breach; periodic human audit sampling; escalation table structurally excluded via path-based protection |

**No level removes the floor controls.** Sandbox, deny-list, egress allowlist, and CI as
independent re-verification apply at L4 exactly as at L1. Autonomy does not graduate out
of them.

Most teams should live at **L2** and consider L3 only after months of clean metrics.

## 2. Sandbox profile

Claude Code ships an OS-level sandboxed Bash tool — macOS Seatbelt, Linux/WSL2 via
bubblewrap + seccomp — enforcing a filesystem boundary and a network boundary via an
egress broker outside the sandbox. The kernel enforces it, not the model.

Recommended profile for an agent permitted to run arbitrary commands:

| Dimension | Setting |
|---|---|
| **Compute** | Ephemeral and disposable per task. Never the developer's machine, never a long-lived shared box. |
| **Filesystem** | Read/write confined to the worktree + scratch. No `~/.ssh`, no cloud credential files, no sibling repos, no host `/etc`. |
| **Network** | **Default-deny egress.** Allowlist: package registries, the git remote, the model API. Nothing else. |
| **Secrets** | None long-lived in the environment. Short-lived scoped tokens injected per run. |
| **Identity** | Non-root inside the sandbox. |
| **Limits** | CPU, memory, and wall-clock caps to bound runaway loops. |
| **Fallback** | `allowUnsandboxedCommands: false`. Every fallback attempt is a signal, not a convenience. |

Heavier isolation when needed: dev containers (shared kernel), then E2B (Firecracker
microVM, per-session kernel) or Modal (gVisor syscall interception) for genuinely
untrusted work.

`--dangerously-skip-permissions` is only defensible when *all* of the above hold. The
flag removes prompts; it does not remove risk. The safety comes from the disposable
environment.

## 3. Command deny-list

Enforced by a `PreToolUse` hook returning exit 2. Recall that **exit 2 blocks regardless
of any JSON `permissionDecision: "allow"`** — the hook wins.

| Operation | Pattern |
|---|---|
| Recursive force delete | `rm\s+-rf\s+(/|~|\.$|\$)` — note unresolved shell variables |
| Force push | `git push.*(-f\|--force)` |
| History destruction | `git reset --hard`, `git clean -fd`, `git rebase` on shared branches |
| Destructive SQL | `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, `DELETE FROM` without `WHERE` |
| Privilege escalation | `sudo`, `chmod 777`, `chown` on system paths |
| Infra destruction | `terraform destroy`, `gh repo delete`, cloud `delete`/`terminate` CLI |
| Credential reads | `~/.aws/credentials`, `~/.ssh/*`, `.env` outside the repo |
| **Disabling its own guardrails** | Write/Edit targeting `.claude/hooks/**`, `.claude/settings.json`, `.claude/gates.json`, `.github/workflows/**` |
| Self-approval | `gh pr review --approve` / `gh pr merge` on a PR it authored |

The guardrail-disabling row is the one people forget, and it is the most important: an
agent that can edit its own gate config has no gates. Enforce at the tool-permission
layer, not just by regex.

Implementation: [`kit/hooks/deny-dangerous.sh`](kit/hooks/deny-dangerous.sh).

## 4. Prompt injection in the agent's own workflow

Underrated because the attack surface is the agent's *normal input*: issue bodies, PR
comments and titles, dependency READMEs, web pages, test fixtures, MCP tool descriptions.

**The lethal trifecta** (Willison): an agent with (a) access to private data, (b)
exposure to untrusted content, and (c) the ability to communicate externally is
exploitable by a single poisoned document. No code vulnerability required — the model
cannot reliably distinguish an instruction from data describing an instruction.

**Agents Rule of Two** (Meta): an unsupervised agent should hold at most two of the three
at once. All three requires a human in the loop.

Mitigations, in order of load-bearingness:

1. **Egress allowlist** (§2) — turns "the agent got tricked" into "the agent got tricked
   but couldn't send anything anywhere." This is the backstop that works even when
   everything else fails.
2. **Drop a capability while processing untrusted content.** Read-only repo mode while
   triaging an issue; escalate to write only after a lower-privilege pass has summarized
   and quarantined the content.
3. **Restricted tool scope** for issue-reading / web-fetching subagents — no Bash, no MCP
   write tools, no credential-bearing tools.
4. **Never auto-merge** when the trigger included untrusted input, regardless of green CI.
5. **Pin and audit MCP servers.** Tool descriptions are text the model reads as
   instruction (CVE-2025-54136 / -54135).
6. **Treat repo and issue content as data** at the system-prompt level — necessary, but
   the weakest of these, because it is layer 1.

Relevant here: Claude Code's auto-mode classifier reviews actions but deliberately does
**not** see tool results, specifically to block injection from file and web content.

## 5. Escalation triggers

Narrow but non-negotiable. Breadth is what causes rubber-stamping.

| Trigger | Why | Approver |
|---|---|---|
| Schema or data migration | Hard to reverse; outage and data-loss risk | Eng lead / DBA |
| Destructive data operation | No undo | Eng lead + on-call |
| Auth / authz change | Privilege-escalation blast radius | Security reviewer |
| Payments or financial logic | Regulatory and monetary risk | Eng lead + compliance |
| Public API breaking change | External consumer contract | API owner |
| New dependency | Supply chain, license, attack surface | Eng lead, SCA-gated |
| Infra / IaC | Security posture, cost, availability | Infra / SRE |
| Anything touching PII | Legal and privacy exposure | Privacy + eng lead |
| Untrusted-content-triggered PR | Injection surface (§4) | Human, no auto-merge |
| Diff exceeds size threshold | Review quality collapses with size | Reviewer; may require a split |

## 6. Review habituation is a real failure mode

Do not assume the human gate holds just because it exists.

- A study of 400 reviewers across 11,429 reviews found approval rates on agent-authored
  PRs rose **+14.5pp**, with review latency up 3.5x but **inline-comment effort down 22%**
  — reviewers wait longer and inspect less.
- Automation-bias literature: erroneous automated recommendations get followed ~26% more
  often once a system is trusted.
- One study found human intervention succeeded only **9–26%** of the time even after a
  problem surfaced — a recognition bottleneck, not mere inattention.

Countermeasures:

- Keep escalation triggers narrow so volume stays low.
- Give reviewers a **structured summary** — what changed, why, blast radius, evidence
  bundle — for routine PRs; reserve full diff review for escalation tier.
- Cap diff size; one task per PR.
- Rotate reviewers on high-volume agent queues.
- Track **review depth** (time-on-diff, comment rate), not just approve/reject counts.
  Depth degrading is the leading indicator.
- Never let one agent approve another agent's PR.

## 7. Reversibility

Design so that being wrong is cheap.

| Control | Application |
|---|---|
| Dry-run first | Any state-changing operation produces a plan artifact before the real op is offered |
| Atomic changes | Partial failure must not leave inconsistent state |
| Feature flags | Agent-shipped code ships dark by default; a bad change is a flag flip |
| Canary + auto-rollback | Progressive rollout with SLO-triggered rollback, required at L3+ |
| Granular commits | Every meaningful action its own commit — `git revert` and `git bisect` stay cheap |
| **Expand / contract migrations** | Expand (additive, backward-compatible) → backfill (batched) → **contract (destructive, separate, human-gated deploy)**. Rollback before contract is just "don't contract." The contract step is always an escalation. |

## 8. CI as independent re-verification

The agent's local green is a claim made inside a trust boundary that might be
compromised — injected instructions, a stale test run, a mocked-away failure. CI green is
an independently executed fact.

```
PR opened by agent (branch, never main)
  ├─ Gate 0  secret scan on diff ................ hard fail, no override
  ├─ Gate 1  lint + typecheck ................... re-run, not trusted from the agent
  ├─ Gate 2  unit + integration ................. fresh execution
  ├─ Gate 3  diff coverage + cheat-flag scan .... 03 §3
  ├─ Gate 4  SCA + dependency existence ......... new deps flagged for human
  ├─ Gate 5  architecture fitness + ratchet ..... 06 §3
  ├─ Gate 6  E2E against ephemeral environment .. artifacts attached
  ├─ Gate 7  policy: diff classified vs escalation table → label
  └─ Gate 8  human review via CODEOWNERS ........ required
        → merge
```

Each is a **required status check matched by exact context string** — renaming a CI job
silently un-enforces the check, a common and dangerous footgun.

One mechanical detail that matters: GitHub does not trigger workflows on commits made
with the default `GITHUB_TOKEN`. An agent committing that way produces a PR whose CI
never runs. Authenticate as a GitHub App (the Claude Code Action does this) so downstream
CI actually fires — otherwise your independent verification layer silently doesn't exist.

## 9. Audit trail

Every agent commit should carry:

- The task/spec ID that produced it
- A link to the evidence bundle (03) and the CI run
- The model and harness version

Retain full run transcripts, tool calls, and hook decisions immutably, linked to the PR.
Organizational trust in agent-authored code rests on three routines: provenance,
independent CI re-verification, and a recorded *human* review attestation — not a bot's
approval standing in for one.
