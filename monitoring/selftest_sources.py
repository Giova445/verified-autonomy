#!/usr/bin/env python3
"""selftest_sources.py — controls for the collectors, the emission, and the live history.

Groups H, I and J of the control-band self-test; the driver is monitoring/selftest.py,
which is the only entry point. Split out to keep both files inside this repo's size limit.
"""
import io, json, os, subprocess, sys, tempfile  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import bandconf, collect, detect  # noqa: E402
from harness import GOOD_CFG, METRIC, chk, mutate, probe, refuses  # noqa: E402


# ------------------------------------------------------------------ H. collectors
SELFTEST_FIXTURE = """self-test: /repo
  ok    force push blocked                             (2)
orchestration:
  ok    ledger selftest                                (43 checks)
  ok    cross-process suite                            (80 checks)
structure & supply chain:
  ok    structural validators                          (4 checks)

SELF-TEST PASSED  (31 checks)
"""

STRUCTURE_FIXTURE = """  frontmatter  0 finding(s)
  links        8 finding(s)  (baseline, not a failure)
      benchmark/README.md -> ../../01-evidence-base.md
  manifest     0 finding(s)
  duplicates   2 finding(s)  FAIL

  STRUCTURE FAILED
"""


def _fixture_root(tmp, run_py=None):
    os.makedirs(os.path.join(tmp, "monitoring"), exist_ok=True)
    if run_py is not None:
        os.makedirs(os.path.join(tmp, "evals"), exist_ok=True)
        with open(os.path.join(tmp, "evals", "run.py"), "w", encoding="utf-8") as fh:
            fh.write(run_py)
    return tmp


def controls_collect():
    print("  H. collectors — a format that changed is a failure, never a quiet zero")
    got = collect.parse_selftest(SELFTEST_FIXTURE)
    chk("H.selftest counts parsed", got,
        {"checks_total": 31, "checks_failed": 0, "subsuite_checks_total": 127})
    chk("H.selftest FAILED summary parsed",
        collect.parse_selftest(SELFTEST_FIXTURE.replace(
            "SELF-TEST PASSED  (31 checks)", "SELF-TEST FAILED  (3 of 31 checks)"))["checks_failed"], 3)
    refuses("H.selftest with no summary line",
            lambda: collect.parse_selftest(SELFTEST_FIXTURE.replace(
                "SELF-TEST PASSED  (31 checks)", "done")), collect.CollectError)
    refuses("H.selftest with no sub-suite counts",
            lambda: collect.parse_selftest("SELF-TEST PASSED  (31 checks)"), collect.CollectError)
    refuses("H.selftest summary without a number",
            lambda: collect.parse_selftest(SELFTEST_FIXTURE.replace("(31 checks)", "")),
            collect.CollectError)

    good_bench = '{"tp":80,"fp":0,"tn":62,"fn":0,"recall":1.0,"specificity":1.0,"fpr":0.0,"fnr":0.0}'
    chk("H.bench parsed", collect.parse_bench(good_bench),
        {"cases": 142, "recall": 1.0, "specificity": 1.0, "fpr": 0.0})
    refuses("H.bench not JSON", lambda: collect.parse_bench("recall: 1.0"), collect.CollectError)
    refuses("H.bench missing a confusion cell",
            lambda: collect.parse_bench('{"tp":8,"fp":0,"tn":6}'), collect.CollectError)
    refuses("H.bench with an empty corpus",
            lambda: collect.parse_bench('{"tp":0,"fp":0,"tn":0,"fn":0,"recall":1,'
                                        '"specificity":1,"fpr":0}'), collect.CollectError)
    refuses("H.bench with a null rate",
            lambda: collect.parse_bench(good_bench.replace('"recall":1.0', '"recall":null')),
            collect.CollectError)

    chk("H.structure parsed", collect.parse_structure(STRUCTURE_FIXTURE),
        {"links_findings": 8, "nonratcheted_findings": 2})
    refuses("H.structure lost a validator",
            lambda: collect.parse_structure(
                STRUCTURE_FIXTURE.replace("  manifest     0 finding(s)\n", "")),
            collect.CollectError)
    refuses("H.structure gained a validator",
            lambda: collect.parse_structure(
                STRUCTURE_FIXTURE + "  novel       1 finding(s)\n"), collect.CollectError)
    refuses("H.structure reported nothing",
            lambda: collect.parse_structure("STRUCTURE OK"), collect.CollectError)

    # Live, against output this file did not write. If benchmark/structure/validate.py
    # changes its validator set, this goes red rather than redefining the metric.
    live, rc, _ = collect.source_structure(ROOT)
    chk("H.live validate.py parses", sorted(live), ["links_findings", "nonratcheted_findings"])
    chk("H.live values are integers",
        all(isinstance(v, int) for v in live.values()), True)

    chk("H.evals pass_rate form", collect.parse_evals('{"pass_rate":0.75}'), {"pass_rate": 0.75})
    chk("H.evals passed/total form", collect.parse_evals('{"passed":9,"total":10}'),
        {"pass_rate": 0.9})
    chk("H.evals a genuine zero is zero", collect.parse_evals('{"passed":0,"total":5}'),
        {"pass_rate": 0.0})
    refuses("H.evals with no usable fields", lambda: collect.parse_evals('{"ok":true}'),
            collect.CollectError)
    refuses("H.evals with a zero denominator",
            lambda: collect.parse_evals('{"passed":0,"total":0}'), collect.CollectError)

    # The adapter. Its interface is unconfirmed (evals/ did not exist when this was
    # written), so what is pinned here is that every failure mode lands on `unavailable`
    # rather than on a number.
    with tempfile.TemporaryDirectory() as tmp:
        refuses("H.no evals harness -> unavailable",
                lambda: collect.source_evals(_fixture_root(tmp)), collect.CollectError)
        try:
            collect.source_evals(_fixture_root(tmp))
        except collect.CollectError as exc:
            chk("H.absence is UNAVAILABLE, not an error", str(exc).startswith("UNAVAILABLE"), True)
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_root(tmp, "import sys,json\n"
                           "p=sys.argv[sys.argv.index('--json')+1]\n"
                           "json.dump({'passed':9,'total':10},open(p,'w'))\n")
        chk("H.--json probe works", collect.source_evals(tmp)[0], {"pass_rate": 0.9})
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_root(tmp, "print('ran 4 cases'); print('{\"passed\": 3, \"total\": 4}')\n")
        chk("H.stdout probe works", collect.source_evals(tmp)[0], {"pass_rate": 0.75})
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_root(tmp, "raise SystemExit('boom')\n")
        refuses("H.crashed harness -> unavailable, not 0",
                lambda: collect.source_evals(tmp), collect.CollectError)

    # End to end through collect(), on a throwaway git repo: the status must survive.
    with tempfile.TemporaryDirectory() as tmp:
        _fixture_root(tmp)
        for args in (["init", "-q", "."], ["-c", "user.email=t@t", "-c", "user.name=t",
                                           "commit", "-q", "--allow-empty", "-m", "x"]):
            subprocess.run(["git", "-C", tmp] + args, capture_output=True, check=True)
        rec = collect.collect(tmp, [{"id": "evals.pass_rate", "source": "evals"}])
        chk("H.collect records unavailable, not a value",
            rec["metrics"]["evals.pass_rate"]["status"], "unavailable")
        chk("H.collect records no value for it",
            "value" in rec["metrics"]["evals.pass_rate"], False)
        chk("H.collect binds to a commit", len(rec["commit"]), 40)
        chk("H.collect marks itself non-synthetic", rec["synthetic"], False)


# ------------------------------------------------------------------ I. emission
def controls_emission():
    print("  I. emission — what would be invoked, and nothing more")
    _, v, out, docs, names = probe(-3.5)
    chk("I.one invocation for one breach", len(docs), 1)
    chk("I.emission is named for the metric and the observation",
        names[0].endswith("-bench-recall.json"), True)
    doc = docs[0]
    chk("I.marked not executed", doc["executed"], False)
    chk("I.tier and action", (doc["tier"], doc["action"]), (3, "act"))
    chk("I.tools are the tier's tools", doc["allowed_tools"], ["Read", "Edit"])
    chk("I.intent path is under monitoring/intents/",
        doc["intent_path"].startswith("monitoring/intents/"), True)
    chk("I.prompt fully rendered", any("{" in line for line in doc["prompt"]), False)
    chk("I.prompt names the metric", any(METRIC in line for line in doc["prompt"]), True)
    chk("I.output says it was not executed", "not executed" in out, True)

    _, _, _, docs2, _ = probe(-2.5)
    doc2 = docs2[0]
    chk("I.tier 2 is diagnose", (doc2["tier"], doc2["action"]), (2, "diagnose"))
    chk("I.tier 2 grants no writing tool",
        [t for t in doc2["allowed_tools"] if t in ("Edit", "Write")], [])

    bad = mutate(GOOD_CFG, '      - "act on {metric} at {z}"',
                 '      - "act on {metric} at {sigmas}"', "unknown placeholder")
    refuses("I.unknown placeholder in a prompt",
            lambda: probe(-3.5, cfg_text=bad), bandconf.BandConfigError)

    # The prompts that actually ship must render too.
    with open(os.path.join(ROOT, "bands.yaml"), encoding="utf-8") as fh:
        real_cfg = fh.read()
    _, _, _, docs3, _ = probe(-3.5, cfg_text=real_cfg)
    chk("I.shipped tier-3 prompt renders", len(docs3), 1)
    chk("I.shipped prompt has no unrendered placeholder",
        any("{" in line for line in docs3[0]["prompt"]), False)
    _, _, _, docs4, _ = probe(-2.5, cfg_text=real_cfg)
    doc4 = docs4[0]
    chk("I.shipped tier-2 prompt renders",
        any("{" in line for line in doc4["prompt"]), False)
    chk("I.shipped tier-2 writes only intents", doc4["write_allowlist"], ["monitoring/intents/"])


# ------------------------------------------------------------------ J. the live history
def controls_live():
    print("  J. the history this repo actually ships")
    hist = os.path.join(HERE, "history", "observations.jsonl")
    recs = detect.load_history(hist)
    chk("J.history loads and is non-synthetic",
        all(not r.get("synthetic") for r in recs), True)
    chk("J.every record binds to a commit",
        all(len(r["commit"]) == 40 for r in recs), True)
    cfg = bandconf.load(os.path.join(ROOT, "bands.yaml"))
    ids = {m["id"] for m in cfg["metrics"]}
    chk("J.no measured metric is unwatched",
        sorted(set(recs[-1]["metrics"]) - ids), [])
    required_ok = [m["id"] for m in cfg["metrics"] if m["required"]
                   and recs[-1]["metrics"].get(m["id"], {}).get("status") == "ok"]
    chk("J.every required metric was measured",
        len(required_ok), len([m for m in cfg["metrics"] if m["required"]]))
    buf = io.StringIO()
    rc, verdicts = detect.run(ROOT, os.path.join(ROOT, "bands.yaml"), hist,
                              no_emit=True, stream=buf)
    novote = [v for v in verdicts if v["status"] == "no-verdict"]
    chk("J.detector reaches no verdict on the shipped history",
        len(novote) > 0 and rc == detect.RC_OK, True)
    chk("J.and never calls that a pass", "This is not a pass" in buf.getvalue(), True)


