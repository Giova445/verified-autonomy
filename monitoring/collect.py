#!/usr/bin/env python3
"""collect.py — run this repo's suite once and record what it measured.

One invocation produces one observation. Observations are appended (never rewritten) to
monitoring/history/observations.jsonl, which is what makes the rolling window in
monitoring/detect.py real rather than assumed.

THREE RULES, ALL OF WHICH ARE FAIL-CLOSED.

1. A metric that could not be measured is `error` or `unavailable`. It is never 0, and it
   is never omitted. "The eval harness is absent" and "the eval harness scored 0" are
   different facts, and a detector that cannot tell them apart is worse than none.
2. Output formats are parsed strictly. If selftest.sh stops printing its summary line, or
   validate.py grows a validator this file has not been told about, collection FAILS. A
   parser that shrugs and returns what it could find turns a format change into a silent
   metric change, and the band then tracks a different quantity under the same name.
3. Every record binds to a commit and to a digest of the working tree, so a measurement
   can be traced to the exact source that produced it.

Usage:
    python3 monitoring/collect.py                 # measure, print the record, write nothing
    python3 monitoring/collect.py --append        # measure and append to the history file
    python3 monitoring/collect.py --skip bench    # debugging; skipped metrics are marked
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from datetime import datetime, timezone

SCHEMA = "verified-autonomy/monitoring/observation@1"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
HISTORY = os.path.join(HERE, "history", "observations.jsonl")
TIMEOUT = 1800

# Declared here, NOT read back from validate.py's output. If that script gains or loses a
# validator, the meaning of structure.nonratcheted_findings changes, and this list makes
# that turn collection red instead of quietly redefining the metric.
EXPECTED_VALIDATORS = ("frontmatter", "links", "manifest", "duplicates")
RATCHETED_VALIDATORS = ("links",)


class CollectError(RuntimeError):
    pass


# --------------------------------------------------------------------------- parsers
# Kept pure and text-in so monitoring/selftest.py can feed them fixtures, including
# deliberately broken ones, without running the 50-second suite.

def parse_selftest(text):
    """-> {'checks_total': int, 'checks_failed': int, 'subsuite_checks_total': int}"""
    total = failed = None
    subsuite, seen_lines = 0, 0
    for line in text.splitlines():
        if line.startswith("SELF-TEST PASSED"):
            m = re.search(r"\((\d+) checks\)", line)
            if not m:
                raise CollectError("selftest: PASSED summary line without a check count")
            total, failed = int(m.group(1)), 0
            continue
        if line.startswith("SELF-TEST FAILED"):
            m = re.search(r"\((\d+) of (\d+) checks\)", line)
            if not m:
                raise CollectError("selftest: FAILED summary line without a `N of M checks` count")
            failed, total = int(m.group(1)), int(m.group(2))
            continue
        m = re.search(r"\((\d+) checks\)", line)
        if m:
            subsuite += int(m.group(1))
            seen_lines += 1
    if total is None:
        raise CollectError("selftest: no SELF-TEST summary line; refusing to guess a count")
    if seen_lines == 0:
        raise CollectError("selftest: no sub-suite check counts; the suite reported nothing")
    return {"checks_total": total, "checks_failed": failed,
            "subsuite_checks_total": subsuite}


def parse_bench(raw):
    """-> {'cases','recall','specificity','fpr'} from bench.sh's JSON output."""
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise CollectError(f"bench: output is not JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise CollectError("bench: JSON output is not an object")
    for key in ("tp", "fp", "tn", "fn"):
        if not isinstance(doc.get(key), int):
            raise CollectError(f"bench: missing or non-integer confusion cell {key!r}")
    cases = doc["tp"] + doc["fp"] + doc["tn"] + doc["fn"]
    if cases == 0:
        raise CollectError("bench: zero cases scored; an empty corpus is not a clean run")
    out = {"cases": cases}
    for key in ("recall", "specificity", "fpr"):
        val = doc.get(key)
        if val is None:
            raise CollectError(f"bench: {key} is null; one class of the corpus is empty")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise CollectError(f"bench: {key} is not a number")
        out[key] = float(val)
    return out


def parse_structure(text):
    """-> {'links_findings': int, 'nonratcheted_findings': int}"""
    found = {}
    for line in text.splitlines():
        m = re.match(r"^ {2}([a-z_]+)\s+(\d+) finding\(s\)", line)
        if m:
            name = m.group(1)
            if name in found:
                raise CollectError(f"structure: validator {name!r} reported twice")
            found[name] = int(m.group(2))
    if set(found) != set(EXPECTED_VALIDATORS):
        raise CollectError(
            "structure: validator set changed — expected "
            f"{sorted(EXPECTED_VALIDATORS)}, saw {sorted(found)}. "
            "structure.nonratcheted_findings would silently mean something else; "
            "update EXPECTED_VALIDATORS in monitoring/collect.py on purpose.")
    return {
        "links_findings": found["links"],
        "nonratcheted_findings": sum(v for k, v in found.items()
                                     if k not in RATCHETED_VALIDATORS),
    }


def parse_evals(raw):
    """-> {'pass_rate': float} from a JSON object carrying passed/total or pass_rate."""
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise CollectError(f"evals: output is not JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise CollectError("evals: JSON output is not an object")
    if isinstance(doc.get("pass_rate"), (int, float)) and not isinstance(doc.get("pass_rate"), bool):
        return {"pass_rate": float(doc["pass_rate"])}
    passed, total = doc.get("passed"), doc.get("total")
    if isinstance(passed, int) and isinstance(total, int) and not isinstance(passed, bool) and total > 0:
        return {"pass_rate": passed / total}
    raise CollectError("evals: JSON carries neither a numeric pass_rate nor integer passed/total")


# --------------------------------------------------------------------------- runners

def _run(cmd, cwd, env=None):
    e = dict(os.environ)
    e.pop("CLAUDE_PLUGIN_ROOT", None)
    e.update(env or {})
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CollectError(f"{cmd[0]}: could not run ({exc})") from exc
    return p.returncode, (p.stdout or "") + (p.stderr or ""), round(time.time() - t0, 1)


def source_selftest(root):
    path = os.path.join(root, "selftest.sh")
    if not os.path.exists(path):
        raise CollectError("selftest.sh: missing")
    rc, out, secs = _run(["bash", path], root, {"CLAUDE_PROJECT_DIR": root})
    return parse_selftest(out), rc, secs


def source_bench(root):
    path = os.path.join(root, "benchmark", "gates", "bench.sh")
    if not os.path.exists(path):
        raise CollectError("benchmark/gates/bench.sh: missing")
    out_json = os.path.join(root, "monitoring", ".bench.json")
    try:
        rc, _, secs = _run(["bash", path, out_json], root)
        if not os.path.exists(out_json):
            raise CollectError("bench: wrote no JSON output")
        with open(out_json, encoding="utf-8") as fh:
            vals = parse_bench(fh.read())
    finally:
        if os.path.exists(out_json):
            os.remove(out_json)
    return vals, rc, secs


def source_structure(root):
    path = os.path.join(root, "benchmark", "structure", "validate.py")
    if not os.path.exists(path):
        raise CollectError("benchmark/structure/validate.py: missing")
    rc, out, secs = _run([sys.executable, path], root)
    return parse_structure(out), rc, secs


def source_evals(root):
    """The one adapter whose interface is unconfirmed — see monitoring/README.md.

    Two documented probes, in order, then `unavailable`. Never a number this file made up.
    """
    path = os.path.join(root, "evals", "run.py")
    if not os.path.exists(path):
        raise CollectError("UNAVAILABLE evals/run.py is not present in this repo")
    out_json = os.path.join(root, "monitoring", ".evals.json")
    try:
        rc, out, secs = _run([sys.executable, path, "--json", out_json], root)
        if os.path.exists(out_json):
            with open(out_json, encoding="utf-8") as fh:
                return parse_evals(fh.read()), rc, secs
        blocks = re.findall(r"\{.*?\}", out, re.S)
        for block in reversed(blocks):
            try:
                return parse_evals(block), rc, secs
            except CollectError:
                continue
        raise CollectError(
            "UNAVAILABLE evals/run.py ran but emitted no JSON this collector understands "
            "(tried --json <file>, then the last JSON object on stdout)")
    finally:
        if os.path.exists(out_json):
            os.remove(out_json)


SOURCES = {"selftest": source_selftest, "bench": source_bench,
           "structure": source_structure, "evals": source_evals}


# --------------------------------------------------------------------------- provenance

def tree_digest(commit, porcelain):
    """Identity of an exact source state. For a CLEAN tree `porcelain` is empty, so the
    digest is a pure function of the commit and monitoring/detect.py can recompute and
    check it without a checkout. That is the one integrity check on this file that a
    hand-written row has to get right rather than merely look plausible."""
    return hashlib.sha256((commit + "\n" + porcelain).encode()).hexdigest()[:16]


def git_provenance(root):
    def git(*args):
        p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
        if p.returncode != 0:
            raise CollectError(f"git {' '.join(args)}: failed ({p.stderr.strip()})")
        return p.stdout
    commit = git("rev-parse", "HEAD").strip()
    porcelain = git("status", "--porcelain")
    return {"commit": commit, "dirty": bool(porcelain.strip()),
            "tree_digest": tree_digest(commit, porcelain)}


def collect(root, config_metrics, skip=()):
    """Measure every source the metric list needs. Returns an observation record."""
    wanted, by_source = {}, {}
    for m in config_metrics:
        by_source.setdefault(m["source"], []).append(m["id"])
        wanted[m["id"]] = m["source"]

    metrics, sources = {}, {}
    for source, ids in sorted(by_source.items()):
        if source in skip:
            sources[source] = {"status": "skipped"}
            for mid in ids:
                metrics[mid] = {"status": "skipped", "reason": "--skip"}
            continue
        if source not in SOURCES:
            sources[source] = {"status": "error", "reason": "no collector"}
            for mid in ids:
                metrics[mid] = {"status": "error", "reason": f"no collector for source {source!r}"}
            continue
        try:
            vals, rc, secs = SOURCES[source](root)
        except CollectError as exc:
            msg = str(exc)
            # UNAVAILABLE marks "this thing is not here", as distinct from "it is here and
            # it broke". Both refuse to produce a number; only the second is an error.
            status = "unavailable" if msg.startswith("UNAVAILABLE") else "error"
            reason = msg[len("UNAVAILABLE "):] if status == "unavailable" else msg
            sources[source] = {"status": status, "reason": reason}
            for mid in ids:
                metrics[mid] = {"status": status, "reason": reason}
            continue
        sources[source] = {"status": "ok", "exit_code": rc, "seconds": secs}
        for mid in ids:
            key = mid.split(".", 1)[1]
            if key not in vals:
                metrics[mid] = {"status": "error",
                                "reason": f"source {source!r} produced no field {key!r}"}
            else:
                metrics[mid] = {"status": "ok", "value": vals[key]}

    rec = {"schema": SCHEMA,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "synthetic": False}
    rec.update(git_provenance(root))
    rec["sources"] = sources
    rec["metrics"] = metrics
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="record one control-band observation")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--config", default=None, help="bands.yaml (default: <root>/bands.yaml)")
    ap.add_argument("--history", default=None, help="observations.jsonl to append to")
    ap.add_argument("--append", action="store_true", help="append the record to the history file")
    ap.add_argument("--skip", action="append", default=[], metavar="SOURCE")
    args = ap.parse_args(argv)

    sys.path.insert(0, HERE)
    import bandconf
    root = os.path.abspath(args.root)
    cfg_path = args.config or os.path.join(root, "bands.yaml")
    try:
        cfg = bandconf.load(cfg_path)
    except bandconf.BandConfigError as exc:
        print(f"collect: {exc}", file=sys.stderr)
        return 2

    rec = collect(root, cfg["metrics"], skip=set(args.skip))
    line = json.dumps(rec, sort_keys=True)
    print(line)

    if args.append:
        hist = args.history or HISTORY
        os.makedirs(os.path.dirname(hist), exist_ok=True)
        with open(hist, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(f"collect: appended to {hist}", file=sys.stderr)

    broken = [m for m, v in rec["metrics"].items() if v["status"] == "error"]
    if broken:
        print(f"collect: {len(broken)} metric(s) errored: {sorted(broken)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
