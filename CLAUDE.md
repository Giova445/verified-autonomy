# CLAUDE.md — verified-autonomy

A Claude Code plugin that makes "done" something the harness proves: a Stop hook refuses the
turn while gates are red, and a PreToolUse hook blocks irreversible commands.

## Verify before claiming done

```bash
bash selftest.sh
```

Exit 0 and `SELF-TEST PASSED`. Needs `python3`, `git`, `node`, `pytest`, and Playwright
(`npm install` in this repo). A suite that cannot run reports `NOTRUN`, never a pass.

## Layout

```
hooks/            stop-gate.sh, deny-dangerous.sh (+ inert-mask.py, push-targets.py),
                  scan-diff-cheats.sh, session-start.sh, hooks.json
bin/              verify (the gate runner), arm, arm-surface.py, scope,
                  ledger, escalate, worktree-guard,
                  test-delta, holdout, mutate-changed, ambiguity, ratchet, ruff-changed
benchmark/gates/  acceptance.py + drive.mjs (deliverable contract), pin-check.py,
                  trailer-check.py, identity-preflight.py
kit/              install.sh copies from the repo root; templates and adapters
skills/, agents/  plugin skills and the verifier agent
docs/             architecture brief and gate ladder
```

`bin/verify` is a plain CLI so the Stop hook, Codex and CI all run the same command.

## Rules

- No code comments. A single line only when the why is genuinely non-obvious.
- A gate gets 2–3 controls: one case it must catch, one it must allow, one load-bearing edge.
- Expected sets are declared literally, never derived from the thing under test.
- Unreadable or missing config is never a pass.
- Protected branches live in `.claude/protected-branches` (default `main`, `master`).
- No commit carries a `Co-Authored-By` trailer, here or in any project the kit installs into.
- Project-agnostic, because this is headed for open source: no project, company, customer or
  domain names, no measurements from a specific codebase, no absolute machine paths. Examples
  use neutral domains (search, invoices, sign-in).
