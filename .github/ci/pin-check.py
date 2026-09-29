#!/usr/bin/env python3
import argparse, os, re, subprocess, sys

RULES = [
    ("pip-unpinned",
     re.compile(r"\b(?:pip3?|uv pip)\s+install\s+"
                r"(?!.*(?:==|--require-hashes|@[0-9a-f]{40}))"
                r"(?!.*(?<![\w-])-[er](?=\s))"
                r"['\"]?[A-Za-z0-9._\[\]-]+"),
     "pip install without == or --require-hashes resolves to the newest release"),
    ("npm-unpinned",
     re.compile(r"\bnpm\s+(?:i|install|add)\s+(?!.*--save-exact)(?!.*\b\S+@\d)[A-Za-z0-9@._/-]+"),
     "npm install without an exact version resolves to the newest satisfying release"),
    ("npx-floating",
     re.compile(r"\bnpx\s+(?:-y\s+)?\S*@(?:latest|next|canary|beta|\*)"),
     "npx @latest fetches and executes whatever the registry serves right now"),
    ("go-latest",
     re.compile(r"\bgo\s+install\s+\S+@(?:latest|master|main)\b"),
     "go install @latest is not reproducible"),
    ("cargo-unpinned",
     re.compile(r"\bcargo\s+install\s+(?!.*--version)(?!.*--locked)[A-Za-z0-9._-]+"),
     "cargo install without --version or --locked"),
    ("curl-pipe-shell",
     re.compile(r"\bcurl\b[^|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b"),
     "curl | sh executes an unverified remote script"),
    ("gha-tag-not-sha",
     re.compile(r"^\s*-?\s*uses:\s*[\w.-]+/[\w.-]+@(?!\b[0-9a-f]{40}\b)\S+"),
     "GitHub Action pinned to a mutable tag; tags can be repointed, SHAs cannot"),
    ("docker-latest",
     re.compile(r"^\s*(?:FROM|image:)\s+\S+:latest\b|^\s*(?:FROM|image:)\s+[^\s:@]+\s*$"),
     "container image without a tag or digest resolves to :latest"),
]

EXPECTED_RULES = {"pip-unpinned", "npm-unpinned", "npx-floating", "go-latest",
                  "cargo-unpinned", "curl-pipe-shell", "gha-tag-not-sha", "docker-latest"}

SKIP_MARKER = "pin-check: allow"

SELF = frozenset({".github/ci/pin-check.py"})

def _inert_before(body):
    spans, quote, start, cut = [], None, 0, None
    for k, ch in enumerate(body):
        if quote:
            if ch == quote:
                spans.append((start, k)); quote = None
        elif ch in "'\"":
            quote, start = ch, k
        elif ch == "#" and cut is None:
            cut = k
    if quote:
        spans.append((start, len(body)))
    return spans, cut

def _is_inert(body, pos):
    spans, cut = _inert_before(body)
    if cut is not None and pos > cut:
        return True
    return any(a < pos < b for a, b in spans)

def scan_diff(text):
    out, path = [], "<unknown>"
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]; continue
        if path in SELF:
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        if SKIP_MARKER in body:
            continue

        for rid, pat, why in RULES:
            m = pat.search(body)
            if m and not _is_inert(body, m.start()):
                out.append((path, rid, body.strip()[:110], why))
                break
    return out

def diff_for(ref):
    return subprocess.run(["git", "show", "--format=", "--unified=0", ref],
                          capture_output=True, text=True).stdout

PINNED = """--- a/setup.sh
+++ b/setup.sh
@@ -1,0 +2,6 @@
+pip install requests==2.32.3
+pip install --require-hashes -r requirements.lock
+npm install --save-exact lodash@4.17.21
+npx cowsay@1.6.0 hi
+go install golang.org/x/tools/cmd/goimports@v0.24.0
+cargo install ripgrep --version 14.1.0 --locked
+      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
+FROM python:3.12.5-slim@sha256:cafebabe
"""
UNPINNED = """--- a/setup.sh
+++ b/setup.sh
@@ -1,0 +2,6 @@
+pip install requests
+npm install lodash
+npx ruflo@latest mcp start
+go install golang.org/x/tools/cmd/goimports@latest
+cargo install ripgrep
+curl -sSL https://example.test/i.sh | sh
+      - uses: actions/checkout@v4
+FROM python:latest
"""

def self_test(fp_budget=10.0, sample=60):
    ok = True
    n = 0
    def check(label, got, want):
        nonlocal ok, n
        n += 1
        print(f"    {label:<50} {got}  (expect {want})")
        if got != want:
            ok = False

    print("  CONTROL 1 — the same installs, pinned and unpinned, one line per rule")
    hit = {r for _, r, _, _ in scan_diff(UNPINNED)}
    miss = scan_diff(PINNED)
    check("every expected rule fires on its fixture", hit, EXPECTED_RULES)
    check("no rule was removed from RULES", {r for r, _, _ in RULES}, EXPECTED_RULES)
    check("silent on the pinned equivalents", [f[1] for f in miss], [])

    print("  CONTROL 2 — removed lines are not offences")
    rem = scan_diff(UNPINNED.replace("\n+", "\n-"))
    check("deleting an unpinned install is not flagged", len(rem), 0)

    print("  CONTROL 4 — the self-exclusion is narrow")
    hdr = "--- a/x\n+++ b/%s\n@@ -1,0 +1,1 @@\n+pip install requests\n"
    for own in sorted(SELF):
        check(f"skipped: {own}", len(scan_diff(hdr % own)), 0)
    check("the same line elsewhere is still caught", len(scan_diff(hdr % "src/setup.sh")), 1)
    for own in sorted(SELF):
        check(f"lookalike not skipped: x/{own}", len(scan_diff(hdr % ("x/" + own))), 1)

    print(f"  CONTROL 3 — false positives on this repo's real commits (budget {fp_budget}%)")
    revs = subprocess.run(["git", "rev-list", "--max-count", str(sample), "HEAD"],
                          capture_output=True, text=True).stdout.split()
    if len(revs) < 10:
        print("    !! fewer than 10 commits available; the FP rate would be noise")
        return 1
    flagged, detail = 0, []
    for r in revs:
        f = scan_diff(diff_for(r))
        if f:
            flagged += 1
            detail.append((r[:9], f[0][0], f[0][1], f[0][2]))
    rate = 100.0 * flagged / len(revs)
    print(f"    {flagged}/{len(revs)} real commits flagged = {rate:.1f}%")
    for r, p, rid, body in detail:
        print(f"      {r}  {rid:<16} {p}")
        print(f"                 {body}")
    check("false-positive rate within budget", rate <= fp_budget, True)
    check("scanner still fires after the corpus run", len(scan_diff(UNPINNED)) > 0, True)
    print(f"\n  unpinned-dependency gate ({n} checks)")
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--rev", help="check one commit (default: staged + unstaged diff)")
    ap.add_argument("--range", dest="rng", help="check a commit range, e.g. main...HEAD")
    ap.add_argument("--fp-budget", type=float, default=10.0)
    a = ap.parse_args()
    if a.self_test:
        print("unpinned-dependency gate — controls\n")
        return self_test(a.fp_budget)
    if a.rev:
        text = diff_for(a.rev)
    elif a.rng:
        text = subprocess.run(["git", "diff", "--unified=0", a.rng],
                              capture_output=True, text=True).stdout
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = subprocess.run(["git", "diff", "HEAD", "--unified=0"],
                              capture_output=True, text=True).stdout
    findings = scan_diff(text)
    if not findings:
        print("  no unpinned installs added")
        return 0
    for path, rid, body, why in findings:
        print(f"  {rid:<17} {path}")
        print(f"    {body}")
        print(f"    {why}")
    print(f"\n  {len(findings)} unpinned install(s) added — add an exact version, a digest,")
    print("  or mark the line 'pin-check: allow' with a reason.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
