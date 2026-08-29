# Two verification items, resolved

Both were open questions where the answer mattered more than any benchmark number, and both
were resolved by experiment or by fetching the primary source — not by re-reading a summary.

---

## 1. Do subagents inherit the parent's `PreToolUse` hooks?

**Answer: YES on Claude Code 2.1.250.** The documentation is correct for this version;
`anthropics/claude-code#27661` does not reproduce here.

### Why it mattered

The whole mechanical story for capability attenuation — "a child may drop capabilities but
cannot add them" — rests on this. If a subagent escapes the parent's `PreToolUse` hooks, then
every deny rule silently stops applying the moment work is delegated, and the enforcement
layer is decorative for exactly the workflow it was built for.

`#27661` (opened 2026-02-22, closed with no visible maintainer response) reports that
subagents inherit neither hooks, nor permission rules, nor CLAUDE.md. The current docs state
the opposite, including that `agent_id` and `agent_type` appear in the hook payload. Both
cannot be true.

### Design

Resolved by experiment, and deliberately **not** by reading either source.

The ground truth is the **hook's own append-only log**, not the model's account. A model
saying "I was blocked" is a self-report, and unverified self-reports are the failure this
project exists to stop. The hook records every invocation with its payload keys; if it never
fires for the subagent's call, it did not inherit, whatever anyone says afterwards.

The experiment runs in a throwaway project directory with its own `settings.json`. It does
not touch user or global configuration.

Guard: the hook is proven to deny standalone *before* the run. Otherwise a silent log would
be indistinguishable between "did not inherit" and "hook was broken."

### Result

`bash benchmark/verification/run-hook-inheritance.sh`, on **Claude Code 2.1.250**:

```
invocations: 2   with agent_id (i.e. from a subagent): 1
  'echo CANARY_SENTINEL_9f3a-parent'     agent_id=None                agent_type=None
  'echo CANARY_SENTINEL_9f3a-subagent'   agent_id='a9dae3a715cf6f5ef' agent_type='general-purpose'
INHERITED
```

The parent's payload carries 10 keys; the subagent's carries 12 — the two extra are exactly
`agent_id` and `agent_type`, as documented. The `exit 2` deny was honoured at **both** levels,
and the sentinel string never appears as command output anywhere in the transcript, so it
never executed.

### Limits

- One version, **2.1.250**. The answer may be version-dependent; if `#27661` was accurate when
  filed, this is a fix, not a contradiction. Re-run the script to check any other version —
  that is why it ships.
- Tests `PreToolUse` on `Bash` only. Permission rules, CLAUDE.md and other hook events were
  not tested and remain unverified.
- Tests inheritance one level deep. Nested subagents were not tested.

---

## 2. The "82.9% multi-agent coordination attack success" figure

**Answer: the figure is REAL and correctly quoted. Both arXiv IDs usually cited for it are
wrong.**

This **corrects an earlier statement in this project** that the number appeared unsourced and
should not be cited. That was wrong. It is sourced; the citation chain was broken.

### Primary source

**AgentLeak: A Benchmark for Internal-Channel Privacy Leakage in Multi-Agent LLM Systems**,
arXiv **2602.11510** (v1 2026-02-12, v3 2026-06-15; IEEE Access 2026,
DOI 10.1109/ACCESS.2026.3704541). Section VI, *"Finding 6: Adversarial Attacks Achieve High
Success Rates"* — **Table XIV** in v3, **Table XI** in v1.

Row, verbatim: `F4 | Multi-Agent Coord. | 252 | 82.9% | [77.8, 87.1]`

### What it actually measures — and three ways it is usually misrepresented

- **"Success" means privacy leakage**, defined as at least one sensitive field extracted
  through any channel. Not code execution, task hijack, or system takeover. Circulated as a
  generic "attack success rate," it reads as compromise, which the paper does not measure.
- **"Highest of all attack categories" is false on the paper's own terms.** Only 4 of 6
  families were instrumented; F5 and F6 are excluded from trace-level tracking.
- **The ranking is not statistically separable.** F4's CI [77.8, 87.1] overlaps F1
  [77.2, 82.2], F2 [75.1, 82.3] and F3 [74.2, 84.1]. The authors flag it themselves as
  possible ceiling effect (σ ≈ 1.7%).

Threat model is adversary level **A2 (strong)** — direct access to components, compromised
tools, or control of agent roles. n = 252 of 1,983 adversarial tests, on GPT-4o, GPT-4o-mini,
Claude 3.5 Sonnet, Mistral Large and Llama 3.3 70B. Leakage adjudicated by LLM-as-judge at
τ=0.72, tuned against 200 expert-labeled trace segments.

### The miscitation

Both IDs commonly given resolve to real papers that **cite AgentLeak but never state the
number** — someone credited the survey they found it through rather than the benchmark it
came from.

- **arXiv 2606.10749** — *Toward Secure LLM Agents* (Ling et al.). Zero occurrences of "82.9".
- **arXiv 2603.09002** — *Security Considerations for Multi-agent Systems*. Four raw hits for
  "82.9", all SVG path coordinates (`282.94`) inside figures.

Do not confuse it with arXiv 2507.06850, which reports **82.4%** for inter-agent-communication
compromise — different paper, different metric, one decimal apart.

### Safe phrasing

> In the AgentLeak benchmark (arXiv:2602.11510, Table XIV), multi-agent coordination attacks
> (n=252, strong-adversary A2) leaked at least one sensitive field in 82.9% of trials
> [95% CI 77.8–87.1], statistically indistinguishable from the 78.9–79.8% of the other
> instrumented families.
