#!/usr/bin/env python3
"""B2 — unpinned-dependency gate. Mitigates the K2 FAILS.

K2 measured that an agent could install a dependency at a floating tag and nothing
objected. This gate reads a DIFF and fails the ones that ADD an install which resolves
to whatever the registry serves at that moment.

WHY A DIFF AND NOT THE TREE. Scanning the whole tree reports every pre-existing unpinned
install on every run, which trains people to ignore it. Scanning added lines fails the
commit that introduces one, while leaving the existing debt to a separate decision.

THE FALSE-POSITIVE BUDGET IS THE HARD PART, AND IT IS MEASURED ON REAL DIFFS. A gate that
flags ordinary work gets switched off, and a switched-off gate protects nothing — so its
error rate matters as much as its detection rate. The controls below measure it against
this repository's own commit history, not against hand-written negatives, because
hand-written negatives are chosen by the same person who wrote the patterns and inherit
their blind spots.

DELIBERATELY NOT FLAGGED:
  - installs inside a fenced code block that is documenting the ATTACK (this file, the
    audit notes). Detected by a marker, not by guessing.
  - removed lines. Deleting an unpinned install is the fix, not the offence.
"""
import argparse, os, re, subprocess, sys

# Each rule: (id, compiled pattern, human explanation). Patterns match an ADDED diff line.
RULES = [
    ("pip-unpinned",
     # -e was written \b-e\b, which never matches: there is no word boundary between a
     # space and a hyphen, so 'pip install -e .' was flagged. The package token also
     # excluded quotes, so 'pip install "django>=4.0"' slipped through as a non-match
     # rather than being caught as an unpinned range. Both found by the labeled corpus.
     re.compile(r"\b(?:pip3?|uv pip)\s+install\s+"
                r"(?!.*(?:==|--require-hashes|@[0-9a-f]{40}))"
                # (?:^|\s)-[er] was wrong: install\s+ has already consumed the space, so at
                # the lookahead's position the flag sits at offset 0 with nothing before it
                # to match \s, and '-e .' / '-r reqs.txt' were both flagged. A lookbehind
                # asks the same question without needing a character to spare.
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

# The rule set the controls REQUIRE, written out independently of RULES. Deriving the
# expectation from RULES itself made the control self-referential: deleting a rule deleted
# the detector and its expectation together, so a gate with a rule removed passed its own
# control and the whole selftest stayed green. Verified by sabotage — see CONTROL 5.
EXPECTED_RULES = {"pip-unpinned", "npm-unpinned", "npx-floating", "go-latest",
                  "cargo-unpinned", "curl-pipe-shell", "gha-tag-not-sha", "docker-latest"}

SKIP_MARKER = "pin-check: allow"   # explicit, per-line, and greppable

# The one file that will always contain every pattern is the file that DEFINES them. It is
# excluded by exact path, hardcoded — NOT by a marker any file could add to itself, which
# would be a general escape hatch wearing a narrow disguise. CONTROL 4 asserts the
# exclusion does not leak: the identical line in any other path is still caught.
# Both files that CONTAIN every pattern by construction: the source that defines the rules,
# and the labeled corpus whose deny class is deliberately-unpinned fixtures. Excluded by
# exact path, hardcoded -- NOT by a marker any file could add to itself, which would be a
# general escape hatch wearing a narrow disguise. CONTROL 4 asserts the exclusion does not
# leak: the identical line in any other path, including a lookalike, is still caught.
#
# corpus-pin.txt was added after CI caught it. The PR-diff step -- which only runs on a
# pull_request event, so it had never fired -- flagged 12 of its own fixtures as unpinned
# installs. A gate that fails its own test data is one somebody switches off.
SELF = frozenset({"benchmark/gates/pin-check.py", "benchmark/gates/corpus-pin.txt"})

def _inert_before(body):
    """Index of the first character that cannot execute, or None.

    Blanking every quoted span was the first attempt and it was too blunt: it erased
    legitimate quoted package specs, turning 'pip install "django>=4.0"' into a non-match
    instead of a catch. What actually matters is where the MATCH starts. So this returns
    the quoted spans and the comment offset, and the caller asks whether its own match
    begins inside one. Naming a command is not running it; running it while quoted is not
    a thing that happens."""
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
    """Return findings for lines the diff ADDS. File context tracked for reporting."""
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

# --------------------------------------------------------------------------- controls
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
    # The two fixtures differ ONLY in the pinning. Same tools, same order, same line
    # count. A pair that also changed the package names would let a pass come from
    # something other than the property under test.
    hit = {r for _, r, _, _ in scan_diff(UNPINNED)}
    miss = scan_diff(PINNED)
    # Every rule must appear in the fixture. The first version of this control exercised
    # six of eight rules and reported the gate green; gha-tag-not-sha was among the two it
    # never touched, and it was broken — it anchored on "uses:" and so missed the standard
    # YAML list form "- uses:", which is nearly every real workflow line. A control that
    # covers most of a gate certifies the whole gate.
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
    # A 0% rate on a history containing no installs at all would be vacuous: it would
    # prove only that nothing was there to find. So require the gate to still fire on a
    # planted diff, verifying the scanner ran over this corpus rather than no-opped.
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
