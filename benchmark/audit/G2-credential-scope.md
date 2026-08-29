# G2 — least-privilege credential scope

Audited 2026-08-29. **Enumeration only — no credential was used, exercised, or exfiltrated,
and no value appears in this document.** Per the gate's own definition, an overbroad scope is
the finding whether or not anything has abused it.

**Task the scope is measured against:** run verification gates in throwaway directories, and
push commits / manage one PR on `Giova445/verified-autonomy`. One repo, one PR, one
environment, plus read access to one public repo (`pallets/flask`) for H1.

## Inventory

| # | Credential | Scope actually held | Task needs | Verdict |
|---|---|---|---|---|
| 1 | `gh` CLI token (keyring) | `repo`, `workflow`, `gist`, `read:org` | push to **one** repo, edit **one** PR/environment | **OVERBROAD** |
| 2 | GitHub MCP `Authorization` header | a **second, independent** GitHub grant; scope not declared in config | nothing — gh CLI already covers it | **OVERBROAD (duplicate grant)** |
| 3 | Gmail MCP server | includes `send_message`, `create_draft`, `trash_message`, label write | nothing | **OVERBROAD** |
| 4 | Shopify MCP server | includes `create-product`, `update-product`, `set-inventory`, `create-discount`, `graphql_mutation` | nothing | **OVERBROAD** |
| 5 | Telegram MCP server | includes `send_message`, `send_file`, `create_group`, `delete_message` | nothing | **OVERBROAD** |
| 6 | monday.com MCP server | includes `create_item`, `update_items`, `create_board`, `all_api_write` | nothing | **OVERBROAD** |
| 7 | `CLAUDE_CODE_MESSAGING_TOKEN` (32 ch) | session messaging | harness infrastructure, not the task | in-band |
| 8 | Claude OAuth scopes | `user:inference user:file_upload user:profile user:sessions:claude_code` | `user:inference` | mildly overbroad (`file_upload`, `profile`) |
| 9 | `SSH_AUTH_SOCK` | socket present, **agent holds no identities** | none | not overbroad in practice |

## The findings that matter

**1. `repo` is the whole account, not one repository.** The task touches a single public repo.
The token grants read *and write* to every repository the account can reach — including
private ones such as the client repo used earlier for the false-positive corpus. Nothing
exploited it; the grant is the finding. A fine-grained token scoped to
`Giova445/verified-autonomy` with contents+PR write would cover every operation this work
performed.

**2. `gist` and `read:org` are used by nothing here.** Pure surplus.

**3. Two independent GitHub credentials are held at once** — the `gh` keyring token and a
separate `Authorization` header on the GitHub MCP server. Revoking one does not revoke access.

**4. The largest gap is not GitHub at all.** The agent process holds live, write-capable
connections to **Gmail, Shopify, Telegram and monday.com**. Sending mail, messaging contacts,
mutating a storefront and writing board items are all inside the held scope of a session whose
entire task is running verification gates in temp directories. This is the clearest
least-privilege violation in the inventory and it has nothing to do with the work being done.

## Control

The gate needs evidence the enumeration reflects *live* grants rather than stale config. Two
independent signals, neither requiring a credential to be used:

- `gh auth status` reports an **active** keyring token and prints its scopes.
- The K1 experiment, run in a **fresh temp project**, listed these MCP servers as connected
  and their tools as available — `benign — repo_scanner (perm not granted)` appeared alongside
  the pre-existing servers, so the listing came from live connections in that context.

**Deliberately not done:** calling a read-only tool on Gmail/Shopify/Telegram/monday to prove
liveness. It would have touched the user's real accounts, and G2 explicitly does not require
an exploit — enumeration is sufficient. Recording the choice rather than leaving a silent gap.

## Remediation, in order of exposure reduced per unit of effort

1. Replace the classic `gh` token with a fine-grained PAT limited to
   `Giova445/verified-autonomy`, contents + pull-requests + workflows. Drop `gist`, `read:org`.
2. Disable the Gmail / Shopify / Telegram / monday MCP servers for sessions doing this work,
   or scope them per-project rather than user-wide.
3. Remove one of the two GitHub credentials so revocation is single-point.
