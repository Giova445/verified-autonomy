import json, re, subprocess, sys
RE = sys.argv[1]
hit = miss = 0
missed_examples = []
for line in open("/tmp/transitions.jsonl"):
    t = json.loads(line)
    added = "\n".join("+"+l for l in (t["after"] or "").splitlines())
    removed = "\n".join("-"+l for l in (t["before"] or "").splitlines())
    a = len(re.findall(RE, added))
    r = len(re.findall(RE, removed))
    if a > r: hit += 1
    else:
        miss += 1
        if len(missed_examples) < 4:
            first = (t["after"] or "").strip().splitlines()[:2]
            missed_examples.append(" | ".join(x.strip() for x in first)[:88])
tot = hit + miss
print(f"  detected {hit}/{tot}  recall = {hit/tot*100:.1f}%")
p = hit/tot; import math
z=1.96; d=1+z*z/tot; c=(p+z*z/(2*tot))/d; h=z*math.sqrt(p*(1-p)/tot+z*z/(4*tot*tot))/d
print(f"  95% Wilson CI [{max(0,c-h)*100:.1f}%, {min(1,c+h)*100:.1f}%]")
if missed_examples:
    print("  examples missed:")
    for e in missed_examples: print("    ", e)
