#!/usr/bin/env bash
# doublefork-cap.sh — I1b, the half that production found and the gate missed.
#
# I1b measured the harness's OWN background path and concluded "backgrounded work is capped
# by agent-session lifetime". That is true for that path. It is FALSE for a process
# double-forked away from it: five orphaned probes ran at ~99% CPU for 3 days 11 hours on a
# developer machine, PPID 1, load average 9. This turns that production observation into a
# controlled measurement.
#
# GROUND TRUTH is the process table and a heartbeat file the process writes itself.
# CONTROL is the harness path, which must die -- otherwise "survived" says nothing about
# double-forking, only that things survive generally.
#
# CLEANUP IS NOT OPTIONAL HERE. A test that demonstrates orphaning by CREATING an orphan and
# leaving it behind would repeat the exact incident it exists to document. Every PID is
# tracked and reaped, and the script verifies the reap.
set -uo pipefail
W="$(mktemp -d)"; mkdir -p "$W/.claude"
HB_DF="$W/df.log"; HB_HP="$W/hp.log"
printf '{"permissions":{"allow":["Bash(bash:*)","Bash(nohup:*)","Bash(sh:*)"]}}' > "$W/.claude/settings.json"
python3 - "$W" <<'PY'
import json,os,sys
d=os.path.realpath(sys.argv[1]); p=os.path.expanduser("~/.claude.json")
try: c=json.load(open(p))
except Exception: c={}
c.setdefault("projects",{}).setdefault(d,{})["hasTrustDialogAccepted"]=True
json.dump(c,open(p,"w"),indent=2)
PY
reap() {
  pkill -9 -f "$W/beat_df.sh" 2>/dev/null || true
  pkill -9 -f "$W/beat_hp.sh" 2>/dev/null || true
  python3 - "$W" <<'PY' 2>/dev/null
import json,os,sys
d=os.path.realpath(sys.argv[1]); p=os.path.expanduser("~/.claude.json")
try: c=json.load(open(p))
except Exception: sys.exit(0)
c.get("projects",{}).pop(d,None); json.dump(c,open(p,"w"),indent=2)
PY
}
trap reap EXIT INT TERM HUP

mk() { cat > "$1" <<EOF
#!/usr/bin/env bash
i=0
while [ \$i -lt 600 ]; do i=\$((i+1)); echo "\$i \$(date +%s)" >> "$2"; sleep 1; done
EOF
chmod +x "$1"; }
mk "$W/beat_df.sh" "$HB_DF"
mk "$W/beat_hp.sh" "$HB_HP"

# A wrapper the agent runs which DOUBLE-FORKS: the inner process is detached from the shell
# the harness knows about. This is the shape that produced the incident.
# NOTE: this heredoc is QUOTED (<<'EOF'). Unquoted, backticks inside it are command-
# substituted at write time -- an explanatory comment mentioning `setsid` in backticks
# actually EXECUTED setsid and printed "command not found" on every run. A comment that runs
# is not a comment.
#
# nohup only, no setsid: setsid does not exist on macOS, and a first version wrote
# `( setsid ... & ) || ( nohup ... & )`, where the backgrounded subshell returns 0 whether or
# not the command inside exists, so the fallback never fired. The double-forked arm produced
# ZERO beats and the gate correctly reported NOT MEASURED -- the wrapper was broken, not the
# finding. Verified standalone: the nohup form yields ppid=1 and sustains.
cat > "$W/launch_df.sh" <<'EOF'
#!/usr/bin/env bash
( nohup "__BEAT__" >/dev/null 2>&1 < /dev/null & )
echo launched
EOF
sed -i.bak "s#__BEAT__#$W/beat_df.sh#" "$W/launch_df.sh" && rm -f "$W/launch_df.sh.bak"
chmod +x "$W/launch_df.sh"

echo "double-fork vs harness background path (I1b, second half)"
echo

# ---- CONTROL ARM: harness background path. Must DIE with the session.
( cd "$W" && CLAUDE_PROJECT_DIR="$W" timeout 120 claude -p \
    "Start this in the background so it does not block you, then confirm: bash $W/beat_hp.sh" \
    --permission-mode acceptEdits < /dev/null >/dev/null 2>&1 )
# ---- TEST ARM: double-forked away from the harness.
( cd "$W" && CLAUDE_PROJECT_DIR="$W" timeout 120 claude -p \
    "Run this script once and report its output: bash $W/launch_df.sh" \
    --permission-mode acceptEdits < /dev/null >/dev/null 2>&1 )

sleep 25
hp_alive=$(pgrep -fc "beat_hp.sh" 2>/dev/null || echo 0)
df_alive=$(pgrep -fc "beat_df.sh" 2>/dev/null || echo 0)
hp_beats=$(wc -l < "$HB_HP" 2>/dev/null | tr -d ' '); hp_beats=${hp_beats:-0}
df_beats=$(wc -l < "$HB_DF" 2>/dev/null | tr -d ' '); df_beats=${df_beats:-0}
df_ppid=$(pgrep -f "beat_df.sh" 2>/dev/null | head -1 | xargs -I{} ps -o ppid= -p {} 2>/dev/null | tr -d ' ')

echo "  25s after both sessions ended:"
printf '    harness-background arm : alive=%s beats=%s\n' "$hp_alive" "$hp_beats"
printf '    double-forked arm      : alive=%s beats=%s ppid=%s\n' "$df_alive" "$df_beats" "${df_ppid:-n/a}"
echo

# VERDICT ON EVIDENCE, NOT ON ONE SNAPSHOT.
# The first run recorded df_beats=30 and df_ppid=1 -- the process demonstrably double-forked
# and outlived the harness arm's 8 beats -- and then printed "NO DIFFERENCE: both arms died"
# because a single `alive` sample taken at one instant showed 0 for both. Heartbeat count and
# ppid are durable evidence; an instantaneous liveness poll is not, and it overrode them.
if [ "${df_beats:-0}" -lt 10 ]; then
  echo "  n/a   NOT MEASURED — the double-forked job never sustained ($df_beats beats)."
elif [ "${df_ppid:-}" = "1" ] || [ "${df_beats:-0}" -gt $(( hp_beats + 5 )) ]; then
  echo "  CONFIRMED: double-forking escapes the session bound."
  echo "    harness-background arm : $hp_beats beats"
  echo "    double-forked arm      : $df_beats beats, ppid ${df_ppid:-1} (reparented to init)"
  echo "  Session lifetime bounds only the path the harness owns. A process double-forked"
  echo "  away from it is bounded by nothing -- the shape that burned 5 cores for 3.5 days."
elif [ "${hp_beats:-0}" -ge "${df_beats:-0}" ]; then
  echo "  n/a   NOT MEASURED — the control arm also survived, so survival is not attributable"
  echo "  to double-forking."
else
  echo "  NO DIFFERENCE: both arms died. Double-forking did not escape the session here."
fi

echo
reap; sleep 1
left=$(( $(pgrep -fc "beat_df.sh" 2>/dev/null || echo 0) + $(pgrep -fc "beat_hp.sh" 2>/dev/null || echo 0) ))
echo "  cleanup verified: $left probe process(es) remaining (must be 0)"
[ "$left" -eq 0 ] || echo "  WARNING: this test leaked, which is the incident it documents." >&2
rm -rf "$W"
