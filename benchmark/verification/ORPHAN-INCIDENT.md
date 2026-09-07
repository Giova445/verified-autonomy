# Incident — five orphaned probes at 99% CPU for 3 days 11 hours

Reported from another session on the same machine: five `bash` processes running `ledger`
(`init` / `done` / `fail` / `rule`) from a temp dir, **PPID 1**, ~99% CPU each, load average
9.09. Killed by that session. This is my code and my defect.

## Cause

`bin/ledger`'s own self-test contains a regression probe for a spin bug. It ran each probe as:

```bash
( CLAUDE_PROJECT_DIR="$tmp" bash "$self" $probe >/dev/null 2>&1 ) &
bg=$!
...
kill -9 "$bg"
```

`$!` is the **subshell**, not the `bash` inside it. `kill -9 "$bg"` killed the wrapper; the
spinning grandchild reparented to PID 1 and kept burning a core indefinitely.

**A test that detects a hang and then leaks it is worse than no test.** It converts a
reproducible, bounded failure into a silent permanent resource drain on someone else's
machine — and it does so precisely when it is working, because the leak only happens on the
path where the probe correctly found a hang.

## Timeline

| | |
|---|---|
| spin bug (`shift 2` re-reading a valueless flag) | present before 2026-08-27 |
| orphans started | ~2026-08-25/26 (3d11h before discovery) |
| spin fixed — `need_value`, commit `dcd8cd3` | 2026-08-27 |
| orphans found and killed by another session | 2026-08-29 |

The orphans predate the spin fix, so they came from the pre-fix binary. Verified on the
current build: all four valueless-flag forms refuse with exit 2 in under 0.1s.

**The spin was fixed. The reaper that leaked it was not, and would have leaked again.**

## Fix

- Drop the subshell so `$!` is the process that can actually hang.
- Kill descendants **before** the parent — killing the parent first is what orphans them.
- New regression check: induce a real hang, reap it, assert nothing survives
  (`hung probe leaves no orphan behind`). Ledger self-test now 43 checks.

Swept the other probe scripts for the same `( … ) &` + `kill $!` shape. One apparent hit in
`bin/mutate-changed` is `) &&`, not `) &` — no risk.

## What this falsifies

**I1b is downgraded VERIFIED → PARTIAL.** It concluded "backgrounded work is capped by
agent-session lifetime" from a control showing 9 heartbeats inside a session versus 59+
outside. That holds only for work started through the harness's **own** background mechanism.

A process double-forked away from it — `( cmd ) &` inside a script the agent runs — is **not**
bounded by anything. It reparents to PID 1 and survives indefinitely. Five processes × 99% CPU
× 3.5 days is the counterexample, and it was found in production rather than by the gate that
was supposed to cover exactly this.

The gate tested the path the harness controls and reported the property as general. The
dangerous path is the one that escapes the harness, and it was the one not measured.
