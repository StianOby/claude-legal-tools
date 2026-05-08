#!/usr/bin/env python3
"""
eurlex_paragraphs.py - extract a paragraph range from a CJEU/General Court
plain-text judgment produced by eurlex_fetch.py.

CJEU paragraphs are numbered "1", "2", ... and EUR-Lex renders them in two
main shapes after tag stripping:

    Style A: number on its own line, body on following lines
        73
        As regards Article 7(2) ...

    Style B: number followed by whitespace and body on the same line (older
             HTML and some XHTML renditions; whitespace can include U+00A0
             non-breaking space)
        73    As regards Article 7(2) ...

Both styles are recognised. A monotonic-counter heuristic rejects spurious
numeric prefixes such as Article numbers, footnote calls, or dates.

Usage:
    python3 eurlex_paragraphs.py plain.txt --from 73 --to 91
    python3 eurlex_paragraphs.py plain.txt --paragraphs 73,80,91
    python3 eurlex_paragraphs.py --celex 62016CJ0569 --lang ENG --from 73 --to 91
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Iterable

_PARA_ON_OWN_LINE = re.compile(r"^\s*(\d{1,4})\.?\s*$")
# Inline: digits, then whitespace including NBSP (U+00A0), then capital/quote
_PARA_INLINE = re.compile(
    "^\\s*(\\d{1,4})[.\\s \\t]+(?=[A-Z‘’“”\\(])"
)


def split_paragraphs(text):
    lines = text.splitlines()
    paras = {}
    current = None
    last_seen = 0
    for line in lines:
        m = _PARA_ON_OWN_LINE.match(line)
        if m:
            n = int(m.group(1))
            if (n == 1 and last_seen == 0) or n in (last_seen + 1, last_seen + 2):
                current = n
                last_seen = n
                paras.setdefault(current, [])
                continue
        m = _PARA_INLINE.match(line)
        if m:
            n = int(m.group(1))
            if (n == 1 and last_seen == 0) or n in (last_seen + 1, last_seen + 2):
                current = n
                last_seen = n
                body_start = line[m.end():].rstrip()
                paras[current] = [body_start] if body_start else []
                continue
        if current is not None:
            paras[current].append(line)
    return {k: "\n".join(v).strip() for k, v in paras.items() if v}


def select(paras, from_n, to_n, explicit):
    if explicit:
        wanted = sorted(set(explicit))
    else:
        a = from_n if from_n is not None else (min(paras) if paras else 1)
        b = to_n if to_n is not None else (max(paras) if paras else 0)
        wanted = list(range(a, b + 1))
    return [(n, paras[n]) for n in wanted if n in paras]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract paragraphs from an EUR-Lex judgment plain-text dump"
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("textfile", nargs="?", help="Plain text from eurlex_fetch --plain")
    src.add_argument("--celex", help="CELEX to fetch via eurlex_fetch")
    ap.add_argument("--lang", default="ENG")
    ap.add_argument("--from", dest="from_n", type=int)
    ap.add_argument("--to", dest="to_n", type=int)
    ap.add_argument("--paragraphs", help="Comma-separated paragraph numbers")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.celex:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        import eurlex_fetch
        text = eurlex_fetch.fetch(args.celex, args.lang)["plain_text"]
    else:
        text = pathlib.Path(args.textfile).read_text(encoding="utf-8")

    paras = split_paragraphs(text)

    if args.list:
        nums = sorted(paras)
        first = nums[0] if nums else "-"
        last = nums[-1] if nums else "-"
        print("Found " + str(len(nums)) + " paragraphs: " + str(first) + ".." + str(last))
        return 0

    explicit = None
    if args.paragraphs:
        explicit = [int(x) for x in args.paragraphs.split(",") if x.strip()]

    chosen = select(paras, args.from_n, args.to_n, explicit)
    if not chosen:
        print("No matching paragraphs found.", file=sys.stderr)
        return 1

    for n, body in chosen:
        print("--- " + chr(167) + str(n) + " ---")
        print(body)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
