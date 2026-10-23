"""
Minimal HTML DOM on top of the standard library's html.parser.

Provides just enough of the BeautifulSoup surface the icj modules need —
`find`, `find_all`, `get_text`, `iter` (descendants in document order),
`decompose` — so the skill runs without third-party packages. It is not a
general-purpose parser: it assumes the reasonably well-formed Drupal HTML
that icj-cij.org serves.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable, Iterator, Optional

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
# Opening one of these while the same tag is still open implicitly closes it.
_AUTO_CLOSE = {"p", "li", "option", "tr", "td", "th"}
# HTML's own whitespace, the only kind a browser collapses (not U+00A0).
_HTML_WS = re.compile(r"[ \t\n\r\f]+")
# Elements a browser lays out as blocks: their text never runs into the
# text around them.
_BLOCK = {
    "address", "article", "aside", "blockquote", "caption", "dd", "div", "dl",
    "dt", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag: Optional[str] = None, attrs: Optional[dict] = None,
                 text: Optional[str] = None, parent: Optional["Node"] = None):
        self.tag = tag            # None for text nodes
        self.attrs = attrs or {}
        self.children: list[Node] = []
        self.parent = parent
        self.text = text

    # -- attribute access --------------------------------------------------
    def get(self, key: str, default=None):
        return self.attrs.get(key, default)

    def __getitem__(self, key: str):
        return self.attrs[key]

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    # -- traversal ---------------------------------------------------------
    def iter(self) -> Iterator["Node"]:
        """Every descendant (not self), in document order."""
        stack = list(reversed(self.children))
        while stack:
            n = stack.pop()
            yield n
            if n.children:
                stack.extend(reversed(n.children))

    def find_all(self, tag: Optional[str | Iterable[str]] = None,
                 class_: Optional[str] = None, *, limit: Optional[int] = None) -> list["Node"]:
        tags = None if tag is None else ({tag} if isinstance(tag, str) else set(tag))
        out: list[Node] = []
        for n in self.iter():
            if n.tag is None:
                continue
            if tags is not None and n.tag not in tags:
                continue
            if class_ is not None and class_ not in n.classes:
                continue
            out.append(n)
            if limit is not None and len(out) >= limit:
                break
        return out

    def find(self, tag: Optional[str | Iterable[str]] = None,
             class_: Optional[str] = None) -> Optional["Node"]:
        hits = self.find_all(tag, class_, limit=1)
        return hits[0] if hits else None

    def get_text(self, sep: str = " ") -> str:
        """The text as a browser renders it: inline tags leave no trace,
        <br> is a line break, HTML whitespace collapses (U+00A0 stays,
        except at the edges of a line), and block elements are joined with
        `sep`. Footnote numbers (see _footnote_label) become "[fn N]"."""
        blocks: list[str] = []
        cur: list[str] = []

        def visit(n: "Node") -> None:
            if n.tag is None:
                cur.append(_HTML_WS.sub(" ", n.text or ""))
            elif n.tag == "br":
                cur.append("\n")
            elif (label := _footnote_label(n)) is not None:
                cur.append(f"[fn {label}]")
            elif n.tag in _BLOCK:
                flush()
                for c in n.children:
                    visit(c)
                flush()
            else:
                for c in n.children:
                    visit(c)

        def flush() -> None:
            lines = [ln.strip() for ln in "".join(cur).split("\n")]
            while lines and not lines[0]:
                lines.pop(0)
            while lines and not lines[-1]:
                lines.pop()
            if lines:
                blocks.append("\n".join(lines))
            cur.clear()

        if self.tag is None:
            visit(self)
        else:
            for c in self.children:
                visit(c)
        flush()
        return sep.join(blocks)

    def decompose(self) -> None:
        if self.parent is not None:
            self.parent.children = [c for c in self.parent.children if c is not self]
            self.parent = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.tag is None:
            return f"Text({self.text!r})"
        return f"<{self.tag} {self.attrs}>"


def _footnote_label(n: Node) -> Optional[str]:
    """The number of a footnote <sup>, else None. The basis-of-jurisdiction
    page marks a reference <a href="#1"><sup>1</sup></a> and starts the note
    <a id="1"></a><sup>1</sup>; written as "[fn 1]" both pair up for citing
    (the same form as the hudoc and lovdata-api skills)."""
    if n.tag != "sup" or len(n.children) != 1 or n.children[0].tag is not None:
        return None
    label = (n.children[0].text or "").strip()
    if not label.isdigit():
        return None
    p = n.parent
    if p is not None and p.tag == "a" and p.get("href", "").startswith("#"):
        return label
    if p is not None:
        i = p.children.index(n)
        prev = next((c for c in reversed(p.children[:i])
                     if c.tag is not None or (c.text or "").strip()), None)
        if prev is not None and prev.tag == "a" and prev.get("id"):
            return label
    return None


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("[document]")
        self.stack = [self.root]

    def _open(self, tag: str, attrs) -> Node:
        if tag in _AUTO_CLOSE and self.stack[-1].tag == tag:
            self.stack.pop()
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._open(tag, attrs)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(Node(text=data, parent=self.stack[-1]))


def parse(html: str) -> Node:
    """Parse an HTML document and return the root node."""
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root


def main_content(root: Node, *, drop: Iterable[str] = ("nav", "footer", "script", "style")) -> Node:
    """Return <main> (or the root when absent) with navigation noise removed."""
    main = root.find("main") or root
    for tag in drop:
        for n in main.find_all(tag):
            n.decompose()
    return main
