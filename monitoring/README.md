# monitoring/ — Stage 6a control bands

A deterministic detector that watches this repo's own numbers against a rolling baseline
and escalates by distance from it. `bands.yaml` at the repo root is the policy; everything
here is the machinery.

| distance from baseline | tier | what happens |
|---|---|---|
| >= 1 sigma | 1 | logged, nothing invoked |
| >= 2 sigma | 2 | Claude invoked READ-ONLY to diagnose; writes its diagnosis to an `intent.md` |
| >= 3 sigma | 3 | Claude may act, via a branch and pull request, or a pre-approved runbook |

**The invocation itself is not implemented here, by design.** `detect.py` emits the
invocation that *would* be made — tier, allowed tools, write allowlist, the rendered
prompt, and the `intent.md` path the diagnosis must be written to — as JSON under
`monitoring/invocations/`. Every emission carries `"executed": false`. Nothing here starts
an agent, edits code, or opens a PR.

## Run it

```
python3 monitoring/collect.py              # measure once, print the record, write nothing
python3 monitoring/collect.py --append     # measure once and append to the history file
python3 monitoring/detect.py               # assess the latest observation, emit invocations
python3 monitoring/detect.py --no-emit     # assess without writing anything
python3 monitoring/selftest.py             # the positive controls (164 checks)
```

`collect.py` takes about a minute: it runs `selftest.sh` (~44 s), `benchmark/gates/bench.sh`
(~16 s) and `benchmark/structure/validate.py`. Useful flags: `--require-baseline` makes an
unestablished baseline exit 3 instead of 0; `--strict-coverage` makes a measured-but-
unwatched metric an error; `--skip <source>` on `collect.py` marks that source's metrics
`skipped` rather than pretending they were measured.

Exit codes from `detect.py`: `0` in band or no verdict, `1` a tier-2-or-above breach,
`2` an error (unreadable config, unreadable history, a required metric that could not be
read), `3` no verdict under `--require-baseline`.

## What it watches

Every metric is something this repo already produces. Nothing is invented.

| metric | where the number comes from | worse when |
|---|---|---|
| `selftest.checks_total` | `SELF-TEST PASSED (N checks)` | lower |
| `selftest.checks_failed` | the `N of M` in the FAILED summary | higher |
| `selftest.subsuite_checks_total` | sum of the per-sub-suite `(N checks)` lines | lower |
| `bench.cases` | `tp+fp+tn+fn` from `bench.sh`'s JSON output | lower |
| `bench.recall` | `bench.sh` JSON | lower |
| `bench.specificity` | `bench.sh` JSON | lower |
| `bench.fpr` | `bench.sh` JSON | higher |
| `structure.links_findings` | `validate.py`'s `links` line, against its ratcheted baseline | higher |
| `structure.nonratcheted_findings` | `validate.py`'s frontmatter + manifest + duplicates lines | higher |
| `evals.pass_rate` | `evals/run.py`, when that harness exists | lower |

`selftest.subsuite_checks_total` is the most interesting of these. `selftest.sh` reports 31
top-level checks, but those delegate to sub-suites carrying 280 checks between them. A
sub-suite that quietly stops running its cases still prints `ok` at the top level; the sum
is what notices.

## What it refuses to do, and why that is the deliverable

**It will not compute a sigma it cannot justify.** Below `min_samples` (8) it prints
`no-verdict`, names `n`, emits nothing, and never prints the word "in band" for that
metric. The summary says *"the baseline is not established yet. This is not a pass."*
A band derived from one or two points either fires on noise or never fires at all, and the
output looks identical either way.

That is the state this ships in. One honest observation exists, taken by running the suite:

```
bands: bands.yaml   history: monitoring/history/observations.jsonl (1 observation(s))
latest: 2026-09-04T03:04:31Z  00ff96bffe89  DIRTY TREE
policy: window=20 min_samples=8 dedupe_by_tree=True clean_tree_only=False

  metric                            status                     value    n        z  tier
  ------------------------------------------------------------------------------------
  selftest.checks_total             no-verdict                    31    0        -   0
      n=0 effective sample(s) < min_samples=8; refusing to compute a sigma
  ...
  BANDS: NO VERDICT for 9/10 metric(s) — the baseline is not established yet. This is not a pass.
```

`n=0`, not `n=1`, because the current observation is never part of its own baseline. Eight
more collections and the first verdicts arrive.

**It will not treat a constant as having a variance.** Most of these metrics are constants
today (recall 1.0, checks_failed 0). A z-score against a zero standard deviation is a
division by zero, not a large number. So a changed constant is reported as
`zero-variance-change` and escalated to the tier `bands.yaml` names for it —
`zero_variance_default_tier: 2`, overridden to 3 for `selftest.checks_failed`, because a
self-test that has never failed and now fails is not a noise event.

**It will not act on an improvement.** A metric moving the good way is capped at tier 1.
Acting on good news is wrong; ignoring it is also wrong, because an improvement is just as
often the measurement breaking — a corpus row that stopped loading raises recall too.

**It will not average history it cannot trust.** A record marked `synthetic` is refused
unless `--allow-synthetic`, which only the controls pass. A corrupt line, a missing file,
a wrong schema, a timestamp that is not a real UTC instant, a timestamp at or before the
row above it, or a row claiming a clean tree whose `tree_digest` is not the one its commit
implies — each is an error exit, never an empty baseline.

**It will not call a broken measurement calm.** A required metric that is missing,
errored, unavailable or skipped exits 2. A metric that is measured but no longer declared
in `bands.yaml` is printed as `UNWATCHED`.

## Sample hygiene

Two adjustments stop the baseline from being quietly wrong:

- **`dedupe_by_tree`** collapses observations taken on an identical source tree (same
  commit, same working-tree digest) to the most recent. Running the suite ten times
  without changing anything is one sample, not ten; counting it as ten shrinks the
  estimated sigma and makes the detector hair-trigger. The output reports `n` after
  deduplication and `n_raw` before it.
- **`baseline_requires_clean_tree`** (default false) can exclude dirty-worktree
  observations. Left off because this repo is usually mid-change and a dirty measurement is
  still a real measurement — but every record carries `dirty`, and each verdict reports how
  many of its baseline points came from dirty trees, so the caveat is visible rather than
  assumed.

## The controls

`python3 monitoring/selftest.py` — 164 checks. Passing on today's tree proves nothing, so
each control holds everything constant and changes exactly one thing.

The two expectations that matter most are declared as literals in `monitoring/harness.py`
and never read back from `bands.yaml`: the tier table `((1.0,1,'log'),(2.0,2,'diagnose'),
(3.0,3,'act'))` and the ten metric ids. If they were derived from the config, deleting a
tier would delete its own expectation and the suite would stay green over a config that no
longer did anything.

The controls were themselves mutation-tested: 23 deliberate defects were introduced one at
a time into a throwaway copy of the repo, and every one turned the suite red.

| defect introduced | result |
|---|---|
| `tier_for` never fires | FAILED (16 of 150) |
| sigma tolerance widened from 1e-9 to 0.5 | FAILED (2 of 164) |
| schema accepts unknown top-level keys | FAILED (1 of 164) |
| `min_samples` refusal removed | FAILED (6 of 157) |
| synthetic history accepted silently | FAILED (1 of 164) |
| zero-variance guard removed (divides by zero) | FAILED (1 of 160) |
| improving-direction cap removed | FAILED (4 of 164) |
| tree dedupe removed | FAILED (1 of 164) |
| clean-tree filter removed | FAILED (1 of 164) |
| required-metric check removed | FAILED (2 of 164) |
| corrupt history line skipped instead of raising | FAILED (1 of 164) |
| append-only timestamp check removed | FAILED (2 of 164) |
| timestamp validity check removed | FAILED (1 of 164) |
| clean-tree digest check removed | FAILED (1 of 164) |
| validator-set check in `parse_structure` removed | FAILED (3 of 164) |
| a failed eval probe returns 0.0 instead of unavailable | FAILED (1 of 164) |
| selftest summary-line guard returns 0 instead of raising | FAILED (1 of 164) |
| bench null-rate guard replaced with 1.0 | FAILED (1 of 164) |
| YAML parser accepts duplicate keys | FAILED (1 of 164) |
| the 3-sigma tier deleted from `bands.yaml` | FAILED (3 of 153) |
| a watched metric deleted from `bands.yaml` | FAILED (2 of 164) |
| tier 2 given a write tool | FAILED (2 of 164) |
| a fabricated row pasted into the history file | FAILED (1 of 159) |
| *(no mutation — control)* | **PASSED (164)** |

Two of those rows are fixes rather than checks that already existed. The first mutation
battery ran 19 defects and one survived: a row pasted into `observations.jsonl` without a
`synthetic` flag was averaged in like any other. Two integrity checks were added in
response — timestamps must be real UTC instants strictly later than the row above, and a
row claiming a clean tree must carry the `tree_digest` its commit implies, which is a pure
function of the commit and so cannot be guessed. Detection went from 18/19 to 23/23. The
`SIGMA_EPS = 1e-9` tolerance is also a fix, for a real defect the controls found: a value
placed at exactly 2 sigma comes back from double-precision arithmetic as 2 - 1e-16 and
landed in the 1-sigma band.

## What this does not do

- **It is not wired into CI or `selftest.sh`.** Both are owned elsewhere. Wiring it in
  means adding `suite "control bands" python3 "$PLUGIN/monitoring/selftest.py"` to
  `selftest.sh` (the summary line already prints `(N checks)` in the format that helper
  greps for) and a `python3 monitoring/collect.py --append` step plus
  `python3 monitoring/detect.py` to `.github/workflows/verify.yml`. Until that happens the
  history grows only when someone runs `collect.py` by hand, and a control band nobody
  feeds is decoration.
- **It has no baseline.** n=1. Every number here is a measurement; no verdict in this repo
  has yet been produced by the band logic against real data. The band logic has only been
  exercised against synthetic histories in the controls, which measures the arithmetic, not
  the metrics' real behaviour over time.
- **The config is self-authored**, and so is most of the corpus the numbers come from. A
  threshold of 2 sigma, a window of 20 and a minimum of 8 samples are judgement calls, not
  results. They should be revisited once there is real history to look at — with the change
  recorded, not slipped in to make a number look better.
- **mean and standard deviation are not robust.** One large outlier inflates the sigma and
  can hide the next real move behind it. A median/MAD estimator would resist that; it is
  not implemented, and swapping it in would change every threshold's meaning.
- **These metrics are not normal.** They are bounded rates and small integer counts, so
  "3 sigma" is a distance, not a tail probability. Do not read a false-alarm rate into it.
- **The `evals` adapter is unconfirmed.** `evals/run.py` did not exist when this was
  written. The collector tries `--json <file>` and then the last JSON object on stdout, and
  records `unavailable` with a reason if neither works. Its controls pin the failure modes —
  absent harness, crashing harness, unparseable output all land on `unavailable`, never on
  a number — but the success path is pinned against fixtures, not against the real harness.
  `evals.pass_rate` is `required: false` for exactly that reason; flip it once the harness
  lands and one observation shows the metric `ok`.
- **The integrity checks catch sloppiness, not a determined forger.** Someone who writes a
  well-formed row with a valid later timestamp and a plausible dirty-tree digest gets it
  into the baseline. The remedy is not in this code: the history file is version-controlled
  and its diffs get read, and every row names a commit, so any value can be re-derived by
  checking that commit out and running `collect.py` again.

## Files

| file | what it is |
|---|---|
| `../bands.yaml` | the policy: window, tiers, tools, prompts, metrics |
| `yamlsub.py` | strict loader for the YAML subset `bands.yaml` uses; no PyYAML dependency, because CI installs none |
| `bandconf.py` | schema validation for that document |
| `collect.py` | runs the suite, parses it strictly, emits one observation |
| `detect.py` | window statistics, tier assignment, invocation emission |
| `harness.py` | shared scaffolding and the independently declared expectations |
| `selftest.py` / `selftest_sources.py` | the 164 controls |
| `history/observations.jsonl` | append-only history; version-controlled, real measurements only |
| `intents/` | where a tier-2 or tier-3 diagnosis is written |
| `invocations/` | emitted invocation specs; gitignored, regenerable from the history |
