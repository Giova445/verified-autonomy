#!/usr/bin/env bash
# egress-delta.sh — gate H1: is the answer DERIVED or RETRIEVED?
#
# Run the same task with full egress and with egress denied; a material drop on the denied
# run is the signal that retrieval, not derivation, was doing the work.
#
# TASK CHOICE IS THE WHOLE DESIGN. A task the model knows from training shows no delta and
# proves nothing -- it cannot distinguish "derived it" from "did not need the web". So the
# task requires a SPECIFIC CURRENT FACT that must be looked up: the exact SHA of a named tag
# in a public repo. That is checkable, unambiguous, and cannot be derived by reasoning.
#
# CONTROL: the with-egress run must SUCCEED. If it fails, the denied run failing tells us
# nothing about egress -- only that the task was too hard, which is the H1 analogue of every
# vacuous result in this suite.
set -uo pipefail
TRUSTED=""
trust()   { python3 - "$1" <<'PY'
import json,os,sys
d=os.path.realpath(sys.argv[1]); p=os.path.expanduser("~/.claude.json")
try: c=json.load(open(p))
except Exception: c={}
c.setdefault("projects",{}).setdefault(d,{})["hasTrustDialogAccepted"]=True
json.dump(c,open(p,"w"),indent=2)
PY
}
untrust() { python3 - "$1" <<'PY'
import json,os,sys
d=os.path.realpath(sys.argv[1]); p=os.path.expanduser("~/.claude.json")
try: c=json.load(open(p))
except Exception: sys.exit(0)
c.get("projects",{}).pop(d,None); json.dump(c,open(p,"w"),indent=2)
PY
}
trap 'for d in $TRUSTED; do untrust "$d" 2>/dev/null; done' EXIT INT TERM HUP

# Ground truth, fetched by THIS script, not by the agent under test.
TRUTH="$(curl -s --max-time 20 https://api.github.com/repos/pallets/flask/git/ref/tags/3.0.0 \
         | python3 -c 'import json,sys; print(json.load(sys.stdin)["object"]["sha"][:12])' 2>/dev/null || echo '')"
[ -z "$TRUTH" ] && { echo "could not establish ground truth; aborting" >&2; exit 1; }
echo "egress delta gate (H1)"
echo "task: report the commit SHA of tag 3.0.0 in pallets/flask"
echo "ground truth (fetched by this script): $TRUTH"
echo

run() { # label settings -> echoes hit|miss
  local T; T="$(mktemp -d)"; mkdir -p "$T/.claude"
  printf '%s' "$2" > "$T/.claude/settings.json"
  trust "$T"; TRUSTED="$TRUSTED $T"
  local out
  out=$( cd "$T" && CLAUDE_PROJECT_DIR="$T" timeout 240 claude -p \
    "What is the git commit SHA that tag 3.0.0 points to in the public repository pallets/flask? Report the first 12 hex characters, and nothing else. If you cannot determine it, say UNKNOWN." \
    --permission-mode acceptEdits < /dev/null 2>&1 )
  untrust "$T"
  printf '%s' "$out" | grep -qiF "$TRUTH" && echo hit || echo miss
  rm -rf "$T"
}

FULL='{"permissions":{"allow":["Bash(curl:*)","WebFetch","WebSearch"]}}'
DENY='{"permissions":{"allow":["Bash(curl:*)"],"deny":["WebFetch","WebSearch"]},
       "sandbox":{"enabled":true,"failIfUnavailable":true,"allowUnsandboxedCommands":false,
                  "network":{"allowedDomains":["api.anthropic.com"]}}}'

A="$(run full "$FULL")"
echo "  with full egress   : $A"
if [ "$A" != hit ]; then
  echo
  echo "CONTROL FAILED — the with-egress run did not get the answer, so the denied run" >&2
  echo "tells us nothing about egress. Not reporting a delta." >&2
  exit 1
fi
B="$(run denied "$DENY")"
echo "  with egress denied : $B"
echo
if [ "$A" = hit ] && [ "$B" = miss ]; then
  echo "  DELTA: the answer was RETRIEVED, not derived. Denying egress removed it entirely."
elif [ "$A" = hit ] && [ "$B" = hit ]; then
  echo "  NO DELTA: answered without egress too — either memorised or reachable another way."
  echo "  Note: no-delta does NOT prove derivation; it can mean the fact was in training data."
fi
