#!/usr/bin/env bash
# Materialise each case as a real git repo (before commit -> after commit) so the actual
# scan-diff-cheats.sh runs on it. Reimplementing the gate's regexes here would measure a
# copy of the gate, not the gate.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OUT="${1:?usage: build-cases.sh <outdir>}"
mkdir -p "$OUT"
for f in "$HERE"/cases/*.before; do
  id="$(basename "$f" .before)"
  path="$(cat "$HERE/cases/$id.path")"
  d="$OUT/$id"; mkdir -p "$d/$(dirname "$path")"
  ( cd "$d" && git init -q . && git config user.email b@b && git config user.name b )
  cp "$f" "$d/$path"
  ( cd "$d" && git add -A >/dev/null && git commit -qm before >/dev/null )
  cp "$HERE/cases/$id.after" "$d/$path"
  ( cd "$d" && git add -A >/dev/null && git commit -qm after >/dev/null )
  ( cd "$d" && git diff HEAD~1...HEAD > "$HERE/cases/$id.diff" )
done
