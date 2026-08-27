# 03 — Definition of Done

The contract that makes "done" checkable. An evidence bundle, the rules that govern it,
and the catalog of ways an agent will try to fake it.

---

## 1. The rule

> **A completion claim is invalid unless every gate in the evidence bundle has
> `exit_code: 0`, the assumption register has zero unresolved entries, and no
> cheat-detector flag is raised.**

Enforced by the `Stop` hook, not by asking. The agent is free to *want* to be done.

### The three sub-rules that make it work

1. **Deterministic beats judgment, always.** Model judgment may *raise* the bar — flag
   something the gates missed — but can never mark a red gate green. Encoded literally:
   the `Stop` hook reads exit codes, not prose.
2. **The harness owns execution.** The agent proposes; the gate runner executes and
   records. The agent cannot write to the runner, the gate config, or CI files.
3. **No assumption may terminate as inference.** An unknown is resolved by reading code,
   reading docs, or asking a human. `resolved-by-inference` is a build failure.

## 1b. This is now a standards question, not an invention

As of 2026 the evidence-bundle idea has real prior art. Build on it rather than inventing:

- **Action Evidence Packages** (arXiv:2608.00801) — signed, append-only records of what an
  agent did, what authorized it, and the outcome, built on IETF RATS remote attestation.
- **Evidence-grounded verification** (arXiv:2607.01793) — verify the recorded trajectory
  *and the final environment state*, explicitly instead of self-report.
- **CAVA** (arXiv:2607.13716) — canonical, runtime-independent action records, for when one
  action is represented inconsistently across heterogeneous runtimes.

**And one caveat that belongs in any long-term plan.** Verification Horizon
(arXiv:2606.26300) argues no fixed reward function stays effective as policy capability
grows — verification must co-evolve with the model. A static evidence spec is not a
permanent solution. Re-validate it as models get better at satisfying it
non-substantively; assume the schema below has a shelf life.

## 2. Evidence bundle schema

Written to `.claude/evidence/<task-id>.json`. This generalizes the SLSA/in-toto idea —
a signed predicate over an artifact — down to a per-task record.

```json
{
  "$schema": "./evidence-bundle-v1.json",
  "task_id": "string",
  "commit_sha": "string (or dirty-worktree snapshot hash)",
  "diff_digest": "sha256 of the full diff",

  "assumption_register": [
    {
      "id": "string",
      "text": "Is a null email valid input to createUser?",
      "status": "resolved-by-reading-code | resolved-by-asking | open",
      "resolution_evidence": "src/models/user.py:42 — email is NOT NULL in schema"
    }
  ],

  "requirement_trace": [
    { "requirement_id": "AC-1", "acceptance_test_ids": ["test_rejects_null_email"], "status": "pass" }
  ],

  "red_proof": {
    "test_id": "test_rejects_null_email",
    "ran_at_commit": "sha before implementation",
    "exit_code": 1,
    "failure_kind": "assertion",
    "stderr_excerpt": "AssertionError: expected ValidationError"
  },

  "gates": [
    {
      "gate": "typecheck | lint | unit | integration | diff-coverage | mutation | e2e | security | arch | perf",
      "command": "exact shell command",
      "exit_code": 0,
      "stdout_sha256": "string",
      "artifact_paths": ["playwright-report/trace.zip"],
      "duration_ms": 0,
      "executed_by": "harness",
      "timestamp": "ISO8601"
    }
  ],

  "coverage":      { "diff_pct": 0.0, "threshold": 80.0 },
  "mutation_score":{ "before": 0.0, "after": 0.0, "scope": "diff" },
  "cheat_flags":   [],

  "verifier": {
    "model": "must differ from the implementer's model",
    "verdict": "pass | fail",
    "findings": [{ "severity": "CRITICAL|HIGH|MEDIUM|LOW", "text": "string", "addressed": true }]
  },

  "escalation": { "required": false, "reason": null, "blocked_report": null },

  "claim": "The only natural-language statement permitted. Must cite gates by index."
}
```

`failure_kind` in `red_proof` matters: an `import`/`collection` failure proves the file
doesn't parse, not that the test exercises anything. Only `assertion` (or an expected
exception mismatch) counts as a valid RED.

## 3. Cheating-pattern catalog

Every one of these is documented behavior from the reward-hacking literature, not
hypothetical — and measured in current agents: a 28.57% baseline hacked-resolved rate
across Claude Opus 4.6/4.7, Qwen3.6-Max and DeepSeek V4 Pro, falling to **0.56% under
active monitoring** (arXiv:2606.26300). Detection is worth roughly 50x here. Each needs an automated detector because each is what an agent reaches for
when a gate is red and the retry budget is running down.

| # | Pattern | Automated detection |
|---|---|---|
| 1 | Test skipped/disabled (`.skip`, `xit`, `@Disabled`, `@pytest.mark.skip`) | AST/regex scan of changed hunks; fail if net skip count increases |
| 2 | Assertion deleted or weakened (tolerance widened, `assertEqual` → no-op) | Structural diff of test files; assertion count delta must be ≥ 0 per touched test |
| 3 | `\|\| true`, `set +e`, `--exit-zero`, `continue-on-error: true` added | Grep CI configs and shell scripts in the diff for exit-code suppression |
| 4 | Mock added around the exact function under test | Flag new mock/stub/patch whose target symbol matches the changed production function |
| 5 | Hardcoded output matching a literal test input | Constant in production code identical to a value in the corresponding fixture |
| 6 | Diff coverage drops | `diff-cover` against the merge base; block on any decrease on touched files |
| 7 | Mutation score drops | Diff-scoped mutation re-run; block if killed-mutant ratio decreases |
| 8 | Test-file-only diff closing a bug ticket | If 100% of changed lines are under test paths and ticket type is `bug`, require justification — never auto-pass |
| 9 | Test edited to match new (wrong) behavior | Assertion-value change co-located with a production behavior change in one commit → mandatory Verifier review |
| 10 | Grader/harness tampering | Checksum gate config, hooks, and CI files before and after the run; `PreToolUse` deny on writes to those paths |
| 11 | Retry-until-green on a flaky test | Detect added `retry(...)`, raised timeouts/thresholds, or `@flaky` without a root-cause note → route to quarantine, never accept as a fix |
| 12 | Snapshot/contract re-recorded to force green | Any change to `__snapshots__/`, `*.pact.json`, or approved-baseline files without a corresponding source change → escalate |
| 13 | Answer retrieved rather than derived | Seal git history beyond HEAD and restrict egress during the solve phase; log outbound calls |
| 14 | Hallucinated dependency added | Resolve every new package against the real registry before install; typosquat-distance check against known packages |

Implementation lives in [`kit/hooks/scan-diff-cheats.sh`](kit/hooks/scan-diff-cheats.sh).

### The one that deserves special handling

**Snapshot and contract re-recording (#12).** This is the highest-frequency,
lowest-friction cheat available, because "update the snapshot" is a legitimate operation
with a one-flag invocation. The rule:

> An agent may never self-authorize `--update-snapshots`, `jest -u`,
> `pact-broker publish`, or an approval-test baseline rewrite inside its own gate loop.

It proposes the old-vs-new diff as an artifact. A separate approval step — different
session, or a human — commits the new baseline. Treat it exactly like a state-mutating
external action.

## 4. Assumption register

The mechanism that answers "no assumptions."

Append-only, at `.claude/evidence/<task-id>.assumptions.jsonl`. The agent writes an entry
the moment it notices an underspecified point, **before** proceeding. Each entry
terminates in exactly one of:

- `resolved-by-reading-code` — with `file:line` evidence
- `resolved-by-asking` — with the human's answer quoted
- `open` — blocks completion

There is deliberately no `resolved-by-inference` status. If the agent wants to guess, it
must instead escalate. A pre-completion gate greps for `"status": "open"` and fails.

## 5. Retry budget, thrash detection, escalation

Unbounded retry is how a stuck agent turns into an expensive stuck agent — and how it
eventually starts cheating.

| Control | Rule |
|---|---|
| **Retry budget** | Max 3 attempts **per failing gate**, tracked separately. Thrashing on one gate must not consume budget for unrelated ones. |
| **Thrash detector** | Hash `(file, gate, diff-shape)` per attempt. Same shape twice without the gate flipping → stop immediately. Catches "keep tweaking the same line" faster than a counter would. |
| **Escalation trigger** | Budget exhausted, thrash detected, an escalation-table path touched (07), or an assumption still `open` after one resolution attempt. |

### The blocked report contract

A low-information "I'm blocked" is just false success wearing a different hat. A blocked
report must contain:

1. The exact failing gate — command, exit code, stderr excerpt.
2. What was tried, and why each attempt failed. Not "I tried a few things."
3. The specific unknown or decision that requires a human.
4. A recommendation with trade-offs, not just a question.

A report missing 1–3 should itself fail a lint check before reaching the human.

## 6. What deterministic gates cannot cover

Being honest about the boundary. These require the Verifier or a human, and they are
exactly where the METR maintainer-review study found agents failing:

| Deterministic | Judgment-only |
|---|---|
| Compiles, typechecks | Is this the right design for the system? |
| Tests pass | Did we solve the *right* problem? |
| Diff coverage ≥ threshold | Does this name mean what it says? |
| Mutation score ≥ baseline | Is the abstraction level consistent? |
| Lint, complexity, duplication | Are there concurrency hazards a test wouldn't hit? |
| Architecture fitness functions | Is this backward compatible for real callers? |
| SAST, secrets, SCA clean | Would a senior engineer approve this? |
| No cheat flags | Is the scope disciplined, or is unrelated churn hiding the change? |

The left column is a hard gate. The right column is the Verifier's checklist, and it can
only ever *add* findings.

**A nuance the first draft got wrong.** LLM-as-judge is not categorically unusable in 2026.
Practitioner consensus is that a judge calibrated against a human gold set, using
chain-of-thought judging, above roughly 0.6 agreement, is acceptable as *a* signal. The
problem is that measured judges sit at or below that threshold specifically on
agentic-completion judgment (AUROC ≤0.65 — [01 §1](01-evidence-base.md)). So: an
uncalibrated judge is not a gate, a calibrated one is a contributor, and neither can clear
a red deterministic check.
