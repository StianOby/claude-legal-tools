"""
ICJ contentious + advisory cases.

Endpoints used:
  /index.php/list-of-all-cases   -> list_all()
  /index.php/pending-cases       -> list_all(pending=True)
  /index.php/decisions           -> recent()
  /case/<N>                      -> show(case_id): title + list of subpages
  /case/<N>/<section>            -> show(case_id): the documents of one section

Since the 2023 site redesign a case's documents are no longer listed on
/case/<N> itself but on per-section subpages such as /case/<N>/orders,
/case/<N>/judgments, /case/<N>/press-releases, /case/<N>/written-proceedings.
The set of subpages varies by case (advisory cases have
/request-advisory-opinion and /advisory-opinions; some have /intervention,
/provisional-measures, /discontinuance …), so show() reads the subpage links
from the case page and fetches each one.

Pleadings and verbatim records (written-proceedings, oral-proceedings,
oral-statements) are deliberately omitted from `show` output by default —
that's the responsibility of a separate skill for hearing documents.

Modern PDF names are uniform:
  /sites/default/files/case-related/<case_id>/<case_id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf
where <type> is jud, adv, ord, app, req, sum, pre (surfaced) or mem, cmem,
rep, rej, obs, wri, wso, cr (pleadings). Old cases use bare numeric file
names, so section membership is decided by the subpage, not the file name.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from _common import BASE, fetch_cached
from _html import Node, main_content, parse

LIST_ALL_URL = f"{BASE}/index.php/list-of-all-cases"
DECISIONS_URL = f"{BASE}/index.php/decisions"
PENDING_URL = f"{BASE}/index.php/pending-cases"


# Document types we expose. Anything else (mem, cmem, rep, rej, cr, ...)
# is treated as a pleading or verbatim record.
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

# Case subpages that hold pleadings / hearing records rather than decisions.
PLEADING_SUBPAGES = {
    "written-proceedings": "pleadings",
    "oral-proceedings": "verbatim",
    "oral-statements": "verbatim",
}

_DATE_IN_LABEL = re.compile(
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"
)


def _parse_pdf_filename(href: str) -> Optional[dict]:
    """Parse /sites/default/files/case-related/<id>/<id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf."""
    m = re.search(
        r"/case-related/(\d+)/\1-(\d{8})-([a-z]+)-(\d{2})-(\d{2})-([a-z]+)\.pdf$",
        href,
        re.IGNORECASE,
    )
    if not m:
        return None
    return {
        "case_id": int(m.group(1)),
        "date": f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:8]}",
        "doc_type": m.group(3).lower(),
        "serial": f"{m.group(4)}-{m.group(5)}",
        "lang": m.group(6).lower(),
        "url": href if href.startswith("http") else urljoin(BASE, href),
    }


# --- /list-of-all-cases and /pending-cases --------------------------------

def _parse_case_tables(main: Node) -> list[dict]:
    cases: list[dict] = []
    for table in main.find_all("table"):
        cap = table.find("caption")
        cap_year = cap.get_text() if cap else None
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            title_cell, intro_cell, conc_cell, kind_cell = cells[:4]
            link = title_cell.find("a")
            if not link or not link.get("href"):
                continue
            href = link["href"]
            m = re.search(r"(?:^|/)case/(\d+)", href)
            case_id = int(m.group(1)) if m else None
            cases.append(
                {
                    "case_id": case_id,
                    "title": title_cell.get_text(),
                    "year_introduced": intro_cell.get_text(),
                    "year_concluded": conc_cell.get_text(),
                    "kind": kind_cell.get_text().lstrip("﻿"),
                    "url": urljoin(BASE, href),
                    "table_year": cap_year,
                }
            )
    return cases


def _parse_pending(main: Node) -> list[dict]:
    """The pending-cases page is a plain list of links to /case/<N>.

    It carries no dates or case type, and /list-of-all-cases does NOT list
    pending cases at all, so the two pages are complementary. The kind is
    inferred from the title (contentious titles contain "v." or "/")."""
    cases: list[dict] = []
    seen: set[int] = set()
    for a in main.find_all("a"):
        href = a.get("href") or ""
        m = re.search(r"(?:^|/)case/(\d+)/?$", href)
        if not m:
            continue
        cid = int(m.group(1))
        title = a.get_text()
        if cid in seen or not title:
            continue
        seen.add(cid)
        contentious = bool(re.search(r"\bv\.\s|/", title))
        cases.append(
            {
                "case_id": cid,
                "title": title,
                "year_introduced": "",
                "year_concluded": "",
                "kind": "Contentious" if contentious else "Advisory",
                "kind_inferred": True,
                "url": urljoin(BASE, href),
                "table_year": None,
                "pending": True,
            }
        )
    return cases


def list_all(*, force_refresh: bool = False, year: Optional[int] = None,
             country: Optional[str] = None, advisory: bool = False,
             contentious: bool = False, pending: bool = False) -> dict:
    """List ICJ cases: the concluded ones from /list-of-all-cases (which
    carries years and case type) plus the pending ones from /pending-cases
    (which the former omits). Filters: --year, --country (substring of the
    title), --advisory, --contentious, --pending (pending cases only)."""
    html, entry, _ = fetch_cached(LIST_ALL_URL, force_refresh=force_refresh)
    concluded = _parse_case_tables(main_content(parse(html)))
    for c in concluded:
        c["pending"] = False
    p_html, p_entry, _ = fetch_cached(PENDING_URL, force_refresh=force_refresh)
    pending_cases = _parse_pending(main_content(parse(p_html)))
    known = {c["case_id"] for c in concluded}
    pending_cases = [c for c in pending_cases if c["case_id"] not in known]
    if pending:
        cases = pending_cases
        entry = p_entry
    else:
        cases = sorted(pending_cases + concluded,
                       key=lambda c: -(c["case_id"] or 0))

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
        "source_url": PENDING_URL if pending else f"{LIST_ALL_URL} + {PENDING_URL}",
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


# --- /case/<N> ----------------------------------------------------------

def _subpage_slugs(root: Node, case_id: int) -> list[str]:
    """The section subpages linked from a case page, in site order. The links
    sit in an <aside> tab bar outside <main>, so search the whole document."""
    slugs: list[str] = []
    pat = re.compile(rf"(?:^|/)case/{case_id}/([a-z-]+)/?$")
    for a in root.find_all("a"):
        m = pat.search(a.get("href") or "")
        if m and m.group(1) not in slugs:
            slugs.append(m.group(1))
    return slugs


def _parse_section_page(html: str) -> tuple[str, list[dict]]:
    """A subpage has one H4 (the section name) followed by PDF links."""
    main = main_content(parse(html))
    h4 = main.find("h4")
    section = h4.get_text() if h4 else ""
    items: list[dict] = []
    seen: set[str] = set()
    for a in main.find_all("a"):
        href = a.get("href") or ""
        if not href.lower().endswith(".pdf"):
            continue
        full = href if href.startswith("http") else urljoin(BASE, href)
        if full in seen:
            continue
        seen.add(full)
        label = a.get_text()
        item: dict = {"label": label, "url": full}
        parsed = _parse_pdf_filename(full)
        if parsed:
            item["date"] = parsed["date"]
            item["doc_type"] = parsed["doc_type"]
            item["lang"] = parsed["lang"]
        else:
            m = _DATE_IN_LABEL.search(label)
            if m:
                item["date"] = m.group(1)
        items.append(item)
    return section, items


def show(case_id: int, *, force_refresh: bool = False,
         include_pleadings: bool = False) -> dict:
    """Return the metadata + decision-document URLs for a single case.

    Reads the case page for the title and the list of section subpages, then
    fetches each subpage. Pleadings and verbatim records are excluded by
    default; pass include_pleadings=True to include them.
    """
    url = f"{BASE}/case/{case_id}"
    html, entry, _ = fetch_cached(url, force_refresh=force_refresh)
    root = parse(html)
    slugs = _subpage_slugs(root, case_id)
    main = main_content(root)
    h1 = main.find("h1")
    title = h1.get_text() if h1 else None

    decision_sections: list[dict] = []
    pleading_sections: list[dict] = []
    for slug in slugs:
        sub_url = f"{url}/{slug}"
        try:
            sub_html, _, _ = fetch_cached(sub_url, force_refresh=force_refresh)
        except RuntimeError as e:
            decision_sections.append({"section": slug, "url": sub_url, "items": [], "error": str(e)})
            continue
        section, items = _parse_section_page(sub_html)
        # Procedural sub-collections reuse the generic "Written proceedings"
        # heading; name them by their slug instead so the output is unambiguous.
        if slug in ("provisional-measures", "intervention", "discontinuance") or not section:
            section = slug.replace("-", " ").capitalize()
        rec = {"section": section, "slug": slug, "url": sub_url, "items": items}
        if slug in PLEADING_SUBPAGES:
            pleading_sections.append({**rec, "kind": PLEADING_SUBPAGES[slug]})
        else:
            decision_sections.append(rec)

    pleadings_count = sum(len(s["items"]) for s in pleading_sections)
    decisions_count = sum(len(s["items"]) for s in decision_sections)

    payload = {
        "case_id": case_id,
        "url": url,
        "title": title,
        "fetched_at": entry.fetched_at,
        "sections_found": slugs,
        "decision_sections": decision_sections,
        "decision_documents_count": decisions_count,
        "pleadings_excluded_count": pleadings_count,
    }
    if include_pleadings:
        payload["pleadings_sections"] = pleading_sections
    if not slugs:
        payload["warning"] = ("no section subpages found on the case page — the site layout "
                              "may have changed; open the URL in a browser")
    return payload


# --- /decisions ---------------------------------------------------------

def recent(*, limit: int = 20, force_refresh: bool = False) -> dict:
    """Latest decisions across all cases (the /decisions page)."""
    html, entry, _ = fetch_cached(DECISIONS_URL, force_refresh=force_refresh)
    main = main_content(parse(html))
    rows = main.find_all("div", class_="views-row")
    out = []
    for row in rows[:limit]:
        title_div = row.find("div", class_="views-field-field-document-long-title")
        case_div = row.find("div", class_="views-field-field-case-long-title")
        sub_div = row.find("div", class_="views-field-field-icj-document-subtitle")
        case_a = case_div.find("a") if case_div else None
        case_href = case_a.get("href") if case_a else ""
        m = re.search(r"(?:^|/)case/(\d+)", case_href or "")
        pdfs = []
        seen: set[str] = set()
        for a in row.find_all("a"):
            href = a.get("href") or ""
            if not href.lower().endswith(".pdf"):
                continue
            full = urljoin(BASE, href)
            if full in seen:
                continue
            seen.add(full)
            lang_text = a.get_text().lower()
            parsed = _parse_pdf_filename(full)
            lang = (parsed or {}).get("lang") or ("en" if "english" in lang_text else "fr" if "french" in lang_text else "")
            pdfs.append({"lang": lang, "url": full})
        first = pdfs[0]["url"] if pdfs else ""
        parsed = _parse_pdf_filename(first) if first else None
        out.append(
            {
                "decision_title": title_div.get_text() if title_div else "",
                "date": (parsed or {}).get("date"),
                "doc_type": (parsed or {}).get("doc_type"),
                "case_title": case_a.get_text() if case_a else "",
                "case_id": int(m.group(1)) if m else None,
                "case_url": urljoin(BASE, case_href) if case_href else None,
                "subtitle": sub_div.get_text() if sub_div else "",
                "pdfs": pdfs,
            }
        )
    return {
        "source_url": DECISIONS_URL,
        "fetched_at": entry.fetched_at,
        "count": len(out),
        "decisions": out,
    }
