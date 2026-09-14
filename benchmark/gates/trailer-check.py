#!/usr/bin/env python3
"""Gate: does each commit's Co-Authored-By trailer match what the repo's settings allow?

WHY THIS GATE EXISTS, WITH THE NUMBER

`Co-Authored-By` is prohibited in the Griffin repo by three independent statements: the
project CLAUDE.md, a memory note, and the user directly. Measured on 2026-09-13 against
real history: **37 of 369 commits since 2026-08-01 carry it anyway.** One in ten. The rule
was stated three times, is decidable from a single JSON field, and still failed.

That is the entire argument for this file. A rule that lives only in prose is obeyed when
it is read and ignored when it is not, and nothing distinguishes the two afterwards.

IT CHECKS BOTH DIRECTIONS, BECAUSE THE POLICY IS NOT ONE-WAY

  attribution.commit falsy  -> a trailer is a violation   (Griffin: {"commit": ""})
  attribution.commit truthy -> a MISSING trailer is one   (verified-autonomy: {"commit": true})

A one-way check would be correct in one of those repos and wrong in the other. The same
session that wrote this audit got it wrong in exactly that way: committed without the
trailer in verified-autonomy (`ec87bdc`), amended in `6c8705f`.

WHAT IT DOES NOT DECIDE

Whether the trailer is *true* — whether a model actually co-authored the commit. It decides
what the repository's own configuration permits, which is the mechanically decidable part.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SETTINGS = os.path.join(".claude", "settings.json")
TRAILER_KEY = "Co-Authored-By"
REC, FIELD = "\x1e", "\x1f"

# Declared here, not derived from a policy lookup, so that a change to how settings are
# read cannot silently change what counts as a violation.
VERDICTS = {"ok", "unexpected-trailer", "missing-trailer", "unknown-policy"}


class PolicyError(Exception):
    pass


def read_policy(root):
    """-> True (trailer required) | False (prohibited).

    Fail closed on an unreadable settings file. A repo whose policy cannot be read is not
    a repo where every commit is fine; it is a repo where the question is unanswered, and
    answering 'ok' there is the fabricated-green this project exists to prevent.
    """
    path = os.path.join(root, SETTINGS)
    if not os.path.exists(path):
        raise PolicyError(f"{SETTINGS} not found — cannot decide the policy")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (ValueError, OSError) as exc:
        raise PolicyError(f"{SETTINGS} unreadable ({exc})") from exc
    attr = doc.get("attribution")
    if attr is None:
        return False          # absent means not enabled; the documented default
    if not isinstance(attr, dict):
        raise PolicyError(f"attribution is {type(attr).__name__}, expected an object")
    # "" and false and 0 are all falsy and all mean off. Griffin ships "".
    return bool(attr.get("commit"))


def commits(root, since=None, rev_range=None, limit=None):
    """(sha, subject, trailer_value) oldest-last, using record separators.

    NOT plain newlines: a trailer value is emitted on its own line, so `wc -l` over a
    newline-delimited format counts 406 'commits' for 369 real ones. That miscount was
    made while building this gate's own corpus.
    """
    fmt = f"%H{FIELD}%s{FIELD}%(trailers:key={TRAILER_KEY},valueonly){REC}"
    cmd = ["git", "-C", root, "log", f"--format={fmt}"]
    if since:
        cmd.append(f"--since={since}")
    if limit:
        cmd.append(f"--max-count={limit}")
    if rev_range:
        cmd.append(rev_range)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise PolicyError(f"git log failed: {p.stderr.strip()[:160]}")
    out = []
    for rec in p.stdout.split(REC):
        if not rec.strip():
            continue
        parts = rec.lstrip("\n").split(FIELD)
        if len(parts) < 3:
            continue
        out.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return out


def policy_start(root):
    """The oldest commit that introduced an `attribution` key into settings.json, or None.

    WHY THIS EXISTS. Run over all history, this gate flags every commit made BEFORE the
    policy was adopted -- 30 of the last 40 in this repo, all of them correct under the
    rule that applied at the time. A gate that is red from its first day on facts nobody
    can change gets switched off, and then it protects nothing.

    Scoping by DATE was tried first and is wrong: `--since` reads committer date, which
    drifts under rebase and amend, and it silently returned 2 commits where the range
    returns 10. A rev-range from the introducing commit is exact.
    """
    p = subprocess.run(["git", "-C", root, "log", "--format=%H", "-S", '"attribution"',
                        "--", SETTINGS], capture_output=True, text=True)
    shas = [l.strip() for l in p.stdout.splitlines() if l.strip()]
    return shas[-1] if shas else None


def judge(required, trailer):
    if required and not trailer:
        return "missing-trailer"
    if not required and trailer:
        return "unexpected-trailer"
    return "ok"


def audit(root, since=None, rev_range=None, limit=None):
    """-> (required, findings, total). A finding is (sha, subject, verdict)."""
    required = read_policy(root)
    rows = commits(root, since, rev_range, limit)
    findings = [(s, subj, judge(required, t)) for s, subj, t in rows]
    return required, [f for f in findings if f[2] != "ok"], len(rows)


def check_message(root, msg_path):
    """Pre-commit use: judge a prepared commit message file."""
    required = read_policy(root)
    with open(msg_path, encoding="utf-8") as fh:
        body = fh.read()
    has = bool(re.search(rf"^{re.escape(TRAILER_KEY)}:\s*\S", body, re.M | re.I))
    return required, judge(required, has)


# --------------------------------------------------------------------------- controls
# Hermetic: each control builds a real throwaway git repo in a temp dir and commits into
# it. No repo copy, no network. Building an actual repo rather than stubbing git means the
# trailer parsing is exercised the way it runs in production -- `%(trailers:...)` is git's
# own parser, and a stub would have tested a regex nobody ships.
import tempfile

EXPECTED_CONTROLS = {
    "prohibited-flags-trailer", "prohibited-allows-clean",
    "required-flags-missing", "required-allows-trailer",
    "unreadable-settings-fails-closed", "absent-settings-fails-closed",
    "message-hook-both-ways", "empty-string-is-falsy",
    "policy-start-found", "policy-start-absent-means-all-history",
}


def _git(root, *args, **kw):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, **kw)


def _repo(tmp, attribution, msgs):
    """A real git repo with .claude/settings.json and one commit per message."""
    os.makedirs(tmp, exist_ok=True)   # git -C on a missing dir fails before init runs
    _git(tmp, "init", "-q", "--initial-branch=main")
    _git(tmp, "config", "user.email", "t@t")
    _git(tmp, "config", "user.name", "t")
    os.makedirs(os.path.join(tmp, ".claude"), exist_ok=True)
    if attribution is not ...:
        with open(os.path.join(tmp, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({} if attribution is None else {"attribution": attribution}, fh)
    for i, m in enumerate(msgs):
        with open(os.path.join(tmp, f"f{i}.txt"), "w", encoding="utf-8") as fh:
            fh.write(str(i))
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", m)
    return tmp


TRAILER = f"{TRAILER_KEY}: Claude Opus 5 <noreply@anthropic.com>"


def self_test():
    print("commit-trailer gate — controls\n")
    ok, n, seen = True, 0, set()

    def check(name, got, want):
        nonlocal ok, n
        n += 1
        seen.add(name.split(" (")[0])
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {name:<46} {got!r}")
        if not good:
            print(f"       expected {want!r}")

    with tempfile.TemporaryDirectory() as td:
        # PROHIBITED ({"commit": ""}), the Griffin shape.
        r = _repo(os.path.join(td, "a"), {"commit": ""},
                  ["clean one", f"dirty one\n\n{TRAILER}"])
        req, bad, tot = audit(r)
        check("empty-string-is-falsy", req, False)
        check("prohibited-flags-trailer", [b[2] for b in bad], ["unexpected-trailer"])
        check("prohibited-allows-clean", tot - len(bad), 1)

        # REQUIRED ({"commit": true}), the verified-autonomy shape.
        r = _repo(os.path.join(td, "b"), {"commit": True},
                  ["missing one", f"good one\n\n{TRAILER}"])
        req, bad, tot = audit(r)
        check("required-flags-missing", [b[2] for b in bad], ["missing-trailer"])
        check("required-allows-trailer", tot - len(bad), 1)

        # FAIL CLOSED. An unreadable or absent policy is not a passing policy.
        r = _repo(os.path.join(td, "c"), {"commit": True}, ["x"])
        with open(os.path.join(r, SETTINGS), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        try:
            audit(r); got = "returned a verdict"
        except PolicyError:
            got = "PolicyError"
        check("unreadable-settings-fails-closed", got, "PolicyError")

        r = _repo(os.path.join(td, "d"), ..., ["x"])   # no settings file at all
        try:
            audit(r); got = "returned a verdict"
        except PolicyError:
            got = "PolicyError"
        check("absent-settings-fails-closed", got, "PolicyError")

        # The pre-commit path, both directions on one fixture.
        r = _repo(os.path.join(td, "e"), {"commit": ""}, ["x"])
        m = os.path.join(td, "msg")
        with open(m, "w", encoding="utf-8") as fh:
            fh.write(f"subject\n\n{TRAILER}\n")
        _, v1 = check_message(r, m)
        with open(m, "w", encoding="utf-8") as fh:
            fh.write("subject\n\nbody\n")
        _, v2 = check_message(r, m)
        check("message-hook-both-ways", [v1, v2], ["unexpected-trailer", "ok"])

        # policy_start locates the commit that adopted the rule, so pre-policy commits
        # are not judged by a rule that did not exist yet.
        r = _repo(os.path.join(td, "f"), ..., ["before one", "before two"])
        check("policy-start-absent-means-all-history", policy_start(r), None)
        os.makedirs(os.path.join(r, ".claude"), exist_ok=True)
        with open(os.path.join(r, SETTINGS), "w", encoding="utf-8") as fh:
            json.dump({"attribution": {"commit": True}}, fh)
        _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", f"adopt policy\n\n{TRAILER}")
        with open(os.path.join(r, "after.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", f"after\n\n{TRAILER}")
        start = policy_start(r)
        scoped = len(commits(r, rev_range=f"{start}..HEAD")) if start else -1
        check("policy-start-found", (start is not None, scoped), (True, 1))

    missing = EXPECTED_CONTROLS - seen
    extra = seen - EXPECTED_CONTROLS
    if missing or extra:
        ok = False
        print(f"\n  !! CONTROL SET CHANGED: missing {sorted(missing) or 'none'}, "
              f"unexpected {sorted(extra) or 'none'}")
    else:
        print(f"\n  control set matches EXPECTED_CONTROLS ({len(EXPECTED_CONTROLS)} names)")
    print(f"\n  commit-trailer gate ({n} checks)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="check Co-Authored-By against repo policy")
    ap.add_argument("--root", default=".")
    ap.add_argument("--since")
    ap.add_argument("--range", dest="rev_range")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--since-policy", action="store_true",
                    help="only commits after the one that introduced attribution")
    ap.add_argument("--message", help="pre-commit: judge a prepared message file")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    root = os.path.abspath(a.root)
    try:
        if a.message:
            required, verdict = check_message(root, a.message)
            if verdict == "ok":
                return 0
            print(f"  {verdict}: attribution.commit is "
                  f"{'enabled' if required else 'off'} in {SETTINGS}", file=sys.stderr)
            return 1
        rng = a.rev_range
        if a.since_policy:
            start = policy_start(root)
            if start is None:
                # No introducing commit means the policy has applied for all of recorded
                # history -- the shape of a repo that has always PROHIBITED the trailer.
                # Full history is then the correct scope, not an error. Erroring here was
                # the first behaviour and it made the flag unusable in exactly the repo
                # whose 37 violations motivated this gate.
                print("  no commit introduces `attribution`; the policy has applied for "
                      "all recorded history, so the scope is all of it")
            else:
                rng = f"{start}..HEAD"
                print(f"  scoped to {start[:9]}..HEAD (the commit that adopted the policy)")
        required, bad, total = audit(root, a.since, rng, a.limit)
    except PolicyError as exc:
        print(f"  POLICY UNREADABLE: {exc}", file=sys.stderr)
        return 2
    print(f"commit-trailer gate — attribution.commit "
          f"{'REQUIRED' if required else 'PROHIBITED'}, {total} commit(s)")
    for sha, subj, verdict in bad:
        print(f"  {verdict:<18} {sha[:9]}  {subj[:56]}")
    if not bad:
        print("  no violations")
        return 0
    print(f"\n  {len(bad)}/{total} violation(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
