#!/usr/bin/env python3
import subprocess
import sys


def split_commands(scan):
    out, cur = [], []
    for tok in scan.replace("&&", " ; ").replace("||", " ; ").replace("|", " ; ").split():
        if tok == ";":
            out.append(cur)
            cur = []
        else:
            cur.append(tok)
    out.append(cur)
    return [c for c in out if c]


def push_targets(argv, current):
    positionals = [a for a in argv if not a.startswith("-")]
    refspecs = positionals[1:]
    if not refspecs:
        return [current] if current and current != "HEAD" else []
    targets = []
    for ref in refspecs:
        dst = ref.split(":", 1)[1] if ":" in ref else ref
        dst = dst.lstrip("+")
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        if dst == "HEAD":
            dst = current
        if dst:
            targets.append(dst)
    return targets


def pr_base(root, number):
    cmd = ["gh", "pr", "view"] + ([number] if number else []) + ["--json", "baseRefName", "-q", ".baseRefName"]
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--pr-base":
        print(pr_base(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
        return 0
    scan, current = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
    found = []
    for words in split_commands(scan):
        for i in range(len(words) - 1):
            if words[i] == "git" and words[i + 1] == "push":
                found += push_targets(words[i + 2:], current)
    print(" ".join(dict.fromkeys(found)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
