#!/usr/bin/env bash
# install.sh — install the Verified Autonomy kit into ANY repo.
#
#   curl -fsSL <raw-url>/install.sh | bash        # or run it from a checkout:
#   bash path/to/kit/install.sh [target-repo]
#
# Idempotent. Never overwrites an existing gates.json or AGENTS.md — it writes .new
# alongside and tells you to merge, because clobbering a project's real config is exactly
# the kind of irreversible surprise this architecture exists to prevent.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$TARGET"
echo "installing into: $TARGET"

mkdir -p bin .claude/hooks .claude/agents .quality-baseline

# Everything the kit ships, not a hardcoded subset. The subset drifted: kit/gates.json's
# deferred tier named bin/test-delta, bin/holdout, bin/mutate-changed and bin/ambiguity while
# this loop installed four unrelated tools, so an agent promoting a deferred gate got
# command-not-found from instructions the kit itself had given it.
for f in "$KIT"/bin/*; do
  [ -f "$f" ] && install -m 0755 "$f" "bin/$(basename "$f")" && echo "  bin/$(basename "$f")"
done

# The Stop hook resolves its runner as <its own dir>/../bin/verify, deliberately refusing to
# fall back to $ROOT/bin/verify — a repo-committed path, where a 17-byte stub once became
# the gate runner and certified a red gate green. In a KIT install the hook lands in
# .claude/hooks/, so that resolution points at .claude/bin/verify, which nothing created:
# the hook then found no runner and exited 2 on every turn, whatever the gates said.
# Fail-closed, but unconditionally, which is a hook anyone would switch off within an hour.
# So the runner is installed where the hook looks — beside the hook, in the same trust
# domain as the hook itself, not at a path the hook merely discovers.
mkdir -p .claude/bin
install -m 0755 "$KIT/bin/verify" ".claude/bin/verify" && echo "  .claude/bin/verify (the Stop hook's runner)"
for f in "$KIT"/hooks/*.sh; do
  [ -f "$f" ] && install -m 0755 "$f" ".claude/hooks/$(basename "$f")" && echo "  .claude/hooks/$(basename "$f")"
done
[ -f "$KIT/agents/verifier.md" ] && cp "$KIT/agents/verifier.md" .claude/agents/ && echo "  .claude/agents/verifier.md"
[ -f "$KIT/selftest.sh" ] && install -m 0755 "$KIT/selftest.sh" ".claude/hooks/selftest.sh" && echo "  .claude/hooks/selftest.sh"

# The deliverable-contract machinery. Without these an installed kit can gate the PROCESS
# but never the PRODUCT: lint, typecheck and the unit suite all pass on a login page whose
# submit button never enables. bin/arm looks for them here when the kit is installed.
mkdir -p .claude/gates
for f in "$KIT"/gates/*; do
  [ -f "$f" ] && install -m 0755 "$f" ".claude/gates/$(basename "$f")" && echo "  .claude/gates/$(basename "$f")"
done

# ---- gates.json: detect the stack, never clobber -----------------------------
detect_gates() {
  local fast=() full=()
  if [ -f package.json ]; then
    grep -q '"lint"'  package.json && fast+=('{"name":"js-lint","cmd":"npm run lint"}')
    grep -q '"test"'  package.json && full+=('{"name":"js-test","cmd":"npm test --silent"}')
    [ -f tsconfig.json ] && full+=('{"name":"js-typecheck","cmd":"npx tsc --noEmit"}')
  fi
  if [ -f pyproject.toml ] || [ -f requirements.txt ] || [ -f setup.py ]; then
    command -v uv >/dev/null 2>&1 && R="uv run " || R=""
    fast+=("{\"name\":\"py-lint\",\"cmd\":\"${R}ruff check .\"}")
    full+=("{\"name\":\"py-test\",\"cmd\":\"${R}pytest -q\"}")
  fi
  [ -f go.mod ]    && { fast+=('{"name":"go-vet","cmd":"go vet ./..."}'); full+=('{"name":"go-test","cmd":"go test ./..."}'); }
  [ -f Cargo.toml ]&& { fast+=('{"name":"rs-clippy","cmd":"cargo clippy -- -D warnings"}'); full+=('{"name":"rs-test","cmd":"cargo test"}'); }

  full+=('{"name":"cheat-scan","cmd":".claude/hooks/scan-diff-cheats.sh"}')
  local IFS=,
  printf '{\n  "_comment": "AUTO-DETECTED. Replace with commands that pass on a clean checkout TODAY. Aspirational gates get switched off within a week.",\n  "fast": [%s],\n  "full": [%s],\n  "deferred": []\n}\n' "${fast[*]:-}" "${full[*]:-}"
}

# bin/arm RUNS each candidate and writes only what exits 0 here, so the result needs no
# review. detect_gates above wrote commands it had never run and told you to replace them;
# that review step is why .claude/gates.json was present in 0 of 242 project roots measured
# across the session corpus. It is kept only as the fallback for when arm is unavailable.
if [ -x bin/arm ]; then
  bash bin/arm write . || {
    echo "  arm found nothing that passes here — falling back to detection"
    [ -f .claude/gates.json ] || detect_gates > .claude/gates.json.unverified
    echo "  .claude/gates.json.unverified written; every command in it is UNTESTED"
  }
elif [ -f .claude/gates.json ]; then
  detect_gates > .claude/gates.json.new
  echo "  .claude/gates.json EXISTS — wrote .claude/gates.json.new for you to merge"
else
  detect_gates > .claude/gates.json
  echo "  .claude/gates.json (auto-detected — REVIEW IT)"
fi

if [ -f AGENTS.md ]; then
  cp "$KIT/AGENTS.md.template" AGENTS.md.new 2>/dev/null && echo "  AGENTS.md EXISTS — wrote AGENTS.md.new to merge"
else
  cp "$KIT/AGENTS.md.template" AGENTS.md 2>/dev/null && echo "  AGENTS.md"
fi

for line in ".claude/evidence/" ".claude/.gate-attempts" ".claude/gates.json.new" "AGENTS.md.new"; do
  grep -qxF "$line" .gitignore 2>/dev/null || echo "$line" >> .gitignore
done
echo "  .gitignore updated"

cat <<'NEXT'

next:
  1. review .claude/gates.json — arm wrote only commands that passed here just now
  2. merge kit/adapters/claude-code.settings.json into .claude/settings.json
  3. bash .claude/hooks/selftest.sh     <-- DO NOT SKIP. proves the gate actually fires.
NEXT
