# REVIEW.md — Stage 5a: PR review policy

Stage 5a runs **after** the machine has finished and **before** a human merges. It produces
findings. It does not produce a decision.

Everything below is specific to what has actually gone wrong in this repo. A review pass tuned
for null-pointer bugs would have caught **none** of the fifty commits of history here: the
defects were a verifier that exited 0 on an unreadable config, a control a shape-match defeated,
a recall number measured against a file nobody installed, a benchmark whose expected counts were
derived from the corpus it was measuring. Those are the shapes to hunt.

---

## 0. Standing rule — findings do not approve and do not block

- A review **cannot clear a red gate**. Deterministic results are facts; model judgment only ever
  *adds* findings (`skills/requesting-review/SKILL.md`). If the review says "fine" and a gate is
  red, the gate wins.
- A clean review is **not** a substitute for a green gate, and a green gate is not a substitute
  for a review. Neither implies the other.
- The reviewer's own job must exit 0 whatever it finds. Nothing in Stage 5a is a required check.
  Publishing the tally is the whole job.
- Merge authority sits with a **human code owner**, enforced by branch protection + CODEOWNERS —
  layer 3 in `README.md`, outside the agent's trust boundary.
- If a team wants a hard threshold ("no merge while `important > 0`"), it is a **separate**
  required check that reads the tally in §8, owned by whoever owns branch protection. The agent
  must not be able to edit it, for the same reason it must not edit `.claude/gates.json`
  ([docs/12 §5](docs/12-pr-lifecycle.md)). This document deliberately names no threshold: a policy
  that both produces the count and rules on it is the same object grading its own work.

> **State of this repo, 2026-09-03.** `CODEOWNERS` and `.github/CODEOWNERS` do not exist, and
> `.github/workflows/verify.yml` runs with `permissions: contents: read`. So the human-approval
> clause above is currently a **convention, not a mechanism**. Put that in the tally's `limits`
> rather than implying an approval gate that is not configured.
>
> ```bash
> ls CODEOWNERS .github/CODEOWNERS      # exit 1 today — no code owner is configured
> ```

## 1. Entry conditions

| Condition | Why |
|---|---|
| `./bin/verify done` has been run, and its exit code recorded in the tally | A reviewer reading red gates spends its context on what the machine already knows. Reviewing on red is allowed; hiding that you did is not. |
| Reviewer gets: the diff range, `.claude/evidence/latest.json`, the spec, the plan, the gate output | Everything a finding must be argued against |
| Reviewer does **not** get the session history | The implementer's reasoning contaminates the review — it has already explained away the thing to catch |
| Different model family from the implementer where one is available | Same-lineage judges share blind spots. Where unavailable: `independent_family: false`, and it goes in `limits` |

Scope: the diff, **plus** any file the diff makes wrong — a manifest row whose script the diff
renamed, a doc whose number the diff changed, a `kit/` copy of a `hooks/` file the diff edited.
Read the whole file around a changed hunk before filing against it.

---

## 2. The passes

Seven passes. P1–P4 are the verification-integrity passes and are the reason this policy is not a
generic checklist. Each names the failure as it actually occurred here.

### P1 — Can this check fail?

**Question:** delete the thing the check exists to catch. Does the check turn red?

**What happened here — and it took two commits, which is the actual lesson.**

*First fail-open (before `a15ab32`).* `run_tier` signalled an unreadable config with
`|| return 1`, and the `full)` and `done)` call sites discarded that status — `bin/verify` runs
under `set -uo pipefail`, **not** `set -e`. So a trailing comma in `gates.json` printed a Python
traceback, then `full: GREEN`, exit **0**, with an evidence bundle reading
`{"gates": [], "all_green": true}`. `a15ab32` fixed that by setting a `CONFIG_ERROR` sentinel and
refusing to certify at each call site.

*Second fail-open (introduced by that same fix, `a15ab32`).* The new refusal block in `full`
evaluated `$((attempts + 1))`, but `attempts` was initialised only inside the `done` branch. Under
`set -u` the branch aborts, the script falls off the end, and exits **0** again — through the very
block written to refuse. `selftest.sh` missed it for one reason: it only ever invoked
`verify done`, which was the branch that worked. `eefb635` closed it by hoisting `attempts` above
the `case`.

Replayed against three fixtures (unparseable / placeholder / empty `full` tier), measured
2026-09-03 on a scratch checkout of each revision:

| revision | `verify full` | `verify done` |
|---|---|---|
| `a15ab32^` (pre-fix) | 0, 0, 0 | 0 |
| `a15ab32` (the fix) | **0, 0, 0** | 1 |
| `eefb635` (the hoist) | 1, 1, 1 | 1 |
| `HEAD` | 1, 1, 1 | 1 |

The middle row is the finding: a commit whose subject is *"fail closed — the verifier was
fabricating green receipts"* left the `full` entrypoint fabricating them for fourteen more
commits, because the suite exercised one entrypoint and the fix touched two. **A fix commit is
not evidence that the class is closed. Re-run the fixture through every entrypoint the change
claims to cover.**

`benchmark/structure/validate.py` states the general form in its own header: *a validator that
returns "ok" unconditionally passes the clean tree too.*

**How to check.** Run each self-test the diff touches, then break the invariant in a scratch copy
and confirm the check goes red:

```bash
python3 hooks/inert-mask.py --self-test                              # exit 0, 12 checks
python3 benchmark/structure/validate.py --self-test                  # exit 0, 4 checks
python3 benchmark/verification/mcp/collision-detect.py --self-test   # exit 0, 6 checks
python3 benchmark/gates/pin-check.py --self-test                     # exit 0, 9 checks
bash selftest.sh                                                     # exit 0, 31 checks
```

Note the ordering `.github/workflows/verify.yml` enforces: **controls before checks.** A diff that
reorders them, or adds a check whose control runs afterwards, is a P1 finding on its own.

**File a finding when:** a check is added or edited with no `--self-test` and no demonstrated
failing input; a check's only evidence is that it passes the clean tree; a control is moved to run
after the check it guards.

**Not a finding:** a check without a self-test that the diff did not touch (out of scope, §5).

### P2 — Does the control actually discriminate?

**Question:** does the control hold everything constant *except* the property under test, and
would it fail if the property were absent?

**What happened here.** `7c5ad4e` — *"I1 defeated a shape-matched control — third vacuous attempt,
recorded."* Three consecutive attempts produced a control that matched the shape of the test
without testing the thing.

The second form is expectation contamination. `benchmark/gates/bench.sh` carries the fix in a
comment: an earlier version **hardcoded each gate's negative count** for the false-positive
budget, so the budget was computed from the corpus it was policing and would have gone quietly
stale the first time anyone added a case.

**How to check.**

- Name the single variable that differs between the arms. If you cannot, it is not a control.
- Ask what the control would print if the property under test were removed. If the answer is "the
  same thing", file it.
- Trace every expected value back to where it is **declared**. An expectation read off the rule
  set under test disappears when a rule is deleted, and the check stays green.

**File a finding when:** both arms of a control pass; an arm differs in more than one variable; an
expected set, count or threshold is computed from the artifact being checked.

### P3 — Does it fail closed?

**Question:** unreadable config, crashed helper, missing file, empty output, timeout — is each of
those non-zero?

**What happened here.** Same commit as P1, stated in `selftest.sh`: *a gate set that cannot be
read is NOT a passing gate set.* The whole fail-closed block of that suite exists because every
one of those cases silently certified before it was written.

**How to check.** For each error path the diff adds or edits, feed it the broken input and read
`$?` — do not read the log line, read the exit code:

```bash
printf '{"full":[{"name":"probe","cmd":"exit 1"},]}' > /tmp/bad-gates.json   # trailing comma
python3 -m json.tool /tmp/bad-gates.json; echo "exit=$?"                     # exit 1 — unparseable
```

Also read for: `|| true` added to a failing command; `2>/dev/null` newly swallowing a diagnostic;
`set -uo pipefail` dropped; an exit code lost across a pipe; a `return 0` on a path that could not
compute an answer.

**File a finding when:** any error path can reach a zero exit, or an "ok" line, without having
performed the check.

### P4 — Is every number bound to the run that produced it?

**Question:** what corpus, what environment, what commit, and who wrote the labels?

**What happened here — four distinct ways.**

1. **The number was true of a file nobody installed.** `benchmark/manifest/gate-manifest.json`,
   gate A3, records it verbatim: recall was measured against `hooks/scan-diff-cheats.sh` while
   `kit/hooks/` still shipped the pre-fix detector with the total `@Ignore` blind spot.
2. **The corpus was self-authored.** `e3211cb` — *"measured recall against a corpus I did not
   author — it was 0%."* The detector scored 0/112 the first time it met third-party labels.
3. **A withdrawn claim survived elsewhere in the tree.** `docs/04 §2.2` withdraws the `0.95^N`
   compliance-decay figure as *"an illustration presented as a measurement."* Six other files
   still assert it as fact:
   ```bash
   grep -rn '0\.95\^' --include='*.md' .    # docs/04 withdraws it; 6 other files still state it
   ```
4. **A ratchet absorbing a regression.** `gate-manifest.json` carries `unbacked_baseline.count = 7`
   and `dead_link_baseline.count = 8`, deliberately ratcheted so existing breakage stays printed.
   A diff that **raises** either number converts a ratchet into an allowlist.

**How to check.**

```bash
bash benchmark/manifest/check-drift.sh                     # which results the live env invalidates
python3 benchmark/structure/validate.py                    # manifest rows <-> scripts, both directions
git diff "$BASE...HEAD" -- benchmark/manifest/gate-manifest.json \
  | grep -E '^\+ *"(status|verified_on)"'                  # a status changed — was it re-run?
for f in hooks/*; do b=$(basename "$f"); [ -e "kit/hooks/$b" ] && diff -q "$f" "kit/hooks/$b"; done
```

The last one prints nothing today and must keep printing nothing: `hooks/` and `kit/hooks/` are
byte-identical, and A3's caveat is what divergence costs.

**File a finding when:** a manifest status changes without `verified_on` moving or a re-runnable
`script`; a VERIFIED row names no artifact anything can re-run; a `judgment`-subsystem row is
cited without the model it was measured on; an accuracy number is reported on cases authored in
the same PR without saying so; a threshold, regex or corpus is edited in the same diff that
reports an improved score, with no stated defect; a printed measurement, corpus case, or reported
column is removed while everything stays green.

`benchmark/gates/bench.sh` reports and does not gate, by design — *"suppressing a measurement to
keep a number green is the failure mode this whole project is about."* Deleting a case is
therefore invisible to CI and visible only to this pass.

### P5 — Security, injection, and the enforcement surface

**Question:** can something outside the trust boundary steer this, and does the diff widen what
the agent can reach?

**What is live in this repo.** `gate-manifest.json` currently records **FAILS** on
`B1 non-escalating child perms`, `G2 least-privilege scope` (OVERBROAD on 6 of 9),
`K1 MCP identity verification`, `K2 dependency pinning`, and `M1 pre-action, spend class`. Those
are known-open holes; a diff that leans on any of them as if closed is a finding.

**The runner-resolution hole, and its stale receipt.** `hooks/stop-gate.sh` used to resolve its
runner as `${CLAUDE_PLUGIN_ROOT}/bin/verify` with a fallback to a **repo-committed**
`$ROOT/bin/verify`, so a 17-byte stub checked into a target repo became the gate runner and
certified a red gate green. It now resolves from `BASH_SOURCE`, has no repo fallback, and exits 2
when it finds no runner. The fix landed — and `selftest.sh` still carries the comment saying it did
not (*"KNOWN FAILING … Left red until the hook is fixed"*), directly above two checks that pass
today:

```bash
bash selftest.sh | grep -E "green gate|stubbed"   # both ok — the comment above them is stale
```

That stale comment is a P4 finding in its own right, and it is why any diff touching runner
resolution is Important either way: this is the single path where repo content can replace the
verifier.

**How to check.**

- Untrusted input: PR titles, comment bodies, issue text, MCP tool output, file contents — data,
  never instructions ([docs/12 §7](docs/12-pr-lifecycle.md)). A diff that pipes any of those into a
  prompt, a shell string, or a decision is a finding.
- Deny-list edits: a false-positive fix that also opens a bypass. `7af82b1`'s subject is literally
  *"quoted-literal false positives, **without the bypass**"* — stripping quotes before matching
  would have blinded the SQL rules and let `bash -c 'rm -rf /'` through. Re-run the corpus:
  ```bash
  bash benchmark/gates/bench.sh            # per-gate confusion matrix + FP budget, exit 0
  ```
- Privilege: `permissions:` widened in a workflow, a new secret, a new network egress, a new
  `allowedTools` entry, an edit to `.claude/settings.json`, `hooks/`, or `gates.json`.
- Dependencies: `python3 benchmark/gates/pin-check.py` over the PR diff. K2 is FAILS; unpinned
  installs are the live risk here, not a hypothetical.

**File a finding when:** untrusted content reaches an instruction position; an enforcement path
becomes bypassable or its bypass widens; a privilege grows without a stated reason; a deny rule is
relaxed without a corpus re-run.

### P6 — Bugs and logic

Ordinary defects, weighted toward what this codebase is made of: bash and small Python.

| Look for | Because |
|---|---|
| `set -uo pipefail` absent; unset var under `set -u` | The exact mechanism of the `a15ab32` fail-open |
| Bash 3.2 assumptions (macOS default): no associative arrays | `bench.sh` documents working around exactly this |
| `$?` read after the wrong command, or a status lost across a pipe | `PIPESTATUS` is bash-only; the surrounding shell may be zsh |
| Committed history vs working tree | `scan-diff-cheats` reads **commits**; the same cheat left uncommitted scores clean, and the gate runs before a done claim when work is usually still in the tree (recorded in `benchmark/README-gates.md`) |
| Background processes not reaped | `benchmark/verification/ORPHAN-INCIDENT.md`: the hang reaper orphaned what it killed — 5 processes at 99% CPU for 3.5 days |
| Bare `except:`, or a `try` that swallows and continues | Turns P3 into a silent pass |
| `mktemp -d` without cleanup; unquoted expansions | Ordinary, still real |

**Severity is by consequence**, not by category: Important if it can produce a wrong verdict, lose
data, hang, or leak; Nit otherwise.

### P7 — Compliance with spec.md and plan.md

- Every acceptance criterion in the spec maps to something in the diff, or to an explicit, written
  deferral. An unmet criterion is Important even when the gates are green.
- Nothing outside the plan's stated scope. In a multi-agent run, **file ownership is the
  invariant**: a diff touching a file another agent owns corrupts their work, and it is Important
  regardless of the change's quality.
- Decisions the spec never asked for. `bin/ambiguity` exists for this class; a design decision
  invented during implementation is a finding **even when it is a good decision**, because the spec
  is what the human agreed to.
- Withdrawn or changed numbers must move everywhere they are asserted (see P4 item 3).

**Not a finding:** the plan being a worse plan than the one you would have written.

---

## 3. Important vs Nit

**Important** — if this ships, then at least one of:

1. a check reports a result it cannot support (P1, P2, P4);
2. an enforcement path can be bypassed or fails open (P3, P5);
3. a stated acceptance criterion is unmet, or an unowned file was written (P7);
4. a defect can produce a wrong verdict, lose data, hang, or leak (P6).

**Nit** — would improve the change; nothing downstream depends on it. Naming, comment placement,
redundancy, doc phrasing, formatting the linter does not own.

Three questions settle it:

| Question | If no |
|---|---|
| Can I state a concrete failing input, or a specific downstream consequence? | Nit at most — usually excluded (§5) |
| Would leaving this in make some *other* check's result untrue? | Not Important on that basis |
| Am I proposing a different approach without a demonstrated defect in this one? | Not a finding at all |

**Severity floors.** These classes may never be filed as a nit — downgrading one to duck a
threshold is itself the defect this repo exists to prevent. The validator in §8 enforces it.

| class | pass | floor |
|---|---|---|
| `check-cannot-fail` | P1 | important |
| `control-does-not-discriminate` | P2 | important |
| `expectation-derived-from-subject` | P2 | important |
| `fails-open` | P3 | important |
| `receipt-not-bound-to-run` | P4 | important |
| `corpus-provenance-undisclosed` | P4 | important |
| `detector-tuned-to-number` | P4 | important |
| `baseline-absorbs-regression` | P4 | important |
| `installed-copy-diverges` | P4 | important |
| `measurement-suppressed` | P4 | important |
| `untrusted-input-trusted` | P5 | important |
| `enforcement-bypassable` | P5 | important |
| `spec-noncompliance` | P7 | important |
| `logic-defect` | P6 | by consequence |
| `plan-noncompliance` | P7 | by consequence |
| `nit` | any | nit |

**Uncertainty.** Default to "not proven" — and file it. "Not proven" is a finding with
`confidence: "argued"`, never a silent pass. `confidence: "demonstrated"` requires an evidence
command with its exit code; an Important finding you cannot demonstrate is still filed, as
`argued`, carrying the counterexample you predict.

## 4. Nit cap

- **At most 5 nits per review.** The reviewer picks the five most valuable.
- Suppressed nits are **counted, never listed**: `counts.nits_suppressed`. "2 nits" and "2 nits out
  of 40" are different statements about a diff, and the second one is the useful one.
- **No cap on Important.** A review with 12 important findings publishes 12.
- The cap is a ceiling, not a quota. A review reporting five nits, zero important findings, and a
  thin `checked` list is a failed review — §6 is how that gets caught.
- The cap is a judgment number with no measurement behind it. Stated as such in §9.

## 5. Exclusions — do not file

- **Anything the machine already decided**: lint, format, type errors, failing tests, gate output.
  Restating a red gate as a finding is noise dressed as diligence.
- Style preferences the linter does not enforce.
- Alternative approaches with no demonstrated defect in the current one.
- "Add more tests" where a gate already measures it (`bin/test-delta`, diff coverage —
  [docs/04](docs/04-gate-ladder.md) gates 4a and 5).
- Pre-existing conditions the diff does not touch — **except** where the diff makes them wrong, or
  raises a ratcheted baseline. Those are in scope (P4).
- Generated files, vendored code, lockfile churn from a pinned bump.
- Limitations already recorded in `benchmark/README-gates.md` §2: the two quoted-literal false
  positives, and the in-place weakened assertion (`== 42` to `is not None`) that leaves the net
  assertion count unchanged. Re-reporting a documented limitation is not a finding. A diff that
  **widens** one is.
- Speculation about intent. Review what the diff does.

## 6. Calibrating the review itself

The house rule applies to this stage too: a reviewer that finds nothing passes a clean PR exactly
like a working reviewer does. So Stage 5a carries a positive control — and it is built from defects
that **actually happened here**, not cases written for the exercise.

Hand the reviewer the inverse of a real fix commit, with the normal instructions and no hint. The
defect it re-introduces is the answer.

```bash
git diff a15ab32 a15ab32^ -- bin/verify                   # P3 — verifier exits 0 on unreadable config
git diff e3211cb e3211cb^ -- hooks/scan-diff-cheats.sh    # P4 — the detector that scored 0/112
git diff 7af82b1 7af82b1^ -- kit/hooks/deny-dangerous.sh  # P5 — pre-fix quoted-literal matching
git diff 0be20ea 0be20ea^ -- bin/ledger                   # P6 — reaper that orphans what it kills
```

Rules for the control:

- Run it when the reviewer **model** or the reviewer **prompt** changes. Record the result next to
  the change.
- **Record misses; do not tune them away.** Editing the review prompt until it catches these four
  and calling that an improvement is fitting the reviewer to four known answers.
- Four cases is a **smoke test, not a measurement**. It shows the reviewer can detect defect shapes
  this repo has already published and fixed. It says nothing about generalisation, and the cases
  come from this repo's own history — the same self-authored-corpus caveat P4 files against
  everyone else applies here.

## 7. Where the tally goes

`.claude/evidence/review-<head_sha>.json`, beside the evidence bundle.

That path is **gitignored** (`.gitignore` line `.claude/evidence/`), so it does not survive the
checkout. To make it durable, publish it as a PR comment or a CI artifact. A tally that only ever
existed in one process is not a receipt.

## 8. The tally — machine-readable findings

Schema 1. The shape is fixed so a human can set a threshold on it without reading prose.

**What the shape encodes, and why:**

| Rule | Reason |
|---|---|
| No approval field, anywhere | §0. A key named `approve`/`verdict`/`block`/`merge`/`lgtm`/`decision` at any depth invalidates the document |
| `review.gate_state` required | A review run on red gates must be visible, not inferable |
| Every declared pass produces a finding **or** a `checked` entry | A silent pass is not a pass. A review that finds nothing must show what it looked at |
| `counts` must match `findings` | Catches a truncated array and a hand-edited total |
| `counts.by_pass` holds exactly one key per declared pass | Omission is the cheap way to hide a pass that was skipped |
| Nit cap enforced; `nits_suppressed` required | §4 — suppression is counted, not hidden |
| Floor classes may not be filed as nits | §3 — no downgrading past a threshold |
| Important requires a counterexample; `demonstrated` requires a command + exit code | A specific counterexample beats a general concern |
| `limits` non-empty | Model family, what was not run, what the review could not see |
| Unreadable or unparseable → exit 2 | Fail closed. A tally nothing can parse is not a clean review |

### Example (valid — this is the exact document the validator below accepts)

```json
{
  "schema": 1,
  "review": {
    "pr": 7,
    "base_sha": "00ff96b",
    "head_sha": "7af82b1",
    "reviewer_model": "claude-opus-4-6",
    "implementer_model": "claude-sonnet-4-6",
    "independent_family": false,
    "passes": ["P1", "P2", "P3", "P4", "P5", "P6", "P7"],
    "gate_state": { "command": "./bin/verify done", "exit_code": 0 },
    "generated": "2026-09-03T18:20:00Z"
  },
  "counts": {
    "important": 1,
    "nit": 1,
    "nits_suppressed": 3,
    "by_pass": { "P1": 0, "P2": 0, "P3": 0, "P4": 1, "P5": 0, "P6": 1, "P7": 0 }
  },
  "findings": [
    {
      "id": "F1",
      "pass": "P4",
      "severity": "important",
      "class": "receipt-not-bound-to-run",
      "file": "skills/pressure-testing/SKILL.md",
      "line": 18,
      "claim": "A claim withdrawn in docs/04 §2.2 is still asserted as measurement in six other files.",
      "counterexample": "grep -rn '0.95\\^' returns docs/04 (withdrawn) alongside skills/pressure-testing/SKILL.md:18 stating it as fact.",
      "evidence": {
        "kind": "command",
        "command": "grep -rn '0\\.95\\^' --include='*.md' .",
        "exit_code": 0,
        "excerpt": "skills/pressure-testing/SKILL.md:18: Compliance decays roughly as `0.95^N`"
      },
      "confidence": "demonstrated",
      "action": "Withdraw the number where it is still asserted, or cite the withdrawal next to it."
    },
    {
      "id": "F2",
      "pass": "P6",
      "severity": "nit",
      "class": "nit",
      "file": "benchmark/gates/bench.sh",
      "line": null,
      "claim": "The bash 3.2 rationale for the string accumulator sits mid-file, not in the header.",
      "evidence": { "kind": "diff", "command": null, "exit_code": null, "excerpt": "OUTCOMES=\"$OUTCOMES\\n$gate:TP\"" },
      "confidence": "argued",
      "action": "Optional: move the rationale into the file header."
    }
  ],
  "checked": [
    { "pass": "P1", "what": "every check the diff adds", "how": "ran each --self-test, then deleted the rule it enforces and re-ran", "result": "each went red with the rule removed" },
    { "pass": "P2", "what": "controls added by the diff", "how": "held all inputs constant except the property under test", "result": "controls discriminate" },
    { "pass": "P3", "what": "error paths in hooks/inert-mask.py", "how": "fed it unreadable input and a forced crash", "result": "non-zero, no ok line" },
    { "pass": "P5", "what": "the deny-dangerous quoting change", "how": "re-ran bash benchmark/gates/bench.sh", "result": "no new false negative on destructive commands" },
    { "pass": "P7", "what": "changed paths against the plan", "how": "compared to the plan's file-ownership list", "result": "in scope" }
  ],
  "limits": [
    "Reviewer shares a model family with the implementer; shared blind spots are uncontrolled.",
    "P6 read the shell only; no mutation run against the changed lines."
  ]
}
```

### Field semantics

| Field | Meaning |
|---|---|
| `review.independent_family` | `false` when reviewer and implementer share a model lineage. Not a blocker; a stated limit |
| `review.gate_state` | The exact command and exit code the review ran against |
| `findings[].pass` | `P1`–`P7` |
| `findings[].class` | One of the closed set in §3. A defect with no class means the class list is incomplete — say so in `limits` rather than forcing a fit |
| `findings[].evidence.kind` | `command` (with `command` + `exit_code`), `diff`, or `citation`. Every kind needs an `excerpt` |
| `findings[].confidence` | `demonstrated` = a command reproduces it. `argued` = reasoning, with a predicted counterexample |
| `checked[]` | What was examined and found clear, per pass. This is what makes an empty `findings` array meaningful |
| `counts.nits_suppressed` | Nits found and dropped under the §4 cap |
| `limits` | What this review could not see or did not run |

### Validator

Fail-closed, no dependencies, runs from the repo root:

```bash
python3 - .claude/evidence/review-<head_sha>.json <<'PY'
import json, sys, re
P = {"P1","P2","P3","P4","P5","P6","P7"}
FLOOR = {  # classes that may never be filed as a nit — declared here, not read off the finding
 "check-cannot-fail","control-does-not-discriminate","expectation-derived-from-subject",
 "fails-open","receipt-not-bound-to-run","corpus-provenance-undisclosed",
 "detector-tuned-to-number","baseline-absorbs-regression","installed-copy-diverges",
 "measurement-suppressed","untrusted-input-trusted","enforcement-bypassable",
 "spec-noncompliance",
}
CLASSES = {  # spelled out, not FLOOR|{...}: deleting a floor entry must not delete the class
 "check-cannot-fail","control-does-not-discriminate","expectation-derived-from-subject",
 "fails-open","receipt-not-bound-to-run","corpus-provenance-undisclosed",
 "detector-tuned-to-number","baseline-absorbs-regression","installed-copy-diverges",
 "measurement-suppressed","untrusted-input-trusted","enforcement-bypassable",
 "logic-defect","spec-noncompliance","plan-noncompliance","nit",
}
FORBIDDEN = {"approve","approved","approval","verdict","block","blocked","blocking",
             "merge","mergeable","lgtm","sign_off","signoff","decision","recommendation_to_merge"}
NIT_CAP = 5
errs = []
def bad(m): errs.append(m)

try:
    raw = open(sys.argv[1], encoding="utf-8").read()
except Exception as e:
    print(f"UNREADABLE: {e}"); sys.exit(2)
try:
    d = json.loads(raw)
except Exception as e:
    print(f"NOT JSON: {e}"); sys.exit(2)

def walk(o, path="$"):
    if isinstance(o, dict):
        for k, v in o.items():
            if k.lower() in FORBIDDEN:
                bad(f"{path}.{k}: forbidden key — a tally states findings, never a merge decision")
            walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o): walk(v, f"{path}[{i}]")
walk(d)

if d.get("schema") != 1: bad("schema must be 1")
r = d.get("review")
if not isinstance(r, dict): bad("review: missing")
else:
    for k in ("base_sha","head_sha","reviewer_model","implementer_model","generated"):
        if not isinstance(r.get(k), str) or not r[k]: bad(f"review.{k}: missing")
    for k in ("base_sha","head_sha"):
        if isinstance(r.get(k), str) and not re.fullmatch(r"[0-9a-f]{7,40}", r[k]):
            bad(f"review.{k}: not a git sha")
    if not isinstance(r.get("independent_family"), bool): bad("review.independent_family: must be bool")
    ps = r.get("passes")
    if not isinstance(ps, list) or not ps or set(ps) - P: bad(f"review.passes: must be a non-empty subset of {sorted(P)}")
    g = r.get("gate_state")
    if not isinstance(g, dict) or not isinstance(g.get("command"), str) or not isinstance(g.get("exit_code"), int):
        bad("review.gate_state: needs {command, exit_code} — a review run on red gates must be visible")

fs = d.get("findings")
if not isinstance(fs, list): bad("findings: must be a list"); fs = []
ids = set()
for i, f in enumerate(fs):
    w = f"findings[{i}]"
    if not isinstance(f, dict): bad(f"{w}: not an object"); continue
    if not isinstance(f.get("id"), str) or f["id"] in ids: bad(f"{w}.id: missing or duplicate")
    else: ids.add(f["id"])
    if f.get("pass") not in P: bad(f"{w}.pass: not one of {sorted(P)}")
    if f.get("severity") not in ("important","nit"): bad(f"{w}.severity: important|nit")
    if f.get("class") not in CLASSES: bad(f"{w}.class: not in the closed class list")
    if f.get("class") in FLOOR and f.get("severity") != "important":
        bad(f"{w}: class '{f.get('class')}' floors at important and may not be filed as a nit")
    if not isinstance(f.get("file"), str) or not f["file"]: bad(f"{w}.file: missing")
    if not (f.get("line") is None or isinstance(f.get("line"), int)): bad(f"{w}.line: int or null")
    if not isinstance(f.get("claim"), str) or not f["claim"]: bad(f"{w}.claim: missing")
    if f.get("confidence") not in ("demonstrated","argued"): bad(f"{w}.confidence: demonstrated|argued")
    if not isinstance(f.get("action"), str) or not f["action"]: bad(f"{w}.action: missing")
    ev = f.get("evidence")
    if not isinstance(ev, dict) or ev.get("kind") not in ("command","diff","citation"):
        bad(f"{w}.evidence.kind: command|diff|citation")
    else:
        if ev["kind"] == "command":
            if not isinstance(ev.get("command"), str) or not isinstance(ev.get("exit_code"), int):
                bad(f"{w}.evidence: kind=command needs command + exit_code")
        if not isinstance(ev.get("excerpt"), str) or not ev["excerpt"]: bad(f"{w}.evidence.excerpt: missing")
    if f.get("severity") == "important":
        if f.get("confidence") == "demonstrated" and not (isinstance(ev, dict) and ev.get("kind") == "command"):
            bad(f"{w}: confidence=demonstrated requires evidence.kind=command")
        if not isinstance(f.get("counterexample"), str) or not f["counterexample"]:
            bad(f"{w}.counterexample: required for an important finding")

ck = d.get("checked")
if not isinstance(ck, list): bad("checked: must be a list"); ck = []
for i, c in enumerate(ck):
    w = f"checked[{i}]"
    if not isinstance(c, dict): bad(f"{w}: not an object"); continue
    if c.get("pass") not in P: bad(f"{w}.pass: not a pass id")
    for k in ("what","how","result"):
        if not isinstance(c.get(k), str) or not c[k]: bad(f"{w}.{k}: missing")

if isinstance(r, dict) and isinstance(r.get("passes"), list):
    covered = {f.get("pass") for f in fs if isinstance(f, dict)} | {c.get("pass") for c in ck if isinstance(c, dict)}
    for p in r["passes"]:
        if p not in covered:
            bad(f"pass {p}: ran but produced neither a finding nor a checked entry — a silent pass is not a pass")

if not isinstance(d.get("limits"), list) or not d["limits"]:
    bad("limits: at least one stated limit is required")

c = d.get("counts")
if not isinstance(c, dict): bad("counts: missing")
else:
    imp = sum(1 for f in fs if isinstance(f, dict) and f.get("severity") == "important")
    nit = sum(1 for f in fs if isinstance(f, dict) and f.get("severity") == "nit")
    if c.get("important") != imp: bad(f"counts.important={c.get('important')} but findings hold {imp}")
    if c.get("nit") != nit: bad(f"counts.nit={c.get('nit')} but findings hold {nit}")
    if not isinstance(c.get("nits_suppressed"), int) or c["nits_suppressed"] < 0:
        bad("counts.nits_suppressed: required int >= 0")
    bp = c.get("by_pass")
    declared = set(r.get("passes") or []) if isinstance(r, dict) else set()
    if not isinstance(bp, dict) or set(bp) != declared:
        bad("counts.by_pass: must hold exactly one key per declared pass")
    else:
        for p, n in bp.items():
            actual = sum(1 for f in fs if isinstance(f, dict) and f.get("pass") == p)
            if n != actual: bad(f"counts.by_pass.{p}={n} but findings hold {actual}")
    if nit > NIT_CAP: bad(f"nit cap: {nit} nits reported, cap is {NIT_CAP}")

if errs:
    print(f"INVALID ({len(errs)}):")
    for e in errs: print("  -", e)
    sys.exit(1)
print(f"valid: {c.get('important')} important, {c.get('nit')} nit "
      f"({c.get('nits_suppressed')} suppressed) over passes {','.join(r['passes'])}")
PY
```

Exit codes: **0** valid · **1** invalid, reasons printed · **2** unreadable or unparseable.

### The validator's own positive controls

A validator that accepts the example proves nothing — one that returned "valid" unconditionally
would accept it too. Take the §8 example, apply one mutation, expect the stated result. All nine
were run against this validator on 2026-09-03; the message column is what it printed.

| mutation to the valid example | exit | message |
|---|---|---|
| add `"approved": true` at top level | 1 | `$.approved: forbidden key — a tally states findings, never a merge decision` |
| refile F1 as `severity: "nit"` (counts adjusted) | 1 | `findings[0]: class 'receipt-not-bound-to-run' floors at important and may not be filed as a nit` |
| duplicate the nit to six, update `counts.nit` | 1 | `nit cap: 6 nits reported, cap is 5` |
| drop the `checked` entry for P2 | 1 | `pass P2: ran but produced neither a finding nor a checked entry — a silent pass is not a pass` |
| set `counts.important` to 3 | 1 | `counts.important=3 but findings hold 1` |
| delete `findings[0].counterexample` | 1 | `findings[0].counterexample: required for an important finding` |
| delete `counts.by_pass.P3` | 1 | `counts.by_pass: must hold exactly one key per declared pass` |
| trailing comma in the JSON | 2 | `NOT JSON: Illegal trailing comma …` |
| file absent | 2 | `UNREADABLE: [Errno 2] No such file or directory` |

Re-run these whenever the validator changes. A mutation that stops failing is a validator that has
stopped discriminating.

## 9. Limits of this policy

1. **The human-approval clause is not currently a mechanism in this repo.** No `CODEOWNERS`, no
   branch protection recorded here. §0 describes where authority belongs, not what is configured.
2. **The nit cap of 5 is a judgment number.** It bounds noise. Nothing measures it, and no claim is
   made that it is optimal.
3. **The passes were derived from this repo's own 50 commits of history.** They describe failures
   already made here, and will systematically miss classes this repo has not yet had — the same
   self-authored-corpus problem P4 files against everyone else.
4. **The validator checks shape, not truth.** A well-formed tally full of wrong findings passes it.
   Shape validation is what a machine can do; the findings still need a reader.
5. **Reviewer independence is usually unavailable.** Reviewer and implementer normally share a model
   family; `benchmark/README-gates.md` §3 measured a three-model panel at **1.09 effective votes of
   3**, mean pairwise phi 0.873. Treat a second opinion from the same lineage as close to one
   opinion counted twice.
6. **Stage 5a costs a model call per PR and is not deterministic.** Where a mechanical rule can
   decide a case, the mechanical rule wins: it is free, repeatable, and cannot be argued with.
