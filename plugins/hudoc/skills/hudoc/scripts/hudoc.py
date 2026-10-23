#!/usr/bin/env python3
"""
hudoc.py — Pure-HTTP CLI for the European Court of Human Rights HUDOC database.

HUDOC has no official API documentation, but it exposes stable endpoints
(undocumented but used by every browser session against hudoc.echr.coe.int):

  GET /app/query/results       JSON metadata + Lucene-style search.
                               REQUIRES the X-Requested-With: XMLHttpRequest
                               header — the CDN serves a 404 without it.
  GET /app/conversion/docx/html/body?library=ECHR&id=<itemid>
                               The HTML HUDOC's reading view shows; the
                               text source. No auth needed.
  GET /app/conversion/pdf/?library=ECHR&id=<itemid>
                               The official PDF; text fallback for
                               PDF-only items. No auth needed.

Subcommands:
  search    Lucene-style query, returns JSON list of itemids + metadata.
  resolve   Map a "human" reference (case name, application number) to an
            itemid. Pick the best language version + originating body.
  metadata  Full metadata for a known itemid or resolved reference.
  fetch     Extract the plain text of a judgment (from HUDOC's HTML, or the
            PDF when there is no HTML), or download the official PDF.
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
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

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
# The HTML that HUDOC's own reading view shows. HUDOC renders it from the
# DOCX with a full Word converter, so heading and list numbers, line breaks
# and non-breaking hyphens come out right — the text source of choice.
HTML_URL = f"{BASE}/app/conversion/docx/html/body"
WEB_URL = f"{BASE}/eng?i="  # human-friendly URL Claude should cite

# Cloudflare in front of HUDOC sometimes answers "Just a moment…" (HTTP 403)
# instead of data. Which requests it challenges changes from minute to minute:
# on 2026-09-28 the same agent string from the same machine passed four times
# in a row and was challenged eight times in a row a minute apart, for curl
# and urllib alike, and waiting 4 + 10 s and retrying did not help. No agent
# string passes reliably, so _http_get() only detects a challenge and says so.
# $HUDOC_USER_AGENT overrides the string.
USER_AGENT = os.environ.get("HUDOC_USER_AGENT") or (
    "hudoc-skill/1.3.0 (+https://github.com/StianOby/claude-legal-tools)"
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
# Atomic, validated file helpers
# ---------------------------------------------------------------------------

def _has_content(p: Path) -> bool:
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


def _write_bytes(p: Path, data: bytes) -> None:
    """Write via a temp file + rename so an interrupted download never
    leaves a partial file that later counts as a cache hit."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def _write_text(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class ChallengeError(RuntimeError):
    """HUDOC's Cloudflare answered with a "Just a moment…" page."""


def _decoded(resp) -> bytes:
    """Body of a response, un-gzipped if the server compressed it. The HTML
    rendition of a judgment is about four times smaller gzipped."""
    raw = resp.read()
    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw


def _http_get(url: str, *, accept: str = "application/json", retries: int = 3) -> bytes:
    """GET with the magic XHR header. Returns raw bytes. Retries on 500 errors."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": "gzip",
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
                return _decoded(resp)
        except urllib.error.HTTPError as e:
            # Retry on 500+ server errors; give up on client errors (4xx)
            if e.code >= 500 and attempt <= retries:
                wait = 2 ** (attempt - 1)  # exponential backoff: 1s, 2s, 4s
                print(f"HTTP {e.code}, retrying in {wait}s ({attempt}/{retries})...", file=sys.stderr)
                time.sleep(wait)
                continue
            raw = _decoded(e)
            if e.code == 403 and (b"Just a moment" in raw
                                  or (e.headers.get("cf-mitigated") or "").lower() == "challenge"):
                raise ChallengeError(
                    "HUDOC answered with a Cloudflare challenge page (HTTP 403, "
                    "\"Just a moment…\"), not data. This is not a missing document: "
                    "try again in a few minutes, and tell the user if it persists."
                ) from None
            body = raw[:300].decode("utf-8", errors="replace")
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
# European Case Law Identifiers, e.g. ECLI:CE:ECHR:1989:0707JUD001403888
ECLI_RE = re.compile(r"^ECLI:CE:ECHR:\d{4}:\d{4}[A-Z]{3}\d{9,12}$", re.IGNORECASE)


# Application numbers are NUMBER/YY (e.g. 14038/88), alone or in a list:
# "no. 14038/88", "nos. 58170/13, 62322/14 and 24960/15", "Application
# no. 14038/88", "requête no 14038/88", "n° 14038/88".
_APPNO_PREFIX_RE = re.compile(
    r"^(?:(?:application|app\.|requête|req\.)\s*)?(?:nos?\.?|n[°º]s?\.?)?\s*", re.IGNORECASE)
_APPNO_ANY_RE = re.compile(r"(?<![\d/])\d{1,6}/\d{2}(?![\d/])")
_APPNO_LIST_RE = re.compile(r"^\d{1,6}/\d{2}(?:\s*(?:;|,|&|\band\b|\bet\b)\s*\d{1,6}/\d{2})*$", re.IGNORECASE)


def looks_like_itemid(s: str) -> bool:
    return bool(ITEMID_RE.match(s.strip()))


def appnos_in(s: str) -> list[str]:
    """Application numbers when `s` is nothing but one or a list of them,
    optionally after "no." / "nos." / "Application no."; else []."""
    rest = _APPNO_PREFIX_RE.sub("", s.strip(), count=1).rstrip(" .")
    return _APPNO_ANY_RE.findall(rest) if _APPNO_LIST_RE.match(rest) else []


# Respondent states as HUDOC codes them (ISO 3166 alpha-3), keyed by the
# lower-cased English and French names used in case titles.
RESPONDENT_CODES = {
    "ALB": ["albania", "albanie"],
    "AND": ["andorra", "andorre"],
    "ARM": ["armenia", "arménie"],
    "AUT": ["austria", "autriche"],
    "AZE": ["azerbaijan", "azerbaïdjan"],
    "BEL": ["belgium", "belgique"],
    "BIH": ["bosnia and herzegovina", "bosnie-herzégovine"],
    "BGR": ["bulgaria", "bulgarie"],
    "HRV": ["croatia", "croatie"],
    "CYP": ["cyprus", "chypre"],
    "CZE": ["czech republic", "czechia", "république tchèque", "tchéquie"],
    "DNK": ["denmark", "danemark"],
    "EST": ["estonia", "estonie"],
    "FIN": ["finland", "finlande"],
    "FRA": ["france"],
    "GEO": ["georgia", "géorgie"],
    "DEU": ["germany", "allemagne"],
    "GRC": ["greece", "grèce"],
    "HUN": ["hungary", "hongrie"],
    "ISL": ["iceland", "islande"],
    "IRL": ["ireland", "irlande"],
    "ITA": ["italy", "italie"],
    "LVA": ["latvia", "lettonie"],
    "LIE": ["liechtenstein"],
    "LTU": ["lithuania", "lituanie"],
    "LUX": ["luxembourg"],
    "MLT": ["malta", "malte"],
    "MDA": ["moldova", "republic of moldova", "république de moldova", "moldavie"],
    "MCO": ["monaco"],
    "MNE": ["montenegro", "monténégro"],
    "NLD": ["netherlands", "pays-bas"],
    "MKD": ["north macedonia", "former yugoslav republic of macedonia", "macedonia",
            "macédoine du nord", "ex-république yougoslave de macédoine", "fyrom"],
    "NOR": ["norway", "norvège"],
    "POL": ["poland", "pologne"],
    "PRT": ["portugal"],
    "ROU": ["romania", "roumanie"],
    "RUS": ["russia", "russian federation", "russie", "fédération de russie"],
    "SMR": ["san marino", "saint-marin"],
    "SRB": ["serbia", "serbie"],
    "SVK": ["slovakia", "slovak republic", "slovaquie"],
    "SVN": ["slovenia", "slovénie"],
    "ESP": ["spain", "espagne"],
    "SWE": ["sweden", "suède"],
    "CHE": ["switzerland", "suisse"],
    "TUR": ["turkey", "türkiye", "turkiye", "turquie"],
    "UKR": ["ukraine"],
    "GBR": ["united kingdom", "uk", "u.k.", "royaume-uni", "great britain"],
}
_RESPONDENT_BY_NAME = {n: code for code, names in RESPONDENT_CODES.items() for n in names}
# "Kurt v. Turkey", "Soering v UK", "Kurt c. Turquie", "X vs. Norway".
_VERSUS_RE = re.compile(r"\s+(?:v\.?|c\.|vs\.?)\s+", re.IGNORECASE)


def respondent_code(state: str) -> Optional[str]:
    """ISO-3 respondent code for the text after "v." in a case name, or None.

    Drops a trailing "[GC]", "(no. 2)", ", no. …" or date, and a leading
    "the" / "la" / "l'", so "the United Kingdom (no. 2) [GC]" is GBR.
    """
    s = re.split(r"[\[(,]", state, maxsplit=1)[0]
    s = re.sub(r"^(?:the|la|le|l')\s*", "", s.strip().lower())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return _RESPONDENT_BY_NAME.get(s) or _RESPONDENT_BY_NAME.get(s.replace(".", ""))


# HUDOC's docname search matches inside words ("Kurt" finds Bozkurt and
# Özkurt too), so a common name can have hundreds of hits, and the case
# wanted need not be in the first page. A name search reads up to this many
# rows; resolve() then ranks whole-word name matches first.
NAME_SEARCH_MAX_ROWS = 300
_NAME_FILLER = {"and", "others", "other", "et", "autres", "the", "of"}


def reference_query(ref: str) -> tuple[str, int, Optional[str], list[str]]:
    """(clause, length, fallback, name) for a reference `resolve` does not
    look up by itemid. `fallback` is a looser clause to try when `clause`
    finds nothing (a name search without the respondent filter), else None.
    `name` holds the applicant-name tokens of a case-name search ([] for
    every other kind of reference)."""
    appnos = appnos_in(ref)
    if appnos:
        # HUDOC indexes every appno of a joined case; the first one is enough.
        return f'appno:"{appnos[0]}"', 50, None, []
    if looks_like_ecli(ref):
        # An ECLI identifies one judgment; rows differ only by language /
        # translation, so the usual scoring picks the preferred version.
        return f'ecli:"{ref.upper()}"', 50, None, []
    if ":" in ref and not ref.startswith('"'):
        # Caller already wrote a Lucene clause (e.g. `docname:"foo"`).
        return ref, 50, None, []
    # A case citation with its application number ("Soering v. UK, no.
    # 14038/88, § 88"): the number is the precise key.
    found = _APPNO_ANY_RE.findall(ref)
    if found:
        return f'appno:"{found[0]}"', 50, None, []
    # Free-text case name. Build a *non-phrasal* docname clause: HUDOC's
    # docnames are like "CASE OF FOO AND OTHERS v. THE UNITED KINGDOM", so
    # the literal user phrase "Foo v. UK" almost never matches as an exact
    # substring. Search for the tokens before " v. " (AND-of-tokens), and
    # narrow by the respondent state after it: "Kurt v. Turkey" must not
    # come back as Kurt v. Austria [GC], which the ranking would prefer.
    parts = _VERSUS_RE.split(ref, maxsplit=1)
    head = parts[0]
    # Drop punctuation that breaks the Lucene parser
    tokens = [t for t in re.findall(r"[\w'-]+", head) if len(t) > 1]
    if not tokens:
        tokens = re.findall(r"[\w'-]+", ref)
    clause = " AND ".join(f'docname:{t}' for t in tokens) or f'docname:"{ref}"'
    code = respondent_code(parts[1]) if len(parts) > 1 else None
    # The applicant's name for ranking: every word before "v.", one-letter
    # ones included ("A v. Norway"), never "v" or the state, and not the
    # words that differ between the English and French title ("and Others"
    # / "et autres").
    name = [t for t in re.findall(r"[\w'-]+", head) if t.lower() not in _NAME_FILLER]
    if code:
        return f'{clause} AND respondent:"{code}"', 50, clause, name
    return clause, 50, None, name


def name_matches(row: dict, name: list[str]) -> bool:
    """True if every name token is a whole word of the row's docname, so
    "Kurt" matches CASE OF KURT v. TURKEY but not BELEK AND ÖZKURT."""
    docname = (row.get("docname") or "").upper()
    return all(re.search(rf"(?<!\w){re.escape(t.upper())}(?!\w)", docname) for t in name)


def _rows_for(clause: str, length: int, name: list[str]) -> list[dict]:
    """Rows for `clause`; for a name search, further pages up to
    NAME_SEARCH_MAX_ROWS when HUDOC reports more hits than the first page."""
    api = _query(clause, length=length)
    rows = _flatten_columns(api)
    total = int(api.get("resultcount") or 0)
    while name and rows and len(rows) < min(total, NAME_SEARCH_MAX_ROWS):
        page = _flatten_columns(_query(clause, start=len(rows), length=100))
        if not page:
            break
        rows += page
    return rows


def looks_like_ecli(s: str) -> bool:
    return bool(ECLI_RE.match(s.strip()))


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
      * ECLI ("ECLI:CE:ECHR:1989:0707JUD001403888")
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

    clause, length, fallback, name = reference_query(ref)
    rows = _rows_for(clause, length, name)
    if not rows and fallback:
        # The respondent filter found nothing (an unusual title, or a state
        # coded differently): fall back to the name alone.
        rows = _rows_for(fallback, length, name)

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
    # Whole-word name matches first (Kurt before Özkurt), then the usual
    # judgment > decision, GC > Chamber, language, date ranking.
    rows.sort(key=lambda c: (not name_matches(c, name),) + _score_candidate(c, lang_pref))
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
    _write_text(p, json.dumps(item, indent=2, ensure_ascii=False))
    return p


def _load_metadata(itemid: str) -> Optional[dict]:
    p = ITEMS_DIR / itemid / "meta.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Document download (PDF / HTML / extracted text)
# ---------------------------------------------------------------------------

def _download(url: str) -> bytes:
    return _http_get(url, accept="*/*")


def pdf_url(itemid: str) -> str:
    """Direct link to the official PDF. Opened in the user's own browser,
    which HUDOC's Cloudflare lets through, it saves the file as
    <itemid>.pdf — the way to hand over a PDF when the script is challenged."""
    return PDF_URL + "?" + urllib.parse.urlencode(
        {"library": "ECHR", "id": itemid, "filename": f"{itemid}.pdf"}
    )


def fetch_pdf(itemid: str) -> Path:
    """Download the official PDF. The conversion endpoint answers 204 with
    an empty body when no PDF exists and may serve an HTML error page with
    200, so the bytes are validated before they are cached."""
    p = _item_dir(itemid) / "judgment.pdf"
    if _has_content(p):
        return p
    data = _download(pdf_url(itemid))
    if not data.startswith(b"%PDF"):
        raise RuntimeError(
            f"HUDOC returned no PDF for {itemid} ({len(data)} bytes, "
            f"starts {data[:20]!r})"
        )
    _write_bytes(p, data)
    return p


def fetch_html(itemid: str) -> Path:
    """Download the HTML rendition HUDOC's reading view shows. The endpoint
    answers 204 with an empty body when the item has none (PDF-only items),
    so anything that is not markup is refused before it is cached."""
    p = _item_dir(itemid) / "judgment.html"
    if _has_content(p):
        return p
    url = HTML_URL + "?" + urllib.parse.urlencode({"library": "ECHR", "id": itemid})
    data = _download(url)
    if not re.search(rb"<(?:p|div|li|td)[\s>]", data[:200000]):
        raise RuntimeError(
            f"HUDOC returned no HTML for {itemid} ({len(data)} bytes, "
            f"starts {data[:20]!r})"
        )
    _write_bytes(p, data)
    return p


# --- HTML -> text (mirrored by htmlToText in scripts/browser/hudoc.js) -----
#
# The two must give the same text, character for character, so both walk the
# markup with the same token regex instead of a real HTML parser (re.A: JS
# regexes treat \d and \w as ASCII).

_HTML_TOKEN = re.compile(r"<!--[\s\S]*?-->|<(/?)([A-Za-z][\w:.-]*)([^>]*?)(/?)>|([^<]+)", re.A)
_HTML_BLOCK = {"p", "div", "li", "tr", "td", "th", "table", "hr", "ol", "ul",
               "h1", "h2", "h3", "h4", "h5", "h6"}
_HTML_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": chr(0xA0)}
# The text keeps the Court's characters, non-breaking hyphens and soft
# hyphens included. Whitespace collapses as in a browser, and non-breaking
# spaces become plain ones: a documented exception to the repo's rule, since
# most of them only imitate Word's tabs (docs/hudoc.md). Characters from
# Word's Symbol/Wingdings fonts, which arrive as private-use code points,
# become the glyph a reader sees; these are the ones judgments use for
# bullets and footnote marks.
_SYMBOL_CHARS = {0xF02A: "*", 0xF09F: "•", 0xF0A7: "▪", 0xF0B7: "•", 0xF0D8: "➢", 0xF0FC: "✓"}
_TEXT_FIXES = {0xA0: " ", 0x09: " ", 0x0D: " ", **_SYMBOL_CHARS}


def _html_unescape(s: str) -> str:
    def one(m: re.Match) -> str:
        e = m.group(1)
        if e[0] == "#":
            return chr(int(e[2:], 16) if e[1] in "xX" else int(e[1:]))
        return _HTML_NAMED.get(e.lower(), m.group(0))
    return re.sub(r"&(#[xX][0-9a-fA-F]+|#\d+|[A-Za-z]+);", one, s, flags=re.A)


def _attr(attrs: str, name: str) -> Optional[str]:
    m = re.search(r"\b" + name + r'="([^"]*)"', attrs, re.A)
    return m.group(1) if m else None


def _list_label(n: int, kind: str) -> str:
    if kind in ("I", "i"):
        out = ""
        for value, numeral in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                               (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
            while n >= value:
                out += numeral
                n -= value
        return out if kind == "I" else out.lower()
    if kind in ("A", "a"):
        out = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            out = chr(ord(kind) + r) + out
        return out
    return str(n)


def _clean_block(s: str) -> str:
    lines = (re.sub(r" {2,}", " ", line).strip(" ") for line in s.translate(_TEXT_FIXES).split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """
    Plain text from HUDOC's HTML rendition: one block per paragraph, blocks
    separated by a blank line, a line break inside a paragraph kept as a
    single newline. Numbers that the HTML leaves to the browser (headings in
    <ol start="2" type="I">) are written out. Nothing else is changed: the
    characters are the Court's, non-breaking hyphens included; only
    non-breaking spaces become plain ones (see _TEXT_FIXES).

    Footnotes are appended as a list under a "FOOTNOTES" heading, and each
    footnote reference in the body is marked [fn N], so citations that the
    Court puts in footnotes remain greppable. N is the label printed in the
    judgment ("12", or "*" for a Registry note), exactly as printed; where a
    label occurs twice, the markers and the notes pair up in order.
    """
    blocks: list[str] = []
    notes: dict[str, list[str]] = {}
    parts: list[str] = []
    lists: list[list] = []      # [kind, next number] per open <ol>/<ul>
    divs = 0                    # <div> depth
    note: Optional[str] = None  # id of the footnote <div> we are in
    note_depth = 0
    skip = 0                    # inside <style>/<script>
    ref: Optional[str] = None   # id of the footnote link we are in
    ref_text: list[str] = []    # its printed label
    printed: dict[str, str] = {}  # footnote id -> its printed label

    def flush() -> None:
        text = _clean_block("".join(parts))
        parts.clear()
        if text:
            (notes.setdefault(note, []) if note else blocks).append(text)

    for m in _HTML_TOKEN.finditer(html):
        closing, tag, attrs, text = m.group(1), m.group(2), m.group(3), m.group(5)
        if text is not None:
            if skip:
                continue
            # A newline in the markup is plain whitespace; only <br> breaks a line.
            text = _html_unescape(re.sub(r"[\r\n]+", " ", text))
            (ref_text if ref else parts).append(text)
            continue
        if tag is None:
            continue  # comment
        tag = tag.lower()
        if tag in ("style", "script"):
            skip += -1 if closing else 1
            continue
        if tag == "a":
            if closing:
                if ref:
                    label = re.sub(r"^\[+|\]+$", "", _clean_block("".join(ref_text))).strip(" ")
                    if label and ref not in printed:
                        printed[ref] = label
                ref = None
                continue
            href = _attr(attrs, "href") or ""
            m_ref = re.fullmatch(r"#_ftn(?:ref)?(\d+)", href, re.A)
            if m_ref:
                ref, ref_text = m_ref.group(1), []
                if not href.startswith("#_ftnref"):
                    # Placeholder for the body marker; the label is only
                    # final once every footnote has been seen.
                    parts.append(f" {chr(0)}{ref}{chr(1)}")
            continue
        if tag == "br":
            parts.append("\n")
            continue
        if tag not in _HTML_BLOCK:
            continue
        flush()
        if tag == "div":
            if closing:
                divs -= 1
                if note and divs < note_depth:
                    note = None
            else:
                divs += 1
                m_note = re.fullmatch(r"_ftn(\d+)", _attr(attrs, "id") or "", re.A)
                if m_note:
                    note, note_depth = m_note.group(1), divs
        elif tag in ("ol", "ul"):
            if closing:
                if lists:
                    lists.pop()
            else:
                start = _attr(attrs, "start")
                kind = "•" if tag == "ul" else (_attr(attrs, "type") or "1")
                lists.append([kind, int(start) if start and re.fullmatch(r"[0-9]+", start) else 1])
        elif tag == "li" and not closing and lists:
            kind, n = lists[-1]
            parts.append("• " if kind == "•" else _list_label(n, kind) + ". ")
            lists[-1][1] = n + 1
    flush()

    # The printed label; Word's footnote id only if none was printed.
    def label(fid: str) -> str:
        return printed.get(fid) or fid

    out = list(blocks)
    if notes:
        out.append("FOOTNOTES")
        out.extend(f"[fn {label(fid)}] {' '.join(texts)}" for fid, texts in notes.items())
    text = "\n\n".join(out) + "\n"
    return re.sub(chr(0) + "([0-9]+)" + chr(1), lambda m: f"[fn {label(m.group(1))}]", text)


def pdf_to_text(pdf_path: Path) -> str:
    """
    Extract plain text from a PDF. Used only when HUDOC has no HTML
    rendition. Tries pypdf (pip install pypdf), then the poppler `pdftotext`
    binary. Page structure is kept but paragraph numbering is less reliable
    than in the HTML extraction.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except ModuleNotFoundError:
        PdfReader = None  # type: ignore
    if PdfReader is not None:
        try:
            reader = PdfReader(str(pdf_path))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            if text.strip():
                return text + "\n"
        except Exception as e:  # corrupt / encrypted
            print(f"pypdf failed on {pdf_path.name}: {e}", file=sys.stderr)
    if shutil.which("pdftotext"):
        out = pdf_path.with_name(pdf_path.stem + ".pdftotext.txt")
        proc = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), str(out)],
                              check=False, capture_output=True, text=True)
        if proc.returncode == 0 and _has_content(out):
            text = out.read_text(encoding="utf-8", errors="replace")
            out.unlink()
            return text
    raise RuntimeError(
        f"Cannot extract text from {pdf_path.name}: install pypdf "
        "(`pip install pypdf`) or poppler-utils (`pdftotext`). The PDF itself is cached."
    )


def fetch_text(itemid: str) -> Path:
    """
    Get the text of a judgment: from the HTML rendition HUDOC's reading view
    shows, or from the official PDF when HUDOC has no HTML (PDF-only items).
    """
    d = _item_dir(itemid)
    txt_path = d / "judgment.txt"
    old_docx = d / "judgment.docx"
    if old_docx.exists():
        # Left by a version before 1.3.0, whose text came from a home-made
        # DOCX extraction that lost heading numbers and non-breaking
        # hyphens. Rebuild that text from the HTML.
        old_docx.unlink()
        txt_path.unlink(missing_ok=True)
    if _has_content(txt_path):
        return txt_path

    # A Cloudflare challenge says nothing about whether the HTML exists, so
    # it is never a reason to settle for the PDF's weaker text.
    try:
        html_path = fetch_html(itemid)
        text = html_to_text(html_path.read_text(encoding="utf-8", errors="replace"))
        _write_text(txt_path, text)
        return txt_path
    except ChallengeError:
        raise
    except (RuntimeError, ValueError) as e:
        print(f"HTML extraction failed: {e}; trying PDF fallback...", file=sys.stderr)

    try:
        pdf_path = fetch_pdf(itemid)
        text = pdf_to_text(pdf_path)
        _write_text(txt_path, text)
        return txt_path
    except ChallengeError:
        raise
    except RuntimeError as e:
        raise RuntimeError(f"Both HTML and PDF extraction failed for {itemid}: {e}") from None


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
        try:
            p = fetch_pdf(itemid)
        except ChallengeError as e:
            raise ChallengeError(
                f"{e} The user can download the PDF in their own browser: {pdf_url(itemid)}"
            ) from None
    elif fmt == "text":
        p = fetch_text(itemid)
    else:
        raise SystemExit(f"unknown format {fmt}")

    if args.output:
        out = Path(args.output)
        _write_bytes(out, p.read_bytes())
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
            "pdf_url": pdf_url(itemid),
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
    if not _has_content(p):
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

    sp = sub.add_parser("fetch", help="Get the judgment as text or as the official PDF.")
    sp.add_argument("reference")
    sp.add_argument("--format", choices=("pdf", "text"), default="text")
    sp.add_argument("-o", "--output",
                    help="Also copy the result to this path (e.g. outputs/judgment.pdf).")
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

    # Judgment text and metadata contain characters outside cp1252; never let
    # the console encoding turn a successful fetch into a crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"hudoc: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
