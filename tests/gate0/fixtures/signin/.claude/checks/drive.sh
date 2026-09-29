#!/bin/sh
scenario="$1"
steps="$(mktemp "${TMPDIR:-/tmp}/signin-steps.XXXXXX")"
trap 'rm -f "$steps"' EXIT
node .claude/checks/steps.mjs "$scenario" > "$steps" || exit $?
node .claude/gates/drive.mjs "$BASE_URL/login" "$steps"
