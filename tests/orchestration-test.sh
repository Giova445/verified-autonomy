#!/usr/bin/env bash
# tests/orchestration-test.sh — integration suite for the durable orchestrator triple:
#   bin/ledger          durable task ledger
#   bin/escalate        fix-loop escalation + thrash detection
#   bin/worktree-guard  parallel-safety claims
#
# Each tool ships its own `selftest`, and this is deliberately NOT a second copy of those.
# A selftest proves one tool behaves inside one process. This proves the three behave as a
# SYSTEM, across process boundaries, which is where the design's actual claim lives:
#
#   * state survives a scrubbed re-invocation (the compaction promise, not just a rerun)
#   * a completion claim without an artifact is refused (the fabrication promise)
#   * ledger and escalate agree about when retrying the same implementer is over
#   * EVERY state file — discovered by diffing the tree, not hardcoded — refuses to be
#     read when corrupt, rather than silently re-initialising
#
# That last one is why discovery matters. A selftest checks the paths its author remembered.
# This checks every file the tool actually wrote, including the ones nobody remembered.
#
# A binary that does not exist yet SKIPS with a message, so the suite is runnable before the
# tools land. A binary that exists but does not answer to the contracted verbs FAILS: that
# is a contract break, not a missing file.
#
# Exit: 0 all green | 1 a check failed | 3 nothing was verified (no orchestrator present).
# Exit 3 is deliberate. A suite that prints PASSED after verifying nothing is the same
# fabricated receipt that made bin/verify emit all_green:true on a config it could not read.
set -uo pipefail

PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LEDGER="$PLUGIN/bin/ledger"
ESCALATE="$PLUGIN/bin/escalate"
GUARD="$PLUGIN/bin/worktree-guard"

pass=0; fail=0; skipped=0
chk(){ if [ "$2" = "$3" ]; then printf '  ok    %-54s (%s)\n' "$1" "$3"; pass=$((pass+1));
       else printf '  FAIL  %-54s want=%s got=%s\n' "$1" "$3" "$2"; fail=$((fail+1)); fi; }
# Fail-closed checks care THAT the tool refused, not which non-zero code it chose.
chk_nz(){ if [ "$2" -ne 0 ]; then printf '  ok    %-54s (exit %s)\n' "$1" "$2"; pass=$((pass+1));
          else printf '  FAIL  %-54s want=nonzero got=0\n' "$1"; fail=$((fail+1)); fi; }
skp(){ printf '  skip  %-54s %s\n' "$1" "$2"; skipped=$((skipped+1)); }

# One root for every scratch repo. `newrepo` is called inside command substitution, so it
# runs in a SUBSHELL — a list of paths appended there never reaches the trap, and every repo
# leaks. Rooting them under one directory is the only cleanup that survives that.
SUITE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/orchestration-test.XXXXXX")"
newrepo(){ local d; d="$(mktemp -d "$SUITE_TMP/repo.XXXXXX")"; git init -q "$d" 2>/dev/null; printf '%s' "$d"; }
cleanup(){ rm -rf "$SUITE_TMP"; }
trap cleanup EXIT

# Every call crosses a process boundary and carries nothing but the project directory. That
# is the premise of the design: if a fact is not on disk, it does not exist. worktree-guard
# resolves its own state from the git common dir, so it needs the cwd, not just the env var.
L(){ local d="$1"; shift; ( cd "$d" && CLAUDE_PROJECT_DIR="$d" "$LEDGER"   "$@" ); }
E(){ local d="$1"; shift; ( cd "$d" && CLAUDE_PROJECT_DIR="$d" "$ESCALATE" "$@" ); }
G(){ local d="$1"; shift; ( cd "$d" && CLAUDE_PROJECT_DIR="$d" "$GUARD"    "$@" ); }

fld(){ printf '%s\n' "$1" | grep -oE "(^|[[:space:]])$2=[^[:space:]]*" | head -1 | sed "s/.*$2=//"; }
col(){ printf '%s' "$1" | head -1 | cut -f"$2"; }        # ledger next prints "<n>\t<text>"
# Status comes from the ledger's own json, not from inference about which verb printed what.
tstatus(){ L "$1" json "$2" 2>/dev/null | python3 -c '
import json, sys
want = int(sys.argv[1])
st = json.load(sys.stdin)
print(next((t["status"] for t in st["tasks"] if t["n"] == want), "missing"))' "$3" 2>/dev/null || echo unreadable; }

mkplan(){ cat > "$1/plan.md" <<'PLAN'
- [x] finished before the run started
- [ ] alpha
- [ ] beta
- [ ] gamma
PLAN
}
mkevidence(){ mkdir -p "$1/.claude/evidence"
  printf '{"all_green": true, "gates": [{"gate":"probe","exit_code":0}]}\n' > "$1/.claude/evidence/latest.json"; }

echo "orchestration suite: $PLUGIN"
echo

# ── 1. full happy path ─────────────────────────────────────────────────────────────────
echo "1. happy path: init -> next -> start -> done(evidence) -> exhaustion"
if [ ! -x "$LEDGER" ]; then skp "ledger happy path" "bin/ledger not present yet"
else
  d="$(newrepo)"; mkplan "$d"; mkevidence "$d"; ev="$d/.claude/evidence/latest.json"
  L "$d" init suite --plan "$d/plan.md" >/dev/null 2>&1; chk "init exits 0" "$?" "0"

  out="$(L "$d" next suite 2>/dev/null)"
  chk "next hands out the first unchecked task" "$(col "$out" 1)/$(col "$out" 2)" "1/alpha"
  chk "a pre-checked '[x]' line is never handed out" \
      "$(printf '%s' "$out" | grep -qi 'finished before' && echo handed || echo skipped)" "skipped"

  L "$d" start suite 1 >/dev/null 2>&1; chk "start exits 0" "$?" "0"
  # Re-dispatching live work is the single failure this ledger exists to prevent.
  chk "next skips the in-progress task" "$(col "$(L "$d" next suite 2>/dev/null)" 1)" "2"
  L "$d" done suite 1 --evidence "$ev" >/dev/null 2>&1; chk "done with real evidence exits 0" "$?" "0"
  chk "next skips the completed task" "$(col "$(L "$d" next suite 2>/dev/null)" 1)" "2"

  for n in 2 3; do
    L "$d" start suite "$n" >/dev/null 2>&1
    L "$d" done  suite "$n" --evidence "$ev" >/dev/null 2>&1
  done
  out="$(L "$d" next suite 2>/dev/null)"; rc=$?
  chk "exhausted ledger exits 1" "$rc" "1"
  chk "exhausted ledger hands out nothing" "${out:-empty}" "empty"

  L "$d" status suite >/dev/null 2>&1; chk "status exits 0" "$?" "0"
  L "$d" json suite 2>/dev/null | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
  chk "json emits parseable JSON" "$?" "0"
  L "$d" selftest >/dev/null 2>&1; chk "ledger selftest exits 0" "$?" "0"
fi
echo

# ── 2. compaction survival ─────────────────────────────────────────────────────────────
# The premise of the whole design: the context window is a cache, disk is the truth. The
# surviving read runs under `env -i` from a foreign working directory, so nothing but the
# project path can carry the answer. State smuggled through a shell variable, an exported
# env var, or an inherited cwd dies here — a plain rerun would not catch any of those.
echo "2. compaction survival: fresh process, scrubbed env, foreign cwd"
if [ ! -x "$LEDGER" ]; then skp "ledger compaction survival" "bin/ledger not present yet"
else
  d="$(newrepo)"; mkplan "$d"; mkevidence "$d"; ev="$d/.claude/evidence/latest.json"
  L "$d" init suite --plan "$d/plan.md" >/dev/null 2>&1
  for n in 1 2; do
    L "$d" start suite "$n" >/dev/null 2>&1
    L "$d" done  suite "$n" --evidence "$ev" >/dev/null 2>&1
  done
  survivor="$(cd / && env -i PATH="$PATH" HOME="$HOME" CLAUDE_PROJECT_DIR="$d" \
              "$LEDGER" next suite 2>/dev/null)"
  chk "scrubbed re-invocation resumes at the right task" "$(col "$survivor" 1)/$(col "$survivor" 2)" "3/gamma"
  # The expensive failure is not "forgets where it was", it is "redoes finished work". The
  # refusal lives on `start`: `done` is deliberately idempotent so a retried write is safe.
  ( cd / && env -i PATH="$PATH" HOME="$HOME" CLAUDE_PROJECT_DIR="$d" \
    "$LEDGER" start suite 1 ) >/dev/null 2>&1
  chk "a new process refuses to restart a completed task" "$?" "2"
  ( cd / && env -i PATH="$PATH" HOME="$HOME" CLAUDE_PROJECT_DIR="$d" \
    "$LEDGER" done suite 1 --evidence "$ev" ) >/dev/null 2>&1
  chk "re-running done on a finished task is idempotent" "$?" "0"
  chk "  ... and does not reopen it" "$(tstatus "$d" suite 1)" "done"
  chk "progress is a file, not a variable" \
      "$(find "$d/.claude/work" -type f 2>/dev/null | grep -q . && echo yes || echo no)" "yes"
fi
echo

# ── 3. fabricated completion ───────────────────────────────────────────────────────────
# `done` is the only verb that can lie. Evidence that does not exist on disk is the cheapest
# possible lie, so it must be the one that costs the most.
echo "3. fabricated completion: done without a real artifact"
if [ ! -x "$LEDGER" ]; then skp "ledger evidence enforcement" "bin/ledger not present yet"
else
  d="$(newrepo)"; mkplan "$d"
  L "$d" init suite --plan "$d/plan.md" >/dev/null 2>&1
  L "$d" start suite 1 >/dev/null 2>&1
  L "$d" done suite 1 --evidence "$d/.claude/evidence/ghost.json" >/dev/null 2>&1
  chk "nonexistent evidence path refused" "$?" "2"
  L "$d" done suite 1 >/dev/null 2>&1
  chk "no --evidence at all refused" "$?" "2"
  : > "$d/empty.json"; L "$d" done suite 1 --evidence "$d/empty.json" >/dev/null 2>&1
  chk "zero-byte evidence refused" "$?" "2"
  # A refusal that still advanced the ledger would be worse than no refusal at all. The task
  # is in_progress, so `next` correctly skips it — the state file is what settles this.
  chk "a refused completion leaves the task open" "$(tstatus "$d" suite 1)" "in_progress"
  mkevidence "$d"
  L "$d" done suite 1 --evidence "$d/.claude/evidence/latest.json" >/dev/null 2>&1
  chk "same task completes once the artifact exists" "$?" "0"
fi
echo

# ── 4. escalation ladder, thrash, and agreement with the ledger ────────────────────────
# Six rounds against the same traceback is not persistence, it is a loop burning budget.
# The rung is asserted against the ROUND the tool itself reports, not against a counter kept
# here — so an off-by-one in either place shows up as a contradiction rather than cancelling.
echo "4. fix-loop escalation, thrash detection, ledger agreement"
if [ ! -x "$ESCALATE" ]; then skp "escalate ladder + thrash" "bin/escalate not present yet"
else
  d="$(newrepo)"
  adv="$(E "$d" advise LADDER 1 2>/dev/null)"; rc=$?
  chk "a task with no history advises retry-same" "$(fld "$adv" ROUND)/$(fld "$adv" ACTION)/$rc" "1/retry-same/0"
  chk "advise prints ROUND ACTION MODEL REASON" \
      "$([ -n "$(fld "$adv" ROUND)" ] && [ -n "$(fld "$adv" ACTION)" ] && \
         [ -n "$(fld "$adv" MODEL)" ] && [ -n "$(fld "$adv" REASON)" ] && echo yes || echo no)" "yes"

  m_early=""; m_late=""; stopped_at=""
  for i in 1 2 3 4 5 6; do
    E "$d" record LADDER 1 --signature "distinct-failure-$i" >/dev/null 2>&1
    adv="$(E "$d" advise LADDER 1 2>/dev/null)"; rc=$?
    r="$(fld "$adv" ROUND)"; a="$(fld "$adv" ACTION)"; m="$(fld "$adv" MODEL)"
    case "$r" in
      1|2|3) chk "round $r -> same implementer, inherited model" "$a/$m" "retry-same/inherit"; m_early="$m" ;;
      4|5)   chk "round $r -> fresh implementer, one tier up"    "$a/$m" "fresh-implementer/tier-up"; m_late="$m" ;;
      *)     chk "round $r -> stop, exit 1"                      "$a/$rc" "stop/1"; stopped_at="$r"; break ;;
    esac
  done
  chk "the ladder reaches a stop within the budget" "${stopped_at:-never}" "6"
  # The tier-up is the only reason rounds 4-5 are a separate rung. If MODEL never changes,
  # the ladder is decoration.
  chk "the model actually tiers up" \
      "$([ -n "$m_early" ] && [ -n "$m_late" ] && [ "$m_early" != "$m_late" ] && echo yes || echo no)" "yes"

  # THRASH — the same signature means the last fix changed nothing, so the remaining budget
  # would buy nothing either. This must fire well before round 6.
  d2="$(newrepo)"
  E "$d2" record THRASH 1 --signature "AssertionError: expected 3 got 4" >/dev/null 2>&1
  adv="$(E "$d2" record THRASH 1 --signature "AssertionError: expected 3 got 4" 2>/dev/null)"; rc=$?
  r="$(fld "$adv" ROUND)"
  chk "repeated signature stops immediately" "$(fld "$adv" ACTION)/$rc" "stop/1"
  chk "the stop lands before the budget is spent" \
      "$( { [ -n "$r" ] && [ "$r" -lt 6 ] 2>/dev/null; } && echo yes || echo no)" "yes"
  chk "the reason names thrash, not budget" \
      "$(printf '%s' "$adv" | grep -qi 'thrash' && echo yes || echo no)" "yes"
  chk "the thrash stop is sticky across processes" "$(fld "$(E "$d2" advise THRASH 1 2>/dev/null)" ACTION)" "stop"
  E "$d2" reset THRASH 1 >/dev/null 2>&1; chk "reset exits 0" "$?" "0"
  chk "reset clears the stop" "$(fld "$(E "$d2" advise THRASH 1 2>/dev/null)" ACTION)" "retry-same"
  E "$d2" selftest >/dev/null 2>&1; chk "escalate selftest exits 0" "$?" "0"

  # AGREEMENT — the two tools hold the same budget from different sides. If the ledger gives
  # up on a task while escalate still says "retry the same implementer", the driving agent
  # gets contradictory instructions and the disagreement is invisible until a run stalls.
  if [ -x "$LEDGER" ]; then
    d3="$(newrepo)"; mkplan "$d3"
    L "$d3" init suite --plan "$d3/plan.md" >/dev/null 2>&1
    for i in 1 2 3; do
      L "$d3" start suite 1 >/dev/null 2>&1
      L "$d3" fail  suite 1 --reason "attempt $i failed" >/dev/null 2>&1
      E "$d3" record suite 1 --signature "ledger-attempt-$i" >/dev/null 2>&1
    done
    chk "ledger blocks the task after its attempt budget" "$(tstatus "$d3" suite 1)" "blocked"
    chk "a blocked task is never handed out again" \
        "$(col "$(L "$d3" next suite 2>/dev/null)" 1)" "2"
    chk "escalate agrees the same implementer is done" \
        "$(fld "$(E "$d3" advise suite 1 2>/dev/null)" ACTION)" "fresh-implementer"
  else skp "ledger/escalate budget agreement" "bin/ledger not present yet"; fi
fi
echo

# ── 5. scope collision ─────────────────────────────────────────────────────────────────
# "One writer per worktree, always" is the documented rule this enforces. Prefix overlap is
# the case a naive string compare misses: 'src/**' and 'src/api/**' are different strings
# and the same files.
echo "5. parallel-safety claims and collisions"
if [ ! -x "$GUARD" ]; then skp "worktree-guard collisions" "bin/worktree-guard not present yet"
else
  d="$(newrepo)"
  G "$d" claim T1 --scope 'src/**'      >/dev/null 2>&1; chk "first claim granted" "$?" "0"
  G "$d" claim T2 --scope 'src/**'      >/dev/null 2>&1; chk "identical scope refused" "$?" "2"
  G "$d" claim T3 --scope 'src/api/**'  >/dev/null 2>&1; chk "narrower prefix overlap refused" "$?" "2"
  G "$d" claim T4 --scope 'srcextra/**' >/dev/null 2>&1; chk "lookalike sibling path granted" "$?" "0"
  G "$d" claim T5 --scope 'docs/**'     >/dev/null 2>&1; chk "disjoint scope granted" "$?" "0"
  out="$(G "$d" list 2>/dev/null)";                      chk "list exits 0" "$?" "0"
  chk "list names the live claim" "$(printf '%s' "$out" | grep -q 'T1' && echo yes || echo no)" "yes"
  G "$d" release T1 >/dev/null 2>&1;                     chk "release exits 0" "$?" "0"
  G "$d" claim T3 --scope 'src/api/**'  >/dev/null 2>&1; chk "blocked scope granted after release" "$?" "0"
  G "$d" check T3 'src/api/handlers.ts' >/dev/null 2>&1; chk "check: path inside own scope" "$?" "0"
  G "$d" check T3 'docs/readme.md'      >/dev/null 2>&1; chk "check: path outside own scope refused" "$?" "2"
  G "$d" stale --dry-run >/dev/null 2>&1;                chk "stale exits 0" "$?" "0"
  G "$d" selftest >/dev/null 2>&1;                       chk "worktree-guard selftest exits 0" "$?" "0"
fi
echo

# ── 6. corrupt state must fail closed ──────────────────────────────────────────────────
# This project already shipped a verifier that emitted all_green:true on a config it could
# not parse. The same defect in a ledger is worse: an unreadable ledger that re-initialises
# silently hands out task 1 again, and every completed task is redone.
#
# State files are DISCOVERED by diffing the tree, not hardcoded, so this covers whatever the
# tools write — including files a hand-written selftest forgot.
#
# Two exemptions, both verified against the implementations rather than assumed: `.log`
# files (a human-readable append log is an artifact, not state anything parses) and `.lock`
# files (ledger takes an fcntl advisory lock on an empty sentinel — the bytes inside it are
# never read, so corrupting them proves nothing). Anything else the tools write is state
# they will act on, and must therefore refuse to misread.
echo "6. corrupt state fails closed"
GARBAGE='%%% this is not a ledger {[, '
TRUNCATED='{"tasks":[{"n":1,"status":"pending"'

# corrupt_case <label> <dir> <init-shell-cmd> -- <read command...>
corrupt_case(){
  local label="$1" dir="$2" init="$3"; shift 3; [ "${1:-}" = "--" ] && shift
  local before after files f keep payload what rc
  before="$(find "$dir" -type f -not -path '*/.git/*' 2>/dev/null | sort)"
  eval "$init" >/dev/null 2>&1
  after="$(find "$dir" -type f -not -path '*/.git/*' 2>/dev/null | sort)"
  files="$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after") \
           | grep -v '\.log$' | grep -v '\.lock$')"
  if [ -z "$files" ]; then chk "$label writes state to disk" "no-state-file-found" "state-file"; return; fi

  # Herestring, not a pipe: a `while` on the right of a pipe runs in a subshell and its
  # pass/fail tallies would be silently discarded — a counter that loses failures is the
  # same class of bug this suite exists to catch.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    keep="$(mktemp "$SUITE_TMP/orig.XXXXXX")"; cp "$f" "$keep"
    for payload in "$GARBAGE" "$TRUNCATED" ""; do
      case "$payload" in
        "$GARBAGE")   what="garbage" ;;
        "$TRUNCATED") what="truncated json" ;;
        *)            what="emptied" ;;
      esac
      printf '%s' "$payload" > "$f"
      ( cd "$dir" && CLAUDE_PROJECT_DIR="$dir" "$@" ) >/dev/null 2>&1; rc=$?
      chk_nz "$label refuses $what $(basename "$f")" "$rc"
    done
    # A failed read must not repair itself. Silent reinitialisation is how a corrupt ledger
    # becomes a confidently wrong one — it loses the record of what is already done.
    printf '%s' "$GARBAGE" > "$f"
    ( cd "$dir" && CLAUDE_PROJECT_DIR="$dir" "$@" ) >/dev/null 2>&1
    chk "$label leaves corrupt $(basename "$f") untouched" \
        "$([ "$(cat "$f" 2>/dev/null)" = "$GARBAGE" ] && echo unchanged || echo rewritten)" "unchanged"
    cp "$keep" "$f"; rm -f "$keep"
  done <<< "$files"
}

if [ -x "$LEDGER" ]; then
  d="$(newrepo)"; mkplan "$d"
  corrupt_case "ledger" "$d" "L '$d' init suite --plan '$d/plan.md'" -- "$LEDGER" next suite
  # Deleting the ledger is not the same as never having had one. A missing file where a run
  # was recorded must refuse, not start over at task 1.
  rm -f "$d"/.claude/work/*.json
  L "$d" next suite >/dev/null 2>&1; chk_nz "ledger refuses a deleted ledger" "$?"
else skp "ledger corrupt-state" "bin/ledger not present yet"; fi

if [ -x "$ESCALATE" ]; then
  d="$(newrepo)"
  corrupt_case "escalate" "$d" "E '$d' record C1 1 --signature sig-a" -- "$ESCALATE" advise C1 1
else skp "escalate corrupt-state" "bin/escalate not present yet"; fi

if [ -x "$GUARD" ]; then
  d="$(newrepo)"
  corrupt_case "worktree-guard" "$d" "G '$d' claim C1 --scope 'src/**'" -- "$GUARD" claim C2 --scope 'other/**'
else skp "worktree-guard corrupt-state" "bin/worktree-guard not present yet"; fi

echo
echo "7. unreadable state must not wear a keep-going exit code"
# Section 6 asks only "did it refuse" (chk_nz), and that is exactly why this defect survived
# it: a corrupt ledger DID exit non-zero — it exited 1, and 1 is the ledger's code for
# "nothing left to hand out". An agent looping `while ledger next` reads 1 as "plan complete"
# and stops, certifying unfinished work as done. Refusing is not enough; the code must not be
# one the caller reads as progress. So these assert the EXACT fail-closed code.
#
# The trigger is a single non-UTF-8 byte, which JSON-level checks never see: the decode blows
# up first, and UnicodeDecodeError is a ValueError, not an OSError, so an `except OSError`
# read handler lets it through and python dies with a bare traceback and status 1.
flipbyte(){ python3 -c 'import sys
b=bytearray(open(sys.argv[1],"rb").read()); b[5]=0xff; open(sys.argv[1],"wb").write(bytes(b))' "$1"; }

if [ -x "$LEDGER" ]; then
  d="$(newrepo)"; mkplan "$d"
  L "$d" init suite --plan "$d/plan.md" >/dev/null 2>&1
  L "$d" next suite >/dev/null 2>&1; chk "healthy ledger hands out work" "$?" "0"
  flipbyte "$d/.claude/work/suite.json"
  L "$d" next suite   >/dev/null 2>&1; chk "non-UTF-8 ledger -> 3, not 1 (not 'done')" "$?" "3"
  L "$d" status suite >/dev/null 2>&1; chk "  ... status agrees"                       "$?" "3"
  L "$d" json suite   >/dev/null 2>&1; chk "  ... json agrees"                         "$?" "3"
else skp "ledger non-utf8" "bin/ledger not present yet"; fi

if [ -x "$GUARD" ]; then
  d="$(newrepo)"
  G "$d" claim C1 --scope 'src/**' >/dev/null 2>&1; chk "healthy guard grants a claim" "$?" "0"
  flipbyte "$(git -C "$d" rev-parse --show-toplevel)/.claude/work/claims.json"
  G "$d" claim C2 --scope 'other/**' >/dev/null 2>&1; chk "non-UTF-8 claims -> 3, not 1 (not usage)" "$?" "3"
  G "$d" list                        >/dev/null 2>&1; chk "  ... list agrees"                        "$?" "3"
else skp "worktree-guard non-utf8" "bin/worktree-guard not present yet"; fi

echo
echo "8. a flag with no value refuses; it never spins"
# `shift 2` with one argument left FAILS and does NOT shift, so a flag-parsing `while [ $# -gt
# 0 ]` re-reads the same flag forever at 100% CPU. Trivially reachable from agent-generated
# shell: `--evidence $EV` with EV empty expands to a bare flag. A hang is the one failure an
# autonomous loop cannot recover from — it wedges the run instead of ending it with a code.
# `run_bounded` returns HUNG rather than a code so the report names the real symptom.
run_bounded(){
  local d="$1" bin="$2"; shift 2
  ( cd "$d" && CLAUDE_PROJECT_DIR="$d" "$bin" "$@" >/dev/null 2>&1 ) & local bg=$!
  local i=0
  while [ "$i" -lt 25 ]; do kill -0 "$bg" 2>/dev/null || break; sleep 0.2; i=$((i+1)); done
  if kill -0 "$bg" 2>/dev/null; then kill -9 "$bg" 2>/dev/null; wait "$bg" 2>/dev/null; printf 'HUNG'
  else wait "$bg"; printf '%s' "$?"; fi
}

if [ -x "$LEDGER" ]; then
  d="$(newrepo)"; mkplan "$d"
  L "$d" init suite --plan "$d/plan.md" >/dev/null 2>&1
  printf 'gate output\n' > "$d/ev.txt"
  chk "init  --plan with no value"     "$(run_bounded "$d" "$LEDGER" init nope --plan)"        "2"
  chk "done  --evidence with no value" "$(run_bounded "$d" "$LEDGER" done suite 1 --evidence)" "2"
  chk "fail  --reason with no value"   "$(run_bounded "$d" "$LEDGER" fail suite 1 --reason)"   "2"
  chk "rule  --text with no value"     "$(run_bounded "$d" "$LEDGER" rule suite --text)"       "2"
  chk "trailing flag after a good one" \
      "$(run_bounded "$d" "$LEDGER" done suite 1 --evidence "$d/ev.txt" --evidence)" "2"
  # The refusal must be total: nothing was recorded on the way out.
  chk "  ... and the task stayed open" "$(tstatus "$d" suite 1)" "pending"
else skp "ledger flag hygiene" "bin/ledger not present yet"; fi

echo
if [ "$((pass+fail))" -eq 0 ]; then
  echo "ORCHESTRATION TESTS NOT RUN  ($skipped skipped — no orchestrator binary present)"
  echo "  Nothing was verified. That is not a pass."
  exit 3
elif [ "$fail" -eq 0 ]; then
  echo "ORCHESTRATION TESTS PASSED  ($pass checks, $skipped skipped)"; exit 0
else
  echo "ORCHESTRATION TESTS FAILED  ($fail of $((pass+fail)) checks, $skipped skipped)"; exit 1
fi
