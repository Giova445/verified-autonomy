#!/usr/bin/env python3
"""Extract labeled test-state transitions from the Kim et al. (FSE 2021) corpus.

Both classes come from the corpus's OWN isActiveTestDisabled / isCOTestDisabled flags. I do
not label anything here, which is the entire reason the resulting numbers are worth more than
the in-house gold sets:

  label="disabling"  enabled -> disabled   (the positives)
  label="neutral"    enabled -> enabled, content changed   (the paired negatives)

The neutral class is what makes a confusion matrix possible. Without it, a rule that fires on
every diff scores 100% recall and nothing detects that it is useless -- the failure mode
CAS/NSA built the discrimination rate for and OWASP built Youden's J for.
"""
import json, glob, os, sys

src = sys.argv[1] if len(sys.argv) > 1 else "."
want = sys.argv[2] if len(sys.argv) > 2 else "both"

for f in glob.glob(os.path.join(src, "*.json")):
    project = os.path.basename(f).split("@")[0]
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for sig, states in d.items():
        st = [s for s in states if isinstance(s, dict)]
        try:
            st.sort(key=lambda s: s.get("time") or 0)
        except Exception:
            pass
        for a, b in zip(st, st[1:]):
            was = bool(a.get("isActiveTestDisabled")) or bool(a.get("isCOTestDisabled"))
            now = bool(b.get("isActiveTestDisabled")) or bool(b.get("isCOTestDisabled"))
            ca = (a.get("content") or "").strip()
            cb = (b.get("content") or "").strip()
            if not ca or not cb or ca == cb:
                continue
            if not was and now:
                label = "disabling"
            elif not was and not now:
                label = "neutral"
            else:
                continue
            if want != "both" and want != label:
                continue
            print(json.dumps({"project": project, "sig": sig, "label": label,
                              "before": ca, "after": cb,
                              "file": b.get("filePath") or "T.java",
                              "commit": b.get("commitId")}))
