#!/usr/bin/env bash
set -uo pipefail
SUITE=g6
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ACCOUNT_EMAIL="tester@example.test"
ACCOUNT_PASSWORD="fixture-only-pw-1"

need_browser
ensure_python_deps

signin_run(){
  local repo="$1" out="$2" with_account="$3"
  if [ "$with_account" = "yes" ]; then
    ( export TEST_ACCOUNT_EMAIL="$ACCOUNT_EMAIL" TEST_ACCOUNT_PASSWORD="$ACCOUNT_PASSWORD"; run_verify "$repo" "$out" )
  else
    ( unset TEST_ACCOUNT_EMAIL TEST_ACCOUNT_PASSWORD; run_verify "$repo" "$out" )
  fi
}

echo "G6: signed-in page (holds with the account, BLOCKED without it)"

echo
echo "with the account: TEST_ACCOUNT_EMAIL and TEST_ACCOUNT_PASSWORD are set for this run"
repo="$(make_repo signin)"
out="$TMP/with.out"
chk "with: only sources are committed" "$(tracked_sources_only "$repo")" "0 dirty, 0 generated files tracked"
signin_run "$repo" "$out" yes; rc=$?
guard_said "$out" | sed 's/^/        /'
chk "with: verify product exits 0" "$rc" "0"
chk "with: every outcome holds" "$(verdicts "$repo")" "holds holds"
while IFS=$'\t' read -r title verdict check control code reason; do
  chk "with: '$title' holds with its control failing" "$verdict, $check, $control" "holds, check passed, control failed"
  note "control: $code${reason:+; $reason}"
done < <(outcome_rows "$repo")
chk "with: the server's own log names the port it listened on" "$([ "$(logged_ports "$repo" | wc -l | tr -d ' ')" -ge 1 ] && echo yes || echo no)" "yes"
chk "with: server stopped, nothing left listening or running" "$(left_behind "$repo")" "nothing"
note "the password appears in $(grep -rl "$ACCOUNT_PASSWORD" "$repo/.claude/evidence" 2>/dev/null | wc -l | tr -d ' ') file(s) under .claude/evidence"

echo
echo "without the account: both variables are unset for this run"
repo="$(make_repo signin)"
out="$TMP/without.out"
signin_run "$repo" "$out" no; rc=$?
guard_said "$out" | sed 's/^/        /'
chk "without: verify product exits non-zero" "$([ "$rc" -ne 0 ] && echo nonzero || echo "$rc")" "nonzero"
chk "without: every outcome is BLOCKED" "$(verdicts "$repo")" "BLOCKED BLOCKED"
chk "without: the output names what blocks it" \
  "$(grep -c 'blocked on: TEST_ACCOUNT_EMAIL, TEST_ACCOUNT_PASSWORD' "$out")" "1"
chk "without: no server was started and no check ran (no logs written)" \
  "$(ls "$repo/.claude/evidence"/*.log 2>/dev/null | wc -l | tr -d ' ')" "0"
chk "without: nothing left listening or running" "$(left_behind "$repo")" "nothing"
sed -n 's/^  - /        | /p' "$out"

finish "G6 SIGNED-IN"
