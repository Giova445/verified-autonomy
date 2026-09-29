#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
import tempfile

CONFIG = ".claude/forbidden-trailers"
DEFAULT_KEYS = ("Co-Authored-By",)
REC, FIELD = "\x1e", "\x1f"


class GitError(Exception):
    pass


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def parse_keys(text):
    keys = [ln.strip().rstrip(":").strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return tuple(keys) or DEFAULT_KEYS


def pattern_for(keys):
    alt = "|".join(re.escape(k) for k in keys)
    return re.compile(rf"^(?:{alt}):\s*\S", re.M | re.I)


def forbidden_keys(root, base=None):
    found = []
    path = os.path.join(root, CONFIG)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            found.extend(parse_keys(fh.read()))
    elif os.path.exists(path):
        raise OSError(f"{CONFIG} exists but is not a readable file")
    if base:
        blob = git(root, "show", f"{base}:{CONFIG}")
        if blob.returncode == 0:
            found.extend(parse_keys(blob.stdout))
    return tuple(dict.fromkeys(found)) or None


def resolve_base(root, ref):
    if git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise GitError(f"base ref '{ref}' does not exist")
    return ref


def commits(root, rev_range):
    p = git(root, "log", f"--format=%H{FIELD}%s{FIELD}%B{REC}", *rev_range)
    if p.returncode != 0:
        raise GitError(f"git log {' '.join(rev_range)} failed: {p.stderr.strip()[:160]}")
    out = []
    for rec in p.stdout.split(REC):
        parts = rec.lstrip("\n").split(FIELD)
        if len(parts) == 3:
            out.append((parts[0].strip(), parts[1].strip(), parts[2]))
    return out


def audit(root, base=None, keys=DEFAULT_KEYS):
    pattern = pattern_for(keys)
    if base:
        rev_range = [f"{resolve_base(root, base)}..HEAD"]
    else:
        rev_range = ["HEAD", "--not", "--remotes"]
    rows = commits(root, rev_range)
    rev_range = " ".join(rev_range)
    return rev_range, [(sha, subj) for sha, subj, body in rows if pattern.search(body)], len(rows)


def message_has_trailer(path, keys=DEFAULT_KEYS):
    with open(path, encoding="utf-8") as fh:
        return bool(pattern_for(keys).search(fh.read()))


EXPECTED_CONTROLS = {
    "branch-commit-with-trailer-flagged", "lowercase-trailer-flagged", "clean-branch-passes",
    "base-history-not-judged", "prose-mention-not-flagged", "no-remote-judges-all-history",
    "pushed-commits-not-judged",
    "missing-explicit-base-refuses", "message-mode-both-ways",
    "unconfigured-repo-exits-0-not-configured", "configured-repo-with-trailer-exits-1",
    "force-judges-without-config", "custom-key-judged-and-default-not",
    "empty-config-means-co-authored-by", "config-deleted-on-branch-still-judged-from-base",
    "unreadable-config-cannot-run",
}

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"
SELF_PATH = os.path.abspath(__file__)


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


def _write_config(r, text):
    os.makedirs(os.path.join(r, ".claude"), exist_ok=True)
    with open(os.path.join(r, CONFIG), "w", encoding="utf-8") as fh:
        fh.write(text)


def _run(r, *args):
    p = subprocess.run([sys.executable, SELF_PATH, "--root", r, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def self_test():
    print("trailer gate — controls\n")
    ok, n, seen = True, 0, set()

    def check(name, got, want):
        nonlocal ok, n
        n += 1
        seen.add(name)
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {name:<46} {got!r}")
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
        _, bad, _ = audit(r)
        check("no-remote-judges-all-history", len(bad), 1)

        origin = os.path.join(td, "origin.git")
        git(td, "init", "-q", "--bare", origin)
        r = _repo(os.path.join(td, "d"))
        _commit(r, "pushed", f"pushed\n\n{TRAILER}")
        git(r, "remote", "add", "origin", origin)
        git(r, "push", "-q", "origin", "main")
        _commit(r, "local", f"local\n\n{TRAILER}")
        _, bad, total = audit(r)
        check("pushed-commits-not-judged", (total, [s for _, s in bad]), (1, ["local"]))
        r = os.path.join(td, "c")
        try:
            audit(r, "nope")
            got = "returned a verdict"
        except GitError:
            got = "GitError"
        check("missing-explicit-base-refuses", got, "GitError")

        m = os.path.join(td, "msg")
        with open(m, "w", encoding="utf-8") as fh:
            fh.write(f"subject\n\n{TRAILER}\n")
        v1 = message_has_trailer(m)
        with open(m, "w", encoding="utf-8") as fh:
            fh.write("subject\n\nbody\n")
        check("message-mode-both-ways", [v1, message_has_trailer(m)], [True, False])

        r = _repo(os.path.join(td, "e"))
        _commit(r, "x", f"tagged\n\n{TRAILER}")
        rc, out = _run(r)
        check("unconfigured-repo-exits-0-not-configured", (rc, "not configured" in out), (0, True))
        rc, _ = _run(r, "--force")
        check("force-judges-without-config", rc, 1)
        _write_config(r, "Co-Authored-By\n")
        rc, _ = _run(r)
        check("configured-repo-with-trailer-exits-1", rc, 1)

        _write_config(r, "Signed-off-by:\n")
        _, bad, _ = audit(r, keys=forbidden_keys(r))
        signed_off = len(bad)
        _commit(r, "y", "signed\n\nSigned-off-by: someone <s@x>")
        _, bad, _ = audit(r, keys=forbidden_keys(r))
        check("custom-key-judged-and-default-not", (signed_off, [s for _, s in bad]), (0, ["signed"]))

        _write_config(r, "\n\n")
        check("empty-config-means-co-authored-by", forbidden_keys(r), DEFAULT_KEYS)

        r = _repo(os.path.join(td, "f"))
        _write_config(r, "Co-Authored-By\n")
        _commit(r, "base", "base")
        git(r, "checkout", "-q", "-b", "feat")
        os.remove(os.path.join(r, CONFIG))
        _commit(r, "x", f"sneaky\n\n{TRAILER}")
        rc, _ = _run(r, "--base", "main")
        check("config-deleted-on-branch-still-judged-from-base", rc, 1)

        r = _repo(os.path.join(td, "g"))
        os.makedirs(os.path.join(r, CONFIG))
        _commit(r, "x", "plain")
        rc, out = _run(r)
        check("unreadable-config-cannot-run", (rc, "CANNOT RUN" in out), (2, True))

    if seen != EXPECTED_CONTROLS:
        ok = False
        print(f"\n  !! CONTROL SET CHANGED: missing {sorted(EXPECTED_CONTROLS - seen) or 'none'}, "
              f"unexpected {sorted(seen - EXPECTED_CONTROLS) or 'none'}")
    print(f"\n  trailer gate ({n} checks)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=f"refuse commits carrying a trailer listed in {CONFIG}")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", help="judge BASE..HEAD (default: commits on no remote, the ones still fixable)")
    ap.add_argument("--message", help="commit-msg hook: judge a prepared message file")
    ap.add_argument("--force", action="store_true", help=f"judge Co-Authored-By even when {CONFIG} is absent")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    root = os.path.abspath(a.root)
    try:
        keys = forbidden_keys(root, a.base)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    if keys is None:
        if not a.force:
            print(f"trailer gate: not configured (no {CONFIG}); nothing judged")
            return 0
        keys = DEFAULT_KEYS
    if a.message:
        if message_has_trailer(a.message, keys):
            print(f"  refused: a forbidden trailer ({', '.join(keys)}) is not allowed on any commit", file=sys.stderr)
            return 1
        return 0
    try:
        rev_range, bad, total = audit(root, a.base, keys)
    except GitError as exc:
        print(f"  CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    print(f"trailer gate ({', '.join(keys)}) - {rev_range}, {total} commit(s)")
    for sha, subj in bad:
        print(f"  trailer  {sha[:9]}  {subj[:60]}")
    if not bad:
        print("  no forbidden trailers")
        return 0
    print(f"\n  {len(bad)}/{total} commit(s) carry a forbidden trailer. Reword them; the rule has no opt-out.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
