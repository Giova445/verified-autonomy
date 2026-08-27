# Kit — Runnable Enforcement Layer

The parts of the architecture that are code rather than prose. Everything here is
project-agnostic; the only file you edit per project is `gates.json`.

## Contents

| File | Hook | Purpose |
|---|---|---|
| `hooks/gate.sh` | `Stop`, `SubagentStop` | Refuses to let the turn end while any gate is red. The core mechanism. |
| `hooks/deny-dangerous.sh` | `PreToolUse` | Blocks irreversible ops and self-modification of guardrails. |
| `hooks/scan-diff-cheats.sh` | gate + CI | Detects the documented ways an agent fakes a green gate. |
| `agents/verifier.md` | subagent | Adversarial reviewer. Runs after gates are green. |
| `gates.json` | config | **The one file you edit per project.** |
| `settings.hooks.json` | config | Merge into `.claude/settings.json`. |

## Install

```bash
mkdir -p .claude/hooks .claude/agents
cp docs/autonomous-agent-architecture/kit/hooks/*.sh   .claude/hooks/
cp docs/autonomous-agent-architecture/kit/agents/*.md  .claude/agents/
cp docs/autonomous-agent-architecture/kit/gates.json   .claude/gates.json
chmod +x .claude/hooks/*.sh
echo ".claude/evidence/" >> .gitignore
echo ".claude/.gate-attempts" >> .gitignore
```

Then edit `.claude/gates.json` with commands that pass on a clean checkout today, and
merge `settings.hooks.json` into `.claude/settings.json`.

## Verify it actually works

**Do not skip this.** An unverified gate is worse than no gate, because you will trust it.

```bash
# 1. The Stop gate must refuse a red build
printf '{"full":[{"name":"probe","cmd":"exit 1"}]}' > /tmp/g.json
cp .claude/gates.json /tmp/gates.bak && cp /tmp/g.json .claude/gates.json
echo '{}' | CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/gate.sh; echo "expect exit 2, got $?"
cp /tmp/gates.bak .claude/gates.json && rm -f .claude/.gate-attempts

# 2. The deny hook must block a force push
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin x"}}' \
  | .claude/hooks/deny-dangerous.sh; echo "expect exit 2, got $?"

# 3. A normal command must pass through
echo '{"tool_name":"Bash","tool_input":{"command":"npm test"}}' \
  | .claude/hooks/deny-dangerous.sh; echo "expect exit 0, got $?"
```

Then do the real test: break a test on purpose, ask the agent to finish, and watch it
refuse.

## Requirements

- `bash`, `git`, `python3` (standard library only — no PyYAML, no jq)
- macOS or Linux. On Windows, run under WSL2.

## Behavior notes

- **Circuit breaker.** `gate.sh` blocks at most `GATE_MAX_BLOCKS` times (default 6) on
  the same red gate, then demands a structured BLOCKED report instead of looping forever.
  Reset by deleting `.claude/.gate-attempts`.
- **Tier selection.** `GATE_TIER=fast` runs the fast gates; default is `full`.
- **No config, no enforcement.** If `.claude/gates.json` is absent, `gate.sh` exits 0 and
  stays out of the way. This is deliberate for gradual adoption — and it means a missing
  config silently disables the gate, so check it in.
- **Evidence bundle** is written to `.claude/evidence/latest.json` on every run,
  green or red.

## Extending

Add gates by adding entries to `gates.json` — no code change needed. Anything that exits
non-zero on failure works.

To add a new cheat detector, add a `flag` call in `scan-diff-cheats.sh`. Keep detectors
cheap; this runs on every completion attempt.

## Deliberate omissions

- **TDD RED-proof gate.** Enforcing "the test must fail first" requires knowing which
  test is new and running it at the pre-implementation commit. That is genuinely
  project-shaped (test runner, selection syntax, monorepo layout), so it is specified in
  [02 §3](../02-architecture.md) but not shipped as a generic script. Write it per project.
- **Language-specific gates.** Commands live in `gates.json` rather than in the hooks, so
  the hooks stay portable.
