#!/usr/bin/env python3
"""Every nbno script that makes HTTP requests sends the honest User-Agent
CLAUDE.md asks for, carrying the plugin's version from plugin.json, and no
request is made without it (Python's default "Python-urllib/…" is refused
by some hosts).
Run: python tests/nbno/test_user_agent.py
"""

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno"
sys.path.insert(0, str(SKILL / "scripts"))
VERSION = json.loads((SKILL.parents[1] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


import geo_check, nb_search, ocr_chunked, zotero_book  # noqa: E402,E401

for mod in (geo_check, nb_search, ocr_chunked, zotero_book):
    ua = mod.USER_AGENT
    check(f"{mod.__name__}: UA carries the plugin version", ua.startswith(f"nbno-skill/{VERSION} "), True)
    check(f"{mod.__name__}: UA names the repo", "github.com/StianOby/claude-legal-tools" in ua, True)
    check(f"{mod.__name__}: not Mozilla/ or Python-urllib/", ua.startswith(("Mozilla/", "Python-urllib/")), False)

check("zotero_book._request sets the UA", zotero_book._request("https://example.org").get_header("User-agent"),
      zotero_book.USER_AGENT)
check("…and keeps the caller's headers",
      zotero_book._request("https://example.org", {"cookie": "nbsso=x"}).get_header("Cookie"), "nbsso=x")

# No bare urlopen(<url string>): every request goes through a Request with
# headers (a Request object or the _request helper).
for path in sorted((SKILL / "scripts").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    bare = re.findall(r"urlopen\(\s*(?:f?[\"']|[A-Z_]+\.format)", text)
    check(f"{path.name}: no urlopen on a bare URL", bare, [])

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
