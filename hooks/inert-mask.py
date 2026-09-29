#!/usr/bin/env python3
import posixpath
import re
import sys

MAX_WORDS = 4096
KEYWORDS = frozenset(("if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!", "esac"))
REDIRS = ("<<<", "<<-", "<<", "<>", "<&", "<", ">>", ">&", ">|", ">", "&>>", "&>")
DQ_RUN = re.compile(r'[^"\\$`]+')
NAME = re.compile(r"[A-Za-z0-9_]+")
RBRACE = re.compile(r"\}(?=[\s;&|)]|$)")
ANSI = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v"}
ESCAPE = re.compile(r"\\(x[0-9a-fA-F]{1,2}|[0-7]{1,3}|.)", re.S)


class Word:
    __slots__ = ("text", "quoted", "dyn", "glob", "tilde")

    def __init__(self, text, quoted=False, dyn=False, glob=False, tilde=False):
        self.text, self.quoted, self.dyn, self.glob, self.tilde = text, quoted, dyn, glob, tilde


class Redir:
    __slots__ = ("op", "word", "body")

    def __init__(self, op, word):
        self.op, self.word, self.body = op, word, None


class Cmd:
    __slots__ = ("words", "redirs", "group", "paren", "subs")

    def __init__(self, words, redirs, group, paren, subs):
        self.words, self.redirs, self.group, self.paren, self.subs = words, redirs, group, paren, subs


def decode_escapes(text):
    def one(m):
        g = m.group(1)
        if g[0] == "x" and len(g) > 1:
            return chr(int(g[1:], 16))
        if g[0] in "01234567":
            return chr(int(g, 8) & 0xFF)
        return ANSI.get(g, "\\" + g if g not in "\\'\"" else g)
    return ESCAPE.sub(one, text)


def brace_expand(text, budget=None):
    budget = [MAX_WORDS] if budget is None else budget
    i = text.find("{")
    while i >= 0:
        depth, commas, j = 0, [], i
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            elif c == "," and depth == 1:
                commas.append(j)
            j += 1
        else:
            break
        if commas:
            cuts = [i] + commas + [j]
            out = []
            for a, b in zip(cuts, cuts[1:]):
                out += brace_expand(text[:i] + text[a + 1:b] + text[j + 1:], budget)
            return out
        i = text.find("{", i + 1)
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("brace expansion is too large to inspect")
    return [text]


class Parser:
    def __init__(self, s):
        self.s, self.i, self.n = s, 0, len(s)
        self.pending, self.subs = [], []

    def flush_heredocs(self):
        s = self.s
        for r in self.pending:
            strip, delim, lines = r.op == "<<-", r.word.text, []
            while self.i < self.n:
                j = s.find("\n", self.i)
                end = self.n if j < 0 else j
                line = s[self.i:end]
                self.i = min(end + 1, self.n)
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            r.body = "\n".join(lines) + ("\n" if lines else "")
        self.pending = []

    def skip_blank(self, newlines=False):
        s = self.s
        while self.i < self.n:
            c = s[self.i]
            if c in " \t":
                self.i += 1
            elif c == "\\" and s.startswith("\n", self.i + 1):
                self.i += 2
            elif c == "#":
                j = s.find("\n", self.i)
                self.i = self.n if j < 0 else j
            elif newlines and c == "\n":
                self.i += 1
                self.flush_heredocs()
            else:
                break

    def read_dollar(self, buf):
        s, i = self.s, self.i
        nxt = s[i + 1:i + 2]
        if nxt == "(":
            if s.startswith("((", i + 1):
                depth, j = 0, i + 1
                while j < self.n:
                    depth += (s[j] == "(") - (s[j] == ")")
                    if depth == 0:
                        break
                    j += 1
                if j < self.n and s[j - 1] == ")":
                    buf.append(s[i:j + 1])
                    self.i = j + 1
                    return True
            self.i = i + 2
            self.subs.append(self.parse_list(")"))
            buf.append(s[i:self.i])
            return True
        if nxt == "{":
            self.i = i + 2
            while self.i < self.n and s[self.i] != "}":
                c = s[self.i]
                if c == "\\":
                    self.i += 2
                elif c == "'":
                    j = s.find("'", self.i + 1)
                    self.i = self.n if j < 0 else j + 1
                elif c == '"':
                    self.i += 1
                    self.read_dquote()
                elif c == "$" or c == "`":
                    self.read_dollar([]) if c == "$" else self.read_backtick([])
                else:
                    self.i += 1
            self.i = min(self.i + 1, self.n)
            buf.append(s[i:self.i])
            return True
        if nxt.isalpha() or nxt == "_":
            self.i = NAME.match(s, i + 1).end()
        elif nxt.isdigit() or (nxt and nxt in "?$!@*#-"):
            self.i = i + 2
        else:
            buf.append("$")
            self.i = i + 1
            return False
        buf.append(s[i:self.i])
        return True

    def read_backtick(self, buf):
        s, i = self.s, self.i
        j = i + 1
        while j < self.n and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        inner = re.sub(r"\\([$`\\])", r"\1", s[i + 1:j])
        self.subs.append(Parser(inner).parse_list(None))
        buf.append(s[i:j + 1])
        self.i = min(j + 1, self.n)

    def read_dquote(self):
        s, buf, dyn = self.s, [], False
        while self.i < self.n:
            m = DQ_RUN.match(s, self.i)
            if m:
                buf.append(m.group())
                self.i = m.end()
                continue
            c = s[self.i]
            if c == '"':
                self.i += 1
                break
            if c == "\\":
                d = s[self.i + 1:self.i + 2]
                if d and d in '$`"\\':
                    buf.append(d)
                    self.i += 2
                elif d == "\n":
                    self.i += 2
                else:
                    buf.append("\\")
                    self.i += 1
            elif c == "$":
                dyn = self.read_dollar(buf) or dyn
            else:
                self.read_backtick(buf)
                dyn = True
        return "".join(buf), dyn

    def read_ansi(self):
        s, j, raw = self.s, self.i + 2, []
        while j < self.n and s[j] != "'":
            if s[j] == "\\" and j + 1 < self.n:
                raw.append(s[j:j + 2])
                j += 2
            else:
                raw.append(s[j])
                j += 1
        self.i = min(j + 1, self.n)
        return decode_escapes("".join(raw))

    def read_word(self):
        s, buf = self.s, []
        quoted = dyn = glob = False
        tilde = s.startswith("~", self.i)
        while self.i < self.n:
            c = s[self.i]
            if c in " \t\n;&|()":
                break
            if c in "<>":
                if buf or not s.startswith("(", self.i + 1):
                    break
                self.i += 1
                self.subs.append(self.parse_list(")"))
                dyn = True
                buf.append("<(...)")
                continue
            if c == "\\":
                d = s[self.i + 1:self.i + 2]
                if d != "\n":
                    buf.append(d)
                    quoted = True
                self.i += 2
            elif c == "'":
                j = s.find("'", self.i + 1)
                j = self.n if j < 0 else j
                buf.append(s[self.i + 1:j])
                quoted = True
                self.i = j + 1
            elif c == '"':
                self.i += 1
                text, d = self.read_dquote()
                buf.append(text)
                quoted, dyn = True, dyn or d
            elif c == "$" and s.startswith("'", self.i + 1):
                buf.append(self.read_ansi())
                quoted = True
            elif c == "$" and s.startswith('"', self.i + 1):
                self.i += 1
            elif c == "$":
                dyn = self.read_dollar(buf) or dyn
            elif c == "`":
                self.read_backtick(buf)
                dyn = True
            else:
                glob = glob or c in "*?["
                buf.append(c)
                self.i += 1
        return Word("".join(buf), quoted, dyn, glob, tilde)

    def read_redirect(self):
        s = self.s
        op = next(o for o in REDIRS if s.startswith(o, self.i))
        self.i += len(op)
        self.skip_blank()
        r = Redir(op, self.read_word())
        if op in ("<<", "<<-"):
            self.pending.append(r)
        return r

    def parse_command(self):
        outer, self.subs = self.subs, []
        words, redirs, group, paren = [], [], None, False
        s = self.s
        while True:
            self.skip_blank()
            if self.i >= self.n:
                break
            c, before = s[self.i], self.i
            if c in "\n;|)":
                break
            if c == "&" and not s.startswith("&>", self.i):
                break
            if c in "<>&" and not s.startswith("(", self.i + 1):
                redirs.append(self.read_redirect())
            elif c == "(":
                if words:
                    j = s.find(")", self.i)
                    fn_def = s[self.i + 1:j].strip() == "" if j >= 0 else False
                    self.i = self.n if j < 0 else j + 1
                    if fn_def:
                        words = []
                        break
                elif s.startswith("((", self.i):
                    j = s.find("))", self.i)
                    self.i = self.n if j < 0 else j + 2
                else:
                    self.i += 1
                    group, paren = self.parse_list(")"), True
            else:
                w = self.read_word()
                if w.text.isdigit() and not w.quoted and s[self.i:self.i + 1] in ("<", ">") and self.i < self.n:
                    continue
                if not words and not w.quoted and w.text in KEYWORDS:
                    continue
                if not words and group is None and not w.quoted and w.text == "{":
                    group = self.parse_list("}")
                elif w.quoted or w.dyn or "{" not in w.text:
                    words.append(w)
                else:
                    words += [Word(t, w.quoted, w.dyn, w.glob, w.tilde) for t in brace_expand(w.text)]
            if self.i == before:
                self.i += 1
        cmd = Cmd(words, redirs, group, paren, self.subs) if (words or redirs or group is not None or self.subs) else None
        self.subs = outer
        return cmd

    def parse_pipeline(self):
        cmds = []
        while True:
            cmd = self.parse_command()
            if cmd:
                cmds.append(cmd)
            self.skip_blank()
            if self.s.startswith("|", self.i) and not self.s.startswith("||", self.i):
                self.i += 2 if self.s.startswith("|&", self.i) else 1
                self.skip_blank(True)
                continue
            return cmds

    def parse_andor(self):
        chain, op = [], None
        while True:
            pipeline = self.parse_pipeline()
            if pipeline:
                chain.append((op, pipeline))
            self.skip_blank()
            two = self.s[self.i:self.i + 2]
            if two in ("&&", "||"):
                op = two
                self.i += 2
                self.skip_blank(True)
            else:
                return chain

    def parse_list(self, closer):
        stmts, s = [], self.s
        while True:
            self.skip_blank()
            if self.i >= self.n:
                return stmts
            c = s[self.i]
            if c == "\n":
                self.i += 1
                self.flush_heredocs()
            elif c == ";" or (c == "&" and not s.startswith("&>", self.i)):
                self.i += 1
            elif c == ")":
                self.i += 1
                if closer == ")":
                    return stmts
            elif closer == "}" and RBRACE.match(s, self.i):
                self.i += 1
                return stmts
            else:
                before = self.i
                chain = self.parse_andor()
                if chain:
                    stmts.append(chain)
                if self.i == before:
                    self.i += 1


def parse(text):
    p = Parser(text)
    return p.parse_list(None)


def base(text):
    return posixpath.basename(text)


def flat_cmds(stmts):
    for chain in stmts:
        for _, pipeline in chain:
            for cmd in pipeline:
                yield cmd
                for sub in cmd.subs:
                    yield from flat_cmds(sub)
                if cmd.group is not None:
                    yield from flat_cmds(cmd.group)


ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
WRAPPERS = frozenset(("env", "command", "builtin", "exec", "nohup", "time", "nice", "timeout", "setsid", "stdbuf", "xargs"))
OPT_VALUE = {
    "env": ("-u", "-C", "-S", "--unset", "--chdir"),
    "exec": ("-a",),
    "nice": ("-n",),
    "timeout": ("-s", "-k", "--signal", "--kill-after"),
    "stdbuf": ("-i", "-o", "-e"),
    "xargs": ("-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "-l"),
}


def skip_wrapper(name, words, i):
    takes = OPT_VALUE.get(name, ())
    if name == "command" and i < len(words) and words[i].text in ("-v", "-V"):
        return None
    while i < len(words):
        t = words[i].text
        if t == "--":
            return i + 1
        if t in takes:
            i += 2
        elif t.startswith("-") and len(t) > 1:
            i += 1
        elif name == "env" and ASSIGN.match(t):
            i += 1
        else:
            break
    if name == "timeout":
        i += 1
    return i


def command_argv(words):
    i = 0
    while True:
        while i < len(words) and ASSIGN.match(words[i].text):
            i += 1
        if i >= len(words):
            return []
        name = base(words[i].text)
        if name not in WRAPPERS:
            return words[i:]
        i = skip_wrapper(name, words, i + 1)
        if i is None:
            return []


def argvs(text):
    return [[w.text for w in c.words] for c in flat_cmds(parse(text)) if c.words]


PARSE_CONTROLS = [
    ("splits on ; && || | and newline", "a 1; b 2 && c || d | e\nf", [["a", "1"], ["b", "2"], ["c"], ["d"], ["e"], ["f"]]),
    ("a comment hides the rest of the line", "a # b ; c\nd", [["a"], ["d"]]),
    ("a hash inside a word is not a comment", "echo a#b", [["echo", "a#b"]]),
    ("quoted operators stay in one word", "echo 'a; b | c' \"d && e\"", [["echo", "a; b | c", "d && e"]]),
    ("redirects are not arguments", "cmd a > f 2>&1 b", [["cmd", "a", "b"]]),
    ("a heredoc body is data", "cat <<'EOF' > f\nsudo x\nit's\nEOF\nnext", [["cat"], ["next"]]),
    ("a substitution is its own command", "echo \"$(git push origin main)\"", [["echo", "$(git push origin main)"], ["git", "push", "origin", "main"]]),
    ("a substitution keeps its heredoc", "git commit -m \"$(cat <<'EOF'\nsay 'x'\nEOF\n)\"", [["git", "commit", "-m", "$(cat <<'EOF'\nsay 'x'\nEOF\n)"], ["cat"]]),
    ("a single-quoted dollar is text", "echo '$(rm -rf /)'", [["echo", "$(rm -rf /)"]]),
    ("backticks run commands", "echo `whoami`", [["echo", "`whoami`"], ["whoami"]]),
    ("a subshell is flattened", "(cd x; make)", [["cd", "x"], ["make"]]),
    ("brace groups are flattened", "{ a; b; }", [["a"], ["b"]]),
    ("reserved words are dropped", "if x; then y; fi", [["x"], ["y"]]),
    ("brace expansion yields words", "git push origin {main,dev}", [["git", "push", "origin", "main", "dev"]]),
    ("ansi-c quoting decodes escapes", "echo $'a\\nb'", [["echo", "a\nb"]]),
    ("arithmetic is not a command", "echo $((1 + 2))", [["echo", "$((1 + 2))"]]),
    ("a function body is parsed", "f() { git push; }", [["git", "push"]]),
    ("line continuation joins", "git \\\n push", [["git", "push"]]),
    ("unterminated quote does not hang", "echo 'abc", [["echo", "abc"]]),
]


def self_test():
    ok = 0
    for name, text, want in PARSE_CONTROLS:
        got = argvs(text)
        ok += got == want
        print("  %s  %s" % ("ok  " if got == want else "FAIL", name))
        if got != want:
            print("        got %r" % (got,))
    print("\ninert-mask (%d checks)" % len(PARSE_CONTROLS))
    return 0 if ok == len(PARSE_CONTROLS) else 1


if __name__ == "__main__":
    sys.exit(self_test() if sys.argv[1:2] == ["--self-test"] else 2)
