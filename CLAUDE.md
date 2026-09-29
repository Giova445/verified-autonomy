# CLAUDE.md: verified-autonomy

A Claude Code plugin. A Stop hook refuses to end a turn while a changed repo fails its gates
or its product contract. A PreToolUse hook blocks a short list of irreversible commands.

## Verify before claiming done

```bash
bash selftest.sh
```

It must end `SELF-TEST PASSED`. It needs `python3`, `git`, `node`, `pytest` and Playwright
(`npm install` in this repo). A suite that cannot run reports `NOTRUN`, never a pass.

## Layout

```
hooks/            Stop, PreToolUse and SessionStart hooks, and hooks.json
bin/              verify (the gate runner), arm (arms gates from commands that pass),
                  scope (gate surfaces), discover (maps the product)
benchmark/gates/  acceptance.py and drive.mjs: the product contract and its browser driver
kit/              install.sh copies the runner and drivers into a repo
skills/           gate and setup, the only two skills
agents/           the verifier agent
docs/             how-it-works.md
```

## Rules

- Delete more than you add. A new rule, check or line of docs needs a reason it earns its cost.
- No code comments. One short line only when the why is not obvious.
- Every shipped claim (README, skill text, hook messages) must be true against the code.
- A check declares its expected values literally, never derived from the code under test.
- Every rule gets a control that must fail. Prove it by sabotage: break the code, watch it fail.
- A missing or unreadable config or helper is never a pass. A harness that could not run says
  CANNOT RUN, never FAILS or holds.
- Test Stop-hook behavior as sequences of consecutive stops, not single calls.
- Project-agnostic: no project, company or customer names, no measurements from one codebase,
  no absolute machine paths. Examples use neutral domains.
- No `Co-Authored-By` trailer on any commit in this repo.
