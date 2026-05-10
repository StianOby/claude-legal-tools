"""
ICJ contentious + advisory cases.

Endpoints used:
  /index.php/list-of-all-cases   -> list_all()
  /index.php/decisions           -> recent()
  /case/<N>                      -> show(case_id)

Pleadings and verbatim records are deliberately omitted from `show` output —
that's the responsibility of a separate skill for hearing documents.

PDF naming on the site is uniform:
  /sites/default/files/case-related/<case_id>/<case_id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf
where <type> is one of:
  jud  Judgment
  adv  Advisory opinion
  ord  Order
  app  Application instituting proceedings
  pre  Press release
  sum  Summary of judgment / order
  mem, cmem, rep, rej, rec   (memorial, counter-memorial, reply, rejoinder, ...)
  cr                          Verbatim record (compte rendu)
We treat jud/adv/ord/sum/app as "decision-or-around" and surface them; mem/cmem/
rep/rej/cr are pleadings/verbatim records and we drop them from show().
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from _common import BASE, fetch_cached

LIST_ALL_URL = f"{BASE}/index.php/list-of-all-cases"
DECISIONS_URL = f"{BASE}/index.php/decisions"
PENDING_URL = f"{BASE}/index.php/pending-cases"


# Document types we expose. Anything else (mem, cmem, rep, rej, cr, rejoinder...)
# is treated as a pleading or verbatim record and excluded.
DECISION_DOC_TYPES = {
    "jud": "Judgment",
    "adv": "Advisory opinion",
    "ord": "Order",
    "sum": "Summary",
    "app": "Application instituting proceedings",
    "req": "Request for advisory opinion",
    "pre": "Press release",
}

PLEADING_DOC_TYPES = {
    "mem": "Memorial",
    "cmem": "Counter-Memorial",
    "rep": "Reply",
    "rej": "Rejoinder",
    "cr": "Verbatim record",
    "obs": "Written observations",
    "wri": "Written statement",
    "wso": "Written observations / written statement",
}


def _parse_pdf_filename(href: str) -> Optional[dict]:
    """Parse /sites/default/files/case-related/<id>/<id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf."""
    m = re.search(
        r"/case-related/(\d+)/\1-(\d{8})-([a-z]+)-(\d{2})-(\d{2})-([a-z]+)\.pdf$",
        href,
    )
    if not m:
        return None
    return {
        "case_id": int(m.group(1)),
        "date": f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:8]}",
        "doc_type": m.group(3),
        "serial": f"{m.group(4)}-{m.group(5)}",
        "lang": m.group(6),
        "url": href if href.startswith("http") else urljoin(BASE, href),
    }


# --- /list-of-all-cases -------------------------------------------------

def list_all(*, force_refresh: bool = False, year: Optional[int] = None,
             country: Optional[str] = None, advisory: bool = False,
             contentious: bool = False, pending: bool = False) -> dict:
    """List all ICJ cases. Filters: --year, --country (substring), --advisory,
    --contentious, --pending."""
    if pending:
        html, entry, _ = fetch_cached(PENDING_URL, force_refresh=force_refresh)
    else:
        html, entry, _ = fetch_cached(LIST_ALL_URL, force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    cases: list[dict] = []
    for table in main.find_all("table"):
        cap = table.find("caption")
        cap_year = cap.get_text(strip=True) if cap else None
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            title_cell, intro_cell, conc_cell, kind_cell = cells[:4]
            link = title_cell.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            m = re.search(r"(?:^|/)case/(\d+)", href)
            case_id = int(m.group(1)) if m else None
            cases.append(
                {
                    "case_id": case_id,
                    "title": title_cell.get_text(" ", strip=True),
                    "year_introduced": intro_cell.get_text(strip=True),
                    "year_concluded": conc_cell.get_text(strip=True),
                    "kind": kind_cell.get_text(strip=True).lstrip("﻿"),
                    "url": urljoin(BASE, href),
                    "table_year": cap_year,
                }
            )
    # Filters
    def keep(c: dict) -> bool:
        if year is not None and str(year) not in (c["year_introduced"], c["year_concluded"]):
            return False
        if country and country.lower() not in c["title"].lower():
            return False
        if advisory and "advisory" not in c["kind"].lower():
            return False
        if contentious and "contentious" not in c["kind"].lower():
            return False
        return True

    filtered = [c for c in cases if keep(c)]
    return {
        "source_url": PENDING_URL if pending else LIST_ALL_URL,
        "fetched_at": entry.fetched_at,
        "count_total": len(cases),
        "count_returned": len(filtered),
        "cases": filtered,
    }


def search(query: str, *, force_refresh: bool = False) -> dict:
    """Substring search over case titles. Returns the same shape as list_all
    so the same printer can render it."""
    payload = list_all(force_refresh=force_refresh)
    q = query.lower()
    hits = [c for c in payload["cases"] if q in c["title"].lower()]
    return {
        "source_url": payload["source_url"],
        "fetched_at": payload["fetched_at"],
        "query": query,
        "count_total": payload["count_total"],
        "count_returned": len(hits),
        "cases": hits,
    }


# Section headings on a case page. Names exactly as they appear in the HTML.
# Anything mapped to "pleadings" or "verbatim" is dropped by default — those
# documents belong to a separate hearing-documents skill.
SECTION_BUCKETS = {
    "Institution of proceedings": "decision",
    "Orders": "decision",
    "Judgments": "decision",
    "Advisory opinions": "decision",
    "Summaries of Judgments and Orders": "decision",
    "Summaries of Advisory opinions": "decision",
    "Other documents": "decision",
    "Press releases": "decision",
    "Correspondence": "decision",
    "Written proceedings": "pleadings",
    "Oral proceedings": "verbatim",
}


def _walk_case_sections(main) -> list[dict]:
    """Walk H4 section headings inside the case page main content.

    Yield {section, items: [{label, url}]} preserving site order. The H4
    text matches the section names listed in SECTION_BUCKETS.
    """
    sections: list[dict] = []
    current: dict | None = None
    seen_urls: set[str] = set()
    # We iterate descendants and switch buckets when we hit an H4.
    for el in main.descendants:
        name = getattr(el, "name", None)
        if name == "h4":
            txt = el.get_text(" ", strip=True)
            current = {"section": txt, "items": []}
            sections.append(current)
            continue
        if current is None:
            continue
        if name == "a":
            href = el.get("href")
            if not href or not href.endswith(".pdf"):
                continue
            full = href if href.startswith("http") else urljoin(BASE, href)
            if full in seen_urls:
                continue
            seen_urls.add(full)
            label = el.get_text(" ", strip=True)
            current["items"].append({"label": label, "url": full})
    # Drop sections we don't have a known bucket for AND that have no items.
    return [s for s in sections if s["items"]]


# --- /case/<N> ----------------------------------------------------------

def show(case_id: int, *, force_refresh: bool = False,
         include_pleadings: bool = False) -> dict:
    """Return the metadata + decision-document URLs for a single case.

    Pleadings and verbatim records are excluded by default (this skill defers
    those to a separate hearing-documents skill). Pass include_pleadings=True
    to include them.

    Sections are detected by their H4 heading rather than by parsing PDF
    filenames — older cases use bare numeric IDs (e.g. 9615.pdf) while
    modern cases use the structured 070-19840510-ORD-01-00-EN.pdf scheme,
    so heading-based grouping is the only approach that works for both.
    """
    url = f"{BASE}/case/{case_id}"
    html, entry, _ = fetch_cached(url, force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    h1 = main.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None

    sections = _walk_case_sections(main)

    decision_sections: list[dict] = []
    pleading_sections: list[dict] = []
    unknown_sections: list[dict] = []
    for sec in sections:
        bucket = SECTION_BUCKETS.get(sec["section"])
        # Try to enrich each item with parsed filename metadata when possible.
        for it in sec["items"]:
            parsed = _parse_pdf_filename(it["url"])
            if parsed:
                it["date"] = parsed["date"]
                it["doc_type"] = parsed["doc_type"]
                it["lang"] = parsed["lang"]
        if bucket == "decision":
            decision_sections.append(sec)
        elif bucket in ("pleadings", "verbatim"):
            pleading_sections.append({**sec, "kind": bucket})
        else:
            unknown_sections.append(sec)

    pleadings_count = sum(len(s["items"]) for s in pleading_sections)
    decisions_count = sum(len(s["items"]) for s in decision_sections)

    payload = {
        "case_id": case_id,
        "url": url,
        "title": title,
        "fetched_at": entry.fetched_at,
        "decision_sections": decision_sections,
        "decision_documents_count": decisions_count,
        "pleadings_excluded_count": pleadings_count,
    }
    if include_pleadings:
        payload["pleadings_sections"] = pleading_sections
    if unknown_sections:
        payload["unknown_sections"] = unknown_sections
    return payload


# --- /decisions ---------------------------------------------------------

def recent(*, limit: int = 20, force_refresh: bool = False) -> dict:
    """Latest decisions across all cases (the /decisions page)."""
    html, entry, _ = fetch_cached(DECISIONS_URL, force_refresh=force_refresh)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    rows = main.find_all("div", class_="views-row")
    out = []
    for row in rows[:limit]:
        title_a = row.find("div", class_="views-field-field-document-long-title")
        case_a = row.find("div", class_="views-field-field-case-long-title")
        sub = row.find("div", class_="views-field-field-icj-document-subtitle")
        title_link = t