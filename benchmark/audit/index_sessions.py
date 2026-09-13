#!/usr/bin/env python3
"""Index every Claude Code and Codex session into one JSONL, cheaply.

Reading 7.3 GB of transcripts into a context window is impossible, so this builds an
index first and the deep reads are aimed afterwards. Per session it records: where it
ran, when, how big, what the user first asked, and how many CORRECTION SIGNALS it
contains.

WHY CORRECTION SIGNALS ARE THE RANKING KEY

A durable learning is almost never in the part where things went well. It is in the
moment the user said "no", "that's wrong", "I already told you", "never do that". Those
are mechanically findable, and they concentrate the transcripts worth reading by hand.
Ranking by size would surface the longest sessions; ranking by corrections surfaces the
ones that taught something.

The signal is a proxy, not a measurement: a session can teach without a correction, and a
matched phrase can be the user quoting someone else. Treated as a sampling aid, never as
a count of lessons.
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude", "projects")
CODEX = os.path.join(HOME, ".codex", "sessions")

# Phrases a user types when correcting an agent. Deliberately narrow: generic negatives
# ("no") match constantly in normal prose and would rank noise to the top.
CORRECTION = re.compile(
    r"\b(that'?s wrong|you'?re wrong|not what i (asked|said|wanted)|i already (told|said)"
    r"|never do|don'?t do that|stop doing|you (broke|deleted|missed)|wrong repo"
    r"|didn'?t work|doesn'?t work|still (broken|failing|wrong)|revert"
    r"|you were supposed to|why did you|i said|prohibited|do not)\b", re.I)

FRUSTRATION = re.compile(r"\b(wtf|ffs|again\?|seriously|come on|no no no)\b", re.I)


def head_lines(path, n=400):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= n:
                    break
                out.append(line)
    except OSError:
        pass
    return out


def text_of(content):
    """Message content is either a string or a list of typed blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif isinstance(b, str):
                parts.append(b)
        return " ".join(parts)
    return ""


def scan_claude(path):
    rec = {"agent": "claude", "path": path, "bytes": os.path.getsize(path),
           "mtime": os.path.getmtime(path), "cwd": None, "first_user": None,
           "user_msgs": 0, "corrections": 0, "frustration": 0}
    for line in head_lines(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if rec["cwd"] is None and d.get("cwd"):
            rec["cwd"] = d["cwd"]
        if d.get("type") == "user":
            msg = d.get("message") or {}
            t = text_of(msg.get("content") if isinstance(msg, dict) else msg).strip()
            if t and not t.startswith("<") and rec["first_user"] is None:
                rec["first_user"] = t[:300]
    # Correction counting streams the WHOLE file as raw text -- no JSON parse, no full
    # load. Matching raw means a phrase inside a tool result can match too; accepted,
    # because the alternative is parsing gigabytes to gain a little precision on a proxy.
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"type":"user"' in line or '"type": "user"' in line:
                    rec["user_msgs"] += 1
                    rec["corrections"] += len(CORRECTION.findall(line))
                    rec["frustration"] += len(FRUSTRATION.findall(line))
    except OSError:
        pass
    return rec


def scan_codex(path):
    rec = {"agent": "codex", "path": path, "bytes": os.path.getsize(path),
           "mtime": os.path.getmtime(path), "cwd": None, "first_user": None,
           "user_msgs": 0, "corrections": 0, "frustration": 0}
    for line in head_lines(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") if isinstance(d.get("payload"), dict) else d
        for key in ("cwd", "workdir", "working_directory"):
            if rec["cwd"] is None and isinstance(p, dict) and p.get(key):
                rec["cwd"] = p[key]
        if isinstance(p, dict) and p.get("role") == "user" and rec["first_user"] is None:
            t = text_of(p.get("content")).strip()
            if t and not t.startswith("<"):
                rec["first_user"] = t[:300]
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"role":"user"' in line or '"role": "user"' in line:
                    rec["user_msgs"] += 1
                    rec["corrections"] += len(CORRECTION.findall(line))
                    rec["frustration"] += len(FRUSTRATION.findall(line))
    except OSError:
        pass
    return rec


def main():
    out_path = sys.argv[1]
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for root, _dirs, files in os.walk(CLAUDE):
            for f in files:
                if f.endswith(".jsonl"):
                    out.write(json.dumps(scan_claude(os.path.join(root, f))) + "\n")
                    n += 1
                    if n % 200 == 0:
                        print(f"  {n} indexed", file=sys.stderr, flush=True)
        for root, _dirs, files in os.walk(CODEX):
            for f in files:
                if f.endswith(".jsonl"):
                    out.write(json.dumps(scan_codex(os.path.join(root, f))) + "\n")
                    n += 1
                    if n % 200 == 0:
                        print(f"  {n} indexed", file=sys.stderr, flush=True)
    print(f"indexed {n} sessions -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
