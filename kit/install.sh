#!/usr/bin/env bash
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$KIT/.." && pwd)"
NEW_FILES=()

usage() {
  echo "usage: install.sh [--no-coauthor] [target-repo]" >&2
  echo "       install.sh --self-test" >&2
  exit 2
}

require_sources() {
  local f missing=0
  for f in bin/arm bin/verify benchmark/gates/acceptance.py benchmark/gates/drive.mjs \
           benchmark/gates/trailer-check.py kit/selftest.sh; do
    [ -f "$SRC/$f" ] || { echo "install: the kit is incomplete, missing $SRC/$f" >&2; missing=1; }
  done
  [ "$missing" -eq 0 ] || exit 2
}

write_forbidden_trailers() {
  mkdir -p .claude
  [ -e .claude/forbidden-trailers ] || printf 'Co-Authored-By\n' > .claude/forbidden-trailers
  echo "  .claude/forbidden-trailers"
}

set_attribution() {
  python3 - <<'PY'
import json, os, sys

path = ".claude/settings.json"
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError as exc:
        sys.exit(f"install: {path} is not valid JSON ({exc}); set attribution.commit to \"\" yourself")
    if not isinstance(data, dict):
        sys.exit(f"install: {path} is not a JSON object; set attribution.commit to \"\" yourself")
attribution = data.get("attribution") if isinstance(data.get("attribution"), dict) else {}
data["attribution"] = {**attribution, "commit": ""}
os.makedirs(".claude", exist_ok=True)
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  echo "  .claude/settings.json (attribution.commit is empty)"
}

place_own() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  install -m 0755 "$src" "$dest"
  echo "  $dest"
}

place_shared() {
  local src="$1" dest="$2" previous="$3"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] && ! cmp -s "$src" "$dest" && ! { [ -f "$previous" ] && cmp -s "$previous" "$dest"; }; then
    install -m 0755 "$src" "$dest.new"
    NEW_FILES+=("$dest.new")
    echo "  WARNING: $dest exists and differs from the kit's; wrote $dest.new and left yours alone. Merge it."
  else
    install -m 0755 "$src" "$dest"
    echo "  $dest"
  fi
}

copy_runtime() {
  local f
  for f in verify scope; do
    [ -f "$SRC/bin/$f" ] || continue
    place_shared "$SRC/bin/$f" "bin/$f" ".claude/bin/$f"
    place_own "$SRC/bin/$f" ".claude/bin/$f"
  done
  for f in acceptance.py drive.mjs trailer-check.py; do
    place_own "$SRC/benchmark/gates/$f" ".claude/gates/$f"
  done
  place_own "$SRC/hooks/state.py" ".claude/hooks/state.py"
  place_own "$KIT/selftest.sh" ".claude/selftest.sh"
}

is_ignored() { git check-ignore -q --no-index -- "$1" 2>/dev/null; }

add_ignore() {
  local pattern="$1" p need=0
  shift
  for p in "$@"; do is_ignored "$p" || need=1; done
  [ "$need" -eq 1 ] || return 0
  if [ -s .gitignore ] && [ -n "$(tail -c1 .gitignore)" ]; then echo >> .gitignore; fi
  printf '%s\n' "$pattern" >> .gitignore
  echo "  .gitignore: $pattern"
}

update_gitignore() {
  local f
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "  not a git repository: .gitignore left alone"
    return 0
  fi
  add_ignore '.claude/.gate-*' .claude/.gate-attempts .claude/.gate-judged .claude/.gate-stalled
  add_ignore '.claude/.sessions/' .claude/.sessions/session
  add_ignore '.claude/evidence/' .claude/evidence/latest.json
  [ -f .claude/gates.json.new ] && add_ignore '.claude/gates.json.new' .claude/gates.json.new
  for f in ${NEW_FILES[@]+"${NEW_FILES[@]}"}; do add_ignore "$f" "$f"; done
  return 0
}

install_into() {
  local no_coauthor="$1"
  echo "installing into: $PWD"
  require_sources
  [ "$no_coauthor" -eq 1 ] && write_forbidden_trailers
  ARM_INSTALLING=1 bash "$SRC/bin/arm" write . || echo "  arm found no command that passes here yet: no gates.json written"
  copy_runtime
  [ "$no_coauthor" -eq 1 ] && set_attribution
  update_gitignore
  cat <<'NEXT'

next: the verified-autonomy:setup skill finishes this. In Claude Code, say
  "set up verified-autonomy". It merges the gates, maps the product, writes and proves
  .claude/acceptance.json, runs the self-test and commits on a branch.
NEXT
}

EXPECTED_CONTROLS=11
self_test() {
  local root ok=0 ran=0 out listing want
  set +e
  root="$(mktemp -d)/with space"
  mkdir -p "$root"
  chk() {
    ran=$((ran + 1))
    if [ "$2" = 0 ]; then ok=$((ok + 1)); printf '  ok    %s\n' "$1"
    else printf '  FAIL  %s\n' "$1"; fi
  }
  fixture() {
    local pkg="${2-}" ignore="${3-.claude/*}"
    [ -n "$pkg" ] || pkg='{"scripts":{"test":"exit 0"}}'
    mkdir -p "$root/$1"
    ( cd "$root/$1" && git init -q . && git config user.email h@h && git config user.name h \
      && printf '%s' "$pkg" > package.json && { [ -z "$ignore" ] || printf '%s\n' "$ignore" > .gitignore; } \
      && git add -A && git commit -qm init ) >/dev/null 2>&1
  }
  run() { local d="$1"; shift; ( cd "$root/$d" && ARM_TIMEOUT=60 bash "$KIT/$(basename "${BASH_SOURCE[0]}")" "$@" 2>&1 ); }
  gate_names() { python3 -c 'import json,sys;print(",".join(g["name"] for g in json.load(open(sys.argv[1]))["full"]))' "$root/$1/.claude/gates.json" 2>/dev/null; }

  fixture plain
  run plain . >/dev/null
  listing="$( cd "$root/plain" && find bin .claude -type f | LC_ALL=C sort | tr '\n' ' ' )"
  want=".claude/bin/verify .claude/gates.json .claude/gates/acceptance.py .claude/gates/drive.mjs .claude/gates/trailer-check.py .claude/hooks/state.py .claude/selftest.sh bin/verify "
  [ -f "$SRC/bin/scope" ] && want=".claude/bin/scope .claude/bin/verify .claude/gates.json .claude/gates/acceptance.py .claude/gates/drive.mjs .claude/gates/trailer-check.py .claude/hooks/state.py .claude/selftest.sh bin/scope bin/verify "
  [ "$listing" = "$want" ]
  chk "only the runtime is copied (the runner helper, no hooks, agents, AGENTS.md or arm), in a path with a space" $?

  [ ! -e "$root/plain/.claude/settings.json" ] && [ ! -e "$root/plain/.claude/forbidden-trailers" ]
  chk "by default no attribution setting and no forbidden-trailers are written" $?

  [ "$(cat "$root/plain/.gitignore")" = ".claude/*" ]
  chk "gitignore lines are added only for paths not already ignored" $?

  fixture open '' ''
  run open . >/dev/null
  [ "$(cat "$root/open/.gitignore")" = "$(printf '.claude/.gate-*\n.claude/.sessions/\n.claude/evidence/')" ]
  chk "gitignore gets the state paths when nothing ignores them" $?

  run plain . >/dev/null
  [ "$(cat "$root/plain/.gitignore")" = ".claude/*" ] && [ ! -e "$root/plain/bin/verify.new" ]
  chk "a second install changes nothing and warns about nothing" $?

  fixture probe '{"scripts":{"lint":"sh -c \"test ! -e .claude/gates/acceptance.py\""}}'
  run probe . >/dev/null
  [ "$(gate_names probe)" = "js-lint" ]
  chk "commands are probed before anything is copied, so lint never sees the kit" $?

  fixture own
  mkdir -p "$root/own/bin"
  printf '#!/bin/sh\necho mine\n' > "$root/own/bin/verify"
  chmod +x "$root/own/bin/verify"
  out="$(run own .)"
  [ "$(sed -n 2p "$root/own/bin/verify")" = "echo mine" ] && [ -f "$root/own/bin/verify.new" ] \
    && printf '%s' "$out" | grep -q 'WARNING' && grep -qxF 'bin/verify.new' "$root/own/.gitignore"
  chk "a differing bin/verify is kept: the kit's copy lands as verify.new with a warning" $?

  fixture stale
  mkdir -p "$root/stale/bin" "$root/stale/.claude/bin"
  printf '#!/bin/sh\necho old kit\n' > "$root/stale/bin/verify"
  cp "$root/stale/bin/verify" "$root/stale/.claude/bin/verify"
  chmod +x "$root/stale/bin/verify" "$root/stale/.claude/bin/verify"
  run stale . >/dev/null
  cmp -s "$SRC/bin/verify" "$root/stale/bin/verify" && [ ! -e "$root/stale/bin/verify.new" ]
  chk "a bin/verify the kit installed earlier is refreshed in place" $?

  fixture agents
  printf 'my rules\n' > "$root/agents/AGENTS.md"
  run agents . >/dev/null
  [ "$(cat "$root/agents/AGENTS.md")" = "my rules" ] && [ ! -e "$root/agents/AGENTS.md.new" ]
  chk "AGENTS.md is never written" $?

  fixture nc
  mkdir -p "$root/nc/.claude"
  printf '{"model":"keep-me","attribution":{"pr":true}}\n' > "$root/nc/.claude/settings.json"
  run nc . --no-coauthor >/dev/null
  python3 - "$root/nc/.claude/settings.json" <<'PY'
import json, sys
want = {"model": "keep-me", "attribution": {"pr": True, "commit": ""}}
sys.exit(0 if json.load(open(sys.argv[1])) == want else 1)
PY
  local settings_ok=$?
  [ "$(cat "$root/nc/.claude/forbidden-trailers")" = "Co-Authored-By" ] && [ "$(gate_names nc)" = "js-test,co-author" ]
  local trailers_ok=$?
  [ "$settings_ok$trailers_ok" = "00" ]
  chk "--no-coauthor writes forbidden-trailers, arms co-author, merges attribution.commit into settings" $?

  fixture inst
  run inst . >/dev/null
  ( cd "$root/inst" && bash .claude/selftest.sh ) >/dev/null 2>&1
  chk "the installed self-test passes in the installed layout" $?

  rm -rf "$(dirname "$root")"
  [ "$ran" -eq "$EXPECTED_CONTROLS" ] || { printf '  FAIL  ran %s controls, expected %s\n' "$ran" "$EXPECTED_CONTROLS"; ok=-1; }
  echo
  if [ "$ok" -eq "$EXPECTED_CONTROLS" ]; then echo "SELF-TEST PASSED  ($EXPECTED_CONTROLS checks)"; return 0
  else echo "SELF-TEST FAILED  ($ok of $EXPECTED_CONTROLS checks)"; return 1; fi
}

NO_COAUTHOR=0
TARGET_ARG=""
for arg in "$@"; do
  case "$arg" in
    --no-coauthor) NO_COAUTHOR=1 ;;
    --self-test|selftest) self_test; exit $? ;;
    -*) usage ;;
    *) [ -z "$TARGET_ARG" ] || usage; TARGET_ARG="$arg" ;;
  esac
done

TARGET="${TARGET_ARG:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -d "$TARGET" ] || { echo "install: no such directory: $TARGET" >&2; exit 2; }
cd "$TARGET"
install_into "$NO_COAUTHOR"
