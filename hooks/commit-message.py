#!/usr/bin/env python3
import json
import os
import re
import sys

DEFAULT_KEYS = ["Co-Authored-By"]
MAX_FILE = 1 << 20
TAKES_VALUE = {"--message": "m", "--file": "F", "--trailer": "t"}


def forbidden_keys(root):
    claude = os.path.join(root, ".claude")
    listing = os.path.join(claude, "forbidden-trailers")
    if os.path.exists(listing):
        try:
            with open(listing, encoding="utf-8") as f:
                lines = [l.strip() for l in f.read().splitlines()]
        except (OSError, UnicodeDecodeError):
            return DEFAULT_KEYS
        keys = [l.rstrip(":").strip() for l in lines if l and not l.startswith("#")]
        return keys or DEFAULT_KEYS
    settings = os.path.join(claude, "settings.json")
    if not os.path.exists(settings):
        return None
    try:
        with open(settings, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return DEFAULT_KEYS
    attribution = data.get("attribution") if isinstance(data, dict) else None
    if isinstance(attribution, dict) and attribution.get("commit") == "":
        return DEFAULT_KEYS
    return None


def message_parts(args):
    parts, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        if a.startswith("--"):
            key, eq, value = a.partition("=")
            kind = TAKES_VALUE.get(key)
            if kind:
                if not eq:
                    i += 1
                    value = args[i] if i < len(args) else ""
                parts.append((kind, value))
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 1):
                if ch in "mF":
                    value = a[j + 1:]
                    if not value:
                        i += 1
                        value = args[i] if i < len(args) else ""
                    parts.append((ch, value))
                    break
                if ch in "cCt":
                    i += 0 if a[j + 1:] else 1
                    break
                if ch in "Su":
                    break
        i += 1
    return parts


def file_text(name, stdin, cwd, written):
    if name in ("-", "/dev/stdin"):
        return stdin
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(name)))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(MAX_FILE)
    except OSError:
        return written.get(path)


def trailer_pattern(keys, separators):
    return re.compile(r"^[ \t]*(?:%s)[ \t]*%s" % ("|".join(re.escape(k) for k in keys), separators), re.I | re.M)


def commit_denial(args, stdin, cwd, written, keys):
    lines = trailer_pattern(keys, ":")
    trailer = trailer_pattern(keys, "[:=]")
    for kind, value in message_parts(args):
        text = file_text(value, stdin, cwd, written) if kind == "F" else value
        if text and (trailer if kind == "t" else lines).search(text):
            return "this commit carries a forbidden %s trailer; this repo does not allow it" % keys[0]
    return None


def selftest():
    keys = ["Co-Authored-By"]
    trailer = "Co-Authored-By: a <a@b>"
    written = {"/w/msg.txt": "fix\n\n" + trailer}
    cases = [
        ("a second -m paragraph is a trailer", ["-m", "x", "-m", trailer], None, True),
        ("a multi-line -m value is read whole", ["-m", "y\n\n" + trailer], None, True),
        ("--trailer is a trailer", ["--amend", "-m", "x", "--trailer", "Co-authored-by: a <a@b>"], None, True),
        ("--message=value is read", ["--message=x\n\n" + trailer], None, True),
        ("-am clusters take the message", ["-am", "x\n\n" + trailer], None, True),
        ("-F - reads stdin", ["-F", "-"], "fix\n\n" + trailer + "\n", True),
        ("-F file reads a file written earlier in the command", ["-F", "/w/msg.txt"], None, True),
        ("a trailer key with no value still counts", ["-m", "x\n\nCo-Authored-By:"], None, True),
        ("the words inside a sentence are not a trailer", ["-m", "fix: parse Co-Authored-By: lines"], None, False),
        ("a mention without a colon is not a trailer", ["-m", "fix: handle co-authored-by header"], None, False),
        ("a plain message is fine", ["-m", "fix: thing"], None, False),
        ("-F - with no stdin text is fine", ["-F", "-"], None, False),
        ("an unrelated trailer is fine", ["-m", "x\n\nSigned-off-by: a <a@b>"], None, False),
    ]
    ok = 0
    for name, args, stdin, want in cases:
        got = commit_denial(args, stdin, "/w", written, keys) is not None
        ok += got == want
        print("  %s  %s" % ("ok  " if got == want else "FAIL", name))
    print("\ncommit-message (%d checks)" % len(cases))
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:2] == ["--self-test"] else 2)
