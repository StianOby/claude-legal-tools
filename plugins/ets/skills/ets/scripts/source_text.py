"""Shared rules for turning a source's markup into text (CLAUDE.md, "Source
text: as little conversion as possible"). Canonical copy in
shared/source-text/; the plugins carry copies (.github/scripts/check-shared.py).

A converter keeps the source's characters and writes out only what the page
draws but the markup leaves implicit:

- Emphasis: the converter emits EM/EM_END around <i>/<em> text and
  STRONG/STRONG_END around <b>/<strong> text, then calls finish(), which
  writes *italic*, **bold**, ***both***. Markers hug the text (spaces go
  outside), never span a line, and empty emphasis disappears.
- Superscript: superscript() writes m², 10⁻¹ when every character has a
  Unicode superscript, else ^text^. Footnote numbers are [fn N] instead
  (the converter decides which <sup> is a footnote).
- List numbers: list_label() as the browser numbers an <ol>.
- Non-breaking spaces (U+00A0, U+202F) become plain spaces: SPACES.

Search code matches the text through fold(), which drops the emphasis
markers and soft hyphens, so a typed phrase finds the text.
"""

from __future__ import annotations

import re
from typing import Optional

EM, EM_END, STRONG, STRONG_END = "\x02", "\x03", "\x04", "\x05"
# Whitespace that finish() moves outside the markers. Explicit, not
# str.isspace(), so a JavaScript port (hudoc.js) behaves the same.
_WS = " \t\r\f\v"
_MARKERS = EM + EM_END + STRONG + STRONG_END

# str.translate table: non-breaking spaces -> plain spaces.
SPACES = {0xA0: " ", 0x202F: " "}

_EMPHASIS_TAGS = {"i": (EM, EM_END), "em": (EM, EM_END), "b": (STRONG, STRONG_END), "strong": (STRONG, STRONG_END)}


def emphasis(tag: str, closing: bool) -> Optional[str]:
    """The placeholder for an emphasis tag, or None for any other tag."""
    pair = _EMPHASIS_TAGS.get(tag.lower())
    return None if pair is None else pair[1 if closing else 0]


_EMPHASIS_TAG_RE = re.compile(r"<(/?)(i|em|b|strong)(?:\s[^>]*)?>", re.I)


def mark_emphasis(html: str) -> str:
    """Replace the emphasis tags in an HTML string by placeholders (for
    converters that work on the markup with regular expressions). Whole tags
    are matched first, so a tag inside a malformed one ("<STRONG]</STRONG>",
    which a browser shows as nothing) is left for the converter to drop."""
    def one(m: re.Match) -> str:
        e = _EMPHASIS_TAG_RE.fullmatch(m.group(0))
        return emphasis(e.group(2), bool(e.group(1))) if e else m.group(0)
    return re.sub(r"<[^>]*>", one, html)


def finish(text: str) -> str:
    """Resolve the emphasis placeholders in `text` to Markdown markers,
    nested as Markdown nests them (*see **Holship**, para 90*)."""
    if not any(c in text for c in _MARKERS):
        return text
    out: list[str] = []
    opened: list[str] = []   # markers open in the output, outermost first
    ws: list[str] = []       # spaces not yet written: they go outside markers
    italic = bold = 0

    def close_to(target: set) -> None:
        keep = 0
        while keep < len(opened) and opened[keep] in target:
            keep += 1
        for mark in reversed(opened[keep:]):
            out.append(mark)
        del opened[keep:]

    for c in text:
        if c in _MARKERS:
            if c == EM:
                italic += 1
            elif c == EM_END:
                italic = max(0, italic - 1)
            elif c == STRONG:
                bold += 1
            else:
                bold = max(0, bold - 1)
            continue
        if c == "\n":
            close_to(set())          # a marker never spans a line break
            out.extend(ws)
            ws.clear()
            out.append(c)
            continue
        if c in _WS:
            ws.append(c)
            continue
        target = {m for m, on in (("**", bold > 0), ("*", italic > 0)) if on}
        close_to(target)
        out.extend(ws)
        ws.clear()
        for mark in ("**", "*"):
            if mark in target and mark not in opened:
                out.append(mark)
                opened.append(mark)
        out.append(c)
    close_to(set())
    out.extend(ws)
    return "".join(out)


def plain(text: str) -> str:
    """Drop the emphasis placeholders (headings, metadata fields)."""
    return text.translate({ord(c): None for c in _MARKERS})


_SUP = dict(zip("0123456789+-−=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾"))


def superscript(text: str) -> str:
    """m<sup>2</sup> -> "m²"; text with no Unicode superscript -> "^text^"."""
    core = text.strip(_WS + "\n")
    if not core:
        return text
    lead, trail = text[:text.index(core)], text[text.index(core) + len(core):]
    if all(c in _SUP for c in core):
        return lead + "".join(_SUP[c] for c in core) + trail
    return f"{lead}^{core}^{trail}"


def list_label(n: int, kind: str) -> str:
    """The number the browser draws for item n of an <ol type=kind>."""
    if kind in ("I", "i"):
        out = ""
        for value, numeral in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                               (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
            while n >= value:
                out += numeral
                n -= value
        return out if kind == "I" else out.lower()
    if kind in ("A", "a"):
        out = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            out = chr(ord(kind) + r) + out
        return out
    return str(n)


_STYLE_KIND = {"lower-alpha": "a", "lower-latin": "a", "upper-alpha": "A", "upper-latin": "A",
               "lower-roman": "i", "upper-roman": "I", "decimal": "1"}


def ol_kind(attrs: str) -> str:
    """The numbering of an <ol> from its attributes: type="a|A|i|I|1", or an
    inline list-style-type. Default decimal."""
    m = re.search(r"list-style-type\s*:\s*([a-z-]+)", attrs, re.I)
    if m and m.group(1).lower() in _STYLE_KIND:
        return _STYLE_KIND[m.group(1).lower()]
    m = re.search(r'\btype\s*=\s*"?([aAiI1])\b', attrs)
    return m.group(1) if m else "1"


def ol_start(attrs: str) -> int:
    m = re.search(r'\bstart\s*=\s*"?(-?\d+)', attrs)
    return int(m.group(1)) if m else 1


def li_value(attrs: str) -> Optional[int]:
    m = re.search(r'\bvalue\s*=\s*"?(-?\d+)', attrs)
    return int(m.group(1)) if m else None


def mark_lists(html: str, bullet: str = "- ") -> str:
    """Write each <li>'s marker into the markup, as the browser draws it:
    `bullet` in a <ul>, the item's number in an <ol> ("1. ", "b. ", "iv. ";
    start, type, list-style-type and <li value> respected). The marker
    follows a newline; the tags stay for the converter's own handling."""
    stack: list = []

    def one(m: re.Match) -> str:
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if tag in ("ol", "ul"):
            if closing:
                if stack:
                    stack.pop()
            else:
                stack.append([ol_kind(attrs), ol_start(attrs)] if tag == "ol" else None)
            return m.group(0)
        if closing:
            return m.group(0)
        top = stack[-1] if stack else None
        if top is None:
            return m.group(0) + "\n" + bullet
        value = li_value(attrs)
        if value is not None:
            top[1] = value
        label = list_label(top[1], top[0])
        top[1] += 1
        return f"{m.group(0)}\n{label}. "

    return re.sub(r"<(/?)(ol|ul|li)\b([^>]*)>", one, html, flags=re.I)


def fold(text: str) -> str:
    """The text as search matches it: without emphasis markers and soft
    hyphens. Apply it to the query as well."""
    return text.replace("*", "").replace("\xad", "")
