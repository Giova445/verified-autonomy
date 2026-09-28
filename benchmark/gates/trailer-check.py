#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys

SETTINGS = os.path.join(".claude", "settings.json")
TRAILER_KEY = "Co-Authored-By"
REC, FIELD = "\x1e", "\x1f"

VERDICTS = {"ok", "unexpected-trailer", "missing-trailer", "unknown-policy"}

class PolicyError(Exception):
    pass

def read_policy(root):
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
        return False
    if not isinstance(attr, dict):
        raise PolicyError(f"attribution is {type(attr).__name__}, expected an object")
    return bool(attr.get("commit"))

def commits(root, since=None, rev_range=None, limit=None):
    fmt = f"%H{FIELD}%s{FIELD}%(trailers:key={TRAILER_KEY},valueonly){REC}"
    cmd = ["git", "-C", root, "log", "--no-merges", f"--format={fmt}"]
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
    required = read_policy(root)
    rows = commits(root, since, rev_range, limit)
    findings = [(s, subj, judge(required, t)) for s, subj, t in rows]
    return required, [f for f in findings if f[2] != "ok"], len(rows)

def check_message(root, msg_path):
    required = read_policy(root)
    with open(msg_path, encoding="utf-8") as fh:
        body = fh.read()
    has = bool(re.search(rf"^{re.escape(TRAILER_KEY)}:\s*\S", body, re.M | re.I))
    return required, judge(required, has)

import tempfile

EXPECTED_CONTROLS = {
    "prohibited-flags-trailer", "prohibited-allows-clean",
    "required-flags-missing", "required-allows-trailer",
    "unreadable-settings-fails-closed", "absent-settings-fails-closed",
    "message-hook-both-ways", "empty-string-is-falsy",
    "policy-start-found", "policy-start-absent-means-all-history",
    "merge-commit-exempt", "non-merge-still-flagged",
}

def _git(root, *args, **kw):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, **kw)

def _repo(tmp, attribution, msgs):
    os.makedirs(tmp, exist_ok=True)
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
        r = _repo(os.path.join(td, "a"), {"commit": ""},
                  ["clean one", f"dirty one\n\n{TRAILER}"])
        req, bad, tot = audit(r)
        check("empty-string-is-falsy", req, False)
        check("prohibited-flags-trailer", [b[2] for b in bad], ["unexpected-trailer"])
        check("prohibited-allows-clean", tot - len(bad), 1)

        r = _repo(os.path.join(td, "b"), {"commit": True},
                  ["missing one", f"good one\n\n{TRAILER}"])
        req, bad, tot = audit(r)
        check("required-flags-missing", [b[2] for b in bad], ["missing-trailer"])
        check("required-allows-trailer", tot - len(bad), 1)

        r = _repo(os.path.join(td, "c"), {"commit": True}, ["x"])
        with open(os.path.join(r, SETTINGS), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        try:
            audit(r); got = "returned a verdict"
        except PolicyError:
            got = "PolicyError"
        check("unreadable-settings-fails-closed", got, "PolicyError")

        r = _repo(os.path.join(td, "d"), ..., ["x"])
        try:
            audit(r); got = "returned a verdict"
        except PolicyError:
            got = "PolicyError"
        check("absent-settings-fails-closed", got, "PolicyError")

        r = _repo(os.path.join(td, "e"), {"commit": ""}, ["x"])
        m = os.path.join(td, "msg")
        with open(m, "w", encoding="utf-8") as fh:
            fh.write(f"subject\n\n{TRAILER}\n")
        _, v1 = check_message(r, m)
        with open(m, "w", encoding="utf-8") as fh:
            fh.write("subject\n\nbody\n")
        _, v2 = check_message(r, m)
        check("message-hook-both-ways", [v1, v2], ["unexpected-trailer", "ok"])

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

        r = _repo(os.path.join(td, "g"), {"commit": True}, [f"base\n\n{TRAILER}"])
        _git(r, "checkout", "-q", "-b", "side")
        with open(os.path.join(r, "s.txt"), "w", encoding="utf-8") as fh: fh.write("s")
        _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", f"side\n\n{TRAILER}")
        _git(r, "checkout", "-q", "main")
        _git(r, "merge", "--no-ff", "-q", "-m", "Merge side into main", "side")
        _, bad, _ = audit(r)
        check("merge-commit-exempt", [b[2] for b in bad], [])
        with open(os.path.join(r, "p.txt"), "w", encoding="utf-8") as fh: fh.write("p")
        _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", "plain, no trailer")
        _, bad2, _ = audit(r)
        check("non-merge-still-flagged", [b[2] for b in bad2], ["missing-trailer"])

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
