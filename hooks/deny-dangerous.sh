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

deny() { echo "BLOCKED by deny-dangerous.sh: $1" >&2; exit 2; }

# ---------------------------------------------------------------- guardrails
# Highest priority: the agent may not disable its own enforcement.
case "$FILE" in
  */.claude/hooks/*|*/.claude/gates.json|*/.claude/settings.json|*/.github/workflows/*\
  |*/bin/verify|*/bin/ratchet|*/bin/ruff-changed|*/.quality-baseline/*\
  |*/.claude/plugins/*|*/plugins/cache/*)
    deny "editing your own guardrails ($FILE) is not permitted. If a gate is wrong, say so and escalate — do not change it." ;;
esac

# The case above only sees Write/Edit. For Bash, $FILE is empty and that rule is a no-op,
# so in-place edits, redirects, and removals of guardrail files sailed through. Match the
# WRITE VERB bound to a protected path, per sub-command.
#
# Bind to the destination, not mere co-occurrence: a naive "protected path AND redirect"
# rule denies this system's own documented usage (running the verifier and redirecting its
# output to a scratch file).
#
# NOTE: this loop must NOT be `printf | tr | while` — a piped while runs in a subshell and
# `exit` inside it does not propagate, so the rule silently never fired (verified: status 0
# on both match and no-match). The here-string keeps the loop body in this shell.
#
# KNOWN FRICTION: because this matches command TEXT, authoring or copying these hook files
# from a shell trips the rule. That is working as designed — editing guardrails is supposed
# to require escalation — but it means maintainers edit these files with an editor, not a
# shell one-liner.
if [ -n "$CMD" ]; then
  PROT='(\.claude/(gates\.json|settings\.json|hooks/)|bin/(verify|ratchet|ruff-changed)|\.github/workflows/|\.quality-baseline/)'
  GUARD_HIT=0
  while IFS= read -r part; do
    [ -z "$part" ] && continue
    if   echo "$part" | grep -Eq ">>?[[:space:]]*[^[:space:]]*$PROT" \
      || echo "$part" | grep -Eq "(^|[[:space:]])(rm|mv|cp|tee|truncate|shred|chmod)([[:space:]]+-[^[:space:]]+)*[[:space:]]+[^|]*$PROT" \
      || echo "$part" | grep -Eq "sed[[:space:]]+-i[^|]*$PROT" \
      || echo "$part" | grep -Eq "find[^|]*$PROT[^|]*-delete" \
      || echo "$part" | grep -Eq "git[[:space:]]+checkout[^|]*--[[:space:]]*[^|]*$PROT" \
      || echo "$part" | grep -Eq "(python3?|node)[^|]*(open|writeFile)[^|]*$PROT"; then
      GUARD_HIT=1
    fi
  done <<< "$(printf '%s' "$CMD" | tr ';&|' '\n\n\n')"
  [ "$GUARD_HIT" -eq 1 ] && deny "that command writes to or removes a guardrail file. If a gate is wrong, say so and escalate — do not change it."
fi

[ "$TOOL" != "Bash" ] && exit 0
[ -z "$CMD" ] && exit 0

# ------------------------------------------------------------ destructive fs
case "$CMD" in
  *"rm -rf /"*|*"rm -rf ~"*|*"rm -fr /"*)
    deny "recursive force delete of a root or home path" ;;
esac
# rm -rf with an unresolved shell variable — the Replit-class footgun
echo "$CMD" | grep -Eq 'rm[[:space:]]+-[rf]{2}[[:space:]]+\$' \
  && deny "rm -rf against an unresolved shell variable"

# --------------------------------------------------------------------- git
echo "$CMD" | grep -Eq 'git[[:space:]]+push.*(--force|[[:space:]]-f([[:space:]]|$))' \
  && deny "force push"
echo "$CMD" | grep -Eq 'git[[:space:]]+reset[[:space:]]+--hard' \
  && deny "git reset --hard discards uncommitted work"
echo "$CMD" | grep -Eq 'git[[:space:]]+clean[[:space:]]+-[a-z]*f' \
  && deny "git clean -f destroys untracked files"
echo "$CMD" | grep -Eq 'git[[:space:]]+push[[:space:]]+.*[[:space:]](main|master)([[:space:]]|$)' \
  && deny "direct push to a protected branch — deliver via branch + PR"

# ----------------------------------------------------------------- self-merge
echo "$CMD" | grep -Eq 'gh[[:space:]]+pr[[:space:]]+(merge|review[[:space:]]+--approve)' \
  && deny "an agent may not approve or merge a pull request"

# --------------------------------------------------------------------- SQL
echo "$CMD" | grep -Eiq '(DROP[[:space:]]+(TABLE|DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE)' \
  && deny "destructive DDL"
echo "$CMD" | grep -Eiq 'DELETE[[:space:]]+FROM[[:space:]]+[a-z_.\"]+[[:space:]]*(;|$)' \
  && deny "DELETE FROM without a WHERE clause"

# ----------------------------------------------------------------- privilege
echo "$CMD" | grep -Eq '(^|[[:space:]])sudo([[:space:]]|$)' && deny "sudo"
echo "$CMD" | grep -Eq 'chmod[[:space:]]+(-[a-zA-Z]+[[:space:]]+)?777' && deny "chmod 777"

# ------------------------------------------------------------------- infra
echo "$CMD" | grep -Eq '(terraform[[:space:]]+destroy|gh[[:space:]]+repo[[:space:]]+delete)' \
  && deny "infrastructure or repository destruction"

# ------------------------------------------------------------- credentials
echo "$CMD" | grep -Eq '(\.aws/credentials|\.ssh/id_|\.netrc|\.pypirc)' \
  && deny "reading credential files"

# ------------------------------------------- snapshot / contract self-approval
echo "$CMD" | grep -Eq '(jest[[:space:]].*-u([[:space:]]|$)|--update-snapshots|--snapshot-update|pact-broker[[:space:]]+publish)' \
  && deny "an agent may not re-record snapshots or contracts. Propose the diff for separate approval."

# ------------------------------------------------- exit-code suppression in CI
echo "$CMD" | grep -Eq '(\|\|[[:space:]]*true|--exit-zero)' \
  && deny "exit-code suppression — this hides a failing gate"

exit 0
