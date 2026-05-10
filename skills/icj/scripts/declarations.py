"""
Article 36(2) optional-clause declarations.

The /index.php/declarations index lists every state currently shown by the
Court. Each state has a per-state page at /declarations/<cc> with the
verbatim text the Court publishes (English version, with translator note
where relevant).
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from _common import BASE, fetch_cached, resolve_state, warn

INDEX_URL = f"{BASE}/index.php/declarations"


def _per_state_url(cc: str) -> str:
    return f"{BASE}/declarations/{cc.lower()}"


# --- Index ---------------------------------------------------------------

def index(*, force_refresh: bool = False) -> dict:
    """Return the list of states with deposited declarations.

    Each entry: {state, deposit_date, iso2, url}.
    """
    html, entry, _ = fetch_cached(INDEX_URL, force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    items: list[dict] = []
    # The index renders each state as a header (h5) containing an <a> to
    # /declarations/<cc>. Grab every link of that shape.
    for a in main.find_all("a", href=True):
        href = a["href"]
        m = re.match(r"^(?:https?://[^/]+)?/declarations/([a-z]{2})/?$", href)
        if not m:
            continue
        cc = m.group(1)
        text = a.get_text(" ", strip=True)
        # Text typically reads: "Norway 24 June 1996"
        # Split on first run of spaces followed by a digit.
        parts = re.split(r"\s+(?=\d)", text, maxsplit=1)
        if len(parts) == 2:
            state_name, deposit_date = parts[0].strip(), parts[1].strip()
        else:
            state_name, deposit_date = text, ""
        items.append(
            {
                "state": state_name,
                "iso2": cc,
                "deposit_date": deposit_date,
                "url": urljoin(BASE, href),
            }
        )
    # De-dup while preserving order — the index sometimes repeats links.
    seen = set()
    deduped = []
    for it in items:
        key = it["iso2"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    # Pull the introductory paragraph(s)
    intro_parts = []
    for p in main.find_all("p", limit=8):
        t = p.get_text(" ", strip=True)
        if t and len(t) > 30:
            intro_parts.append(t)
    return {
        "url": INDEX_URL,
        "fetched_at": entry.fetched_at,
        "count": len(deduped),
        "intro": "\n\n".join(intro_parts[:4]),
        "states": deduped,
    }


# --- Per-state text ------------------------------------------------------

def show(name_or_code: str, *, force_refresh: bool = False) -> dict:
    """Return the full text of one state's declaration."""
    cc = resolve_state(name_or_code)
    if cc is None:
        # Try the live index for a substring match.
        idx = index()
        candidates = [
            s for s in idx["states"]
            if name_or_code.strip().lower() in s["state"].lower()
        ]
        if len(candidates) == 1:
            cc = candidates[0]["iso2"]
        elif len(candidates) > 1:
            return {
                "error": "ambiguous state",
                "matches": candidates,
            }
        else:
            return {
                "error": f"unknown state: {name_or_code!r}",
                "hint": "Pass an ISO-2 code (no, fi, gb) or check `declarations list`.",
            }
    url = _per_state_url(cc)
    html, entry, _ = fetch_cached(url, force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    # Drop nav/footer noise
    for sel in ["nav", "footer"]:
        for n in main.find_all(sel):
            n.decompose()
    # The declaration text sits inside the page body, after the H1
    # (which is generic) and an H3 with the state name.
    h3 = main.find("h3")
    state_name = h3.get_text(" ", strip=True) if h3 else cc.upper()
    # Collect all paragraphs after the H3.
    parts: list[str] = []
    started = False
    for el in main.descendants:
        if el is h3:
            started = True
            continue
        if not started:
            continue
        name = getattr(el, "name", None)
        if name in ("p", "li"):
            t = el.get_text(" ", strip=True)
            # Stop when we hit the secondary navigation block.
            if t in ("Jurisdiction", "Top Menu", "Footer menu"):
                break
            if t:
                parts.append(t)
        elif name in ("h2", "h3") and el is not h3:
            t = el.get_text(" ", strip=True)
            if t and t not in ("Jurisdiction",):
                parts.append(f"## {t}")
    text = "\n\n".join(parts).strip()
    return {
        "url": url,
        "iso2": cc,
        "state": state_name,
        "fetched_at": entry.fetched_at,
        "text": text,
    }


def compare(states: list[str], *, force_refresh: bool = False) -> dict:
    """Return the text of two or more declarations side by side."""
    out = []
    for s in states:
        d = show(s, force_refresh=force_refresh)
        out.append(d)
    return {"declarations": out}
