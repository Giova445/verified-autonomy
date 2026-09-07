#!/usr/bin/env python3
"""Gate: does docs/sdlc-playbook.md still describe the repository that exists?

The playbook map is the one artifact in this repo that claims things ABOUT the other
artifacts — which stage is covered, at what enforcement layer, and what command proves it.
Prose that makes claims about executable things is the easiest kind of receipt to falsify,
because nothing runs it. A stage can be quietly deleted, a Verify command can rot, and a
stated check count can drift, and the document keeps reading as authoritative.

WHAT THIS CHECKS

  A. coverage      Every playbook stage is either mapped or listed under "Not implemented,
                   and why". A stage that appears in neither is silently uncovered, which
                   reads identically to a stage nobody needed.
  B. verify-runs   Every runnable **Verify** command in the map actually exits 0.
  C. counts        Every check count a Verify row states matches what the command reports.
                   This is the row that rots first: selftest.sh grew 31 -> 34 and the
                   document kept saying 31.
  D. layer-honesty A stage claiming Layer 2 (enforcement) or 3 (adjudication) must name an
                   artifact that is not purely markdown. A document cannot enforce anything;
                   claiming layer 2 for a template is the overclaim this repo exists to stop.

WHAT IT DELIBERATELY DOES NOT CHECK

Whether the prose is true. It decides presence, exit codes and arithmetic — the
mechanically decidable part. A stage whose Verify command exits 0 while testing the wrong
thing passes this gate. Said plainly rather than implied, because the same limit is
recorded for intent/check-chain.sh and pretending otherwise is how a checker becomes
theatre.

WHY THE STAGE LIST IS WRITTEN OUT HERE

PLAYBOOK_STAGES is a literal. It is NOT read from docs/sdlc-playbook.md. If it were, a
stage deleted from the document would delete its own coverage requirement and the gate
would stay green having checked less — the expectation-derived-from-subject defect recorded
in commit a25e83d, where a sibling gate's control took its fixture count from len(RULES).
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = os.path.join("docs", "sdlc-playbook.md")

# The playbook's stages and every lettered sub-stage, as published at
# claude.com/blog/the-ai-native-sdlc-playbook. Declared independently of the document under
# test. Update this when the PLAYBOOK changes, never to match what the repo implements.
#
# A first version had 11 keys and collapsed 3a-3e into "3" and 4a into "4". That was not the
# playbook's numbering; it was the DOCUMENT's own inferred numbering, copied here -- so the
# gate was checking the map against the map's own scheme. A block titled "Stage 3" satisfied
# it while saying nothing about skills (3c) or subagents (3e). Re-keyed from the source.
PLAYBOOK_STAGES = {
    "1":  "Plan — capture as intent.md",
    "2":  "Design — requirements and design collapse into one session (spec.md)",
    "3a": "Build — plan mode as the default starting point (plan.md)",
    "3b": "Build — CLAUDE.md as machine-readable institutional context",
    "3c": "Build — skills as institutional knowledge (skills/<name>/SKILL.md)",
    "3d": "Build — hooks as build-time guardrails (settings.json, hook scripts)",
    "3e": "Build — parallel sessions and subagents (agents/<name>.md)",
    "4a": "Test — give Claude a feedback loop (verifier commands, healthy output)",
    "4b": "Test — continuous evals in CI (evals/, agent-evals.yml)",
    "5a": "Deploy — AI in the PR review loop (REVIEW.md)",
    "5b": "Deploy — hooks as approval gates",
    "5c": "Deploy — CI/CD integration, MCP deployment, tiered autonomy",
    "6a": "Maintain — control-band monitoring (bands.yaml)",
    "6b": "Maintain — recurring codebase scans",
    "6c": "Maintain — Claude on call",
}

# [a-e], not [a-c]: the playbook goes to 3e. A first version stopped at c, so "### Stage 3e"
# was never parsed as a block and a "3d, 4a" Playbook row matched "3" and "4a" -- both
# sub-stages read as uncovered while the document attested them. Found by the re-keyed gate
# reporting 3d and 3e missing from a document that had just gained a 3e block.
STAGE_RE = re.compile(r"^###\s+Stage\s+([0-9]+[a-e]?)\b(.*)$", re.M)
ROW_RE = re.compile(r"^\|\s*\*\*(\w[\w -]*)\*\*\s*\|\s*(.*?)\s*\|?\s*$", re.M)
CODE_RE = re.compile(r"`([^`]+)`")
COUNT_RE = re.compile(r"(\d+)\s*checks?|→\s*(\d+)\s|\((\d+)\)")
RUNNABLE = ("bash ", "python3 ", "./bin/", "bin/")

# Commands the CONTROLS skip. Not a correctness exclusion -- the real audit still runs
# them. Controls B and C target `bash bin/ambiguity selftest`, which takes a second; running
# the 40-second suites four more times inside temp copies made selftest.sh exceed ten
# minutes, and a suite nobody will wait for is a suite that gets skipped.
SLOW = ("bash tests/orchestration-test.sh",)

# NEVER executed by this gate, at any depth. selftest.sh runs this gate's own --self-test,
# so auditing it re-enters here: each nested run copied the whole repo to a temp dir and
# ran commands inside it. Under a few concurrent audits that reached load average 39 and
# left orphaned selftest.sh processes with PPID 1 -- the same runaway class recorded in
# benchmark/verification/ORPHAN-INCIDENT.md.
#
# Coverage is not lost. selftest.sh's check count is pinned independently in
# evals/expected.json, which is the eval that already owns it, and evals/run.py fails when
# the real count drifts from the pin. The count check simply lives there instead of here.
NO_RUN = ("bash selftest.sh",)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def parse_stages(text):
    """Map stage-id -> {heading, rows{field: value}} for every '### Stage N' block."""
    out, marks = {}, list(STAGE_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end]
        rows = {k.strip().lower(): v for k, v in ROW_RE.findall(body)}
        out[m.group(1)] = {"heading": m.group(2).strip(), "rows": rows, "body": body}
    return out


def not_implemented_ids(text):
    """Stage ids named under the 'Not implemented, and why' section."""
    i = text.find("## Not implemented, and why")
    if i < 0:
        return set()
    j = text.find("\n## ", i + 4)
    section = text[i: j if j > 0 else len(text)]
    return set(re.findall(r"Stage\s+([0-9]+[a-e]?)\b", section))


def stated_count(cell, cmd):
    """The check count a Verify cell states for one command, or None."""
    tail = cell.split(f"`{cmd}`", 1)[-1][:40] if f"`{cmd}`" in cell else cell
    m = COUNT_RE.search(tail)
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def run(root, cmd, timeout=420):
    try:
        p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timed out"
    return p, (p.stdout or "") + (p.stderr or "")


def audit(root, run_commands=True, skip_slow=False, only=None):
    """Return a list of findings. Empty means the map matches the repository."""
    bad = []
    path = os.path.join(root, DOC)
    if not os.path.exists(path):
        return [f"{DOC}: missing — the playbook map is the artifact under test"]
    text = read(root, DOC)
    stages = parse_stages(text)
    skipped = not_implemented_ids(text)

    # A. coverage. A block attests the sub-stages named in its **Playbook** row
    # ("3d, 4a"); a block with no such row attests whatever its heading number is. The
    # explicit row exists because the document's heading numbers were inferred by its
    # author before the source was available, and several blocks attest more than one
    # playbook sub-stage (the gate block is both 3d hooks and 4a feedback loop).
    attested = set()
    for sid, st in stages.items():
        row = st["rows"].get("playbook", "")
        ids = re.findall(r"\b([1-6][a-e]?)\b", row)
        attested.update(ids if ids else [sid])
    for sid in sorted(PLAYBOOK_STAGES):
        if sid in attested or sid in skipped:
            continue
        bad.append(f"A. stage {sid} ({PLAYBOOK_STAGES[sid]}) is neither attested by any "
                   f"block's **Playbook** row nor listed under 'Not implemented, and why' "
                   f"— silently uncovered")

    for sid, st in sorted(stages.items()):
        rows = st["rows"]

        # D. layer honesty
        layer = rows.get("layer", "")
        claims_enforcement = re.search(r"\*\*([23])\*\*|(?<!\w)([23])(?!\w)", layer)
        if claims_enforcement:
            # Scan the WHOLE stage block, not just the Artifact row. The first version read
            # only Artifact and reported stages 2 and 3 as overclaiming, because each names
            # its executable part in a different row ("Layer 2 part": bin/ambiguity). Two
            # false positives out of two findings in that class -- and a gate that flags
            # correct work is one somebody switches off, which protects nothing.
            arts = CODE_RE.findall(st["body"]) + re.findall(r"\]\(([^)]+)\)", st["body"])
            arts = [a for a in arts if "/" in a or a.endswith((".py", ".sh", ".json", ".yaml"))]
            nonmd = [a for a in arts if not a.endswith(".md")]
            if arts and not nonmd:
                bad.append(f"D. stage {sid} claims layer {claims_enforcement.group(0)} but "
                           f"every artifact it names is markdown — a document does not enforce")

        # B / C. the Verify row
        cell = rows.get("verify", "")
        if not cell:
            continue
        for cmd in CODE_RE.findall(cell):
            cmd = cmd.strip()
            if not cmd.startswith(RUNNABLE) or "<" in cmd:
                continue          # prose, or a placeholder like <chain-dir>
            if cmd in NO_RUN:
                continue
            if not run_commands or (skip_slow and cmd in SLOW):
                continue
            if only is not None and cmd not in only:
                continue   # controls run ONLY the commands they target
            p, out = run(root, cmd)
            if p is None:
                bad.append(f"B. stage {sid}: `{cmd}` {out}")
                continue
            if p.returncode != 0:
                bad.append(f"B. stage {sid}: `{cmd}` exited {p.returncode}, "
                           f"but the map states it as the proof for this stage")
                continue
            want = stated_count(cell, cmd)
            if want is None:
                continue
            got = [int(n) for n in re.findall(r"\((\d+) checks?\)", out)]
            if got and want not in got:
                bad.append(f"C. stage {sid}: the map says `{cmd}` reports {want} checks; "
                           f"it reports {got[-1]}")
    return bad


# --------------------------------------------------------------------------- controls
# HERMETIC. Each control writes a MINIMAL docs/sdlc-playbook.md into a temp directory and
# audits that. It does not copy the repository.
#
# The first version did copy the whole tree, and control B/C then ran real Verify commands
# inside the copy. selftest.sh runs this gate, so those runs re-entered here; a few
# concurrent audits took the machine to load average 39 and left orphaned selftest.sh
# processes with PPID 1. A control that can take down the host is not a control worth
# having, and copying a repo to test a markdown parser was never the property under test.
#
# Each control breaks exactly one thing and requires the finding that NAMES that break.
# Counting findings is not enough: a break that replaces one finding with another leaves
# the total unchanged, which is how a working validator was once reported as a failed
# control (commit a25e83d).
import tempfile

EXPECTED_CLASSES = {"A", "B", "C", "D"}   # declared independently of the audit() body

# Every stage listed so control A starts from zero coverage findings, and one stage
# carrying a runnable Verify row for B and C to target.
_STAGES_MD = "\n".join(
    f"### Stage {sid} — fixture\n\n|  |  |\n|---|---|\n"
    f"| **Artifact** | [`bin/verify`](../bin/verify) |\n"
    f"| **Layer** | **2.** enforced |\n"
    for sid in sorted(PLAYBOOK_STAGES))

BASE_DOC = _STAGES_MD + (
    "\n### Stage 6a — fixture with a proof\n\n|  |  |\n|---|---|\n"
    "| **Artifact** | [`bin/verify`](../bin/verify) |\n"
    "| **Layer** | **2.** enforced |\n"
    "| **Verify** | `bash -c 'echo \"(12 checks)\"'` → 12 checks |\n"
    "\n## Not implemented, and why\n\nnothing.\n")


def _fixture(tmp, doc_text):
    os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
    with open(os.path.join(tmp, DOC), "w", encoding="utf-8") as fh:
        fh.write(doc_text)
    return tmp


def _break_A(doc):
    """Delete a mapped stage outright. It is then neither mapped nor excused."""
    m = [x for x in STAGE_RE.finditer(doc) if x.group(1) == "6b"][0]
    end = next((x.start() for x in STAGE_RE.finditer(doc) if x.start() > m.start()), len(doc))
    return doc[:m.start()] + doc[end:], "6b", "removed the Stage 6b block from the map"


def _break_B(doc):
    """Point a Verify row at a command that fails."""
    return (doc.replace("""`bash -c 'echo "(12 checks)"'`""", "`bash -c 'exit 3'`"),
            "exit 3", "pointed a Verify row at a command that exits 3")


def _break_C(doc):
    """State a check count the command does not report."""
    return doc.replace("→ 12 checks", "→ 999 checks"), "999", \
        "claimed the command reports 999 checks"


def _break_D(doc):
    """Claim enforcement for a stage whose only artifact is a document."""
    return (doc.replace("| **Artifact** | [`bin/verify`](../bin/verify) |",
                        "| **Artifact** | [`README.md`](../README.md) |", 1),
            "does not enforce",
            "claimed layer 2 for a stage whose only artifact is markdown")


BREAKERS = {"A": _break_A, "B": _break_B, "C": _break_C, "D": _break_D}


def self_test():
    print("playbook coverage — controls\n")
    if set(BREAKERS) != EXPECTED_CLASSES:
        print(f"  !! CONTROL SET CHANGED: expected {sorted(EXPECTED_CLASSES)}, "
              f"got {sorted(BREAKERS)}", file=sys.stderr)
        return 1
    ok, n = True, 0
    for cls in sorted(BREAKERS):
        with tempfile.TemporaryDirectory() as td:
            clean = audit(_fixture(td, BASE_DOC))
            broken_doc, token, what = BREAKERS[cls](BASE_DOC)
            broken = audit(_fixture(td, broken_doc))
            new = [b for b in broken if b not in clean]
            hit = [b for b in new if b.startswith(f"{cls}.") and token in b]
            n += 1
            print(f"  control {cls}: {what}")
            print(f"    clean {len(clean)} finding(s) -> broken {len(broken)}   "
                  f"detected={bool(hit)}")
            print(f"    {hit[0][:150]}" if hit
                  else f"    !! CONTROL FAILED: no {cls}. finding naming {token!r}")
            ok = ok and bool(hit)
    print(f"\n  playbook coverage ({n} checks)")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()
    fast = "--fast" in sys.argv
    findings = audit(ROOT, run_commands=not fast)
    print(f"playbook coverage — {len(PLAYBOOK_STAGES)} stages declared"
          + ("  (--fast: Verify commands not run)" if fast else ""))
    if not findings:
        print("  the map matches the repository")
        return 0
    for f in findings:
        print(f"  {f}")
    print(f"\n  {len(findings)} finding(s) — the map claims something the repo does not do")
    return 1


if __name__ == "__main__":
    sys.exit(main())
