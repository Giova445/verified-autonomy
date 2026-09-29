# Kit

What `install.sh` puts into a project. Hooks, skills and the verifier agent come from the
plugin and are never copied.

```bash
bash "$VA/kit/install.sh" [--no-coauthor] [target-repo]
```

`$VA` is the plugin root. Run it from the target repo or pass the path (spaces are fine).

## What it does

1. Probes the project's own commands, before anything is copied. It runs each lint,
   typecheck and test command it finds at the root and up to two directories down
   (`apps/web`, `packages/ui`) and writes `.claude/gates.json` from the ones that exit 0.
   Lint and typecheck go in both tiers, tests in `full`; a gate for a sub-app carries a
   `surface` so it runs only when the diff touches that app. A probe that hangs is killed
   with its process group. Files a probe creates (`package-lock.json`, build info) are
   removed or restored and named in the output; ignored files and your own work are left alone.
2. Copies the runtime.
3. Appends `.gitignore` lines for state paths that are not already ignored.

## What it copies

| Path | Purpose |
|---|---|
| `bin/verify`, `.claude/bin/verify` | the gate runner: `verify done` |
| `bin/scope`, `.claude/bin/scope` | picks the surface-scoped gates a diff touches |
| `.claude/gates/acceptance.py`, `drive.mjs` | product contract runner and browser driver |
| `.claude/gates/trailer-check.py` | forbidden-trailer gate |
| `.claude/selftest.sh` | proves the runner in this project: `bash .claude/selftest.sh` |

An existing `bin/verify` that differs from the kit's is kept; the kit's copy lands beside it
as `bin/verify.new` with a warning. An existing `.claude/gates.json` is kept the same way.
It refuses to write a config whose only passing gates are policy gates.

## No co-author trailers

Off by default. `--no-coauthor` writes `.claude/forbidden-trailers` (one trailer key per
line) and sets `attribution.commit` to `""` in `.claude/settings.json`. The `co-author` gate
is armed only when `.claude/forbidden-trailers` exists.

## CI

Copy `ci/verify.yml` to `.github/workflows/`. It runs `./bin/verify done` and uploads
`.claude/evidence/`.

## Requirements

`bash`, `git`, `python3`. `node` and Playwright only for a product contract that drives pages.
