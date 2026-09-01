#!/usr/bin/env python3
"""A2 — structural validators for the repo, plus their positive controls.

Three validators, each answering a question nothing in this repo previously asked:

  frontmatter  every skills/*/SKILL.md declares name + description, and name matches
               its directory. A skill whose name disagrees with its folder is invisible
               to the loader and to the A1 routing eval alike.
  links        every RELATIVE markdown link resolves to a file that exists.
  manifest     every gate row in gate-manifest.json names a script, that script exists
               and is executable, and every verification script is claimed by a row.
               Both directions: a dangling row is a gate whose evidence was deleted;
               an unclaimed script is evidence nobody is reading.

THE CONTROLS ARE THE POINT. Passing on the clean tree proves nothing — a validator
that returns "ok" unconditionally passes the clean tree too. So --self-test copies the
tree, breaks exactly one thing per validator, and asserts that THAT validator fails and
reports the break. A validator that cannot fail is not shipped.
"""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQUIRED_KEYS = ("name", "description")

def _fm(path):
    """Parse the leading --- block. Deliberately not a YAML library: the check must run
    in CI with no dependencies, and the frontmatter here is flat key: value."""
    txt = open(path, encoding="utf-8").read()
    if not txt.startswith("---\n"):
        return None
    end = txt.find("\n---", 4)
    if end < 0:
        return None
    out = {}
    for line in txt[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out

def frontmatter(root):
    bad = []
    sk = os.path.join(root, "skills")
    dirs = sorted(d for d in os.listdir(sk) if os.path.isdir(os.path.join(sk, d))) \
        if os.path.isdir(sk) else []
    if not dirs:
        return ["skills/ contains no skill directories at all"]
    for d in dirs:
        p = os.path.join(sk, d, "SKILL.md")
        rel = os.path.relpath(p, root)
        if not os.path.exists(p):
            bad.append(f"{rel}: missing"); continue
        fm = _fm(p)
        if fm is None:
            bad.append(f"{rel}: no --- frontmatter block"); continue
        for k in REQUIRED_KEYS:
            if not fm.get(k):
                bad.append(f"{rel}: frontmatter key '{k}' missing or empty")
        if fm.get("name") and fm["name"] != d:
            bad.append(f"{rel}: name '{fm['name']}' != directory '{d}'")
    return bad

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

def links(root):
    """Ratcheted, like the manifest's unbacked rows. 8 links point at documents that do not
    exist anywhere in the repo; repairing those needs a judgment about what they were meant
    to reference, which is not this validator's job. Recording the count means the existing
    breakage stays printed on every run while any NEW dead link fails the build. An
    allowlist of specific paths was the alternative and is worse: it goes stale silently
    and lets a file be renamed into an already-allowed path."""
    bad = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "node_modules", "__pycache__")]
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(dp, fn)
            for m in LINK.finditer(open(p, encoding="utf-8", errors="replace").read()):
                t = m.group(1).split()[0].strip()
                if t.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                t = t.split("#")[0]
                if not t:
                    continue
                tgt = os.path.normpath(os.path.join(dp, t))
                if os.path.exists(tgt):
                    continue
                # Three distinct defects, deliberately distinguished because they have
                # three different fixes. The common one is a path written as if from the
                # repo root inside a file that is not at the root: GitHub resolves markdown
                # links relative to the CONTAINING file, so it 404s for readers while
                # looking correct to whoever wrote it.
                if os.path.exists(os.path.join(root, t.lstrip("./"))):
                    why = "broken as written, but resolves from the REPO ROOT — link is root-relative"
                elif os.path.commonpath([os.path.abspath(tgt), root]) != root:
                    why = "resolves OUTSIDE the repo"
                else:
                    why = "target does not exist anywhere"
                bad.append(f"{os.path.relpath(p, root)} -> {t}\n          {why}")
    return bad

def manifest(root):
    """Correspondence in BOTH directions, which is the only version that detects drift.

      row -> script   the named path exists and (for .sh) is executable
      script -> row   the script's own '# gate: <ID>' header agrees with the row that
                      claims it. Existence alone is too weak: renaming a gate, or pointing
                      a row at the wrong script, leaves every path resolving fine.
      orphans         a verification script no manifest row claims is evidence nobody reads
      unbacked        rows with no artifact at all are RATCHETED against a recorded
                      baseline, so the existing ones stay visible and new ones cannot land
    """
    bad = []
    mp = os.path.join(root, "benchmark", "manifest", "gate-manifest.json")
    if not os.path.exists(mp):
        return ["benchmark/manifest/gate-manifest.json: missing"]
    try:
        doc = json.load(open(mp))
        gates = doc["gates"]
    except Exception as e:
        return [f"gate-manifest.json: unparseable ({e})"]

    claimed, unbacked = set(), []
    for g in gates:
        name = g.get("gate", "<unnamed>")
        gid = name.split()[0]
        refs = g.get("script") or g.get("evidence_doc")
        if not refs:
            unbacked.append(name); continue
        for one in ([refs] if isinstance(refs, str) else refs):
            fp = os.path.join(root, one)
            if not os.path.exists(fp):
                bad.append(f"gate '{name}': '{one}' does not exist"); continue
            if one.endswith(".sh") and not os.access(fp, os.X_OK):
                bad.append(f"gate '{name}': '{one}' is not executable")
            claimed.add(one)
            if one.startswith("benchmark/verification/"):
                m = re.search(r"^# gate: (.+)$", open(fp, encoding="utf-8",
                                                      errors="replace").read(), re.M)
                if not m:
                    bad.append(f"{one}: no '# gate:' declaration to check the row against")
                elif gid not in [x.strip() for x in m.group(1).split(",")] \
                        and m.group(1).strip() != "shared":
                    bad.append(f"gate '{name}': row claims {one}, but that script declares "
                               f"'# gate: {m.group(1).strip()}'")

    vdir = os.path.join(root, "benchmark", "verification")
    if os.path.isdir(vdir):
        for fn in sorted(os.listdir(vdir)):
            rel = f"benchmark/verification/{fn}"
            if not fn.endswith(".sh") or rel in claimed:
                continue
            txt = open(os.path.join(vdir, fn), encoding="utf-8", errors="replace").read()
            if re.search(r"^# gate: shared$", txt, re.M):
                continue   # declared shared infrastructure, not a per-gate probe
            bad.append(f"{rel}: exists but no manifest row claims it")

    base = doc.get("unbacked_baseline", {}).get("count")
    if base is None:
        bad.append("gate-manifest.json: no unbacked_baseline recorded; the ratchet is off")
    elif len(unbacked) > base:
        new_ones = [u for u in unbacked if u not in doc["unbacked_baseline"].get("gates", [])]
        bad.append(f"REGRESSION unbacked rows grew {base} -> {len(unbacked)}: {', '.join(new_ones)}")
    return bad

def links_ratchet(root):
    bad = links(root)
    mp = os.path.join(root, "benchmark", "manifest", "gate-manifest.json")
    base = None
    if os.path.exists(mp):
        try: base = json.load(open(mp)).get("dead_link_baseline", {}).get("count")
        except Exception: pass
    if base is None:
        return bad + ["no dead_link_baseline recorded; the link ratchet is off"]
    if len(bad) > base:
        return bad + [f"REGRESSION dead links grew {base} -> {len(bad)}: a NEW broken link was added"]
    if len(bad) < base:
        bad.append(f"NOTE dead links fell {base} -> {len(bad)}; lower the baseline to lock it in")
    return bad

VALIDATORS = {"frontmatter": frontmatter, "links": links_ratchet, "manifest": manifest}
RATCHETED = {"links"}   # report baseline without failing; only growth fails

# --------------------------------------------------------------------------- controls
def _break_frontmatter(t):
    d = sorted(os.listdir(os.path.join(t, "skills")))[0]
    p = os.path.join(t, "skills", d, "SKILL.md")
    s = open(p).read()
    open(p, "w").write(re.sub(r"^name: .*$", "name: definitely-not-this-directory",
                              s, count=1, flags=re.M))
    return f"renamed 'name:' in skills/{d}/SKILL.md so it disagrees with its directory"

def _break_links(t):
    p = os.path.join(t, "benchmark", "structure", "CONTROL-FIXTURE.md")
    open(p, "w").write("[dangling](./no-such-file-xyz.md)\n")
    return "added a markdown file linking to ./no-such-file-xyz.md"

def _break_manifest(t):
    mp = os.path.join(t, "benchmark", "manifest", "gate-manifest.json")
    d = json.load(open(mp))
    d["gates"][0]["script"] = "benchmark/verification/deleted-by-control.sh"
    json.dump(d, open(mp, "w"), indent=2)
    return "pointed the first gate row at a script that does not exist"

BREAKERS = {"frontmatter": _break_frontmatter, "links": _break_links,
            "manifest": _break_manifest}
# The string the control's new finding must contain, so "detected" means "detected THIS".
TOKEN = {"frontmatter": "definitely-not-this-directory",
         "links": "no-such-file-xyz.md",
         "manifest": "deleted-by-control.sh"}

def self_test():
    print("structural validators — positive controls\n")
    ok = True
    for name in VALIDATORS:
        with tempfile.TemporaryDirectory() as td:
            t = os.path.join(td, "tree")
            shutil.copytree(ROOT, t, ignore=shutil.ignore_patterns(".git", "node_modules",
                                                                  "__pycache__", "*.pyc"))
            clean = VALIDATORS[name](t)
            what = BREAKERS[name](t)
            broken = VALIDATORS[name](t)
            # The control asks for a NEW finding that NAMES the break. Counting was the
            # first criterion and it was wrong: breaking a manifest row REPLACED its
            # "no script field" finding with "script does not exist", so the count held at
            # 40 and a working validator was reported as a failed control. Counting also
            # cannot tell a finding about the break from any other finding that appeared.
            new = [b for b in broken if b not in clean]
            grew = any(TOKEN[name] in b for b in new)
            print(f"  {name}")
            print(f"    clean tree      : {len(clean)} finding(s)")
            print(f"    control break   : {what}")
            print(f"    after the break : {len(broken)} finding(s)  detected={grew}")
            if new:
                print(f"    new finding     : {new[0]}")
            if not grew:
                print(f"    !! CONTROL FAILED: breaking the tree did not change the verdict.")
                ok = False
    print()
    return 0 if ok else 1

def main():
    if "--self-test" in sys.argv:
        return self_test()
    # Exit code semantics. RATCHETED validators report their recorded baseline every run —
    # those findings are printed but do NOT fail the build, or CI would be red from the
    # first commit and the ratchet would buy nothing. Only a REGRESSION past the baseline,
    # or any finding at all from a non-ratcheted validator, fails.
    rc = 0
    for name, fn in VALIDATORS.items():
        bad = fn(ROOT)
        ratcheted = name in RATCHETED
        regress = [b for b in bad if b.startswith("REGRESSION")]
        tag = "" if not bad else ("  (baseline, not a failure)" if ratcheted and not regress
                                  else "  FAIL")
        print(f"  {name:<12} {len(bad)} finding(s){tag}")
        for b in bad:
            print(f"      {b}")
        if regress or (bad and not ratcheted):
            rc = 1
    print("\n  " + ("STRUCTURE OK" if rc == 0 else "STRUCTURE FAILED"))
    return rc

if __name__ == "__main__":
    sys.exit(main())
