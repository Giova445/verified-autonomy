#!/usr/bin/env python3
"""harness.py — shared scaffolding for the control-band controls.

Split out of monitoring/selftest.py only so that no file here runs past the size this
repo keeps to. It holds the score, the assertion helpers, the known-good config the
mutations start from, and the synthetic-history builders. It contains no controls itself.

The literals at the top are the load-bearing part: EXPECTED_TIERS and EXPECTED_METRIC_IDS
are declared HERE, not read out of bands.yaml, so deleting a tier or a metric from the
config fails a control instead of deleting its own expectation.
"""
import io, json, os, statistics, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bandconf, collect, detect, yamlsub  # noqa: E402,F401

SCORE = {"pass": 0, "fail": 0}
FAILURES = []


def chk(label, got, want):
    if got == want:
        SCORE["pass"] += 1
    else:
        SCORE["fail"] += 1
        FAILURES.append(f"{label}: want={want!r} got={got!r}")


def refuses(label, fn, *exc):
    """Assert fn() raises. A control that cannot fail is not a control."""
    try:
        fn()
    except exc:
        SCORE["pass"] += 1
        return
    except Exception as other:  # noqa: BLE001 - the wrong exception is still a failure
        SCORE["fail"] += 1
        FAILURES.append(f"{label}: raised {type(other).__name__}({other}), wanted {exc}")
        return
    SCORE["fail"] += 1
    FAILURES.append(f"{label}: accepted input that must be refused")


# --------------------------------------------------------------------- independent facts
# Declared here so that deleting them from bands.yaml fails a control. If these were read
# out of bands.yaml, removing a tier would remove its expectation too and this file would
# stay green over a config that no longer does anything.
EXPECTED_TIERS = ((1.0, 1, "log"), (2.0, 2, "diagnose"), (3.0, 3, "act"))
EXPECTED_METRIC_IDS = (
    "selftest.checks_total", "selftest.checks_failed", "selftest.subsuite_checks_total",
    "bench.cases", "bench.recall", "bench.specificity", "bench.fpr",
    "structure.links_findings", "structure.nonratcheted_findings", "evals.pass_rate",
)
EXPECTED_TIER2_TOOLS_HEAD = ("Read", "Grep", "Glob")

GOOD_CFG = """version: 1
window: 20
min_samples: 8
dedupe_by_tree: true
baseline_requires_clean_tree: false
zero_variance_default_tier: 2
tiers:
  - sigma: 1.0
    tier: 1
    action: log
    tools: null
    writes: null
    runbooks: null
    prompt: null
  - sigma: 2.0
    tier: 2
    action: diagnose
    tools:
      - Read
    writes:
      - monitoring/intents/
    runbooks: null
    prompt:
      - "metric={metric} z={z} n={n} intent={intent_path}"
  - sigma: 3.0
    tier: 3
    action: act
    tools:
      - Read
      - Edit
    writes:
      - monitoring/intents/
    runbooks: null
    prompt:
      - "act on {metric} at {z}"
metrics:
  - id: bench.recall
    source: bench
    description: "d"
    direction: lower_is_worse
    required: true
  - id: evals.pass_rate
    source: evals
    description: "d"
    direction: lower_is_worse
    required: false
"""


def mutate(text, old, new, label):
    """Replace exactly one occurrence, or fail loudly. A mutation that silently did not
    apply produces a control that tests the unmutated input and calls it a pass."""
    if text.count(old) != 1:
        chk(f"{label} [mutation anchor]", text.count(old), 1)
        return text
    return text.replace(old, new)


# ------------------------------------------------------------------ harness for detector
BASE = [100.0, 101.0, 99.0, 102.0, 98.0, 101.0, 99.0, 100.0, 102.0, 98.0, 100.0, 101.0]
MEAN = statistics.fmean(BASE)
SD = statistics.stdev(BASE)
METRIC = "bench.recall"


def obs(i, value, status="ok", digest=None, clean=False, synthetic=False, extra=None):
    m = {"evals.pass_rate": {"status": "unavailable", "reason": "absent"}}
    if status is not None:
        m[METRIC] = {"status": status} if status != "ok" else {"status": "ok", "value": value}
    if extra:
        m.update(extra)
    commit = f"{i:040d}"
    # Synthetic records are marked dirty unless a digest is supplied, because a clean-tree
    # digest is checked against the commit and a made-up one is refused — which is the
    # point of that check.
    return {"schema": detect.OBS_SCHEMA,
            "ts": f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00Z",
            "commit": commit,
            "tree_digest": digest or collect.tree_digest(commit, "" if clean else f"x{i}"),
            "dirty": not clean,
            "synthetic": synthetic, "sources": {}, "metrics": m}


def run_detect(tmp, cfg_text, records, raw_lines=None, **kw):
    cfg = os.path.join(tmp, "bands.yaml")
    hist = os.path.join(tmp, "obs.jsonl")
    emitdir = os.path.join(tmp, "invocations")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write(cfg_text)
    with open(hist, "w", encoding="utf-8") as fh:
        for line in (raw_lines if raw_lines is not None
                     else [json.dumps(r, sort_keys=True) for r in records]):
            fh.write(line + "\n")
    buf = io.StringIO()
    rc, verdicts = detect.run(tmp, cfg, hist, emit_dir=emitdir, stream=buf, **kw)
    by_id = {v["metric"]: v for v in verdicts}
    names = sorted(os.listdir(emitdir)) if os.path.isdir(emitdir) else []
    # Read the emissions here: the caller's temp directory is gone by the time it looks.
    docs = [json.load(open(os.path.join(emitdir, n), encoding="utf-8")) for n in names]
    return rc, by_id, buf.getvalue(), docs, names


def probe(k, n=len(BASE), cfg_text=GOOD_CFG, **kw):
    """Baseline held constant; only the latest value moves, to k standard deviations."""
    with tempfile.TemporaryDirectory() as tmp:
        recs = [obs(i, v) for i, v in enumerate(BASE[:n])]
        recs.append(obs(90, MEAN + k * SD))
        return run_detect(tmp, cfg_text, recs, **kw)


