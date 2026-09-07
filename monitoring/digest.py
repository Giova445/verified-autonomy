#!/usr/bin/env python3
"""Read the observation history and say what it shows: what crashed, what is degrading,
what cannot be measured at all, and what got slower.

WHY THIS IS SEPARATE FROM detect.py

`detect.py` answers one narrow question per metric — is the latest value outside its band?
It is deliberately silent about everything else, and it refuses to answer at all on short
history. That is right for a control-band detector and useless for the question a person
actually asks after a run: *what should I fix next?*

This reads the same `observations.jsonl` and answers that. It is a REPORTER, not a gate:
it exits 0 whatever it finds, except when the history itself is unreadable. Nothing gates
on its output, so nothing is tempted to suppress a finding to keep a build green.

WHAT IT WILL NOT DO

- Compute a trend from one observation. Two points are a line, not a trend; one point is
  not even that. Sections that need history say how many records they needed and stop.
- Attribute a duration change to a cause. It reports that `selftest` went 40s -> 70s. It
  does not guess why, because the record does not carry why.
- Treat `unavailable` as `ok`. A metric nothing can read is the most actionable line in
  the report, not an absence to skip over — every observation before 2026-09-07 recorded
  `evals.pass_rate: unavailable`, and nothing surfaced it until this file existed.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HISTORY = os.path.join(HERE, "history", "observations.jsonl")

# A duration change smaller than this is noise on a laptop that also runs a browser.
# Stated as a judgment number with no measurement behind it, per the same disclosure
# bands.yaml makes about its own tier thresholds.
SLOWER_FACTOR = 1.5
SLOWER_FLOOR_S = 5.0


def load(path):
    """Records oldest-first. A malformed line is a finding, never a skipped line."""
    if not os.path.exists(path):
        raise SystemExit(f"digest: no history at {path}")
    out, bad = [], []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError as exc:
                bad.append(f"line {n}: {exc}")
    return out, bad


def _metric(rec, name):
    return (rec.get("metrics") or {}).get(name) or {}


def _sources(rec):
    return rec.get("sources") or {}


def report(records, bad_lines):
    """Return (lines, counts). Pure: takes parsed records, returns text."""
    out = []
    n = len(records)
    counts = {"crashed": 0, "unavailable": 0, "moved": 0, "slower": 0, "malformed": len(bad_lines)}

    out.append(f"observations: {n}")
    if bad_lines:
        out.append(f"  MALFORMED history lines ({len(bad_lines)}) — these were not parsed:")
        out += [f"    {b}" for b in bad_lines]
    if not n:
        out.append("  nothing to report. Seed history with:")
        out.append("    python3 monitoring/collect.py --append")
        return out, counts

    latest = records[-1]
    out.append(f"latest: {latest.get('ts')}  commit {str(latest.get('commit'))[:7]}"
               f"  dirty={latest.get('dirty')}  synthetic={latest.get('synthetic')}")

    # ---- what crashed, in the latest run
    out.append("")
    out.append("CRASHED OR ERRORED (latest run)")
    crashed = [(k, v) for k, v in sorted(_sources(latest).items())
               if v.get("status") == "error" or (v.get("exit_code") not in (0, None))]
    for k, v in crashed:
        counts["crashed"] += 1
        out.append(f"  {k}: status={v.get('status')} exit={v.get('exit_code')}"
                   f" {v.get('reason', '')}".rstrip())
    if not crashed:
        out.append("  none")

    # ---- what cannot be measured at all
    out.append("")
    out.append("UNAVAILABLE — cannot be measured, so no band can ever fire on it")
    unavail = [(k, v) for k, v in sorted(latest.get("metrics", {}).items())
               if v.get("status") == "unavailable"]
    for k, v in unavail:
        counts["unavailable"] += 1
        out.append(f"  {k}")
        out.append(f"    reason: {v.get('reason', '(none recorded)')}")
    if not unavail:
        out.append("  none — every configured metric produced a value")

    # ---- what moved
    out.append("")
    if n < 2:
        out.append(f"MOVEMENT — needs 2 observations, have {n}. Not computed.")
    else:
        out.append("MOVEMENT since the previous observation")
        prev = records[-2]
        keys = sorted(set(latest.get("metrics", {})) | set(prev.get("metrics", {})))
        moved = []
        for k in keys:
            a, b = _metric(prev, k), _metric(latest, k)
            if a.get("status") != "ok" or b.get("status") != "ok":
                if a.get("status") != b.get("status"):
                    moved.append(f"  {k}: status {a.get('status')} -> {b.get('status')}")
                continue
            if a.get("value") != b.get("value"):
                moved.append(f"  {k}: {a.get('value')} -> {b.get('value')}")
        counts["moved"] = len(moved)
        out += moved or ["  nothing changed"]

    # ---- what got slower
    out.append("")
    if n < 2:
        out.append(f"DURATION — needs 2 observations, have {n}. Not computed.")
    else:
        out.append(f"DURATION (flagged at >{SLOWER_FACTOR}x and >{SLOWER_FLOOR_S}s)")
        prev = records[-2]
        slower = []
        for k in sorted(_sources(latest)):
            a = (_sources(prev).get(k) or {}).get("seconds")
            b = (_sources(latest).get(k) or {}).get("seconds")
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a <= 0:
                continue
            if b >= SLOWER_FLOOR_S and b / a >= SLOWER_FACTOR:
                slower.append(f"  {k}: {a:.1f}s -> {b:.1f}s ({b / a:.1f}x)")
        counts["slower"] = len(slower)
        out += slower or ["  nothing materially slower"]

    # ---- what to fix, ordered
    out.append("")
    out.append("WHAT TO IMPROVE, most actionable first")
    todo = []
    todo += [f"  fix the crash in '{k}' (exit {v.get('exit_code')})" for k, v in crashed]
    todo += [f"  make '{k}' measurable — {v.get('reason', '')[:90]}" for k, v in unavail]
    if counts["slower"]:
        todo.append(f"  investigate {counts['slower']} source(s) that got materially slower")
    if n < 3:
        todo.append(f"  accumulate history: {n} observation(s); "
                    f"detect.py needs more before any band can fire")
    out += todo or ["  nothing outstanding in this history"]
    return out, counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="report what the observation history shows")
    ap.add_argument("--history", default=HISTORY)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    records, bad = load(args.history)
    lines, _ = report(records, bad)
    print("\n".join(lines))
    return 0


# --------------------------------------------------------------------------- controls
# Hermetic: every control builds records in memory and calls report(). No repo copy, no
# subprocess -- the lesson from playbook-coverage.py, whose first controls copied the tree
# and took the machine to load average 39.
#
# Each control requires the finding that NAMES its break. Counting lines is not enough: a
# break that swaps one line for another leaves the count unchanged.
EXPECTED_CONTROLS = {
    "crash-surfaced", "unavailable-surfaced", "movement-needs-two", "regression-surfaced",
    "slower-surfaced", "malformed-not-skipped", "clean-history-says-so",
}


def _rec(ts, metrics=None, sources=None, **kw):
    base = {"ts": ts, "commit": "0" * 40, "dirty": False, "synthetic": False,
            "metrics": metrics or {}, "sources": sources or {}}
    base.update(kw)
    return base


OK = lambda v: {"status": "ok", "value": v}


def self_test():
    print("digest — controls\n")
    results, n, seen = [], 0, set()

    def check(name, records, bad, token, want=True):
        nonlocal n
        n += 1
        seen.add(name.split(" (")[0])
        text = "\n".join(report(records, bad)[0])
        hit = token in text
        ok = hit is want
        results.append(ok)
        verb = "surfaces" if want else "does NOT claim"
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {verb} {token!r}")
        if not ok:
            print(f"       --- report was ---\n{text}\n       ---")

    # A crashed source must be named with its exit code, not folded into a pass.
    check("crash-surfaced",
          [_rec("t1", sources={"bench": {"status": "error", "exit_code": 2}})],
          [], "bench: status=error exit=2")

    # An unmeasurable metric is the most actionable line, not an absence.
    check("unavailable-surfaced",
          [_rec("t1", metrics={"evals.pass_rate": {"status": "unavailable",
                                                   "reason": "no --json flag"}})],
          [], "make 'evals.pass_rate' measurable")

    # One observation must not yield a trend. This is the vacuity guard: a digest that
    # reports movement from a single record is inventing the comparison.
    check("movement-needs-two", [_rec("t1", metrics={"bench.recall": OK(1.0)})], [],
          "MOVEMENT — needs 2 observations, have 1. Not computed.")

    # A real regression between two observations must be named with both values.
    check("regression-surfaced",
          [_rec("t1", metrics={"bench.recall": OK(1.0)}),
           _rec("t2", metrics={"bench.recall": OK(0.8)})],
          [], "bench.recall: 1.0 -> 0.8")

    # A source that doubled in wall-clock is reported; a small change is not.
    check("slower-surfaced",
          [_rec("t1", sources={"selftest": {"status": "ok", "exit_code": 0, "seconds": 20.0}}),
           _rec("t2", sources={"selftest": {"status": "ok", "exit_code": 0, "seconds": 70.0}})],
          [], "selftest: 20.0s -> 70.0s (3.5x)")
    check("slower-surfaced (noise not flagged)",
          [_rec("t1", sources={"selftest": {"status": "ok", "exit_code": 0, "seconds": 20.0}}),
           _rec("t2", sources={"selftest": {"status": "ok", "exit_code": 0, "seconds": 22.0}})],
          [], "20.0s -> 22.0s", want=False)

    # A history line that does not parse is a finding. Silently skipping it would let a
    # corrupted record read as a shorter, healthier history.
    check("malformed-not-skipped", [_rec("t1")], ["line 4: bad json"],
          "MALFORMED history lines (1)")

    # And the negative direction: a clean two-record history must not manufacture findings.
    clean = [_rec("t1", metrics={"bench.recall": OK(1.0)},
                  sources={"bench": {"status": "ok", "exit_code": 0, "seconds": 10.0}}),
             _rec("t2", metrics={"bench.recall": OK(1.0)},
                  sources={"bench": {"status": "ok", "exit_code": 0, "seconds": 10.0}})]
    check("clean-history-says-so", clean, [], "nothing changed")
    check("clean-history-says-so (no crash claimed)", clean, [], "status=error", want=False)

    # The control NAMES are declared in EXPECTED_CONTROLS above, independently of the
    # calls below. Without this, deleting a check() call deletes its own requirement and
    # the suite reports a smaller green -- the expectation-derived-from-subject defect
    # this repo has now hit four times (a25e83d, and the three registries fixed with it).
    missing = EXPECTED_CONTROLS - seen
    extra = seen - EXPECTED_CONTROLS
    if missing or extra:
        results.append(False)
        print(f"\n  !! CONTROL SET CHANGED: missing {sorted(missing) or 'none'}, "
              f"unexpected {sorted(extra) or 'none'}")
    else:
        print(f"\n  control set matches EXPECTED_CONTROLS ({len(EXPECTED_CONTROLS)} names)")

    print(f"\n  digest ({n} checks)")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
