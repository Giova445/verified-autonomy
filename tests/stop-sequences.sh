#!/usr/bin/env bash
set -uo pipefail
PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STOP="$PLUGIN/hooks/stop-gate.sh"; VERIFY="$PLUGIN/bin/verify"; STATE="$PLUGIN/hooks/state.py"
START="$PLUGIN/hooks/session-start.sh"
W="$(mktemp -d "${TMPDIR:-/tmp}/stop-seq.XXXXXX")"
trap 'chmod -R u+w "$W" 2>/dev/null; rm -rf "$W"' EXIT
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-62s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-62s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
ms(){ python3 -c 'import time;print(int(time.time()*1000))'; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && echo yes || echo no; }
jmsg(){ printf '%s' "$1" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("systemMessage",""))' 2>/dev/null; }

RED='{"full":[{"name":"red","cmd":"printf r >> .claude/runs; exit 1"}]}'
GREEN='{"full":[{"name":"green","cmd":"printf r >> .claude/runs"}]}'
HELD='{"outcomes":[{"name":"o","expect":"e","check":"exit 0","control":"exit 1"}]}'

mkrepo(){ local d; d="$(mktemp -d "$W/r.XXXXXX")"
  ( cd "$d" && git init -q . && git config user.email t@t && git config user.name t && mkdir -p .claude src \
    && echo a > src/a.txt && printf '%s' "$1" > .claude/gates.json && git add -A && git commit -qm init ) >/dev/null 2>&1
  [ -n "${2:-}" ] && printf '%s' "$2" > "$d/.claude/acceptance.json"
  printf '%s' "$d"; }
runs(){ if [ -f "$1/.claude/runs" ]; then wc -c < "$1/.claude/runs" | tr -d ' '; else echo 0; fi; }
edit(){ echo "$RANDOM$RANDOM" >> "$1/src/a.txt"; }
STOPENV=""
stop(){ local d="$1" sid="${2:-}" ev="${3:-Stop}" t0; t0=$(ms)
  if [ -n "$sid" ]; then
    OUT="$(printf '{"session_id":"%s","hook_event_name":"%s"}' "$sid" "$ev" | env $STOPENV CLAUDE_PROJECT_DIR="$d" bash "$STOP" 2>"$W/err")"; RC=$?
  else
    OUT="$(env $STOPENV CLAUDE_PROJECT_DIR="$d" bash "$STOP" </dev/null 2>"$W/err")"; RC=$?
  fi
  ERR="$(cat "$W/err")"; MS=$(( $(ms) - t0 )); }
prompt(){ PO="$(printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","prompt":"x"}' "${2:-}" | CLAUDE_PROJECT_DIR="$1" python3 "$STATE" baseline 2>/dev/null)"; PRC=$?; }
seqstops(){ local d="$1" sid="$2" n="$3" chg="$4" i s=""; for i in $(seq 1 "$n"); do
  [ "$chg" = yes ] && edit "$d"; stop "$d" "$sid"; s="$s$RC"; done; printf '%s' "$s"; }
fpr(){ CLAUDE_PROJECT_DIR="$1" bash "$VERIFY" fingerprint 2>/dev/null; }
vdone(){ CLAUDE_PROJECT_DIR="$1" bash "$VERIFY" "${@:2}" </dev/null >"$W/vout" 2>"$W/verr"; VRC=$?; VERR="$(cat "$W/verr")"; }

unset CLAUDE_CONFIG_DIR
echo "stop-sequences: $PLUGIN"

d="$(mkrepo "$GREEN" "$HELD")"
vdone "$d" done; vdone "$d" done; vdone "$d" done
chk "manual done executes every time" "$(runs "$d") $VRC" "3 0"
stop "$d" s1; a=$(runs "$d"); vdone "$d" done
chk "manual done still executes after a hook verdict on the same tree" "$a $(runs "$d")" "3 4"
vdone "$d" done --hook; vdone "$d" done --hook
chk "the caches do apply with --hook" "$(runs "$d")" "4"

d="$(mkrepo '{"full":[{"name":"stdin","cmd":"[ -z \"$(cat)\" ]"}]}' "$HELD")"
echo data | CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" done >/dev/null 2>&1
chk "a gate never inherits the runner's stdin" "$?" "0"

d="$(mkrepo "$RED")"
stop "$d" s2; r1=$RC
stop "$d" s2; r2=$RC; o2="$OUT"; m2="$(jmsg "$OUT")"
stop "$d" s2; r3=$RC
chk "red unchanged: refuse once, then allow" "$r1$r2$r3 $(runs "$d")" "200 1"
chk "the allowed stop says it is still red and why it was allowed" \
  "$(has "$m2" 'verified-autonomy: still red (red); stop allowed because nothing changed since the refusal')" "yes"
stop "$d" s2; chk "the message repeats on every later unchanged stop" "$(has "$(jmsg "$OUT")" 'still red (red)')" "yes"
d="$(mkrepo "$GREEN" "$HELD")"
stop "$d" s2; a="$RC${OUT:+ out}"; stop "$d" s2; b="$RC${OUT:+ out}"
chk "green then unchanged: silent both times, gates ran once" "$a|$b|$(runs "$d")" "0|0|1"
d="$(mkrepo "$GREEN" '{"outcomes":[{"name":"Search results","expect":"matches only","check":"exit 1"}]}')"
stop "$d" s2; stop "$d" s2
chk "an open outcome is named when its refusal is waved through" "$RC $(has "$(jmsg "$OUT")" 'Search results')" "0 yes"

d="$(mkrepo "$RED")"
prompt "$d" s3; stop "$d" s3
chk "a turn that changed nothing stops silently and runs no gate" "$RC${OUT:+ out} $(runs "$d")" "0 0"

d="$(mkrepo "$RED")"
stop "$d" s4 SubagentStop
chk "SubagentStop exits at once and touches no state" "$RC${OUT:+ out} $(ls -A "$d/.claude" | tr '\n' ' ') $(runs "$d")" "0 gates.json  0"
chk "SubagentStop is not registered in hooks.json" "$(python3 -c 'import json,sys;print("SubagentStop" in json.load(open(sys.argv[1]))["hooks"])' "$PLUGIN/hooks/hooks.json")" "False"

d="$(mkrepo '{"full":[{"name":"slow","cmd":"printf r >> .claude/runs; sleep 2; exit 1"}]}')"
for n in a b; do ( printf '{"session_id":"c%s","hook_event_name":"Stop"}' "$n" | CLAUDE_PROJECT_DIR="$d" bash "$STOP" >"$W/o.$n" 2>"$W/e.$n"; echo $? > "$W/rc.$n" ) & sleep 0.4; done
wait
chk "two concurrent stops run the gate once and agree on the verdict" "$(runs "$d") $(cat "$W/rc.a" "$W/rc.b" | sort | tr -d '\n')" "1 02"
chk "the waiter is told what it is reusing" "$(has "$(jmsg "$(cat "$W/o.a" "$W/o.b")")" 'still red (slow)')" "yes"
d="$(mkrepo "$RED")"
sh -c 'exit 0' & dead=$!; wait $dead
mkdir "$d/.claude/.gate-lock"; echo "$dead" > "$d/.claude/.gate-lock/pid"
stop "$d" s5
chk "a lock left by a dead process is recovered, and released after" "$RC $([ -e "$d/.claude/.gate-lock" ] && echo held || echo free) $(runs "$d")" "2 free 1"

d="$(mkrepo '{"full":[{"name":"hang","cmd":"printf r >> .claude/runs; sleep 30"}]}')"
STOPENV="GATE_TIMEOUT=1"; stop "$d" s6; STOPENV=""
chk "a gate past its timeout is NO VERDICT: allowed, said so, not green" \
  "$RC $(has "$(jmsg "$OUT")" 'NO VERDICT') $(has "$(jmsg "$OUT")" 'hang') $([ "$MS" -lt 9000 ] && echo fast || echo slow)" "0 yes yes fast"
chk "the evidence for it is not green" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["all_green"])' "$d/.claude/evidence/latest.json") $(cut -d' ' -f2 "$d/.claude/.gate-judged")" "False noverdict"
stop "$d" s6; chk "the same tree is not re-run, and still says NO VERDICT" "$RC $(runs "$d") $(has "$(jmsg "$OUT")" 'NO VERDICT')" "0 1 yes"
d="$(mkrepo '{"full":[{"name":"leaky","cmd":"sleep 25 & echo $! > .claude/childpid"}]}' "$HELD")"
stop "$d" s6b; sleep 1; cp_="$(cat "$d/.claude/childpid" 2>/dev/null)"
kill -0 "$cp_" 2>/dev/null && alive=alive || alive=dead
chk "a child a gate leaves behind neither hangs the hook nor survives it" "$RC $alive $([ "$MS" -lt 9000 ] && echo fast || echo slow)" "0 dead fast"
d="$(mkrepo '{"full":[{"name":"big","cmd":"head -c 3000000 /dev/zero | tr \"\\0\" x"}]}' "$HELD")"
stop "$d" s6c
chk "3 MB of gate output is recorded, not lost" "$RC $(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));g=d["gates"];print(len(g),d["all_green"],len(g[0]["stdout_sha256"]))' "$d/.claude/evidence/latest.json")" "0 1 True 64"
d="$(mkrepo '{"full":[{"name":"long","cmd":"sleep 30"}]}')"
STOPENV="VERIFY_BUDGET=2"; stop "$d" s6d; STOPENV=""
chk "an exhausted hook budget allows with NO VERDICT, and quickly" \
  "$RC $(has "$(jmsg "$OUT")" 'NO VERDICT: hook budget exhausted') $([ "$MS" -lt 9000 ] && echo fast || echo slow)" "0 yes fast"

d="$(mkrepo "$RED")"; mkdir "$d/.claude/.gate-judged"
stop "$d" s7; a="$RC $(has "$(jmsg "$OUT")" 'cannot be persisted')"
d="$(mkrepo "$RED")"; mkdir "$d/.claude/.gate-attempts"
stop "$d" s7; a="$a|$RC $(has "$(jmsg "$OUT")" 'cannot be persisted')"
chk "state that cannot be written allows with a message, never exit 2" "$a" "0 yes|0 yes"
if [ "$(id -u)" != 0 ]; then
  d="$(mkrepo "$RED")"; chmod 555 "$d/.claude"
  s="$(seqstops "$d" s7b 4 yes)"
  chk "a read-only .claude never loops, and says why" "$s $(has "$OUT" 'cannot be persisted') $(runs "$d")" "0000 yes 0"
  chmod 755 "$d/.claude"
  d="$(mkrepo "$RED")"; prompt "$d" s7c; chmod 555 "$d/.claude"; prompt "$d" s7c
  chk "the prompt hook is silent and harmless when it cannot write" "$PRC${PO:+ out}" "0"
  chmod 755 "$d/.claude"
else chk "read-only .claude" "cannot run as root" "cannot run as root"; fi

d="$(mkrepo "$GREEN" "$HELD")"; rm "$d/.claude/gates.json"
stop "$d" ""; r1=$RC; e1="$ERR"; stop "$d" ""; r2=$RC; stop "$d" ""; r3=$RC
chk "tracked config deleted: refuse once, then it is a visible allow" "$r1$r2$r3" "200"
chk "  and the refusal says the config is gone" "$(has "$e1" 'gates.json')" "yes"
d="$(mkrepo "$GREEN" "$HELD")"; rm "$d/.claude/gates.json"; prompt "$d" s8; stop "$d" s8
chk "config already missing at the turn baseline: silent allow" "$RC${OUT:+ out}" "0"
d="$(mkrepo "$GREEN" "$HELD")"; : > "$d/.claude/gates.json"
s="$(seqstops "$d" "" 3 no)"
chk "tracked config emptied: refuse once, then allow" "$s" "200"
d="$(mkrepo "$GREEN")"; git -C "$d" rm -q --cached .claude/gates.json; rm "$d/.claude/gates.json"; git -C "$d" commit -qm x
stop "$d" ""; chk "never-armed repo: silent allow" "$RC${OUT:+ out}${ERR:+ err}" "0"

d="$(mkrepo "$RED")"
f1="$(fpr "$d")"; f2="$(fpr "$d")"
chk "the fingerprint is stable" "$([ "$f1" = "$f2" ] && [ -n "$f1" ] && echo same)" "same"
mkdir "$W/shim"; printf '#!/bin/sh\nexit 1\n' > "$W/shim/shasum"; chmod +x "$W/shim/shasum"
g1="$(PATH="$W/shim:$PATH" fpr "$d")"; edit "$d"; g2="$(PATH="$W/shim:$PATH" fpr "$d")"
chk "it does not depend on shasum: a broken one still sees a change" "$([ "$g1" != "$g2" ] && echo differs)" "differs"
nog="$(mktemp -d "$W/n.XXXXXX")"; n1="$(fpr "$nog")"; n2="$(fpr "$nog")"
chk "outside a git repo it is a unique uncacheable token each time" "${n1%%-*} ${n2%%-*} $([ "$n1" != "$n2" ] && echo unique)" "uncacheable uncacheable unique"
ur="$(mktemp -d "$W/u.XXXXXX")"; ( cd "$ur" && git init -q . && echo a > a ) >/dev/null 2>&1
u1="$(fpr "$ur")"; u2="$(fpr "$ur")"; echo b > "$ur/b"; u3="$(fpr "$ur")"
chk "a repo with no commit yet is cacheable, and sees new files" "$([ "$u1" = "$u2" ] && [ "$u2" != "$u3" ] && [ "${u1%%-*}" != uncacheable ] && echo ok)" "ok"

IGNORED=".venv/x .mypy_cache/y .claude/.gate-lock/pid .claude/.gate-green .claude/.gate-stalled .claude/.gate-judged .claude/.sessions/s .claude/evidence/latest.json .claude-flow/log .agents/a .swarm/s .hive-mind/h .quality-baseline/q .DS_Store src/.DS_Store app.db-wal app.db-shm agentdb.rvf agentdb.rvf.lock ruvector.db .claude/gates.json.new .claude/memory.db"
COUNTED=".github/workflows/ci.yml .claude/checks/c.sh .claude/acceptance.json src/new.txt docs/n.md .gitignore"
d="$(mkrepo "$RED")"; base="$(fpr "$d")"; moved=""
for p in $IGNORED; do mkdir -p "$d/$(dirname "$p")"; echo x > "$d/$p"; [ "$(fpr "$d")" != "$base" ] && moved="$moved $p"; done
chk "harness output and agent tooling never move the fingerprint" "${moved:-none}" "none"
cur="$base"; missed=""
for p in $COUNTED; do mkdir -p "$d/$(dirname "$p")"; echo x > "$d/$p"; n="$(fpr "$d")"; [ "$n" = "$cur" ] && missed="$missed $p"; cur="$n"; done
chk "source, CI config, checks and the contract each move it" "${missed:-none}" "none"
printf '{"full":[]}' > "$d/.claude/gates.json"; n="$(fpr "$d")"
chk "an edit to the gate config moves it" "$([ "$n" != "$cur" ] && echo moved)" "moved"
d="$(mkrepo "$RED")"; printf '.claude/*\n' > "$d/.gitignore"; git -C "$d" add .gitignore; git -C "$d" commit -qm ig; git -C "$d" rm -q --cached -r .claude; git -C "$d" commit -qm un
a="$(fpr "$d")"; printf '{"full":[]}' > "$d/.claude/gates.json"; chk "a git-ignored gate config still moves it" "$([ "$(fpr "$d")" != "$a" ] && echo moved)" "moved"
d="$(mkrepo "$RED")"; a="$(fpr "$d")"; ln -s /nonexistent/x "$d/src/link"
chk "an untracked symlink is skipped" "$([ "$a" = "$(fpr "$d")" ] && echo same)" "same"
d="$(mkrepo "$RED")"; head -c 2000000 /dev/zero > "$d/big.bin"; a="$(fpr "$d")"
head -c 2500000 /dev/zero > "$d/big.bin"; b="$(fpr "$d")"; cp -p "$d/big.bin" "$W/ref.bin"
printf x | dd of="$d/big.bin" bs=1 count=1 conv=notrunc 2>/dev/null; touch -r "$W/ref.bin" "$d/big.bin"; c="$(fpr "$d")"
chk "a file over 1 MB is fingerprinted by size and mtime, not by content" \
  "$([ "$a" != "$b" ] && echo size-moves) $([ "$b" = "$c" ] && echo content-blind)" "size-moves content-blind"
mkdir -p "$W/plug" && cp -R "$PLUGIN/bin" "$PLUGIN/hooks" "$PLUGIN/benchmark" "$W/plug/"
d="$(mkrepo "$RED")"; a="$(CLAUDE_PROJECT_DIR="$d" bash "$W/plug/bin/verify" fingerprint)"; printf '\n' >> "$W/plug/bin/verify"
chk "the runner itself is part of the fingerprint" "$([ "$a" != "$(CLAUDE_PROJECT_DIR="$d" bash "$W/plug/bin/verify" fingerprint)" ] && echo moved)" "moved"

d="$(mkrepo "$RED")"; mkdir -p "$d/.claude/.gate-lock" "$d/.venv" "$d/.claude/checks" "$d/.github/workflows"
for p in $IGNORED $COUNTED; do mkdir -p "$d/$(dirname "$p")"; echo x > "$d/$p"; done
cat > "$W/scope_files.py" <<'PY'
import importlib.machinery, importlib.util, sys
loader = importlib.machinery.SourceFileLoader("scope", sys.argv[1])
spec = importlib.util.spec_from_loader("scope", loader)
m = importlib.util.module_from_spec(spec); loader.exec_module(m)
files, _ = m.changed_files(sys.argv[2])
print(" ".join(files))
PY
sc="$(python3 "$W/scope_files.py" "$PLUGIN/bin/scope" "$d")"
exp="$(printf '%s\n' $COUNTED | LC_ALL=C sort | tr '\n' ' ')"
chk "bin/scope excludes exactly what the fingerprint ignores" "${sc% }" "${exp% }"

d="$(mkrepo "$RED")"
prompt "$d" s9; stop "$d" s9; a="$RC${OUT:+ out}"
prompt "$d" s9; edit "$d"; stop "$d" s9; b="$RC"; stop "$d" s9; c="$RC"
chk "a read-only turn, then a changed turn refused, then unchanged allowed" "$a|$b|$c|$(runs "$d")" "0|2|0|1"
edit "$d"; prompt "$d" s9; stop "$d" s9
chk "an edit made by the user between turns is not the agent's: silent, no gate" "$RC${OUT:+ out} $(runs "$d")" "0 1"
d="$(mkrepo "$RED")"; prompt "$d" s9b; edit "$d"; stop "$d" s9b; git -C "$d" checkout -q -- src/a.txt; stop "$d" s9b
chk "reverting to the turn's starting tree makes the stop silent" "$RC${OUT:+ out}" "0"
chk "the baseline is the fingerprint, stored per session" "$([ "$(cat "$d/.claude/.sessions/s9b")" = "$(fpr "$d")" ] && echo same)" "same"
d="$(mkrepo "$RED")"; prompt "$d" ""
chk "no session id: the prompt hook writes nothing and says nothing" "$PRC${PO:+ out} $([ -e "$d/.claude/.sessions" ] && echo dir || echo none)" "0 none"
s="$(seqstops "$d" "" 3 yes)$(seqstops "$d" "" 2 no)"
chk "no session id: changed stops judged, unchanged allowed" "$s" "22200"
ud="$(mktemp -d "$W/un.XXXXXX")"; ( cd "$ud" && git init -q . ) >/dev/null 2>&1; prompt "$ud" s9c
chk "the prompt hook does nothing in an unarmed repo" "$PRC $([ -e "$ud/.claude" ] && echo made || echo none)" "0 none"
d="$(mkrepo "$RED")"; t=0; for i in 1 2 3 4 5; do t0=$(ms); prompt "$d" s9d; t=$((t + $(ms) - t0)); done; ptime=$((t / 5))
chk "the prompt hook is fast on a small repo (avg ${ptime}ms)" "$([ "$ptime" -lt 600 ] && echo fast)" "fast"
d="$(mkrepo "$GREEN" "$HELD")"; stop "$d" s9e; stop "$d" s9e; utime=$MS
chk "an unchanged stop is fast (${utime}ms)" "$([ "$utime" -lt 1500 ] && echo fast)" "fast"
d="$(mkrepo "$RED")"; prompt "$d" s9f; stop "$d" s9f; rtime=$MS
chk "a read-only stop is fast (${rtime}ms)" "$([ "$rtime" -lt 1500 ] && echo fast)" "fast"

d="$(mkrepo "$RED")"
seqstops "$d" sA 2 yes >/dev/null; edit "$d"; stop "$d" sB
chk "attempts are per session: a new session starts at 1/3" "$RC $(has "$ERR" 'Attempt 1/3')" "2 yes"
d="$(mkrepo "$RED")"; codes=""; msgs=""; m4=""
for i in 1 2 3 4 5; do edit "$d"; stop "$d" sC; codes="$codes$RC"; msgs="$msgs|$ERR"; last="$OUT"; [ "$i" = 4 ] && m4="$ERR"; done
chk "red, changed every stop: three refusals, a blocked report, then allow" "$codes" "22220"
n1="$(has "$msgs" 'Attempt 1/3')"; n3="$(has "$msgs" 'Attempt 3/3')"; n4="$(has "$msgs" 'Attempt 4')"
chk "the counter matches reality and never says 4/3" "$n1 $n3 $n4" "yes yes no"
chk "the blocked-report refusal names the failing gate" "$(has "$m4" 'Still red: red')$(has "$m4" 'BLOCKED report')" "yesyes"
chk "the allow after the report says it is still red" "$(has "$(jmsg "$last")" 'still red (red)')" "yes"
d="$(mkrepo "$RED")"; edit "$d"; stop "$d" sD
chk "the counter file names its session while counting" "$(has "$(cat "$d/.claude/.gate-attempts")" sD)" "yes"

d="$(mkrepo '{"full":[]}')"
vdone "$d" full
chk "verify full with a config error refuses cleanly" "$VRC $(has "$VERR" 'REFUSING TO CERTIFY') $(has "$VERR" 'unbound')" "1 yes no"
chk "  and a manual run leaves no hook state" "$(ls -A "$d/.claude" | grep -c -e gate-attempts -e gate-judged)" "0"
d="$(mkrepo "$RED")"; edit "$d"; stop "$d" sE
chk "refusal text: no rule about editing gates, no codegraph nag, no screenshots" \
  "$(has "$ERR" 'Do not edit gates') $(has "$ERR" 'graph') $(has "$ERR" 'Screenshots')" "no no no"
d="$(mkrepo "$GREEN" "$HELD")"; vdone "$d" done; a="$(has "$VERR" 'Screenshots:')"
mkdir -p "$d/.claude/evidence/shots"; : > "$d/.claude/evidence/shots/x.png"; vdone "$d" done
chk "Screenshots is only mentioned when there are some" "$a $(has "$VERR" 'Screenshots:')" "no yes"
d="$(mkrepo '{"full":[{"name":"nap","cmd":"sleep 0.3"}]}' "$HELD")"; vdone "$d" done
dur="$(printf '%s' "$VERR" | sed -n 's/.*nap (\([0-9]*\)ms).*/\1/p')"
chk "durations are real milliseconds" "$([ -n "$dur" ] && [ "$dur" -ge 250 ] && [ "$dur" -le 900 ] && echo real || echo "got ${dur:-none}")" "real"
vdone "$d" blast x; a="$VRC$(has "$VERR" usage)"; vdone "$d" tests; b="$VRC$(has "$VERR" usage)"
chk "verify blast and verify tests are gone" "$a $b" "1yes 1yes"
vdone "$d" preflight
chk "verify preflight is where the graph note lives" "$(has "$VERR" 'graph')" "yes"

d="$(mkrepo "$GREEN" "$HELD")"; mkdir -p "$W/plug2" && cp -R "$PLUGIN/bin" "$PLUGIN/hooks" "$PLUGIN/benchmark" "$W/plug2/"
cat > "$W/plug2/benchmark/gates/acceptance.py" <<'PY'
import json, os, sys
a = sys.argv[1:]
if a and a[0] == "--summarize":
    print("open"); print("product : 1 of 1 expectation(s) not established. Still open:")
    print("  - Checkout: pay (BLOCKED: STRIPE_KEY is not set)"); sys.exit(0)
i = a.index("--results")
json.dump({"contract": "ok", "outcomes": [{"name": "Checkout", "expect": "pay", "verdict": "BLOCKED",
                                            "detail": "STRIPE_KEY is not set", "controlled": True}]}, open(a[i + 1], "w"))
sys.exit(1)
PY
bs(){ OUT="$(printf '{"session_id":"blk","hook_event_name":"Stop"}' | CLAUDE_PROJECT_DIR="$d" bash "$W/plug2/hooks/stop-gate.sh" 2>"$W/err")"; RC=$?; ERR="$(cat "$W/err")"; }
bs; a="$RC $(has "$ERR" 'Checkout')"; bs
chk "a BLOCKED outcome is reported once, then the stop is allowed and says so" "$a|$RC $(has "$(jmsg "$OUT")" 'still red (Checkout')" "2 yes|0 yes"

d="$(mkrepo "$RED")"; t0=$(ms)
{ printf '{"session_id":"eof","hook_event_name":"Stop"}'; sleep 5; } | { CLAUDE_PROJECT_DIR="$d" bash "$STOP" >/dev/null 2>&1; echo $(( $(ms) - t0 )) > "$W/eof.ms"; }
chk "JSON on stdin without EOF does not stall the hook" "$([ "$(cat "$W/eof.ms")" -lt 3500 ] && echo prompt)" "prompt"

hj="$PLUGIN/hooks/hooks.json"
hq(){ python3 -c 'import json,sys;h=json.load(open(sys.argv[1]))["hooks"];exec(sys.argv[2])' "$hj" "$1"; }
chk "PreToolUse matches Bash only" "$(hq 'print(h["PreToolUse"][0]["matcher"])')" "Bash"
chk "SessionStart also fires on resume" "$(hq 'print("resume" in h["SessionStart"][0]["matcher"].split("|"))')" "True"
chk "UserPromptSubmit runs the baseline writer" "$(hq 'print(any("state.py" in x["command"] and "baseline" in x["command"] for e in h["UserPromptSubmit"] for x in e["hooks"]))')" "True"
chk "every timeout is whole seconds, and Stop outlasts the 800 s budget" \
  "$(hq 'ts=[x["timeout"] for v in h.values() for e in v for x in e["hooks"]];print(all(isinstance(t,int) and 0<t<=900 for t in ts), h["Stop"][0]["hooks"][0]["timeout"]>800)')" "True True"

fake="$W/fakeplug"; mkdir -p "$fake/.claude-plugin"; cp -R "$PLUGIN/hooks" "$fake/hooks"
printf '{"name":"verified-autonomy","version":"0.0.1"}' > "$fake/.claude-plugin/plugin.json"
home="$W/home"; mkdir -p "$home/.claude/plugins/cache/verified-autonomy/verified-autonomy/0.0.1/.claude-plugin"
printf '{"version":"0.0.1"}' > "$home/.claude/plugins/cache/verified-autonomy/verified-autonomy/0.0.1/.claude-plugin/plugin.json"
ss(){ local d="$1" src="${2:-}" in=""; [ -n "$src" ] && in="{\"hook_event_name\":\"SessionStart\",\"source\":\"$src\"}"
  SOUT="$(printf '%s' "$in" | HOME="$home" CLAUDE_PROJECT_DIR="$d" bash "$fake/hooks/session-start.sh" 2>/dev/null)"; }
ctx(){ printf '%s' "$SOUT" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("hookSpecificOutput",{}).get("additionalContext",""))
except Exception: pass'; }
smsg(){ printf '%s' "$SOUT" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("systemMessage",""))
except Exception: pass'; }
d="$(mkrepo "$GREEN")"; ss "$d" startup; c="$(ctx)"
chk "armed: at most 3 lines injected, naming the runner and the Stop hook" \
  "$([ "$(printf '%s\n' "$c" | grep -c .)" -le 3 ] && echo short) $(has "$c" 'bin/verify') $(has "$c" 'Stop hook')" "short yes yes"
chk "armed: no rule lists" "$(has "$c" 'Never')$(has "$c" 'blast')$(has "$c" 'Co-Authored')" "nonono"
chk "armed and current: no stale warning" "$(smsg)" ""
before="$(cd "$d" && find . -path ./.git -prune -o -print | sort | cksum)"; ss "$d" resume
after="$(cd "$d" && find . -path ./.git -prune -o -print | sort | cksum)"
chk "session start modifies nothing" "$([ "$before" = "$after" ] && [ ! -e "$d/.claude/.sessions" ] && echo same)" "same"
k=""; for src in clear compact resume; do ss "$d" $src; [ -n "$(ctx)" ] && k="$k$src:armed-ok " || k="$k$src:EMPTY "; done
chk "armed context is re-injected on clear, compact and resume" "$k" "clear:armed-ok compact:armed-ok resume:armed-ok "
ud="$(mktemp -d "$W/un.XXXXXX")"; ( cd "$ud" && git init -q . ) >/dev/null 2>&1
ss "$ud" startup; a="$(has "$(ctx)" 'verified-autonomy:setup')"; b=""
for src in clear compact resume; do ss "$ud" $src; b="$b${SOUT:+X}"; done
chk "unarmed hint on startup only" "$a ${b:-none}" "yes none"
ng="$(mktemp -d "$W/ng.XXXXXX")"; mkdir "$ng/.claude"; printf '%s' "$GREEN" > "$ng/.claude/gates.json"; ss "$ng" startup
chk "armed outside a git repo: no enforcement claim" "$(ctx)" ""
mkdir -p "$home/.claude/plugins/cache/verified-autonomy/verified-autonomy/9.9.9/.claude-plugin" "$home/.claude-other/plugins/cache/verified-autonomy/verified-autonomy/10.0.0/.claude-plugin"
printf '{"version":"9.9.9"}' > "$home/.claude/plugins/cache/verified-autonomy/verified-autonomy/9.9.9/.claude-plugin/plugin.json"
d="$(mkrepo "$GREEN")"; ss "$d" startup; m="$(smsg)"
chk "a newer cached version warns the user with the update command" "$(has "$m" 9.9.9) $(has "$m" '/plugin update')" "yes yes"
rm -rf "$home/.claude/plugins/cache/verified-autonomy/verified-autonomy/9.9.9"
printf '{"version":"10.0.0"}' > "$home/.claude-other/plugins/cache/verified-autonomy/verified-autonomy/10.0.0/.claude-plugin/plugin.json"
ss "$d" startup
chk "another profile's newer version warns too" "$(has "$(smsg)" 10.0.0)" "yes"
ss "$ud" startup; chk "the warning also shows on an unarmed startup" "$(has "$(smsg)" 10.0.0)" "yes"
t=0; for i in 1 2 3 4 5; do t0=$(ms); ss "$d" startup; t=$((t + $(ms) - t0)); done; stime=$((t / 5))
chk "session start is fast (avg ${stime}ms)" "$([ "$stime" -lt 400 ] && echo fast)" "fast"
u="$(VERIFIED_AUTONOMY_UNATTENDED=1 HOME="$home" CLAUDE_PROJECT_DIR="$d" bash "$fake/hooks/session-start.sh" </dev/null 2>/dev/null | grep -c '<unattended>')"
chk "unattended guidance only when opted in" "$u $(ss "$d" startup; has "$SOUT" '<unattended>')" "1 no"

echo
if [ "$fail" -eq 0 ]; then echo "SELF-TEST PASSED  ($pass checks)"; exit 0
else echo "SELF-TEST FAILED  ($fail of $((pass+fail)) checks)"; exit 1; fi
