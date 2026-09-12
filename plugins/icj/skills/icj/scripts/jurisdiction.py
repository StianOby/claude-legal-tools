"""
Scrape and serve the seven ICJ jurisdiction pages.

Each function returns a dict suitable for json.dumps. The HTML is fetched
through _common.fetch_cached, so calls are cheap after the first hit.

Pages handled:
  /index.php/states-entitled-to-appear        -> states()
  /index.php/states-not-members               -> non_un_parties()
  /index.php/states-not-parties               -> non_parties()
  /index.php/basis-of-jurisdiction            -> basis()
  /index.php/treaties                         -> treaties()
  /index.php/organs-agencies-authorized       -> organs()
  /index.php/declarations                     -> handled in declarations.py
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from _common import BASE, fetch_cached
from _html import Node, main_content, parse

URLS = {
    "states_entitled_to_appear": f"{BASE}/index.php/states-entitled-to-appear",
    "states_not_members": f"{BASE}/index.php/states-not-members",
    "states_not_parties": f"{BASE}/index.php/states-not-parties",
    "basis_of_jurisdiction": f"{BASE}/index.php/basis-of-jurisdiction",
    "treaties": f"{BASE}/index.php/treaties",
    "organs_agencies_authorized": f"{BASE}/index.php/organs-agencies-authorized",
    "declarations": f"{BASE}/index.php/declarations",
}


def all_jurisdiction_urls() -> list[str]:
    return list(URLS.values())


# --- helpers ------------------------------------------------------------

def _get_text_block(root: Node) -> str:
    """The page's prose from the H1 onwards, as paragraphs. Tables are
    dropped (they are extracted separately where they matter)."""
    main = main_content(root)
    for t in main.find_all("table"):
        t.decompose()
    h1 = main.find("h1")
    parts: list[str] = []
    capture = h1 is None
    for el in main.iter():
        if el is h1:
            capture = True
            continue
        if capture and el.tag in ("p", "li", "h2", "h3", "h4"):
            t = el.get_text()
            if t:
                parts.append(t)
    if parts:
        return "\n\n".join(parts)
    return main.get_text("\n")


# --- /states-entitled-to-appear -----------------------------------------

def states(*, force_refresh: bool = False) -> dict:
    """All UN-member states currently entitled to appear, with admission date and
    (where applicable) the date their Article 36(2) declaration was deposited."""
    html, entry, _ = fetch_cached(URLS["states_entitled_to_appear"], force_refresh=force_refresh)
    main = main_content(parse(html))
    table = main.find("table")
    rows = []
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3 or cells[0].tag == "th":
                continue
            state = cells[0].get_text().lstrip("﻿")
            admission = cells[1].get_text()
            decl_cell = cells[2]
            decl_link = decl_cell.find("a")
            decl_date = decl_cell.get_text() or None
            decl_url = urljoin(BASE, decl_link["href"]) if decl_link and decl_link.get("href") else None
            rows.append(
                {
                    "state": state,
                    "admission_date": admission,
                    "declaration_date": decl_date,
                    "declaration_url": decl_url,
                }
            )
    intro = []
    for p in main.find_all("p", limit=4):
        t = p.get_text()
        if t and len(t) > 30:
            intro.append(t)
    return {
        "url": URLS["states_entitled_to_appear"],
        "fetched_at": entry.fetched_at,
        "intro": "\n\n".join(intro),
        "states": rows,
    }


# --- text-only pages ----------------------------------------------------

def _text_page(key: str, *, force_refresh: bool = False) -> dict:
    html, entry, _ = fetch_cached(URLS[key], force_refresh=force_refresh)
    return {
        "url": URLS[key],
        "fetched_at": entry.fetched_at,
        "text": _get_text_block(parse(html)),
    }


def non_un_parties(*, force_refresh: bool = False) -> dict:
    return _text_page("states_not_members", force_refresh=force_refresh)


def non_parties(*, force_refresh: bool = False) -> dict:
    return _text_page("states_not_parties", force_refresh=force_refresh)


def basis(*, force_refresh: bool = False) -> dict:
    return _text_page("basis_of_jurisdiction", force_refresh=force_refresh)


def organs(*, force_refresh: bool = False) -> dict:
    return _text_page("organs_agencies_authorized", force_refresh=force_refresh)


# --- /treaties ----------------------------------------------------------

def treaties(*, force_refresh: bool = False, year: Optional[int] = None,
             search: Optional[str] = None) -> dict:
    """Return the list of treaties conferring jurisdiction on the Court.

    The page is a table with the columns Year, Date, Place, Title and Clause,
    Contracting Parties; the Year cell spans all treaties of that year. Each entry: {year, date, place, title, parties, text,
    url (when the title links somewhere)}. Filters: --year matches the Year
    column; --search is a case-insensitive substring of title + parties.
    """
    html, entry, _ = fetch_cached(URLS["treaties"], force_refresh=force_refresh)
    main = main_content(parse(html))
    items: list[dict] = []
    intro: list[str] = []
    for p in main.find_all("p", limit=6):
        t = p.get_text()
        if t and len(t) > 30:
            intro.append(t)
    last_year = ""
    for table in main.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) == 5:
                yr, date, place, title, parties = (c.get_text() for c in cells)
                last_year = yr or last_year
            elif len(cells) == 4:
                # The Year cell spans several rows (rowspan): carry it forward.
                yr = last_year
                date, place, title, parties = (c.get_text() for c in cells)
            else:
                continue
            if not title:
                continue
            link = cells[-2].find("a")
            items.append(
                {
                    "year": yr,
                    "date": date,
                    "place": place,
                    "title": title,
                    "parties": parties,
                    "text": f"{yr} {date} {place} — {title} — {parties}".strip(),
                    "url": urljoin(BASE, link["href"]) if link and link.get("href") else None,
                }
            )
    total = len(items)
    if year is not None:
        items = [i for i in items if i["year"] == str(year)]
    if search:
        s = search.lower()
        items = [i for i in items if s in i["title"].lower() or s in i["parties"].lower()]
    return {
        "url": URLS["treaties"],
        "fetched_at": entry.fetched_at,
        "intro": "\n\n".join(intro),
        "count_total": total,
        "count": len(items),
        "items": items,
    }
