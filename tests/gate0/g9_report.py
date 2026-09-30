import csv
import json
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


def load_manifests():
    out = {}
    for fixture in FIXTURES:
        with open(os.path.join(FAULTS, fixture, "manifest.json")) as handle:
            out[fixture] = json.load(handle)
    return out


def load_spec_results(out_dir):
    path = os.path.join(out_dir, "results.tsv")
    rows = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows[row["id"]] = row
    return rows


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


def tally(kinds):
    total = len(kinds)
    caught = sum(1 for k in kinds if k == "caught")
    missed = sum(1 for k in kinds if k == "missed")
    return total, caught, missed, total - caught - missed


def fmt_row(label, spec, hand):
    st, sc, sm, sn = tally(spec)
    ht, hc, hm, hn = tally(hand)
    return "  %-40s SPEC %3d faults %3d caught %3d missed %3d no-signal %5.1f%%   HAND %3d caught %3d missed %3d no-signal %5.1f%%" % (
        label, st, sc, sm, sn, rate(sc, st), hc, hm, hn, rate(hc, ht))


def short(text, width):
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def kind_of(spec_rows, fault_id):
    row = spec_rows.get(fault_id)
    return row["kind"] if row else None


def main(argv):
    if len(argv) < 2:
        print("usage: g9_report.py G9_OUT [RESULTS.md]")
        return 2
    out_dir = argv[1]
    results_md = argv[2] if len(argv) > 2 else os.path.join(FAULTS, "RESULTS.md")
    manifests = load_manifests()
    spec_rows = load_spec_results(out_dir)
    g4_special, g4_table = parse_g4(results_md)

    entries = {}
    for fixture in FIXTURES:
        for e in manifests[fixture]:
            entries[e["id"]] = dict(e, fixture=fixture)

    g4 = {fid: g4_special.get(fid, "caught") for fid in entries}
    for fixture in FIXTURES:
        got = tally([g4[e["id"]] for e in manifests[fixture]])
        if g4_table.get(fixture) != got:
            print("WARNING: RESULTS.md table for %s says %s but its faults list gives %s" % (fixture, g4_table.get(fixture), got))

    missing = [fid for fid in entries if fid not in spec_rows]
    measured = not missing
    spec = {fid: spec_rows[fid]["kind"] for fid in entries if fid in spec_rows}

    print("G9 REPORT from %s" % out_dir)
    print("faults in corpus: %d, with a saved SPEC result: %d%s" % (
        len(entries), len(spec), "" if measured else "  MISSING: %s" % " ".join(missing)))
    timing = {}
    timing_path = os.path.join(out_dir, "timing.txt")
    if os.path.exists(timing_path):
        for line in open(timing_path):
            key, _, value = line.partition(": ")
            timing[key] = value.strip()
    run_secs = sum(float(r["secs"]) for r in spec_rows.values())
    print("wall time of the run (baseline + faults): %s s; summed verify time of the faults: %.0f s; peak memory of any run: %s MB" % (
        timing.get("wall_seconds_total", "unknown"), run_secs,
        max([int(r["peak_mb"]) for r in spec_rows.values()] or [0])))

    print()
    print("== per fixture: SPEC vs HAND-WRITTEN (G4) ==")
    for fixture in FIXTURES:
        ids = [e["id"] for e in manifests[fixture] if e["id"] in spec]
        print(fmt_row(fixture, [spec[i] for i in ids], [g4[i] for i in ids]))
    all_ids = [i for i in entries if i in spec]
    print(fmt_row("all", [spec[i] for i in all_ids], [g4[i] for i in all_ids]))
    kept = [i for i in all_ids if i not in NOT_A_DEFECT]
    print(fmt_row("all without nj-29", [spec[i] for i in kept], [g4[i] for i in kept]))
    nj = [e["id"] for e in manifests["nextjs"] if e["id"] in spec and e["id"] not in NOT_A_DEFECT]
    print(fmt_row("nextjs without nj-29", [spec[i] for i in nj], [g4[i] for i in nj]))

    print()
    print("== false-PASS rate (missed / faults) and rate without break-marked faults ==")
    for fixture in FIXTURES + ["all"]:
        ids = [i for i in all_ids if fixture == "all" or entries[i]["fixture"] == fixture]
        live = [i for i in ids if not entries[i]["breaks_run"]]
        print("  %-9s false-PASS SPEC %4.1f%% (%d/%d) HAND %4.1f%% (%d/%d);  caught without break-marked faults: SPEC %4.1f%% (%d/%d) HAND %4.1f%% (%d/%d)" % (
            fixture,
            rate(sum(1 for i in ids if spec[i] == "missed"), len(ids)), sum(1 for i in ids if spec[i] == "missed"), len(ids),
            rate(sum(1 for i in ids if g4[i] == "missed"), len(ids)), sum(1 for i in ids if g4[i] == "missed"), len(ids),
            rate(sum(1 for i in live if spec[i] == "caught"), len(live)), sum(1 for i in live if spec[i] == "caught"), len(live),
            rate(sum(1 for i in live if g4[i] == "caught"), len(live)), sum(1 for i in live if g4[i] == "caught"), len(live)))
    uncaught = [i for i in all_ids if spec[i] != "caught"]
    print("  SPEC not caught: %d = %d missed + %d no signal; of the no-signal ones %d are break-marked and %d live-marked (%s)" % (
        len(uncaught), sum(1 for i in uncaught if spec[i] == "missed"), sum(1 for i in uncaught if spec[i] == "no_signal"),
        sum(1 for i in uncaught if spec[i] == "no_signal" and entries[i]["breaks_run"]),
        sum(1 for i in uncaught if spec[i] == "no_signal" and not entries[i]["breaks_run"]),
        ", ".join(i for i in uncaught if spec[i] == "no_signal" and not entries[i]["breaks_run"])))

    print()
    print("== per category, per fixture ==")
    for fixture in FIXTURES:
        print("  -- %s" % fixture)
        cats = sorted({e["category"] for e in manifests[fixture]})
        for cat in cats:
            ids = [e["id"] for e in manifests[fixture] if e["category"] == cat and e["id"] in spec]
            if ids:
                print(fmt_row(cat, [spec[i] for i in ids], [g4[i] for i in ids]))

    print()
    print("== per category, all fixtures ==")
    for cat in sorted({e["category"] for e in entries.values()}):
        ids = [i for i, e in entries.items() if e["category"] == cat and i in spec]
        print(fmt_row(cat, [spec[i] for i in ids], [g4[i] for i in ids]))

    def listing(title, ids):
        print()
        print("%s: %d" % (title, len(ids)))
        for i in ids:
            e = entries[i]
            print("  %-8s %-5s [%s] %s | SPEC %s, HAND %s" % (
                i, "break" if e["breaks_run"] else "live", e["category"], short(e["statement"], 110), spec.get(i), g4[i]))

    print()
    print("== differences ==")
    listing("caught by SPEC, not caught by HAND (missed or no signal)",
            [i for i in all_ids if spec[i] == "caught" and g4[i] != "caught"])
    listing("caught by HAND, not caught by SPEC",
            [i for i in all_ids if g4[i] == "caught" and spec[i] != "caught"])
    listing("caught by neither", [i for i in all_ids if g4[i] != "caught" and spec[i] != "caught"])

    print()
    print("== SPEC faults not caught ==")
    for kind, title in (("missed", "missed (false PASS)"), ("no_signal", "no signal (counted as not caught)")):
        print()
        print("%s:" % title)
        for i in all_ids:
            if spec[i] == kind:
                e = entries[i]
                print("  %-8s %-5s [%s] %s" % (i, "break" if e["breaks_run"] else "live", e["category"], short(e["statement"], 110)))
                print("           %s" % short(spec_rows[i]["detail"], 230))

    print()
    print("== loading, empty, error and wrong-field faults ==")
    fixture_state_ok = {}
    fixture_field_ok = {}
    for fixture in FIXTURES:
        print("  -- %s" % fixture)
        tagged_all = True
        state_note = []
        for state in ("loading", "empty", "error"):
            ids = STATE_FAULTS.get(fixture, {}).get(state, [])
            present = PRODUCT_STATES[fixture][state]
            if not present and not ids:
                print("    %-8s the product has no %s state (ticket); no fault seeded" % (state, state))
                continue
            if present and not ids:
                print("    %-8s the product has this state but no fault is seeded in it: NOT MEASURED" % state)
                tagged_all = False
                state_note.append(state)
                continue
            results = [(i, kind_of(spec_rows, i)) for i in ids]
            caught = [i for i, k in results if k == "caught"]
            print("    %-8s %d of %d caught: %s" % (state, len(caught), len(ids),
                  ", ".join("%s=%s" % (i, k) for i, k in results)))
            if len(caught) != len(ids):
                tagged_all = False
                state_note.append(state)
        shape = STATE_FAULTS.get(fixture, {}).get("shape", [])
        for i in shape:
            k = kind_of(spec_rows, i)
            print("    %-8s %s=%s (labelled state by the fault author; a response-shape fault)" % ("shape", i, k))
            if k != "caught":
                tagged_all = False
                state_note.append("shape")
        fixture_state_ok[fixture] = (tagged_all, state_note)
        wf = [e["id"] for e in manifests[fixture] if e["category"] in WRONG_FIELD_CATEGORIES]
        wf_results = [(i, kind_of(spec_rows, i)) for i in wf]
        wf_caught = [i for i, k in wf_results if k == "caught"]
        print("    wrong-field: %d of %d caught: %s" % (len(wf_caught), len(wf),
              ", ".join("%s(%s)=%s" % (i, entries[i]["category"].replace("wrong field ", ""), k) for i, k in wf_results)))
        fixture_field_ok[fixture] = len(wf_caught) >= 1 if wf else None

    print()
    print("== G9 verdicts ==")
    verdicts = {}
    for fixture in FIXTURES:
        ids = [e["id"] for e in manifests[fixture]]
        if any(i not in spec for i in ids):
            verdicts[fixture] = "NOT MEASURED"
            print("  %-9s NOT MEASURED (faults missing)" % fixture)
            continue
        caught = sum(1 for i in ids if spec[i] == "caught")
        r = rate(caught, len(ids))
        kept_ids = [i for i in ids if i not in NOT_A_DEFECT]
        r2 = rate(sum(1 for i in kept_ids if spec[i] == "caught"), len(kept_ids))
        rate_ok = r >= RATE_LINE
        state_ok, notes = fixture_state_ok[fixture]
        field_ok = fixture_field_ok[fixture]
        parts = [
            "rate %.1f%% (%d/%d)%s %s" % (r, caught, len(ids),
                  " [%.1f%% without nj-29]" % r2 if len(kept_ids) != len(ids) else "", "ok" if rate_ok else "below %d%%" % RATE_LINE),
            "state faults %s" % ("all caught" if state_ok else "NOT all caught (%s)" % ",".join(notes)),
            "wrong-field %s" % ("caught" if field_ok else "NOT caught" if field_ok is False else "none seeded"),
        ]
        ok = rate_ok and state_ok and bool(field_ok)
        verdicts[fixture] = "MET" if ok else "NOT MET"
        print("  %-9s %-8s %s" % (fixture, verdicts[fixture], "; ".join(parts)))
    total = len(all_ids)
    caught_all = sum(1 for i in all_ids if spec[i] == "caught")
    agg = rate(caught_all, total)
    kept_caught = sum(1 for i in kept if spec[i] == "caught")
    agg2 = rate(kept_caught, len(kept))
    print("  aggregate rate %.1f%% (%d/%d); without nj-29 %.1f%% (%d/%d)" % (agg, caught_all, total, agg2, kept_caught, len(kept)))
    if not measured or "NOT MEASURED" in verdicts.values():
        overall = "NOT MEASURED"
    else:
        overall = "MET" if agg >= RATE_LINE and all(v == "MET" for v in verdicts.values()) else "NOT MET"
    if measured:
        kind_ok = {}
        for fixture in FIXTURES:
            flags = []
            for state, present in PRODUCT_STATES[fixture].items():
                if present:
                    ids = STATE_FAULTS.get(fixture, {}).get(state, [])
                    flags.append(any(kind_of(spec_rows, i) == "caught" for i in ids))
            kind_ok[fixture] = all(flags) and bool(fixture_field_ok[fixture])
        strict_ok = all(fixture_state_ok[f][0] and bool(fixture_field_ok[f]) for f in FIXTURES)
        agg_ok = agg >= RATE_LINE
        print("  reading A (corpus-wide rate; each existing state has a caught seeded fault; a wrong-field fault caught per fixture): %s" % (
            "MET" if agg_ok and all(kind_ok.values()) else "NOT MET"))
        print("  reading B (corpus-wide rate; every seeded state fault caught; a wrong-field fault caught per fixture): %s" % (
            "MET" if agg_ok and strict_ok else "NOT MET"))
        print("  reading C (every fixture at least %d%% as well as reading B): %s" % (
            RATE_LINE, "MET" if agg_ok and all(v == "MET" for v in verdicts.values()) else "NOT MET"))
    print("G9 OVERALL: %s (reading C: aggregate at least %d%% and every fixture MET on rate, state faults and wrong-field)" % (overall, RATE_LINE))

    summary = {
        "overall": overall,
        "aggregate": {"caught": caught_all, "total": total, "rate": round(agg, 1)},
        "aggregate_without_nj29": {"caught": kept_caught, "total": len(kept), "rate": round(agg2, 1)},
        "fixtures": verdicts,
        "spec": spec,
        "hand": g4,
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
