#!/usr/bin/env python3
"""Shared helpers for the Stage 4b configuration evals.

Nothing here decides anything. Every helper that can fail returns a value the caller can
turn into a FINDING, because the alternative — raising, or returning a default — is how a
check quietly becomes a no-op. An unreadable file is not a pass.
"""
import json
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories a tree copy must never carry: they are large, or they are state that would
# make a control's temp tree behave differently from the real one.
COPY_IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", "*.pyc",
                                     ".claude-flow", ".agents")


def read_text(root, rel):
    """Return the file's text, or None if it cannot be read. None means FAIL CLOSED at
    the call site — never 'nothing to check here'."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def load_json(root, rel):
    """Return (obj, error_string). Exactly one of the two is None."""
    txt = read_text(root, rel)
    if txt is None:
        return None, f"{rel}: missing or unreadable"
    try:
        return json.loads(txt), None
    except ValueError as exc:
        return None, f"{rel}: unparseable JSON ({exc})"


def frontmatter(root, rel):
    """Parse a leading --- block into a flat dict.

    Deliberately not a YAML library: these checks must run in CI with no dependencies, and
    every frontmatter block in this repo is flat `key: value`. Returns None when there is
    no parseable block at all, which callers must treat as a finding.
    """
    txt = read_text(root, rel)
    if txt is None or not txt.startswith("---\n"):
        return None
    end = txt.find("\n---", 4)
    if end < 0:
        return None
    out = {}
    for line in txt[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key, val = line.split(":", 1)
            out[key.strip()] = val.strip()
    return out


def list_dirs(root, rel):
    base = os.path.join(root, rel)
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))


def list_files(root, rel, suffix):
    base = os.path.join(root, rel)
    if not os.path.isdir(base):
        return []
    return sorted(f for f in os.listdir(base) if f.endswith(suffix))


def run(cmd, cwd=None, timeout=900, stdin_text=None):
    """Run a command. Returns (returncode, combined output).

    A timeout or a missing binary comes back as a non-zero code and an output string that
    says so, so a check can report it rather than crash the whole run.
    """
    try:
        proc = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                              input=stdin_text, capture_output=True, text=True)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except OSError as exc:
        return 127, f"could not execute {cmd[0]}: {exc}"


CHECK_COUNT = re.compile(r"\((\d+) checks?")


def reported_check_count(output):
    """The last '(N checks)' a suite printed, or None.

    None is the fabricated-receipt case: a suite that exits 0 having verified nothing.
    Callers must treat it as a failure, never as 'no data'.
    """
    hits = CHECK_COUNT.findall(output)
    return int(hits[-1]) if hits else None


def copy_tree(dest, root=ROOT):
    shutil.copytree(root, dest, ignore=COPY_IGNORE, symlinks=True)
    return dest


def write_file(root, rel, text, mode=None):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if mode is not None:
        os.chmod(path, mode)
    return path


def replace_once(root, rel, old, new):
    """Substitute a literal exactly once. Returns True when it actually changed the file.

    A control whose edit silently matched nothing would leave the tree clean and then
    report the eval as a failed control, so the caller asserts on this.
    """
    txt = read_text(root, rel)
    if txt is None or old not in txt:
        return False
    write_file(root, rel, txt.replace(old, new, 1))
    return True


def drop_lines(root, rel, needle):
    """Remove every line containing `needle`. Returns the number removed."""
    txt = read_text(root, rel)
    if txt is None:
        return 0
    keep = [ln for ln in txt.splitlines(True) if needle not in ln]
    removed = len(txt.splitlines(True)) - len(keep)
    if removed:
        write_file(root, rel, "".join(keep))
    return removed
