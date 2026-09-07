#!/usr/bin/env python3
"""Fixed-seed sample: all positives plus N negatives. Reproducibility is the point."""
import json, random, sys
src = sys.argv[1]; n_neg = int(sys.argv[2]) if len(sys.argv) > 2 else 300
random.seed(20260828)
rows = [l for l in open(src)]
pos = [l for l in rows if json.loads(l)["label"] == "disabling"]
neg = [l for l in rows if json.loads(l)["label"] == "neutral"]
random.shuffle(neg)
sel = pos + neg[:n_neg]
random.shuffle(sel)
sys.stdout.writelines(sel)
