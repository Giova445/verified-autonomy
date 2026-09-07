#!/usr/bin/env python3
"""selftest.py — positive controls for the Stage 6a control bands.

A detector that returns "in band" unconditionally also returns "in band" on a healthy
repo. Running it on today's history proves nothing. So every control below holds the whole
setup constant and changes exactly ONE thing, then asserts the detector's answer changes
in the one way it should.

Three properties get the most weight, because they are what makes a control band a real
instrument rather than a decoration:

  REFUSAL      below min_samples it must say so and emit nothing. Controls D-* pin the
               boundary at min_samples-1 and min_samples.
  DELETION     removing a rule must break something. The expected tier table and metric
               list are literals in monitoring/harness.py, never read back from
               bands.yaml, so deleting a tier or a metric from the config turns these red.
               Deriving the expectation from the config would delete the expectation
               along with the rule.
  FABRICATION  a synthetic or corrupt history is refused, not averaged.

Groups A-G live here; the collector, emission and live-history groups are in
monitoring/selftest_sources.py. Every one of them has been mutation-tested: see the table
in monitoring/README.md for what was broken and what went red.

Run:  python3 monitoring/selftest.py
"""
import json, os, statistics, sys, tempfile  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bandconf, collect, detect, yamlsub  # noqa: E402,F401
from harness import (BASE, MEAN, METRIC, SCORE, SD, EXPECTED_METRIC_IDS,  # noqa: E402
                     EXPECTED_TIER2_TOOLS_HEAD, EXPECTED_TIERS, FAILURES, GOOD_CFG,
                     chk, mutate, obs, probe, refuses, run_detect)
import selftest_sources  # noqa: E402


# ------------------------------------------------------------------ A. subset parser
def controls_yaml():
    print("\n  A. bands.yaml parser — every construct outside the subset is refused")
    cases = [
        ("tab indentation", "  - sigma: 1.0", "\t- sigma: 1.0"),
        ("flow mapping", "  - sigma: 1.0", "  - sigma: {a: 1}"),
        ("flow sequence", "    tools: null\n    writes: null\n    runbooks: null\n    prompt: null\n",
         "    tools: [Read]\n    writes: null\n    runbooks: null\n    prompt: null\n"),
        ("anchor", "version: 1", "version: &v 1"),
        ("alias", "window: 20", "window: *v"),
        ("block scalar", '    description: "d"\n    direction: lower_is_worse\n    required: true',
         "    description: |\n      d\n    direction: lower_is_worse\n    required: true"),
        ("document marker", "version: 1", "---\nversion: 1"),
        ("duplicate key", "window: 20", "window: 20\nwindow: 21"),
        ("key with no value", "min_samples: 8", "min_samples:"),
        ("sequence at parent indent", "tiers:\n  - sigma: 1.0", "tiers:\n- sigma: 1.0"),
        ("unterminated quote", '    description: "d"\n    direction: lower_is_worse\n    required: true',
         '    description: "d\n    direction: lower_is_worse\n    required: true'),
        ("ambiguous boolean", "dedupe_by_tree: true", "dedupe_by_tree: yes"),
    ]
    for label, old, new in cases:
        text = mutate(GOOD_CFG, old, new, label)
        refuses(f"A.{label}", lambda t=text: yamlsub.parse(t), yamlsub.YamlSubsetError)

    # Positive side: the good config parses, and a `#` inside quotes is content, not a comment.
    doc = yamlsub.parse(GOOD_CFG)
    chk("A.good config parses", isinstance(doc, dict) and len(doc["tiers"]), 3)
    chk("A.quoted hash kept", yamlsub.parse('k: "a # b"  # real comment')["k"], "a # b")
    chk("A.types", [type(doc["window"]).__name__, type(doc["dedupe_by_tree"]).__name__,
                    type(doc["tiers"][0]["sigma"]).__name__, doc["tiers"][0]["tools"]],
        ["int", "bool", "float", None])

    # Oracle: where PyYAML happens to be installed, the two parsers must agree on the real
    # file. Absence of PyYAML is reported, never counted as agreement.
    try:
        import yaml
    except ImportError:
        print("      note: PyYAML absent — oracle comparison NOT RUN (not counted as a pass)")
    else:
        chk("A.agrees with PyYAML on bands.yaml",
            yamlsub.load(os.path.join(ROOT, "bands.yaml")) ==
            yaml.safe_load(open(os.path.join(ROOT, "bands.yaml"), encoding="utf-8")), True)


# ------------------------------------------------------------------ B. schema validation
def controls_schema():
    print("  B. bands.yaml schema — one broken field each, all refused")
    good = yamlsub.parse(GOOD_CFG)
    chk("B.good config validates", bool(bandconf.validate(good)), True)

    def bad(label, fn):
        d = json.loads(json.dumps(good))
        fn(d)
        refuses(f"B.{label}", lambda: bandconf.validate(d), bandconf.BandConfigError)

    bad("unknown top-level key", lambda d: d.update(extra=1))
    bad("missing top-level key", lambda d: d.pop("window"))
    bad("unsupported version", lambda d: d.update(version=2))
    bad("min_samples below 2", lambda d: d.update(min_samples=1))
    bad("min_samples above window", lambda d: d.update(min_samples=99))
    bad("window below 2", lambda d: d.update(window=1))
    bad("non-monotonic sigma", lambda d: d["tiers"][2].update(sigma=1.5))
    bad("non-monotonic tier number", lambda d: d["tiers"][2].update(tier=1))
    bad("negative sigma", lambda d: d["tiers"][0].update(sigma=-1.0))
    bad("unknown action", lambda d: d["tiers"][1].update(action="page"))
    bad("acting tier without a prompt", lambda d: d["tiers"][1].update(prompt=None))
    bad("acting tier without tools", lambda d: d["tiers"][1].update(tools=None))
    bad("unknown key inside a tier", lambda d: d["tiers"][0].update(colour="red"))
    bad("no tiers at all", lambda d: d.update(tiers=[]))
    bad("no metrics at all", lambda d: d.update(metrics=[]))
    bad("metric with no collector", lambda d: d["metrics"][0].update(source="vibes"))
    bad("metric with unknown direction", lambda d: d["metrics"][0].update(direction="up"))
    bad("duplicate metric id", lambda d: d["metrics"][1].update(id="bench.recall"))
    bad("required not a boolean", lambda d: d["metrics"][0].update(required="yes"))
    bad("unknown key inside a metric", lambda d: d["metrics"][0].update(budget=3))
    bad("empty metric description", lambda d: d["metrics"][0].update(description="  "))
    bad("zero-variance tier out of range", lambda d: d.update(zero_variance_default_tier=9))
    bad("per-metric zero-variance tier out of range",
        lambda d: d["metrics"][0].update(zero_variance_tier=9))
    refuses("B.missing file", lambda: bandconf.load("/nonexistent/bands.yaml"),
            bandconf.BandConfigError)

    # The shipped file, checked against literals declared at the top of this module.
    real = bandconf.load(os.path.join(ROOT, "bands.yaml"))
    chk("B.shipped tier table", tuple((t["sigma"], t["tier"], t["action"]) for t in real["tiers"]),
        EXPECTED_TIERS)
    chk("B.shipped metric set", tuple(m["id"] for m in real["metrics"]), EXPECTED_METRIC_IDS)
    chk("B.tier 2 grants read tools", tuple(real["tiers"][1]["tools"][:3]),
        EXPECTED_TIER2_TOOLS_HEAD)
    chk("B.tier 2 grants no write tool",
        [t for t in real["tiers"][1]["tools"] if t in ("Edit", "Write")], [])
    chk("B.tier 3 names no unapproved runbook", real["tiers"][2]["runbooks"], [])
    chk("B.every source has a collector",
        sorted({m["source"] for m in real["metrics"]} - set(collect.SOURCES)), [])


# ------------------------------------------------------------------ C. band arithmetic
def controls_bands():
    print("  C. band arithmetic — baseline fixed, only the latest value moves")
    # Expected tiers are literals. They are NOT read from the config under test.
    for k, want_tier, want_status in [
        (-0.5, 0, "in-band"), (-1.0, 1, "breach"), (-1.99, 1, "breach"),
        (-2.0, 2, "breach"), (-2.99, 2, "breach"), (-3.0, 3, "breach"),
        (-8.0, 3, "breach"),
    ]:
        _, v, _, _, _ = probe(k, no_emit=True)
        chk(f"C.{k:+} sigma -> tier {want_tier}",
            (v[METRIC]["tier"], v[METRIC]["status"]), (want_tier, want_status))
        chk(f"C.{k:+} sigma z is the real z", round(v[METRIC]["z"], 6), round(k, 6))

    # Direction. bench.recall is lower_is_worse, so a large move UP is an improvement:
    # reported, never acted on, and no invocation emitted.
    _, v, _, emitted, _ = probe(+3.5)
    chk("C.improving move capped to log", v[METRIC]["tier"], 1)
    chk("C.improving move labelled", v[METRIC]["status"], "breach-improving")
    chk("C.improving move emits nothing", emitted, [])
    _, v, _, emitted, _ = probe(-3.5)
    chk("C.worsening move reaches tier 3", v[METRIC]["tier"], 3)
    chk("C.worsening move emits one invocation", len(emitted), 1)
    _, _, _, emitted, _ = probe(-1.4)
    chk("C.tier 1 emits nothing", emitted, [])

    # Zero variance: a constant baseline has no sigma. Report that, do not divide by zero.
    def constant(latest, cfg=GOOD_CFG):
        with tempfile.TemporaryDirectory() as tmp:
            recs = [obs(i, 1.0) for i in range(12)] + [obs(90, latest)]
            return run_detect(tmp, cfg, recs, no_emit=True)

    _, v, _, _, _ = constant(1.0)
    chk("C.constant baseline unchanged -> in band",
        (v[METRIC]["status"], v[METRIC]["tier"]), ("in-band", 0))
    _, v, _, _, _ = constant(0.9)
    chk("C.constant baseline changed -> zero-variance tier",
        (v[METRIC]["status"], v[METRIC]["tier"]), ("zero-variance-change", 2))
    chk("C.zero variance reports no z", v[METRIC]["z"], None)
    _, v, _, _, _ = constant(1.1)
    chk("C.constant baseline improved -> capped to log",
        (v[METRIC]["status"], v[METRIC]["tier"]), ("breach-improving", 1))
    over = mutate(GOOD_CFG, "    direction: lower_is_worse\n    required: true",
                  "    direction: lower_is_worse\n    required: true\n    zero_variance_tier: 3",
                  "per-metric zero-variance override")
    _, v, _, _, _ = constant(0.9, over)
    chk("C.per-metric zero-variance override wins", v[METRIC]["tier"], 3)


# ------------------------------------------------------------------ D. refusals
def controls_refusal():
    print("  D. refusals — too little history, or history that cannot be trusted")
    for n, want in [(7, "no-verdict"), (8, "in-band")]:
        _, v, out, emitted, _ = probe(-0.2, n=n)
        chk(f"D.n={n} -> {want}", v[METRIC]["status"], want)
        chk(f"D.n={n} reports n honestly", v[METRIC]["n"], n)
        if want == "no-verdict":
            chk("D.no verdict computes no sigma",
                (v[METRIC]["z"], v[METRIC]["mean"], v[METRIC]["stdev"]), (None, None, None))
            chk("D.no verdict emits nothing", emitted, [])
            chk("D.no verdict never prints in-band", "in-band" in out, False)

    with tempfile.TemporaryDirectory() as tmp:
        recs = [obs(i, v) for i, v in enumerate(BASE)] + [obs(90, MEAN - 4 * SD)]
        refuses("D.corrupt history line",
                lambda: run_detect(tmp, GOOD_CFG, None,
                                   raw_lines=[json.dumps(recs[0]), "{not json"]),
                detect.HistoryError)
        refuses("D.missing history file",
                lambda: detect.load_history(os.path.join(tmp, "nope.jsonl")),
                detect.HistoryError)
        refuses("D.empty history file",
                lambda: run_detect(tmp, GOOD_CFG, None, raw_lines=[]),
                detect.HistoryError)
        bad_schema = json.loads(json.dumps(recs[0])); bad_schema["schema"] = "other@9"
        refuses("D.wrong observation schema",
                lambda: run_detect(tmp, GOOD_CFG, [bad_schema]), detect.HistoryError)
        no_digest = json.loads(json.dumps(recs[0])); no_digest.pop("tree_digest")
        refuses("D.record with no tree digest",
                lambda: run_detect(tmp, GOOD_CFG, [no_digest]), detect.HistoryError)

        dup = [obs(0, 100.0), obs(0, 999.0)]
        refuses("D.a row pasted in with a repeated timestamp",
                lambda: run_detect(tmp, GOOD_CFG, dup), detect.HistoryError)
        back = [obs(5, 100.0), obs(1, 999.0)]
        refuses("D.a row dated before the one above it",
                lambda: run_detect(tmp, GOOD_CFG, back), detect.HistoryError)
        odd_ts = json.loads(json.dumps(recs[0])); odd_ts["ts"] = "yesterday"
        refuses("D.a timestamp that is not fixed-width UTC",
                lambda: run_detect(tmp, GOOD_CFG, [odd_ts]), detect.HistoryError)
        fake_ts = json.loads(json.dumps(recs[0])); fake_ts["ts"] = "2026-09-04T03:99:99Z"
        refuses("D.a right-shaped timestamp that is not a real instant",
                lambda: run_detect(tmp, GOOD_CFG, [fake_ts]), detect.HistoryError)
        _, v, _, _, _ = run_detect(tmp, GOOD_CFG, recs, no_emit=True)
        chk("D.a properly ordered history still loads", v[METRIC]["n"], 12)

        synth = [obs(i, v, synthetic=(i == 3)) for i, v in enumerate(BASE)] + [obs(90, MEAN)]
        refuses("D.synthetic record refused by default",
                lambda: run_detect(tmp, GOOD_CFG, synth), detect.HistoryError)
        rc, v, _, _, _ = run_detect(tmp, GOOD_CFG, synth, allow_synthetic=True, no_emit=True)
        chk("D.synthetic record allowed only behind the flag", v[METRIC]["n"], 12)
        refuses("D.unreadable config",
                lambda: run_detect(tmp, "version: [1]\n", recs), bandconf.BandConfigError)


# ------------------------------------------------------------------ E. deletion controls
def controls_deletion():
    print("  E. deletion — removing a rule must change the answer")
    without3 = GOOD_CFG.split("  - sigma: 3.0")[0] + GOOD_CFG.split("prompt:\n      - \"act on {metric} at {z}\"\n")[1]
    chk("E.tier-3 removal actually removed it", "sigma: 3.0" in without3, False)
    _, v, _, _, _ = probe(-3.5, cfg_text=without3, no_emit=True)
    chk("E.without the 3-sigma tier, a 3.5-sigma breach stops at tier 2", v[METRIC]["tier"], 2)
    _, v, _, _, _ = probe(-3.5, no_emit=True)
    chk("E.with it, the same breach reaches tier 3", v[METRIC]["tier"], 3)

    # A metric deleted from the config is still measured. It must be named as unwatched,
    # not silently dropped.
    without_metric = GOOD_CFG.replace(
        '  - id: bench.recall\n    source: bench\n    description: "d"\n'
        "    direction: lower_is_worse\n    required: true\n", "")
    chk("E.metric removal actually removed it", "bench.recall" in without_metric, False)
    with tempfile.TemporaryDirectory() as tmp:
        recs = [obs(i, v) for i, v in enumerate(BASE)] + [obs(90, MEAN)]
        rc, _, out, _, _ = run_detect(tmp, without_metric, recs, no_emit=True)
        chk("E.unwatched metric is named", "UNWATCHED" in out and METRIC in out, True)
        chk("E.unwatched alone is not an error", rc, detect.RC_OK)
        rc, _, _, _, _ = run_detect(tmp, without_metric, recs, no_emit=True, strict_coverage=True)
        chk("E.--strict-coverage makes it an error", rc, detect.RC_ERROR)


# ------------------------------------------------------------------ F. fail closed
def controls_failclosed():
    print("  F. fail closed — a metric that could not be read is not a calm metric")
    with tempfile.TemporaryDirectory() as tmp:
        base = [obs(i, v) for i, v in enumerate(BASE)]
        rc, _, out, _, _ = run_detect(tmp, GOOD_CFG, base + [obs(90, 0, status="error")],
                                      no_emit=True)
        chk("F.required metric errored -> ERROR", rc, detect.RC_ERROR)
        rc, _, _, _, _ = run_detect(tmp, GOOD_CFG, base + [obs(90, 0, status=None)], no_emit=True)
        chk("F.required metric absent -> ERROR", rc, detect.RC_ERROR)
        rc, v, _, _, _ = run_detect(tmp, GOOD_CFG, base + [obs(90, MEAN)], no_emit=True)
        chk("F.optional metric unavailable is not an error", rc, detect.RC_OK)
        chk("F.optional metric still reported", v["evals.pass_rate"]["status"], "unavailable")
        rc, _, _, _, _ = run_detect(tmp, GOOD_CFG, base + [obs(90, MEAN - 2.5 * SD)])
        chk("F.tier-2 breach exits 1", rc, detect.RC_BREACH)
        rc, _, _, _, _ = run_detect(tmp, GOOD_CFG, [obs(0, 100.0), obs(1, 100.0)],
                                    no_emit=True, require_baseline=True)
        chk("F.--require-baseline turns no-verdict into exit 3", rc, detect.RC_NO_BASELINE)


# ------------------------------------------------------------------ G. sample hygiene
def controls_sampling():
    print("  G. sample hygiene — re-runs and dirty trees are not free samples")
    with tempfile.TemporaryDirectory() as tmp:
        same = [obs(i, v, digest="same") for i, v in enumerate(BASE)] + [obs(90, MEAN - 4 * SD)]
        _, v, _, _, _ = run_detect(tmp, GOOD_CFG, same, no_emit=True)
        chk("G.identical trees collapse to one sample",
            (v[METRIC]["n"], v[METRIC]["n_raw"], v[METRIC]["status"]), (1, 12, "no-verdict"))
        off = mutate(GOOD_CFG, "dedupe_by_tree: true", "dedupe_by_tree: false",
                     "dedupe switch")
        _, v, _, _, _ = run_detect(tmp, off, same, no_emit=True)
        chk("G.dedupe off keeps all 12", v[METRIC]["n"], 12)

        dirty = [obs(i, v) for i, v in enumerate(BASE)] + [obs(90, MEAN - 4 * SD)]
        clean = [obs(i, v, clean=True) for i, v in enumerate(BASE)] + [obs(90, MEAN - 4 * SD)]
        strict = mutate(GOOD_CFG, "baseline_requires_clean_tree: false",
                        "baseline_requires_clean_tree: true", "clean-tree switch")
        _, v, _, _, _ = run_detect(tmp, GOOD_CFG, dirty, no_emit=True)
        chk("G.dirty points counted by default, and counted out loud",
            (v[METRIC]["n"], v[METRIC]["dirty_points"]), (12, 12))
        _, v, _, _, _ = run_detect(tmp, strict, clean, no_emit=True)
        chk("G.clean-tree-only keeps clean points",
            (v[METRIC]["n"], v[METRIC]["tier"]), (12, 3))
        _, v, _, _, _ = run_detect(tmp, strict, dirty, no_emit=True)
        chk("G.clean-tree-only drops dirty ones", (v[METRIC]["n"], v[METRIC]["status"]),
            (0, "no-verdict"))

        forged = json.loads(json.dumps(clean[0])); forged["tree_digest"] = "0" * 16
        refuses("G.a clean-tree row whose digest the commit does not imply",
                lambda: run_detect(tmp, GOOD_CFG, [forged]), detect.HistoryError)
        _, v, _, _, _ = run_detect(tmp, GOOD_CFG, clean, no_emit=True)
        chk("G.an honest clean-tree row is accepted", v[METRIC]["n"], 12)


def main():
    print("control bands self-test")
    groups = (controls_yaml, controls_schema, controls_bands, controls_refusal,
              controls_deletion, controls_failclosed, controls_sampling,
              selftest_sources.controls_collect, selftest_sources.controls_emission,
              selftest_sources.controls_live)
    for fn in groups:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            # A control group that crashed has not passed. Recording it as a failure
            # instead of letting the traceback escape keeps the summary line printable,
            # which is what a parent suite greps for.
            SCORE["fail"] += 1
            FAILURES.append(f"{fn.__name__} crashed: {type(exc).__name__}: {exc}")
    total = SCORE["pass"] + SCORE["fail"]
    print()
    if SCORE["fail"]:
        for f in FAILURES:
            print(f"  FAIL  {f}")
        print(f"\n  BANDS SELF-TEST FAILED  ({SCORE['fail']} of {total} checks)")
        return 1
    print(f"  BANDS SELF-TEST PASSED  ({SCORE['pass']} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
