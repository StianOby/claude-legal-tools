"""
Permanent Court of International Justice (1922-1946).

The Court hosts the PCIJ collection at three pages:
  /pcij-series-a    Judgments 1923-1930   (codes A01..A24)
  /pcij-series-b    Advisory opinions 1923-1930  (codes B01..B17 or so)
  /pcij-series-ab   Judgments, Orders, Advisory opinions from 1931  (codes A/B 40..)

Each page renders its cases as h3/h4 headings (the case code, e.g. "A10")
followed by an h4 with the case name ("A10 \"Lotus\""), with one or more
PDF links underneath (judgment, dissenting opinions, annexes).

Series C, D, E, F are out of scope for this skill — Series C is pleadings
and oral arguments (handled by the future hearing-documents skill); D, E, F
are organisational documents and indexes.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from _common import BASE, fetch_cached

SERIES_URLS = {
    "a": f"{BASE}/pcij-series-a",
    "b": f"{BASE}/pcij-series-b",
    "ab": f"{BASE}/pcij-series-ab",
}

# Recognise codes like A01, A24, B04, "A/B 53", "A/B53".
_CODE_RE = re.compile(r"^(A/B|A|B)\s*[-/]?\s*(\d{1,3})", re.IGNORECASE)


def _normalise_code(s: str) -> Optional[str]:
    """Return a canonical code like 'A10', 'B04', 'A/B53' from any reasonable input."""
    s = s.strip()
    m = _CODE_RE.match(s.replace(" ", ""))
    if not m:
        # Try matching 'A10 "Lotus"' style — the regex above already handles A10
        m = _CODE_RE.match(s)
        if not m:
            return None
    series = m.group(1).upper().replace("/", "/")
    num = int(m.group(2))
    if series in ("A", "B"):
        return f"{series}{num:02d}"
    return f"A/B{num}"


def _parse_series_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    cases: list[dict] = []
    current: Optional[dict] = None
    # Walk H3 (case code) and H4 (case name) and H6 (PDF links) in order.
    for el in main.descendants:
        name = getattr(el, "name", None)
        if name == "h3":
            txt = el.get_text(" ", strip=True)
            code = _normalise_code(txt)
            if code is None:
                continue
            current = {
                "code": code,
                "raw_code": txt,
                "title": None,
                "documents": [],
            }
            cases.append(current)
        elif name == "h4" and current is not None:
            txt = el.get_text(" ", strip=True)
            # Strip leading code if echoed
            stripped = re.sub(r"^[AB]/?B?\s*\d{1,3}\s*", "", txt, count=1).strip()
            if stripped:
                current["title"] = stripped
        elif name == "h6" and current is not None:
            a = el.find("a", href=True) if hasattr(el, "find") else None
            if a is None:
                continue
            href = a["href"]
            if not href.endswith(".pdf"):
                continue
            current["documents"].append(
                {
                    "label": a.get_text(" ", strip=True),
                    "url": href if href.startswith("http") else urljoin(BASE, href),
                }
            )
    return cases


def list_cases(series: Optional[str] = None, *, force_refresh: bool = False) -> dict:
    """List PCIJ cases. series in {'a', 'b', 'ab', None for all}."""
    out: dict[str, dict] = {}
    if series in (None, "all"):
        wanted = list(SERIES_URLS.keys())
    elif series.lower() in SERIES_URLS:
        wanted = [series.lower()]
    else:
        return {"error": f"unknown series: {series!r}; use a | b | ab"}
    for s in wanted:
        html, entry, _ = fetch_cached(SERIES_URLS[s], force_refresh=force_refresh)
        out[s] = {
            "url": SERIES_URLS[s],
            "fetched_at": entry.fetched_at,
            "cases": _parse_series_page(html),
        }
    return out


def show(code: str, *, force_refresh: bool = False) -> dict:
    """Return a single PCIJ case by its code (A10, B04, A/B53)."""
    norm = _normalise_code(code)
    if norm is None:
        return {"error": f"unrecognised PCIJ code: {code!r}"}
    if norm.startswith("A/B"):
        series = "ab"
    elif norm.startswith("A"):
        series = "a"
    else:
        series = "b"
    payload = list_cases(series, force_refresh=force_refresh)
    if "error" in payload:
        return payload
    cases = payload[series]["cases"]
    for c in cases:
        if c["code"] == norm:
            return {
                "series": series,
                "case": c,
                "source_url": payload[series]["url"],
                "fetched_at": payload[series]["fetched_at"],
            }
    return {"error": f"PCIJ code {norm} not found in series {series.upper()}"}
