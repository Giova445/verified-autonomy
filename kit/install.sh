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

for f in verify ratchet ruff-changed; do
  [ -f "$KIT/bin/$f" ] && install -m 0755 "$KIT/bin/$f" "bin/$f" && echo "  bin/$f"
done
for f in "$KIT"/hooks/*.sh; do
  [ -f "$f" ] && install -m 0755 "$f" ".claude/hooks/$(basename "$f")" && echo "  .claude/hooks/$(basename "$f")"
done
[ -f "$KIT/agents/verifier.md" ] && cp "$KIT/agents/verifier.md" .claude/agents/ && echo "  .claude/agents/verifier.md"
[ -f "$KIT/selftest.sh" ] && install -m 0755 "$KIT/selftest.sh" ".claude/hooks/selftest.sh" && echo "  .claude/hooks/selftest.sh"

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

if [ -f .claude/gates.json ]; then
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
  1. edit .claude/gates.json  — commands must pass on a clean checkout TODAY
  2. merge kit/adapters/claude-code.settings.json into .claude/settings.json
  3. bash .claude/hooks/selftest.sh     <-- DO NOT SKIP. proves the gate actually fires.
NEXT
