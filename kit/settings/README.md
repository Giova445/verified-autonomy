# Config hardening — what is verified, and what I could not apply

Tested on **Claude Code 2.1.250, macOS (Darwin, Seatbelt)** on 2026-08-28. Every claim below
was checked by running it, not by reading documentation. All four key names exist in the
shipped 2.1.250 binary (`failIfUnavailable` ×12, `allowUnsandboxedCommands` ×8,
`allowManagedPermissionRulesOnly` ×8, `disableBypassPermissionsMode` ×7), so none of them is
invented — but existing in the binary is not the same as binding at the scope you write them.

## VERIFIED ENFORCED — sandbox, at project scope

`sandbox.filesystem.denyWrite` is enforced at the OS level. Probe: a `denyWrite` path, then a
`Bash` command told to `touch` a file inside it. **Ground truth is the filesystem, not the
model's account** — the file did not appear. That is Seatbelt refusing the syscall, and it
covers child processes, unlike a permission rule that only sees Claude's own tools.

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "filesystem": { "denyWrite": ["/path/you/protect/**"] }
  }
}
```

`failIfUnavailable: true` matters because the default is **fail-open**: with no sandbox
available Claude Code warns and runs the command unsandboxed. `allowUnsandboxedCommands:
false` closes the retry-with-`dangerouslyDisableSandbox` escape hatch.

Caveat measured during the probe: TMPDIR-adjacent paths interact with the built-in write
allowlist, so verify your own paths rather than assuming a pattern matched.

## VERIFIED **NOT** ENFORCED at project or user scope — the managed keys

`disableBypassPermissionsMode` in **project** settings does **not** stop the CLI starting in
bypass mode. Harness-level probe, control vs treatment:

```
control (no setting)         CLI started in bypass mode, exit=0
project disableBypass        CLI started in bypass mode, exit=0
project + permissions block  CLI started in bypass mode, exit=0
```

Identical. Writing these keys where you can reach them is **theatre** — the config looks
correct and enforces nothing, which is precisely the fabricated-green failure this repo
exists to stop.

A methodology note, because I got this wrong first: my initial probe read the *model's reply*
("BYPASSED" vs a refusal). That measures the model's disposition, not the harness. Re-run on
a harness-level signal — does the CLI refuse to start — the answer was unambiguous.

### They only bind in managed settings, which needs admin

macOS: `/Library/Application Support/ClaudeCode/managed-settings.json`
(absent on this machine; the directory does not exist and creating it requires admin).

```bash
sudo mkdir -p "/Library/Application Support/ClaudeCode"
sudo tee "/Library/Application Support/ClaudeCode/managed-settings.json" >/dev/null <<'JSON'
{
  "permissions": { "allowManagedPermissionRulesOnly": true },
  "disableBypassPermissionsMode": "disable",
  "sandbox": { "failIfUnavailable": true, "allowUnsandboxedCommands": false }
}
JSON
```

**This is the only scope where "no other level, including CLI arguments, can override" holds.**
It requires your password, so it is not something an agent can or should do for you. After
running it, re-run the probe in `benchmark/verification/` to confirm the CLI now refuses.
