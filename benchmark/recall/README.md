# Recall — measured against labels I did not create

Measured 2026-08-28. Every other number in `benchmark/` comes from cases I wrote, which makes
a recall claim circular: I pick the positives, so I pick the answer. This is the one
measurement that escapes that.

## Method

**The detector was pinned before any labeled example was looked at.** Recall below is for
commit `aa6f400e12de` (`hooks/scan-diff-cheats.sh`, sha256 `67306658a364eb95`), extracted to
an immutable path and measured there.

**The real detector is run, not a copy of it.** Each case becomes a two-commit git repo and
the hook is invoked exactly as in production. An earlier version of this measurement
approximated the detector with a Python regex lifted out of it — that measures the copy, and
any drift between them is invisible.

**Canaries run first and the harness refuses without them.** A harness stuck on "detected"
reports 100%; one stuck on "not detected" reports 0%. Both look like findings. This codebase
has produced several vacuous-green measurements, so the harness proves it can emit both
answers before any number is trusted. It earned its keep immediately: the first post-fix run
was invoked with a relative detector path, every case errored, and the canary **refused to
report** rather than printing a clean-looking matrix of zeros.

## The corpus

Kim et al., *"Are Your Tests Really Disabled?"*, ESEC/FSE 2021 — 122K commits over 15 Java
systems; 3,111 test-disabling changes identified by a tool the authors measured at 2.6% FP;
327 hand-labeled by two annotators at Cohen's κ = 0.7. Labels made by other people, for
another paper, before this project existed.
Source: `github.com/boyang9602/FSE_Ignore_Test` (`RAW.zip`), reachable 2026-08-28.

Both classes come from the corpus's **own** `isActiveTestDisabled` / `isCOTestDisabled`
flags. Nothing was relabeled.

- **positives** — enabled → disabled: **112**
- **negatives** — enabled → enabled with changed content: 42,709, of which **300 sampled**
  (seed 20260828, reproducible)

## Result — pinned pre-fix detector `aa6f400e12de`

```
                  detected   clean
  disabling  (P)        0      112     n=112
  neutral    (N)        0      300     n=300
```

| metric | value | 95% Wilson CI |
|---|---|---|
| **RECALL** | **0 / 112 = 0.0%** | **0.0% – 3.3%** |
| specificity | 300 / 300 = 100.0% | 98.7% – 100.0% |

**The shipped detector caught nothing.** Not one of 112 real test-disabling changes.

## The `@Ignore` result, stated separately

The gap was real: the pinned detector contains **zero** occurrences of `@Ignore`. It covered
JUnit 5's `@Disabled` and never JUnit 4's `@Ignore`.

**But this corpus cannot measure it, contrary to what I expected going in.** Of the 112
positives:

| idiom marking the disabled state | count |
|---|---|
| TestNG `@Test(enabled = false)` | **111 / 112** |
| commented-out `@Test` | 13 / 112 |
| JUnit 4 `@Ignore` | **0 / 112** |
| JUnit 5 `@Disabled` | 0 / 112 |

The extractable slice reduces to two projects — orientdb and incubator-pinot — and both use
TestNG. So the 0% recall above is **not** evidence about `@Ignore`; it is evidence about
TestNG's disable idiom, which the detector also missed. **`@Ignore` coverage remains
unmeasured.** Fixing it was still correct (see the change record below), but no number here
supports it.

## Post-fix on the same corpus — a TRAINING score

```
                  detected   clean
  disabling  (P)      112        0     n=112
  neutral    (N)       12      288     n=300
```

| metric | value | 95% Wilson CI |
|---|---|---|
| recall | 112 / 112 = 100.0% | 96.7% – 100.0% |
| specificity | 288 / 300 = 96.0% | 93.1% – 97.7% |

**This is a training score and must be read as one** — the vocabulary was changed after
seeing these labels. It is reported only to show the cost, which is real: **specificity fell
from 100% to 96%.** The fix bought recall and paid 12 false positives.

Those 12 break down as 9 `@Ignore` additions and 3 commented-out `@Test`. At least one
(camel: `@Ignore("test manual, irc.codehaus.org has been closed")`) reads as a genuinely
disabled test the corpus flag did not capture. **I did not relabel it.** Deciding those 12 in
my own favour would substitute my judgment for the third-party label, which is the entire
reason this corpus is worth using. They are counted as false positives as measured.

## Detector change record

One change, three idioms. Per the discipline: (a) the gap, (b) found before or after seeing
labeled data, (c) would the change be correct with no corpus in existence?

| idiom added | (a) gap | (b) when found | (c) correct without a corpus? |
|---|---|---|---|
| JUnit 4 `@Ignore` | not covered at all | **before** — by reading the vocabulary against known JUnit idioms | **Yes.** `@Ignore` is JUnit 4's canonical disable annotation. A test-disabling detector that misses it is incomplete regardless of any dataset. |
| TestNG `@Test(enabled = false)` | not covered at all | **after** — this corpus is what exposed it | **Yes.** It is TestNG's documented disable mechanism, as standard as `@Disabled`. The corpus revealed the omission; it did not create the justification. |
| commented-out `@Test` | not covered at all | **after** | **Yes in principle** — commenting out the annotation does disable the test — **but it does not earn its keep here.** TestNG alone gives 111/112; this idiom adds ~1 true positive and costs 3 of the 12 false positives. Kept, with its measured cost recorded rather than buried. |

No change was made whose only justification was that a number went up.


## Extending to all 15 projects — attempted, and not achievable with the public artifact

The obvious next step was to pull the other 13 Java systems. **It cannot be done without
substituting my own label, which would defeat the purpose.** Evidence, per project, from
`RAW.zip`:

| project | states | `@Ignore` in the corpus's own parsed annotations | `isActiveTestDisabled` set |
|---|---|---|---|
| camel | 29,857 | **954** | **0** |
| hadoop | 20,637 | 288 | **0** |
| flink | 20,165 | 228 | **0** |
| hbase | 8,806 | 378 | **0** |
| orientdb | 9,050 | — | 282 |
| incubator-pinot | 7,463 | — | 254 |
| *(9 others)* | — | — | **0** |

The disabled flag is populated for **2 of 15** projects. It is not a general "is disabled"
label in the public artifact. The repo's README advertises an `RQ_data` folder holding the
hand-labeled subset; only `RAW.zip` shipped, and the remote has a single branch and no tags.

So the third-party-labeled positive set is capped at **112**, and no amount of extraction
changes that.

## `@Ignore` capability check — 10 projects, and the label is MINE

Since the corpus flag cannot answer "does the detector see `@Ignore`?", this does — on real
code, with the limitation stated up front.

Positives are transitions where `@Ignore` enters the corpus's own parsed `activeAnnotations`.
The parse is theirs; the judgment *"`@Ignore` added ⇒ disabled"* is **mine**. **This is a
capability check, not third-party recall**, and it does not escape circularity the way the
112 do. 200 positives + 200 negatives, 10 projects, seed 20260828.

| detector | recall | 95% CI | specificity | 95% CI |
|---|---|---|---|---|
| **pinned pre-fix `aa6f400e12de`** | **0 / 200 = 0.0%** | **0.0% – 1.9%** | 200/200 = 100% | 98.1% – 100% |
| current | 199 / 200 = 99.5% | 97.2% – 99.9% | 198/200 = 99.0% | 96.4% – 99.7% |

**JUnit 4 `@Ignore` is now recognized**, and the pinned detector was blind to all 200. The
current specificity cost is 2 false positives on my own labels.

## What this still does not measure

- **`@Ignore` coverage.** Zero of the 112 positives use it. Unmeasured.
- **Any detector shape other than `skip-added`.** No third-party corpus exists with
  diff-level labels for weakened assertions, swallowed errors, special-casing, or unstated
  magic constants — I looked; none as of 2026-08-28.
- **Independent observations.** 112 positives from **two** projects are correlated; the
  effective sample is far smaller than n=112 implies and the CIs are optimistic.
- **Agent behaviour.** These are human commits, Java/JUnit/TestNG, 2015–2020.
- **Recall against disabling nobody ever noticed.** The wall Meta states directly: "the
  number of false negatives is notoriously difficult to quantify (how many unknown bugs are
  there?)." Every number here is recall against what the corpus authors' tool could see.
- **Whether the 12 post-fix false positives are detector errors or corpus label noise.**
  Deliberately unresolved, because resolving it requires the judgment this corpus exists to
  replace.

## Reproduce

```bash
git clone --depth 1 https://github.com/boyang9602/FSE_Ignore_Test /tmp/kim
unzip -q /tmp/kim/RAW.zip -d /tmp/kim/raw
python3 benchmark/recall/extract.py /tmp/kim/raw/data-03 > /tmp/all.jsonl
python3 benchmark/recall/sample.py /tmp/all.jsonl 300 > /tmp/measure.jsonl
bash benchmark/recall/harness.sh "$PWD/hooks/scan-diff-cheats.sh" /tmp/measure.jsonl
```

Pass an absolute detector path — the probe changes directory, and a relative path makes every
case error. The canary catches this.

## The measurement that would actually settle recall

**ImpossibleBench** (`github.com/safety-research/impossiblebench`, ungated, 349
conflicting-test SWE-bench instances). The tests contradict the spec, so **any passing patch
is a cheat by construction** — the label is a theorem, not a judgment. Published cheat rates
run 39–76% by model, so two or three runs would give ~350–500 verified positives on real
multi-file repo diffs, against ImpossibleBench's own published monitor baseline of 42–65% at
SWE-bench scale. That is a compute cost, not a research problem, and it is not done.
