#!/usr/bin/env python3
"""Gate: does the CLI identity that would create a remote resource match this project's?

WHY THIS ONE EXISTS

It is the only class in docs/cross-account-learning-audit.md that has already cost
something real. A Vercel project created from this machine was filed under a **Cadre**
org while the work belonged to **Orchid**, and a Siigo access key went into it. The user's
words at the time: *"wait, im getting this on the cadre account!!!"* The rule they wrote
afterwards -- `no-render-vercel-cli` -- is prose in one project's memory directory, and it
is true of all 47 project directories on this host.

Verified on this machine, from files, on 2026-09-13:

    ~/.render/cli.yaml                 workspace_name: Cadre AI
    ~/.config/gh/hosts.yml             user: Giova445
    ~/Library/.../com.vercel.cli/auth.json   userId: eqGW...  (opaque, no org name)

IT READS FILES. IT DOES NOT INVOKE THE CLIs.

Two reasons, and the first is the binding one. The standing rule for this host is not to
*use* the render and vercel CLIs at all, so a gate that shells out to `vercel whoami` to
enforce that rule would violate it on every run. The second is that a file read is
offline, instant, and cannot itself create or mutate anything -- a preflight that can have
side effects is not a preflight.

The cost is honest: a config file can be stale relative to the live session. A token that
expired, or a `logout` that left the file behind, will read as an identity the service no
longer accepts. That makes this gate sound in the direction that matters (it will still
flag a Cadre file when Orchid was expected) and weak in the other (it cannot detect that a
recorded identity has gone invalid). `expires_at` is checked where the file records one,
which narrows but does not close that gap.

WHAT IT DECIDES

Whether the identity on disk matches the one this project declares in
`.claude/identity.json`. Not whether the credential is valid, not whether the operation is
wise. An undeclared project is `undeclared`, never `ok` -- silence is not permission.
"""
import argparse
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
POLICY = os.path.join(".claude", "identity.json")

# Declared independently of RESOLVERS so that deleting a resolver cannot delete its own
# requirement -- the expectation-derived-from-subject defect this repo has now hit five
# times. A tool named here with no resolver is a failure, not a silent skip.
EXPECTED_TOOLS = {"gh", "render", "vercel"}

VERDICTS = {"ok", "mismatch", "unresolved", "undeclared", "no-policy"}

# Sub-commands that create or mutate a remote resource. Read-only verbs are deliberately
# absent: gating `gh pr view` would make the gate noise, and a noisy gate gets removed.
CREATING = re.compile(
    r"\b(?:"
    r"vercel\s+(?:deploy|link|env\s+add|project\s+add|alias|domains\s+add|secrets\s+add)"
    r"|render\s+(?:services?\s+(?:create|deploy|update)|deploys?\s+create|env\s+set)"
    r"|gh\s+(?:repo\s+create|secret\s+set|release\s+create|workflow\s+run|api\s+-X\s*(?:POST|PUT|PATCH|DELETE))"
    r"|shopify\s+(?:app\s+deploy|theme\s+push)"
    r"|supabase\s+(?:link|db\s+push|projects?\s+create)"
    r")\b", re.I)

# Bare `vercel` and bare `render` deploy by default with no sub-command at all.
BARE_DEPLOY = re.compile(r"(?:^|[;&|]\s*)(vercel|render)\s*(?:$|[;&|])", re.I)


class IdentityError(Exception):
    pass


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def resolve_gh(home=HOME):
    """~/.config/gh/hosts.yml -> the active user. Parsed as text: the file is a tiny
    fixed-shape YAML and this gate must not take a PyYAML dependency to read three lines."""
    p = os.path.join(home, ".config", "gh", "hosts.yml")
    if not os.path.exists(p):
        raise IdentityError("gh: ~/.config/gh/hosts.yml not found — not logged in?")
    m = re.search(r"^\s{4}user:\s*(\S+)\s*$", _read(p), re.M)
    if not m:
        raise IdentityError("gh: hosts.yml has no active `user:` line")
    return {"user": m.group(1)}


def resolve_render(home=HOME):
    """~/.render/cli.yaml -> workspace_name, the human-readable org."""
    p = os.path.join(home, ".render", "cli.yaml")
    if not os.path.exists(p):
        raise IdentityError("render: ~/.render/cli.yaml not found — not logged in?")
    txt = _read(p)
    m = re.search(r"^workspace_name:\s*(.+?)\s*$", txt, re.M)
    if not m:
        raise IdentityError("render: cli.yaml has no `workspace_name:`")
    out = {"workspace_name": m.group(1)}
    e = re.search(r"^\s*expires_at:\s*(\d+)\s*$", txt, re.M)
    if e and int(e.group(1)) < time.time():
        out["expired"] = True
    return out


def resolve_vercel(home=HOME):
    """auth.json -> userId. Vercel records no org name here, so the declaration must pin
    the opaque id. Less readable than a name and still decidable, which is what matters."""
    p = os.path.join(home, "Library", "Application Support", "com.vercel.cli", "auth.json")
    if not os.path.exists(p):
        p = os.path.join(home, ".config", "vercel", "auth.json")
    if not os.path.exists(p):
        raise IdentityError("vercel: no auth.json found — not logged in?")
    try:
        doc = json.loads(_read(p))
    except ValueError as exc:
        raise IdentityError(f"vercel: auth.json unreadable ({exc})") from exc
    uid = doc.get("userId")
    if not uid:
        raise IdentityError("vercel: auth.json has no userId")
    out = {"userId": uid}
    exp = doc.get("expiresAt")
    if isinstance(exp, (int, float)) and exp / 1000 < time.time():
        out["expired"] = True
    return out


RESOLVERS = {"gh": resolve_gh, "render": resolve_render, "vercel": resolve_vercel}


def read_policy(root):
    """-> {tool: {field: expected}}. A missing file is `no-policy`, not `ok`."""
    p = os.path.join(root, POLICY)
    if not os.path.exists(p):
        return None
    try:
        doc = json.loads(_read(p))
    except ValueError as exc:
        raise IdentityError(f"{POLICY} unreadable ({exc})") from exc
    if not isinstance(doc, dict):
        raise IdentityError(f"{POLICY} is not an object")
    return doc


def judge_tool(tool, policy, home=HOME):
    """-> (verdict, detail) for one tool."""
    if policy is None:
        return "no-policy", f"{POLICY} absent — this project declares no expected identity"
    want = policy.get(tool)
    if not want:
        return "undeclared", f"{tool}: project declares no expected identity"
    fn = RESOLVERS.get(tool)
    if fn is None:
        return "unresolved", f"{tool}: no resolver — cannot read its identity"
    try:
        have = fn(home)
    except IdentityError as exc:
        return "unresolved", str(exc)
    for field, expected in want.items():
        actual = have.get(field)
        if actual != expected:
            return "mismatch", (f"{tool}.{field} is {actual!r}, project expects "
                                f"{expected!r}")
    if have.get("expired"):
        return "unresolved", f"{tool}: credential on disk is expired"
    return "ok", f"{tool}: {have}"


def tools_in(command):
    """Which gated tools a shell command would invoke to create something."""
    hits = set()
    for m in CREATING.finditer(command or ""):
        hits.add(m.group(0).split()[0].lower())
    for m in BARE_DEPLOY.finditer(command or ""):
        hits.add(m.group(1).lower())
    return hits & EXPECTED_TOOLS


def check_command(root, command, home=HOME):
    """-> (tools, findings). Empty tools means the command creates nothing gated."""
    tools = tools_in(command)
    if not tools:
        return set(), []
    policy = read_policy(root)
    out = []
    for t in sorted(tools):
        verdict, detail = judge_tool(t, policy, home)
        if verdict != "ok":
            out.append((t, verdict, detail))
    return tools, out


# --------------------------------------------------------------------------- controls
# Hermetic: every control builds a fake HOME with fake config files and a fake project,
# then resolves against it. Nothing reads the real machine, nothing invokes a CLI, nothing
# touches the network.
import tempfile

EXPECTED_CONTROLS = {
    "render-match", "render-mismatch", "render-expired-is-unresolved",
    "gh-match", "gh-mismatch",
    "vercel-match", "vercel-mismatch",
    "missing-config-is-unresolved", "no-policy-is-not-ok", "undeclared-is-not-ok",
    "creating-verb-detected", "readonly-verb-ignored", "bare-deploy-detected",
    "resolver-set-matches-expected",
}


def _home(tmp, render=None, gh=None, vercel=None, render_expires=None, vercel_expires=None):
    h = os.path.join(tmp, "home")
    if render is not None:
        os.makedirs(os.path.join(h, ".render"), exist_ok=True)
        exp = f"\n    expires_at: {render_expires}" if render_expires else ""
        with open(os.path.join(h, ".render", "cli.yaml"), "w", encoding="utf-8") as fh:
            fh.write(f"version: 1\nworkspace: tea-x\nworkspace_name: {render}\napi:{exp}\n")
    if gh is not None:
        os.makedirs(os.path.join(h, ".config", "gh"), exist_ok=True)
        with open(os.path.join(h, ".config", "gh", "hosts.yml"), "w", encoding="utf-8") as fh:
            fh.write(f"github.com:\n    git_protocol: https\n    users:\n        {gh}:\n    user: {gh}\n")
    if vercel is not None:
        d = os.path.join(h, "Library", "Application Support", "com.vercel.cli")
        os.makedirs(d, exist_ok=True)
        doc = {"userId": vercel}
        if vercel_expires:
            doc["expiresAt"] = vercel_expires
        with open(os.path.join(d, "auth.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    os.makedirs(h, exist_ok=True)
    return h


def _proj(tmp, policy):
    r = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(r, ".claude"), exist_ok=True)
    if policy is not None:
        with open(os.path.join(r, POLICY), "w", encoding="utf-8") as fh:
            json.dump(policy, fh)
    return r


def self_test():
    print("identity preflight — controls\n")
    ok, n, seen = True, 0, set()

    def check(name, got, want):
        nonlocal ok, n
        n += 1
        seen.add(name.split(" (")[0])
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {name:<40} {str(got)[:62]}")
        if not good:
            print(f"       expected {want!r}")

    with tempfile.TemporaryDirectory() as td:
        # The real-world case, both arms. Same project, same command, only the identity
        # on disk differs -- which is what makes the pass meaningful rather than lucky.
        proj = _proj(os.path.join(td, "a"), {"render": {"workspace_name": "Orchid"}})
        good = _home(os.path.join(td, "a"), render="Orchid")
        bad = _home(os.path.join(td, "b"), render="Cadre AI")
        check("render-match", judge_tool("render", read_policy(proj), good)[0], "ok")
        check("render-mismatch", judge_tool("render", read_policy(proj), bad)[0], "mismatch")

        # An expired credential is not a valid identity.
        old = _home(os.path.join(td, "c"), render="Orchid", render_expires=1)
        check("render-expired-is-unresolved",
              judge_tool("render", read_policy(proj), old)[0], "unresolved")

        p2 = _proj(os.path.join(td, "d"), {"gh": {"user": "Giova445"}})
        check("gh-match", judge_tool("gh", read_policy(p2),
                                     _home(os.path.join(td, "d"), gh="Giova445"))[0], "ok")
        check("gh-mismatch", judge_tool("gh", read_policy(p2),
                                        _home(os.path.join(td, "e"), gh="someone-else"))[0], "mismatch")

        p3 = _proj(os.path.join(td, "f"), {"vercel": {"userId": "abc123"}})
        check("vercel-match", judge_tool("vercel", read_policy(p3),
                                         _home(os.path.join(td, "f"), vercel="abc123"))[0], "ok")
        check("vercel-mismatch", judge_tool("vercel", read_policy(p3),
                                            _home(os.path.join(td, "g"), vercel="zzz"))[0], "mismatch")

        # FAIL CLOSED, three ways. None of these may read as ok.
        check("missing-config-is-unresolved",
              judge_tool("render", read_policy(proj), _home(os.path.join(td, "h")))[0],
              "unresolved")
        check("no-policy-is-not-ok",
              judge_tool("render", read_policy(_proj(os.path.join(td, "i"), None)), good)[0],
              "no-policy")
        check("undeclared-is-not-ok",
              judge_tool("vercel", read_policy(proj), good)[0], "undeclared")

        # Command classification: gate what creates, ignore what reads.
        check("creating-verb-detected", sorted(tools_in("vercel deploy --prod")), ["vercel"])
        check("readonly-verb-ignored", sorted(tools_in("gh pr view 42 && render services list")), [])
        check("bare-deploy-detected", sorted(tools_in("cd app && vercel")), ["vercel"])

    check("resolver-set-matches-expected", set(RESOLVERS), EXPECTED_TOOLS)

    missing = EXPECTED_CONTROLS - seen
    extra = seen - EXPECTED_CONTROLS
    if missing or extra:
        ok = False
        print(f"\n  !! CONTROL SET CHANGED: missing {sorted(missing) or 'none'}, "
              f"unexpected {sorted(extra) or 'none'}")
    else:
        print(f"\n  control set matches EXPECTED_CONTROLS ({len(EXPECTED_CONTROLS)} names)")
    print(f"\n  identity preflight ({n} checks)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="assert CLI identity matches the project")
    ap.add_argument("--root", default=".")
    ap.add_argument("--command", help="judge a shell command about to run")
    ap.add_argument("--report", action="store_true", help="show identities on this host")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    root = os.path.abspath(a.root)

    if a.report:
        print("identities readable on this host (from files; no CLI was invoked)")
        for t in sorted(EXPECTED_TOOLS):
            try:
                print(f"  {t:<8} {RESOLVERS[t]()}")
            except IdentityError as exc:
                print(f"  {t:<8} unresolved — {exc}")
        try:
            pol = read_policy(root)
        except IdentityError as exc:
            print(f"  policy: {exc}")
            return 2
        print(f"  policy   {pol if pol else f'{POLICY} absent'}")
        return 0

    if not a.command:
        ap.error("--command, --report or --self-test required")
    try:
        tools, findings = check_command(root, a.command)
    except IdentityError as exc:
        print(f"  POLICY UNREADABLE: {exc}", file=sys.stderr)
        return 2
    if not tools:
        return 0
    if not findings:
        print(f"  identity ok for {', '.join(sorted(tools))}")
        return 0
    for tool, verdict, detail in findings:
        print(f"  {verdict.upper()}: {detail}", file=sys.stderr)
    print(f"\n  refusing: this command would create a remote resource as the wrong "
          f"identity.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
