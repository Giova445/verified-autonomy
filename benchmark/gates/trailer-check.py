#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
import tempfile

CO_AUTHOR = re.compile(r"^co-authored-by:\s*\S", re.M | re.I)
BASES = ("origin/HEAD", "origin/main", "origin/master", "main", "master")
REC, FIELD = "\x1e", "\x1f"


class GitError(Exception):
    pass


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def resolve_base(root, explicit=None):
    for ref in ([explicit] if explicit else BASES):
        if git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return ref
    if explicit:
        raise GitError(f"base ref '{explicit}' does not exist")
    return None


def commits(root, rev_range):
    p = git(root, "log", f"--format=%H{FIELD}%s{FIELD}%B{REC}", rev_range)
    if p.returncode != 0:
        raise GitError(f"git log {rev_range} failed: {p.stderr.strip()[:160]}")
    out = []
    for rec in p.stdout.split(REC):
        parts = rec.lstrip("\n").split(FIELD)
        if len(parts) == 3:
            out.append((parts[0].strip(), parts[1].strip(), parts[2]))
    return out


def audit(root, base=None):
    ref = resolve_base(root, base)
    rev_range = f"{ref}..HEAD" if ref else "HEAD"
    rows = commits(root, rev_range)
    return rev_range, [(sha, subj) for sha, subj, body in rows if CO_AUTHOR.search(body)], len(rows)


def message_has_co_author(path):
    with open(path, encoding="utf-8") as fh:
        return bool(CO_AUTHOR.search(fh.read()))


EXPECTED_CONTROLS = {
    "branch-commit-with-trailer-flagged", "lowercase-trailer-flagged", "clean-branch-passes",
    "base-history-not-judged", "prose-mention-not-flagged", "no-base-judges-all-history",
    "missing-explicit-base-refuses", "message-mode-both-ways",
}

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def _commit(r, name, msg):
    with open(os.path.join(r, name), "w", encoding="utf-8") as fh:
        fh.write(name)
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", msg)


def _repo(path, branch="main"):
    os.makedirs(path)
    git(path, "init", "-q", f"--initial-branch={branch}")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    return path


def self_test():
    print("co-author gate — controls\n")
    ok, n, seen = True, 0, set()

    def check(name, got, want):
        nonlocal ok, n
        n += 1
        seen.add(name)
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {name:<40} {got!r}")
        if not good:
            print(f"       expected {want!r}")

    with tempfile.TemporaryDirectory() as td:
        r = _repo(os.path.join(td, "a"))
        _commit(r, "old", f"old work\n\n{TRAILER}")
        git(r, "checkout", "-q", "-b", "feat")
        _commit(r, "one", "clean")
        _commit(r, "two", f"dirty\n\n{TRAILER}")
        _commit(r, "three", "lower\n\nco-authored-by: someone <s@x>")
        _commit(r, "four", "prose\n\nthe Co-Authored-By: trailer is banned here")
        _, bad, total = audit(r, "main")
        subjects = sorted(s for _, s in bad)
        check("branch-commit-with-trailer-flagged", "dirty" in subjects, True)
        check("lowercase-trailer-flagged", "lower" in subjects, True)
        check("prose-mention-not-flagged", "prose" in subjects, False)
        check("base-history-not-judged", (total, subjects), (4, ["dirty", "lower"]))

        r = _repo(os.path.join(td, "b"))
        _commit(r, "base", "base")
        git(r, "checkout", "-q", "-b", "feat")
        _commit(r, "x", "feature")
        _, bad, total = audit(r, "main")
        check("clean-branch-passes", (bad, total), ([], 1))

        r = _repo(os.path.join(td, "c"), "trunk")
        _commit(r, "x", f"only\n\n{TRAILER}")
        rng, bad, _ = audit(r)
        check("no-base-judges-all-history", (rng, len(bad)), ("HEAD", 1))
        try:
            audit(r, "nope")
            got = "returned a verdict"
        except GitError:
            got = "GitError"
        check("missing-explicit-base-refuses", got, "GitError")

        m = os.path.join(td, "msg")
        with open(m, "w", encoding="utf-8") as fh:
            fh.write(f"subject\n\n{TRAILER}\n")
        v1 = message_has_co_author(m)
        with open(m, "w", encoding="utf-8") as fh:
            fh.write("subject\n\nbody\n")
        check("message-mode-both-ways", [v1, message_has_co_author(m)], [True, False])

    if seen != EXPECTED_CONTROLS:
        ok = False
        print(f"\n  !! CONTROL SET CHANGED: missing {sorted(EXPECTED_CONTROLS - seen) or 'none'}, "
              f"unexpected {sorted(seen - EXPECTED_CONTROLS) or 'none'}")
    print(f"\n  co-author gate ({n} checks)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="refuse any commit carrying a Co-Authored-By trailer")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", help="judge BASE..HEAD (default: first of origin/HEAD, origin/main, main)")
    ap.add_argument("--message", help="commit-msg hook: judge a prepared message file")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.message:
        if message_has_co_author(a.message):
            print("  refused: Co-Authored-By trailers are not allowed on any commit", file=sys.stderr)
            return 1
        return 0
    try:
        rev_range, bad, total = audit(os.path.abspath(a.root), a.base)
    except GitError as exc:
        print(f"  CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    print(f"co-author gate — {rev_range}, {total} commit(s)")
    for sha, subj in bad:
        print(f"  co-author  {sha[:9]}  {subj[:60]}")
    if not bad:
        print("  no Co-Authored-By trailers")
        return 0
    print(f"\n  {len(bad)}/{total} commit(s) carry a co-author. Reword them; the rule has no opt-out.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
