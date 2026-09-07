#!/usr/bin/env python3
"""Stage 4b — continuous evals for the AGENT CONFIGURATION.

WHAT THIS IS NOT. It is not the gate suite. selftest.sh, benchmark/gates/bench.sh and the
per-tool controls all test the repo's CODE: does the hook block, does the runner refuse,
does the detector discriminate. This suite tests the CONFIGURATION that tells an agent how
to behave — skills/, agents/, hooks/hooks.json, the sandbox settings, the agent contract,
and the CI that runs the gates. It is the thing that gates a change to any of those.

WHY IT DOES NOT CALL A MODEL. The playbook describes an eval as a prompt plus deterministic
acceptance checks. Every eval here carries its prompt — the plausible request whose
plausible execution is the defect — but the acceptance check is a deterministic assertion
over the configuration, not a sampled model run. That is not a shortcut: it is
reproducible, free, and cannot be flaky, and a sampled run would be none of those. Where a
question genuinely needs a model to answer it, this suite says nothing rather than
pretending.

    python3 evals/run.py                 run every eval, report the pass rate
    python3 evals/run.py --self-test     run the positive controls
    python3 evals/run.py --only deny     run the evals whose ID contains 'deny'
    python3 evals/run.py --list          print the registry

EXIT 0 ONLY WHEN EVERY EVAL PASSED AND THE DECLARED ID SET WAS COMPLETE. A missing
expected.json, an unreadable configuration file, a suite that will not run: all failures.
None of them is "nothing to check here".
"""
import contextlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import ROOT, copy_tree, load_json  # noqa: E402
import evals_ci                             # noqa: E402
import evals_config                         # noqa: E402
import evals_hooks                          # noqa: E402
import evals_suites                         # noqa: E402

EXPECTED_PATH = "evals/expected.json"

# THE DECLARED SET. Written out literally, and deliberately NOT derived from the registry
# below or from expected.json. An expectation computed from the thing it checks cannot
# notice that thing shrinking: delete an eval, and a derived expectation deletes itself
# alongside it, leaving a smaller suite reporting a perfect score. Adding an eval means
# adding its ID here, in the same commit.
EXPECTED_EVAL_IDS = frozenset({
    # instruction surface
    "skill-usage-triggers",
    "config-name-collisions",
    "contract-commands-resolve",
    "verify-subcommands-dispatch",
    "contract-clauses-intact",
    "subagent-write-privileges",
    # enforcement configuration
    "deny-hook-blocks-attacks",
    "deny-hook-allows-real-work",
    "hook-events-wired",
    "pretooluse-covers-write-tools",
    "sandbox-protects-guardrails",
    "kit-permission-classes",
    # CI that runs the gates
    "ci-actions-sha-pinned",
    "ci-controls-run-first",
    "ci-eval-suite-triggered",
    "ci-no-write-scope",
    # suite integrity — one per pinned control suite
    "suite-integrity:selftest.sh",
    "suite-integrity:tests/orchestration-test.sh",
    "suite-integrity:bin/ledger",
    "suite-integrity:bin/escalate",
    "suite-integrity:bin/worktree-guard",
    "suite-integrity:bin/test-delta",
    "suite-integrity:bin/holdout",
    "suite-integrity:bin/mutate-changed",
    "suite-integrity:bin/ambiguity",
    "suite-integrity:hooks/inert-mask.py",
    "suite-integrity:benchmark/structure/validate.py",
    "suite-integrity:benchmark/skills/trigger-eval.py",
    "suite-integrity:benchmark/verification/mcp/collision-detect.py",
    "suite-integrity:benchmark/gates/pin-check.py",
})


def build_registry():
    """(registry, fatal_errors). A fatal error means the run cannot be trusted at all."""
    expected, err = load_json(ROOT, EXPECTED_PATH)
    if err:
        return {}, [f"{err} — the pinned expectations are unreadable, so nothing below "
                    f"can be checked against anything"]
    registry, duplicates = {}, []
    for item in (evals_config.EVALS + evals_hooks.build(expected)
                 + evals_ci.EVALS + evals_suites.build(expected)):
        if item.id in registry:
            duplicates.append(f"duplicate eval ID '{item.id}'")
        registry[item.id] = item
    return registry, duplicates


def id_set_findings(registry):
    """Drift between the declared ID set and what actually got registered."""
    findings = []
    for missing in sorted(EXPECTED_EVAL_IDS - set(registry)):
        findings.append(f"DECLARED BUT MISSING: '{missing}' is in EXPECTED_EVAL_IDS and "
                        f"registered nowhere. The suite got smaller.")
    for extra in sorted(set(registry) - EXPECTED_EVAL_IDS):
        findings.append(f"REGISTERED BUT UNDECLARED: '{extra}' runs but is not in "
                        f"EXPECTED_EVAL_IDS. Declare it, or it is not part of the suite.")
    return findings


# --------------------------------------------------------------------------- reporting

def _rule():
    print("-" * 74)


def run_all(only=None, json_out=None):
    registry, fatal = build_registry()
    print("agent-configuration evals — Stage 4b")
    print(f"repo: {ROOT}")
    _rule()

    problems = fatal + id_set_findings(registry)
    for line in problems:
        print(f"  !! {line}")
    if fatal:
        _rule()
        print("EVALS FAILED — the registry could not be built")
        return 1
    if problems:
        _rule()

    ids = sorted(registry)
    if only:
        ids = [i for i in ids if only in i]
        if not ids:
            print(f"  !! --only '{only}' matched no eval")
            return 1

    passed, failed = 0, []
    for eval_id in ids:
        findings = registry[eval_id].check(ROOT)
        if findings:
            failed.append(eval_id)
            print(f"  FAIL  {eval_id}")
            for finding in findings:
                print(f"          {finding}")
        else:
            passed += 1
            print(f"  pass  {eval_id}")

    total = passed + len(failed)
    _rule()
    rate = f"{100.0 * passed / total:.1f}%" if total else "n/a"
    print(f"  {total} evals run, {passed} passed, {len(failed)} failed — pass rate {rate}")
    if only:
        print(f"  (filtered by --only '{only}'; the full suite declares "
              f"{len(EXPECTED_EVAL_IDS)})")
    if failed:
        print("  failed: " + ", ".join(failed))
    print()
    ok = not failed and not problems
    print("EVALS PASSED" if ok else "EVALS FAILED")

    # Machine-readable result for monitoring/collect.py, whose source_evals() calls
    # `evals/run.py --json <file>` and falls back to the last JSON object on stdout.
    # That contract was documented on the collector side and never implemented here, so
    # evals.pass_rate -- the metric bands.yaml most wants to watch -- recorded
    # "unavailable" on every observation. The collector was right to refuse a number
    # rather than invent one; the missing half was this.
    #
    # `filtered` is emitted because a --only run is not a suite-wide pass rate. A consumer
    # that ignores it and records 1/1 as 100% is recording something else.
    if json_out:
        payload = {
            "schema": "verified-autonomy/evals/result@1",
            "passed": passed,
            "total": total,
            "pass_rate": (passed / total) if total else None,
            "failed": sorted(failed),
            "problems": problems,
            "declared": len(EXPECTED_EVAL_IDS),
            "filtered": bool(only),
        }
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return 0 if ok else 1


# ------------------------------------------------------------------- positive controls

def _fixture(control, stack):
    if control.fixture == "empty":
        return stack.enter_context(tempfile.TemporaryDirectory())
    tmp = stack.enter_context(tempfile.TemporaryDirectory())
    return copy_tree(os.path.join(tmp, "tree"))


def _run_control(item, control):
    """(ok, lines to print). Each control gets its own fixture; none leaks into another."""
    lines = []
    with contextlib.ExitStack() as stack:
        root = _fixture(control, stack)
        prepared = control.setup(root) if control.setup else None
        clean = item.check(root) if control.fixture == "tree" else []
        what = control.apply(root)
        after = item.check(root)
        new = [f for f in after if f not in clean]

        lines.append(f"    control        : {control.name}")
        if prepared:
            lines.append(f"    fixture setup  : {prepared}")
        lines.append(f"    manipulation   : {what}")
        lines.append(f"    baseline       : {len(clean)} finding(s)")
        if control.expect == "pass":
            ok = not after
            lines.append(f"    after          : {len(after)} finding(s)  "
                         f"expected none, got={'none' if ok else after[0]}")
        else:
            ok = any(control.token in f for f in new)
            lines.append(f"    after          : {len(after)} finding(s)  "
                         f"detected={ok}")
            if new:
                lines.append(f"    new finding    : {new[0]}")
        if not ok:
            lines.append("    !! CONTROL FAILED: the manipulation did not produce the "
                         "verdict this eval claims to produce. An eval that cannot fail "
                         "is not an eval.")
    return ok, lines


def self_test(only=None):
    registry, fatal = build_registry()
    print("agent-configuration evals — positive controls")
    print("Every eval below is shown FAILING against a deliberately broken fixture, and")
    print("(where a passing control is declared) PASSING against a correct one.")
    _rule()

    problems = fatal + id_set_findings(registry)
    for line in problems:
        print(f"  !! {line}")
    if fatal:
        print("\n  CONTROLS NOT RUN")
        return 1

    ids = sorted(registry)
    if only:
        ids = [i for i in ids if only in i]

    ok, count = not problems, 0
    for eval_id in ids:
        item = registry[eval_id]
        print(f"\n  {eval_id}")
        for control in item.controls:
            good, lines = _run_control(item, control)
            print("\n".join(lines))
            count += 1
            ok = ok and good

    print(f"\n  agent-configuration evals ({count} checks)")
    if not ok:
        print("  CONTROLS FAILED")
    return 0 if ok else 1


def list_registry():
    registry, fatal = build_registry()
    for line in fatal + id_set_findings(registry):
        print(f"  !! {line}")
    for eval_id in sorted(registry):
        item = registry[eval_id]
        print(f"\n{eval_id}")
        print(f"  prompt : {item.prompt}")
        print(f"  why    : {item.why}")
        print(f"  controls: {len(item.controls)}")
    print(f"\n{len(registry)} registered, {len(EXPECTED_EVAL_IDS)} declared")
    return 0 if not fatal and not id_set_findings(registry) else 1


def main(argv):
    only = None
    json_out = None
    if "--json" in argv:
        idx = argv.index("--json")
        if idx + 1 >= len(argv):
            print("--json needs a path")
            return 1
        json_out = argv[idx + 1]
    if "--only" in argv:
        idx = argv.index("--only")
        if idx + 1 >= len(argv):
            print("--only needs a substring")
            return 1
        only = argv[idx + 1]
    if "--list" in argv:
        return list_registry()
    if "--self-test" in argv:
        return self_test(only)
    return run_all(only, json_out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
