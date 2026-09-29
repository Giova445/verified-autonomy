#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

CONFIG_REL = ".claude/gates.json"
CHECKS_REL = ".claude/checks"
COUNTED_CONFIG = (CONFIG_REL, ".claude/acceptance.json")
NOISE_SUFFIXES = (".pyc", ".db-wal", ".db-shm", ".rvf", ".rvf.lock")
NOISE_FILES = ("ruvector.db",)
FILE_CAP = 1 << 20
DEFAULT_GATE_TIMEOUT = 300.0
DEFAULT_MEMORY_MB = 600
RUN_LOG = "runs.jsonl"
RUN_SUBS = ("product", "fast", "full", "done")
USAGE = "usage: verify {preflight|fast|full|done|product|fingerprint}"
NOT_RUN = {"status": "not run", "msg": ""}

def say(text):
    sys.stderr.write(text.rstrip("\n") + "\n")

def remove(path):
    try:
        os.unlink(path)
    except OSError:
        pass

def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""

def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None

def write_atomic(path, text):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except OSError:
        remove(tmp)
        raise

def env_number(name, default, cast=float):
    try:
        value = cast(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

def git_run(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)

def git(root, *args):
    proc = git_run(root, *args)
    if proc.returncode != 0:
        raise RuntimeError("git %s failed" % " ".join(args))
    return proc.stdout

def is_tracked(root, rel):
    try:
        return bool(git(root, "ls-files", "--", rel).strip())
    except Exception:
        return False

def head_sha(root):
    try:
        return git(root, "rev-parse", "HEAD").decode().strip()
    except Exception:
        return "unknown"

def project_root():
    root = os.environ.get("VERIFY_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        return root
    cwd = os.getcwd()
    try:
        return git(cwd, "rev-parse", "--show-toplevel").decode().strip() or cwd
    except Exception:
        return cwd

def is_harness_path(rel):
    rel = rel.replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    parts = rel.split("/")
    if "__pycache__" in parts or parts[-1] == ".DS_Store" or rel.endswith(NOISE_SUFFIXES):
        return True
    if rel in COUNTED_CONFIG or rel.startswith(CHECKS_REL + "/"):
        return False
    if len(parts) > 1 and parts[0].startswith(".") and parts[0] != ".github":
        return True
    return rel in NOISE_FILES

def sha_of_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def file_token(path):
    try:
        st = os.lstat(path)
    except OSError:
        return "gone"
    if stat.S_ISLNK(st.st_mode):
        return "link"
    if not stat.S_ISREG(st.st_mode):
        return "special"
    mark = "x" if st.st_mode & 0o111 else "-"
    if st.st_size > FILE_CAP:
        return "%s%d:%d" % (mark, st.st_size, st.st_mtime_ns)
    try:
        return mark + sha_of_file(path)
    except OSError:
        return "unreadable"

def tokenize(root, rels):
    return {rel: file_token(os.path.join(root, rel)) for rel in rels}

def nul_list(raw):
    return [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]

def head_state(root):
    proc = git_run(root, "rev-parse", "--verify", "-q", "HEAD")
    if proc.returncode == 0:
        return proc.stdout.decode().strip()
    if proc.returncode == 1:
        git(root, "rev-parse", "--git-dir")
        return "unborn"
    raise RuntimeError("no git head")

def tracked_changes(root, head):
    base = ["diff", "--name-only", "--no-renames", "--relative", "-z"]
    if head == "unborn":
        return set(nul_list(git(root, *base, "--cached"))) | set(nul_list(git(root, *base)))
    return set(nul_list(git(root, *base, "HEAD")))

def config_files(root):
    found = list(COUNTED_CONFIG)
    for dirpath, dirs, names in os.walk(os.path.join(root, CHECKS_REL)):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if not is_harness_path(rel):
                found.append(rel)
    return found

def runner_tokens():
    here = os.path.dirname(os.path.abspath(__file__))
    up = os.path.dirname(here)
    paths = [os.path.join(here, "state.py"), os.path.join(here, "stop-gate.sh"),
             os.path.join(up, "bin", "verify"), os.path.join(up, "bin", "scope"),
             os.path.join(up, "benchmark", "gates", "acceptance.py"),
             os.path.join(up, "gates", "acceptance.py")]
    return {"runner:" + os.path.basename(p): file_token(p) for p in paths if os.path.isfile(p)}

def compute_fingerprint(root):
    head = head_state(root)
    changed = tracked_changes(root, head)
    others = set(nul_list(git(root, "ls-files", "--others", "--exclude-standard", "-z"))) - changed
    rels = [r for r in sorted(changed) if not is_harness_path(r)]
    rels += [r for r in sorted(others)
             if not is_harness_path(r) and not os.path.islink(os.path.join(root, r))]
    entries = {**tokenize(root, rels), **tokenize(root, config_files(root)), **runner_tokens()}
    digest = hashlib.sha256(head.encode())
    for key in sorted(entries):
        digest.update(("\0%s\0%s" % (key, entries[key])).encode("utf-8", "surrogateescape"))
    return digest.hexdigest()

def fingerprint(root):
    try:
        return compute_fingerprint(root)
    except Exception:
        return "uncacheable-" + os.urandom(8).hex()

class Ctx:
    def __init__(self):
        self.root = project_root()
        self.claude = os.path.join(self.root, ".claude")
        self.evidence = os.path.join(self.claude, "evidence")
        self.config = os.path.join(self.root, CONFIG_REL)
        self.home = os.environ.get("VERIFY_HOME") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
        self.gate_timeout = env_number("GATE_TIMEOUT", DEFAULT_GATE_TIMEOUT)

ACTIVE = []

def descendants(root):
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    kids = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, stack = [], [root]
    while stack:
        for kid in kids.get(stack.pop(), []):
            found.append(kid)
            stack.append(kid)
    return found

def footprint_mb(pids):
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["footprint", "-f", "bytes"] + [a for p in pids for a in ("-p", str(p))],
                                 capture_output=True, text=True, timeout=10).stdout
            return sum(int(v) for v in re.findall(r"\]: \d+-bit\s+Footprint: (\d+) B", out)) / 1048576
        except (OSError, subprocess.SubprocessError):
            return 0.0
    total = 0.0
    for p in pids:
        text = read_text("/proc/%d/smaps_rollup" % p) or ""
        found = re.search(r"^Pss:\s+(\d+) kB", text, re.M)
        total += int(found.group(1)) / 1024 if found else 0
    return total

class Meter:
    def __init__(self):
        import threading
        self.phase, self.peak, self.peak_phase = "startup", 0.0, "startup"
        self.budget = env_number("VERIFY_MEMORY_MB", DEFAULT_MEMORY_MB)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stopped.is_set():
            self.sample()
            self.stopped.wait(0.5)

    def sample(self):
        used = footprint_mb([os.getpid()] + descendants(os.getpid()))
        if used > self.peak:
            self.peak, self.peak_phase = used, self.phase

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stopped.set()
        self.thread.join(timeout=15)
        if self.peak <= 0:
            return
        if self.peak > self.budget:
            say("memory  : peak %d MB during %s, over the %d MB budget (VERIFY_MEMORY_MB)"
                % (self.peak, self.peak_phase, self.budget))
        else:
            say("memory  : peak %d MB (budget %d MB)" % (self.peak, self.budget))

METER = None

def at_phase(label):
    if METER:
        METER.phase = label

def kill_group(proc, sig=9):
    try:
        os.killpg(proc.pid, sig)
    except OSError:
        pass

def install_signal_handlers():
    import signal

    def stop(signum, _frame):
        for proc in ACTIVE:
            kill_group(proc)
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

def tail_lines(path, count=30):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            data = fh.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()[-count:]

def run_gate(root, cmd, limit):
    import tempfile
    fd, path = tempfile.mkstemp(prefix="va-gate-")
    started, timed_out = time.monotonic(), False
    try:
        with os.fdopen(fd, "wb") as out:
            proc = subprocess.Popen(["bash", "-o", "pipefail", "-c", cmd], cwd=root, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            ACTIVE.append(proc)
            try:
                code = proc.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
            kill_group(proc)
            proc.wait()
            ACTIVE.remove(proc)
        code = code if code is None or code >= 0 else 128 - code
        return {"code": code, "timed_out": timed_out, "sha": sha_of_file(path),
                "ms": int((time.monotonic() - started) * 1000), "tail": tail_lines(path)}
    finally:
        remove(path)

def valid_gate(gate):
    return isinstance(gate, dict) and isinstance(gate.get("name"), str) and isinstance(gate.get("cmd"), str)

def load_gates(ctx, tier):
    try:
        present = os.path.getsize(ctx.config) > 0
    except OSError:
        present = False
    if not present:
        if is_tracked(ctx.root, CONFIG_REL):
            return None, "gate config .claude/gates.json is tracked but missing or empty"
        return None, "no .claude/gates.json declares the %s gates" % tier
    data = load_json(ctx.config)
    if not isinstance(data, dict):
        return None, "gate config is unparseable"
    gates = data.get(tier, [])
    if not isinstance(gates, list) or not all(valid_gate(g) for g in gates):
        return None, "gate list is unreadable"
    if tier == "full" and not gates:
        return None, "tier 'full' declares no gates"
    return gates, None

def scope_skipped(ctx, gates):
    scope = os.path.join(ctx.home, "scope")
    if os.environ.get("VERIFY_SCOPE", "1") == "0" or not os.access(scope, os.X_OK):
        return set()
    if not any(isinstance(g.get("surface"), list) and g["surface"] for g in gates):
        return set()
    try:
        proc = subprocess.run([sys.executable, scope, "skip", ctx.root], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(proc.stdout.decode("utf-8", "replace").splitlines())

def failure_block(name, cmd, code, tail):
    head = "\u2500\u2500 GATE FAILED: %s\n   command : %s\n   exit    : %s" % (name, cmd, code)
    return head + "".join("\n   \u2502 " + line for line in tail)

def run_tier(ctx, tier):
    gates, error = load_gates(ctx, tier)
    out = {"gates": [], "blocks": [], "errors": [error] if error else [], "timed_out": [],
           "skipped": 0, "declared": len(gates or [])}
    skipped = scope_skipped(ctx, gates or []) if tier == "full" else set()
    for gate in gates or []:
        name, cmd = gate["name"], gate["cmd"]
        if cmd == "" or cmd == ":" or cmd.startswith(("echo ", " ")):
            say("  \u2717 %s: placeholder command (%s), not a gate" % (name, cmd))
            out["errors"].append("gate '%s' is a placeholder" % name)
            continue
        if name in skipped:
            say("  \u2298 %s: scoped out, nothing in the diff touches its declared surface" % name)
            out["gates"].append({"gate": name, "command": cmd, "skipped": True,
                                 "reason": "no changed file matches the declared surface of this gate",
                                 "executed_by": "harness"})
            out["skipped"] += 1
            continue
        limit = ctx.gate_timeout
        at_phase("gate '%s'" % name)
        result = run_gate(ctx.root, cmd, limit)
        entry = {"gate": name, "command": cmd, "exit_code": result["code"],
                 "stdout_sha256": result["sha"], "duration_ms": result["ms"], "executed_by": "harness"}
        if result["timed_out"]:
            say("  \u2717 %s (NO VERDICT: no answer after %ds)" % (name, limit))
            out["gates"].append({**entry, "timed_out": True, "timeout_s": int(limit)})
            out["timed_out"].append({"name": name, "limit": int(limit)})
            continue
        out["gates"].append(entry)
        if result["code"] == 0:
            say("  \u2713 %s (%dms)" % (name, result["ms"]))
        else:
            say("  \u2717 %s (exit %s)" % (name, result["code"]))
            out["blocks"].append(failure_block(name, cmd, result["code"], result["tail"]))
    return out

def tier_verdict(tier):
    if tier["errors"]:
        refusing = ("REFUSING TO CERTIFY: %s.\nFix .claude/gates.json: a gate set that cannot be read is not "
                    "a passing gate set." % "; ".join(tier["errors"]))
        return "config", "\n\n".join(tier["blocks"] + [refusing])
    if tier["blocks"]:
        return "red", "\n\n".join(tier["blocks"] + ["Fix the code, not the test."])
    if tier["timed_out"]:
        first = tier["timed_out"][0]
        return "noverdict", ("NO VERDICT: gate '%s' gave no answer after %ds, so it is unproven, not green."
                             % (first["name"], first["limit"]))
    return None, ""

def accept_py(ctx):
    here = ctx.home
    for path in (os.path.join(here, "..", "benchmark", "gates", "acceptance.py"),
                 os.path.join(here, "..", "gates", "acceptance.py"),
                 os.path.join(ctx.claude, "gates", "acceptance.py")):
        if os.path.isfile(path):
            return os.path.normpath(path)
    return None

def run_acceptance(ctx, script, results, tier=None):
    passed = [g["command"] for g in (tier or {}).get("gates", []) if not g.get("skipped") and g.get("exit_code") == 0]
    env = dict(os.environ, VERIFY_TREE=fingerprint(ctx.root), VERIFY_PASSED=json.dumps(passed))
    with open(os.path.join(ctx.evidence, "product.txt"), "wb") as log:
        proc = subprocess.Popen([sys.executable, script, ".", "--results", results], cwd=ctx.root,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        ACTIVE.append(proc)
        try:
            proc.wait()
        finally:
            ACTIVE.remove(proc)

def product_half(ctx, tier=None):
    if tier and (tier["errors"] or tier["blocks"] or tier["timed_out"]):
        return NOT_RUN
    script = accept_py(ctx)
    if script is None:
        return {"status": "open", "msg": "product : CANNOT RUN - acceptance.py is neither beside bin/verify "
                                         "nor in .claude/gates/"}
    results = os.path.join(ctx.evidence, "product.json")
    remove(results)
    at_phase("the product check")
    run_acceptance(ctx, script, results, tier)
    proc = subprocess.run([sys.executable, script, "--summarize", results], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    lines = proc.stdout.decode("utf-8", "replace").splitlines()
    return {"status": lines[0] if lines else "open", "msg": "\n".join(lines[1:]), "measured": True}

def decide(tier, prod):
    kind, text = tier_verdict(tier)
    if kind:
        return kind, text
    if prod["status"] != "held":
        return "product", prod["msg"] + "\nEngineering gates are green; the product is not established, so this is not done."
    return "green", prod["msg"]

def write_bundle(ctx, tier, prod, kind):
    gates = tier["gates"]
    error = "; ".join(tier["errors"])
    executed = [g for g in gates if not g.get("skipped")]
    green = bool(gates) and all(g.get("exit_code") == 0 for g in executed) and not error \
        and prod["status"] in ("held", "not run")
    bundle = {"commit_sha": head_sha(ctx.root), "product": prod["status"], "verdict": kind,
              "peak_memory_mb": int(METER.peak) if METER else None,
              "generated_at": utc_now().isoformat(),
              "gates": gates, "all_green": green,
              "trust": "self-reported by the process under test; not a receipt", "verified_by": "producer"}
    if error:
        bundle["error"] = error
    elif not gates:
        bundle["error"] = "no gates executed"
    write_atomic(os.path.join(ctx.evidence, "latest.json"), json.dumps(bundle, indent=2))

def save_bundle(ctx, tier, prod, kind):
    try:
        write_bundle(ctx, tier, prod, kind)
    except OSError:
        say("warning: evidence not written")

def ensure_evidence(ctx):
    try:
        os.makedirs(ctx.evidence, exist_ok=True)
        return True
    except OSError:
        say("warning: cannot write %s; no evidence is kept" % ctx.evidence)
        return False

def evaluate(ctx):
    writable = ensure_evidence(ctx)
    tier = run_tier(ctx, "full")
    prod = product_half(ctx, tier)
    kind, text = decide(tier, prod)
    if writable:
        save_bundle(ctx, tier, prod, kind)
    return kind, text, tier, prod

def green_report(ctx, tier, text):
    if tier["skipped"]:
        say("GATES GREEN for what ran: %d gate(s) scoped out and unexecuted, not green.\n"
            "   Those gates are unproven for this change. Run VERIFY_SCOPE=0 bin/verify done to execute every one."
            % tier["skipped"])
    else:
        say("ALL GATES GREEN - evidence: .claude/evidence/latest.json")
    import glob
    shots = " Screenshots: .claude/evidence/shots/" if glob.glob(os.path.join(ctx.evidence, "shots", "*.png")) else ""
    say("DONE - %s; engineering gates green.%s" % (text, shots))

def finished(code, verdict, gates=(), prod=NOT_RUN):
    return {"code": code, "verdict": verdict, "gates": list(gates), "product": prod}

def cmd_done(ctx):
    kind, text, tier, prod = evaluate(ctx)
    if kind != "green":
        say(text)
        return finished(1, kind, tier["gates"], prod)
    green_report(ctx, tier, text)
    return finished(0, kind, tier["gates"], prod)

def cmd_tier(ctx, name):
    say("%s gates:" % name)
    ensure_evidence(ctx)
    tier = run_tier(ctx, name)
    kind, text = tier_verdict(tier)
    if name == "full":
        save_bundle(ctx, tier, NOT_RUN, kind or "green")
    if kind:
        say(text)
        return finished(1, kind, tier["gates"])
    if not tier["declared"]:
        say("%s: no gates declared" % name)
        return finished(0, "empty", tier["gates"])
    if tier["skipped"]:
        say("%s: GREEN for what ran, %d gate(s) scoped out and UNEXECUTED" % (name, tier["skipped"]))
    else:
        say("%s: GREEN" % name)
    return finished(0, "green", tier["gates"])

def cmd_product(ctx):
    ensure_evidence(ctx)
    prod = product_half(ctx)
    say(prod["msg"])
    held = prod["status"] == "held"
    return finished(0 if held else 1, "green" if held else "product", (), prod)

def dispatch(ctx, sub):
    if sub == "product":
        return cmd_product(ctx)
    if sub == "done":
        return cmd_done(ctx)
    return cmd_tier(ctx, sub)

def gate_record(gate):
    skipped = bool(gate.get("skipped"))
    return {"name": gate.get("gate"), "exit_code": gate.get("exit_code"),
            "duration_ms": None if skipped else gate.get("duration_ms"), "skipped": skipped}

def product_record(ctx, prod):
    outcomes = []
    if prod.get("measured"):
        data = load_json(os.path.join(ctx.evidence, "product.json"))
        listed = data.get("outcomes") if isinstance(data, dict) else None
        outcomes = [{"name": o.get("name"), "verdict": o.get("verdict")}
                    for o in listed or [] if isinstance(o, dict)]
    return {"status": prod["status"], "outcomes": outcomes}

def run_record(ctx, sub, begun, result):
    return {"started_at": begun["started_at"], "subcommand": sub, "commit": begun["commit"],
            "tree": begun["tree"], "wall_ms": int((time.monotonic() - begun["clock"]) * 1000),
            "peak_memory_mb": int(METER.peak) if METER and METER.peak > 0 else None,
            "exit_code": result["code"], "verdict": result["verdict"],
            "gates": [gate_record(g) for g in result["gates"]],
            "product": product_record(ctx, result["product"])}

def append_run(ctx, sub, begun, result):
    try:
        line = json.dumps(run_record(ctx, sub, begun, result), separators=(",", ":")) + "\n"
        os.makedirs(ctx.evidence, exist_ok=True)
        with open(os.path.join(ctx.evidence, RUN_LOG), "ab") as fh:
            fh.write(line.encode("utf-8"))
    except Exception as exc:
        say("warning: run log not written (%s: %s)" % (type(exc).__name__, exc))

def begin_run(ctx):
    return {"started_at": utc_now().isoformat(timespec="milliseconds"), "clock": time.monotonic(),
            "commit": head_sha(ctx.root), "tree": fingerprint(ctx.root)}

def run_logged(ctx, sub):
    global METER
    begun = begin_run(ctx)
    if os.environ.get("VERIFY_MEMORY_MB") != "0":
        METER = Meter()
        with METER:
            result = dispatch(ctx, sub)
    else:
        result = dispatch(ctx, sub)
    append_run(ctx, sub, begun, result)
    return result["code"]

def cmd_verify(argv):
    args = argv[2:]
    sub = args[0] if args else "done"
    if len(args) > 1 or sub not in RUN_SUBS + ("fingerprint",):
        say(USAGE)
        return 1
    ctx = Ctx()
    install_signal_handlers()
    if sub == "fingerprint":
        print(fingerprint(ctx.root))
        return 0
    return run_logged(ctx, sub)

def main(argv):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    if len(argv) > 1 and argv[1] == "verify":
        return cmd_verify(argv)
    say("usage: state.py verify {fast|full|done|product|fingerprint}")
    return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv))
