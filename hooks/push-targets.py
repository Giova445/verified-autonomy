#!/usr/bin/env python3
import fnmatch
import os
import re
import sys

ALL = "\0every-branch"
DEFAULT_PROTECTED = ("main", "master")
PUSH_VALUE_OPTS = frozenset(("--repo", "--receive-pack", "--exec", "-o", "--push-option"))
MERGE_VALUE_OPTS = frozenset(("-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email", "--match-head-commit"))
API_MERGE = re.compile(r"(?:^|/)(?:repos/([^/{}]+)/([^/{}]+)/)?pulls/([^/]+)/merge/?$")


def load_protected(root):
    path = os.path.join(root, ".claude", "protected-branches")
    if not os.path.exists(path):
        return list(DEFAULT_PROTECTED)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return list(DEFAULT_PROTECTED)
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def is_protected(branch, protected):
    return any(fnmatch.fnmatchcase(branch, p) for p in protected)


def find_git_dir(start):
    p = os.path.abspath(start)
    while True:
        g = os.path.join(p, ".git")
        if os.path.isdir(g):
            return g
        if os.path.isfile(g):
            try:
                with open(g, encoding="utf-8") as f:
                    line = f.readline().strip()
            except (OSError, UnicodeDecodeError):
                return None
            if line.startswith("gitdir:"):
                return os.path.normpath(os.path.join(p, line[len("gitdir:"):].strip()))
            return None
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def current_branch(cwd, git_dir=None):
    d = os.path.join(cwd, git_dir) if git_dir else find_git_dir(cwd)
    if not d:
        return None
    try:
        with open(os.path.join(d, "HEAD"), encoding="utf-8") as f:
            head = f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else None


def push_dsts(args, current):
    positional, everything, tags_only, has_repo_opt, i = [], False, False, False, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a in ("--all", "--mirror"):
            everything = True
        elif a == "--tags":
            tags_only = True
        elif a in PUSH_VALUE_OPTS:
            has_repo_opt = has_repo_opt or a == "--repo"
            i += 1
        elif a.startswith("--repo="):
            has_repo_opt = True
        elif not a.startswith("-"):
            positional.append(a)
        i += 1
    if everything:
        return [ALL]
    refspecs = positional if has_repo_opt else positional[1:]
    if not refspecs:
        return [] if tags_only else [current()]
    dsts = []
    for ref in refspecs:
        src, colon, dst = ref.lstrip("+").partition(":")
        target = dst if colon else src
        if target.startswith("refs/tags/"):
            continue
        for prefix in ("refs/heads/", "heads/"):
            if target.startswith(prefix):
                target = target[len(prefix):]
        dsts.append(current() if target in ("HEAD", "@") else target)
    return dsts


def push_denial(args, protected, cwd, git_dir, branch=None):
    if not protected:
        return None
    for dst in push_dsts(args, lambda: branch or current_branch(cwd, git_dir)):
        if dst == ALL:
            return "this push touches every branch, protected ones included"
        if dst and ("*" in dst and any(fnmatch.fnmatchcase(p, dst) for p in protected) or is_protected(dst, protected)):
            return "push to protected branch '%s' is the operator's decision; open a pull request instead" % dst
    return None


def merge_selector(args):
    selector = repo = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-R", "--repo"):
            repo = args[i + 1] if i + 1 < len(args) else None
            i += 1
        elif a.startswith("--repo="):
            repo = a[len("--repo="):]
        elif a in MERGE_VALUE_OPTS:
            i += 1
        elif not a.startswith("-") and selector is None:
            selector = a
        i += 1
    return selector, repo


def api_merge(args):
    method = None
    for i, a in enumerate(args):
        if a in ("-X", "--method") and i + 1 < len(args):
            method = args[i + 1]
        elif a.startswith("--method="):
            method = a[len("--method="):]
        elif a.startswith("-X") and len(a) > 2:
            method = a[2:]
    if method and method.upper() == "GET":
        return None
    for a in args:
        m = None if a.startswith("-") else API_MERGE.search(a)
        if m:
            return m.group(3), (m.group(1) + "/" + m.group(2) if m.group(1) else None)
    return None


def pr_base(selector, repo, cwd):
    import subprocess
    cmd = ["gh", "pr", "view"] + ([selector] if selector else []) + (["-R", repo] if repo else [])
    cmd += ["--json", "baseRefName", "-q", ".baseRefName"]
    env = dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    try:
        p = subprocess.run(cmd, cwd=cwd if os.path.isdir(cwd) else None, capture_output=True, text=True,
                           timeout=6, stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def merge_denial(args, protected, cwd):
    if args[:2] == ["pr", "merge"]:
        selector, repo = merge_selector(args[2:])
    else:
        target = api_merge(args[1:])
        if not target:
            return None
        selector, repo = target
    base = pr_base(selector, repo, cwd)
    if not base:
        return "cannot determine the base branch of the pull request being merged, so it may be protected"
    if is_protected(base, protected):
        return "merging into protected branch '%s' is the operator's decision" % base
    return None


CONTROLS = [
    ("plain push to a feature branch", ["origin", "feature/x"], "feature/t", ["feature/x"]),
    ("push to main", ["origin", "main"], "feature/t", ["main"]),
    ("HEAD:main", ["origin", "HEAD:main"], "feature/t", ["main"]),
    ("HEAD on main resolves to the current branch", ["origin", "HEAD"], "main", ["main"]),
    ("HEAD on a feature branch is fine", ["origin", "HEAD"], "feature/t", ["feature/t"]),
    ("plus force refspec", ["origin", "+main"], "feature/t", ["main"]),
    ("delete refspec", ["origin", ":main"], "feature/t", ["main"]),
    ("full ref name", ["origin", "x:refs/heads/main"], "feature/t", ["main"]),
    ("source main into a feature branch is fine", ["origin", "main:feature/x"], "feature/t", ["feature/x"]),
    ("--delete lists the branch", ["--delete", "origin", "main"], "feature/t", ["main"]),
    ("--all touches everything", ["--all", "origin"], "feature/t", [ALL]),
    ("--mirror touches everything", ["--mirror"], "feature/t", [ALL]),
    ("bare push is the current branch", [], "main", ["main"]),
    ("remote-only push is the current branch", ["origin"], "main", ["main"]),
    ("tags alone touch no branch", ["--tags", "origin"], "main", []),
    ("a glob destination is kept for matching", ["origin", "refs/heads/*:refs/heads/*"], "feature/t", ["*"]),
    ("force flags do not change targets", ["--force-with-lease", "-u", "origin", "feature/x"], "main", ["feature/x"]),
    ("a push option value is not a refspec", ["-o", "main", "origin", "feature/x"], "feature/t", ["feature/x"]),
    ("merge selector after flags", ["--squash", "99"], None, ("99", None)),
    ("merge selector before flags", ["99", "--squash"], None, ("99", None)),
    ("merge body value is not the selector", ["--body", "text", "12"], None, ("12", None)),
    ("merge without selector", ["--squash"], None, (None, None)),
    ("merge repo flag", ["-R", "o/r", "7"], None, ("7", "o/r")),
    ("api merge path", ["-X", "PUT", "repos/o/r/pulls/9/merge"], None, ("9", "o/r")),
    ("api GET is not a merge", ["-X", "GET", "repos/o/r/pulls/9/merge"], None, None),
]
GLOBS = [("release/1.2", ["release/*"], True), ("main", ["release/*"], False), ("main", ["main", "master"], True)]
GLOB_PUSHES = [
    ("a wildcard destination reaches main", ["origin", "refs/heads/*:refs/heads/*"], True),
    ("a feature wildcard does not reach main", ["origin", "refs/heads/feature/*:refs/heads/feature/*"], False),
    ("a release wildcard reaches release/*", ["origin", "refs/heads/release/*:refs/heads/release/*"], True),
]


def controls():
    for name, args, current, want in CONTROLS:
        if isinstance(want, list):
            yield name, push_dsts(args, lambda: current), want
        elif want is None or name.startswith("api"):
            yield name, api_merge(args), want
        else:
            yield name, merge_selector(args), want
    for branch, patterns, want in GLOBS:
        yield "%s matches %s" % (branch, patterns), is_protected(branch, patterns), want
    for name, args, want in GLOB_PUSHES:
        yield name, push_denial(args, ["main", "master", "release/*"], ".", None, "feature/t") is not None, want


def selftest():
    results = list(controls())
    for name, got, want in results:
        print("  %s  %s" % ("ok  " if got == want else "FAIL", name))
        if got != want:
            print("        got %r want %r" % (got, want))
    print("\npush-targets (%d checks)" % len(results))
    return 0 if all(g == w for _, g, w in results) else 1


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:2] == ["--self-test"] else 2)
