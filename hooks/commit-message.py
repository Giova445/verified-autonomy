#!/usr/bin/env python3
import re
import sys

COMMIT = re.compile(r"\bgit(?:\s+-C\s+\S+)?\s+commit\b")
HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
SEPARATOR = re.compile(r"&&|\|\||;|\||\n")
TRAILER = re.compile(r"(^|[^a-z])co-authored-by:", re.I)


def messages(cmd):
    for m in COMMIT.finditer(cmd):
        rest = cmd[m.start():]
        first, _, tail = rest.partition("\n")
        h = HEREDOC.search(first)
        if h:
            body = re.split(r"^\s*%s\s*$" % re.escape(h.group(1)), tail, maxsplit=1, flags=re.M)[0]
            yield first + "\n" + body
        else:
            yield SEPARATOR.split(rest, maxsplit=1)[0]


def carries_trailer(cmd):
    return any(TRAILER.search(msg) for msg in messages(cmd))


CONTROLS = [
    ("an -m trailer is caught", "git commit -m x -m 'Co-Authored-By: a <a@b>'", True),
    ("a heredoc trailer is caught", "git commit -F - <<'EOF'\nfix\n\nCo-Authored-By: a <a@b>\nEOF", True),
    ("a grep for the trailer beside a commit is not", "git commit -m fix && git log --format=%B | grep -i '^co-authored-by:'", False),
    ("text after the heredoc ends is not", "git commit -F - <<EOF\nfix\nEOF\necho co-authored-by: x", False),
    ("a plain commit is not", "git commit -m 'fix: thing'", False),
    ("git -C dir commit is still judged", "git -C repo commit -m 'x' -m 'co-authored-by: a'", True),
]


def selftest():
    ok = 0
    for name, cmd, want in CONTROLS:
        got = carries_trailer(cmd)
        ok += got == want
        print("  %s  %s" % ("ok  " if got == want else "FAIL", name))
    print("\ncommit-message (%d checks)" % len(CONTROLS))
    return 0 if ok == len(CONTROLS) else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-test"]:
        sys.exit(selftest())
    sys.exit(0 if carries_trailer(sys.argv[1] if len(sys.argv) > 1 else "") else 1)
