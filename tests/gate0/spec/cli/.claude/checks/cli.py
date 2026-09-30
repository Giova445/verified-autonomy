import json
import os
import re
import shlex
import shutil
import subprocess
import sys

CANNOT_RUN = 75
CASE_TIMEOUT_SECONDS = 20
ENTRYPOINTS = ("bin/orders.mjs", "cli/bin/orders.mjs")


def repo_root():
    checks_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(checks_dir))


def find_entrypoint(root):
    for entry in ENTRYPOINTS:
        path = os.path.join(root, entry)
        if os.path.isfile(path):
            return path
    return None


def split_lines(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def row_pattern(fields):
    body = r"\W+".join(re.escape(field) for field in fields)
    return re.compile(r"\W*" + body + r"\W*")


def describe(args):
    return "orders " + " ".join(shlex.quote(arg) for arg in args)


def judge_exit(code, wanted):
    if wanted is None:
        return []
    if wanted == "nonzero":
        return ["exit status 0, wanted a non-zero status"] if code == 0 else []
    if code != wanted:
        return ["exit status %d, wanted %d" % (code, wanted)]
    return []


def judge_lines(stream, text, wanted):
    if wanted is None:
        return []
    lines = split_lines(text)
    if lines != wanted:
        return ["%s was %r, wanted %r" % (stream, lines, wanted)]
    return []


def judge_rows(text, rows):
    if rows is None:
        return []
    lines = split_lines(text)
    if len(lines) != len(rows):
        return ["stdout has %d lines, wanted %d: %r" % (len(lines), len(rows), lines)]
    problems = []
    for number, (line, fields) in enumerate(zip(lines, rows), 1):
        if not row_pattern(fields).fullmatch(line):
            problems.append(
                "stdout line %d is %r, wanted %s in that order" % (number, line, ", ".join(fields))
            )
    return problems


def run_case(node, entrypoint, case):
    working_dir = os.path.dirname(os.path.dirname(entrypoint))
    try:
        done = subprocess.run(
            [node, entrypoint] + case["args"],
            cwd=working_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=CASE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ["no exit within %d seconds" % CASE_TIMEOUT_SECONDS]
    out = done.stdout.decode("utf-8", "replace")
    err = done.stderr.decode("utf-8", "replace")
    return (
        judge_exit(done.returncode, case.get("exit"))
        + judge_lines("stdout", out, case.get("stdout_lines"))
        + judge_rows(out, case.get("stdout_rows"))
        + judge_lines("stderr", err, case.get("stderr_lines"))
    )


def main(argv):
    if len(argv) != 3 or argv[2] not in ("check", "control"):
        print("usage: cli.py SPEC.json check|control", file=sys.stderr)
        return 2
    with open(argv[1]) as handle:
        cases = json.load(handle)[argv[2]]
    node = shutil.which("node")
    if node is None:
        print("node is not installed")
        return CANNOT_RUN
    entrypoint = find_entrypoint(repo_root())
    if entrypoint is None:
        print("there is no bin/orders.mjs (or cli/bin/orders.mjs) to run")
        return 1
    failed = 0
    for case in cases:
        problems = run_case(node, entrypoint, case)
        if problems:
            failed += 1
            print("FAIL %s" % describe(case["args"]))
            for problem in problems:
                print("     %s" % problem)
        else:
            print("PASS %s" % describe(case["args"]))
    print("%d of %d cases passed" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
