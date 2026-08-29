#!/usr/bin/env bash
# concurrent-writers.sh — do concurrent writers on shared git state lose work SILENTLY?
#
# claude-code#55724 reports 8 of 13 concurrent worktree agents failing with PERMANENT work
# loss, the failure surfacing as `Unable to create '.git/index.lock': File exists` after which
# the agent exits without committing and auto-cleanup deletes the tree.
#
# The property under test is not "does it error" but "does it lose writes". A race that drops
# a commit and returns 0 is far worse than one that crashes, because nothing surfaces it.
# So this counts COMMITS THAT LANDED against commits attempted, and treats a silent shortfall
# as the finding.
#
#   concurrent-writers.sh [n_writers] [mode]     mode = worktree | clone
set -uo pipefail
N="${1:-13}"; MODE="${2:-worktree}"
BASE="$(mktemp -d)"
( cd "$BASE" && git init -q . && git config user.email c@c && git config user.name c
  echo seed > seed.txt && git add -A && git commit -qm seed ) >/dev/null 2>&1

start="$(mktemp)"; : > "$start"
for i in $(seq 1 "$N"); do
  (
    d="$BASE/../w$i.$$"
    if [ "$MODE" = clone ]; then
      git clone -q "$BASE" "$d" 2>/dev/null
    else
      git -C "$BASE" worktree add -q -b "b$i" "$d" 2>/dev/null
    fi
    [ -d "$d" ] || exit 0
    cd "$d" || exit 0
    git config user.email c@c; git config user.name c
    echo "writer $i" > "f$i.txt"
    git add -A >/dev/null 2>&1
    git commit -qm "writer $i" >/dev/null 2>&1 && echo "$i" >> "$start"
    if [ "$MODE" = clone ]; then
      git push -q origin HEAD:"refs/heads/b$i" >/dev/null 2>&1 || true
    fi
  ) &
done
wait

landed_local="$(sort -u "$start" | grep -c . || echo 0)"
# What actually exists in the shared repo afterwards is the only thing that counts.
refs="$(git -C "$BASE" for-each-ref --format='%(refname:short)' refs/heads 2>/dev/null | grep -c '^b' || echo 0)"

echo "mode=$MODE writers=$N"
echo "  commits the writers believed they made : $landed_local"
echo "  branches actually present in shared repo: $refs"
if [ "$landed_local" -gt "$refs" ]; then
  echo "  SILENT LOSS: $((landed_local - refs)) commit(s) reported success and are not there"
elif [ "$landed_local" -lt "$N" ]; then
  echo "  $((N - landed_local)) writer(s) failed loudly (visible error, no silent loss)"
else
  echo "  no loss detected at this concurrency"
fi

# ---- the failure mode actually reported, which the loop above does NOT exercise ----
# claude-code#55724's loss is not git dropping a commit. It is: agent errors out BEFORE
# committing, then auto-cleanup removes the worktree, taking the uncommitted work with it.
# Raw-git concurrency and harness cleanup are different layers, and the loop above only
# tests the first. This tests the second.
echo
echo "harness-cleanup failure mode (uncommitted work + automatic tree removal):"
d2="$BASE/../uncommitted.$$"
git -C "$BASE" worktree add -q -b cleanup-probe "$d2" >/dev/null 2>&1
if [ -d "$d2" ]; then
  echo "substantial uncommitted work" > "$d2/important.txt"
  dirty="$(git -C "$d2" status --porcelain | grep -c . || echo 0)"
  # what a cleanup step does when it does not check for uncommitted changes
  rm -rf "$d2"
  git -C "$BASE" worktree prune >/dev/null 2>&1
  if [ -e "$d2/important.txt" ]; then
    echo "  work survived cleanup"
  else
    echo "  LOST: $dirty uncommitted change(s) destroyed by tree removal, no error raised"
    echo "  => the guard is 'never remove a worktree with a dirty index', not a lock"
  fi
fi

git -C "$BASE" worktree prune >/dev/null 2>&1
rm -rf "$BASE" "$BASE"/../w*.$$ "$start" 2>/dev/null
