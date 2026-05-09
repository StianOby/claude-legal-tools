#!/usr/bin/env python3
"""efta_court.py — fetch and search EFTA Court case law.

Self-contained CLI with no required third-party dependencies for the basic
flows. PDF text extraction uses `pypdf` if installed, otherwise the system
`pdftotext` binary, otherwise it falls back to writing only the PDF.

Cache layout (under the resolved cache dir):

  index.json                                   # all cases from WP REST API
  pending.json                                 # case numbers known to be pending
  cases/<CASE>/raw.html                        # the source HTML of the detail page
  cases/<CASE>/meta.json                       # parsed metadata
  cases/<CASE>/summary.txt                     # human-readable summary
  cases/<CASE>/<doctype>-<lang>.pdf            # downloaded PDFs
  cases/<CASE>/<doctype>-<lang>.txt            # extracted text
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BASE = "https://eftacourt.int"
REST = f"{BASE}/wp-json/wp/v2/cases"
USER_AGENT = "Mozilla/5.0 (efta-court-skill; +https://eftacourt.int/cases/)"

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
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = _request(url, accept="application/pdf,*/*")
    dest.write_bytes(data)
    return dest


# ---------------------------------------------------------------------------
# Case-number normalisation
#
# Accepts: E-14/15, e14-15, E-08/26, 8/25, e 14/15, E0825, joined "E-31/24+E-32/24"

_CASE_RE = re.compile(r"e?\s*-?\s*0*(\d+)\s*[-/_\s]\s*0*(\d+)", re.IGNORECASE)


def normalise(case: str) -> str:
    """Return canonical form 'E-N/YY' (no leading zeros)."""
    m = _CASE_RE.search(case)
    if not m:
        raise ValueError(f"Cannot parse case number: {case!r}")
    n, yr = int(m.group(1)), int(m.group(2))
    return f"E-{n}/{yr:02d}"


def case_key(case_canonical: str) -> str:
    """Filesystem-safe key (used as cache subdirectory): 'E-14-15'."""
    return case_canonical.replace("/", "-")


# ---------------------------------------------------------------------------
# Index management

def index_path() -> Path:
    return cache_dir() / "index.json"


def load_index() -> dict | None:
    p = index_path()
    if not p.exists():
        return None
    return json.loads(p.read_text())


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
            # Try to back out the canonical case number from the WP title
            title = html.unescape(c.get("title", {}).get("rendered", "") or "")
            try:
                canonical = normalise(title) if title else _slug_to_case(slug)
            except ValueError:
                try:
                    canonical = _slug_to_case(slug)
                except ValueError:
                    canonical = ""  # joined cases etc.
            out.append({
                "id": c["id"],
                "slug": slug,
                "url": c["link"],
                "date": c.get("date", "")[:10],
                "modified": c.get("modified", "")[:10],
                "case_number": canonical,
                "title_raw": title,
                "sources": sources,
                "procedure_codes": procs,
                "country": _country_from_sources(sources),
                "procedure": _procedure_from_codes(procs),
            })
        if len(batch) < 100:
            break
        page += 1

    # NOTE: We deliberately do NOT mark pending status here. The /cases/pending/
    # listing page is JS-paginated and only returns the first batch of slugs, so
    # using it as the source of truth misses recently-filed cases. Authoritative
    # status comes from the per-case detail page's "Status:" field, populated
    # lazily by verify_recent_status() the first time `list --pending` or
    # `list --decided` runs (and cached in the index thereafter).
    for entry in out:
        entry["status"] = None

    # Carry over previously-verified statuses so we don't re-fetch unchanged cases.
    if (existing := load_index()) is not None:
        prev = {c["slug"]: c.get("status") for c in existing.get("cases", [])}
        for entry in out:
            if entry["slug"] in prev and prev[entry["slug"]]:
                entry["status"] = prev[entry["slug"]]

    data = {
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total": len(out),
        "verified_count": sum(1 for e in out if e["status"]),
        "cases": out,
    }
    index_path().write_text(json.dumps(data, indent=2, ensure_ascii=False))
    if verbose:
        print(f"[update] wrote {len(out)} cases ({data['verified_count']} with verified status) → {index_path()}",
              file=sys.stderr)
    return data


def verify_recent_status(years: int = 3, *, verbose: bool = True) -> dict:
    """For all cases from the last `years` years that don't have a verified
    status yet, fetch the detail page and read the authoritative `Status:`
    field. Persist into the index. Returns the updated index.

    This is the trustworthy way to know whether a case is Pending or Decided,
    because the /cases/pending/ listing page is JS-paginated and incomplete.
    """
    idx = load_index() or update_index(verbose=verbose)
    today = datetime.utcnow()
    cutoff_yy = (today.year - years) % 100  # 2-digit year
    candidates = [
        e for e in idx["cases"]
        if e.get("status") in (None, "")
        and (e["case_number"] and _case_year(e) >= cutoff_yy)
    ]
    if not candidates:
        return idx
    if verbose:
        print(f"[verify] checking status of {len(candidates)} recent cases …", file=sys.stderr)
    for i, entry in enumerate(candidates, 1):
        try:
            meta = fetch_case(entry["case_number"])
            entry["status"] = meta.get("status") or "Decided"
            # Backfill country for INF / DA cases where the index has no
            # `sources-*` taxonomy (those only exist for AO cases referred by
            # a national court). For ESA actions the defendant country lives
            # in the parties title.
            if not entry.get("country"):
                entry["country"] = _country_from_parties(meta.get("title", ""))
        except Exception as e:
            if verbose:
                print(f"[verify]   {entry['case_number']} failed: {e}", file=sys.stderr)
            entry["status"] = "Unknown"
        if verbose and i % 10 == 0:
            print(f"[verify]   {i}/{len(candidates)} …", file=sys.stderr)
    idx["verified_count"] = sum(1 for e in idx["cases"] if e.get("status"))
    index_path().write_text(json.dumps(idx, indent=2, ensure_ascii=False))
    if verbose:
        n_p = sum(1 for e in idx["cases"] if e.get("status") == "Pending")
        print(f"[verify] done — {n_p} pending out of {idx['verified_count']} verified", file=sys.stderr)
    return idx


_SLUG_RE = re.compile(r"^e-?0*(\d+)-0*(\d+)$")


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

def _resolve_entry(case_canonical: str) -> dict:
    idx = load_index()
    if idx is None:
        idx = update_index()
    for e in idx["cases"]:
        if e["case_number"] == case_canonical:
            return e
    # joined cases or non-canonical: search by slug containing year+number
    n, yr = case_canonical.removeprefix("E-").split("/")
    needle = f"{int(n)}-{int(yr):02d}"
    for e in idx["cases"]:
        if needle in e["slug"]:
            return e
    raise SystemExit(f"Case {case_canonical} not in index. Try `update`.")


def fetch_case(case: str, force: bool = False) -> dict:
    canonical = normalise(case)
    entry = _resolve_entry(canonical)
    cdir = cache_dir() / "cases" / case_key(canonical)
    cdir.mkdir(parents=True, exist_ok=True)
    raw_p = cdir / "raw.html"
    if force or not raw_p.exists():
        raw_p.write_text(fetch_text(entry["url"]))
    meta = parse_case_html(raw_p.read_text(), canonical=canonical, entry=entry)
    (cdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    (cdir / "summary.txt").write_text(_summary(meta))
    return meta


_LABEL_RE = re.compile(
    r'<span[^>]*c-case-meta-type[^>]*>\s*([^<]+?)\s*:\s*</span>\s*(?:<br\s*/?>)?\s*([^<]*)',
    re.IGNORECASE,
)
# Single-case page: two consecutive <h2> tags — first is the case number, second is the parties.
_TITLE_RE = re.compile(r'<h2[^>]*>\s*(E-\d+/\d+)\s*</h2>\s*<h2[^>]*>\s*(.*?)\s*</h2>', re.DOTALL)
# Joined-case page: single <h2 class="p-cases-title-first"> with "Joined Cases E-X/YY and E-Z/YY – PARTIES"
_JOINED_TITLE_RE = re.compile(
    r'<h2[^>]*p-cases-title-first[^>]*>\s*(.*?)\s*</h2>',
    re.DOTALL,
)
_DOCS_BLOCK_RE = re.compile(r'<h2[^>]*>\s*Documents:\s*</h2>(.*?)(?=<h2|<main)', re.IGNORECASE | re.DOTALL)
_DOC_LINK_RE = re.compile(
    r'<a[^>]*href="([^"]+/download/[^"]+\?wpdmdl=\d+)"[^>]*>\s*(.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
_ABOUT_RE = re.compile(
    r'<h2[^>]*>\s*About this case[^<]*</h2>\s*<div>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_html(s: str) -> str:
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).strip()


def parse_case_html(raw: str, canonical: str, entry: dict) -> dict:
    # Title (parties). Joined cases use a single combined H2; single cases use two H2s.
    parties = ""
    if m := _TITLE_RE.search(raw):
        parties = _strip_html(m.group(2))
    elif m := _JOINED_TITLE_RE.search(raw):
        # Strip leading "Joined Cases E-X/YY and E-Z/YY – " (en-dash or hyphen)
        full = _strip_html(m.group(1))
        parties = re.sub(r'^Joined Cases\s+E-[\d/]+(\s+and\s+E-[\d/]+)*\s*[–—\-]\s*', '', full)

    # Meta labels
    fields: dict[str, str] = {}
    for label, value in _LABEL_RE.findall(raw):
        key = label.strip().lower().replace(" ", "_")
        fields[key] = _strip_html(value)

    # About
    about = ""
    m = _ABOUT_RE.search(raw)
    if m:
        about = _strip_html(m.group(1))

    # Documents
    documents: list[dict] = []
    block_m = _DOCS_BLOCK_RE.search(raw)
    if block_m:
        block = block_m.group(1)
        for url, label in _DOC_LINK_RE.findall(block):
            text = _strip_html(label)
            documents.append({
                "label": text,
                "url": html.unescape(url),
                **_parse_doc_label(text),
            })

    return {
        "case_number": canonical,
        "title": parties,
        "url": entry["url"],
        "slug": entry["slug"],
        "status": fields.get("status", entry.get("status") or "Unknown"),
        "type": fields.get("type", ""),
        "language_of_request": fields.get("language_of_the_request", ""),
        "date_submitted": fields.get("date_submitted", ""),
        "hearing_date": fields.get("hearing_date", ""),
        "judgment_date": fields.get("judgment_date", ""),
        "procedure": fields.get("procedure", entry.get("procedure", "")),
        "source_court": ", ".join(entry.get("sources", [])).replace("-", " ").title() if entry.get("sources") else "",
        "country": entry.get("country", ""),
        "about": about,
        "documents": documents,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


# Document labels look like:
#   "14/15 Judgment 19/04/2017 EN"
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
    "order": "order",
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
        f"Procedure:    {meta['procedure']}",
        f"Source court: {meta['source_court']} ({meta['country']})",
        f"Submitted:    {meta['date_submitted']}",
        f"Hearing:      {meta['hearing_date'] or '-'}",
        f"Judgment:     {meta['judgment_date'] or '-'}",
        f"URL:          {meta['url']}",
        "",
        "About:",
        meta["about"] or "(no description)",
        "",
        "Documents:",
    ]
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
        avail = ", ".join(f"{d.get('type','?')}({d.get('lang','?')})" for d in docs)
        raise SystemExit(f"No matching document. Available: {avail}")
    cdir = cache_dir() / "cases" / case_key(canonical)
    pdf_p = cdir / f"{chosen.get('type','doc')}-{chosen.get('lang','XX')}.pdf"
    if not pdf_p.exists():
        download(chosen["url"], pdf_p)
    txt_p = pdf_p.with_suffix(".txt")
    if not txt_p.exists():
        text = extract_pdf_text(pdf_p)
        if text is not None:
            txt_p.write_text(text)
        else:
            txt_p = None
    return pdf_p, txt_p


def _choose_doc(docs: list[dict], doc_type: str | None, lang: str) -> dict | None:
    lang = lang.upper()
    candidates = docs
    if doc_type:
        dt = doc_type.lower().strip()
        candidates = [d for d in docs if dt in (d.get("type", "").lower())]
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
        reader = PdfReader(str(pdf))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ModuleNotFoundError:
        pass
    # Fall back to pdftotext binary
    import shutil as _sh, subprocess as _sp
    if _sh.which("pdftotext"):
        out = pdf.with_suffix(".txt")
        _sp.run(["pdftotext", "-layout", str(pdf), str(out)], check=False)
        if out.exists():
            return out.read_text(errors="replace")
    return None


# ---------------------------------------------------------------------------
# List / search

def cmd_list(args: argparse.Namespace) -> None:
    idx = load_index() or update_index()
    # When the user filters by status, verify all recent cases first — the index
    # alone can't be trusted for pending/decided (see verify_recent_status docstring).
    if args.pending or args.decided:
        idx = verify_recent_status(years=args.verify_years, verbose=True)
    rows = idx["cases"]
    if args.year:
        rows = [r for r in rows if _case_year(r) == args.year % 100]
    if args.country:
        rows = [r for r in rows if r["country"] == args.country.upper()]
    if args.procedure:
        rows = [r for r in rows if r["procedure"] == args.procedure.upper()]
    if args.pending:
        rows = [r for r in rows if r.get("status") == "Pending"]
    if args.decided:
        rows = [r for r in rows if r.get("status") == "Decided"]
    rows.sort(key=lambda r: (-_case_year(r), -_case_num(r)))
    if args.limit:
        rows = rows[: args.limit]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    for r in rows:
        flag = {"Pending": "P", "Decided": "D"}.get(r.get("status") or "", "?")
        print(f"{flag} {r['case_number'] or r['slug']:10}  "
              f"{r.get('country','--'):2}  "
              f"{r.get('procedure','--'):3}  "
              f"{r['date']}  {r['url']}")


def _case_year(r: dict) -> int:
    if r["case_number"]:
        return int(r["case_number"].split("/")[-1])
    return int(r["date"][:4]) % 100


def _case_num(r: dict) -> int:
    if r["case_number"]:
        return int(r["case_number"].removeprefix("E-").split("/")[0])
    return 0


def cmd_search(args: argparse.Namespace) -> None:
    idx = load_index() or update_index()
    rows = idx["cases"]
    if args.year:
        rows = [r for r in rows if _case_year(r) == args.year % 100]
    if args.country:
        rows = [r for r in rows if r["country"] == args.country.upper()]
    q = args.query.lower()
    hits: list[tuple[dict, str]] = []
    for r in rows:
        cdir = cache_dir() / "cases" / case_key(r["case_number"]) if r["case_number"] else None
        meta = None
        if cdir and (cdir / "meta.json").exists():
            try:
                meta = json.loads((cdir / "meta.json").read_text())
            except Exception:
                meta = None
        title = (meta or {}).get("title", "")
        about = (meta or {}).get("about", "")
        haystack = " | ".join([r["case_number"], r["slug"], title, about,
                               " ".join(r.get("sources", []))]).lower()
        snippet = ""
        if q in haystack:
            snippet = title or about[:120]
        elif args.full_text and cdir:
            for txt in cdir.glob("*.txt"):
                try:
                    body = txt.read_text(errors="replace").lower()
                except Exception:
                    continue
                if q in body:
                    i = body.find(q)
                    snippet = "…" + body[max(0, i - 60): i + 120] + "…"
                    break
        if snippet:
            hits.append((r, snippet))
    hits.sort(key=lambda x: (-_case_year(x[0]), -_case_num(x[0])))
    if args.json:
        print(json.dumps([{"case": r, "snippet": s} for r, s in hits], indent=2, ensure_ascii=False))
        return
    if not hits:
        print(f"No hits for {args.query!r}. Try `update` first, or `fetch` likely cases to enrich the local cache.",
              file=sys.stderr)
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
    n_cached = sum(1 for _ in (cdir / "cases").glob("*/meta.json"))
    n_pdfs = sum(1 for _ in (cdir / "cases").glob("*/*.pdf"))
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
    pl.add_argument("--country", help="Filter by country of referring court (NO/IS/LI).")
    pl.add_argument("--procedure", help="Filter by procedure type (AO/INF/DA).")
    pl.add_argument("--pending", action="store_true",
                    help="Only pending cases. Triggers status verification of recent cases (cached).")
    pl.add_argument("--decided", action="store_true",
                    help="Only decided cases. Triggers status verification of recent cases (cached).")
    pl.add_argument("--verify-years", type=int, default=3,
                    help="When verifying status, look back this many years (default: 3).")
    pl.add_argument("--limit", type=int, default=50)
    pl.add_argument("--json", action="store_true")

    ps = sub.add_parser("search", help="Search local index (run `update` and `fetch` to enrich).")
    ps.add_argument("query")
    ps.add_argument("--year", type=int)
    ps.add_argument("--country")
    ps.add_argument("--full-text", action="store_true",
                    help="Also search inside extracted PDF text (only works on cases already fetched).")
    ps.add_argument("--party-only", action="store_true", help="(reserved — currently equivalent to default).")
    ps.add_argument("--json", action="store_true")

    pf = sub.add_parser("fetch", help="Fetch a case page; parse and cache its metadata + document list.")
    pf.add_argument("case", help="Case number in any form (e.g. E-14/15, e14-15, 8/25).")
    pf.add_argument("--refresh", action="store_true", help="Re-download even if cached.")
    pf.add_argument("--json", action="store_true")

    pg = sub.add_parser("get", help="Download a specific document PDF and extract text.")
    pg.add_argument("case")
    pg.add_argument("--type", help="judgment, order, request, notification, opinion-aag, etc.")
    pg.add_argument("--lang", default="EN")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "update": cmd_update,
        "status": cmd_status,
        "list":   cmd_list,
        "search": cmd_search,
        "fetch":  cmd_fetch,
        "get":    cmd_get,
    }
    handlers[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
