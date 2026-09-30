#!/usr/bin/env python3
"""paste.py - make a browser helper cheaper to paste through javascript_tool.

Shared file: the canonical copy is shared/browser-paste/ in the repo; every
plugin with a browser helper carries an identical copy at
scripts/browser/paste.py (CI checks it).

Usage:  python3 <skill_dir>/scripts/browser/paste.py <skill_dir>/scripts/browser/<helper>.js

Writes a copy of the helper without comments, indentation or blank lines to
the system temp directory and prints one line: the path and the sizes. Read
that file and send its whole contents via javascript_tool. The copy is 30-55 %
smaller than the source and runs identically: a small JavaScript lexer keeps
every string, template literal and regular expression byte for byte, and
every line break stays where it was (automatic semicolon insertion depends on
them). CI runs each helper's own tests against this output.

Why not fetch the helper from GitHub: running code fetched from the internet
inside a logged-in page is what the Cowork safety check blocks ("Code from
External"), and a sha256 check does not change how that looks.
"""

import os
import re
import sys
import tempfile

_KEYWORDS_BEFORE_REGEX = {
    "return", "typeof", "case", "do", "else", "in", "of", "new", "delete",
    "void", "throw", "instanceof", "yield", "await",
}
_WORD = re.compile(r"[A-Za-z0-9_$\u0080-￿]+")


def _skip_string(src, i, quote):
    """Index just past the string literal that opens at src[i]."""
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        i += 1
        if c == quote:
            return i
    raise ValueError("unterminated string")


def _skip_regex(src, i):
    """Index just past the regex literal (with flags) that opens at src[i]."""
    i += 1
    in_class = False
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            raise ValueError("newline in regex literal at %d" % i)
        i += 1
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            m = _WORD.match(src, i)
            return m.end() if m else i
    raise ValueError("unterminated regex")


def tokens(src):
    """Yield (kind, text): kind is 'nl', 'ws' or 'code'. Comments become
    'ws' (or 'nl' when they span lines); strings, templates and regexes are
    single 'code' tokens, so nothing inside them is ever changed."""
    i, n = 0, len(src)
    stack = []      # one brace counter per open template ${ ... }
    prev = ""       # last significant token, for regex-vs-division
    while i < n:
        c = src[i]
        if c == "\n":
            yield "nl", c
            i += 1
            continue
        if c in " \t\r\f\v":
            j = i
            while j < n and src[j] in " \t\r\f\v":
                j += 1
            yield "ws", src[i:j]
            i = j
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            yield "ws", " "
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("unterminated block comment")
            yield ("nl" if "\n" in src[i:j] else "ws"), "\n"
            i = j + 2
            continue
        if c in "'\"":
            j = _skip_string(src, i, c)
            yield "code", src[i:j]
            prev, i = '"', j
            continue
        if c == "`" or (c == "}" and stack and stack[-1] == 0):
            # template text: from ` (or the } closing a ${) to ` or ${
            if c == "}":
                stack.pop()
            j = i + 1
            while True:
                if j >= n:
                    raise ValueError("unterminated template")
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "`":
                    j += 1
                    break
                if src.startswith("${", j):
                    j += 2
                    stack.append(0)
                    break
                j += 1
            yield "code", src[i:j]
            prev = "`" if src[j - 1] == "`" else "{"
            i = j
            continue
        if c == "/":
            regex = (prev == "" or prev in _KEYWORDS_BEFORE_REGEX
                     or (not _WORD.fullmatch(prev) and prev not in (")", "]", '"', "`", "/")))
            if regex:
                j = _skip_regex(src, i)
                yield "code", src[i:j]
                prev, i = "/", j
                continue
        m = _WORD.match(src, i)
        if m:
            yield "code", m.group()
            prev, i = m.group(), m.end()
            continue
        if stack:
            if c == "{":
                stack[-1] += 1
            elif c == "}":
                stack[-1] -= 1
        yield "code", c
        prev = c
        i += 1


def strip(src):
    lines, cur = [], []
    for kind, text in tokens(src):
        if kind == "nl":
            lines.append(cur)
            cur = []
        elif kind == "ws":
            if cur and cur[-1] != " ":
                cur.append(" ")
        else:
            cur.append(text)
    lines.append(cur)
    out = []
    for parts in lines:
        line = "".join(parts).rstrip(" ")
        if line:
            out.append(line)
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) != 2 or not os.path.isfile(argv[1]):
        sys.exit("usage: paste.py <skill_dir>/scripts/browser/<helper>.js")
    src = open(argv[1], encoding="utf-8").read()
    out = strip(src)
    dest = os.path.join(tempfile.gettempdir(),
                        os.path.basename(argv[1])[:-3] + ".paste.js")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("%s  (%d chars, from %d) - Read it and send ALL of it via "
          "javascript_tool" % (dest, len(out), len(src)))


if __name__ == "__main__":
    main(sys.argv)
