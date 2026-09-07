#!/usr/bin/env bash
# deny-dangerous.sh — PreToolUse hook.
#
# Blocks irreversible operations and, critically, blocks the agent from editing its
# own guardrails. An agent that can edit gates.json has no gates.
#
# Install:
#   "hooks": { "PreToolUse": [ { "matcher": "Bash|Write|Edit|NotebookEdit", "hooks": [
#       { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/deny-dangerous.sh",
#         "timeout": 5000 } ] } ] }
set -uo pipefail

INPUT="$(cat)"

# Extract fields safely. Do NOT use `read` here — it word-splits, which silently
# truncates every multi-word command to its first token and disables all matchers.
eval "$(python3 - "$INPUT" <<'PY'
import json, shlex, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    d = {}
ti = d.get("tool_input") or {}
print("TOOL=" + shlex.quote(str(d.get("tool_name") or "")))
print("CMD="  + shlex.quote(str(ti.get("command")   or "")))
print("FILE=" + shlex.quote(str(ti.get("file_path") or "")))
PY
)"

# MASKED is CMD with only the provably-non-executing spans blanked — arguments to echo and
# printf, and python -c programs that are nothing but print() of literals. See
# inert-mask.py for why this is an allowlist of print sinks and not "strip quoted regions".
# If the helper is missing or errors, MASKED falls back to CMD: a masker that cannot run
# must not silently disable matching.
MASK_BIN="$(dirname "${BASH_SOURCE[0]}")/inert-mask.py"
if [ -f "$MASK_BIN" ]; then
  MASKED="$(python3 "$MASK_BIN" "$CMD" 2>/dev/null)" || MASKED="$CMD"
  [ -z "$MASKED" ] && [ -n "$CMD" ] && MASKED="$CMD"
else
  MASKED="$CMD"
fi

deny() { echo "BLOCKED by deny-dangerous.sh: $1" >&2; exit 2; }

# ------------------------------- guardrail self-protection: REMOVED (operator decision)
# This hook used to refuse every write to .claude/settings.json, .claude/hooks/,
# gates.json, .github/workflows/, bin/verify|ratchet|ruff-changed, .quality-baseline/
# and the plugin cache -- for Write/Edit (matched on file_path) and for Bash (write
# verbs bound to those paths).
#
# Removed at the operator's explicit instruction: "if any tool wants to modify the
# hooks, let them." The rule had no notion of WHO was asking, so it could not tell an
# agent disabling its own enforcement from the operator configuring their tooling. It
# hard-blocked with exit 2 and offered no approval path, and because it also protected
# the plugin directory it blocked the agent from helping fix it.
#
# WHAT THIS COSTS, stated plainly rather than buried: an agent can now edit or delete
# the gates, this hook, the Stop hook and the CI workflow, and nothing here objects.
# What stands between an agent and the enforcement is git review and branch protection,
# not this file. A softer middle path -- returning permissionDecision "ask" so the
# operator approves each edit -- was offered and declined in favour of full removal.
#
# To restore: the exact cases this used to deny are preserved, reclassified rather than
# deleted, under POLICY CHANGE in benchmark/gates/corpus-deny.txt.
#
# Every OTHER protection in this file is untouched: filesystem-root and home deletes,
# force push, protected-branch push, self-merge and self-approval, destructive DDL,
# privilege escalation, world-writable permission changes, infrastructure teardown,
# credential file reads, snapshot self-approval, and exit-code suppression.

[ "$TOOL" != "Bash" ] && exit 0
[ -z "$CMD" ] && exit 0

# SCAN is MASKED with shell quoting and grouping characters flattened to spaces.
#
# Every rule below anchors its target on whitespace or end-of-line, so a quote sitting
# where a space was expected defeated them: bash -c "rm -rf /" was NOT blocked, because the
# character after the slash is a quote. Same for eval "sudo ...", printf "$(rm -rf /)", and
# python3 -c "...os.system('rm -rf /')". Four false negatives on destructive commands,
# invisible until the corpus gained cases that quote their payload.
#
# Flattening is safe HERE and only here, after masking: whatever quoting remains at this
# point surrounds live content, so turning its delimiters into spaces hides nothing and
# merely lets word boundaries work. ';' is deliberately NOT flattened — the DELETE FROM
# rule uses it to detect a missing WHERE clause.
SCAN="$(printf '%s' "$MASKED" | tr '"'"'"'`()' '      ')"

# ------------------------------------------------------------ destructive fs
# ANCHORED. The previous rule was a substring glob (*"rm -rf /"*), which matched every
# scoped delete under an absolute path: `rm -rf /tmp/scratch` and `rm -rf ~/Library/Caches`
# were both denied. Measured as 2 of 4 false positives in benchmark/gates. A deny list that
# blocks routine cleanup gets switched off, and then it protects nothing.
# The target must BE the root or home dir — nothing after the slash.
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+/([[:space:]]|$)' \
  && deny "recursive force delete of the filesystem root"
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+~/?([[:space:]]|$)' \
  && deny "recursive force delete of the home directory"
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+/\*' \
  && deny "recursive force delete of everything under root"
# rm -rf with an unresolved shell variable — the Replit-class footgun
echo "$SCAN" | grep -Eq 'rm[[:space:]]+-[rf]{2}[[:space:]]+\$' \
  && deny "rm -rf against an unresolved shell variable"

# --------------------------------------------------------------------- git
echo "$SCAN" | grep -Eq 'git[[:space:]]+push.*(--force|[[:space:]]-f([[:space:]]|$))' \
  && deny "force push"
echo "$SCAN" | grep -Eq 'git[[:space:]]+reset[[:space:]]+--hard' \
  && deny "git reset --hard discards uncommitted work"
echo "$SCAN" | grep -Eq 'git[[:space:]]+clean[[:space:]]+-[a-z]*f' \
  && deny "git clean -f destroys untracked files"
echo "$SCAN" | grep -Eq 'git[[:space:]]+push[[:space:]]+.*[[:space:]](main|master)([[:space:]]|$)' \
  && deny "direct push to a protected branch — deliver via branch + PR"

# ----------------------------------------------------------------- self-merge
# `review` and `--approve` are separated by the PR number in real usage
# (`gh pr review 42 --approve`), which the old adjacent-token pattern missed.
echo "$SCAN" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+merge' \
  && deny "an agent may not merge a pull request"
echo "$SCAN" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+review([[:space:]]|$)' \
  && echo "$SCAN" | grep -Eq '(--approve|-a([[:space:]]|$))' \
  && deny "an agent may not approve a pull request"

# QUOTED LITERALS — fixed, and not in the way this note previously ruled out.
# The rejected fix was "strip quoted regions before matching", which would blind the SQL
# rules below and wave through bash -c 'rm -rf /'. Both objections still stand and neither
# applies here: masking is an ALLOWLIST of sinks that print rather than execute, so psql,
# bash -c, sh -c, eval and everything unrecognised keep their payloads. Rules from the
# destructive-fs section down read $MASKED; the guardrail rules above deliberately still
# read $CMD, because editing enforcement is the one place to stay maximally paranoid.
# --------------------------------------------------------------------- SQL
echo "$SCAN" | grep -Eiq '(DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE)' \
  && deny "destructive DDL"
echo "$SCAN" | grep -Eiq 'DELETE[[:space:]]+FROM[[:space:]]+[a-z_.\"]+[[:space:]]*(;|$)' \
  && deny "DELETE FROM without a WHERE clause"

# ----------------------------------------------------------------- privilege
echo "$SCAN" | grep -Eq '(^|[[:space:]])sudo([[:space:]]|$)' && deny "sudo"
echo "$SCAN" | grep -Eq 'chmod[[:space:]]+(-[a-zA-Z]+[[:space:]]+)?777' && deny "chmod 777"

# ------------------------------------------------------------------- infra
echo "$SCAN" | grep -Eq '(terraform[[:space:]]+destroy|gh[[:space:]]+repo[[:space:]]+delete)' \
  && deny "infrastructure or repository destruction"

# ------------------------------------------------------------- credentials
echo "$SCAN" | grep -Eq '(\.aws/credentials|\.ssh/id_|\.netrc|\.pypirc)' \
  && deny "reading credential files"

# ------------------------------------------- snapshot / contract self-approval
echo "$SCAN" | grep -Eq '(jest[[:space:]].*-u([[:space:]]|$)|--update-snapshots|--snapshot-update|pact-broker[[:space:]]+publish)' \
  && deny "an agent may not re-record snapshots or contracts. Propose the diff for separate approval."

# ------------------------------------------------- exit-code suppression in CI
echo "$SCAN" | grep -Eq '(\|\|[[:space:]]*true|--exit-zero)' \
  && deny "exit-code suppression — this hides a failing gate"

exit 0
