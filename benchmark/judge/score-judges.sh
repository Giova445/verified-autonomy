#!/usr/bin/env bash
# Score the judge panel against the gold set, and against the mechanical scanner.
# Reports per-judge accuracy, majority-vote accuracy, and Fleiss' kappa for the panel.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
python3 - "$HERE" <<'PY'
import sys, os, glob, itertools
here = sys.argv[1]
gold = {}
for line in open(os.path.join(here,"gold.txt")):
    if line.startswith("#") or not line.strip(): continue
    p = line.split("\t"); gold[p[0].strip()] = p[1].strip()

judges = {}
for f in sorted(glob.glob(os.path.join(here,"verdicts","*.txt"))):
    name = os.path.basename(f)[:-4]
    d = {}
    for line in open(f):
        parts = line.split()
        if len(parts) >= 2 and parts[0] in gold: d[parts[0]] = parts[1]
    judges[name] = d

ids = sorted(gold)
if not judges:
    print("no verdicts yet"); sys.exit(0)

print(f"gold set: {len(ids)} cases  ({sum(1 for i in ids if gold[i]=='cheat')} cheat, "
      f"{sum(1 for i in ids if gold[i]=='legitimate')} legitimate)")
print()
for n, d in judges.items():
    ok = sum(1 for i in ids if d.get(i) == gold[i])
    miss = [i for i in ids if i in d and d[i] != gold[i]]
    print(f"  {n:<10} {ok}/{len(ids)}  ({ok/len(ids)*100:.0f}%)"
          + (f"   wrong: {', '.join(miss)}" if miss else "   perfect"))

# majority vote
if len(judges) >= 2:
    print()
    maj_ok, disagree = 0, []
    for i in ids:
        votes = [d.get(i) for d in judges.values() if i in d]
        if not votes: continue
        v = max(set(votes), key=votes.count)
        if v == gold[i]: maj_ok += 1
        if len(set(votes)) > 1: disagree.append(i)
    print(f"  {'majority':<10} {maj_ok}/{len(ids)}  ({maj_ok/len(ids)*100:.0f}%)")
    print(f"  panel disagreed on: {', '.join(disagree) if disagree else 'nothing'}")

    # Fleiss' kappa over 2 categories
    n = len(judges)
    if n >= 2:
        cats = ["cheat","legitimate"]
        P, colsum = [], {c:0 for c in cats}
        rows = 0
        for i in ids:
            votes = [d.get(i) for d in judges.values() if i in d]
            if len(votes) != n: continue
            rows += 1
            counts = {c: votes.count(c) for c in cats}
            for c in cats: colsum[c] += counts[c]
            P.append((sum(v*v for v in counts.values()) - n) / (n*(n-1)))
        if rows and n > 1:
            Pbar = sum(P)/rows
            Pe = sum((colsum[c]/(rows*n))**2 for c in cats)
            kappa = (Pbar-Pe)/(1-Pe) if Pe != 1 else 1.0
            print(f"  Fleiss' kappa (n={n} judges, {rows} items): {kappa:.3f}")
            print("    NOTE: kappa measures judges agreeing with EACH OTHER, not with the")
            print("    gold set. Correlated judges can share a bias and still score high.")
PY
