#!/usr/bin/env python3
"""
eurlex_search.py — last-resort search wrapper.

The eurlex MCP's `eurlex_search` is the primary search tool (it queries the
publications.europa.eu SPARQL endpoint directly and returns structured CELEX
hits). This script is only useful when:

  - the MCP search returns no hits but you suspect the document exists,
  - the user has a Curia-style case number ("C-371/02") and you want to
    confirm the CELEX,
  - you want to bulk-resolve case numbers to CELEX IDs offline.

It does this by hitting EUR-Lex's public quick-search HTML page and
extracting CELEX identifiers from the result list.

Usage:
    python3 eurlex_search.py "Björnekulla" --limit 5
    python3 eurlex_search.py "C-371/02"    --limit 3
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse

import requests  # type: ignore[import-untyped]

USER_AGENT = "Mozilla/5.0 (eurlex/1.0)"
TIMEOUT = 30
SEARCH_URL = "https://eur-lex.europa.eu/search.html"

# CELEX shapes:
#   Treaty: 1####E### / 1####M### etc.
#   Acts:   3####R####, 3####L####, 3####D####, 3####H####, ...
#   Cases:  6####CJ####, 6####CC####, 6####TJ####, 6####CO####, ...
CELEX_RE = re.compile(r"\b([1-9]\d{3}[A-Z]{1,2}\d{2,4})\b")


def search(query: str, limit: int = 10) -> list[dict[str, str]]:
    params = {
        "scope": "EURLEX",
        "text": query,
        "lang": "en",
        "qid": "1",
        "DTS_DOM": "ALL",
    }
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text

    seen: list[str] = []
    for m in CELEX_RE.finditer(text):
        c = m.group(1)
        if c not in seen:
            seen.append(c)
        if len(seen) >= limit:
            break

    out = []
    # Pull a snippet near each CELEX so the human/agent can disambiguate.
    for celex in seen:
        idx = text.find(celex)
        snippet_start = max(0, idx - 200)
        snippet_end = min(len(text), idx + 200)
        snippet = re.sub(r"<[^>]+>", " ", text[snippet_start:snippet_end])
        snippet = re.sub(r"\s+", " ", snippet).strip()
        out.append({"celex": celex, "context": snippet})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="EUR-Lex HTML search (last-resort fallback)")
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)

    hits = search(args.query, limit=args.limit)
    if not hits:
        print("No CELEX hits found in the search HTML response.", file=sys.stderr)
        return 1
    for h in hits:
        print(f"{h['celex']}  {h['context'][:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
