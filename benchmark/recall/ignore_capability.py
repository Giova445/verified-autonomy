"""@Ignore CAPABILITY CHECK — NOT a recall measurement.

The corpus's isActiveTestDisabled flag is populated for only 2 of 15 projects, and neither
uses @Ignore. So the third-party label cannot answer "does the detector see @Ignore?".

This uses real transitions from the other 13 projects where @Ignore appears in the corpus's
own parsed activeAnnotations. But the judgment "@Ignore added => test disabled" is MINE, not
the corpus's. That makes this a capability check on real code, not third-party recall, and it
does not escape circularity the way the 112 corpus-labeled cases do. Labeled accordingly.
"""
import json, glob, os, sys
out=[]
for f in glob.glob("/tmp/kim/raw/data-03/*.json"):
    proj=os.path.basename(f).split("@")[0]
    if proj in ("orientdb","incubator-pinot"): continue      # keep the labeled set separate
    try: d=json.load(open(f))
    except Exception: continue
    for sig, states in d.items():
        st=[s for s in states if isinstance(s,dict)]
        try: st.sort(key=lambda s: s.get("time") or 0)
        except Exception: pass
        for a,b in zip(st, st[1:]):
            aa=set(a.get("activeAnnotations") or [])
            ba=set(b.get("activeAnnotations") or [])
            a_ign=any("@Ignore" in x for x in aa)
            b_ign=any("@Ignore" in x for x in ba)
            ca=(a.get("content") or "").strip(); cb=(b.get("content") or "").strip()
            if not ca or not cb or ca==cb: continue
            if not a_ign and b_ign:
                out.append({"project":proj,"label":"disabling","before":ca,"after":cb})
            elif not a_ign and not b_ign:
                out.append({"project":proj,"label":"neutral","before":ca,"after":cb})
import random
random.seed(20260828)
pos=[o for o in out if o["label"]=="disabling"]
neg=[o for o in out if o["label"]=="neutral"]
random.shuffle(neg)
sel=pos+neg[:200]
random.shuffle(sel)
for o in sel: print(json.dumps(o))
sys.stderr.write(f"@Ignore-added transitions: {len(pos)} across {len(set(p['project'] for p in pos))} projects; negatives sampled {len(neg[:200])} of {len(neg)}\n")
