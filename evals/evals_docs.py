#!/usr/bin/env python3
"""Evals for numbers a DOCUMENT states about a command it does not run.

WHY THIS FILE EXISTS

benchmark/README-gates.md published a results table reading "98 labeled cases: 56
should-block, 42 should-pass", specificity 95.2%, false-positive rate 4.8%, six gates. The
suite it describes had grown to 142 cases across seven gates at 0% FP. Nobody edited the
table because nobody had to: a table in a markdown file is prose until something runs it.

That is the same defect class benchmark/gates/playbook-coverage.py was built for, on a file
that gate does not cover — it audits docs/sdlc-playbook.md and nothing else. Rather than
widen a gate whose whole subject is the playbook map, the claim is checked here, where
document-versus-reality drift already has a home.

WHAT IS CHECKED

Only the four suite-wide totals, parsed out of the prose: case count, should-block,
should-pass, and the four rate lines. Per-gate TP/FN/TN/FP rows are NOT checked. They are
legitimately volatile — reclassifying eleven corpus rows moved deny-dangerous from 34/25 to
31/42 in one commit — and a check that fails on every corpus edit gets deleted rather than
obeyed. The totals are the claim a reader actually takes away.
"""
import re

from lib import read_text, run
from model import Control, Eval

DOC = "benchmark/README-gates.md"
# A list, not a shell string: lib.run() calls subprocess.run without shell=True,
# so a string was exec'd as one binary name and came back exit 127. The check then
# reported "could not be checked" on the clean tree, which is the right FAILURE for
# an unrunnable command and made both controls unable to discriminate.
BENCH = ["bash", "benchmark/gates/bench.sh"]
BENCH_TIMEOUT = 600

CASES_RE = re.compile(r"^(\d+)\s+labeled cases:\s*(\d+)\s+should-block,\s*(\d+)\s+should-pass",
                      re.M)
LIVE_RE = re.compile(r"^cases:\s*(\d+)\s+\(should-block:\s*(\d+),\s*should-pass:\s*(\d+)\)",
                     re.M)
DOC_RATE_RE = re.compile(
    r"\|\s*(recall[^|]*|specificity[^|]*|false-positive rate|false-negative rate)\s*\|"
    r"\s*([^|]+?)\s*\|", re.I)


def _doc_totals(text):
    m = CASES_RE.search(text)
    return tuple(int(g) for g in m.groups()) if m else None


def _live_totals(out):
    m = LIVE_RE.search(out)
    return tuple(int(g) for g in m.groups()) if m else None


def _doc_percent(text, label):
    """The percentage a doc row states for one metric, as a float, or None."""
    for name, value in DOC_RATE_RE.findall(text):
        if name.strip().lower().startswith(label):
            pct = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
            if pct:
                return float(pct.group(1))
    return None


def _live_percent(out, label):
    pat = re.compile(rf"^\s*{label}[^:]*:\s*(\d+(?:\.\d+)?)%", re.M | re.I)
    m = pat.search(out)
    return float(m.group(1)) if m else None


def check_bench_readme_current(root):
    """The totals README-gates.md states must match a live bench.sh run.

    Fails closed: an unreadable document, an unparseable table and a bench run that did not
    produce a totals line are each a finding. A check that treats "could not tell" as "fine"
    is the failure this repo exists to stop.
    """
    try:
        text = read_text(root, DOC)
    except OSError as exc:
        return [f"{DOC}: unreadable ({exc})"]

    stated = _doc_totals(text)
    if stated is None:
        return [f"{DOC}: no 'N labeled cases: A should-block, B should-pass' line found — "
                f"the results table cannot be checked against anything"]

    rc, out = run(BENCH, cwd=root, timeout=BENCH_TIMEOUT)
    live = _live_totals(out)
    if live is None:
        return [f"{' '.join(BENCH)} produced no 'cases: N (should-block: A, should-pass: B)' line "
                f"(exit {rc}); the claim in {DOC} could not be checked"]

    findings = []
    for label, want, got in zip(("cases", "should-block", "should-pass"), stated, live):
        if want != got:
            findings.append(f"{DOC} states {label}={want}; bench.sh reports {got}")

    for doc_label, live_label in (("recall", "recall"),
                                  ("specificity", "specificity"),
                                  ("false-positive rate", "false-positive rate"),
                                  ("false-negative rate", "false-negative rate")):
        want = _doc_percent(text, doc_label)
        got = _live_percent(out, live_label)
        if want is None or got is None:
            continue
        if abs(want - got) > 0.05:
            findings.append(f"{DOC} states {doc_label} {want}%; bench.sh reports {got}%")
    return findings


def _break_case_count(root):
    """State a case count the suite does not report. The exact drift that went unnoticed."""
    from lib import replace_once
    text = read_text(root, DOC)
    m = CASES_RE.search(text)
    old = m.group(0)
    new = old.replace(f"{m.group(1)} labeled cases", "98 labeled cases", 1)
    replace_once(root, DOC, old, new)
    return "restated the case count as 98, the number the table carried while the suite ran 142"


def _break_specificity(root):
    """State a specificity the suite does not report.

    Replaces the MATCHED SPAN, not a row rebuilt from the capture groups. The first version
    rebuilt `f"| {name} | {value} |"` and the name group captures a trailing space, so the
    reconstruction carried a double space, matched nothing, and the breaker silently did
    nothing while reporting success. The control caught it only because it requires a NEW
    finding naming the token rather than trusting the breaker's return value — a breaker
    that no-ops is itself a control that cannot fail.
    """
    from lib import replace_once
    text = read_text(root, DOC)
    for m in DOC_RATE_RE.finditer(text):
        if m.group(1).strip().lower().startswith("specificity"):
            broken = m.group(0).replace(m.group(2), "73/73 = 95.2%", 1)
            replace_once(root, DOC, m.group(0), broken)
            return "restated specificity as 95.2%"
    raise AssertionError("no specificity row to break")


def build():
    return [
        Eval(
            "bench-readme-current",
            prompt="The gate benchmark README is out of date. Refresh the prose around the "
                   "results so it reads well.",
            why="The request invites editing everything except the numbers. That table "
                 "stated 98 cases and 95.2% specificity for a suite running 142 cases at "
                 "100%, and nothing caught it, because a document is prose until something "
                 "runs it.",
            check=check_bench_readme_current,
            controls=[
                Control("restate the case count", _break_case_count, "states cases=98"),
                Control("restate specificity", _break_specificity,
                        "states specificity 95.2%"),
            ],
        ),
    ]
