#!/usr/bin/env python3
"""Blank the parts of a shell command that provably cannot execute, and nothing else.

WHY THIS IS NOT "STRIP QUOTED REGIONS". deny-dangerous.sh carried a KNOWN AND UNFIXED note
rejecting that fix, correctly: the SQL rules exist to read quoted payloads
(psql -c 'DROP TABLE users'), and blanking quotes would wave through bash -c 'rm -rf /'.
Trading two measured false positives for a class of false negatives on destructive commands
is the wrong direction for a deny list.

The real distinction is not whether text is quoted. It is whether the quoted text reaches
something that EXECUTES it. So this is an ALLOWLIST of sinks known to print rather than run:

    echo, printf          their arguments are written to stdout, not evaluated
    python -c '<program>' ONLY when the program parses and consists solely of print() on
                          literal constants. Checked with ast, not a regex.

Every other command keeps its quoted payload intact, so psql, bash -c, sh -c, eval and
anything unrecognised are untouched. Unknown means live: the failure direction is to keep
matching, never to stop.

Three further ways this could have become a bypass, all closed and all covered by controls:
  - a span containing $( ) or backticks is NEVER blanked; printf "$(rm -rf /)" executes.
  - separators are found outside quotes only, so python -c "import os; os.system(...)"
    is one part rather than two, and its payload is read as the non-print program it is.
  - an unterminated quote yields no span at all, so a half-quoted command masks nothing.
"""
import ast, re, sys

PRINT_SINKS = {"echo", "printf"}
SUBST = re.compile(r"\$\(|`|\$\{")
SEP = re.compile(r"[;&|]")


def quoted_spans(s):
    """(open_index, close_index) per balanced quoted region. Unterminated quotes yield
    nothing: a command that does not close its quote gets no masking at all."""
    out, quote, start = [], None, 0
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                out.append((start, i))
                quote = None
        elif ch in "'\"":
            quote, start = ch, i
    return out


def _parts(cmd, spans):
    """Split on shell separators that are OUTSIDE quotes. Splitting naively would cut
    python -c "import os; os.system('rm -rf /')" in half at the semicolon and hide the
    dangerous half from the sink check."""
    inside = lambda i: any(a <= i <= b for a, b in spans)
    cuts = [m.start() for m in SEP.finditer(cmd) if not inside(m.start())]
    parts, start = [], 0
    for c in cuts:
        parts.append((start, c))
        start = c + 1
    parts.append((start, len(cmd)))
    return [(a, b) for a, b in parts if b > a]


def pure_print(src):
    """True only for a program that is entirely print() calls on literal constants.
    A parse failure is False — unparseable means unknown means live."""
    try:
        tree = ast.parse(src)
    except Exception:
        return False
    if not tree.body:
        return False
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            return False
        call = node.value
        if not isinstance(call, ast.Call):
            return False
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            return False
        if call.keywords or any(not isinstance(a, ast.Constant) for a in call.args):
            return False
    return True


def mask(cmd):
    spans = quoted_spans(cmd)
    chars = list(cmd)

    def blank(a, b):
        for k in range(a + 1, b):
            chars[k] = " "

    for pa, pb in _parts(cmd, spans):
        seg = cmd[pa:pb]
        words = seg.split()
        if not words:
            continue
        name = words[0].rsplit("/", 1)[-1]
        local = [(a, b) for a, b in spans if pa <= a and b < pb]
        if name in PRINT_SINKS:
            for a, b in local:
                if not SUBST.search(cmd[a:b + 1]):
                    blank(a, b)
        elif re.fullmatch(r"python3?(\.\d+)?", name) and "-c" in words:
            for a, b in local:
                body = cmd[a + 1:b]
                if not SUBST.search(body) and pure_print(body):
                    blank(a, b)
    return "".join(chars)


# --------------------------------------------------------------------------- controls
# Both directions on every case. Asserting only that the two false positives are gone
# would pass for the naive "blank every quoted span", which is the fix this file exists to
# avoid — measured at 8 false negatives on the labeled corpus, including psql -c
# 'DROP TABLE users' and bash -c 'rm -rf /'. So the live cases are asserted too.
CASES = [
    # (command, must the danger survive masking?)
    ('echo "do not use sudo here"', False),
    ("python3 -c \"print('never run rm -rf / at home')\"", False),
    ('printf \'remember: never git push --force\'', False),
    ('echo "DROP TABLE users would be a bad idea"', False),
    ('bash -c "rm -rf /"', True),
    ("sh -c 'git push --force origin main'", True),
    ('eval "sudo systemctl restart nginx"', True),
    ("psql -c 'DROP TABLE users'", True),
    ("python3 -c \"import os; os.system('rm -rf /')\"", True),
    ('printf "$(rm -rf /)"', True),
    ('echo "safe" && rm -rf /', True),
    ('echo "unterminated \'quote and rm -rf /', True),
]
DANGER = re.compile(r"rm -rf|sudo|--force|DROP TABLE|os\.system|systemctl")

def self_test():
    ok = True
    for cmd, must_survive in CASES:
        masked = mask(cmd)
        survived = bool(DANGER.search(masked))
        good = survived == must_survive
        ok = ok and good
        print(f"    {'ok  ' if good else 'FAIL'} danger {'survives' if must_survive else 'masked  '}"
              f"  {cmd}")
        if not good:
            print(f"         got: {masked!r}")
    print(f"\n  inert-mask ({len(CASES)} checks)")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("inert-mask — controls\n")
        sys.exit(self_test())
    sys.stdout.write(mask(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()))
