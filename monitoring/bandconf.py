#!/usr/bin/env python3
"""Schema validation for bands.yaml.

Parsing it is not the same as understanding it. This module turns the parsed document
into a checked configuration and refuses everything else, because a control file that is
half-understood produces bands that half-exist.

Every rejection below has a positive control in monitoring/selftest.py that mutates ONE
field of a known-good config and asserts this module refuses it.
"""
import os

try:
    from . import yamlsub  # package import
except ImportError:  # pragma: no cover - script import
    import yamlsub

# Collectors that monitoring/collect.py actually implements. A metric naming a source not
# in this set is a configuration error, not a metric that silently never reports: an
# unimplemented source would otherwise look exactly like a healthy one that is in band.
KNOWN_SOURCES = ("selftest", "bench", "structure", "evals")
DIRECTIONS = ("higher_is_worse", "lower_is_worse", "both")
ACTIONS = ("log", "diagnose", "act")

TOP_KEYS = {
    "version": int, "window": int, "min_samples": int,
    "dedupe_by_tree": bool, "baseline_requires_clean_tree": bool,
    "zero_variance_default_tier": int, "tiers": list, "metrics": list,
}
TIER_KEYS = {"sigma", "tier", "action", "tools", "writes", "runbooks", "prompt"}
TIER_REQUIRED = {"sigma", "tier", "action"}
METRIC_KEYS = {"id", "source", "description", "direction", "required", "zero_variance_tier"}
METRIC_REQUIRED = {"id", "source", "description", "direction", "required"}

SUPPORTED_VERSION = 1


class BandConfigError(ValueError):
    """Raised for any config this module does not fully understand."""


def _strlist(value, where):
    """null means "none"; anything else must be a list of non-empty strings."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise BandConfigError(f"{where}: expected a list or null, got {type(value).__name__}")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BandConfigError(f"{where}: list entries must be non-empty strings")
    return list(value)


def _check_tiers(raw):
    if not raw:
        raise BandConfigError("tiers: at least one tier is required")
    tiers, prev = [], None
    for n, t in enumerate(raw):
        where = f"tiers[{n}]"
        if not isinstance(t, dict):
            raise BandConfigError(f"{where}: expected a mapping")
        unknown = set(t) - TIER_KEYS
        if unknown:
            raise BandConfigError(f"{where}: unknown key(s) {sorted(unknown)}")
        missing = TIER_REQUIRED - set(t)
        if missing:
            raise BandConfigError(f"{where}: missing key(s) {sorted(missing)}")
        sigma, tier, action = t["sigma"], t["tier"], t["action"]
        if isinstance(sigma, bool) or not isinstance(sigma, (int, float)):
            raise BandConfigError(f"{where}.sigma: must be a number")
        if sigma <= 0:
            raise BandConfigError(f"{where}.sigma: must be > 0")
        if isinstance(tier, bool) or not isinstance(tier, int) or tier < 1:
            raise BandConfigError(f"{where}.tier: must be an integer >= 1")
        if action not in ACTIONS:
            raise BandConfigError(f"{where}.action: must be one of {list(ACTIONS)}")
        if prev is not None:
            if sigma <= prev["sigma"]:
                raise BandConfigError(f"{where}.sigma: must be strictly greater than the previous tier's")
            if tier <= prev["tier"]:
                raise BandConfigError(f"{where}.tier: must be strictly greater than the previous tier's")
        entry = {
            "sigma": float(sigma), "tier": tier, "action": action,
            "tools": _strlist(t.get("tools"), f"{where}.tools"),
            "writes": _strlist(t.get("writes"), f"{where}.writes"),
            "runbooks": _strlist(t.get("runbooks"), f"{where}.runbooks"),
            "prompt": _strlist(t.get("prompt"), f"{where}.prompt"),
        }
        if entry["action"] != "log" and not entry["prompt"]:
            raise BandConfigError(f"{where}: action {entry['action']!r} invokes an agent but carries no prompt")
        if entry["action"] != "log" and not entry["tools"]:
            raise BandConfigError(f"{where}: action {entry['action']!r} invokes an agent but grants no tools")
        tiers.append(entry)
        prev = entry
    return tiers


def _check_metrics(raw, max_tier):
    if not raw:
        raise BandConfigError("metrics: at least one metric is required")
    metrics, seen = [], set()
    for n, m in enumerate(raw):
        where = f"metrics[{n}]"
        if not isinstance(m, dict):
            raise BandConfigError(f"{where}: expected a mapping")
        unknown = set(m) - METRIC_KEYS
        if unknown:
            raise BandConfigError(f"{where}: unknown key(s) {sorted(unknown)}")
        missing = METRIC_REQUIRED - set(m)
        if missing:
            raise BandConfigError(f"{where}: missing key(s) {sorted(missing)}")
        mid = m["id"]
        if not isinstance(mid, str) or not mid.strip():
            raise BandConfigError(f"{where}.id: must be a non-empty string")
        if mid in seen:
            raise BandConfigError(f"{where}.id: duplicate metric id {mid!r}")
        seen.add(mid)
        if m["source"] not in KNOWN_SOURCES:
            raise BandConfigError(
                f"{where}.source: {m['source']!r} has no collector; known sources are {list(KNOWN_SOURCES)}")
        if m["direction"] not in DIRECTIONS:
            raise BandConfigError(f"{where}.direction: must be one of {list(DIRECTIONS)}")
        if not isinstance(m["required"], bool):
            raise BandConfigError(f"{where}.required: must be true or false")
        if not isinstance(m["description"], str) or not m["description"].strip():
            raise BandConfigError(f"{where}.description: must be a non-empty string")
        zvt = m.get("zero_variance_tier")
        if zvt is not None:
            if isinstance(zvt, bool) or not isinstance(zvt, int) or not 0 <= zvt <= max_tier:
                raise BandConfigError(f"{where}.zero_variance_tier: must be an integer in 0..{max_tier}")
        metrics.append({
            "id": mid, "source": m["source"], "description": m["description"],
            "direction": m["direction"], "required": m["required"],
            "zero_variance_tier": zvt,
        })
    return metrics


def validate(doc):
    """Return a checked config dict, or raise BandConfigError."""
    if not isinstance(doc, dict):
        raise BandConfigError("top level must be a mapping")
    unknown = set(doc) - set(TOP_KEYS)
    if unknown:
        raise BandConfigError(f"unknown top-level key(s) {sorted(unknown)}")
    missing = set(TOP_KEYS) - set(doc)
    if missing:
        raise BandConfigError(f"missing top-level key(s) {sorted(missing)}")
    for key, typ in TOP_KEYS.items():
        val = doc[key]
        if typ is bool:
            if not isinstance(val, bool):
                raise BandConfigError(f"{key}: must be true or false")
        elif typ is int:
            if isinstance(val, bool) or not isinstance(val, int):
                raise BandConfigError(f"{key}: must be an integer")
        elif not isinstance(val, typ):
            raise BandConfigError(f"{key}: must be a {typ.__name__}")
    if doc["version"] != SUPPORTED_VERSION:
        raise BandConfigError(
            f"version {doc['version']} is not supported by this detector (expected {SUPPORTED_VERSION})")
    if doc["window"] < 2:
        raise BandConfigError("window: must be >= 2")
    if doc["min_samples"] < 2:
        raise BandConfigError("min_samples: must be >= 2; a sigma needs at least two points")
    if doc["min_samples"] > doc["window"]:
        raise BandConfigError("min_samples: cannot exceed window, or no verdict is ever reachable")

    tiers = _check_tiers(doc["tiers"])
    max_tier = max(t["tier"] for t in tiers)
    if not 0 <= doc["zero_variance_default_tier"] <= max_tier:
        raise BandConfigError(f"zero_variance_default_tier: must be an integer in 0..{max_tier}")
    metrics = _check_metrics(doc["metrics"], max_tier)

    return {
        "version": doc["version"], "window": doc["window"], "min_samples": doc["min_samples"],
        "dedupe_by_tree": doc["dedupe_by_tree"],
        "baseline_requires_clean_tree": doc["baseline_requires_clean_tree"],
        "zero_variance_default_tier": doc["zero_variance_default_tier"],
        "tiers": tiers, "metrics": metrics,
        "metrics_by_id": {m["id"]: m for m in metrics},
    }


def load(path):
    """Read and validate. A config that cannot be read is not an empty config."""
    if not os.path.exists(path):
        raise BandConfigError(f"{path}: missing; the detector has no policy to apply")
    try:
        doc = yamlsub.load(path)
    except yamlsub.YamlSubsetError as exc:
        raise BandConfigError(f"{path}: {exc}") from exc
    except OSError as exc:
        raise BandConfigError(f"{path}: unreadable ({exc})") from exc
    return validate(doc)


# A value placed at exactly k standard deviations comes back from the arithmetic as
# k - 1e-16, so a bare `>=` puts an exactly-2-sigma observation in the 1-sigma band. This
# tolerance covers double-precision round-off and nothing else: it is nine orders of
# magnitude below the smallest gap between the tiers in bands.yaml, so it can move a
# verdict across a boundary only when the two are already numerically indistinguishable.
SIGMA_EPS = 1e-9


def tier_for(cfg, z):
    """Highest tier whose sigma threshold |z| meets. 0 when inside every band."""
    hit = 0
    for t in cfg["tiers"]:
        if abs(z) + SIGMA_EPS >= t["sigma"]:
            hit = t["tier"]
    return hit


def tier_spec(cfg, tier):
    for t in cfg["tiers"]:
        if t["tier"] == tier:
            return t
    return None
