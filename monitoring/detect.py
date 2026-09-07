#!/usr/bin/env python3
"""detect.py — Stage 6a control-band detector.

Compares the latest observation against a rolling baseline built from the ones before it
and assigns the tier bands.yaml declares for that distance. Deterministic: same history and
same config give the same verdict on every machine.

WHAT IT REFUSES, AND WHY THAT IS THE POINT

  n below min_samples      -> NO VERDICT. It does not compute a sigma, does not guess a
                              baseline, and emits no invocation. A band derived from two
                              points either fires on noise or never fires at all, and the
                              output looks identical either way, so the only honest answer
                              at n=1 is to say n=1.
  a constant baseline      -> ZERO-VARIANCE CHANGE, not "infinite sigma". Dividing by a
                              zero standard deviation does not produce a large z-score, it
                              produces a fabricated one.
  a corrupt history line   -> error exit. Not "no data", not "in band".
  a synthetic record       -> refused unless --allow-synthetic, which only the controls
                              pass. Fabricated history is the one input that would make
                              every number here meaningless, so it takes an explicit flag.
  a required metric that
  is missing or errored    -> error exit. Collection breaking must never read as calm.

It emits what WOULD be invoked (monitoring/invocations/*.json) and never invokes anything.
The diagnosis itself is written by the agent, to the intent.md path named in the emission.
"""
import argparse, json, os, re, statistics, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bandconf, collect  # noqa: E402

DEFAULT_ROOT = os.path.dirname(HERE)
OBS_SCHEMA = "verified-autonomy/monitoring/observation@1"
# Fixed-width UTC, so lexicographic order is chronological order. Enforced, because the
# append-only ordering check below is meaningless over timestamps of varying shape.
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
EMIT_SCHEMA = "verified-autonomy/monitoring/invocation@1"

RC_OK, RC_BREACH, RC_ERROR, RC_NO_BASELINE = 0, 1, 2, 3


class HistoryError(RuntimeError):
    pass


# --------------------------------------------------------------------------- history

def load_history(path, allow_synthetic=False):
    """Read observations.jsonl strictly. Anything unreadable is an error, never an empty
    history: an empty history and a corrupt one would otherwise print the same calm."""
    if not os.path.exists(path):
        raise HistoryError(f"{path}: missing; there is no history to build a baseline from")
    records = []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        raise HistoryError(f"{path}: unreadable ({exc})") from exc
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            raise HistoryError(f"{path}:{n}: not valid JSON ({exc})") from exc
        if not isinstance(rec, dict):
            raise HistoryError(f"{path}:{n}: record is not an object")
        if rec.get("schema") != OBS_SCHEMA:
            raise HistoryError(f"{path}:{n}: schema {rec.get('schema')!r} != {OBS_SCHEMA!r}")
        for key in ("ts", "commit", "tree_digest", "metrics"):
            if key not in rec:
                raise HistoryError(f"{path}:{n}: record is missing {key!r}")
        if not isinstance(rec["metrics"], dict):
            raise HistoryError(f"{path}:{n}: `metrics` is not an object")
        if rec.get("synthetic") and not allow_synthetic:
            raise HistoryError(
                f"{path}:{n}: record is marked synthetic. Fabricated history makes every "
                "band meaningless; pass --allow-synthetic only in controls.")
        # Append-only, in time order. This is an integrity check, not a nicety: a row
        # pasted in by hand — the cheapest way to fake a baseline — almost always
        # duplicates or predates a timestamp already in the file. It catches sloppy
        # forgery and accidental double-appends, not a careful forger; against that the
        # defence is that this file is version-controlled and its diffs get read.
        if not TS_RE.match(str(rec["ts"])):
            raise HistoryError(f"{path}:{n}: ts {rec['ts']!r} is not YYYY-MM-DDTHH:MM:SSZ")
        try:
            datetime.strptime(rec["ts"], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            # The regex fixes the width so the ordering below is meaningful; this fixes
            # that the width is filled with a real instant. `03:99:99` passes the first
            # and sorts after everything real.
            raise HistoryError(f"{path}:{n}: ts {rec['ts']!r} is not a real UTC instant ({exc})") from exc
        if not rec.get("dirty"):
            want = collect.tree_digest(rec["commit"], "")
            if rec["tree_digest"] != want:
                raise HistoryError(
                    f"{path}:{n}: record claims a clean tree at {rec['commit'][:12]} but its "
                    f"tree_digest is {rec['tree_digest']}, not the {want} that commit implies. "
                    "A clean-tree digest is a pure function of the commit, so this row was "
                    "not produced by monitoring/collect.py.")
        if records and rec["ts"] <= records[-1]["ts"]:
            raise HistoryError(
                f"{path}:{n}: ts {rec['ts']} is not after the previous record's "
                f"{records[-1]['ts']}; observations are append-only and each run takes "
                "the better part of a minute, so a repeated or earlier timestamp means "
                "the file was edited rather than appended to")
        records.append(rec)
    if not records:
        raise HistoryError(f"{path}: contains no observations")
    return records


def baseline_points(prior, metric_id, cfg):
    """Baseline values for one metric, newest-first filtering, oldest-first output."""
    usable = [r for r in prior
              if r["metrics"].get(metric_id, {}).get("status") == "ok"]
    if cfg["baseline_requires_clean_tree"]:
        usable = [r for r in usable if not r.get("dirty")]
    n_raw = len(usable)
    if cfg["dedupe_by_tree"]:
        seen, kept = set(), []
        for r in reversed(usable):                 # newest first, keep the newest per tree
            key = r["tree_digest"]
            if key in seen:
                continue
            seen.add(key)
            kept.append(r)
        usable = list(reversed(kept))
    window = usable[-cfg["window"]:]
    return window, n_raw


# --------------------------------------------------------------------------- verdicts

def _is_improving(direction, value, mean):
    if direction == "lower_is_worse":
        return value > mean
    if direction == "higher_is_worse":
        return value < mean
    return False


def assess(metric, latest, prior, cfg):
    """One metric -> one verdict dict. No side effects."""
    mid = metric["id"]
    obs = latest["metrics"].get(mid)
    v = {"metric": mid, "direction": metric["direction"], "required": metric["required"],
         "tier": 0, "z": None, "n": 0, "n_raw": 0, "value": None,
         "mean": None, "stdev": None, "baseline_commit": None, "note": ""}

    if obs is None:
        v["status"] = "missing"
        v["note"] = "not present in the latest observation"
        return v
    if obs.get("status") != "ok":
        v["status"] = obs.get("status", "error")
        v["note"] = obs.get("reason", "")
        return v
    value = obs.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        v["status"] = "error"
        v["note"] = f"value {value!r} is not a number"
        return v
    v["value"] = value

    window, n_raw = baseline_points(prior, mid, cfg)
    v["n"], v["n_raw"] = len(window), n_raw
    v["dirty_points"] = sum(1 for r in window if r.get("dirty"))
    if window:
        v["baseline_commit"] = window[0]["commit"]

    if len(window) < cfg["min_samples"]:
        v["status"] = "no-verdict"
        v["note"] = (f"n={len(window)} effective sample(s) < min_samples="
                     f"{cfg['min_samples']}; refusing to compute a sigma")
        return v

    values = [r["metrics"][mid]["value"] for r in window]
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values)
    v["mean"], v["stdev"] = mean, stdev

    if stdev == 0.0:
        if value == mean:
            v["status"] = "in-band"
            v["note"] = "constant baseline, unchanged"
            return v
        v["status"] = "zero-variance-change"
        zvt = metric["zero_variance_tier"]
        v["tier"] = cfg["zero_variance_default_tier"] if zvt is None else zvt
        v["note"] = (f"baseline is constant at {mean:g}; a z-score is undefined, so the "
                     f"configured zero-variance tier applies")
    else:
        z = (value - mean) / stdev
        v["z"] = z
        v["tier"] = bandconf.tier_for(cfg, z)
        v["status"] = "in-band" if v["tier"] == 0 else "breach"

    if v["tier"] > 1 and _is_improving(metric["direction"], value, mean):
        v["note"] = ((v["note"] + "; ") if v["note"] else "") + \
            f"moved the good way for {metric['direction']}, capped to tier 1 (log only)"
        v["tier"] = 1
        v["status"] = "breach-improving"
    return v


# --------------------------------------------------------------------------- emission

def render(lines, fields):
    out = []
    for line in lines:
        try:
            out.append(line.format(**fields))
        except (KeyError, IndexError) as exc:
            raise bandconf.BandConfigError(
                f"prompt line has an unknown placeholder {exc}; known placeholders are "
                f"{sorted(fields)}") from exc
    return out


def emit(verdict, latest, cfg, outdir, intents_rel):
    """Write the invocation that WOULD be made. Nothing is executed here."""
    spec = bandconf.tier_spec(cfg, verdict["tier"])
    if spec is None:
        raise bandconf.BandConfigError(
            f"tier {verdict['tier']} has no entry in bands.yaml; the zero-variance tier "
            "must name a tier that exists")
    stamp = latest["ts"].replace(":", "").replace("-", "")
    slug = verdict["metric"].replace(".", "-")
    intent_path = os.path.join(intents_rel, f"{stamp}-{slug}.intent.md")
    fields = {
        "metric": verdict["metric"],
        "value": f"{verdict['value']:g}",
        "mean": "n/a" if verdict["mean"] is None else f"{verdict['mean']:g}",
        "stdev": "n/a" if verdict["stdev"] is None else f"{verdict['stdev']:g}",
        "n": verdict["n"], "window": cfg["window"],
        "z": "undefined (constant baseline)" if verdict["z"] is None else f"{verdict['z']:.2f}",
        "commit": latest["commit"], "baseline_commit": verdict["baseline_commit"] or "unknown",
        "intent_path": intent_path,
    }
    doc = {
        "schema": EMIT_SCHEMA,
        "emitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "executed": False,
        "observation_ts": latest["ts"], "commit": latest["commit"],
        "dirty_tree": bool(latest.get("dirty")),
        "tier": verdict["tier"], "action": spec["action"],
        "verdict": verdict,
        "allowed_tools": spec["tools"], "write_allowlist": spec["writes"],
        "runbooks": spec["runbooks"],
        "intent_path": intent_path,
        "prompt": render(spec["prompt"], fields),
    }
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{stamp}-{slug}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path, doc


# --------------------------------------------------------------------------- driver

def run(root, cfg_path, hist_path, allow_synthetic=False, emit_dir=None,
        strict_coverage=False, require_baseline=False, no_emit=False, stream=sys.stdout):
    cfg = bandconf.load(cfg_path)
    records = load_history(hist_path, allow_synthetic=allow_synthetic)
    latest, prior = records[-1], records[:-1]

    p = lambda s="": print(s, file=stream)
    p(f"bands: {os.path.relpath(cfg_path, root)}   history: "
      f"{os.path.relpath(hist_path, root)} ({len(records)} observation(s))")
    p(f"latest: {latest['ts']}  {latest['commit'][:12]}"
      f"{'  DIRTY TREE' if latest.get('dirty') else ''}")
    p(f"policy: window={cfg['window']} min_samples={cfg['min_samples']} "
      f"dedupe_by_tree={cfg['dedupe_by_tree']} "
      f"clean_tree_only={cfg['baseline_requires_clean_tree']}")
    p()

    verdicts = [assess(m, latest, prior, cfg) for m in cfg["metrics"]]
    p(f"  {'metric':<34}{'status':<22}{'value':>10}{'n':>5}{'z':>9}  tier")
    p("  " + "-" * 84)
    for v in verdicts:
        val = "-" if v["value"] is None else f"{v['value']:.6g}"
        z = "-" if v["z"] is None else f"{v['z']:+.2f}"
        p(f"  {v['metric']:<34}{v['status']:<22}{val:>10}{v['n']:>5}{z:>9}   {v['tier']}")
        if v["note"]:
            p(f"      {v['note']}")

    unwatched = sorted(set(latest["metrics"]) - {m["id"] for m in cfg["metrics"]})
    if unwatched:
        p()
        p(f"  UNWATCHED — measured but absent from bands.yaml: {unwatched}")
        p("      A metric quietly dropped from the config stops being watched without "
          "anything turning red.")

    emitted = []
    emit_dir = emit_dir or os.path.join(HERE, "invocations")
    for v in verdicts:
        if v["tier"] >= 2 and not no_emit:
            path, doc = emit(v, latest, cfg, emit_dir, "monitoring/intents")
            emitted.append((v, path, doc))

    if emitted:
        p()
        p("  WOULD INVOKE (emitted, not executed):")
        for v, path, doc in emitted:
            p(f"    tier {doc['tier']} / {doc['action']}  {v['metric']}")
            p(f"      spec   {os.path.relpath(path, root)}")
            p(f"      intent {doc['intent_path']}")
            p(f"      tools  {doc['allowed_tools']}")

    hard = [v for v in verdicts
            if v["required"] and v["status"] in ("missing", "error", "unavailable", "skipped")]
    breaches = [v for v in verdicts if v["tier"] >= 2]
    novote = [v for v in verdicts if v["status"] == "no-verdict"]

    p()
    if hard:
        p(f"  BANDS: ERROR — {len(hard)} required metric(s) could not be read: "
          f"{[v['metric'] for v in hard]}")
        rc = RC_ERROR
    elif breaches:
        p(f"  BANDS: BREACH — {len(breaches)} metric(s) at tier 2 or above")
        rc = RC_BREACH
    elif novote and require_baseline:
        p(f"  BANDS: NO VERDICT for {len(novote)}/{len(verdicts)} metric(s) and "
          "--require-baseline was set")
        rc = RC_NO_BASELINE
    elif novote:
        p(f"  BANDS: NO VERDICT for {len(novote)}/{len(verdicts)} metric(s) — "
          "the baseline is not established yet. This is not a pass.")
        rc = RC_OK
    else:
        p(f"  BANDS: all {len(verdicts)} metric(s) in band")
        rc = RC_OK
    if unwatched and strict_coverage:
        p("  BANDS: ERROR — unwatched metrics and --strict-coverage was set")
        rc = RC_ERROR
    return rc, verdicts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage 6a control-band detector")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--config", default=None)
    ap.add_argument("--history", default=None)
    ap.add_argument("--emit-dir", default=None)
    ap.add_argument("--no-emit", action="store_true", help="assess without writing invocations")
    ap.add_argument("--allow-synthetic", action="store_true",
                    help="permit records marked synthetic; for controls only")
    ap.add_argument("--strict-coverage", action="store_true",
                    help="fail when an observed metric is not declared in bands.yaml")
    ap.add_argument("--require-baseline", action="store_true",
                    help="fail when any metric still has no verdict")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    cfg_path = args.config or os.path.join(root, "bands.yaml")
    hist_path = args.history or os.path.join(HERE, "history", "observations.jsonl")
    try:
        rc, _ = run(root, cfg_path, hist_path,
                    allow_synthetic=args.allow_synthetic, emit_dir=args.emit_dir,
                    strict_coverage=args.strict_coverage,
                    require_baseline=args.require_baseline, no_emit=args.no_emit)
    except (bandconf.BandConfigError, HistoryError) as exc:
        print(f"  BANDS: ERROR — {exc}", file=sys.stderr)
        return RC_ERROR
    return rc


if __name__ == "__main__":
    sys.exit(main())
