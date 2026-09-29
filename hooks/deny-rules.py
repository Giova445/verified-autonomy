#!/usr/bin/env python3
import importlib.util
import json
import fnmatch
import os
import posixpath
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
MAX_DEPTH = 8


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Deny(Exception):
    pass


MASK = load("inert-mask")
parse, flat_cmds, command_argv, base = MASK.parse, MASK.flat_cmds, MASK.command_argv, MASK.base
decode_escapes, ASSIGN, Word = MASK.decode_escapes, MASK.ASSIGN, MASK.Word


def stdin_of(cmd, piped):
    docs = [r.body or "" for r in cmd.redirs if r.op in ("<<", "<<-")]
    here = [r.word.text + "\n" for r in cmd.redirs if r.op == "<<<"]
    return docs[-1] if docs else here[-1] if here else piped


def out_text(name, args, stdin):
    if name == "echo":
        opts = ""
        while args and re.fullmatch(r"-[neE]+", args[0]):
            opts += args[0]
            args = args[1:]
        text = " ".join(args)
        return (decode_escapes(text) if "e" in opts else text) + ("" if "n" in opts else "\n")
    if name == "printf" and args:
        rest = iter(args[1:])
        return re.sub(r"%[sbd]", lambda m: next(rest, ""), decode_escapes(args[0]))
    if name == "cat" and all(a.startswith("-") for a in args):
        return stdin
    if name == "tee":
        return stdin
    return None


SHELLS = frozenset(("sh", "bash", "zsh", "dash", "ksh", "ash"))
CURRENT_BRANCH = re.compile(r"\$\(\s*git\s+(?:branch\s+--show-current|rev-parse\s+--abbrev-ref\s+HEAD)\s*\)")
VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def expand(text, env):
    text = CURRENT_BRANCH.sub("HEAD", text)
    return VARIABLE.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), text)


def substituted_output(script):
    s = script.strip()
    if not (s.startswith("$(") and s.endswith(")")):
        return None
    cmds = list(flat_cmds(parse(s[2:-1])))
    argv = command_argv(cmds[0].words) if len(cmds) == 1 else []
    return out_text(base(argv[0].text), [w.text for w in argv[1:]], stdin_of(cmds[0], None)) if argv else None


def shell_scripts(name, args, stdin):
    scripts = shell_sources(name, args, stdin)
    return scripts + [t for t in map(substituted_output, scripts) if t]


def shell_sources(name, args, stdin):
    if name == "eval":
        return [" ".join(args)] if args else []
    if name not in SHELLS:
        return []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
        elif a.startswith("-") and not a.startswith("--") and "c" in a:
            return [args[i + 1]] if i + 1 < len(args) else []
        elif a.startswith(("-", "+")):
            i += 1
        else:
            break
    if i < len(args):
        return []
    return [stdin] if stdin else []


DIRECT = frozenset(("pytest", "py.test", "jest", "vitest", "mocha", "tox", "ruff", "mypy", "tsc", "eslint", "playwright"))
SCRIPT = re.compile(r"(test|lint|check|verify|typecheck)")
LEAD_VALUE = frozenset(("--prefix", "-w", "--workspace", "-C", "--cwd", "--filter", "-F", "-p", "--package", "--with", "--python", "--directory"))
PY_LAUNCHERS = frozenset(("uv", "poetry", "pipenv", "pdm", "hatch", "rye"))


def lead(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a in LEAD_VALUE:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            return a, args[i + 1:]
    return None, []


def runner_of(path, args):
    name = base(path)
    if name in DIRECT:
        return name
    if path.endswith("bin/verify"):
        return "verify"
    if name in ("npx", "pnpx", "bunx"):
        t, rest = lead(args)
        return runner_of(t, rest) if t else None
    if name in ("npm", "pnpm", "yarn", "bun"):
        sub, rest = lead(args)
        if sub in ("test", "t", "tst"):
            return "npm-test"
        if sub in ("run", "run-script"):
            t, _ = lead(rest)
            return "npm-test" if t and SCRIPT.match(t) else None
        if sub in ("exec", "x", "dlx"):
            t, more = lead(rest)
            return runner_of(t, more) if t else None
        if sub and name in ("yarn", "pnpm"):
            return runner_of(sub, rest) or ("npm-test" if SCRIPT.match(sub) else None)
        return None
    if re.fullmatch(r"python[0-9.]*|py", name) and "-m" in args:
        mod = args[args.index("-m") + 1:][:1]
        return runner_of(mod[0], []) or ("unittest" if mod == ["unittest"] else None) if mod else None
    if name in PY_LAUNCHERS:
        sub, rest = lead(args)
        t, more = lead(rest) if sub == "run" else (None, [])
        return runner_of(t, more) if t else None
    if name == "make":
        skip, targets = False, []
        for a in args:
            if skip:
                skip = False
            elif a in ("-C", "-f", "-j", "-I", "-o", "-W"):
                skip = True
            elif not a.startswith("-") and "=" not in a:
                targets.append(a)
        return "make" if any(re.fullmatch(r"tests?|lint|verify|check.*", t) for t in targets) else None
    sub, _ = lead([a for a in args if not a.startswith("+")])
    if (name == "go" and sub == "test") or (name == "cargo" and sub in ("test", "clippy")):
        return name + " " + sub
    return None


def word_runner(cmd):
    if cmd.group is not None:
        return any(word_runner(c) for c in flat_cmds(cmd.group))
    argv = command_argv(cmd.words)
    if not argv:
        return False
    name, args = base(argv[0].text), [w.text for w in argv[1:]]
    if runner_of(argv[0].text, args):
        return True
    return any(any(word_runner(c) for c in flat_cmds(parse(sc))) for sc in shell_scripts(name, args, None))


def noop_success(pipeline):
    if len(pipeline) != 1:
        return False
    cmd = pipeline[0]
    if cmd.group is not None:
        return len(cmd.group) == 1 and len(cmd.group[0]) == 1 and noop_success(cmd.group[0][0][1])
    argv = command_argv(cmd.words)
    if not argv:
        return False
    name, args = base(argv[0].text), [w.text for w in argv[1:]]
    return (name in ("true", ":") and not args) or (name in ("exit", "return") and args == ["0"])


SUPPRESSED = "exit-code suppression on a test or lint command; fix the failure instead"


def check_suppression(stmts):
    for chain in stmts:
        seen = False
        for op, pipeline in chain:
            if op == "||" and seen and noop_success(pipeline):
                raise Deny(SUPPRESSED)
            seen = seen or any(word_runner(c) for c in pipeline)
    if len(stmts) > 1 and len(stmts[-1]) == 1 and noop_success(stmts[-1][0][1]):
        if any(word_runner(c) for chain in stmts[:-1] for _, pl in chain for c in pl):
            raise Deny(SUPPRESSED)


def git_split(args):
    cdirs, git_dir, i = [], None, 0
    while i < len(args):
        a = args[i]
        if a == "-C":
            cdirs.append(args[i + 1] if i + 1 < len(args) else "")
            i += 2
        elif a in ("-c", "--work-tree", "--namespace", "--super-prefix", "--config-env", "--attr-source"):
            i += 2
        elif a == "--git-dir":
            git_dir = args[i + 1] if i + 1 < len(args) else None
            i += 2
        elif a.startswith("--git-dir="):
            git_dir = a[len("--git-dir="):]
            i += 1
        elif a.startswith("-"):
            i += 1
        else:
            return a, args[i + 1:], cdirs, git_dir
    return None, [], cdirs, git_dir


def resolve(cwd, path):
    p = os.path.expanduser(path)
    if os.path.isabs(p):
        return os.path.normpath(p)
    return os.path.normpath(os.path.join(cwd, p)) if cwd else None


def flags_of(args):
    short, long_ = "", set()
    for a in args:
        if a == "--":
            break
        if a.startswith("--"):
            long_.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1:
            short += a[1:]
    return short, long_


SQL_CLIS = frozenset(("psql", "pgcli", "mysql", "mariadb", "mycli", "sqlite3", "sqlcmd", "duckdb", "usql"))
SQL_NOISE = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.S)
TAUTOLOGY = re.compile(r"\s*\(*\s*(?:1\s*=\s*1|true|1|''\s*=\s*'')\s*\)*\s*", re.I)


def destructive_sql(text):
    cleaned = SQL_NOISE.sub(lambda m: "''" if m.group().startswith("'") else " ", text)
    for stmt in cleaned.split(";"):
        m = re.search(r"\bdrop\s+(table|database|schema)\b", stmt, re.I)
        if m:
            return "DROP " + m.group(1).upper()
        if re.search(r"\btruncate\s+(?!\()", stmt, re.I):
            return "TRUNCATE"
        if re.search(r"\bdelete\s+from\b", stmt, re.I):
            w = re.search(r"\bwhere\b(.*)$", stmt, re.I | re.S)
            if not w or TAUTOLOGY.fullmatch(w.group(1)):
                return "DELETE without a WHERE clause"
    return None


HOME = re.escape(os.environ.get("HOME", "").rstrip("/") or "/nonexistent")
HOME_RE = r"(?:~|\$HOME|\$\{HOME\}|/Users/[^/]+|/home/[^/]+|/root|" + HOME + ")"
SECRET_RES = [re.compile(p) for p in (
    r"(?:^|/)\.env(?:\.(?!(?:example|sample|template|dist)$)[^/]+)?$",
    "^" + HOME_RE + r"/\.aws/credentials$",
    "^" + HOME_RE + r"/\.ssh/id_[^/]*(?<!\.pub)$",
    "^" + HOME_RE + r"/\.(?:netrc|npmrc|pypirc)$",
    "^" + HOME_RE + r"/\.config/gh/hosts\.yml$",
)]
READERS = frozenset((
    "cat tac head tail less more most bat batcat nl od xxd hexdump hd strings base64 base32 cut sort uniq "
    "awk gawk mawk sed grep egrep fgrep zgrep rg ag ack jq yq diff cmp comm paste column fold rev cp install rsync scp"
).split())
PATTERN_FIRST = frozenset("grep egrep fgrep zgrep rg ag ack sed awk gawk mawk jq yq".split())
DEST_LAST = frozenset(("cp", "install", "rsync", "scp"))
DATA_CMDS = frozenset("echo printf grep egrep fgrep rg ag ack git gh curl jq yq man cat sed awk".split())
SNAP_LONG = ("--updateSnapshot", "--update-snapshots", "--update-snapshot", "--snapshot-update")


def secret_patterns(root):
    path = os.path.join(root or "", ".claude", "protected-files")
    try:
        with open(path, encoding="utf-8") as fh:
            globs = [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]
    except FileNotFoundError:
        return []
    except OSError:
        return SECRET_RES
    return [re.compile(fnmatch.translate(g)) for g in globs] or SECRET_RES


def is_secret(arg, pats):
    return any(p.search(arg) or p.match(posixpath.basename(arg)) for p in pats)


def secret_read(name, args, pats):
    if name not in READERS or not pats:
        return None
    pos = [a for a in args if not a.startswith("-")]
    if name in PATTERN_FIRST and not {"-e", "-f", "--regexp", "--file"} & set(args):
        pos = pos[1:]
    if name in DEST_LAST:
        pos = pos[:-1]
    return next((a for a in pos if is_secret(a, pats)), None)


def rm_target(w, at_root, force):
    t = w.text
    if t.startswith("/") and posixpath.normpath(t[:-1] if t.endswith("*") else t).strip("/") == "":
        return "the filesystem root"
    if w.tilde and re.fullmatch(r"~/*\*?", t):
        return "the home directory"
    if w.dyn and re.fullmatch(r"\$(?:HOME|\{HOME\})/*\*?", t):
        return "the home directory"
    if force and w.dyn and re.fullmatch(r"\$\w+|\$\{\w+\}", t):
        return "an unresolved shell variable"
    if re.fullmatch(r"\.{1,2}/*", t) or (w.glob and t == ".*"):
        return "the current or parent directory"
    if re.fullmatch(r"(?:\./)?\.git(?:/+\*?)?", t):
        return "the .git directory"
    if at_root and w.glob and re.fullmatch(r"(?:\./)?\*", t):
        return "everything at the repository root"
    return None


class Ctx:
    def __init__(self, root, cwd, shared=None, env=None, branch=None):
        self.root, self.cwd, self.branch = root, cwd, branch
        self.env = dict(env or {})
        self.shared = shared if shared is not None else {"written": {}}

    def fork(self):
        return Ctx(self.root, self.cwd, self.shared, self.env, self.branch)

    def sib(self, name):
        if name not in self.shared:
            self.shared[name] = load(name)
        return self.shared[name]

    def protected(self):
        if "protected" not in self.shared:
            self.shared["protected"] = self.sib("push-targets").load_protected(self.root)
        return self.shared["protected"]

    def trailer_keys(self):
        if "keys" not in self.shared:
            self.shared["keys"] = self.sib("commit-message").forbidden_keys(self.root)
        return self.shared["keys"]

    def at_root(self):
        if not self.cwd:
            return False
        return os.path.exists(os.path.join(self.cwd, ".git")) or os.path.realpath(self.cwd) == os.path.realpath(self.root)


def rule_git(args, stdin, ctx):
    sub, rest, cdirs, git_dir = git_split(args)
    repo = ctx.cwd
    for c in cdirs:
        repo = resolve(repo or ctx.root, c)
    if sub == "push":
        reason = ctx.sib("push-targets").push_denial(rest, ctx.protected(), repo or ctx.root, git_dir, None if cdirs else ctx.branch)
        if reason:
            raise Deny(reason)
    elif sub == "reset" and "--hard" in rest:
        raise Deny("git reset --hard discards uncommitted work")
    elif sub == "clean":
        short, long_ = flags_of(rest)
        if ("f" in short or "--force" in long_) and "n" not in short and "--dry-run" not in long_:
            raise Deny("git clean -f destroys untracked files")
    elif sub in ("checkout", "switch") and not cdirs:
        ctx.branch = switched_branch(sub, rest, repo or ctx.root) or ctx.branch
    elif sub in ("commit", "commit-tree"):
        keys = ctx.trailer_keys()
        if keys:
            reason = ctx.sib("commit-message").commit_denial(rest, stdin, repo or ctx.root, ctx.shared["written"], keys)
            if reason:
                raise Deny(reason)


def switched_branch(sub, args, cwd):
    for i, a in enumerate(args):
        if a in ("-b", "-B", "-c", "-C") and i + 1 < len(args):
            return args[i + 1]
    names = [a for a in args if not a.startswith("-")]
    if "--" in args or not names or (sub == "checkout" and os.path.exists(os.path.join(cwd, names[0]))):
        return None
    return names[0]


def rule_gh(args, ctx):
    if args[:2] == ["pr", "review"] and ("--approve" in args or "-a" in args):
        raise Deny("an agent may not approve a pull request")
    if args[:2] == ["repo", "delete"]:
        raise Deny("gh repo delete destroys a repository")
    if args[:2] == ["pr", "merge"] or args[:1] == ["api"]:
        protected = ctx.protected()
        reason = protected and ctx.sib("push-targets").merge_denial(args, protected, ctx.cwd or ctx.root)
        if reason:
            raise Deny(reason)


def rule_rm(argv, ctx):
    rec = force = opts_done = False
    targets = []
    for w in argv:
        t = w.text
        if opts_done or not t.startswith("-") or t == "-":
            targets.append(w)
        elif t == "--":
            opts_done = True
        elif t.startswith("--"):
            rec, force = rec or t == "--recursive", force or t == "--force"
        else:
            rec, force = rec or "r" in t or "R" in t, force or "f" in t
    if rec:
        for w in targets:
            why = rm_target(w, ctx.at_root(), force)
            if why:
                raise Deny("recursive delete of " + why)


def rule_sql(args, stdin):
    texts = [re.sub(r"^--(?:command|execute)=", "", a) for a in args] + [stdin or ""]
    for t in texts:
        why = destructive_sql(t)
        if why:
            raise Deny("destructive SQL (%s) through a database client" % why)


def rule_runner(name, path, args):
    fam = runner_of(path, args)
    if fam in ("jest", "vitest", "playwright", "npm-test") and ("-u" in args or (fam == "vitest" and "--update" in args)):
        raise Deny("an agent may not re-record snapshots; propose the diff for approval")
    if name not in DATA_CMDS:
        if any(a.startswith(SNAP_LONG) for a in args):
            raise Deny("an agent may not re-record snapshots; propose the diff for approval")
        if "--exit-zero" in args:
            raise Deny(SUPPRESSED)


def new_cwd(ctx, args):
    target = next((a for a in args if not a.startswith("-")), None)
    if target is None:
        return os.path.expanduser("~")
    if target == "-" or "$" in target or "`" in target:
        return None
    return resolve(ctx.cwd, target)


def record_writes(cmd, argv, stdin, ctx):
    if not argv or not ctx.cwd:
        return
    name = base(argv[0].text)
    text = out_text(name, [w.text for w in argv[1:]], stdin) if name in ("echo", "printf", "cat") else None
    if text is None:
        return
    for r in cmd.redirs:
        if r.op in (">", ">>") and not r.word.dyn:
            path = resolve(ctx.cwd, r.word.text)
            ctx.shared["written"][path] = ctx.shared["written"].get(path, "") + text


def assign(words, ctx):
    for w in words:
        m = ASSIGN.match(w.text)
        if m:
            name, value = w.text[:m.end()].rstrip("+="), expand(w.text[m.end():], ctx.env)
            if m.group().endswith("+=") or "$" in value or "`" in value:
                ctx.env.pop(name, None)
            else:
                ctx.env[name] = value


def expanded(argv, env):
    out = []
    for w in argv:
        text = expand(w.text, env) if w.dyn else w.text
        out.append(w if text == w.text else Word(text, w.quoted, "$" in text or "`" in text, w.glob, w.tilde))
    return out


def judge(cmd, stdin, ctx, depth):
    pats = secret_patterns(ctx.root)
    for r in cmd.redirs:
        if r.op == "<" and pats and is_secret(r.word.text, pats):
            raise Deny("reading a secret file: " + r.word.text)
    argv = command_argv(cmd.words)
    record_writes(cmd, argv, stdin, ctx)
    if not argv:
        assign(cmd.words, ctx)
        return
    argv = expanded(argv, ctx.env)
    path, name = argv[0].text, base(argv[0].text)
    args = [w.text for w in argv[1:]]
    if name in ("export", "declare", "local", "readonly", "typeset"):
        assign(argv[1:], ctx)
    if name == "sudo":
        raise Deny("sudo needs the operator's approval")
    if name in ("cd", "pushd"):
        ctx.cwd = new_cwd(ctx, args)
        return
    for script in shell_scripts(name, args, stdin):
        check(script, ctx.fork(), depth + 1)
    secret = secret_read(name, args, pats)
    if secret:
        raise Deny("reading a secret file: " + secret)
    if name == "git":
        rule_git(args, stdin, ctx)
    elif name == "gh":
        rule_gh(args, ctx)
    elif name == "rm":
        rule_rm(argv[1:], ctx)
    elif name == "chmod" and any(re.fullmatch(r"0?777", a) for a in args):
        raise Deny("chmod 777 makes files world-writable")
    elif name in SQL_CLIS:
        rule_sql(args, stdin)
    elif name == "terraform" and lead(args)[0] == "destroy":
        raise Deny("terraform destroy tears down infrastructure")
    rule_runner(name, path, args)


def run_cmd(cmd, piped, ctx, depth):
    for sub in cmd.subs:
        walk(sub, ctx.fork(), depth)
    if cmd.group is not None:
        walk(cmd.group, ctx.fork() if cmd.paren else ctx, depth)
    stdin = stdin_of(cmd, piped)
    judge(cmd, stdin, ctx, depth)
    argv = command_argv(cmd.words)
    return out_text(base(argv[0].text), [w.text for w in argv[1:]], stdin) if argv else None


def walk(stmts, ctx, depth):
    check_suppression(stmts)
    for chain in stmts:
        for _, pipeline in chain:
            piped = None
            for cmd in pipeline:
                piped = run_cmd(cmd, piped, ctx, depth)


def check(text, ctx, depth=0):
    if depth > MAX_DEPTH:
        raise Deny("command nests shells too deeply to inspect")
    walk(parse(text), ctx, depth)


def repo_root(cwd):
    p = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return os.path.abspath(cwd)
        p = parent


def hook(raw):
    try:
        data = json.loads(raw)
    except ValueError:
        raise RuntimeError("hook input is not valid JSON")
    if not isinstance(data, dict):
        raise RuntimeError("hook input is not a JSON object")
    if data.get("tool_name") != "Bash":
        return
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if command is None or command == "":
        return
    if not isinstance(command, str):
        raise RuntimeError("the Bash command is not a string")
    cwd = data.get("cwd")
    cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
    root = os.environ.get("CLAUDE_PROJECT_DIR") or repo_root(cwd or os.getcwd())
    check(command, Ctx(root, cwd or root))


def main():
    try:
        hook(sys.stdin.buffer.read())
    except Deny as e:
        sys.stderr.write("BLOCKED by deny-dangerous.sh: %s\n" % e)
        return 2
    except Exception as e:
        sys.stderr.write("deny hook error: %s: %s. The command was not run.\n" % (type(e).__name__, e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
