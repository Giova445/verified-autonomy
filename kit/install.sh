#!/usr/bin/env bash
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$KIT/.." && pwd)"
TARGET="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$TARGET"
echo "installing into: $TARGET"

mkdir -p bin .claude/bin .claude/hooks .claude/gates .claude/agents

for f in "$SRC"/bin/*; do
  [ -f "$f" ] && install -m 0755 "$f" "bin/$(basename "$f")" && echo "  bin/$(basename "$f")"
done
# The Stop hook resolves its runner beside itself, never from the repo, so it needs its own copy.
install -m 0755 "$SRC/bin/verify" .claude/bin/verify && echo "  .claude/bin/verify"
for f in "$SRC"/hooks/*.sh "$SRC"/hooks/*.py; do
  [ -f "$f" ] && install -m 0755 "$f" ".claude/hooks/$(basename "$f")" && echo "  .claude/hooks/$(basename "$f")"
done
for f in acceptance.py drive.mjs; do
  install -m 0755 "$SRC/benchmark/gates/$f" ".claude/gates/$f" && echo "  .claude/gates/$f"
done
cp "$KIT/agents/verifier.md" .claude/agents/ && echo "  .claude/agents/verifier.md"
install -m 0755 "$KIT/selftest.sh" .claude/hooks/selftest.sh && echo "  .claude/hooks/selftest.sh"

bash bin/arm write . || echo "  arm found no command that passes here yet — no gates.json written"

if [ -f AGENTS.md ]; then
  cp "$KIT/AGENTS.md.template" AGENTS.md.new && echo "  AGENTS.md exists — wrote AGENTS.md.new to merge"
else
  cp "$KIT/AGENTS.md.template" AGENTS.md && echo "  AGENTS.md"
fi

for line in ".claude/evidence/" ".claude/.gate-attempts" ".claude/gates.json.new" ".claude/gates.json.surfaced" "AGENTS.md.new"; do
  grep -qxF "$line" .gitignore 2>/dev/null || echo "$line" >> .gitignore
done

cat <<'NEXT'

next:
  1. review .claude/gates.json — arm wrote only commands that passed here
  2. merge kit/adapters/claude-code.settings.json into .claude/settings.json
  3. bash .claude/hooks/selftest.sh
NEXT
