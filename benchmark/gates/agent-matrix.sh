#!/usr/bin/env bash
# agent-matrix.sh — is each enforcement unit agent-portable, or Claude-coupled?
#
#   agent-matrix.sh            run the matrix
#   agent-matrix.sh --self-test  run the positive controls
#
# WHY THIS EXISTS
#
# Every gate in this repository was built, measured and demonstrated inside Claude Code.
# That says nothing about whether it works for any other agent. Codex runs on this host
# too: 584 sessions, 10,756 correction signals, and its own hook system with PreToolUse,
# PostToolUse, PermissionRequest, SessionStart, Stop, SubagentStart, SubagentStop and
# UserPromptSubmit events, plus a wire schema carrying BlockDecisionWire = ["block"].
# The mechanism to enforce there exists. Nothing of this repository is installed in it.
#
# Before porting anything, the question is which units are portable at all. A unit that
# reads CLAUDE_PROJECT_DIR and silently passes without it is not a gate for another agent,
# it is a gate that turns itself off.
#
# WHAT IS MEASURED
#
# Each unit's OWN selftest, run twice: once with the Claude environment present, once with
# every CLAUDE_* variable unset. Identical exit codes mean the unit does not depend on the
# harness that happens to be running it. Different exit codes locate the coupling.
#
# WHY THE CONTROLS ARE NOT CEREMONY
#
# "Both runs exited 0" is exactly what a probe that measures nothing reports. Control 2
# below is a unit that IS environment-coupled — stop-gate.sh run from outside a repo with
# no CLAUDE_PROJECT_DIR resolves its root to the cwd, finds no gate config, and exits 0
# where the same script exits 2 in-repo. If the matrix cannot show that difference, it
# cannot show any difference, and every "portable" verdict it prints is vacuous.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"

# Declared independently of the tree ON PURPOSE. Deriving this list by globbing bin/ and
# hooks/ would mean deleting a unit also deletes its own requirement to be portable — the
# expectation-derived-from-subject defect this repository has now hit six times. A unit
# that disappears from disk must show up as a FINDING, not as a silently shorter matrix.
UNITS=(
  "scan-diff-cheats|bash hooks/scan-diff-cheats.sh selftest"
  "inert-mask|python3 hooks/inert-mask.py --self-test"
  "ambiguity|bash bin/ambiguity selftest"
  "escalate|bash bin/escalate selftest"
  "holdout|bash bin/holdout selftest"
  "ledger|bash bin/ledger selftest"
  "mutate-changed|bash bin/mutate-changed selftest"
  "test-delta|bash bin/test-delta selftest"
  "worktree-guard|bash bin/worktree-guard selftest"
  "identity-preflight|python3 benchmark/gates/identity-preflight.py --self-test"
  "pin-check|python3 benchmark/gates/pin-check.py --self-test"
  "playbook-coverage|python3 benchmark/gates/playbook-coverage.py --self-test"
  "trailer-check|python3 benchmark/gates/trailer-check.py --self-test"
)
EXPECTED_UNITS=13
EXPECTED_CONTROLS=3

# bin/verify is deliberately absent: it has no `selftest` subcommand, so probing it that
# way measures its usage message. Its portability is covered by control 1, which drives it
# through stop-gate.sh — the path that actually runs it in production.

FINDINGS=0
finding() { printf 'FINDING: %s\n' "$*"; FINDINGS=$((FINDINGS + 1)); }

# Run a command with the Claude environment present.
as_claude() ( cd "$ROOT" && CLAUDE_PROJECT_DIR="$ROOT" CLAUDE_PLUGIN_ROOT="$ROOT" \
  bash -c "$1" >/dev/null 2>&1; echo $? )

# Run the same command with every CLAUDE_* variable removed. This is the shape a Codex
# hook, a CI step, or a bare shell sees.
as_bare() ( cd "$ROOT" && env -u CLAUDE_PROJECT_DIR -u CLAUDE_PLUGIN_ROOT \
  -u CLAUDE_CODE_SSE_PORT -u CLAUDE_CODE_ENTRYPOINT \
  bash -c "$1" >/dev/null 2>&1; echo $? )

# --------------------------------------------------------------------- controls
# A scratch repo carrying a gate that can never pass. stop-gate must refuse there.
make_red_repo() {
  local d="$1"
  mkdir -p "$d/.claude"
  ( cd "$d" && git init -q . && git config user.email h@h && git config user.name h )
  printf '%s\n' '{ "fast": [], "full": [ { "name": "always-red", "cmd": "exit 1" } ], "deferred": [] }' \
    > "$d/.claude/gates.json"
  ( cd "$d" && git add -A >/dev/null 2>&1 && git commit -qm init >/dev/null 2>&1 )
}

controls() {
  local tmp="${TMPDIR:-/tmp}/agent-matrix-ctl.$$"
  mkdir -p "$tmp/red"
  make_red_repo "$tmp/red"
  local sg="$ROOT/hooks/stop-gate.sh" ok=0 ran=0

  # CONTROL 1 — the gate fires at all. A red gate must refuse the turn (exit 2) with the
  # Claude environment set. If this passes, every "portable" row below is measuring a
  # script that never blocks anything.
  ran=$((ran + 1))
  local c1; c1=$( cd "$tmp/red" && CLAUDE_PROJECT_DIR="$tmp/red" bash "$sg" </dev/null >/dev/null 2>&1; echo $? )
  if [ "$c1" = 2 ]; then ok=$((ok + 1)); printf '  %-52s %s\n' "1 red gate refuses the turn under Claude env" "PASS (exit 2)"
  else finding "control 1: stop-gate returned $c1 on a red gate, expected 2"; printf '  %-52s %s\n' "1 red gate refuses the turn under Claude env" "FAIL (exit $c1)"; fi

  # CONTROL 2 — the probe can SEE environment coupling. Same script, same red gate, but no
  # CLAUDE_PROJECT_DIR and a cwd outside the repo: the root resolves elsewhere, no config
  # is found, and it exits 0. This is the discriminating case. Without it a matrix of all
  # zeroes would be indistinguishable from a matrix that measured nothing.
  ran=$((ran + 1))
  local c2; c2=$( cd "$tmp" && env -u CLAUDE_PROJECT_DIR -u CLAUDE_PLUGIN_ROOT bash "$sg" </dev/null >/dev/null 2>&1; echo $? )
  if [ "$c2" = 0 ] && [ "$c1" = 2 ]; then ok=$((ok + 1)); printf '  %-52s %s\n' "2 same script, bare env, outside repo: differs" "PASS (2 vs 0)"
  else finding "control 2: expected exit 2 in-repo and 0 bare-outside, got $c1 and $c2 — the matrix cannot discriminate"; printf '  %-52s %s\n' "2 same script, bare env, outside repo: differs" "FAIL ($c1 vs $c2)"; fi

  # CONTROL 3 — a deliberately coupled unit is reported as coupled. Built here rather than
  # borrowed from the tree so it cannot drift into portability and quietly stop testing.
  ran=$((ran + 1))
  local fake="$tmp/coupled.sh"
  printf '%s\n' '#!/usr/bin/env bash' '[ -n "${CLAUDE_PROJECT_DIR:-}" ] || exit 7' 'exit 0' > "$fake"
  local a3 b3
  a3=$(as_claude "bash '$fake'"); b3=$(as_bare "bash '$fake'")
  if [ "$a3" = 0 ] && [ "$b3" = 7 ]; then ok=$((ok + 1)); printf '  %-52s %s\n' "3 synthetic CLAUDE_-coupled unit is detected" "PASS (0 vs 7)"
  else finding "control 3: synthetic coupled unit gave $a3/$b3, expected 0/7"; printf '  %-52s %s\n' "3 synthetic CLAUDE_-coupled unit is detected" "FAIL ($a3 vs $b3)"; fi

  rm -rf "$tmp"

  [ "$ran" -eq "$EXPECTED_CONTROLS" ] || finding "ran $ran controls, expected $EXPECTED_CONTROLS"
  printf '\ncontrols: %d/%d passed\n' "$ok" "$EXPECTED_CONTROLS"
  [ "$ok" -eq "$EXPECTED_CONTROLS" ]
}

# --------------------------------------------------------------------- matrix
matrix() {
  [ "${#UNITS[@]}" -eq "$EXPECTED_UNITS" ] \
    || finding "UNITS holds ${#UNITS[@]} entries, expected $EXPECTED_UNITS — update both deliberately"

  printf '%-22s %8s %8s  %s\n' UNIT CLAUDE BARE VERDICT
  local portable=0 coupled=0 missing=0
  for e in "${UNITS[@]}"; do
    local name="${e%%|*}" cmd="${e#*|}"
    # A declared unit whose file is gone is a finding, never a shorter table.
    local target; target="$(printf '%s' "$cmd" | awk '{print $2}')"
    if [ ! -f "$ROOT/$target" ]; then
      missing=$((missing + 1)); finding "declared unit '$name' has no file at $target"
      printf '%-22s %8s %8s  %s\n' "$name" "-" "-" "MISSING"
      continue
    fi
    local a b v
    a=$(as_claude "$cmd"); b=$(as_bare "$cmd")
    if [ "$a" = "$b" ]; then v="portable"; portable=$((portable + 1))
    else v="COUPLED"; coupled=$((coupled + 1)); finding "$name exits $a under Claude env and $b bare — not portable to another agent"; fi
    printf '%-22s %8s %8s  %s\n' "$name" "$a" "$b" "$v"
  done
  printf '\n%d portable, %d coupled, %d missing, of %d declared\n' \
    "$portable" "$coupled" "$missing" "$EXPECTED_UNITS"
}

case "${1:-run}" in
  --self-test|selftest)
    echo "agent-matrix positive controls"
    echo
    controls || { echo; echo "CONTROLS FAILED — the matrix cannot discriminate, so its verdicts mean nothing." >&2; exit 1; }
    # The count is emitted in the shape selftest.sh parses. A sub-suite that exits 0 with no
    # parseable count is failed there rather than credited, which is the right default.
    echo "SELF-TEST PASSED  ($EXPECTED_CONTROLS checks)"
    ;;
  run)
    echo "agent-matrix — enforcement portability across agents"
    echo
    echo "controls (the matrix is not reported unless these discriminate):"
    controls || { echo; echo "CONTROLS FAILED — refusing to print a matrix that cannot mean anything." >&2; exit 1; }
    echo
    matrix
    echo
    if [ "$FINDINGS" -gt 0 ]; then echo "$FINDINGS finding(s)."; exit 1; fi
    echo "No findings: every declared unit behaves identically with and without the Claude environment."
    ;;
  *) echo "usage: agent-matrix.sh [run|--self-test]" >&2; exit 2 ;;
esac
