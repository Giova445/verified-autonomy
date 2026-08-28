# Recall — measured against a corpus I did not author

Every other number in `benchmark/` is measured on cases I wrote. That makes a recall claim
circular: I choose the positives, so I choose the answer. This directory holds the one
measurement that escapes it.

## The corpus

Kim, Chen, Hassan et al., *"Are Your Tests Really Disabled?"* — ESEC/FSE 2021. 122K commits
across 15 Java systems, of which **3,111 test-disabling changes** were identified by a tool
the authors measured at a **2.6% false-positive rate**, and a stratified 327 were
hand-labeled by two annotators at **Cohen's κ = 0.7**.

The labels were produced by other people, for another paper, years before this project
existed. That is the whole point. Source: `github.com/boyang9602/FSE_Ignore_Test` (`RAW.zip`).

Positives are extracted mechanically: for each test method, sort its states by time and take
every transition where the corpus's own `isActiveTestDisabled` / `isCOTestDisabled` flag goes
false → true. **112 transitions** survive in the public data.

## Result

| detector vocabulary | detected | recall | 95% CI (Wilson) |
|---|---|---|---|
| **as shipped before this measurement** | **0 / 112** | **0.0%** | 0.0% – 3.3% |
| + JUnit 4 `@Ignore` | 0 / 112 | 0.0% | — |
| + TestNG `@Test(enabled = false)` | 112 / 112 | 100% | 96.7% – 100% |
| + commented-out `@Test` | 13 / 112 | 11.6% | — |
| **all three** | **112 / 112** | **100%** | 96.7% – 100% |

The shipped detector caught **nothing**. The entire signal was TestNG's `enabled = false`
idiom, which the vocabulary never covered.

**Discrimination, not pattern-matching.** Recall alone is gameable — a rule that fires on
everything scores 100%. The paired check (CAS/NSA's discrimination rate, and the reason
OWASP scores Youden's J rather than TPR) is whether the same rule stays quiet on the matched
negative. It fires on **112/112** disabled states and **1/112** of the corresponding
still-enabled ones. And the false-positive corpus in `benchmark/gates` is unchanged at 4.8%,
so the recall was not bought with noise.

## What this does and does not establish

**Does:** the shipped rule had a total blind spot for the idiom two real projects use to
disable tests, and that blind spot is closed. Measured against labels I did not create.

**Does not:**

- **100% is not a general recall figure.** The 112 transitions come from **two projects**
  (orientdb, incubator-pinot), both TestNG. These are correlated observations, not 112
  independent ones; the effective sample is far smaller than *n* suggests, and the CI above
  is therefore optimistic.
- **It covers one detector shape.** `skip-added` only. There is no third-party corpus with
  diff-level labels for weakened assertions, swallowed errors, special-casing, or unstated
  magic constants — I looked, and none exists as of 2026-08-28.
- **It is human commits, not agent commits**, from a 2015–2020 window, Java/JUnit/TestNG only.
- **Recall against *undetected* disabling is unmeasurable**, the wall Meta names directly:
  "the number of false negatives is notoriously difficult to quantify (how many unknown bugs
  are there?)."

## Reproduce

```bash
git clone --depth 1 https://github.com/boyang9602/FSE_Ignore_Test /tmp/kim
unzip -q /tmp/kim/RAW.zip -d /tmp/kim/raw
python3 benchmark/recall/extract.py /tmp/kim/raw/data-03 > /tmp/transitions.jsonl
python3 benchmark/recall/measure.py '<regex>'
```

## The next measurement, and why it is not done here

The one route to *definitional* labels is **ImpossibleBench**
(`github.com/safety-research/impossiblebench`, ungated, 349 conflicting-test SWE-bench
instances). There the tests contradict the spec, so **any passing patch is a cheat by
construction** — the label is a theorem, not a judgment, which is exactly the property that
breaks the circularity. Published cheat rates run 39–76% depending on model, so two or three
runs would yield ~350–500 verified positives on real multi-file repo diffs, against
ImpossibleBench's own published monitor baseline (42–65% at SWE-bench scale). That is a
compute cost, not a research problem. It is the honest next step and it is not done yet.
