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
_WS = re.compile(r"\s+")


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

    def get_text(self, sep: str = " ", strip: bool = True) -> str:
        if self.tag is None:
            pieces = [self.text or ""]
        else:
            pieces = [n.text or "" for n in self.iter() if n.tag is None]
        if strip:
            pieces = [_WS.sub(" ", p).strip() for p in pieces]
            pieces = [p for p in pieces if p]
        return sep.join(pieces)

    def decompose(self) -> None:
        if self.parent is not None:
            self.parent.children = [c for c in self.parent.children if c is not self]
            self.parent = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.tag is None:
            return f"Text({self.text!r})"
        return f"<{self.tag} {self.attrs}>"


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
