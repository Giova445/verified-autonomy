import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAULTS = os.path.join(HERE, "faults")
FIXTURES = ["cli", "fastapi", "monorepo", "nextjs", "signin"]
RATE_LINE = 80.0
NOT_A_DEFECT = {"nj-29"}

PRODUCT_STATES = {
    "cli": {"loading": False, "empty": True, "error": True},
    "fastapi": {"loading": False, "empty": True, "error": True},
    "monorepo": {"loading": True, "empty": True, "error": False},
    "nextjs": {"loading": True, "empty": True, "error": False},
    "signin": {"loading": False, "empty": False, "error": True},
}

STATE_FAULTS = {
    "cli": {"empty": ["cli-16", "cli-31"], "error": ["cli-12"]},
    "fastapi": {
        "empty": ["fa-24", "fa-30", "fa-32"],
        "error": ["fa-05", "fa-11", "fa-15"],
        "shape": ["fa-31"],
    },
    "monorepo": {"loading": ["mr-07", "mr-14", "mr-26"], "empty": ["mr-17"]},
    "nextjs": {
        "loading": ["nj-05", "nj-13", "nj-22", "nj-31"],
        "empty": ["nj-06", "nj-27"],
    },
    "signin": {"error": ["si-10", "si-12"]},
}

WRONG_FIELD_CATEGORIES = ("wrong field displayed", "wrong field in search/filter")
Z95 = 1.96
VERDICT_WORDS = "holds|FAILS|NOT PROVEN|WRONG BUILD|CANNOT RUN|NO VERDICT|BLOCKED|REFUSED"


def load_manifests():
    out = {}
    for fixture in FIXTURES:
        with open(os.path.join(FAULTS, fixture, "manifest.json")) as handle:
            out[fixture] = json.load(handle)
    return out


def load_results(path):
    if os.path.isdir(path):
        path = os.path.join(path, "results.tsv")
    with open(path, newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle, delimiter="\t")}


def parse_g4(results_md):
    section = None
    kinds = {}
    per_fixture = {}
    with open(results_md) as handle:
        for line in handle:
            if line.startswith("## "):
                if line.startswith("## Missed faults"):
                    section = "missed"
                elif line.startswith("## No signal"):
                    section = "no_signal"
                else:
                    section = None
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if section and len(cells) > 2 and re.fullmatch(r"[a-z]+-\d+", cells[1]):
                kinds[cells[1]] = section
            if cells and cells[0] in FIXTURES and len(cells) >= 6 and cells[1].isdigit():
                per_fixture[cells[0]] = tuple(int(c) for c in cells[1:5])
    return kinds, per_fixture


def rate(caught, total):
    return 100.0 * caught / total if total else 0.0


def wilson(caught, total, z=Z95):
    if not total:
        return 0.0, 0.0
    p = caught / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return 100.0 * (centre - margin) / denom, 100.0 * (centre + margin) / denom


def tally(kinds):
    total = len(kinds)
    caught = sum(1 for k in kinds if k == "caught")
    missed = sum(1 for k in kinds if k == "missed")
    return total, caught, missed, total - caught - missed


def short(text, width):
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def verdict_words(detail):
    return re.findall(r"=(%s)(?= \| |$)" % VERDICT_WORDS, detail or "")


def state_map_digest():
    blob = json.dumps({"product_states": PRODUCT_STATES, "state_faults": STATE_FAULTS}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def split_population(entries):
    behaviour = [i for i, e in entries.items() if not e["breaks_run"] and i not in NOT_A_DEFECT]
    breaks = [i for i, e in entries.items() if e["breaks_run"]]
    return behaviour, breaks


def state_clause(fixture, kinds):
    rows = []
    for state, present in PRODUCT_STATES[fixture].items():
        if present:
            ids = STATE_FAULTS.get(fixture, {}).get(state, [])
            rows.append((state, ids, [i for i in ids if kinds.get(i) == "caught"]))
    if any(not ids for _, ids, _ in rows):
        return rows, None
    return rows, all(caught for _, _, caught in rows)


def wrong_field_clause(fixture, manifests, kinds):
    ids = [e["id"] for e in manifests[fixture] if e["category"] in WRONG_FIELD_CATEGORIES]
    caught = [i for i in ids if kinds.get(i) == "caught"]
    return ids, caught, (bool(caught) if ids else None)


def fixture_result(fixture, entries, manifests, behaviour, kinds):
    ids = [i for i in behaviour if entries[i]["fixture"] == fixture]
    caught = sum(1 for i in ids if kinds.get(i) == "caught")
    low, high = wilson(caught, len(ids))
    states, states_ok = state_clause(fixture, kinds)
    wf_ids, wf_caught, wf_ok = wrong_field_clause(fixture, manifests, kinds)
    rate_fails = high < RATE_LINE
    ok = None if states_ok is None or wf_ok is None else states_ok and wf_ok and not rate_fails
    return {"ids": ids, "caught": caught, "low": low, "high": high, "rate_fails": rate_fails, "states": states,
            "states_ok": states_ok, "wf_ids": wf_ids, "wf_caught": wf_caught, "wf_ok": wf_ok, "ok": ok}


def break_class(row):
    if row is None:
        return "no result"
    if row["kind"] == "missed":
        return "holds"
    if row["kind"] == "caught":
        return "FAILS-type"
    if (row.get("detail") or "").startswith("could not read"):
        return "no result"
    words = [w for w in verdict_words(row.get("detail")) if w != "holds"]
    return "CANNOT RUN" if words and all(w == "CANNOT RUN" for w in words) else "other"


def preregistered(entries, manifests, rows):
    kinds = {i: r["kind"] for i, r in rows.items()}
    behaviour, breaks = split_population(entries)
    missing = [i for i in behaviour + breaks if i not in rows]
    caught = sum(1 for i in behaviour if kinds.get(i) == "caught")
    low, high = wilson(caught, len(behaviour))
    pooled_ok = caught * 100 >= int(RATE_LINE) * len(behaviour)
    fixtures = {f: fixture_result(f, entries, manifests, behaviour, kinds) for f in FIXTURES}
    classes = {i: break_class(rows.get(i)) for i in breaks}
    not_passed = sum(1 for c in classes.values() if c not in ("holds", "no result"))
    counts = {c: sum(1 for v in classes.values() if v == c) for c in ("FAILS-type", "CANNOT RUN", "other", "holds", "no result")}
    if missing or any(f["ok"] is None for f in fixtures.values()):
        verdict = "NOT MEASURED"
    else:
        verdict = "MET" if pooled_ok and all(f["ok"] for f in fixtures.values()) else "NOT MET"
    return {"behaviour": behaviour, "breaks": breaks, "missing": missing, "caught": caught, "low": low, "high": high,
            "pooled_ok": pooled_ok, "fixtures": fixtures, "classes": classes, "not_passed": not_passed, "counts": counts,
            "secondary_ok": not_passed == len(breaks) and bool(breaks), "verdict": verdict}


def print_preregistered(result, digest):
    behaviour, fixtures = result["behaviour"], result["fixtures"]
    print("== PREREGISTERED (tests/gate0/G9-PREREGISTRATION.md) ==")
    print("population: %d behaviour faults (manifest breaks_run=false, without %s) + %d break faults (breaks_run=true, scored on the secondary line only)" % (
        len(behaviour), ",".join(sorted(NOT_A_DEFECT)), len(result["breaks"])))
    print("state map digest (sha256 of PRODUCT_STATES + STATE_FAULTS as json, sorted keys): %s" % digest)
    if result["missing"]:
        print("MISSING pass-1 results for %d scored faults: %s" % (len(result["missing"]), " ".join(result["missing"])))
    print("primary: pooled catch rate on behaviour faults %d/%d = %.1f%%, Wilson 95%% interval %.1f%% to %.1f%%, line %d%%: %s" % (
        result["caught"], len(behaviour), rate(result["caught"], len(behaviour)), result["low"], result["high"], RATE_LINE,
        "MET" if result["pooled_ok"] else "NOT MET"))
    for fixture in FIXTURES:
        f = fixtures[fixture]
        print("  -- %s: %d/%d = %.1f%%, Wilson 95%% %.1f%% to %.1f%%, rate rule (fails only if upper bound < %d%%): %s" % (
            fixture, f["caught"], len(f["ids"]), rate(f["caught"], len(f["ids"])), f["low"], f["high"], RATE_LINE,
            "FAILS" if f["rate_fails"] else "ok"))
        for state, ids, caught in f["states"]:
            print("       state %-8s %d of %d seeded faults caught (%s): %s" % (
                state, len(caught), len(ids), ", ".join(ids) or "none seeded",
                "ok" if caught else "NOT MET" if ids else "NOT MEASURED"))
        print("       wrong-field     %d of %d caught (%s): %s" % (
            len(f["wf_caught"]), len(f["wf_ids"]), ", ".join(f["wf_ids"]) or "none seeded",
            "ok" if f["wf_ok"] else "NOT MET" if f["wf_ids"] else "NOT MEASURED"))
        print("       fixture: %s" % ("MET" if f["ok"] else "NOT MET" if f["ok"] is False else "NOT MEASURED"))
    counts = result["counts"]
    print("SECONDARY build/start broken, not passed: %d/%d break faults (FAILS-type %d, CANNOT RUN %d, other non-holds %d, holds %d, no result %d): %s" % (
        result["not_passed"], len(result["breaks"]), counts["FAILS-type"], counts["CANNOT RUN"], counts["other"], counts["holds"],
        counts["no result"], "MET" if result["secondary_ok"] else "NOT MET"))
    for i in result["breaks"]:
        print("       %-8s %s" % (i, result["classes"][i]))
    reasons = []
    if not result["pooled_ok"]:
        reasons.append("pooled %.1f%% below %d%%" % (rate(result["caught"], len(behaviour)), RATE_LINE))
    for fixture in FIXTURES:
        f = fixtures[fixture]
        why = []
        if f["states_ok"] is False:
            why.append("state faults not caught: %s" % ",".join(s for s, _, caught in f["states"] if not caught))
        if f["wf_ok"] is False:
            why.append("no wrong-field fault caught")
        if f["rate_fails"]:
            why.append("rate upper bound %.1f%% < %d%%" % (f["high"], RATE_LINE))
        if why:
            reasons.append("%s (%s)" % (fixture, "; ".join(why)))
    detail = "pooled %d/%d = %.1f%% [Wilson 95%% %.1f to %.1f]; %s" % (
        result["caught"], len(behaviour), rate(result["caught"], len(behaviour)), result["low"], result["high"],
        "failing: " + ", ".join(reasons) if reasons else "all five fixtures satisfy the state, wrong-field and rate clauses")
    if result["missing"]:
        detail = "%d scored faults have no pass-1 result" % len(result["missing"])
    print("PREREGISTERED VERDICT: %s (%s)" % (result["verdict"], detail))


def fmt_cols(label, series):
    cells = []
    for name, kinds in series:
        total, caught, missed, nosig = tally(kinds)
        cells.append("%s n=%3d c=%3d m=%3d ns=%3d %5.1f%%" % (name, total, caught, missed, nosig, rate(caught, total)))
    return "  %-40s %s" % (label, "   ".join(cells))


def print_tables(title, names, series, entries, manifests):
    common = [i for i in entries if all(i in s for s in series)]
    behaviour = set(split_population(entries)[0])

    def row(label, ids):
        if ids:
            print(fmt_cols(label, [(n, [s[i] for i in ids]) for n, s in zip(names, series)]))

    print()
    print("== %s: per fixture (n faults, c caught, m missed, ns no signal; rate = caught / n) ==" % title)
    for fixture in FIXTURES:
        row(fixture, [i for i in common if entries[i]["fixture"] == fixture])
    row("all", common)
    row("all without %s" % ",".join(sorted(NOT_A_DEFECT)), [i for i in common if i not in NOT_A_DEFECT])
    print("  -- primary population (behaviour faults)")
    for fixture in FIXTURES:
        row(fixture, [i for i in common if i in behaviour and entries[i]["fixture"] == fixture])
    row("pooled", [i for i in common if i in behaviour])
    print()
    print("== %s: per category, per fixture ==" % title)
    for fixture in FIXTURES:
        print("  -- %s" % fixture)
        for cat in sorted({e["category"] for e in manifests[fixture]}):
            row(cat, [e["id"] for e in manifests[fixture] if e["category"] == cat and e["id"] in common])
    print()
    print("== %s: per category, all fixtures ==" % title)
    for cat in sorted({e["category"] for e in entries.values()}):
        row(cat, [i for i in common if entries[i]["category"] == cat])


def vector(row):
    return row.get("detail", "") if row else ""


def outcome_pairs(detail):
    return [tuple(part.rsplit("=", 1)) for part in (detail or "").split(" | ") if "=" in part]


def outcome_diff(left, right):
    before, after = dict(outcome_pairs(vector(left))), dict(outcome_pairs(vector(right)))
    names = list(after) + [n for n in before if n not in after]
    return ["%s: %s -> %s" % (n, before.get(n, "-"), after.get(n, "-")) for n in names if before.get(n) != after.get(n)], len(names)


def changed_ids(entries, left_kinds, right_kinds, left_rows=None, right_rows=None):
    out = []
    for i in entries:
        if i not in left_kinds or i not in right_kinds:
            continue
        moved = left_kinds[i] != right_kinds[i]
        if left_rows and right_rows and i in left_rows and i in right_rows:
            moved = moved or vector(left_rows[i]) != vector(right_rows[i])
        if moved:
            out.append(i)
    return out


def print_changed(title, left_name, right_name, ids, entries, left_kinds, right_kinds, left_rows=None, right_rows=None):
    print()
    print("== %s: verdict changed, %s -> %s: %d ==" % (title, left_name, right_name, len(ids)))
    for i in ids:
        e = entries[i]
        print("  %-8s %-5s [%s] %s" % (i, "break" if e["breaks_run"] else "live", e["category"], short(e["statement"], 110)))
        print("           %s: %s   ->   %s: %s" % (left_name, left_kinds[i], right_name, right_kinds[i]))
        if left_rows and right_rows and i in left_rows and i in right_rows:
            diff, count = outcome_diff(left_rows[i], right_rows[i])
            print("           outcomes that differ: %d of %d" % (len(diff), count))
            for line in diff:
                print("             %s" % short(line, 200))
        elif right_rows and i in right_rows:
            print("           %s: %s" % (right_name, short(vector(right_rows[i]), 200)))


def print_repeats(entries, rows, repeat_rows, first_rows, expected, behaviour):
    print()
    print("== repeats: every fault whose verdict differs from the first G9 run, run again ==")
    print("expected repeat set (%d): %s" % (len(expected), " ".join(expected) or "none"))
    not_run = [i for i in expected if i not in repeat_rows]
    if not_run:
        print("NOT REPEATED: %s" % " ".join(not_run))
    unstable = []
    for i in [i for i in entries if i in repeat_rows and i in rows]:
        a, b = rows[i], repeat_rows[i]
        same_kind, same_vector = a["kind"] == b["kind"], vector(a) == vector(b)
        if not same_vector:
            unstable.append(i)
        first = first_rows.get(i) if first_rows else None
        print("  %-8s first-G9 %-9s pass-1 %-9s repeat %-9s %s" % (
            i, first["kind"] if first else "-", a["kind"], b["kind"],
            "stable" if same_vector else "UNSTABLE (same classification, different outcome verdicts)" if same_kind else "UNSTABLE (classification differs)"))
        if not same_vector:
            print("           pass-1: %s" % short(vector(a), 200))
            print("           repeat: %s" % short(vector(b), 200))
    flipped = [i for i in unstable if rows[i]["kind"] != repeat_rows[i]["kind"]]
    print("repeated %d, stable %d, unstable %d (classification differs: %d)" % (
        len([i for i in entries if i in repeat_rows and i in rows]), len([i for i in entries if i in repeat_rows and i in rows]) - len(unstable),
        len(unstable), len(flipped)))
    lost = [i for i in flipped if i in behaviour and rows[i]["kind"] == "caught"]
    caught = sum(1 for i in behaviour if i in rows and rows[i]["kind"] == "caught") - len(lost)
    low, high = wilson(caught, len(behaviour))
    print("SENSITIVITY (not the verdict): pooled rate if pass-1 catches the repeat did not reproduce counted as not caught: %d/%d = %.1f%%, Wilson 95%% %.1f%% to %.1f%%" % (
        caught, len(behaviour), rate(caught, len(behaviour)), low, high))


def print_not_caught(entries, rows):
    print()
    print("== faults not caught in this run ==")
    for kind, title in (("missed", "missed (false PASS)"), ("no_signal", "no signal (counted as not caught)")):
        print()
        print("%s:" % title)
        for i in entries:
            if i in rows and rows[i]["kind"] == kind:
                e = entries[i]
                print("  %-8s %-5s [%s] %s" % (i, "break" if e["breaks_run"] else "live", e["category"], short(e["statement"], 110)))
                print("           %s" % short(vector(rows[i]), 230))


def read_timing(out_dir):
    timing = {}
    path = os.path.join(out_dir, "timing.txt")
    if os.path.exists(path):
        for line in open(path):
            key, _, value = line.partition(": ")
            timing[key] = value.strip()
    peaks = []
    base = os.path.join(out_dir, "baseline.tsv")
    if os.path.exists(base):
        with open(base, newline="") as handle:
            peaks = [int(r["peak_mb"]) for r in csv.DictReader(handle, delimiter="\t") if (r.get("peak_mb") or "").isdigit()]
    return timing, peaks


def main(argv):
    ap = argparse.ArgumentParser(prog="g9_report.py")
    ap.add_argument("out_dir")
    ap.add_argument("results_md", nargs="?", default=os.path.join(FAULTS, "RESULTS.md"))
    ap.add_argument("--first")
    ap.add_argument("--repeat")
    ap.add_argument("--hand-after")
    ap.add_argument("--print-repeat-set", action="store_true")
    args = ap.parse_args(argv[1:])
    manifests = load_manifests()
    entries = {e["id"]: dict(e, fixture=f) for f in FIXTURES for e in manifests[f]}
    rows = load_results(args.out_dir)
    first_rows = load_results(args.first) if args.first else None
    repeat_rows = load_results(args.repeat) if args.repeat else None
    hand_after_rows = load_results(args.hand_after) if args.hand_after else None
    kinds = {i: r["kind"] for i, r in rows.items()}
    first_kinds = {i: r["kind"] for i, r in first_rows.items()} if first_rows else None
    expected_repeat = changed_ids(entries, first_kinds, kinds, first_rows, rows) if first_rows else []

    if args.print_repeat_set:
        print(" ".join(expected_repeat))
        return 0

    g4_special, g4_table = parse_g4(args.results_md)
    g4 = {i: g4_special.get(i, "caught") for i in entries}
    for fixture in FIXTURES:
        got = tally([g4[e["id"]] for e in manifests[fixture]])
        if g4_table.get(fixture) != got:
            print("WARNING: RESULTS.md table for %s says %s but its faults list gives %s" % (fixture, g4_table.get(fixture), got))

    result = preregistered(entries, manifests, rows)
    timing, baseline_peaks = read_timing(args.out_dir)
    run_secs = sum(float(r["secs"]) for r in rows.values() if r.get("secs"))
    peak = max([int(r["peak_mb"]) for r in rows.values() if (r.get("peak_mb") or "").isdigit()] + baseline_peaks or [0])
    print("G9 REPORT from %s" % args.out_dir)
    print("faults in corpus: %d, with a saved result: %d" % (len(entries), sum(1 for i in entries if i in rows)))
    print("wall time of the run (baseline + faults): %s s; summed verify time of the faults: %.0f s; peak memory of any run (baseline included): %s MB" % (
        timing.get("wall_seconds_total", "unknown"), run_secs, peak))
    print()
    print_preregistered(result, state_map_digest())

    g9_names, g9_series = (["FIRST", "RERUN"], [first_kinds, kinds]) if first_kinds else (["RERUN"], [kinds])
    print_tables("G9 spec contracts" + (", first run vs rerun" if first_kinds else ""), g9_names, g9_series, entries, manifests)
    g4_names, g4_series = (["BEFORE", "AFTER"], [g4, {i: r["kind"] for i, r in hand_after_rows.items()}]) if hand_after_rows else (["BEFORE"], [g4])
    print_tables("G4 hand-written contracts" + (", before vs after the probe fix" if hand_after_rows else ""), g4_names, g4_series, entries, manifests)

    if first_kinds:
        print_changed("G9", "FIRST", "RERUN", expected_repeat, entries, first_kinds, kinds, first_rows, rows)
    if hand_after_rows:
        after_kinds = {i: r["kind"] for i, r in hand_after_rows.items()}
        print_changed("G4", "BEFORE", "AFTER", changed_ids(entries, g4, after_kinds), entries, g4, after_kinds, None, hand_after_rows)
    if repeat_rows is not None:
        print_repeats(entries, rows, repeat_rows, first_rows, expected_repeat, result["behaviour"])
    print_not_caught(entries, rows)

    summary = {
        "verdict": result["verdict"],
        "pooled": {"caught": result["caught"], "total": len(result["behaviour"]), "rate": round(rate(result["caught"], len(result["behaviour"])), 1),
                   "wilson95": [round(result["low"], 1), round(result["high"], 1)]},
        "fixtures": {f: {"caught": r["caught"], "total": len(r["ids"]), "wilson95": [round(r["low"], 1), round(r["high"], 1)],
                         "states_ok": r["states_ok"], "wrong_field_ok": r["wf_ok"], "rate_fails": r["rate_fails"], "ok": r["ok"]}
                     for f, r in result["fixtures"].items()},
        "secondary": {"not_passed": result["not_passed"], "total": len(result["breaks"]), "counts": result["counts"], "classes": result["classes"]},
        "state_map_digest": state_map_digest(),
        "repeat_set": expected_repeat,
        "kinds": kinds,
    }
    with open(os.path.join(args.out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
