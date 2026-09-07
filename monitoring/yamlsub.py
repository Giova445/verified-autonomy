#!/usr/bin/env python3
"""Strict parser for the small YAML subset bands.yaml is written in.

WHY NOT PyYAML. CI here is `actions/setup-python` with no `pip install` step
(.github/workflows/verify.yml), so PyYAML is not guaranteed to be importable. A loader
that works locally and silently does something else in CI is the exact class of bug this
repo exists to stop, so the parser is dependency-free and identical everywhere.

WHY STRICT. A lenient parser is worse than no parser for a control file: a construct it
does not understand gets skipped, the key it carried vanishes, and the band it configured
stops existing without anything turning red. So every construct outside the subset is a
hard error, not a shrug:

  tabs, `---`/`...` document markers, anchors/aliases (& *), merge keys (<<),
  flow collections ({} []), block scalars (| >), tags (!), duplicate keys,
  a mapping key with no value, a sequence at its parent's indent.

Supported: nested block mappings, block sequences (of scalars or of mappings), `#`
comments, and scalars typed as int / float / bool / null / single- or double-quoted
string / plain string.

`monitoring/selftest.py` holds a positive control for each rejection above, plus an
oracle comparison against PyYAML when PyYAML happens to be importable.
"""
import re

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
FLOAT_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")
BAD_PLAIN_START = "&*{}[]|>!%@`,?"


class YamlSubsetError(ValueError):
    """Raised for anything outside the supported subset. Never swallowed."""


def _err(lineno, msg):
    raise YamlSubsetError(f"line {lineno}: {msg}")


def _strip_comment(raw, lineno):
    """Remove a trailing `#` comment that is outside quotes."""
    out, quote, i = [], None, 0
    while i < len(raw):
        ch = raw[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(raw):
                out.append(raw[i + 1]); i += 2; continue
            if ch == quote:
                if quote == "'" and i + 1 < len(raw) and raw[i + 1] == "'":
                    out.append(raw[i + 1]); i += 2; continue
                quote = None
        elif ch in "\"'":
            quote = ch; out.append(ch)
        elif ch == "#" and (i == 0 or raw[i - 1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    if quote:
        _err(lineno, "unterminated quoted scalar")
    return "".join(out).rstrip()


class _Line:
    __slots__ = ("no", "indent", "body", "is_item")

    def __init__(self, no, indent, body, is_item):
        self.no, self.indent, self.body, self.is_item = no, indent, body, is_item


def _scan(text):
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            _err(no, "tab character; this subset requires spaces")
        stripped = raw.strip()
        if stripped.startswith("---") or stripped.startswith("..."):
            _err(no, "document markers are not supported")
        content = _strip_comment(raw, no)
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        body = content.strip()
        if body == "-" or body.startswith("- "):
            # A sequence item. Its payload sits two columns right of the dash, which is
            # how it is indexed below, so `- id: x` and an indented `id: x` agree.
            lines.append(_Line(no, indent, body[1:].strip(), True))
        else:
            lines.append(_Line(no, indent, body, False))
    return lines


def _split_kv(line):
    body = line.body
    m = re.match(r"^([^:]+):(?:\s(.*))?$", body)
    if not m:
        if body.endswith(":"):
            m = re.match(r"^([^:]+):$", body)
            if m:
                return m.group(1).strip(), ""
        _err(line.no, f"not a `key: value` mapping entry: {body!r}")
    key = m.group(1).strip()
    if not KEY_RE.match(key):
        _err(line.no, f"unsupported key {key!r}")
    return key, (m.group(2) or "").strip()


def _scalar(text, lineno):
    if text == "":
        _err(lineno, "empty scalar; write null explicitly if that is meant")
    if text[0] in "\"'":
        q = text[0]
        if len(text) < 2 or text[-1] != q:
            _err(lineno, "unterminated quoted scalar")
        inner = text[1:-1]
        if q == "'":
            if "'" in inner.replace("''", ""):
                _err(lineno, "stray quote in single-quoted scalar")
            return inner.replace("''", "'")
        out, i = [], 0
        while i < len(inner):
            if inner[i] == "\\":
                if i + 1 >= len(inner) or inner[i + 1] not in '"\\n':
                    _err(lineno, "unsupported escape in double-quoted scalar")
                out.append({'"': '"', "\\": "\\", "n": "\n"}[inner[i + 1]]); i += 2
            else:
                out.append(inner[i]); i += 1
        return "".join(out)
    if text[0] in BAD_PLAIN_START:
        _err(lineno, f"unsupported construct starting with {text[0]!r}")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if text in ("True", "False", "yes", "no", "on", "off", "Null", "NULL", "None"):
        _err(lineno, f"ambiguous scalar {text!r}; use true/false/null")
    if INT_RE.match(text):
        return int(text)
    if FLOAT_RE.match(text):
        return float(text)
    if ": " in text or text.endswith(":"):
        _err(lineno, f"ambiguous plain scalar {text!r}; quote it")
    return text


def _parse_block(lines, i, indent):
    if lines[i].is_item:
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines, i, indent):
    out, n = {}, len(lines)
    while i < n and lines[i].indent == indent and not lines[i].is_item:
        key, val = _split_kv(lines[i])
        if key in out:
            _err(lines[i].no, f"duplicate key {key!r}")
        if val == "":
            j = i + 1
            if j >= n or lines[j].indent <= indent:
                _err(lines[i].no, f"key {key!r} has no value and no nested block")
            out[key], i = _parse_block(lines, j, lines[j].indent)
        else:
            out[key] = _scalar(val, lines[i].no)
            i += 1
    if i < n and lines[i].indent == indent and lines[i].is_item:
        _err(lines[i].no, "sequence at the same indent as its parent mapping; indent it")
    return out, i


def _parse_seq(lines, i, indent):
    out, n = [], len(lines)
    while i < n and lines[i].indent == indent and lines[i].is_item:
        body = lines[i].body
        if body == "":
            j = i + 1
            if j >= n or lines[j].indent <= indent:
                _err(lines[i].no, "empty sequence item")
            v, i = _parse_block(lines, j, lines[j].indent)
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_.\-]*:( |$)", body):
            v, i = _parse_item_map(lines, i, indent + 2)
        else:
            v = _scalar(body, lines[i].no)
            i += 1
        out.append(v)
    return out, i


def _parse_item_map(lines, i, mindent):
    """A `- key: value` item, plus any following entries aligned under it."""
    out, n = {}, len(lines)
    key, val = _split_kv(lines[i])
    if val == "":
        j = i + 1
        if j >= n or lines[j].indent <= mindent:
            _err(lines[i].no, f"key {key!r} has no value and no nested block")
        out[key], i = _parse_block(lines, j, lines[j].indent)
    else:
        out[key] = _scalar(val, lines[i].no)
        i += 1
    while i < n and lines[i].indent == mindent and not lines[i].is_item:
        k2, v2 = _split_kv(lines[i])
        if k2 in out:
            _err(lines[i].no, f"duplicate key {k2!r}")
        if v2 == "":
            j = i + 1
            if j >= n or lines[j].indent <= mindent:
                _err(lines[i].no, f"key {k2!r} has no value and no nested block")
            out[k2], i = _parse_block(lines, j, lines[j].indent)
        else:
            out[k2] = _scalar(v2, lines[i].no)
            i += 1
    return out, i


def parse(text):
    """Parse the subset. Raises YamlSubsetError on anything it does not fully understand."""
    lines = _scan(text)
    if not lines:
        raise YamlSubsetError("document is empty")
    if lines[0].indent != 0:
        _err(lines[0].no, "document must start at column 0")
    doc, i = _parse_block(lines, 0, 0)
    if i != len(lines):
        _err(lines[i].no, "unexpected indentation; block did not close cleanly")
    return doc


def load(path):
    with open(path, encoding="utf-8") as fh:
        return parse(fh.read())
