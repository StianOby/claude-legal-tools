#!/usr/bin/env python3
"""
hudoc.py — Pure-HTTP CLI for the European Court of Human Rights HUDOC database.

HUDOC has no official API documentation, but it exposes two stable endpoints
(undocumented but used by every browser session against hudoc.echr.coe.int):

  GET /app/query/results       JSON metadata + Lucene-style search.
                               REQUIRES the X-Requested-With: XMLHttpRequest
                               header — the CDN serves a 404 without it.
  GET /app/conversion/{docx,pdf}/?library=ECHR&id=<itemid>
                               Document download. No auth needed.

Subcommands:
  search    Lucene-style query, returns JSON list of itemids + metadata.
  resolve   Map a "human" reference (case name, application number) to an
            itemid. Pick the best language version + originating body.
  metadata  Full metadata for a known itemid or resolved reference.
  fetch     Download the official PDF or DOCX, plus extract plain text from
            the DOCX (no auth, no Selenium).
  citations List every ECtHR case this judgment cites (parsed from the
            `scl` Strasbourg-case-law field).
  show      cat the cached extracted text of a previously fetched item.

Examples:
  hudoc.py search 'docname:"big brother watch"'
  hudoc.py search '(article:"8") AND (conclusion:"Violation of Article 8") AND (doctypebranch:GRANDCHAMBER)' --sort 'kpdate Descending' -n 10
  hudoc.py resolve "Big Brother Watch v. UK"
  hudoc.py metadata 001-210077
  hudoc.py fetch 001-210077 --format text
  hudoc.py fetch "Big Brother Watch v. UK" --format pdf -o bbw.pdf
  hudoc.py citations 001-210077

Cache lives in `~/.cache/hudoc/items/<itemid>/` (or $HUDOC_CACHE_DIR) and is reused on every call,
so a workflow like search→fetch→citations only hits the network once per
artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_default_cache = Path.home() / ".cache" / "hudoc"
CACHE_DIR = Path(os.environ.get("HUDOC_CACHE_DIR", _default_cache))
ITEMS_DIR = CACHE_DIR / "items"
SEARCH_DIR = CACHE_DIR / "searches"

BASE = "https://hudoc.echr.coe.int"
QUERY_URL = f"{BASE}/app/query/results"
PDF_URL = f"{BASE}/app/conversion/pdf/"
DOCX_URL = f"{BASE}/app/conversion/docx/"
WEB_URL = f"{BASE}/eng?i="  # human-friendly URL Claude should cite

USER_AGENT = (
    "hudoc-skill/0.1 "
    "(legal research; Python urllib; contact via Claude session)"
)

# Default field set: everything the HUDOC UI itself exposes for a result row,
# plus the citation-relevant fields. Trimmed down via --select if needed.
DEFAULT_FIELDS = [
    "itemid",
    "docname",
    "appno",
    "respondent",
    "article",
    "kpdate",
    "judgementdate",
    "doctypebranch",
    "doctype",
    "documentcollectionid2",
    "importance",
    "languageisocode",
    "conclusion",
    "ecli",
    "scl",            # Strasbourg case-law cited
    "extractedappno", # all appnos referenced in the document
    "kpthesaurus",
    "originatingbody",
    "issue",
    "separateopinion",
]

# What a result must include to even be considered. ECHR is the public
# Court collection; CASELAW pulls in Commission docs as well.
SITE_FILTER = "(contentsitename=ECHR)"

# A few well-known doctypebranch / doctype codes — useful for filter docs.
DOCTYPEBRANCH = {
    "GRANDCHAMBER": "Grand Chamber judgment",
    "CHAMBER":      "Chamber judgment",
    "COMMITTEE":    "Committee judgment / decision",
    "ADMISSIBILITY":"Admissibility decision",
    "ADMISSIBILITYCOM": "Commission admissibility decision",
    "COMMUNICATEDCASES": "Communicated case",
    "ADVISORYOPINIONS": "Advisory opinion",
    "MERITS":       "Old Commission report on the merits",
    "RESOLUTIONS":  "Committee of Ministers resolution",
    "CLIN":         "Case-Law Information Note legal summary",
}

LANG_PREFERENCE_DEFAULT = ["ENG", "FRE"]  # English first, French fallback


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

def _http_get(url: str, *, accept: str = "application/json", retries: int = 3) -> bytes:
    """GET with the magic XHR header. Returns raw bytes. Retries on 500 errors."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Referer": f"{BASE}/eng",
            # Without this header the CDN serves a 404 page for /app/query/*
            # and a few other endpoints. With it, the JSON API just works.
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            # Retry on 500+ server errors; give up on client errors (4xx)
            if e.code >= 500 and attempt <= retries:
                wait = 2 ** (attempt - 1)  # exponential backoff: 1s, 2s, 4s
                print(f"HTTP {e.code}, retrying in {wait}s ({attempt}/{retries})...", file=sys.stderr)
                time.sleep(wait)
                continue
            body = e.read()[:300].decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error fetching {url}: {e}") from None


def _query(
    lucene_query: str,
    *,
    fields: Iterable[str] = DEFAULT_FIELDS,
    sort: str = "",
    start: int = 0,
    length: int = 20,
) -> dict:
    """Run a search against HUDOC. `lucene_query` is appended to SITE_FILTER."""
    full_query = f"{SITE_FILTER} AND ({lucene_query})" if lucene_query else SITE_FILTER
    params = [
        ("query", full_query),
        ("select", ",".join(fields)),
        ("sort", sort),
        ("start", str(start)),
        ("length", str(length)),
    ]
    url = QUERY_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    raw = _http_get(url)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        snippet = raw[:200].decode("utf-8", errors="replace")
        raise RuntimeError(f"HUDOC did not return JSON. First bytes: {snippet}")


def _flatten_columns(api_result: dict) -> list[dict]:
    """Pull the inner column dicts out of the HUDOC API response."""
    return [r["columns"] for r in api_result.get("results", [])]


# ---------------------------------------------------------------------------
# Resolve human references → itemid
# ---------------------------------------------------------------------------

# Itemids look like NNN-NNNNNN (e.g. 001-57619, 003-8420063-11915360).
ITEMID_RE = re.compile(r"^\d{3}-\d+(?:-\d+)?$")
# Application numbers are NUMBER/YY (e.g. 14038/88; sometimes joined with ;)
APPNO_RE = re.compile(r"^\d{1,6}/\d{2}(?:;\d{1,6}/\d{2})*$")


def looks_like_itemid(s: str) -> bool:
    return bool(ITEMID_RE.match(s.strip()))


def looks_like_appno(s: str) -> bool:
    return bool(APPNO_RE.match(s.strip()))


def _score_candidate(c: dict, lang_pref: list[str]) -> tuple:
    """
    Build a sort key that ranks the "best" version of a case across all the
    duplicate rows HUDOC returns (one per language, one per court instance,
    press release, legal summary, EXECUTION resolution etc.).

    Lower is better. Order of priorities:
      1. Real judgment first (HEJUD/HFJUD), press releases last
      2. Higher court instance (GC > Chamber > Committee > admissibility)
      3. Language preference (ENG before FRE before everything)
      4. Most recent date (Grand Chamber rehearing wins over original Chamber)
    """
    doctype = c.get("doctype") or ""
    branch = c.get("doctypebranch") or ""
    lang = c.get("languageisocode") or ""

    # 1) doc kind: real judgments / decisions win, summaries and press last
    if doctype in ("HEJUD", "HFJUD"):
        kind_score = 0
    elif doctype in ("HEDEC", "HFDEC"):
        kind_score = 1   # admissibility / strike-out decisions
    elif doctype in ("ADV", "HEADV", "HFADV"):
        kind_score = 2   # advisory opinions
    elif doctype in ("CLIN", "INFONOTE"):
        kind_score = 3   # legal summaries
    elif doctype.startswith("HERES") or doctype.startswith("HFRES"):
        kind_score = 4   # Committee of Ministers EXECUTION resolutions
    elif doctype == "PR":
        kind_score = 6   # press release — almost never what a researcher wants
    else:
        kind_score = 5

    # 2) instance: GC > Chamber > Committee > admissibility (only meaningful
    #    for HEJUD/HFJUD, but a useful tiebreak)
    branch_priority = {
        "GRANDCHAMBER": 0, "CHAMBER": 1, "COMMITTEE": 2,
        "ADMISSIBILITY": 3, "ADMISSIBILITYCOM": 4,
        "MERITS": 5,  # old Commission
    }
    branch_score = branch_priority.get(branch, 9)

    # 3) language: prefer first available in lang_pref
    try:
        lang_score = lang_pref.index(lang)
    except ValueError:
        lang_score = len(lang_pref)

    # 4) date: most recent first. kpdate is ISO-like ("2018-09-04T00:00:00").
    #    Negate alphabetically by inverting digits; missing date sorts last.
    raw_date = c.get("kpdate") or ""
    if raw_date:
        # Map each digit d → (9-d). e.g. "2018" → "7981", so newer < older.
        date_score = "".join(str(9 - int(ch)) if ch.isdigit() else ch for ch in raw_date)
    else:
        date_score = "9" * 19  # missing date sorts last

    return (kind_score, branch_score, lang_score, date_score)


def resolve(
    reference: str,
    lang_pref: Optional[list[str]] = None,
    doctype_filter: Optional[str] = None,
) -> dict:
    """
    Turn a human-typed reference into a single best-match HUDOC row.

    Accepts:
      * raw itemid (skips network if cached)
      * application number ("14038/88")
      * case name ("Big Brother Watch v. UK", "Soering")
      * docname:"..." or any Lucene clause — passed straight through

    doctype_filter: if set, restrict candidates to rows whose doctypebranch
    matches (case-insensitive). E.g. "ADMISSIBILITY" when the user explicitly
    wants the decision rather than a later Grand Chamber judgment.

    Returns the columns dict for the chosen item.
    """
    lang_pref = lang_pref or LANG_PREFERENCE_DEFAULT
    ref = reference.strip()

    if looks_like_itemid(ref):
        # Direct itemid lookup
        api = _query(f'itemid:"{ref}"', length=1)
        rows = _flatten_columns(api)
        if not rows:
            raise RuntimeError(f"No HUDOC item with itemid={ref}")
        return rows[0]

    if looks_like_appno(ref):
        # Application number — usually 2-4 hits across languages
        # Use the first appno only when there's a list; HUDOC indexes them
        first_app = ref.split(";")[0]
        api = _query(f'appno:"{first_app}"', length=50)
    elif ":" in ref and not ref.startswith('"'):
        # Caller already wrote a Lucene clause (e.g. `docname:"foo"`).
        api = _query(ref, length=50)
    else:
        # Free-text case name. Build a *non-phrasal* docname clause: HUDOC's
        # docnames are like "CASE OF FOO AND OTHERS v. THE UNITED KINGDOM",
        # so the literal user phrase "Foo v. UK" almost never matches as an
        # exact substring. Strip everything after the first " v. " or " c. "
        # and search for the remaining tokens against docname (AND-of-tokens).
        head = re.split(r"\s+(?:v\.|c\.|vs\.?)\s+", ref, maxsplit=1)[0]
        # Drop punctuation that breaks the Lucene parser
        tokens = [t for t in re.findall(r"[\w'-]+", head) if len(t) > 1]
        if not tokens:
            tokens = re.findall(r"[\w'-]+", ref)
        clause = " AND ".join(f'docname:{t}' for t in tokens) or f'docname:"{ref}"'
        api = _query(clause, length=50)

    rows = _flatten_columns(api)
    if not rows:
        raise RuntimeError(
            f"No HUDOC item matched reference {ref!r}. Try `hudoc.py search` "
            f"with a Lucene query or check the spelling."
        )
    if doctype_filter:
        want = doctype_filter.upper()
        filtered = [r for r in rows if (r.get("doctypebranch") or "").upper() == want]
        if not filtered:
            available = sorted({r.get("doctypebranch") or "?" for r in rows})
            raise RuntimeError(
                f"No {want!r} row found for {ref!r}. "
                f"Available doctypebranch values: {', '.join(available)}. "
                f"Pass the itemid directly to skip resolve filtering."
            )
        rows = filtered
    rows.sort(key=lambda c: _score_candidate(c, lang_pref))
    return rows[0]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _item_dir(itemid: str) -> Path:
    d = ITEMS_DIR / itemid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(item: dict) -> Path:
    itemid = item["itemid"]
    p = _item_dir(itemid) / "meta.json"
    p.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _load_metadata(itemid: str) -> Optional[dict]:
    p = ITEMS_DIR / itemid / "meta.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Document download (PDF / DOCX / extracted text)
# ---------------------------------------------------------------------------

def _download(url: str) -> bytes:
    return _http_get(url, accept="*/*")


def fetch_pdf(itemid: str) -> Path:
    p = _item_dir(itemid) / "judgment.pdf"
    if p.exists() and p.stat().st_size > 0:
        return p
    url = (
        PDF_URL
        + "?"
        + urllib.parse.urlencode(
            {"library": "ECHR", "id": itemid, "filename": f"{itemid}.pdf"}
        )
    )
    p.write_bytes(_download(url))
    return p


def fetch_docx(itemid: str) -> Path:
    p = _item_dir(itemid) / "judgment.docx"
    if p.exists() and p.stat().st_size > 0:
        return p
    url = (
        DOCX_URL
        + "?"
        + urllib.parse.urlencode(
            {"library": "ECHR", "id": itemid, "filename": f"{itemid}.docx"}
        )
    )
    p.write_bytes(_download(url))
    return p


def docx_to_text(docx_path: Path) -> str:
    """
    Extract plain text from a HUDOC DOCX without external deps.
    Walks word/document.xml, joins paragraphs with newlines, and preserves
    paragraph breaks so paragraph numbers ("§ 47") are easy to find.
    """
    NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(docx_path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    out_paragraphs = []
    for para in tree.iter(f'{{{NS["w"]}}}p'):
        # Concatenate every text run inside this paragraph
        runs = [t.text or "" for t in para.iter(f'{{{NS["w"]}}}t')]
        text = "".join(runs).strip()
        if text:
            out_paragraphs.append(text)
    return "\n\n".join(out_paragraphs) + "\n"


def pdf_to_text(pdf_path: Path) -> str:
    """
    Extract plain text from a PDF without external deps.
    Attempts to decompress and extract text from PDF content streams.
    Less accurate than DOCX but works as a fallback. May not preserve
    paragraph structure.
    """
    import zlib
    raw = pdf_path.read_bytes()
    text_parts = []

    # Try to decompress every stream (FlateDecode), then scan for text ops.
    # Unconditionally attempt zlib.decompress — valid headers include \x78\x01,
    # \x78\x5e, \x78\x9c, \x78\xda; checking one prefix misses the rest.
    for match in re.finditer(rb'stream\s*\n(.*?)\nendstream', raw, re.DOTALL):
        stream_data = match.group(1)
        try:
            decompressed = zlib.decompress(stream_data)
        except zlib.error:
            continue
        # PDF literal strings: (text)Tj / (text)TJ. Handle \) escapes.
        for text_match in re.finditer(rb'\(((?:[^()\\]|\\.)*)\)\s*[Tj]', decompressed):
            try:
                text = text_match.group(1).decode('utf-8', errors='ignore')
                text = text.replace('\\n', ' ').replace('\\t', ' ')
                if text.strip():
                    text_parts.append(text.strip())
            except Exception:
                pass

    if not text_parts:
        raise RuntimeError(
            f"No extractable text found in PDF {pdf_path.name}. "
            "Download the PDF directly from HUDOC for full content."
        )

    # Join with newlines, de-duplicate consecutive duplicates
    lines = []
    for part in text_parts:
        if not lines or part != lines[-1]:
            lines.append(part)

    return '\n'.join(lines) + '\n'


def fetch_text(itemid: str) -> Path:
    """
    Get the text of a judgment. Tries DOCX first (better formatting),
    falls back to PDF if DOCX fails.
    """
    txt_path = _item_dir(itemid) / "judgment.txt"
    if txt_path.exists() and txt_path.stat().st_size > 0:
        return txt_path

    # Try DOCX first (preserves paragraph structure)
    try:
        docx_path = fetch_docx(itemid)
        text = docx_to_text(docx_path)
        txt_path.write_text(text, encoding="utf-8")
        return txt_path
    except Exception as e:
        print(f"DOCX extraction failed: {e}; trying PDF fallback...", file=sys.stderr)

    # Fallback to PDF
    try:
        pdf_path = fetch_pdf(itemid)
        text = pdf_to_text(pdf_path)
        txt_path.write_text(text, encoding="utf-8")
        return txt_path
    except Exception as e:
        raise RuntimeError(f"Both DOCX and PDF extraction failed for {itemid}: {e}") from None


# ---------------------------------------------------------------------------
# Citation parsing
# ---------------------------------------------------------------------------

# An scl entry looks like:
#   "Cristescu v. Romania, no. 13589/07, § 50, 10 January 2012"
#   "Radomilja and Others v. Croatia [GC], nos. 37685/10 and 22768/12, § 114, 20 March 2018"
# We split on ';' (HUDOC's chosen separator), then pull out appno + date.
_CITE_SPLIT = re.compile(r";\s*")
_APPNO_IN_CITE = re.compile(r"nos?\.\s*([\d/]+(?:\s*and\s*[\d/]+)*)", re.IGNORECASE)
_DATE_IN_CITE = re.compile(
    r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"
)


def parse_scl(scl: str) -> list[dict]:
    """Turn the raw `scl` string into a list of {raw, name, appnos, date}."""
    out: list[dict] = []
    for raw in _CITE_SPLIT.split(scl or ""):
        raw = raw.strip()
        if not raw:
            continue
        appnos: list[str] = []
        m = _APPNO_IN_CITE.search(raw)
        if m:
            # "37685/10 and 22768/12" → ["37685/10", "22768/12"]
            for part in re.split(r"\s+and\s+", m.group(1), flags=re.IGNORECASE):
                part = part.strip()
                if "/" in part:
                    appnos.append(part)
        # The case name is everything before the first "no." marker
        name = re.split(r",\s*nos?\.", raw, maxsplit=1, flags=re.IGNORECASE)[0]
        date = None
        d = _DATE_IN_CITE.search(raw)
        if d:
            date = d.group(1)
        out.append({"raw": raw, "name": name.strip(), "appnos": appnos, "date": date})
    return out


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> int:
    """Run a Lucene-style search and print JSON to stdout."""
    api = _query(
        args.query,
        sort=args.sort,
        start=args.start,
        length=args.length,
        fields=args.select.split(",") if args.select else DEFAULT_FIELDS,
    )
    rows = _flatten_columns(api)
    print(json.dumps(
        {"resultcount": api.get("resultcount", 0), "results": rows},
        indent=2, ensure_ascii=False
    ))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    item = resolve(args.reference, lang_pref=args.lang_pref.split(","),
                   doctype_filter=args.doctype)
    print(json.dumps(item, indent=2, ensure_ascii=False))
    _save_metadata(item)
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    if looks_like_itemid(args.reference):
        cached = _load_metadata(args.reference)
        if cached and not args.refresh:
            print(json.dumps(cached, indent=2, ensure_ascii=False))
            return 0
        item = resolve(args.reference, doctype_filter=args.doctype)
    else:
        item = resolve(args.reference, lang_pref=args.lang_pref.split(","),
                       doctype_filter=args.doctype)
    _save_metadata(item)
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    item = resolve(args.reference, lang_pref=args.lang_pref.split(","),
                   doctype_filter=args.doctype)
    itemid = item["itemid"]
    _save_metadata(item)

    fmt = args.format
    if fmt == "pdf":
        p = fetch_pdf(itemid)
    elif fmt == "docx":
        p = fetch_docx(itemid)
    elif fmt == "text":
        p = fetch_text(itemid)
    else:
        raise SystemExit(f"unknown format {fmt}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(p.read_bytes())
        target = out
    else:
        target = p

    if args.print and fmt == "text":
        print(target.read_text(encoding="utf-8"))
    else:
        print(json.dumps({
            "itemid": itemid,
            "docname": item.get("docname"),
            "appno": item.get("appno"),
            "kpdate": item.get("kpdate"),
            "doctypebranch": item.get("doctypebranch"),
            "languageisocode": item.get("languageisocode"),
            "format": fmt,
            "path": str(target),
            "source_url": WEB_URL + itemid,
        }, indent=2, ensure_ascii=False))
    return 0


def cmd_citations(args: argparse.Namespace) -> int:
    item = resolve(args.reference, lang_pref=args.lang_pref.split(","),
                   doctype_filter=args.doctype)
    _save_metadata(item)
    cites = parse_scl(item.get("scl") or "")
    print(json.dumps({
        "itemid": item["itemid"],
        "docname": item.get("docname"),
        "cited_count": len(cites),
        "cited": cites,
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    if not looks_like_itemid(args.itemid):
        raise SystemExit("show requires an itemid like 001-57619")
    p = ITEMS_DIR / args.itemid / "judgment.txt"
    if not p.exists():
        raise SystemExit(f"no cached text for {args.itemid}; run `fetch --format text` first")
    print(p.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="hudoc",
        description="Lookup and download ECtHR case law from HUDOC.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # global lang pref / doctype filter
    lang_arg = ("--lang-pref",)
    lang_kw = dict(default="ENG,FRE",
                   help="Comma-sep ISO codes; first one available wins. Default: ENG,FRE")
    doctype_arg = ("--doctype",)
    doctype_kw = dict(default=None, metavar="BRANCH",
                      help="Filter resolve to this doctypebranch, e.g. ADMISSIBILITY, "
                           "GRANDCHAMBER, CHAMBER. Useful when an appno has both a "
                           "decision and a later judgment.")

    sp = sub.add_parser("search", help="Lucene-style search; returns JSON.")
    sp.add_argument("query", help='e.g. \'docname:"big brother"\' or \'(article:"8") AND (respondent:"NOR")\'')
    sp.add_argument("--sort", default="kpdate Descending",
                    help='HUDOC sort string. Default: "kpdate Descending"')
    sp.add_argument("-n", "--length", type=int, default=10)
    sp.add_argument("--start", type=int, default=0)
    sp.add_argument("--select", default="",
                    help="Comma-sep field list. Empty = full default set.")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("resolve", help="Map a name/appno/itemid to a single best HUDOC row.")
    sp.add_argument("reference")
    sp.add_argument(*lang_arg, **lang_kw)
    sp.add_argument(*doctype_arg, **doctype_kw)
    sp.set_defaults(func=cmd_resolve)

    sp = sub.add_parser("metadata", help="Full metadata for a case (cached after first call).")
    sp.add_argument("reference")
    sp.add_argument(*lang_arg, **lang_kw)
    sp.add_argument(*doctype_arg, **doctype_kw)
    sp.add_argument("--refresh", action="store_true",
                    help="Bypass cache and re-fetch from HUDOC.")
    sp.set_defaults(func=cmd_metadata)

    sp = sub.add_parser("fetch", help="Download the judgment as PDF/DOCX/text.")
    sp.add_argument("reference")
    sp.add_argument("--format", choices=("pdf", "docx", "text"), default="text")
    sp.add_argument("-o", "--output",
                    help="Also copy the result to this path (e.g. /tmp/judgment.pdf).")
    sp.add_argument("--print", action="store_true",
                    help="With --format text, print the full text to stdout.")
    sp.add_argument(*lang_arg, **lang_kw)
    sp.add_argument(*doctype_arg, **doctype_kw)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("citations", help="List ECtHR cases cited (parsed from scl).")
    sp.add_argument("reference")
    sp.add_argument(*lang_arg, **lang_kw)
    sp.add_argument(*doctype_arg, **doctype_kw)
    sp.set_defaults(func=cmd_citations)

    sp = sub.add_parser("show", help="Print previously fetched plain text from cache.")
    sp.add_argument("itemid")
    sp.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"hudoc: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
