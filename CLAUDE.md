# CLAUDE.md — verified-autonomy

This repo is the enforcement layer, not a consumer of one. Everything here exists to stop a
*fabricated green*: a check that reports success without having measured anything. Read the
verification block before you change code, and run it before you say you are done.

## Verification — run ALL of it before reporting done

No build, no install, no lint step. Python is **stdlib only** (`argparse ast collections glob
json math os random re shutil subprocess sys tempfile`); the rest is `bash` + `git`. Every
command below was run on this tree at `00ff96b` and its exit code recorded.

| Command | Healthy output | Exit |
|---|---|---|
| `bash selftest.sh` | `SELF-TEST PASSED  (31 checks)` | 0 |
| `bash benchmark/gates/bench.sh` | `cases: 142` · `recall 100.0% [80/80]` · `specificity 100.0% [62/62]` · `false-positive rate 0.0%` | 0 |
| `python3 hooks/inert-mask.py --self-test` | `inert-mask (12 checks)` | 0 |
| `python3 benchmark/structure/validate.py --self-test` | `structural validators (4 checks)` | 0 |
| `python3 benchmark/structure/validate.py` | `links 8 finding(s)  (baseline, not a failure)` … `STRUCTURE OK` | 0† |
| `python3 benchmark/skills/trigger-eval.py --self-test` | `skill trigger eval controls (8 checks)` | 0 |
| `python3 benchmark/skills/trigger-eval.py` | `all four rankers discriminate in both directions`, then `FINDINGS — misroute under all 4 rankers (7/42 prompts)` | 0 |
| `python3 benchmark/verification/mcp/collision-detect.py --self-test` | `MCP collision detector (6 checks)` | 0 |
| `python3 benchmark/gates/pin-check.py --self-test` | `unpinned-dependency gate (9 checks)` | 0 |
| `bash benchmark/manifest/check-drift.sh` | `gates: 30` · `environment matches the manifest` | 0 |

† `validate.py`'s `links` check is a **ratchet**, so that row is exit 0 *on the committed tree
only*. Any markdown you add — including an untracked scratch file — that carries a dead link
prints `REGRESSION dead links grew 8 -> N` and exits 1. That is the gate working. Fix your
link; do not raise the baseline. To confirm the baseline itself is still 8, run it against a
pristine checkout rather than your working tree:

```
T="$(mktemp -d)" && git archive HEAD | tar -x -C "$T" \
  && (cd "$T" && python3 benchmark/structure/validate.py)
```

`selftest.sh` is the single entry point and CI's `selftest` job. **31 is the count of its own
rows, not of assertions.** Thirteen of those rows are sub-suites that print their own counts
and carry **280 further assertions** — run one directly when it fails:

```
bash bin/ledger selftest          (43)   bash bin/test-delta selftest       (15)
bash bin/escalate selftest        (25)   bash bin/holdout selftest          (16)
bash bin/worktree-guard selftest  (39)   bash bin/mutate-changed selftest   (11)
bash tests/orchestration-test.sh  (80)   bash bin/ambiguity selftest        (12)
```

CI (`.github/workflows/verify.yml`, jobs `structure` / `selftest` / `bench`) runs each
control **before** the check it belongs to, and pins `actions/*` to commit SHAs. Keep that
order. A validator that has silently stopped discriminating passes a clean tree exactly like a
working one, so controls-after-checks would report green on a dead suite.

Four gates get an explicit `— CONTROLS FIRST` step ahead of themselves (`inert-mask`,
`validate.py`, `collision-detect`, `pin-check`). `trigger-eval.py` has **no separate
`--self-test` step in CI** — its four ranker controls run inside the single invocation and
abort it before any result prints, so a green there means the controls held. If you ever make
that script print findings without first aborting on a non-discriminating ranker, CI loses the
control entirely and you must add the step.

**Two commands that do NOT exit 0 here, by design — do not "fix" them:**

- `bash hooks/scan-diff-cheats.sh` → **exit 1**, currently 4 flags on this branch. Only
  `guardrail-edit` is justifiable, only when it is the *only* flag, and only through a commit
  trailer `Guardrail-Change: <why this edit to gates/hooks/CI is correct>`. Every other flag
  names a defect to actually fix.
- `bash bin/verify done` → exit 0 printing `ALL GATES GREEN` **while the bundle it just wrote
  says** `"all_green": false, "error": "no gates executed"`. This repo has no
  `.claude/gates.json`; `bin/verify` gates *target* repos and is exercised here only through
  `selftest.sh`'s temp fixtures. Never use it as this repo's own verification, and never read
  its console line instead of `.claude/evidence/latest.json`.

## Architecture

Three layers; this repo is layer 2. Layer 1 (`CLAUDE.md`, skills) is persuasion the agent can
ignore. Layer 3 (CI, branch protection) is outside the trust boundary.

```
hooks/          the enforcement layer, loaded by hooks/hooks.json
                  stop-gate.sh      Stop/SubagentStop → exit 2 while gates are red
                  deny-dangerous.sh PreToolUse → force-push, destructive SQL, guardrail edits
                  inert-mask.py     allowlist of print sinks; masks quoted literals for the above
                  scan-diff-cheats.sh  the documented ways an agent fakes green
                  session-start.sh  injects the contract, only in opted-in repos
kit/            what kit/install.sh SHIPS. kit/hooks/ duplicates hooks/ — see mistake 5.
bin/            the portable spine. verify (gate runner, called by hook + Codex + CI),
                ledger / escalate / worktree-guard (durable orchestration state),
                test-delta / holdout / mutate-changed / ambiguity (coverage gates)
benchmark/      gates/ (labeled corpora + bench.sh), structure/ (validators),
                skills/ (trigger eval), verification/ (per-gate probe scripts),
                manifest/gate-manifest.json (the 30-row ledger), recall/ (third-party corpus)
skills/<name>/SKILL.md, agents/*.md   plugin layout
docs/01..16     evidence base, gate ladder, verification checklist
```

Enforcement lives in `bin/verify`, a plain CLI — **not** in a hook. Codex has no blocking
hook, so CI is its gate; all three callers must run the same command or "done" means different
things in different places.

## Conventions

- **Every verification script declares `# gate: <ID>` on line 2**, and every
  `gate-manifest.json` row names its script. `validate.py` checks *both directions*, so a row
  pointing at the wrong script fails even when every path resolves.
- **Declare expected sets independently**: `EXPECTED_RULES`, `EXPECTED_VALIDATORS`,
  `EXPECTED_RANKERS`. Adding a rule/validator/ranker without adding it to the EXPECTED set
  fails the suite closed. That is intended — see mistake 2.
- **Corpora are `EXPECT <TAB> …` text files** whose header states the correct answer was
  decided *before* running the gate, and states honestly how weak the evidence is when the
  author of the corpus also fixed the gate against it.
- **Ratchet, don't allowlist.** Existing unbacked manifest rows (7 of 30) and dead links (8)
  stay printed as a baseline; new ones cannot land.
- **Fail closed everywhere.** Unparseable input, a missing file, a crashed helper, an
  unparseable check count — none of these is a pass. `selftest.sh` fails a sub-suite that
  exits 0 without a parseable count.
- Commit messages state what was measured, what failed first, and what the number does *not*
  establish. Keep that.

## Common mistakes — every one of these actually happened here

1. **Fail closed, and check the exit code the caller needs.** `bin/verify` certified
   completion whenever `gates.json` could not be read: a trailing comma, an empty `full` tier,
   a mis-keyed tier, a zero-byte file and a merge marker each produced `exit=0
   all_green=true gates=0`. No adversary required, and CI ran the identical command, so layers
   2 and 3 failed together. In the same fix, a bare `${CLAUDE_PLUGIN_ROOT}` expansion under
   `set -u` exited 1 — and **exit 1 does not block a Stop hook; only exit 2 does.** (`a15ab32`)

2. **Never derive a check's expectation from the thing it checks.** Deleting a whole rule from
   `pin-check.py` left `selftest.sh` green, because the control asserted the fixture-hit count
   matched `len(RULES)`: removing the rule removed its expectation too. The same flaw was in
   two more places — deleting the frontmatter validator reported "2 checks, exit 0", and
   deleting three of four rankers collapsed the ensemble to one while still printing green,
   though the ensemble's entire claim is that a finding survived four tokenizers. (`a25e83d`)

3. **A control must hold constant everything EXCEPT the property under test.** Shape-matching
   is not enough when the subject can perceive the difference. The runaway control proved the
   agent sustains a retry loop *when success is reachable*, then tested it with success
   *unreachable* — the very variable driving the agent's decision to stop. It scored "ok"
   three times over three vacuous designs. Separately, a routing control failed because it was
   built from a fixture prompt that is itself a genuine routing defect, so a **real finding
   masqueraded as a broken instrument**. (`7c5ad4e`, `6f58575`)

4. **Cover every rule, not most of them.** `gha-tag-not-sha` anchored on `uses:` and missed the
   standard YAML list form `- uses:` — nearly every real workflow line. The control had
   exercised six of eight rules and reported the gate green; the broken rule was one of the two
   it never touched. A control that covers most of a gate certifies the whole gate. (`8935a3e`)

5. **Edit both copies: `hooks/` and `kit/hooks/`.** The recall fix to `scan-diff-cheats.sh`
   landed in `hooks/` and never reached `kit/hooks/`. `hooks/` is what the benchmark measures;
   `kit/` is what people install, so the benchmark reported a fixed detector while the shipped
   one still had the blind spot. `validate.py`'s `duplicates` validator now fails on
   divergence — run it after touching either tree. **Read the number carefully before you
   repeat it**, because this repo's own summary of it was wrong: `benchmark/recall/README.md`
   measures 0/112 → 112/112 on Kim et al. (ESEC/FSE 2021), but that 112/112 is a **training
   score** (the vocabulary was changed after seeing the labels), it **cost specificity, 100% →
   96%** (12 new false positives), and it is **not** evidence about `@Ignore` — 111 of the 112
   positives are TestNG `@Test(enabled=false)` and **zero** are `@Ignore`, so `@Ignore`
   coverage is still unmeasured. Fixing it was right; no number here supports it. Quoting
   "0/112 → 112/112" as a clean before/after breaks mistake 9 in the act of stating mistake 5.
   (`7af82b1`, `00ff96b`)

6. **Write a regex that can actually fire, then prove it fires.** Two of four `pin-check`
   defects were patterns with no possible match: `\b-e\b` has no word boundary after a space,
   and a lookahead demanded a character `install\s+` had already consumed. `bin/test-delta` hit
   the platform version: **BSD awk rejects `\b`** ("illegal primary in regular expression"),
   which emptied the counts and silently compared garbage — permanently wrong on macOS, which
   is the platform this repo is developed on. Spell it `[^A-Za-z0-9_]`. A rule that never fires
   is indistinguishable from a clean tree. (`a25e83d`, `5237883`)

7. **Read the rows; a green summary is not evidence.** An egress gate printed "4 passed, 0
   failed" containing the row `ok  H2b: allowlist includes target -> reachable  (blocked)` — a
   pass row contradicting its own label. The verdict was echoed and captured with `$( )`, so
   the result function received seven arguments instead of three and the surplus shifted the
   expected value into `$3`. Send verdicts to a file; never share stdout with anything inside
   `$( )`. The same shape is live today in `bin/verify done` (see the verification block).
   (`0d8d1bb`)

8. **Committed work is not the working tree.** `test-delta`'s `resolve_base` accepted a local
   branch name, so work committed on `main` resolved `base == HEAD`, produced an empty diff and
   exited 0 — deleting 42 of 43 tests and committing also returned 0. All nine self-tests had
   used a dirty tree, so none reached that path. `scan-diff-cheats.sh` shipped the mirror image:
   scoped to committed history, the identical cheat scored clean if the agent simply had not
   committed yet. Test both states. (`5237883`)

9. **Prefer data you did not author, and say so when you cannot.** The shipped cheat detector
   scored well on this repo's own corpus and **0/112** against third-party labels. `corpus-pin`
   reads 16/16 and its own header calls that weak evidence, because the same person wrote the
   corpus and then fixed the gate against it; the number that carries weight is the
   false-positive rate over real commits nobody authored for the purpose — `pin-check.py
   --self-test` CONTROL 3, budget 10%. **Do not copy that rate into prose.** It is computed
   over a trailing window of this repo's history, so it moves as history grows:
   `gate-manifest.json` still records `4.3% on 47` while the gate today reports `3/50 = 6.0%`,
   and this file previously quoted the manifest's stale pair. Cite the control, not the digits.
   Recall alone is gameable — a rule that fires on everything scores 100%.
   (`e3211cb`, `a25e83d`, `8935a3e`)

10. **Do not tune the number.** `bench.sh` reports; it does not gate. A false positive found
    there is a defect to fix, not a figure to suppress. `trigger-eval.py` refuses to print a
    single rank@1 percentage at all, because perturbing only the tokenizer moved it 14.3 points
    without touching a single skill description — a figure that swings that far on an internal
    choice is a property of the instrument. (`6f58575`)

11. **A VERIFIED row nothing can re-run is a claim, not a measurement.** `check-drift.sh` also
    names three VERIFIED rows (F1/F2 instruction boundary, G1 credential non-exfiltration, H1
    retrieval vs derivation) that hold **because the model declined, not because a mechanism
    refused**. Re-run them on any model change; do not treat them as mechanical. (`b591755`)
