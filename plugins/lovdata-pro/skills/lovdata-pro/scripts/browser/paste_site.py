#!/usr/bin/env python3
"""paste_site.py - the lovdata-pro helper copy for one Lovdata Pro site.

Usage:  python3 <skill_dir>/scripts/browser/paste_site.py <pro2|klassisk>

lovdata_pro.js serves both the new Lovdata Pro ("pro2") and Lovdata Pro
Klassisk. Code for only one of them sits between a line "//#site pro2" (or
"//#site klassisk") and a line "//#end". This drops the other site's blocks,
sets HELPER_SITE to the chosen site, strips the result with paste.py (same
folder) and writes it to the system temp directory. It prints one line: the
path and the size. Read that file and send its whole contents via
javascript_tool; its last line makes the reply [VERSION, SITE].
"""

import os
import re
import sys
import tempfile

# No __pycache__ in the installed plugin's folder.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paste  # noqa: E402  (shared/browser-paste/paste.py)

SITES = ("pro2", "klassisk")
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lovdata_pro.js")
_OPEN = re.compile(r"^\s*//#site\s+(\w+)\s*$")
_CLOSE = re.compile(r"^\s*//#end\s*$")
_SITE_LINE = "const HELPER_SITE = 'all';"


def cut(src, site):
    """src without the blocks of the other site, HELPER_SITE set to site."""
    out, inside = [], None
    for n, line in enumerate(src.split("\n"), 1):
        m = _OPEN.match(line)
        if m:
            if inside:
                raise ValueError("line %d: //#site inside a //#site block" % n)
            if m.group(1) not in SITES:
                raise ValueError("line %d: unknown site %r" % (n, m.group(1)))
            inside = m.group(1)
            continue
        if _CLOSE.match(line):
            if not inside:
                raise ValueError("line %d: //#end without //#site" % n)
            inside = None
            continue
        out.append(line if inside in (None, site) else "")
    if inside:
        raise ValueError("unclosed //#site %s block" % inside)
    text = "\n".join(out)
    if text.count(_SITE_LINE) != 1:
        raise ValueError("expected exactly one %r" % _SITE_LINE)
    return text.replace(_SITE_LINE, "const HELPER_SITE = '%s';" % site)


def main(argv):
    if len(argv) not in (2, 3) or argv[1] not in SITES:
        sys.exit("usage: paste_site.py <pro2|klassisk>  (pro2 = the new Lovdata Pro)")
    helper = argv[2] if len(argv) == 3 else HELPER
    src = open(helper, encoding="utf-8").read()
    out = paste.strip(cut(src, argv[1]))
    # The paste's reply: which helper now runs in the tab.
    out += "[window.__lp.VERSION, window.__lp.SITE]" + chr(10)
    dest = os.path.join(tempfile.gettempdir(),
                        "%s.%s.paste.js" % (os.path.basename(helper)[:-3], argv[1]))
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("%s  (%d chars, from %d) - Read it and send ALL of it via "
          "javascript_tool" % (dest, len(out), len(src)))


if __name__ == "__main__":
    main(sys.argv)
