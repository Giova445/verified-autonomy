#!/usr/bin/env python3
"""A1 — skill trigger/routing eval. Deterministic, no dependencies, CI-safe.

Ported from addyosmani/agent-skills' Tier 2, which is itself the one part of that repo with
no equivalent here: a lexical check that each skill's DESCRIPTION carries the vocabulary users
actually say, and that no two descriptions collide. A skill that never fires is worth nothing,
and until now this project had no way to know.

WHAT IT CANNOT DO, STATED FIRST. This is stemmed TF-IDF over descriptions. It is a lexical
approximation of routing and cannot judge semantics — the upstream README says the same about
its own. It catches the two failure modes that dominate real trigger bugs: a description
missing the words users say (false negative), and an over-broad description that outranks the
right skill (false positive). A Tier-2 failure usually means fix the description.

THE CONTROLS ARE THE POINT. "14/14 rank 1" is meaningless from a ranker that ranks everything
first. Two controls run before any score is reported, and the run aborts if either fails:
  NEGATIVE control — a deliberately mis-described skill must FAIL to rank 1 for its own prompts
  POSITIVE control — a correctly-described skill must rank 1
Together they prove the ranker discriminates in both directions.
"""
import json, math, os, re, sys

COLLIDE = 0.45   # cosine over stemmed description vectors
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STOP = set("a an the is are be to of for and or in on with when before after use uses using "
           "this that it its any all how what why not do does can may your you we our".split())

def stem(w):
    for suf in ("ing", "ies", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w

def toks(text):
    ws = re.findall(r"[a-z][a-z0-9]+", text.lower())
    return [stem(w) for w in ws if w not in STOP and len(w) > 2]

def load_skills(root):
    out = {}
    sk = os.path.join(root, "skills")
    for name in sorted(os.listdir(sk)):
        p = os.path.join(sk, name, "SKILL.md")
        if not os.path.isfile(p):
            continue
        desc = ""
        for line in open(p, encoding="utf-8", errors="replace"):
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        out[name] = desc
    return out

class Index:
    def __init__(self, docs):                      # docs: {name: text}
        self.names = list(docs)
        self.tf = {n: Counter(toks(docs[n])) for n in self.names}
        N = len(self.names)
        df = Counter()
        for n in self.names:
            for t in set(self.tf[n]):
                df[t] += 1
        self.idf = {t: math.log((N + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.vec = {n: self._vec(self.tf[n]) for n in self.names}

    def _vec(self, counter):
        v = {t: (1 + math.log(c)) * self.idf.get(t, math.log(len(self.names) + 1) + 1)
             for t, c in counter.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def rank(self, query):
        q = self._vec(Counter(toks(query)))
        scored = []
        for n in self.names:
            d = self.vec[n]
            s = sum(w * d.get(t, 0.0) for t, w in q.items())
            scored.append((s, n))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored

    def collisions(self, thresh):
        out = []
        for i, a in enumerate(self.names):
            for b in self.names[i + 1:]:
                va, vb = self.vec[a], self.vec[b]
                s = sum(w * vb.get(t, 0.0) for t, w in va.items())
                if s >= thresh:
                    out.append((round(s, 3), a, b))
        return sorted(out, reverse=True)

def evaluate(idx, fx, floor):
    """Two distinct failure modes, deliberately NOT merged into one number.

      WRONG   another skill outranked the right one -> descriptions overlap, fix wording
      NOSIG   the top score is 0.000, i.e. NO skill shares a single term with the prompt.
              The 'winner' there is just whichever name sorted first; the ranking is
              arbitrary. Reporting this as 'ranked #N' would imply an ordering that does
              not exist. NOSIG is the worse defect: the vocabulary is absent entirely.
    """
    hits = misses = 0
    failures = []
    for skill, prompts in fx["positives"].items():
        if skill not in idx.names:
            failures.append((skill, "<no such skill>", "NOSIG", "skill missing from tree"))
            misses += len(prompts); continue
        for p in prompts:
            ranked = idx.rank(p)
            if ranked[0][1] == skill and ranked[0][0] > 0:
                hits += 1
                continue
            misses += 1
            if ranked[0][0] == 0.0:
                failures.append((skill, p, "NOSIG",
                                 "no skill shares any term with this prompt"))
            else:
                pos = [n for _, n in ranked].index(skill) + 1
                failures.append((skill, p, "WRONG",
                                 f"ranked #{pos}, top was {ranked[0][1]} ({ranked[0][0]:.3f})"))
    neg_fail = []
    for p in fx["negatives"]:
        top = idx.rank(p)[0]
        if top[0] >= floor:
            neg_fail.append((p, top[1], round(top[0], 3)))
    return hits, misses, failures, neg_fail

# ---------------------------------------------------------------------------
# The ensemble, and why the headline is a failure SET and not a percentage.
#
# The first working version of this file reported "rank@1: 69.0%". Perturbing the
# tokenizer moved that to 71.4% (no stemming), 71.4% (no stopwords) and 83.3%
# (character 4-grams) WITHOUT touching a single skill description. A number that
# swings 14 points on an arbitrary choice inside the measuring instrument is a
# property of the instrument, not of the skills, and reporting it as a skill
# metric would be exactly the vacuous green this suite exists to prevent.
#
# So the tool runs four deliberately different rankers and reports the
# INTERSECTION of their failures. A prompt that misroutes under word-level TF-IDF,
# under unstemmed tokens, under no stopword list, AND under character 4-grams that
# never see a word boundary is not failing because of a tokenizer choice. It is
# failing because the description does not contain the vocabulary. Those are the
# findings. Prompts that fail under some rankers but not others are printed
# separately and explicitly labelled NOT reportable.
# ---------------------------------------------------------------------------
def _nostem(t):
    return [w for w in re.findall(r"[a-z][a-z0-9]+", t.lower())
            if w not in STOP and len(w) > 2]

def _nostop(t):
    return [stem(w) for w in re.findall(r"[a-z][a-z0-9]+", t.lower()) if len(w) > 2]

def _fourgram(t):
    s = re.sub(r"[^a-z ]", " ", t.lower())
    return [s[i:i + 4] for i in range(max(0, len(s) - 3))]

RANKERS = {"stemmed TF-IDF": None, "unstemmed": _nostem,
           "no stopwords": _nostop, "char 4-gram": _fourgram}

def main():
    global toks
    fx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures.json")
    fx = json.load(open(fx_path))
    skills = load_skills(ROOT)
    floor = float(os.environ.get("NEG_FLOOR", "0.2"))
    npos = sum(len(v) for v in fx["positives"].values())
    print(f"skill trigger/routing eval — {len(skills)} skills, {npos} positive prompts, "
          f"{len(fx['negatives'])} negatives\n")

    base_toks = toks
    probe = "systematic-debugging"
    if probe not in skills:
        print("  CONTROL SETUP FAILED: probe skill absent", file=sys.stderr); return 1

    # Controls run against EVERY ranker. A control that only holds for the one ranker
    # you happened to ship proves nothing about the other three.
    # The control prompt is built from the probe's OWN vocabulary, not from fixtures:
    # an earlier version used fixtures[probe][0] and the control "failed" while the ranker
    # was fine — that prompt is a genuine routing defect, which is what the EVAL reports.
    # Using it as the control conflated "is the ranker working" with "is the description
    # good", so a real finding masqueraded as a broken instrument and aborted the run.
    # A control must hold constant everything except the property under test.
    ctrl_prompt = " ".join(base_toks(skills[probe])[:8])
    broken = dict(skills)
    broken[probe] = "Miscellaneous helper for unrelated administrative paperwork tasks."
    for name, fn in RANKERS.items():
        toks = fn or base_toks
        pos = Index(skills).rank(ctrl_prompt)[0][1] == probe
        neg = Index(broken).rank(ctrl_prompt)[0][1] == probe
        print(f"  CONTROL {name:<16} good-ranks-1={pos}  mis-described-ranks-1={neg} (must be False)")
        if not pos or neg:
            toks = base_toks
            print(f"\n  CONTROLS FAILED for '{name}'. That ranker does not discriminate in both\n"
                  f"  directions, so its votes are meaningless. Refusing to report a result.",
                  file=sys.stderr)
            return 1
    toks = base_toks
    print("  all four rankers discriminate in both directions\n")

    per, fails = {}, {}
    for name, fn in RANKERS.items():
        toks = fn or base_toks
        h, m, f, neg_fail = evaluate(Index(skills), fx, floor)
        per[name] = (h, h + m, neg_fail)
        fails[name] = {(x[0], x[1]): x for x in f}
    toks = base_toks

    print("  rank@1 per ranker (spread shows how much of any single number is instrument):")
    for name, (h, t, _) in per.items():
        print(f"    {name:<16} {h}/{t} = {100.0*h/t:.1f}%")
    lo = min(100.0*h/t for h, t, _ in per.values())
    hi = max(100.0*h/t for h, t, _ in per.values())
    print(f"    spread: {hi-lo:.1f} points on tokenizer choice alone — do not quote a single figure\n")

    keys = [set(d) for d in fails.values()]
    inv, anyf = set.intersection(*keys), set.union(*keys)
    print(f"  FINDINGS — misroute under all {len(RANKERS)} rankers ({len(inv)}/{npos} prompts):")
    for sk_, p in sorted(inv):
        kind = fails["stemmed TF-IDF"][(sk_, p)][2]
        print(f"    {kind}  {sk_:<22} {p!r}")
    print(f"\n  NOT reportable — ranker-sensitive, {len(anyf-inv)} prompts:")
    for sk_, p in sorted(anyf - inv):
        who = [n for n in RANKERS if (sk_, p) in fails[n]]
        print(f"    {sk_:<22} {p!r}  (fails under {len(who)}/{len(RANKERS)})")

    # FLOOR CONTROL. "no negative scored above 0.2" is vacuous if no prompt of any kind
    # can reach 0.2 — a floor set above the achievable range silently passes everything.
    # So: measure what the POSITIVES score. The floor is only meaningful if positives
    # routinely clear it while negatives do not.
    toks = base_toks
    gidx = Index(skills)
    ptop = sorted(gidx.rank(pr)[0][0] for ps in fx["positives"].values() for pr in ps)
    clears = sum(1 for v in ptop if v >= floor)
    ntop = [gidx.rank(pr)[0][0] for pr in fx["negatives"]]
    print(f"  FLOOR CONTROL: positives clearing the {floor} floor: {clears}/{len(ptop)} "
          f"(median {ptop[len(ptop)//2]:.3f}, max {ptop[-1]:.3f})")
    print(f"                 negatives  max {max(ntop):.3f}")
    if clears * 2 < len(ptop):
        print(f"\n  FLOOR IS VACUOUS: fewer than half the positives reach {floor}, so "
              f"'no negative fired'\n  says nothing about discrimination.", file=sys.stderr)
        return 1

    nf = per["stemmed TF-IDF"][2]
    print()
    if nf:
        print(f"  negatives scoring above the {floor} floor (false triggers):")
        for p, n, s in nf:
            print(f"    {p!r} -> {n} ({s})")
    else:
        print(f"  negatives: none of {len(fx['negatives'])} scored above the {floor} floor")

    # Printed unconditionally. A threshold that finds nothing is indistinguishable from a
    # similarity function that returns zero for everything; showing the actual maxima makes
    # a degenerate metric visible instead of silently reassuring.
    pairs = Index(skills).collisions(0.0)[:5]
    print(f"\n  nearest description pairs (collision threshold {COLLIDE}):")
    for sim, a, b in pairs:
        print(f"    {sim:.3f}  {a}  <->  {b}" + ("  <== COLLISION" if sim >= COLLIDE else ""))
    if not [c for c in pairs if c[0] >= COLLIDE]:
        print(f"    none reach {COLLIDE}; highest real overlap is {pairs[0][0]:.3f}")

    cap = int(os.environ.get("MAX_INVARIANT_FAILURES", "-1"))
    if cap >= 0 and len(inv) > cap:
        print(f"\n  OVER BUDGET: {len(inv)} invariant failures > MAX_INVARIANT_FAILURES={cap}",
              file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
