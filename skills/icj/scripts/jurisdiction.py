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

from bs4 import BeautifulSoup

from _common import BASE, fetch_cached

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

def _main_content(soup: BeautifulSoup) -> BeautifulSoup:
    """Return the main content node, falling back gracefully if the layout shifts."""
    main = soup.find("main") or soup
    # Strip nav menus and footer that bleed into get_text otherwise
    for sel in ["nav", "footer"]:
        for n in main.find_all(sel):
            n.decompose()
    return main


def _get_text_block(soup: BeautifulSoup) -> str:
    main = _main_content(soup)
    # Remove tables (we may extract them separately)
    for t in main.find_all("table"):
        t.decompose()
    text = main.get_text("\n", strip=True)
    # Drop nav residuals — anything before the H1 or anything that looks like
    # the site navigation is not interesting.
    h1 = main.find("h1")
    if h1:
        # Reconstruct a cleaner block from the H1 onwards.
        parts = []
        capture = False
        for el in main.descendants:
            if el is h1:
                capture = True
            if capture and getattr(el, "name", None) in ("p", "li", "h2", "h3", "h4"):
                t = el.get_text(" ", strip=True)
                if t:
                    parts.append(t)
        if parts:
            return "\n\n".join(parts)
    return text


# --- /states-entitled-to-appear -----------------------------------------

def states(*, force_refresh: bool = False) -> dict:
    """All UN-member states currently entitled to appear, with admission date and
    (where applicable) the date their Article 36(2) declaration was deposited."""
    html, entry, _ = fetch_cached(URLS["states_entitled_to_appear"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = _main_content(soup)
    table = main.find("table")
    rows = []
    if table:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            # Skip header
            if cells[0].name == "th":
                continue
            state = cells[0].get_text(" ", strip=True).lstrip("﻿")
            admission = cells[1].get_text(" ", strip=True)
            decl_cell = cells[2]
            decl_link = decl_cell.find("a")
            decl_date = decl_cell.get_text(" ", strip=True) or None
            decl_url = urljoin(BASE, decl_link["href"]) if decl_link else None
            rows.append(
                {
                    "state": state,
                    "admission_date": admission,
                    "declaration_date": decl_date,
                    "declaration_url": decl_url,
                }
            )
    # Pull the leading explanatory paragraph(s)
    intro = []
    for p in main.find_all("p", limit=4):
        t = p.get_text(" ", strip=True)
        if t and len(t) > 30:
            intro.append(t)
    return {
        "url": URLS["states_entitled_to_appear"],
        "fetched_at": entry.fetched_at,
        "intro": "\n\n".join(intro),
        "states": rows,
    }


# --- /states-not-members ------------------------------------------------

def non_un_parties(*, force_refresh: bool = False) -> dict:
    html, entry, _ = fetch_cached(URLS["states_not_members"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    return {
        "url": URLS["states_not_members"],
        "fetched_at": entry.fetched_at,
        "text": _get_text_block(soup),
    }


# --- /states-not-parties ------------------------------------------------

def non_parties(*, force_refresh: bool = False) -> dict:
    html, entry, _ = fetch_cached(URLS["states_not_parties"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    return {
        "url": URLS["states_not_parties"],
        "fetched_at": entry.fetched_at,
        "text": _get_text_block(soup),
    }


# --- /basis-of-jurisdiction ---------------------------------------------

def basis(*, force_refresh: bool = False) -> dict:
    html, entry, _ = fetch_cached(URLS["basis_of_jurisdiction"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    return {
        "url": URLS["basis_of_jurisdiction"],
        "fetched_at": entry.fetched_at,
        "text": _get_text_block(soup),
    }


# --- /treaties ----------------------------------------------------------

def treaties(*, force_refresh: bool = False, year: Optional[int] = None,
             search: Optional[str] = None) -> dict:
    """Return the list of treaties conferring jurisdiction on the Court.

    Each entry: {date, title, status_of_court (text), url (when present)}.
    Filters: --year and --search are applied case-insensitively to the title.
    """
    html, entry, _ = fetch_cached(URLS["treaties"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = _main_content(soup)
    items: list[dict] = []
    # The treaties page renders as paragraphs / list-items rather than a table;
    # the format varies. Pull both <p> and <li> chunks and extract any link.
    for el in main.find_all(["p", "li"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) < 20:
            continue
        link = el.find("a", href=True)
        items.append(
            {
                "text": text,
                "url": urljoin(BASE, link["href"]) if link else None,
            }
        )
    # Light filtering
    if year is not None:
        items = [i for i in items if str(year) in i["text"]]
    if search:
        s = search.lower()
        items = [i for i in items if s in i["text"].lower()]
    return {
        "url": URLS["treaties"],
        "fetched_at": entry.fetched_at,
        "count": len(items),
        "items": items,
    }


# --- /organs-agencies-authorized ----------------------------------------

def organs(*, force_refresh: bool = False) -> dict:
    html, entry, _ = fetch_cached(URLS["organs_agencies_authorized"], force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    return {
        "url": URLS["organs_agencies_authorized"],
        "fetched_at": entry.fetched_at,
        "text": _get_text_block(soup),
    }
