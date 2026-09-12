#!/usr/bin/env python3
"""efta_court.py — fetch and search EFTA Court case law.

Self-contained CLI with no required third-party dependencies for the basic
flows. PDF text extraction uses `pypdf` if installed, otherwise the system
`pdftotext` binary, otherwise it falls back to writing only the PDF.

Cache layout (under the resolved cache dir):

  index.json                                   # all cases from WP REST API
  cases/<CASE>/raw.html                        # the source HTML of the detail page
  cases/<CASE>/meta.json                       # parsed metadata
  cases/<CASE>/summary.txt                     # human-readable summary
  cases/<CASE>/<doctype>-<lang>.pdf            # downloaded PDFs
  cases/<CASE>/<doctype>-<lang>.txt            # extracted text

All text files are written and read as UTF-8 regardless of the platform
locale, and writes are atomic (temp file + rename) so an interrupted run
never leaves a truncated file behind that later looks like a cache hit.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = "https://eftacourt.int"
REST = f"{BASE}/wp-json/wp/v2/cases"
USER_AGENT = "Mozilla/5.0 (efta-court-skill; +https://eftacourt.int/cases/)"
PROCEDURE_CODES = ("AO", "INF", "DA")
FIRST_YEAR = 1994  # the EFTA Court's first case is E-1/94

# ---------------------------------------------------------------------------
# Cache directory resolution

def cache_dir() -> Path:
    if env := os.environ.get("EFTA_COURT_CACHE_DIR"):
        p = Path(env)
    elif env := os.environ.get("XDG_CACHE_HOME"):
        p = Path(env) / "efta-court"
    elif sys.platform == "win32" and (la := os.environ.get("LOCALAPPDATA")):
        p = Path(la) / "efta-court"
    else:
        p = Path.home() / ".cache" / "efta-court"
    p.mkdir(parents=True, exist_ok=True)
    (p / "cases").mkdir(exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# UTF-8, atomic file helpers

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def _write_bytes(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def _has_content(p: Path) -> bool:
    """A cache file counts as present only if it is non-empty."""
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# HTTP

def _request(url: str, *, accept: str = "*/*", timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str) -> str:
    return _request(url, accept="text/html,application/xhtml+xml").decode("utf-8", errors="replace")


def fetch_json(url: str) -> Any:
    return json.loads(_request(url, accept="application/json"))


def download(url: str, dest: Path) -> Path:
    data = _request(url, accept="application/pdf,*/*", timeout=120)
    _write_bytes(dest, data)
    return dest


# ---------------------------------------------------------------------------
# Case-number normalisation
#
# Accepts: E-14/15, e14-15, E-08/26, 8/25, e 14/15, E0825, E-14/2015,
# and joined forms like "E-31/24+E-32/24" (first component wins; use
# all_case_numbers() to get every component).

_CASE_RE = re.compile(r"e?\s*-?\s*0*(\d+)\s*[-/_\s]\s*0*(\d+)", re.IGNORECASE)
# Compact form with no separator at all: E0825, E1415, E-0825 → number + 2-digit year
_COMPACT_RE = re.compile(r"^\s*e?\s*-?\s*(\d{1,2})(\d{2})\s*$", re.IGNORECASE)


def _two_digit_year(yr: int) -> int:
    """Accept 15, 2015, 94 or 1994 and return the 2-digit year."""
    return yr % 100


def full_year(yy: int) -> int:
    """Map a 2-digit case year to a 4-digit year (94–99 → 1990s)."""
    if yy >= 100:
        return yy
    return 1900 + yy if yy >= FIRST_YEAR % 100 else 2000 + yy


def normalise(case: str) -> str:
    """Return canonical form 'E-N/YY' (no leading zeros, 2-digit year)."""
    m = _CASE_RE.search(case)
    if m:
        n, yr = int(m.group(1)), int(m.group(2))
    else:
        m = _COMPACT_RE.match(case)
        if not m:
            raise ValueError(f"Cannot parse case number: {case!r}")
        n, yr = int(m.group(1)), int(m.group(2))
    return f"E-{n}/{_two_digit_year(yr):02d}"


def all_case_numbers(text: str) -> list[str]:
    """Every case number mentioned in a string, canonicalised, in order."""
    out: list[str] = []
    for m in _CASE_RE.finditer(text):
        c = f"E-{int(m.group(1))}/{_two_digit_year(int(m.group(2))):02d}"
        if c not in out:
            out.append(c)
    return out


def case_key(case_canonical: str) -> str:
    """Filesystem-safe key (used as cache subdirectory): 'E-14-15'."""
    return case_canonical.replace("/", "-")


def _is_plain_title(title: str) -> bool:
    """True for a WP title that is exactly one case number ('E-02/12'),
    False for 'E-02/12 INT', 'Joined Cases E-1/24 and E-7/24', etc."""
    return bool(re.fullmatch(r"\s*E-?\s*0*\d+\s*/\s*\d+\s*", title, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Index management

def index_path() -> Path:
    return cache_dir() / "index.json"


def load_index() -> dict | None:
    p = index_path()
    if not _has_content(p):
        return None
    try:
        return json.loads(_read(p))
    except json.JSONDecodeError:
        return None


def save_index(idx: dict) -> None:
    idx["verified_count"] = sum(1 for e in idx["cases"] if e.get("status"))
    _write(index_path(), json.dumps(idx, indent=2, ensure_ascii=False))


def update_index(verbose: bool = True) -> dict:
    """Pull all cases from the WP REST API and write index.json."""
    out: list[dict] = []
    page = 1
    while True:
        url = f"{REST}?per_page=100&page={page}&orderby=date&order=desc"
        if verbose:
            print(f"[update] fetching page {page} …", file=sys.stderr)
        try:
            batch = fetch_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 400:  # ran past the end
                break
            raise
        if not batch:
            break
        for c in batch:
            class_list = c.get("class_list", []) or []
            sources = [t.split("sources-", 1)[1] for t in class_list if t.startswith("sources-")]
            procs = [t.split("procedure_an_result-", 1)[1] for t in class_list if t.startswith("procedure_an_result-")]
            slug = c["slug"]
            title = html.unescape(c.get("title", {}).get("rendered", "") or "")
            numbers = all_case_numbers(title)
            if not numbers:
                try:
                    numbers = [_slug_to_case(slug)]
                except ValueError:
                    numbers = []
            out.append({
                "id": c["id"],
                "slug": slug,
                "url": c["link"],
                "date": c.get("date", "")[:10],
                "modified": c.get("modified", "")[:10],
                "case_number": numbers[0] if numbers else "",
                "case_numbers": numbers,
                "plain": _is_plain_title(title),
                "title_raw": title,
                "sources": sources,
                "procedure_codes": procs,
                "country": _country_from_sources(sources),
                "procedure": _procedure_from_codes(procs),
                # Authoritative status/parties come from the detail page and are
                # filled in lazily by fetch_case()/verify_recent_status().
                "status": None,
                "parties": "",
            })
        if len(batch) < 100:
            break
        page += 1

    # Carry over previously verified data so we don't re-fetch unchanged cases.
    if (existing := load_index()) is not None:
        prev = {c["slug"]: c for c in existing.get("cases", [])}
        for entry in out:
            old = prev.get(entry["slug"])
            if not old:
                continue
            for k in ("status", "parties"):
                if old.get(k):
                    entry[k] = old[k]
            for k in ("country", "procedure"):
                if not entry.get(k) and old.get(k):
                    entry[k] = old[k]

    data = {"fetched_at": _now_iso(), "total": len(out), "cases": out}
    save_index(data)
    if verbose:
        print(f"[update] wrote {len(out)} cases ({data['verified_count']} with verified status) → {index_path()}",
              file=sys.stderr)
    return data


def _apply_meta_to_entry(entry: dict, meta: dict) -> None:
    """Copy the authoritative fields from a parsed detail page into an index entry."""
    if meta.get("status") in ("Pending", "Decided"):
        entry["status"] = meta["status"]
    if meta.get("title"):
        entry["parties"] = meta["title"]
    if not entry.get("procedure") and meta.get("procedure_code"):
        entry["procedure"] = meta["procedure_code"]
    if not entry.get("country"):
        entry["country"] = _country_from_parties(meta.get("title", ""))


def verify_recent_status(years: int = 3, *, verbose: bool = True) -> dict:
    """For all cases from the last `years` years that don't have a verified
    status yet, fetch the detail page and read the authoritative `Status:`
    field. Persist into the index. Returns the updated index.

    This is the trustworthy way to know whether a case is Pending or Decided,
    because the /cases/pending/ listing page is JS-paginated and incomplete.
    Cases older than the window are assumed decided.
    """
    idx = load_index() or update_index(verbose=verbose)
    cutoff = datetime.now(timezone.utc).year - years
    candidates = [
        e for e in idx["cases"]
        if not e.get("status") and e["case_number"] and _case_year(e) >= cutoff
    ]
    # Anything older than the window: mark Decided without fetching. Failed or
    # unreadable pages stay unverified (status None) so a later run retries.
    for e in idx["cases"]:
        if not e.get("status") and e["case_number"] and _case_year(e) < cutoff:
            e["status"] = "Decided"
    if not candidates:
        save_index(idx)
        return idx
    if verbose:
        print(f"[verify] checking status of {len(candidates)} recent cases …", file=sys.stderr)
    for i, entry in enumerate(candidates, 1):
        try:
            meta = fetch_case(entry["case_number"], idx=idx, persist=False)
            _apply_meta_to_entry(entry, meta)
            if not entry.get("status") and verbose:
                print(f"[verify]   {entry['case_number']}: page has no Status field", file=sys.stderr)
        except Exception as e:  # network / parse errors: leave unverified
            if verbose:
                print(f"[verify]   {entry['case_number']} failed: {e}", file=sys.stderr)
        if verbose and i % 10 == 0:
            print(f"[verify]   {i}/{len(candidates)} …", file=sys.stderr)
    save_index(idx)
    if verbose:
        n_p = sum(1 for e in idx["cases"] if e.get("status") == "Pending")
        print(f"[verify] done — {n_p} pending out of {idx['verified_count']} verified", file=sys.stderr)
    return idx


_SLUG_RE = re.compile(r"^(?:case-)?e-?0*(\d+)-0*(\d+)")


def _slug_to_case(slug: str) -> str:
    m = _SLUG_RE.match(slug)
    if not m:
        raise ValueError(f"slug {slug!r} not in normal form")
    return f"E-{int(m.group(1))}/{int(m.group(2)):02d}"


def _country_from_parties(parties: str) -> str:
    """Infer the EFTA-State country from a party title.

    For INF actions the title is typically 'EFTA Surveillance Authority v
    The Kingdom of Norway' / 'v Iceland' / 'v Liechtenstein'. For DA actions
    the applicant might be a Norwegian/Icelandic/Liechtenstein-incorporated
    company, but that's harder to detect reliably from the title alone — we
    only return a country when we're confident.
    """
    p = parties.lower()
    if "norway" in p or "norge" in p:
        return "NO"
    if "iceland" in p or "ísland" in p or "island" in p:
        return "IS"
    if "liechtenstein" in p:
        return "LI"
    return ""


def _country_from_sources(sources: list[str]) -> str:
    s = " ".join(sources).lower()
    if any(k in s for k in ("norges", "borgarting", "agder", "frostating", "gulating", "hålogaland", "halogaland", "norsk", "norwegian", "norway")):
        return "NO"
    if any(k in s for k in ("liechtenstein", "fürstentum", "furstentum", "vaduz")):
        return "LI"
    if any(k in s for k in ("island", "iceland", "héraðsdómur", "heradsdomur", "landsréttur", "landsrettur", "hæstirétt", "haestirett", "reykjavik", "reykjavík")):
        return "IS"
    return ""


def _procedure_from_page(page_type: str, procedure_text: str, parties: str) -> str:
    """Derive AO/INF/DA from a detail page. The page's own "Type" field is
    not reliable (ESA v Norway infringement actions are tagged "DA"), so
    prefer the Procedure text, then the shape of the party names, and use
    Type only as a last resort.
    """
    proc = procedure_text.lower()
    if "advisory" in proc:
        return "AO"
    if "infringement" in proc or "fulfil" in proc:
        return "INF"
    if "annulment" in proc or "failure to act" in proc:
        return "DA"
    p = parties.lower()
    if p.startswith("efta surveillance authority v"):
        return "INF"
    if p.endswith("v efta surveillance authority"):
        return "DA"
    return page_type if page_type in PROCEDURE_CODES else ""


def _procedure_from_codes(codes: list[str]) -> str:
    s = " ".join(codes).lower()
    if "advisory" in s or "preliminary" in s:
        return "AO"
    if "fulfil" in s or "infringement" in s:
        return "INF"
    if "annulment" in s or "failure-to-act" in s:
        return "DA"
    return ""


# ---------------------------------------------------------------------------
# Case page fetch + parse

def _resolve_entry(case_canonical: str, idx: dict) -> dict:
    """Find the index entry for a canonical case number.

    Several pages can share a case number (main case, '… INT', '… costs',
    joined-cases pages). Preference order: a page whose WP title is exactly
    the case number, then the shortest slug (so 'e-15-10' beats
    'e-15-10-costs'). A joined-cases page is used only when no page for the
    single case exists, e.g. for the second component of a joined case.
    """
    exact = [e for e in idx["cases"] if e["case_number"] == case_canonical]
    if exact:
        exact.sort(key=lambda e: (not e.get("plain"), len(e["slug"])))
        return exact[0]
    member = [e for e in idx["cases"] if case_canonical in e.get("case_numbers", [])]
    if member:
        member.sort(key=lambda e: len(e["slug"]))
        return member[0]
    # Last resort: number+year somewhere in the slug, with or without hyphen
    # ('e-2725', 'joined-cases-e-1-24-and-e-7-24').
    n, yr = case_canonical.removeprefix("E-").split("/")
    needle = re.compile(rf"(?<!\d)0*{int(n)}-?0*{int(yr):02d}(?!\d)")
    matches = [e for e in idx["cases"] if needle.search(e["slug"])]
    if matches:
        matches.sort(key=lambda e: len(e["slug"]))
        return matches[0]
    raise SystemExit(f"Case {case_canonical} not in index. Try `update`.")


def fetch_case(case: str, force: bool = False, *, idx: dict | None = None, persist: bool = True) -> dict:
    canonical = normalise(case)
    if idx is None:
        idx = load_index() or update_index()
    entry = _resolve_entry(canonical, idx)
    cdir = cache_dir() / "cases" / case_key(canonical)
    raw_p = cdir / "raw.html"
    if force or not _has_content(raw_p):
        _write(raw_p, fetch_text(entry["url"]))
    meta = parse_case_html(_read(raw_p), canonical=canonical, entry=entry)
    _write(cdir / "meta.json", json.dumps(meta, indent=2, ensure_ascii=False))
    _write(cdir / "summary.txt", _summary(meta))
    # Feed status / parties / country / procedure back into the index so
    # list/search filters improve with every page fetched.
    _apply_meta_to_entry(entry, meta)
    if persist:
        save_index(idx)
    return meta


_LABEL_RE = re.compile(
    r'<span[^>]*c-case-meta-type[^>]*>\s*([^<]+?)\s*:\s*</span>\s*(?:<br\s*/?>)?\s*([^<]*)',
    re.IGNORECASE,
)
# Single-case page: two consecutive <h2> tags — first is the case number, second is the parties.
_TITLE_RE = re.compile(r'<h2[^>]*>\s*(E-\d+/\d+[^<]*?)\s*</h2>\s*<h2[^>]*>\s*(.*?)\s*</h2>', re.DOTALL)
# Joined-case page: single <h2 class="p-cases-title-first"> with "Joined Cases E-X/YY and E-Z/YY – PARTIES"
_JOINED_TITLE_RE = re.compile(
    r'<h2[^>]*p-cases-title-first[^>]*>\s*(.*?)\s*</h2>',
    re.DOTALL,
)
_DOCS_BLOCK_RE = re.compile(r'<h2[^>]*>\s*Documents:\s*</h2>(.*?)(?=<h2|<main|</main)', re.IGNORECASE | re.DOTALL)
_DOC_LINK_RE = re.compile(
    r'<a[^>]*href="([^"]+/download/[^"]+\?wpdmdl=\d+)"[^>]*>\s*(.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
# "About this case" = one or more <p> blocks, followed by the procedural
# timeline (div.o-cont-cases-tl blocks), then the page footer. Stop at the
# first timeline block, the next <h2>, or the end of <main>.
_ABOUT_RE = re.compile(
    r'<h2[^>]*>\s*About this case[^<]*</h2>(.*?)(?=<div[^>]*o-cont-cases-tl|<h2|</main|<footer|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_TIMELINE_RE = re.compile(
    r'<div[^>]*o-cont-cases-tl[^>]*>(.*?)</div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
_TL_DATE_RE = re.compile(r'(\d{1,2}/\d{1,2}/\d{4})')
_P_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)


def _strip_html(s: str) -> str:
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def _paragraphs(fragment: str) -> list[str]:
    paras = [_strip_html(p) for p in _P_RE.findall(fragment)]
    paras = [p for p in paras if p]
    return paras or ([_strip_html(fragment)] if _strip_html(fragment) else [])


def parse_case_html(raw: str, canonical: str, entry: dict) -> dict:
    # Title (parties). Joined cases use a single combined H2; single cases use two H2s.
    parties = ""
    if m := _TITLE_RE.search(raw):
        parties = _strip_html(m.group(2))
    elif m := _JOINED_TITLE_RE.search(raw):
        # Strip leading "Joined Cases E-X/YY and E-Z/YY – " (en-dash or hyphen)
        full = _strip_html(m.group(1))
        parties = re.sub(r'^Joined Cases\s+E-[\d/]+(\s*(,|and)\s*E-[\d/]+)*\s*[–—\-]\s*', '', full)

    # Meta labels
    fields: dict[str, str] = {}
    for label, value in _LABEL_RE.findall(raw):
        key = label.strip().lower().replace(" ", "_")
        fields[key] = _strip_html(value)

    # About: keyword line + description paragraphs, without the timeline/footer
    about = ""
    if m := _ABOUT_RE.search(raw):
        about = "\n".join(_paragraphs(m.group(1)))

    # Procedural timeline (dated events on the case page)
    timeline: list[dict] = []
    for block in _TIMELINE_RE.findall(raw):
        text = _strip_html(block)
        dm = _TL_DATE_RE.search(text)
        date = dm.group(1) if dm else ""
        event = text.replace(date, "", 1).strip() if date else text
        if event:
            timeline.append({"date": date, "event": event})

    # Documents
    documents: list[dict] = []
    if block_m := _DOCS_BLOCK_RE.search(raw):
        for url, label in _DOC_LINK_RE.findall(block_m.group(1)):
            text = _strip_html(label)
            documents.append({
                "label": text,
                "url": html.unescape(url),
                **_parse_doc_label(text),
            })

    page_type = fields.get("type", "")
    procedure_code = _procedure_from_page(page_type, fields.get("procedure", ""), parties) or entry.get("procedure", "")
    status = fields.get("status") or entry.get("status") or "Unknown"

    return {
        "case_number": canonical,
        "title": parties,
        "url": entry["url"],
        "slug": entry["slug"],
        "status": status,
        "type": page_type,
        "procedure_code": procedure_code,
        "language_of_request": fields.get("language_of_the_request", ""),
        "date_submitted": fields.get("date_submitted", ""),
        "hearing_date": fields.get("hearing_date", ""),
        "judgment_date": fields.get("judgment_date", ""),
        "procedure": fields.get("procedure", ""),
        "source_court": ", ".join(entry.get("sources", [])).replace("-", " ").title() if entry.get("sources") else "",
        "country": entry.get("country") or _country_from_parties(parties),
        "about": about,
        "timeline": timeline,
        "documents": documents,
        "fetched_at": _now_iso(),
    }


# Document labels look like:
#   "14/15 Judgment 19/04/2016 EN"
#   "8/26 Notification 06/05/2026 EN"
#   "8/26 Request AO 06/05/2026 NO"
_DOC_LABEL_RE = re.compile(
    r'^(?P<num>\d+/\d+)\s+'
    r'(?P<type>.+?)\s+'
    r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
    r'(?P<lang>[A-Z]{2,3})$'
)
_DOC_TYPE_NORMAL = {
    "judgment": "judgment",
    "advisory opinion": "advisory-opinion",
    "order": "order",
    "costs order": "costs-order",
    "request ao": "request",
    "request": "request",
    "notification": "notification",
    "summary of the request": "summary",
    "report for the hearing": "report",
    "opinion of the advocate general": "opinion-aag",
    "opinion": "opinion",
}


def _parse_doc_label(label: str) -> dict:
    m = _DOC_LABEL_RE.match(label)
    if not m:
        return {"type": "", "date": "", "lang": ""}
    raw_type = m.group("type").strip().lower()
    return {
        "type": _DOC_TYPE_NORMAL.get(raw_type, raw_type),
        "date": m.group("date"),
        "lang": m.group("lang").upper(),
    }


def _summary(meta: dict) -> str:
    lines = [
        f"{meta['case_number']} — {meta['title']}",
        "=" * 70,
        f"Status:       {meta['status']}",
        f"Type:         {meta['type']}",
        f"Procedure:    {meta['procedure'] or meta.get('procedure_code', '')}",
        f"Source court: {meta['source_court']} ({meta['country']})",
        f"Submitted:    {meta['date_submitted']}",
        f"Hearing:      {meta['hearing_date'] or '-'}",
        f"Judgment:     {meta['judgment_date'] or '-'}",
        f"URL:          {meta['url']}",
        "",
        "About:",
        meta["about"] or "(no description)",
        "",
    ]
    if meta.get("timeline"):
        lines.append("Timeline:")
        for t in meta["timeline"]:
            lines.append(f"  {t['date'] or '          ':10}  {t['event']}")
        lines.append("")
    lines.append("Documents:")
    for d in meta["documents"]:
        lines.append(f"  - [{d.get('lang','??'):2}] {d.get('type',''):12} {d.get('date',''):10}  {d['url']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Get a specific document

def get_document(case: str, doc_type: str | None, lang: str) -> tuple[Path, Path | None]:
    canonical = normalise(case)
    meta = fetch_case(canonical)
    docs = meta["documents"]
    if not docs:
        raise SystemExit(f"No documents listed on the case page for {canonical}.")
    chosen = _choose_doc(docs, doc_type, lang)
    if not chosen:
        avail = ", ".join(f"{d.get('type') or d.get('label') or '?'}({d.get('lang') or '?'})" for d in docs)
        raise SystemExit(f"No matching document. Available: {avail}")
    cdir = cache_dir() / "cases" / case_key(canonical)
    stem = chosen.get("type") or re.sub(r"[^a-z0-9]+", "-", chosen.get("label", "doc").lower()).strip("-") or "doc"
    pdf_p = cdir / f"{stem}-{chosen.get('lang') or 'XX'}.pdf"
    if not _has_content(pdf_p):
        download(chosen["url"], pdf_p)
    txt_p = pdf_p.with_suffix(".txt")
    if not _has_content(txt_p):
        text = extract_pdf_text(pdf_p)
        if text:
            _write(txt_p, text)
        else:
            txt_p = None
    return pdf_p, txt_p


def _norm_type(s: str) -> str:
    """Normalize a document type string: lowercase, collapse hyphens/underscores to spaces."""
    return re.sub(r'[-_]+', ' ', s.lower().strip())


def _choose_doc(docs: list[dict], doc_type: str | None, lang: str) -> dict | None:
    lang = lang.upper()
    candidates = docs
    if doc_type:
        dt = _norm_type(doc_type)
        # Substring match in both directions so 'advisory opinion' matches 'advisory-opinion' etc.
        candidates = [d for d in docs if dt in _norm_type(d.get("type", "")) or _norm_type(d.get("type", "")) in dt]
    # prefer requested language, then EN, then anything
    for L in (lang, "EN"):
        for d in candidates:
            if d.get("lang", "").upper() == L:
                return d
    return candidates[0] if candidates else None


def extract_pdf_text(pdf: Path) -> str | None:
    # Try pypdf first
    try:
        from pypdf import PdfReader  # type: ignore
    except ModuleNotFoundError:
        PdfReader = None  # type: ignore
    if PdfReader is not None:
        try:
            reader = PdfReader(str(pdf))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            if text.strip():
                return text
        except Exception as e:  # corrupt / encrypted PDF — try the next backend
            print(f"[pdf] pypdf failed on {pdf.name}: {e}", file=sys.stderr)
    # Fall back to pdftotext binary
    if shutil.which("pdftotext"):
        out = pdf.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(pdf), str(out)], check=False)
        if _has_content(out):
            return _read(out)
    return None


# ---------------------------------------------------------------------------
# List / search

def _year_arg(y: int | None) -> int | None:
    """Accept 2024 or 24 and return a 4-digit year."""
    return None if y is None else full_year(y)


def _case_year(r: dict) -> int:
    """4-digit year of a case (from the case number, else the page date)."""
    if r["case_number"]:
        return full_year(int(r["case_number"].split("/")[-1]))
    return int(r["date"][:4])


def _case_num(r: dict) -> int:
    if r["case_number"]:
        return int(r["case_number"].removeprefix("E-").split("/")[0])
    return 0


def _sort_key(r: dict):
    return (-_case_year(r), -_case_num(r), len(r["slug"]))


def _filter_rows(rows: list[dict], year: int | None, country: str | None, procedure: str | None) -> list[dict]:
    if year:
        rows = [r for r in rows if _case_year(r) == year]
    dropped = 0
    if country:
        c = country.upper()
        dropped += sum(1 for r in rows if not r.get("country"))
        rows = [r for r in rows if r.get("country") == c]
    if procedure:
        p = procedure.upper()
        dropped += sum(1 for r in rows if not r.get("procedure"))
        rows = [r for r in rows if r.get("procedure") == p]
    if dropped:
        print(f"[note] {dropped} case(s) skipped because their country/procedure is not yet known — "
              "the REST index only tags advisory opinions; run `list --decided` (verifies recent pages) "
              "or `fetch` individual cases to fill the gaps.", file=sys.stderr)
    return rows


def cmd_list(args: argparse.Namespace) -> None:
    idx = load_index() or update_index()
    # When the user filters by status, verify all recent cases first — the index
    # alone can't be trusted for pending/decided (see verify_recent_status docstring).
    if args.pending or args.decided:
        idx = verify_recent_status(years=args.verify_years, verbose=True)
    rows = _filter_rows(idx["cases"], _year_arg(args.year), args.country, args.procedure)
    if args.pending:
        rows = [r for r in rows if r.get("status") == "Pending"]
    if args.decided:
        rows = [r for r in rows if r.get("status") == "Decided"]
    rows.sort(key=_sort_key)
    if args.limit:
        rows = rows[: args.limit]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    for r in rows:
        flag = {"Pending": "P", "Decided": "D"}.get(r.get("status") or "", "?")
        print(f"{flag} {r['case_number'] or r['slug']:10}  "
              f"{r.get('country') or '--':2}  "
              f"{r.get('procedure') or '--':3}  "
              f"{r['date']}  {r['url']}"
              + (f"  {r['parties']}" if r.get("parties") else ""))


def cmd_search(args: argparse.Namespace) -> None:
    idx = load_index() or update_index()
    rows = _filter_rows(idx["cases"], _year_arg(args.year), args.country, None)
    q = args.query.lower()
    hits: list[tuple[dict, str]] = []
    for r in rows:
        cdir = cache_dir() / "cases" / case_key(r["case_number"]) if r["case_number"] else None
        meta = None
        if cdir and _has_content(cdir / "meta.json"):
            try:
                meta = json.loads(_read(cdir / "meta.json"))
            except Exception:
                meta = None
        title = (meta or {}).get("title") or r.get("parties") or ""
        about = (meta or {}).get("about", "")
        if args.party_only:
            haystack = title.lower()
        else:
            haystack = " | ".join([r["case_number"], r["slug"], r.get("title_raw", ""), title, about,
                                   " ".join(r.get("sources", []))]).lower()
        snippet = ""
        if q in haystack:
            snippet = title or about[:120]
        elif args.full_text and cdir and not args.party_only:
            for txt in cdir.glob("*.txt"):
                try:
                    body = _read(txt).lower()
                except Exception:
                    continue
                if q in body:
                    i = body.find(q)
                    snippet = "…" + body[max(0, i - 60): i + 120].replace("\n", " ") + "…"
                    break
        if snippet:
            hits.append((r, snippet))
    hits.sort(key=lambda x: _sort_key(x[0]))
    if args.json:
        print(json.dumps([{"case": r, "snippet": s} for r, s in hits], indent=2, ensure_ascii=False))
        return
    if not hits:
        print(
            f"No hits for {args.query!r} in local cache.\n"
            "Party names, subject keywords and full text only match cases whose detail page has been "
            "fetched (by `fetch`, `get`, or the verification pass of `list --pending/--decided`).\n"
            "Workflow: `list --decided --limit 100` → identify candidates → `fetch E-X/YY` each → "
            "re-run search with --full-text.",
            file=sys.stderr,
        )
        return
    for r, snippet in hits:
        flag = {"Pending": "P", "Decided": "D"}.get(r.get("status") or "", "?")
        print(f"{flag} {r['case_number'] or r['slug']:10}  {r['date']}  {snippet}")


def cmd_fetch(args: argparse.Namespace) -> None:
    meta = fetch_case(args.case, force=args.refresh)
    if args.json:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print(_summary(meta))
        cdir = cache_dir() / "cases" / case_key(meta["case_number"])
        print(f"\n(cached at {cdir})")


def cmd_get(args: argparse.Namespace) -> None:
    pdf, txt = get_document(args.case, args.type, args.lang)
    print(f"PDF:  {pdf}")
    if txt:
        print(f"TEXT: {txt}")
    else:
        print("TEXT: (extraction failed — install pypdf or poppler-utils)")


def cmd_update(args: argparse.Namespace) -> None:
    update_index(verbose=True)


def cmd_status(args: argparse.Namespace) -> None:
    cdir = cache_dir()
    print(f"cache dir:   {cdir}")
    idx = load_index()
    if idx is None:
        print("index:       (none — run `update`)")
        return
    print(f"index:       {idx['total']} cases (fetched {idx['fetched_at']})")
    n_pending = sum(1 for c in idx["cases"] if c.get("status") == "Pending")
    n_verified = idx.get("verified_count", sum(1 for c in idx["cases"] if c.get("status")))
    print(f"verified:    {n_verified} of {idx['total']} ({n_pending} pending)")
    n_cached = sum(1 for p in (cdir / "cases").glob("*/meta.json") if _has_content(p))
    n_pdfs = sum(1 for p in (cdir / "cases").glob("*/*.pdf") if _has_content(p))
    print(f"detail pages cached: {n_cached}")
    print(f"PDFs cached:         {n_pdfs}")


# ---------------------------------------------------------------------------
# CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="efta-court",
        description="Lookup and fetch EFTA Court case law from eftacourt.int.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("update", help="Refresh the local case index from the EFTA Court REST API.")
    sub.add_parser("status", help="Show cache location and freshness.")

    pl = sub.add_parser("list", help="List cases, with filters.")
    pl.add_argument("--year", type=int, help="Filter by year (2-digit or 4-digit, e.g. 2024 or 24).")
    pl.add_argument("--country", help="Filter by EFTA State (NO/IS/LI): referring court for AOs, defendant for ESA actions.")
    pl.add_argument("--procedure", help="Filter by procedure type (AO/INF/DA).")
    pl.add_argument("--pending", action="store_true",
                    help="Only pending cases. Triggers status verification of recent cases (cached).")
    pl.add_argument("--decided", action="store_true",
                    help="Only decided cases. Triggers status verification of recent cases (cached).")
    pl.add_argument("--verify-years", type=int, default=3,
                    help="When verifying status, look back this many years (default: 3).")
    pl.add_argument("--limit", type=int, default=50)
    pl.add_argument("--json", action="store_true")

    ps = sub.add_parser("search", help="Search local index and cached case pages (run `fetch` to enrich).")
    ps.add_argument("query")
    ps.add_argument("--year", type=int)
    ps.add_argument("--country")
    ps.add_argument("--full-text", action="store_true",
                    help="Also search inside extracted PDF text (only works on cases already fetched).")
    ps.add_argument("--party-only", action="store_true",
                    help="Match only against the parties (case title), not the About text, slug or sources.")
    ps.add_argument("--json", action="store_true")

    pf = sub.add_parser("fetch", help="Fetch a case page; parse and cache its metadata + document list.")
    pf.add_argument("case", help="Case number in any form (e.g. E-14/15, e14-15, 8/25, E0825).")
    pf.add_argument("--refresh", action="store_true", help="Re-download even if cached.")
    pf.add_argument("--json", action="store_true")

    pg = sub.add_parser("get", help="Download a specific document PDF and extract text.")
    pg.add_argument("case")
    pg.add_argument("--type", help="judgment, order, request, notification, opinion-aag, etc.")
    pg.add_argument("--lang", default="EN")

    return p


def main(argv: list[str] | None = None) -> int:
    # Case titles and About text contain characters outside cp1252; never let
    # the console encoding turn a successful fetch into a crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    handlers = {
        "update": cmd_update,
        "status": cmd_status,
        "list":   cmd_list,
        "search": cmd_search,
        "fetch":  cmd_fetch,
        "get":    cmd_get,
    }
    try:
        handlers[args.cmd](args)
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"Network error talking to eftacourt.int: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
