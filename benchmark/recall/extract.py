#!/usr/bin/env python3
"""Extract enabled->disabled test transitions from the Kim et al. FSE 2021 corpus.

Positives come from the corpus's OWN isActiveTestDisabled / isCOTestDisabled flags, not from
any judgment of mine. That is the property that makes the resulting recall number worth
anything: the labels predate this project and were made for a different purpose.
"""
import json, glob, os, sys

src = sys.argv[1] if len(sys.argv) > 1 else "."
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
            if not was and now:
                print(json.dumps({
                    "project": project, "sig": sig,
                    "before": a.get("content") or "", "after": b.get("content") or "",
                    "path": b.get("filePath") or "T.java", "commit": b.get("commitId"),
                }))
