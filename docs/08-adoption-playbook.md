# 08 — Adoption Playbook

How to install this in a project, in what order, what to measure, and what will go wrong.

---

## 1. Sequence

Do not install everything at once. Each phase should be stable before the next.

### Phase 1 — Make "done" mean something (week 1)

The minimum viable version of this whole architecture. Everything else is refinement.

1. Write `.claude/gates.json` naming your project's **real** commands. Not aspirational
   ones — commands that pass today.
2. Install `kit/hooks/gate.sh` and wire the `Stop` hook.
3. Install `kit/hooks/deny-dangerous.sh` on `PreToolUse`.
4. Verify the block works: break a test deliberately, ask the agent to finish, confirm it
   refuses and explains why.

**Step 4 is not optional.** An unverified gate is worse than no gate, because you will
trust it.

### Phase 2 — Close the cheating paths (week 2)

5. Install `kit/hooks/scan-diff-cheats.sh`.
6. Add diff coverage to the ladder (`diff-cover --fail-under=80`).
7. Deny agent writes to `.claude/hooks/**`, `.claude/gates.json`, `.github/workflows/**`.
8. Add the assumption register to the agent's workflow.

### Phase 3 — Raise the floor (weeks 3–4)

9. Type strictness (`noUncheckedIndexedAccess`, `mypy --strict`, `-D warnings`).
10. Architecture fitness function with 0 violations on new code.
11. Complexity and duplication baselines with the ratchet.
12. Secret scanning + SCA + dependency-existence check.

### Phase 4 — Quality of tests, not just presence (month 2)

13. RED-proof gate (the TDD enforcement).
14. Diff-scoped mutation testing, break at 70%, ratchet up.
15. Test scenario catalog as a project skill (05).
16. Adversarial Verifier subagent, on a different model.

### Phase 5 — Autonomy (month 3+)

17. CI re-runs the full ladder; required status checks by exact name.
18. Branch protection, CODEOWNERS, no self-approval.
19. Move from L1 → L2. Sit there.
20. Consider L3 only with three months of clean metrics.

## 2. Per-project configuration

The only project-specific file should be `.claude/gates.json`. Everything else is portable.

```json
{
  "fast": [
    { "name": "lint",      "cmd": "make lint" },
    { "name": "typecheck", "cmd": "make typecheck" },
    { "name": "unit",      "cmd": "make test-unit" }
  ],

  "full": [
    { "name": "integration",   "cmd": "make test-integration" },
    { "name": "diff-coverage", "cmd": "diff-cover coverage.xml --compare-branch=origin/main --fail-under=80" },
    { "name": "arch",          "cmd": "lint-imports" },
    { "name": "cheat-scan",    "cmd": ".claude/hooks/scan-diff-cheats.sh" }
  ],

  "deferred": [
    { "name": "e2e",      "cmd": "npx playwright test" },
    { "name": "mutation", "cmd": "mutmut run --paths-to-mutate=src" }
  ]
}
```

### Monorepos

Scope gates per package. Claude Code loads nested `.claude/skills/` lazily and
directory-qualifies them (`apps/web:deploy`), so a per-package gate skill is viable. Run
only the gates whose package the diff touches — otherwise the ladder's cost scales with
repo size instead of change size, and the agent will start avoiding it.

### Distributing across many projects

Options, roughly in order of preference:

1. **Claude Code plugin marketplace** — `.claude-plugin/marketplace.json` bundles skills,
   hooks, agents, and MCP servers as one installable, version-pinnable unit. Closest
   thing to npm for agent config.
2. **`AGENTS.md`** for anything that should outlive one harness. Cross-tool convention
   read by 30+ tools. Worth noting: independent analysis found only ~1.6% of 10,000
   open-source repos actually contain one, so "de facto standard" is aspirational — but
   the portability argument stands, and Roo Code's 2026 shutdown is a live reminder that
   harness-specific config carries platform risk.
3. **Central config repo + git submodule** for the hooks directory.
4. Copy-paste. Fine for 2–3 projects, unmanageable at 10.

## 3. Metrics

Measure the harness, because intuition about whether it is working is not evidence. The
durable version of the METR result is not a percentage — their 2025 RCT found developers
19% slower on early-2025 tools, their 2026 re-run collapsed under selection bias, and no
RCT-quality replacement exists ([01 §4](01-evidence-base.md)). What survives is the
**perception gap**: in the one clean experiment, developers were wrong about their own
speed by roughly 40 percentage points, in the flattering direction.

| Metric | Definition | Target | Degradation means |
|---|---|---|---|
| **First-pass gate rate** | % of work items passing VERIFY without returning to RED | >70% | Spec/plan quality problem, not implementation skill |
| **Rework loops** | Mean RED↔GREEN cycles per item | <2 | Poor test design or unstable requirements |
| **Escalation rate** | % hitting BLOCKED at least once | <15% | Ambiguous specs or too-narrow tool permissions |
| **Time to green** | Wall clock RED → all gates green | task-normalized baseline | Context rot, tool friction, wrong model routing |
| **Human intervention rate** | % needing a human *decision* (not just review) | <10% | Harness under-scoped for the task class |
| **Cost per merged item** | All-agent tokens ÷ successfully integrated items | topology baseline (1x / 4x / 15x) | Topology escalation isn't paying for itself |
| **Cheat-flag rate** | Diff scans raising a flag | trending to 0 | Gates are too hard, or the agent is under retry pressure |
| **CI-after-local-green failure rate** | CI red after the agent's local gates were green | **<2%** | Your local ladder isn't representative — the most important diagnostic here |
| **Duplicate-work incidents** | Overlapping edits from two workers | 0 | Worktree/ownership boundary leak |
| **Review depth** | Time-on-diff and comment rate on agent PRs | flat or rising | Rubber-stamping (07 §6) |
| **Suite runtime growth** | vs LOC growth | ≤ parity | Test duplication accumulating |

Two of these deserve emphasis:

**CI-after-local-green failure rate** is the honest measure of whether your enforcement
layer actually mirrors your adjudication layer. Above ~5% and the agent is learning that
local green is meaningless.

**Cheat-flag rate** is a thermostat, not just an alarm. A rising rate usually means gates
became unreasonable rather than that the model got worse. Investigate the gate first.

## 4. Evaluating changes to the harness

Treat the harness like production code. Keep 15–25 golden tasks — real, from your repo,
with known-good outcomes. Anthropic started their own multi-agent evaluation with ~20
realistic queries rather than waiting for a large benchmark.

Run them before and after any harness change (new gate, new topology, new model route).
Ship only when first-pass gate rate, time-to-green, or cost-per-merged-item moves the
intended direction. SWE-bench's own FAIL_TO_PASS / PASS_TO_PASS structure is directly
reusable for your regression suite.

## 5. Anti-patterns

Ranked by how often they will actually bite.

| Anti-pattern | Why it fails |
|---|---|
| **Putting the gate in `CLAUDE.md`** | Layer 1 is persuasion. Under gate-failure pressure, the agent discards it. This is the single most common mistake. |
| **Gates the agent can edit** | An agent that can edit `gates.json` has no gates. Deny those paths. |
| **Skipping the "verify the block works" step** | You end up trusting a gate that silently never fires. |
| **Turning on strict gates in a legacy repo without a ratchet** | Everything is red, nobody can work, gates get disabled. Baseline first. |
| **Multi-agent because it sounds sophisticated** | ~15x tokens. Anthropic observed leads spawning 50+ subagents for trivial queries. Add a check instead of an agent. |
| **Self-review as the verifier** | Worse than parity: frontier models self-select correct answers *below* their generation accuracy, and the gap widens with capability (ICML 2026). Uncalibrated LLM-as-judge is not a gate. |
| **Coverage as the quality gate** | Trivially gamed by executing lines without asserting. Use diff coverage + mutation. |
| **Letting the agent update snapshots or contracts** | The lowest-friction cheat available. Requires separate approval. |
| **Retry-until-green on flakes** | Masks real races. "Failing, with extra steps." |
| **Escalating everything to humans** | Volume causes habituation; the gate becomes a rubber stamp. Narrow and non-negotiable beats broad and ignored. |
| **Jumping to L3/L4 early** | The controls that make L3 safe (canary, auto-rollback, diff classification) take months to build properly. |
| **Trusting benchmark numbers** | SWE-bench Verified is saturated (~96%) and partly discredited — OpenAI stopped reporting it after finding >60% of a sample unsolvable as written. Use SWE-bench Pro / SWE-rebench, and note ~half of test-passing patches were still rejected by real maintainers. |

## 6. What this architecture does not solve

Stated plainly, so the limits are known up front:

- **A test that fails for the wrong reason still passes the RED gate.** A hook proves a
  test fails, not that it fails for the intended reason. Mutation testing and the
  Verifier narrow this; nothing closes it.
- **Reward hacking is not eliminable by better tests.** SpecBench: agents saturate visible
  tests while the held-out gap grows ~28 points per 10x increase in LOC. Monitoring helps a
  great deal — 28.57% → 0.56% hacked-resolved (arXiv:2606.26300) — but gates catch known
  cheats, and novel ones arrive first.
- **Your detectors decay.** A false-success detector trained on one model generation
  transfers to the next at only AUROC 0.68–0.73. Recalibrate per model generation; treat
  the cheat catalog as a living document, not a fixed spec.
- **Model judgment remains necessary for design quality.** The METR maintainer study
  found half of test-passing patches rejected on grounds no gate encodes. A human still
  has to care.
- **This costs more than not doing it.** More tokens, more CI minutes, more wall-clock per
  task. The trade is fewer defects reaching main and less time on "almost right" code —
  which the Stack Overflow data says is where 66% of developers now lose their time. Track
  cost per merged item and decide with data.
- **Context rot is managed, not fixed.** Long autonomous runs degrade. Externalized state
  and compaction buy headroom; they don't remove the ceiling.

## 7. First-week checklist

- [ ] `.claude/gates.json` written with commands that pass on a clean checkout
- [ ] `gate.sh` installed, `Stop` hook wired
- [ ] `deny-dangerous.sh` installed on `PreToolUse`
- [ ] Agent writes denied to `.claude/hooks/**`, `.claude/gates.json`, `.github/workflows/**`
- [ ] **Deliberately broken test → agent refuses to finish → confirmed by hand**
- [ ] Deliberate `rm -rf` attempt → blocked → confirmed by hand
- [ ] Branch protection on; direct pushes to main disabled
- [ ] Baseline metrics recorded so week 4 has something to compare against
