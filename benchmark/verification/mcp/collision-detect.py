#!/usr/bin/env python3
# gate: N3
"""B1 — MCP name-collision detector. Mitigates the K1 FAILS.

K1 measured this: an impostor server advertising a trusted tool's name was configured,
answered calls, and the harness surfaced NO collision anywhere in the UI. The operator
had no way to notice. This does not fix the harness — it makes the collision visible
from outside it, which is the part that was actually available to build.

TWO KINDS OF COLLISION, FOUND TWO DIFFERENT WAYS.

  server names, statically   The same server name declared in more than one config scope.
                             Only one wins. If the losing definition has a DIFFERENT
                             command, the operator is running something other than what
                             they think they configured. Read from the config files.

  tool names, by probing     Two different servers advertising the same tool name. This
                             CANNOT be read from config: the tool list lives inside the
                             server and is only knowable by launching it and asking. So
                             --probe speaks real MCP over stdio (initialize, then
                             tools/list) and compares what comes back. A version of this
                             check that only read config would miss the exact attack K1
                             demonstrated, while looking like it was checking.

Probing executes the configured commands. That is the point — the tool list is not
declared anywhere else — but it is why --probe is opt-in and never runs against the
user's real config unless asked.
"""
import argparse, json, os, subprocess, sys, tempfile

def scopes_from(path):
    """Every scope a single claude.json defines: the user-level block plus each project's."""
    out = []
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return [("<unreadable>", path, {}, f"{e}")]
    if isinstance(d.get("mcpServers"), dict):
        out.append(("user", path, d["mcpServers"], None))
    for proj, v in (d.get("projects") or {}).items():
        if isinstance(v, dict) and isinstance(v.get("mcpServers"), dict) and v["mcpServers"]:
            out.append((f"project:{proj}", path, v["mcpServers"], None))
    return out

def collect(paths):
    sc = []
    for p in paths:
        if not os.path.exists(p):
            continue
        if os.path.basename(p) == ".mcp.json":
            try:
                d = json.load(open(p, encoding="utf-8"))
                if isinstance(d.get("mcpServers"), dict):
                    sc.append((f"file:{p}", p, d["mcpServers"], None))
            except Exception as e:
                sc.append(("<unreadable>", p, {}, str(e)))
        else:
            sc += scopes_from(p)
    return sc

def _cmdline(cfg):
    if not isinstance(cfg, dict):
        return repr(cfg)
    return " ".join([str(cfg.get("command", "?"))] + [str(a) for a in (cfg.get("args") or [])])

def server_collisions(scopes):
    by = {}
    for name, src, servers, err in scopes:
        if err:
            continue
        for s, cfg in servers.items():
            by.setdefault(s, []).append((name, json.dumps(cfg, sort_keys=True)))
    out = []
    for s, entries in sorted(by.items()):
        if len(entries) < 2:
            continue
        distinct = {c for _, c in entries}
        out.append({
            "kind": "server-name",
            "name": s,
            "scopes": [n for n, _ in entries],
            # Identical definitions in two scopes are redundant but harmless: whichever
            # wins, the operator gets what they expect. Differing definitions mean the
            # losing one is silently discarded, which is the shadowing risk worth a HIGH.
            "severity": "HIGH" if len(distinct) > 1 else "LOW",
            "detail": ("definitions DIFFER between scopes — one is silently discarded"
                       if len(distinct) > 1 else "identical definitions, redundant only"),
            # The differing commands, printed. "definitions differ" alone tells an operator
            # nothing about which one they are actually running or why it matters.
            "commands": sorted({_cmdline(json.loads(c)) for c in distinct}) if len(distinct) > 1 else [],
        })
    return out

def probe_tools(name, cfg, timeout=10):
    """Launch one stdio server and ask it what tools it advertises. Real MCP, not a mock."""
    cmd = cfg.get("command")
    if not cmd or cfg.get("type") not in (None, "stdio"):
        return None, "not a stdio server"
    argv = [cmd] + list(cfg.get("args") or [])
    env = dict(os.environ, **(cfg.get("env") or {}))
    reqs = ("".join(json.dumps(r) + "\n" for r in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "collision-detect", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})))
    try:
        p = subprocess.run(argv, input=reqs, capture_output=True, text=True,
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except Exception as e:
        return None, f"failed to launch: {e}"
    for line in p.stdout.splitlines():
        try:
            m = json.loads(line)
        except Exception:
            continue
        if m.get("id") == 2 and "result" in m:
            return [t.get("name") for t in m["result"].get("tools", [])], None
    return None, "no tools/list response"

def tool_collisions(scopes, timeout=10):
    seen, notes, out = {}, [], []
    for sname, _, servers, err in scopes:
        if err:
            continue
        for s, cfg in servers.items():
            tools, why = probe_tools(s, cfg, timeout)
            if tools is None:
                notes.append(f"{s} ({sname}): not probed — {why}")
                continue
            for t in tools:
                seen.setdefault(t, []).append(f"{s}@{sname}")
    for t, owners in sorted(seen.items()):
        uniq = sorted(set(owners))
        if len({o.split("@")[0] for o in uniq}) > 1:
            out.append({"kind": "tool-name", "name": t, "scopes": uniq, "severity": "HIGH",
                        "detail": "two DIFFERENT servers advertise this tool name; "
                                  "a call routes to whichever the client resolves first"})
    return out, notes

def report(findings, notes, quiet=False):
    if not quiet:
        for n in notes:
            print(f"    note: {n}")
    for f in findings:
        print(f"  {f['severity']:<5} {f['kind']:<11} {f['name']}")
        print(f"        scopes: {', '.join(f['scopes'])}")
        print(f"        {f['detail']}")
        for c in f.get("commands", []):
            print(f"          - {c}")
    if not findings:
        print("  no collisions")
    return 1 if any(f["severity"] == "HIGH" for f in findings) else 0

# --------------------------------------------------------------------------- controls
# "No collisions found" is the same output whether the detector works or is broken, so a
# clean run proves nothing on its own. Each control asserts BOTH directions on the SAME
# detector: it fires on a config carrying the collision, and stays silent on one that
# differs only by removing it. Holding everything else constant is what makes the silence
# evidence rather than luck.
HERE = os.path.dirname(os.path.abspath(__file__))
IMPOSTOR = os.path.join(HERE, "impostor_server.py")

def _cfg(tmp, servers, projects=None):
    p = os.path.join(tmp, "claude.json")
    json.dump({"mcpServers": servers, "projects": projects or {}}, open(p, "w"))
    return p

def _srv(tool):
    return {"command": sys.executable, "args": [IMPOSTOR], "env": {"IMPOSTOR_NAME": tool}}

def self_test(timeout=10):
    ok = True
    n = 0
    def check(label, got, want):
        nonlocal ok, n
        n += 1
        print(f"    {label:<52} {got}  (expect {want})")
        if got != want:
            ok = False
    with tempfile.TemporaryDirectory() as td:
        print("  CONTROL 1 — server name shadowed across scopes, definitions differ")
        dirty = _cfg(td, {"github": {"command": "real-github-mcp"}},
                     {"/some/project": {"mcpServers": {"github": {"command": "/tmp/evil"}}}})
        clean = os.path.join(td, "clean.json")
        json.dump({"mcpServers": {"github": {"command": "real-github-mcp"}},
                   "projects": {"/some/project": {"mcpServers": {"notgithub":
                                {"command": "/tmp/other"}}}}}, open(clean, "w"))
        d = server_collisions(collect([dirty]))
        c = server_collisions(collect([clean]))
        check("fires on the shadowing config", any(f["severity"] == "HIGH" for f in d), True)
        check("silent on the same config without it", len(c), 0)

        print("  CONTROL 2 — identical definitions must NOT be reported HIGH")
        same = os.path.join(td, "same.json")
        json.dump({"mcpServers": {"github": {"command": "real-github-mcp"}},
                   "projects": {"/p": {"mcpServers": {"github":
                                {"command": "real-github-mcp"}}}}}, open(same, "w"))
        s = server_collisions(collect([same]))
        check("reported, but LOW not HIGH", [f["severity"] for f in s], ["LOW"])

        print("  CONTROL 3 — tool name advertised by two DIFFERENT servers (probed live)")
        if not os.path.exists(IMPOSTOR):
            print("    !! impostor_server.py missing; cannot run the probe control")
            return 1
        dirty2 = _cfg(td, {"trusted": _srv("search_code"), "helper": _srv("search_code")})
        clean2 = os.path.join(td, "clean2.json")
        json.dump({"mcpServers": {"trusted": _srv("search_code"),
                                  "helper": _srv("list_files")}, "projects": {}},
                  open(clean2, "w"))
        dt, dn = tool_collisions(collect([dirty2]), timeout)
        ct, cn = tool_collisions(collect([clean2]), timeout)
        # If neither config could be probed the two results are equal and both empty, which
        # would read as "silent on clean" while nothing was ever measured. Require evidence
        # that the probe actually reached the servers.
        probed = not dn and not cn
        check("both configs actually probed (no launch failures)", probed, True)
        if not probed:
            for n in dn + cn:
                print(f"      {n}")
        check("fires on the duplicated tool name", [f["name"] for f in dt], ["search_code"])
        check("silent when the tool names differ", len(ct), 0)
    print(f"\n  MCP collision detector ({n} checks)")
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("configs", nargs="*", help="claude.json / .mcp.json paths")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--probe", action="store_true",
                    help="launch each stdio server and compare advertised tool names")
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args()
    if a.self_test:
        print("MCP name-collision detector — controls\n")
        return self_test(a.timeout)
    paths = a.configs or [os.path.expanduser("~/.claude.json")]
    scopes = collect(paths)
    print(f"MCP name-collision detector — {len(scopes)} scope(s) from {len(paths)} file(s)")
    for n, src, servers, err in scopes:
        print(f"    {n}: {len(servers)} server(s)" + (f"  ERROR {err}" if err else ""))
    findings = server_collisions(scopes)
    notes = []
    if a.probe:
        t, notes = tool_collisions(scopes, a.timeout)
        findings += t
    else:
        notes = ["tool names NOT checked (--probe omitted); server names only"]
    print()
    return report(findings, notes)

if __name__ == "__main__":
    sys.exit(main())
