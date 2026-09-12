#!/usr/bin/env python3
"""
nb_search.py — find an nb.no item from a bibliographic reference.

The download scripts all start from an item ID (digibok_…). When you have
only author/title/year — a footnote, a bibliography entry — this searches
the public catalogue and prints, per hit, everything needed to pick the
right *edition*: year, publisher, page count, the canonical ID, and the
access class that decides whether it can be read at all.

No credentials: api.nb.no/catalog/v1/items is open and the access class it
reports is the same one `zotero_book.py` checks before downloading.

Usage:

    python nb_search.py "Eckhoff Rettskildelære"
    python nb_search.py "Eckhoff Rettskildelære" --year 2001
    python nb_search.py "Rettskildelære" --author Eckhoff --max 20
    python nb_search.py "Lov og Rett" --type tidsskrift
    python nb_search.py "Eckhoff Rettskildelære" --json

Every word in the query must match somewhere in the record (title,
creators, publisher, subjects…), so "Eckhoff Rettskildelære" is a good
query and a full citation with punctuation is not. Narrow with --year
rather than by adding words.

Reading the output:
  - Several hits with the same title and different years are different
    editions. Pick the one whose year matches the reference; never
    substitute another edition.
  - A title starting "Utdrag av …" is an excerpt (a compendium reprint of
    a few chapters), not the book.
  - access: EVERYWHERE = free anywhere; NORWAY = free from a Norwegian IP
    (Bokhylla); NB = legal deposit, readable only with a FEIDE loan.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.nb.no/catalog/v1/items"

_MEDIATYPE = {
    "bok": "bøker", "bøker": "bøker", "book": "bøker", "books": "bøker",
    "avis": "aviser", "aviser": "aviser", "newspaper": "aviser",
    "tidsskrift": "tidsskrift", "journal": "tidsskrift",
    "all": None, "alle": None,
}


def _get(url: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "nbno-skill nb_search.py",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search(query: str, year: str | None = None, author: str | None = None,
           mediatype: str | None = "bøker", size: int = 10) -> dict:
    q = query.strip()
    if author:
        q = f"{author.strip()} {q}".strip()
    params = [("q", q), ("size", str(size))]
    if mediatype:
        params.append(("filter", f"mediatype:{mediatype}"))
    if year:
        params.append(("filter", f"year:{year}"))
    url = API + "?" + urllib.parse.urlencode(params)
    return _get(url)


def _hit(item: dict) -> dict:
    md = item.get("metadata") or {}
    ai = item.get("accessInfo") or {}
    origin = md.get("originInfo") or {}
    urn = (md.get("identifiers") or {}).get("urn") or ""
    return {
        "id": urn.replace("URN:NBN:no-nb_", "") if urn else "",
        "urn": urn,
        "title": (md.get("title") or "").strip(),
        "creators": md.get("creators") or [],
        "year": origin.get("issued") or "",
        "publisher": origin.get("publisher") or "",
        "pages": md.get("pageCount") or "",
        "access": ai.get("accessAllowedFrom") or "?",
        "viewability": ai.get("viewability") or "?",
        "digital": bool(ai.get("isDigital")),
        "excerpt": (md.get("title") or "").lower().startswith("utdrag"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("query", help="Words that must all match (author, title).")
    ap.add_argument("--year", help="Publication year (exact).")
    ap.add_argument("--author", help="Added to the query; kept separate for readability.")
    ap.add_argument("--type", default="bok",
                    help="bok (default) | avis | tidsskrift | all")
    ap.add_argument("--max", type=int, default=10, help="Hits to print (default 10).")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = ap.parse_args(argv)

    if args.type not in _MEDIATYPE:
        ap.error(f"--type must be one of: {', '.join(sorted(_MEDIATYPE))}")
    try:
        data = search(args.query, year=args.year, author=args.author,
                      mediatype=_MEDIATYPE[args.type], size=max(1, args.max))
    except Exception as exc:  # network, JSON
        print(f"ERROR: catalogue search failed: {exc}", file=sys.stderr)
        return 2

    total = (data.get("page") or {}).get("totalElements", 0)
    hits = [_hit(it) for it in (data.get("_embedded") or {}).get("items", [])]

    if args.json:
        print(json.dumps({"total": total, "hits": hits}, ensure_ascii=False, indent=1))
        return 0

    print(f"{total} hit(s) in the catalogue; showing {len(hits)}"
          + (f" for year {args.year}" if args.year else "") + ".")
    if total > len(hits):
        print("Narrow with --year or --author if the one you want is not listed.")
    for h in hits:
        who = "; ".join(h["creators"]) or "(no creator)"
        flag = "  [EXCERPT — not the full book]" if h["excerpt"] else ""
        print(f"\n{h['id'] or '(no digital copy)'}")
        print(f"  {h['title']}{flag}")
        print(f"  {who}")
        print(f"  {h['year'] or '?'} · {h['publisher'] or '?'} · "
              f"{h['pages'] or '?'} pages")
        print(f"  access: {h['access']}  viewability: {h['viewability']}"
              + ("" if h["digital"] else "  (not digitised)"))
    if hits:
        print("\naccess: EVERYWHERE = free; NORWAY = Norwegian IP (Bokhylla); "
              "NB = FEIDE loan required. Pass the id to zotero_book.py or "
              "nbno_run.sh.")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
