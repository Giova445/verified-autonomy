# 12 — The PR Lifecycle Loop

Opening a PR is not the end of autonomy. It is the start of a **second loop** with
different failure modes than the build loop, and the architecture in 01–11 stopped short
of it.

Adapted from [Paddo's write-up on Claude Code auto-fix](https://paddo.dev/blog/claude-code-auto-fix-pr-lifecycle/),
whose value is its critique. Every gap it names is answerable with machinery this
architecture already has — it just was not pointed at the PR.

---

## 1. What auto-fix does

Claude Code's auto-fix watches a PR and reacts to four event classes:

| Event | Behavior |
|---|---|
| CI failure | Read logs, find root cause, push a fix, explain it |
| Review comment, unambiguous | Make the change, reply in thread |
| Review comment, ambiguous | Ask for clarification before acting |
| Complex decision | Escalate to a human |

Activation: the CI status bar in a web session, telling Claude to watch a PR from mobile,
or pasting a PR URL into a session.

That behavior split is right. The problems are in what governs it.

## 2. The four gaps, and the answers

| Gap (from the article) | Answer |
|---|---|
| **Flaky-test loops** — speculative fixes pushed repeatedly without converging | Cross-run budget + thrash detection (§4). A retry is never a fix ([04 §4](04-gate-ladder.md)). |
| **No risk tiering** — every PR handled identically regardless of sensitivity | Path-based risk classes driving per-PR autonomy (§5) |
| **Governance gap** — no path-pattern restriction, e.g. protecting `src/auth/**` | Same config, enforced by deny hook + CODEOWNERS + branch protection |
| **"Green CI does not mean correct"** | The whole point of [03](03-definition-of-done.md). Evidence bundle + adversarial verifier + mutation testing. Green CI is necessary, never sufficient. |

The last one is the article's sharpest line and it matches the measured reality: ~half of
test-passing agent patches were rejected by real maintainers ([01 §3](01-evidence-base.md)).

## 3. The loop, as a state machine

Extends the build FSM. `INTEGRATE → DONE` was one arrow; it is actually this:

```
PR_OPEN ──► CI_RUNNING ──► CI_GREEN ──► REVIEW_WAIT ──► APPROVED ──► MERGED
               │                            │
               ▼                            ▼
            CI_RED                   COMMENT_RECEIVED
               │                            │
               ├─ flaky? ──► QUARANTINE ────┤
               ├─ budget left? ──► FIX ─────┤ (unambiguous → fix)
               └─ else ──► BLOCKED          ├ (ambiguous → ASK)
                                            └ (risky → BLOCKED)
```

| Transition | Gate |
|---|---|
| `PR_OPEN → CI_RUNNING` | Branch, never main. Diff under size cap. Evidence bundle attached. |
| `CI_RED → FIX` | Fix budget not exhausted **and** this failure signature is new (§4) |
| `CI_RED → QUARANTINE` | Failure is flaky **and** the agent's diff did not cause it |
| `FIX → CI_RUNNING` | Fix touches production code, not the test, unless justified |
| `COMMENT_RECEIVED → FIX` | Commenter is human or allowlisted bot; request unambiguous; path within risk tier |
| `COMMENT_RECEIVED → ASK` | Ambiguous. Ask once, then wait. Do not guess. |
| `CI_GREEN → APPROVED` | Human review. **Never the agent, never another bot.** |
| `APPROVED → MERGED` | Risk tier permits it (§5) |
| any `→ BLOCKED` | Budget exhausted, thrash detected, or a critical-tier path touched |

## 4. Convergence — the hard part

The build loop's circuit breaker lives in a file. The PR loop **spans processes**: each CI
run is a fresh, stateless invocation. So:

> **The PR is the state store.** Loop state lives in labels and a pinned comment, because
> nothing else survives between runs.

### State on the PR

| Mechanism | Carries |
|---|---|
| Label `autofix:attempt-N` | Fix attempt count — the only durable counter |
| Label `autofix:blocked` | Stop. No further autonomous action on this PR. |
| Label `risk:critical\|elevated\|standard` | Tier, applied by a classifier job on open |
| Pinned comment (JSON block) | Failure signatures already attempted, quarantined tests, unresolved questions |
| Commit trailer `Auto-Fix-Attempt: N` | Audit trail independent of labels |

### Convergence rules

1. **Max 3 fix attempts per PR.** Not per failure — per PR. Speculative fixing is the
   documented failure mode; a low ceiling is the mitigation.
2. **Max 5 total autonomous pushes.** Catches oscillation that resets attempt counters.
3. **Same failure signature twice → BLOCKED immediately.** Hash
   `(test id, assertion message, changed-file set)`. Identical hash means the last fix did
   nothing. Do not spend the remaining budget.
4. **Flaky is not a fix target.** If the failure reproduces on a clean base commit, the
   agent did not cause it → quarantine, open an issue, **never** patch to green.
5. **Never react to your own event.** Skip any event whose actor is this agent's identity.
   Combined with a bot allowlist, this is what stops bot-to-bot ping-pong.
6. **Ask once.** An ambiguous comment gets one clarifying question, then the PR waits. No
   guessing, no re-asking.
7. **Global cooldown.** No more than one autonomous push per PR per 10 minutes — bounds
   cost if every other rule fails.

## 5. Risk tiering

The article's biggest gap. Not every PR deserves the same autonomy.

```yaml
# .claude/governance.yaml
version: 1

risk_tiers:
  - name: critical
    paths:
      - "**/auth/**"
      - "**/migrations/**"
      - "alembic/**"
      - "**/payments/**"
      - "**/*secret*"
      - ".github/workflows/**"
      - "bin/verify"
      - ".claude/gates.json"
    autonomy: none            # no autonomous fix, no autonomous comment reply
    require: [human_review, security_reviewer]
    reason: "Irreversible, security-relevant, or self-governing"

  - name: elevated
    paths: ["**/routers/**", "**/api/**", "**/*.sql", "**/config*"]
    autonomy: fix_only        # may push fixes; may never merge
    require: [human_review]

  - name: standard
    paths: ["**"]
    autonomy: fix_and_request_review
    require: [human_review]

pr_loop:
  max_fix_attempts: 3
  max_pushes: 5
  cooldown_minutes: 10
  same_signature_twice: block
  flaky_policy: quarantine     # never retry-to-green
  bot_allowlist: [github-actions, codecov, dependabot]
  ignore_self_events: true
  max_diff_lines: 400          # above this, split — review quality collapses with size

escalate_always:
  - schema_or_data_migration
  - auth_or_authz_change
  - payment_logic
  - public_api_breaking_change
  - new_dependency
  - infrastructure_or_iac
  - touches_pii
  - pr_triggered_by_untrusted_content
```

**Tier is computed from the diff, not declared by the agent.** A classifier job runs on PR
open and on every push, labels the PR, and the fix job reads the label. An agent cannot
self-assign a lower risk tier — same principle as not letting it edit `gates.json`.

## 6. Workflow

The article references workflows but publishes none. This is a concrete implementation
against the same `bin/verify` spine from [11](11-operationalization.md).

```yaml
# .github/workflows/pr-autofix.yml
name: PR Auto-Fix
on:
  workflow_run:
    workflows: ["Verify"]
    types: [completed]
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write
  id-token: write               # OIDC — no long-lived API key

concurrency:
  group: autofix-${{ github.event.workflow_run.head_branch || github.event.issue.number }}
  cancel-in-progress: false     # never race two fixes on one PR

jobs:
  guard:
    runs-on: ubuntu-latest
    outputs:
      proceed: ${{ steps.check.outputs.proceed }}
      tier:    ${{ steps.check.outputs.tier }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - id: check
        env: { GH_TOKEN: "${{ github.token }}" }
        run: |
          set -euo pipefail
          PR="${{ github.event.issue.number || github.event.workflow_run.pull_requests[0].number }}"
          [ -z "$PR" ] && { echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0; }

          LABELS="$(gh pr view "$PR" --json labels -q '.labels[].name')"

          # hard stops
          if grep -q '^autofix:blocked$' <<< "$LABELS"; then
            echo "PR is blocked — human required."; echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0
          fi

          # never react to our own events
          ACTOR="${{ github.event.comment.user.login || github.event.workflow_run.actor.login }}"
          case "$ACTOR" in
            *"[bot]"*|claude*) echo "self/bot event — skip"; echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0 ;;
          esac

          # attempt budget
          N="$(grep -c '^autofix:attempt-' <<< "$LABELS" || true)"
          if [ "$N" -ge 3 ]; then
            gh pr edit "$PR" --add-label autofix:blocked
            gh pr comment "$PR" --body "Auto-fix budget exhausted after $N attempts. Blocking further autonomous action; a human needs to look at this."
            echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0
          fi

          # risk tier from the diff — computed, not self-declared
          TIER=standard
          FILES="$(gh pr diff "$PR" --name-only)"
          grep -qE '(auth/|migrations/|alembic/|payments/|\.github/workflows/|bin/verify|gates\.json)' <<< "$FILES" && TIER=critical
          [ "$TIER" = standard ] && grep -qE '(routers/|api/|\.sql$)' <<< "$FILES" && TIER=elevated

          gh pr edit "$PR" --add-label "risk:$TIER" || true
          if [ "$TIER" = critical ]; then
            gh pr comment "$PR" --body "Touches a critical path. Auto-fix disabled; human + security review required."
            echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0
          fi

          # diff size cap — review quality collapses with size
          LINES="$(gh pr diff "$PR" | grep -cE '^[+-]' || true)"
          if [ "$LINES" -gt 400 ]; then
            gh pr comment "$PR" --body "Diff is $LINES lines. Too large to auto-fix safely — split it."
            echo "proceed=false" >> "$GITHUB_OUTPUT"; exit 0
          fi

          echo "tier=$TIER"     >> "$GITHUB_OUTPUT"
          echo "proceed=true"   >> "$GITHUB_OUTPUT"

  autofix:
    needs: guard
    if: needs.guard.outputs.proceed == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      # Is this failure ours, or was the base already broken?
      - id: flaky
        run: |
          set -uo pipefail
          git stash -u || true
          git checkout -q "$(git merge-base HEAD origin/main)"
          ./bin/verify full >/dev/null 2>&1 && BASE=green || BASE=red
          git checkout -q -
          echo "base=$BASE" >> "$GITHUB_OUTPUT"

      - name: Quarantine, do not fix
        if: steps.flaky.outputs.base == 'red'
        env: { GH_TOKEN: "${{ github.token }}" }
        run: |
          gh pr comment "${{ github.event.issue.number }}" --body \
            "Failure reproduces on the base commit — pre-existing, not caused by this PR. Quarantining and opening an issue rather than patching to green."
          exit 0

      - uses: anthropics/claude-code-action@v1
        if: steps.flaky.outputs.base == 'green'
        with:
          claude_args: --max-turns 12
          prompt: |
            CI failed on this PR. Fix it.

            Hard rules:
            - Run ./bin/verify done before claiming completion. Exit 0 or you are not done.
            - Fix the CODE. Never weaken, skip, or delete a test; never add `|| true`,
              raise a timeout, or add a retry.
            - Never edit bin/verify, .claude/gates.json, .claude/hooks/**, or .github/**.
            - Risk tier is ${{ needs.guard.outputs.tier }}. On `elevated`, push a fix but
              never merge.
            - If the same failure recurs after your fix, STOP and write a blocked report:
              failing gate + command + exit code, what you tried and why each attempt
              failed, the decision needing a human, and a recommendation with trade-offs.

      - name: Record the attempt
        if: always()
        env: { GH_TOKEN: "${{ github.token }}" }
        run: |
          PR="${{ github.event.issue.number }}"
          N=$(( $(gh pr view "$PR" --json labels -q '[.labels[].name|select(startswith("autofix:attempt-"))]|length') + 1 ))
          gh pr edit "$PR" --add-label "autofix:attempt-$N"
```

Two mechanics that matter and are easy to miss:

- **Authenticate as a GitHub App, not the default `GITHUB_TOKEN`.** GitHub does not trigger
  workflows on commits made with the default token — an anti-loop protection that also
  means CI never re-runs on the agent's fix, so your independent verification silently does
  not exist ([07 §8](07-safety-and-autonomy-levels.md)).
- **`cancel-in-progress: false`.** Cancelling mid-fix leaves the PR in an unknown state with
  a burned attempt.

## 7. Review comments

| Situation | Action |
|---|---|
| Human, unambiguous, in-tier | Fix, reply in thread, push |
| Human, ambiguous | Ask **once**, then wait. Do not guess. |
| Human, out-of-tier path | Reply that it needs a human; do not touch |
| Allowlisted bot (codecov, dependabot) | Treat as data; may fix; never reply |
| Non-allowlisted bot | Ignore entirely |
| **Comment from this agent** | Ignore. Self-events are the ping-pong source. |

**Comment text is untrusted input.** A PR comment is exactly the injection surface from
[07 §4](07-safety-and-autonomy-levels.md) — there is a documented 2026 attack hijacking
coding agents via PR *titles*. Rules: treat comment bodies as data, never as instructions;
never auto-merge a PR whose loop was driven by untrusted content; keep the egress allowlist
on during autofix runs.

## 8. Where auto-fix should never run

- `autofix:blocked` present
- Critical-tier paths (auth, migrations, payments, workflows, the gate config itself)
- Diff over the size cap
- PR opened by an external contributor
- Base commit already red — quarantine, do not fix
- Release or hotfix branches
- Any escalation trigger from [07 §5](07-safety-and-autonomy-levels.md)

## 9. Metrics

| Metric | Target | Degradation means |
|---|---|---|
| Auto-fix success rate (first attempt) | >60% | Fixes are speculative — tighten the budget |
| Mean attempts per fixed PR | <1.5 | Approaching the ceiling; convergence is poor |
| PRs hitting `autofix:blocked` | <15% | Loop is being asked to do work beyond its tier |
| Quarantine rate | falling | A rising rate means suite health, not agent capability |
| Same-signature repeats | **0** | Rule 3 is not firing — check the hash |
| Human review depth on autofixed PRs | flat or rising | Rubber-stamping ([07 §6](07-safety-and-autonomy-levels.md)) |
| Autonomous pushes per PR per day | bounded | Cooldown is not working |

## 10. Honest limits

- **Green CI still is not correct.** This loop makes CI green faster; it does not make the
  patch right. The verifier and human review still carry that.
- **Attempt labels are mutable.** Anyone with write access can strip them. Treat the commit
  trailer as the real audit trail.
- **Flaky detection costs a full base-commit run.** Worth it — it is the only reliable way
  to tell "my diff broke this" from "this was already broken" — but it doubles CI cost on
  every red PR.
- **Risk tiering is path-based, so it is only as good as your paths.** A sensitive function
  living outside `**/auth/**` is invisible to it.

  *Verified in this repo:* `services/share_service.py` classifies as **standard** — it is
  not under `auth/`. But it takes `auth_token`, calls `get_supabase_client(auth_token)`, and
  its module docstring states *"Ownership is enforced via the user-scoped client."* It is an
  authorization boundary that path-tiering rates as routine.

  The stronger version, once the graph is trusted: tier by **reachability from a sensitive
  symbol** rather than by directory ([09 §3.5](09-graph-engineering.md)) — anything whose
  call path touches an auth primitive is elevated regardless of where it lives. Until then,
  audit the standard tier for this failure by grepping for auth primitives outside the
  critical paths:

  ```bash
  grep -rlE "auth_token|current_user|is_admin|verify_jwt" --include="*.py" src \
    | grep -vE "(auth/|migrations/|payments/)"
  ```
