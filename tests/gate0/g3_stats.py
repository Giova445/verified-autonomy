import json
import os
import statistics
import sys
from collections import Counter

COLUMNS = ("fixture", "run", "rc", "wall", "peak", "built", "load", "verdicts", "bad", "left")
ALWAYS_SHOWN = ("FAILS", "CANNOT RUN", "NO VERDICT")
EXCERPT_LINES = 14
SERVER_LINES = 10
WIDTH = 220


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def evidence(repo, name):
    return os.path.join(repo, ".claude", "evidence", name)


def product_outcomes(repo):
    data = load_json(evidence(repo, "product.json"))
    return data.get("outcomes") if isinstance(data, dict) else None


def declared_outcomes(repo):
    data = load_json(os.path.join(repo, ".claude", "acceptance.json"))
    return len(data["outcomes"]) if isinstance(data, dict) else 0


def classify(repo, rc):
    outcomes = product_outcomes(repo)
    if not outcomes:
        return [], ["NO RESULT"]
    verdicts = [str(o.get("verdict", "?")) for o in outcomes]
    bad = [v for v in verdicts if v != "holds"]
    if len(verdicts) != declared_outcomes(repo):
        bad.append("MISSING OUTCOMES")
    if not bad and rc != 0:
        bad.append("EXIT %d" % rc)
    return verdicts, bad


def trim(text):
    return text if len(text) <= WIDTH else text[:WIDTH] + "..."


def excerpt(repo, out):
    outcomes = product_outcomes(repo)
    if not outcomes:
        print("        no product.json was written; the runner said:")
        for line in read_lines(out)[-EXCERPT_LINES:]:
            print("          | " + trim(line))
    for o in outcomes or []:
        if o.get("verdict") == "holds":
            continue
        print("        outcome '%s': %s" % (o.get("name"), o.get("verdict")))
        print("          detail: " + trim(str(o.get("detail"))))
        lines = read_lines(os.path.join(repo, o["log"])) if o.get("log") else []
        for line in [l for l in lines if l.strip()][-EXCERPT_LINES:]:
            print("          | " + trim(line))
    logs = sorted(f for f in os.listdir(evidence(repo, "")) if f.startswith("server-") and f.endswith(".log")) \
        if os.path.isdir(evidence(repo, "")) else []
    for name in logs:
        print("        %s (last %d lines):" % (name, SERVER_LINES))
        for line in [l for l in read_lines(evidence(repo, name)) if l.strip()][-SERVER_LINES:]:
            print("          | " + trim(line))


def rows_for(path, fixture):
    rows = []
    for line in read_lines(path):
        cells = line.split("\t")
        if len(cells) == len(COLUMNS) and cells[0] == fixture:
            rows.append(dict(zip(COLUMNS, cells)))
    return rows


def number(cell):
    try:
        return float(cell)
    except ValueError:
        return None


def facts(rows):
    walls = [number(r["wall"]) for r in rows if number(r["wall"]) is not None]
    peaks = [(number(r["peak"]), r["run"]) for r in rows if number(r["peak"]) is not None]
    loads = [number(r["load"]) for r in rows if number(r["load"]) is not None]
    by_verdict = Counter(v for r in rows if r["bad"] != "-" for v in r["bad"].split(","))
    peak_max = max(peaks, key=lambda p: p[0]) if peaks else (None, "-")
    return {
        "runs": len(rows),
        "false_runs": sum(1 for r in rows if r["bad"] != "-"),
        "holds": sum(1 for r in rows if r["bad"] == "-"),
        "by_verdict": by_verdict,
        "walls": walls,
        "loads": loads,
        "peak_max": peak_max[0],
        "peak_run": peak_max[1],
        "no_meter": sum(1 for r in rows if number(r["peak"]) is None),
        "leaks": [(r["run"], r["left"]) for r in rows if r["left"] != "nothing"],
        "rebuilt": [r["run"] for r in rows if r["built"] == "ran"],
        "builds": any(r["built"] != "n/a" for r in rows),
    }


def spread(values, unit):
    if not values:
        return "not measured"
    return "min %.1f%s, median %.1f%s, max %.1f%s" % (
        min(values), unit, statistics.median(values), unit, max(values), unit)


def summary(rows):
    f = facts(rows)
    counts = f["by_verdict"]
    shown = list(ALWAYS_SHOWN) + sorted(k for k in counts if k not in ALWAYS_SHOWN)
    print("        runs %d, holds %d, false FAIL runs %d" % (f["runs"], f["holds"], f["false_runs"]))
    print("        false FAILs by verdict (per outcome): %s" % ", ".join("%s %d" % (k, counts.get(k, 0)) for k in shown))
    print("        wall: %s" % spread(f["walls"], " s"))
    print("        peak MB (verify meter): max %s at run %s, runs without a reading %d" % (
        "%.0f" % f["peak_max"] if f["peak_max"] is not None else "not measured", f["peak_run"], f["no_meter"]))
    print("        load average (1 min) at run start: %s" % spread(f["loads"], ""))
    if f["builds"]:
        print("        build ran on run(s): %s" % (", ".join(f["rebuilt"]) or "none"))


def fact(rows, name, budget):
    f = facts(rows)
    if name == "runs":
        return f["runs"]
    if name == "false_runs":
        return f["false_runs"]
    if name == "peak":
        if f["no_meter"]:
            return "%d run(s) without a meter reading" % f["no_meter"]
        if f["peak_max"] >= budget:
            return "%.0f MB at run %s" % (f["peak_max"], f["peak_run"])
        return "within"
    if name == "leaks":
        return "nothing" if not f["leaks"] else "; ".join("run %s: %s" % l for l in f["leaks"])
    raise SystemExit("unknown fact %s" % name)


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "classify":
        verdicts, bad = classify(argv[2], int(argv[3]))
        print("\t".join([",".join(verdicts) or "-", ",".join(bad) or "-"]))
    elif command == "excerpt":
        excerpt(argv[2], argv[3])
    elif command == "summary":
        summary(rows_for(argv[2], argv[3]))
    elif command == "fact":
        print(fact(rows_for(argv[2], argv[3]), argv[4], float(argv[5])))
    else:
        print("usage: g3_stats.py {classify REPO RC | excerpt REPO OUT | summary TSV FIXTURE | fact TSV FIXTURE NAME BUDGET}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
