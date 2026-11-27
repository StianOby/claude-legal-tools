#!/usr/bin/env python3
"""
zotero_book.py — download a book from nb.no, give it a text layer, and emit a
Zotero-ready RDF + PDF pair.

Run from the nbno skill's scripts/ folder (nb_download.py is the same
download without OCR, shrink or RDF):

    python zotero_book.py \\
        --id URN:NBN:no-nb_digibok_2008051600041 \\
        --out /path/to/outputs/folder \\
        [--nbsso "nbsso=<value>" | --cookie auto | --cookie /path/cookie.txt] \\
        [--size half|full] [--start N --stop M] [--keep-images] \\
        [--ocr auto|nb|tesseract] [--no-ocr] \\
        [--shrink-mode bitonal|grey|jpeg] [--no-rdf]

Auth, in short: `api.nb.no` authenticates by cookie, so `--nbsso` alone is
enough and `--bearer` is optional (kept for older DevTools captures that
happen to include one). Public-domain and Bokhylla items need no cookie at
all — Bokhylla only needs a Norwegian IP. FEIDE-licensed items need `--nbsso`
*and* an active digital loan taken by the user in a browser.

What it produces:

    <out>/AUTHOR_TITLE_(YEAR).pdf      — searchable (nb.no's own OCR where
                                         available, else Tesseract nor)
                                         and shrunk (bitonal text pages,
                                         JPEG covers/photos) by default
    <out>/AUTHOR_TITLE_(YEAR).rdf      — Zotero RDF, references the PDF
                                         as an imported-file attachment
                                         and the nb.no URL as a Web Link
                                         titled "eBok (nb.no)".
    <out>/AUTHOR_TITLE_(YEAR).zotero.json — the same item as Zotero JSON,
                                         for direct import with Zoteus.

The Zotero "URL" metadata field is intentionally left blank — the only link
to nb.no lives as a Web Link attachment on the imported item.

Pipeline:
  1. Resolve --id into a canonical nb.no item ID (digibok_NNN…).
  2. Fetch metadata from https://api.nb.no/catalog/v1/items/<URN>.
  3. For a geo-gated item, ask the image resolver for one tile of a
     mid-book page and stop on a 403 — every page would fail the same way;
     for a legal-deposit (NB) item with --nbsso, also stop when the
     catalogue shows no active loan.
     Then compute AUTHOR_TITLE_(YEAR) and the destination PDF path.
  4. Download the PDF with the in-process IIIF downloader, pages at half
     size (--size). It needs no credential for public-domain items or
     Bokhylla from a Norwegian IP, and takes --nbsso (or a --cookie file
     holding it) for FEIDE-licensed ones. Pages are kept in <out>/_pages/
     until the PDF is complete, so a re-run resumes.
  5. Add a text layer unless --no-ocr: nb.no's own OCR (ALTO, see
     alto_text.py) when the item serves it — public-domain books do —
     otherwise ocrmypdf (-l nor; the model is fetched from tessdata_fast
     when the sandbox lacks it). --ocr picks one explicitly. --no-ocr also
     skips the shrink, so a later ocr_chunked.py run sees unshrunk pages.
  6. Shrink the page images (shrink_pdf.py, --shrink-mode): bitonal by
     default. When OCR failed, the unshrunk PDF is kept as
     <base>.original.pdf so the OCR can be retried without a new download.
  7. Render the Zotero RDF and item JSON via zotero_rdf.write_zotero_files
     (shared/zotero-rdf/ in the repo), unless --no-rdf.

Designed to stream progress (each step prints a single line) so the user can
follow along in a Cowork session even when individual phases take a while.
Each subprocess call has its own timeout.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make the sibling zotero_rdf module importable regardless of the
# directory we're invoked from.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import zotero_rdf   # noqa: E402  (after sys.path mutation)


# ---------------------------------------------------------------------------
# Normalized metadata
# ---------------------------------------------------------------------------

@dataclass
class Creator:
    """A person or organisation associated with the book.

    creator_type:  "author" (default), "editor", "translator", "contributor".
    """

    surname: str = ""
    given: str = ""
    organization: str = ""    # used when surname/given are empty
    creator_type: str = "author"

    @property
    def is_person(self) -> bool:
        return bool(self.surname or self.given)


@dataclass
class NormalizedBook:
    """The book metadata nb.no gives us, before it becomes a Zotero item."""

    title: str
    short_title: str = ""
    subtitle: str = ""
    creators: List[Creator] = field(default_factory=list)
    publisher: str = ""
    place: str = ""
    year: str = ""                  # ISO year as string ("1890")
    date: str = ""                  # full ISO date when known ("1870-08-17");
                                    # newspaper issues have one, books do not
    language: str = ""              # ISO 639 code, two- or three-letter
    isbn: str = ""
    num_pages: str = ""             # string to allow "[358]" etc.
    abstract: str = ""
    series: str = ""
    edition: str = ""
    extra: str = ""                 # Zotero's Extra field


# The plugin's version (plugin.json); tests/nbno checks that they agree.
VERSION = "2.0.3"
USER_AGENT = f"nbno-skill/{VERSION} (+https://github.com/StianOby/claude-legal-tools)"


def _request(url: str, headers: Optional[Dict[str, str]] = None) -> urllib.request.Request:
    """A GET request with the skill's own User-Agent (never Python's
    default "Python-urllib/…", which some hosts refuse; see CLAUDE.md)."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})


def book_to_item(book: NormalizedBook) -> dict:
    """The Zotero item (Zotero's own JSON) for a book. Every nb.no item type
    is a Zotero Book: Zotero has no "newspaper issue" type. The URL field
    stays empty by design — the nb.no link is a Web Link attachment."""
    creators = []
    for c in book.creators:
        if c.surname and c.given:
            creators.append({"creatorType": c.creator_type,
                             "firstName": c.given, "lastName": c.surname})
        elif c.is_person or c.organization:
            creators.append({"creatorType": c.creator_type,
                             "name": c.surname or c.given or c.organization})
    title = book.title.strip()
    if book.subtitle:
        title = f"{title}: {book.subtitle.strip()}"
    fields = {
        "title": title,
        "shortTitle": book.short_title,
        "creators": creators,
        "series": book.series,
        "edition": book.edition,
        "place": book.place,
        "publisher": book.publisher,
        "date": book.date or book.year,
        "numPages": book.num_pages,
        "language": book.language,
        "ISBN": book.isbn,
        "abstractNote": book.abstract,
        "extra": book.extra,
    }
    item = {"itemType": "book"}
    item.update({k: v for k, v in fields.items() if v})
    return item


# ---------------------------------------------------------------------------
# ID handling
# ---------------------------------------------------------------------------

_URN_PREFIXES = ("URN:NBN:no-nb_", "urn:nbn:no-nb_", "urn:nbn:no-nb:")
# Underscores are part of many real ids, not just a separator after the
# type: newspapers are digavis_aftenposten_morgen_1_20150107_156_7_2 and
# journals digitidsskrift_2021052683055_001. Keep this in step with the
# identical pattern in scripts/browser/nbno_auth.js.
_TYPE_RE = re.compile(
    r"^(digibok|digavis|digifoto|digitidsskrift|digikart|digimanus|"
    r"digiprogramrapport|pliktmonografi|pliktperiodika)_[0-9A-Za-z_]+$"
)


def normalise_id(raw: str) -> str:
    """Strip URN prefix and validate the canonical form."""
    s = raw.strip()
    for p in _URN_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    if s.startswith("http"):
        raise SystemExit(
            "ERROR: nb.no /items/<hash> URLs do not contain the canonical "
            "ID. Click 'Referere/Sitere' on nb.no and paste the URN."
        )
    if not _TYPE_RE.match(s):
        raise SystemExit(
            f"ERROR: '{s}' is not a canonical nb.no media ID. Expected a type "
            "prefix followed by the item key, e.g. 'digibok_2008051600041', "
            "'digavis_aftenposten_morgen_1_20150107_156_7_2' or "
            "'digitidsskrift_2021052683055_001'."
        )
    return s


def urn_form(canonical_id: str) -> str:
    return f"URN:NBN:no-nb_{canonical_id}"


def items_page_url(canonical_id: str) -> str:
    """Public web URL for the items page (used as the Web Link target)."""
    return f"https://www.nb.no/items/{urn_form(canonical_id)}"


# ---------------------------------------------------------------------------
# nb.no metadata fetch
# ---------------------------------------------------------------------------

# nb.no's MARC "cre" / "aut" role codes that count as primary creators.
_AUTHOR_ROLES = {"aut", "cre"}
# "red" (redaktør) is nb.no's own code, often alone: Eckhoff, Rettskildelære
# 4. utg. (digibok_2009010704007) gives Helgesen only "red", the 5. utg.
# "red" + "edt".
_EDITOR_ROLES = {"edt", "red"}
_TRANSLATOR_ROLES = {"trl"}


class AccessHint:
    """Result of pre-flighting an item's access requirements via the catalog API.

    Set early in the pipeline so we can short-circuit a wasted no-auth attempt
    for FEIDE-licensed material instead of letting the download fail opaquely.
    """
    __slots__ = ("requires_auth", "geo_gated", "access_allowed_from",
                 "viewability", "login_text", "reason")

    def __init__(self, requires_auth: bool, geo_gated: bool,
                 access_allowed_from: str, viewability: str,
                 login_text: str, reason: str) -> None:
        self.requires_auth = requires_auth
        self.geo_gated = geo_gated
        self.access_allowed_from = access_allowed_from
        self.viewability = viewability
        self.login_text = login_text
        self.reason = reason

    def __repr__(self) -> str:
        return (f"AccessHint(requires_auth={self.requires_auth}, "
                f"geo_gated={self.geo_gated}, "
                f"access_allowed_from={self.access_allowed_from!r}, "
                f"viewability={self.viewability!r}, reason={self.reason!r})")


# accessAllowedFrom values, in increasing order of restriction:
#   EVERYWHERE — open, no credential, works from any IP
#   NORWAY     — Bokhylla: Norwegian IP, but no cookie
#   NB         — legal deposit: Norwegian IP *and* nbsso *and* a digital loan
_GEO_GATED_FROM = {"NORWAY", "NB"}
_COOKIE_GATED_FROM = {"NB"}


def check_nb_access(api_blob: dict) -> AccessHint:
    """Inspect the catalog response for signals that auth is required.

    Keys on `accessAllowedFrom`, which is a property of the item and is the
    same whoever asks. The other access fields are properties of *this
    request* and shift under you:

      - `viewability` is NONE anonymously and ALL once the caller may read it;
      - `legalDepositLoginText` is the "log in to read this" prompt, so it is
        present anonymously and **absent** once the caller is logged in;
      - `legalDepositReservationStatus` only appears for a logged-in user.

    Verified 2026-09-06 by reading digibok_2014050705024 anonymously and as a
    logged-in FEIDE user from the same IP a minute apart. Keying on those
    fields alone made this function report requires_auth=False for a
    FEIDE-licensed item whose images still 403 without nbsso — the exact case
    the pre-check exists to catch.
    """
    access = api_blob.get("accessInfo") or {}
    allowed_from = (access.get("accessAllowedFrom") or "").strip().upper()
    viewability = (access.get("viewability") or "").strip().upper()
    login_text = (access.get("legalDepositLoginText") or "").strip()

    geo_gated = allowed_from in _GEO_GATED_FROM
    requires_auth = False
    reason = ""
    if allowed_from in _COOKIE_GATED_FROM:
        requires_auth = True
        reason = (f"accessInfo.accessAllowedFrom == {allowed_from} "
                  "(legal deposit: needs nbsso and an active digital loan)")
    elif login_text:
        requires_auth = True
        reason = f"accessInfo.legalDepositLoginText present ({login_text[:80]!r})"
    elif viewability == "NONE" and allowed_from not in ("EVERYWHERE", "NORWAY"):
        # Keep the old signal as a backstop for item classes we haven't
        # characterised, but never let it fire on an item the API says is
        # readable from everywhere, nor on a Bokhylla item, where NONE means
        # a non-Norwegian IP, which no credential fixes (main() says so).
        requires_auth = True
        reason = "accessInfo.viewability == NONE"

    return AccessHint(requires_auth, geo_gated, allowed_from or "?",
                      viewability or "?", login_text, reason)

# ISO 639-2/B → Zotero language tag. Zotero accepts plain ISO 639-2 codes,
# but a few popular ones translate to two-letter forms for prettier display.
_LANG_TO_ZOTERO = {
    "nob": "nb",
    "nno": "nn",
    "nor": "no",
    "eng": "en",
    "dan": "da",
    "swe": "sv",
    "ger": "de",
    "fra": "fr",
    "spa": "es",
    "ita": "it",
    "rus": "ru",
    "lat": "la",
}


def fetch_nb_metadata(canonical_id: str, timeout: float = 30.0,
                      nbsso: Optional[str] = None) -> dict:
    """Hit api.nb.no for the JSON metadata blob.

    The endpoint needs no auth, but `accessInfo` is both IP- and
    session-dependent: the same Bokhylla item reports viewability NONE
    anonymously and ALL to a logged-in Norwegian session. Pass `nbsso` when
    you have it so the pre-check sees what the user's own session sees.
    """
    url = f"https://api.nb.no/catalog/v1/items/{urn_form(canonical_id)}"
    headers = {"Accept": "application/json"}
    if nbsso:
        headers["cookie"] = nbsso
    req = _request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _squash(value: Optional[str]) -> str:
    """Trim and collapse internal whitespace (nb.no emits double spaces where
    a non-sorting article was marked up)."""
    return " ".join((value or "").split())


def _split_name(name: str) -> Tuple[str, str]:
    """nb.no usually gives "Surname, Given" — split on the first comma."""
    if "," in name:
        surname, given = name.split(",", 1)
        return surname.strip(), given.strip()
    return name.strip(), ""


def _edition(value: Optional[str]) -> str:
    """Zotero Edition from `originInfo.edition`: the leading number when
    there is one ("5. utg. [redigert av] Jan E. Helgesen" -> "5", "[2.
    utg.]" -> "2", "6. utgave" -> "6"), else the text verbatim ("Ny utg.",
    "Rev. utg.") so the user can see it in Zotero and decide whether to
    replace it with a number, delete it or keep it."""
    m = re.match(r"\s*\[?\s*(\d{1,3})(?!\d)", value or "")
    return str(int(m.group(1))) if m else _squash(value)


def normalize_metadata(api_blob: dict) -> NormalizedBook:
    """Translate the nb.no JSON response into our NormalizedBook."""
    md = api_blob.get("metadata", {}) or {}
    title_infos = md.get("titleInfos") or []
    # `titleInfos[0].title` is the *sort* form: MODS strips a leading
    # non-sorting article into it, so "En bryggesjauers bekjennelser"
    # (digibok_2014050705024) arrives as "bryggesjauers bekjennelser" while
    # `metadata.title` keeps the article. The two agree for the vast
    # majority of items, so prefer the full form whenever it merely adds a
    # prefix, and keep the titleInfos form otherwise (it is the one that
    # excludes the subtitle).
    ti_title = _squash(title_infos[0].get("title") if title_infos else "")
    full_title = _squash(md.get("title"))
    subtitle = _squash(title_infos[0].get("subTitle")) if title_infos else ""
    if ti_title and full_title and ti_title != full_title \
            and full_title.endswith(ti_title):
        title = full_title
    else:
        title = ti_title or full_title

    creators: List[Creator] = []
    for p in md.get("people") or []:
        roles = {r.get("name", "") for r in p.get("roles") or []}
        if roles & _EDITOR_ROLES:
            kind = "editor"
        elif roles & _TRANSLATOR_ROLES:
            kind = "translator"
        elif roles & _AUTHOR_ROLES or not roles:
            # nb.no often omits roles on co-authors; treat as author by default.
            kind = "author"
        else:
            kind = "contributor"
        surname, given = _split_name(p.get("name", ""))
        if surname or given:
            creators.append(Creator(
                surname=surname, given=given, creator_type=kind
            ))

    origin = md.get("originInfo") or {}
    year = (origin.get("issued") or "").strip()
    # Newspaper issues carry `issued` as YYYYMMDD ("18700817"); books carry
    # a plain year. Keep `year` a year (basename, sorting) and put the full
    # ISO date in `date` for Zotero's date field. `issuedUntouched` is not
    # used: for serials it is the run's *start* year, not this issue's.
    date = ""
    m8 = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", year)
    if m8:
        date = "-".join(m8.groups())
        year = m8.group(1)
    publisher = (origin.get("publisher") or "").strip()
    edition = _edition(origin.get("edition"))
    place = _pick_place(md.get("geographic") or {})

    lang_code = ""
    for entry in md.get("languages") or []:
        code = (entry.get("code") or "").strip().lower()
        if code:
            lang_code = _LANG_TO_ZOTERO.get(code, code)
            break

    # nb.no reports modern books under `isbn13` and older ones under `isbn`;
    # either may be a bare string rather than a list (iterating a string
    # would otherwise yield its first character).
    isbn = ""
    identifiers = md.get("identifiers") or {}
    for key in ("isbn13", "isbn"):
        raw_isbn = identifiers.get(key)
        if not raw_isbn:
            continue
        if isinstance(raw_isbn, str):
            isbn = raw_isbn.strip()
        else:
            for ident in raw_isbn:
                isbn = ident.strip() if isinstance(ident, str) else str(ident)
                break
        if isbn:
            break

    num_pages = ""
    pc = md.get("pageCount")
    if isinstance(pc, int) and pc > 0:
        num_pages = str(pc)

    extras = []
    urn = (md.get("identifiers") or {}).get("urn")
    if urn:
        extras.append(f"URN: {urn}")
    return NormalizedBook(
        title=title,
        subtitle=subtitle,
        creators=creators,
        publisher=publisher,
        place=place,
        year=year,
        date=date,
        edition=edition,
        language=lang_code,
        isbn=isbn,
        num_pages=num_pages,
        extra="\n".join(extras),
    )


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------

_NO_PLACE = {"S.l.", "s.l.", "[S.l.]"}   # "sine loco" — no real value


def _pick_place(geo: dict) -> str:
    """One publication place from nb.no's `geographic` block.

    Books give `placeString: "Oslo"`. Newspapers give the whole hierarchy,
    `"Norge;Oslo;;Oslo;;;;"`, with `city` alongside. Prefer `city`, then
    the most specific (last) non-empty segment of `placeString`.
    """
    city = (geo.get("city") or "").strip()
    if city and city not in _NO_PLACE:
        return city
    segments = [seg.strip() for seg in (geo.get("placeString") or "").split(";")]
    segments = [seg for seg in segments if seg and seg not in _NO_PLACE]
    return segments[-1] if segments else ""


_FS_SAFE = re.compile(r"[^A-Za-z0-9._\-()]+")
_TRANSLIT = str.maketrans({
    "æ": "ae", "Æ": "Ae", "ø": "oe", "Ø": "Oe", "å": "aa", "Å": "Aa",
    "ß": "ss", "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th",
})


def _slug(s: str, maxlen: int = 60) -> str:
    """ASCII-fold + collapse to underscore-separated tokens.

    Letters with no decomposition (æ ø å) are transliterated first —
    NFKD alone turns "Jægertidende" into "Jgertidende".
    """
    s = s.translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _FS_SAFE.sub("_", s).strip("_")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("_")
    return s or "Untitled"


def compute_basename(book: NormalizedBook) -> str:
    """Compose AUTHOR_TITLE_(YEAR), filesystem-safe.

    Picks the first author's surname; falls back to the first creator of any
    kind. With no creator at all (newspaper issues, anonymous works) the
    author part is omitted rather than written as "Unknown".
    """
    surname = ""
    for c in book.creators:
        if c.creator_type == "author" and c.surname:
            surname = c.surname
            break
    if not surname:
        for c in book.creators:
            if c.is_person:
                surname = c.surname or c.given
                break
            if c.organization:
                surname = c.organization
                break
    title_for_name = book.title.split(":")[0]  # drop subtitle
    year = (book.year or "n.d.").strip()
    head = f"{_slug(surname, 30)}_" if surname else ""
    return f"{head}{_slug(title_for_name, 60)}_({_slug(year, 8)})"


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def _fetch_manifest(canonical_id: str, hdr_api: Dict[str, str],
                    timeout: float = 30.0) -> dict:
    """Fetch the IIIF presentation manifest.

    nb.no exposes two endpoints with different coverage:
      - /catalog/v1/items/<id>/manifest             — works for most digibok
      - /catalog/v1/iiif/URN:NBN:no-nb_<id>/manifest — required for some
        pliktmonografi items where /items/ returns 404.

    We try the first and fall back to the second on 404, so callers don't
    need to know which form a given item uses.
    """
    candidates = [
        f"https://api.nb.no/catalog/v1/items/{canonical_id}/manifest",
        f"https://api.nb.no/catalog/v1/iiif/{urn_form(canonical_id)}/manifest",
    ]
    last_err: Optional[Exception] = None
    for url in candidates:
        try:
            req = _request(url, headers=hdr_api)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404:
                continue
            raise
    raise SystemExit(
        "ERROR: manifest fetch failed for both /items/ and /iiif/ endpoints "
        f"({last_err!r})."
    )


# HTTP statuses worth retrying: rate limiting and transient server errors.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (2.0, 5.0, 12.0)


def _read_url(url: str, headers: Dict[str, str], timeout: float) -> bytes:
    """GET `url` and return the body, retrying transient failures (timeouts,
    dropped connections, 429 and 5xx) with backoff. 403/404 and other
    client errors are raised at once — they mean "not allowed" or "not
    there", which a retry will not change."""
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            req = _request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in _RETRY_STATUS or attempt == len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[attempt]
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after and retry_after.isdigit():
                delay = min(float(retry_after), 60.0)
        except (OSError, http.client.HTTPException):
            # URLError, timeouts, dropped connections, truncated bodies.
            if attempt == len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[attempt]
        time.sleep(delay)
    raise AssertionError("unreachable")


def _fetch_iiif_info(base_url: str, hdr_img: Dict[str, str],
                     timeout: float = 15.0) -> dict:
    """GET <base_url>/info.json — the IIIF Image API descriptor.

    Returns a dict with at least `width`, `height`, and `sizes` (a list of
    {width, height} entries that the resolver will actually serve without
    silently downsampling).
    """
    return json.loads(_read_url(f"{base_url}/info.json", hdr_img, timeout).decode("utf-8"))


# Page sizes. nb.no's resolver serves each scan at full size and at 1/2,
# 1/4, … of it (info.json `sizes`), and asking for any other width gets a
# silently smaller image. Half size (~1100 px wide, ~145 dpi on a book page)
# is the default: OCR on it matched full-size OCR 99.6 % on three law books,
# it needs 4 tiles a page where full size needs 12, and the bitonal shrink
# scales it up 2x to sharp black-and-white pages (measured 2026-10-23).
SIZES = {"half": 2, "full": 1}


class PageImageError(Exception):
    """nb.no answered a page or tile request with something that is not the
    image asked for: an empty body, a non-image, or the wrong pixel size."""


# Pillow refuses images above ~179 megapixels as possible decompression
# bombs. nb.no's maps are larger at full size (18217 x 13488 = 246 MP,
# 17071 x 24236 = 414 MP; 2026-11-27), and the pages come from nb.no at the
# size its manifest states, so the limit is raised well above any scan.
MAX_IMAGE_PIXELS = 2_000_000_000


# The download threads all reach _ensure_pillow at once; without this lock
# each of them started its own pip install (8 at once on the local VM,
# 2026-11-27).
_PILLOW_LOCK = threading.Lock()


def _ensure_pillow():
    """Import PIL.Image, pip-installing Pillow into _pylib on first use (the
    local VM's Python has none, 2026-11-26), as img2pdf and ocrmypdf are.
    Raises Pillow's image-size limit to MAX_IMAGE_PIXELS. Thread-safe."""
    with _PILLOW_LOCK:
        return _ensure_pillow_locked()


def _ensure_pillow_locked():
    for attempt in range(2):
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            return Image
        except ImportError:
            if attempt == 0:
                _ensure_pylib_on_path()   # installed by an earlier call?
    _pip_install_to_pylib(["Pillow"])   # prints the one "[pip] installing" line
    import importlib
    importlib.invalidate_caches()   # _pylib's directory listing is cached
    try:
        from PIL import Image  # noqa: F811
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        return Image
    except ImportError as exc:
        raise SystemExit(
            "ERROR: Pillow is required and could not be installed. Install with: "
            f"pip install --target {_pylib_target()} --break-system-packages "
            f"-c {CONSTRAINTS} Pillow"
        ) from exc


def _read_image(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, Tuple[int, int]]:
    """GET an image and return (bytes, (w, h)). Raises PageImageError on an
    empty or unreadable body: nb.no has answered some region requests with
    HTTP 200 and no body at all (2026-11-26), which must fail the page with
    a clear message rather than as a PIL exception or a blank tile."""
    import io
    Image = _ensure_pillow()
    data = _read_url(url, headers, timeout)
    if not data:
        raise PageImageError(f"empty response (HTTP 200, no body) for {url}")
    try:
        with Image.open(io.BytesIO(data)) as im:
            size = im.size
    except Exception as exc:  # noqa: BLE001 - PIL raises several kinds
        raise PageImageError(f"not an image ({len(data)} bytes) for {url}") from exc
    return data, size


def _fetch_page_singleshot(
    base_url: str, scale: int, hdr_img: Dict[str, str],
    timeout: float = 30.0,
) -> Tuple[Optional[bytes], Optional[Tuple[int, int]]]:
    """One request for the whole page at 1/`scale` of full size
    (/full/pct:50/ for half, /full/full/ for full). Returns (bytes, (w,h)).

    The (w,h) tuple is the *actual* size of the returned image as measured by
    PIL — callers compare it with the canvas size to detect silent
    downsampling. Returns (None, None) when refused (403/404) or answered
    with an empty or unreadable body; the caller then uses tiles.

    Which items get a single image at half size has changed: on 2026-10-23
    anything but public domain got 403 above 1/4 size; on 2026-11-26 a loaned
    legal-deposit book (NB) was served every page at half size this way. So
    it is tried first for every item.
    """
    size = "full" if scale == 1 else f"pct:{100 // scale}"
    url = f"{base_url}/full/{size}/0/default.jpg"
    try:
        return _read_image(url, hdr_img, timeout)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None, None
        raise
    except PageImageError:
        return None, None


def _tile_starts(full: int, step: int) -> List[int]:
    """Region origins along one axis of a canvas `full` px long, `step` px a
    region. The last region is moved back so it keeps the whole step and
    overlaps its neighbour: nb.no answers a narrower region at the right
    edge with an empty body, and one moved back with the full width works
    (2026-11-26). An axis no longer than one step is one region."""
    if full <= step:
        return [0]
    n = -(-full // step)
    return [i * step for i in range(n - 1)] + [full - step]


def _fetch_page_tiled(
    base_url: str, info: dict, hdr_img: Dict[str, str],
    scale: int = 1, tile_size: int = 1024, timeout: float = 30.0,
) -> Optional[bytes]:
    """Fetch a canvas at 1/`scale` of full size as regionByPx tiles and
    stitch with PIL. Returns None when a tile is refused (403/404).

    The resolver serves any region, scaled down, as long as the image it
    returns is at most 1024 px a side. So each tile is a region of
    1024*scale px, returned at 1024: 4 tiles a page at half size, 12 at
    full (2026-10-23).

    Every tile is checked before it is pasted: an empty body, or a tile
    whose pixel size is not the one asked for, fails the page with
    PageImageError. On 2026-11-26 nb.no returned a region at full size when
    asked for `,h` (height only), and pasting those quietly gave pages that
    showed only their top-left quarter.
    """
    import io
    Image = _ensure_pillow()
    full_w = int(info.get("width") or 0)
    full_h = int(info.get("height") or 0)
    if full_w <= 0 or full_h <= 0:
        return None
    out_w, out_h = -(-full_w // scale), -(-full_h // scale)
    tiles: List[Tuple[int, int, bytes]] = []
    step = tile_size * scale
    for y in _tile_starts(full_h, step):
        for x in _tile_starts(full_w, step):
            tw = min(step, full_w)
            th = min(step, full_h)
            want = (-(-tw // scale), -(-th // scale))
            size = "full" if scale == 1 else f"{want[0]},"
            url = f"{base_url}/{x},{y},{tw},{th}/{size}/0/default.jpg"
            try:
                data, got = _read_image(url, hdr_img, timeout)
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    return None
                raise
            # 1 px of slack for the server's rounding of an odd length.
            if abs(got[0] - want[0]) > 1 or abs(got[1] - want[1]) > 1:
                raise PageImageError(
                    f"tile {x},{y},{tw},{th} came back {got[0]}x{got[1]}, "
                    f"expected {want[0]}x{want[1]}")
            # A tile reaching the far edge is pasted flush with the canvas
            # edge: x // scale rounds down, and with an odd length that left
            # the last row or column white.
            tiles.append((out_w - got[0] if x + tw >= full_w else x // scale,
                          out_h - got[1] if y + th >= full_h else y // scale, data))
    # Downloading is network-bound and runs on all --workers threads; the
    # stitched canvas and JPEG encode are CPU- and memory-bound, so only one
    # page per usable CPU is stitched at a time.
    with _STITCH_SLOTS:
        canvas = Image.new("RGB", (out_w, out_h), "white")
        for x, y, data in tiles:
            canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"), (max(0, x), max(0, y)))
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# A4 portrait height in inches (297 mm). Each downloaded canvas is treated as
# one A4-ish book page; anchoring its physical height to A4 lets us derive the
# correct DPI from the actual pixel height. This matters because the cover and
# the content pages of an nb.no book are scanned at *different* pixel heights
# (e.g. a 2560 px cover vs 3368 px content pages), so a single fixed DPI
# mis-sizes one or the other.
_A4_HEIGHT_IN = 297.0 / 25.4  # ≈ 11.69


def _page_dpi(height_px: int) -> int:
    """DPI that places a `height_px`-tall image at A4 height (297 mm)."""
    return max(1, round(height_px / _A4_HEIGHT_IN))


def _assemble_pages_to_pdf(page_paths: List[str], out_pdf: Path) -> None:
    """Bundle page JPEGs into a PDF with a correct, per-page A4 MediaBox.

    Two DPI traps this guards against — both seen in real downloads:

    * PIL's PDF writer applies ONE resolution to every page in a save_all
      run and defaults to 72 DPI, so a multi-page book comes out with a
      huge (poster-size) MediaBox.
    * img2pdf honours the DPI embedded in each JPEG and falls back to 96
      DPI when none is present (again poster-size); it also ignores its own
      dpi= argument when JPEG metadata is present. So the DPI must be baked
      into each JPEG's metadata, not passed as a convert() argument.

    We compute each page's DPI from its real pixel height (anchored to A4),
    re-save each JPEG with that DPI embedded, and let img2pdf assemble them
    (compact JPEG streams, exact per-page A4 MediaBox). If img2pdf can't be
    imported or installed, we fall back to PIL at the median per-page DPI —
    not exact for mixed page sizes, but far better than the 72 DPI default.
    """
    Image = _ensure_pillow()

    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        import img2pdf  # noqa: F401
    except ImportError:
        _pip_install_to_pylib(["img2pdf"])
        try:
            import img2pdf  # type: ignore  # noqa: F811
        except ImportError:
            img2pdf = None  # type: ignore

    if img2pdf is not None:
        dpi_paths: List[str] = []
        for p in page_paths:
            with Image.open(p) as im:
                im = im.convert("RGB")
                dpi = _page_dpi(im.height)
                dp = str(Path(p).with_suffix(".dpi.jpg"))
                im.save(dp, "JPEG", quality=95, dpi=(dpi, dpi))
                dpi_paths.append(dp)
        try:
            with open(out_pdf, "wb") as fh:
                fh.write(img2pdf.convert(dpi_paths))
        finally:
            for dp in dpi_paths:
                try:
                    os.unlink(dp)
                except OSError:
                    pass
        return

    # Fallback: single-resolution PIL PDF at the median per-page DPI.
    dpis = []
    for p in page_paths:
        with Image.open(p) as im:
            dpis.append(_page_dpi(im.height))
    dpis.sort()
    median_dpi = dpis[len(dpis) // 2] if dpis else 200
    print(f"[pdf] img2pdf unavailable; assembling with PIL at {median_dpi} DPI "
          "(uniform — mixed page sizes may be slightly off).")
    images = [Image.open(p).convert("RGB") for p in page_paths]
    images[0].save(str(out_pdf), save_all=True, append_images=images[1:],
                   resolution=float(median_dpi))


def download_via_iiif(
    canonical_id: str,
    out_pdf: Path,
    bearer: Optional[str] = None,
    nbsso: Optional[str] = None,
    size: str = "half",
    workers: int = 12,
    tiles: str = "auto",
    start: Optional[int] = None,
    stop: Optional[int] = None,
    keep_images: bool = False,
) -> dict:
    """Fast in-process downloader.

    Pulls the IIIF manifest and downloads each canvas at `size` ("half" or
    "full", see SIZES): in one request where nb.no allows it, otherwise as
    tiles. A one-request page smaller than the canvas says it should be (a
    silent downsample) is fetched again as tiles.

    start/stop select a 1-based, inclusive range of manifest canvases (by
    position, covers included); stop is clamped to the number of canvases. Page numbers, placeholders and the returned "canvases" are
    relative to the selected range (page 1 = canvas `start`).

    Auth is optional. `api.nb.no` serves manifests and metadata without any
    credential and otherwise authenticates by cookie, so `bearer` is never
    required — when it is absent the `nbsso` cookie is sent to api.nb.no as
    well, which is what makes the response reflect the user's own session.
    Public-domain and Bokhylla items need no credential at all (Bokhylla
    needs a Norwegian IP instead); only FEIDE-licensed items require `nbsso`
    plus a digital loan the user has taken in a browser.

    tiles ∈ {"auto", "always", "never"}:
      - auto:   one request first, for every item; tiles on 403, an empty
                answer or a silent downsample. Once a few pages have been
                refused and none served, the rest go straight to tiles.
      - always: skip the one request; tile every page
      - never:  one request only

    When the first _EARLY_PAGES pages all fail, the run stops there with
    the access hint instead of spending its time on a book it cannot get.
    Every request retries transient failures (timeouts, 429, 5xx), and pages
    that still fail get a second, slower pass. A page that cannot be had at
    all is NOT dropped: it becomes a placeholder page saying so, so every
    later page keeps its page number in the PDF (kildesjekk and citations
    depend on that). Returns {"pages", "missing", "canvases"} — `missing`
    lists the 1-based PDF page numbers that are placeholders, which the
    caller must tell the user about; `canvases` gives each PDF page's canvas
    name (None for a placeholder), which the ALTO text layer is keyed on.

    Resume: pages are saved in pages_dir(out_pdf, size) beside the PDF. A run
    that stops early (the ~170 s call limit, an error) or leaves placeholders
    keeps that folder, and a re-run with the same arguments fetches only the
    pages not yet there. Once every page is in the PDF the folder is removed,
    or, with keep_images, renamed to <pdf stem>_images/ beside the PDF.
    """
    if start is not None and start < 1:
        raise ValueError(f"start must be >= 1 (got {start})")
    if stop is not None and stop < (start or 1):
        raise ValueError(f"stop must be >= start (got start={start}, stop={stop})")
    if size not in SIZES:
        raise ValueError(f"size must be one of {sorted(SIZES)} (got {size!r})")
    pages = pages_dir(out_pdf, size)
    pages.mkdir(parents=True, exist_ok=True)
    result = _download_via_iiif(canonical_id, out_pdf, bearer, nbsso,
                                SIZES[size], workers, tiles, pages,
                                start, stop)
    if result["missing"]:
        print(f"[iiif] the pages downloaded so far are kept in {pages}; "
              "re-running the same command fetches only the missing ones.")
        return result
    if keep_images:
        images = out_pdf.parent / f"{out_pdf.stem}_images"
        shutil.rmtree(images, ignore_errors=True)
        images.mkdir(parents=True)
        # Only the downloaded pages: not placeholders (page_NNNN.missing.jpg)
        # or a .dpi.jpg left by an interrupted PDF assembly.
        for p in sorted(pages.glob("page_[0-9][0-9][0-9][0-9].jpg")):
            p.replace(images / p.name)
        result["images"] = str(images)
        print(f"[iiif] page images kept in {images}")
    shutil.rmtree(pages, ignore_errors=True)
    try:
        pages.parent.rmdir()   # _pages/, when no other download is pending
    except OSError:
        pass
    return result


def pages_dir(out_pdf: Path, size: str = "half") -> Path:
    """Where download_via_iiif keeps the pages of `out_pdf` between runs.
    The PDF's name already carries the page range (_c<N>-<M>); the size is
    added because half- and full-size pages must not mix in one PDF."""
    return out_pdf.parent / "_pages" / f"{out_pdf.stem}_{size}"


# Pages fetched before deciding that the whole book will fail (see above).
_EARLY_PAGES = 8
_NO_PAGES_HINT = (
    "Check, in this order: (1) is the egress IP Norwegian? "
    "accessAllowedFrom NORWAY/NB items 403 on every page regardless of "
    "login; (2) for a FEIDE-licensed item, has the user taken the digital "
    "loan in a browser (legalDepositReservationStatus == TAKENBYCURRENTUSER) "
    "and is --nbsso set and still valid?")


def _download_via_iiif(canonical_id, out_pdf, bearer, nbsso, scale,
                       workers, tiles, tmpdir: Path,
                       start: Optional[int] = None,
                       stop: Optional[int] = None) -> dict:
    from concurrent.futures import ThreadPoolExecutor

    referer = f"https://www.nb.no/items/{urn_form(canonical_id)}"
    hdr_api: Dict[str, str] = {}
    if bearer:
        hdr_api["authorization"] = bearer
    elif nbsso:
        hdr_api["cookie"] = nbsso
    hdr_img = {"referer": referer}
    if nbsso:
        hdr_img["cookie"] = nbsso

    manifest = _fetch_manifest(canonical_id, hdr_api)
    canvases = manifest["sequences"][0]["canvases"]
    if start is not None or stop is not None:
        total = len(canvases)
        lo = start or 1
        hi = min(stop, total) if stop is not None else total
        if lo > total:
            raise SystemExit(f"ERROR: --start {lo} is beyond the {total} canvases "
                             "in the manifest.")
        canvases = canvases[lo - 1:hi]
        print(f"[iiif] page range: canvases {lo}-{hi} of {total}")

    entries: List[Dict[str, Any]] = []
    for c in canvases:
        canvas_name = c["@id"].split("/")[-1]
        base = c["images"][0]["resource"]["service"]["@id"]
        entries.append({"canvas": canvas_name, "base_url": base,
                        "width": int(c.get("width") or 0),
                        "height": int(c.get("height") or 0)})

    label = "half size" if scale == 2 else "full size"
    how = {"always": "as tiles", "never": "one request each",
           "auto": "one request each, tiles where refused"}[tiles]
    print(f"[iiif] manifest has {len(entries)} canvases; pages at {label}, {how}")

    def tiled(entry) -> Optional[bytes]:
        try:
            info = _fetch_iiif_info(entry["base_url"], hdr_img)
        except urllib.error.HTTPError:
            return None
        return _fetch_page_tiled(entry["base_url"], info, hdr_img, scale=scale)

    # --tiles auto: after this many refused one-request pages, with none
    # served, the rest of the book goes straight to tiles (a Bokhylla book
    # would otherwise cost one refused request per page). Updated from
    # several threads without a lock; a lost update only delays the switch.
    single = {"served": 0, "refused": 0}
    REFUSALS_BEFORE_TILES = 3

    # Every page reports how it was fetched and the caller tallies the modes;
    # counting inside the workers would race (12 threads, non-atomic +=).
    def fetch_page(idx_entry: Tuple[int, Dict[str, Any]]) -> Tuple[int, Optional[str], str]:
        idx, entry = idx_entry
        if entry["canvas"].endswith("_C2"):
            return idx, None, "skipped_c2"
        path = tmpdir / f"page_{idx:04d}.jpg"
        if path.exists():
            return idx, str(path), "cached"   # from an earlier run (resume)

        data: Optional[bytes] = None
        mode = "single"

        if tiles == "always" or (
                tiles == "auto" and not single["served"]
                and single["refused"] >= REFUSALS_BEFORE_TILES):
            data = tiled(entry)
            mode = "tiled"
        else:
            data, actual = _fetch_page_singleshot(entry["base_url"], scale, hdr_img)
            want_w = -(-entry["width"] // scale) if entry["width"] else 0
            want_h = -(-entry["height"] // scale) if entry["height"] else 0
            if data is not None and actual is not None:
                # Tolerate 1–4 px of rounding; anything smaller is a
                # silent downsample.
                if (want_w and actual[0] < want_w - 4) or (want_h and actual[1] < want_h - 4):
                    mode = "single_downsampled"
                    if tiles == "auto":
                        retry = tiled(entry)
                        if retry is not None:
                            data = retry
                            mode = "tiled_after_downsample"
                else:
                    single["served"] += 1
            elif tiles == "auto":
                # Refused or empty → try tiles.
                single["refused"] += 1
                data = tiled(entry)
                if data is not None:
                    mode = "tiled_after_403"

        if data is None:
            return idx, None, mode + "_failed"
        # Written under another name and renamed, so a run killed mid-write
        # never leaves a truncated page that the next run takes as done.
        part = path.with_name(path.name + ".part")
        part.write_bytes(data)
        os.replace(part, path)
        return idx, str(path), mode

    def fetch_page_safe(idx_entry):
        # One page's network error (after _read_url's retries) must not
        # abort the other pages of the book.
        try:
            return fetch_page(idx_entry)
        except Exception as e:  # noqa: BLE001
            return idx_entry[0], None, f"error_failed ({type(e).__name__}: {e})"

    t0 = time.time()
    results: Dict[int, Optional[str]] = {}
    modes: Dict[int, str] = {}
    work = list(enumerate(entries, start=1))
    have = sum(1 for i, _ in work if (tmpdir / f"page_{i:04d}.jpg").exists())
    if have:
        print(f"[iiif] resuming: {have} of {len(work)} pages already downloaded in {tmpdir}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # The first pages on their own: when every one of them fails, so
        # will the rest (no Norwegian IP, no loan, an expired cookie), and
        # fetching and retrying a whole book of failures used up a 170 s
        # call with nothing written (2026-11-26).
        for idx, path, mode in pool.map(fetch_page_safe, work[:_EARLY_PAGES]):
            results[idx] = path
            modes[idx] = mode
        tried = [m for m in modes.values() if m != "skipped_c2"]
        if len(work) > _EARLY_PAGES and tried and not any(results.values()):
            raise SystemExit(
                f"ERROR: the first {len(tried)} pages all failed, so the rest "
                "were not tried.\n       First failure: "
                f"{next(m for m in modes.values() if m != 'skipped_c2')[:200]}\n"
                f"       {_NO_PAGES_HINT}")
        for idx, path, mode in pool.map(fetch_page_safe, work[_EARLY_PAGES:]):
            results[idx] = path
            modes[idx] = mode

    # Second pass for failed pages, two at a time after a pause: a burst of
    # 429s or a flaky tile server usually lets them through on a retry.
    retry = [i for i, m in modes.items() if m.endswith("_failed") or "_failed " in m]
    if retry:
        print(f"[iiif] {len(retry)} page(s) failed; retrying them more slowly ...")
        time.sleep(5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for idx, path, mode in pool.map(
                fetch_page_safe, [(i, entries[i - 1]) for i in retry]
            ):
                results[idx] = path
                modes[idx] = mode

    elapsed = time.time() - t0
    ok = sum(1 for v in results.values() if v)
    tile_count = sum(1 for m in modes.values() if m.startswith("tiled"))
    downsample_count = sum(1 for m in modes.values() if "downsample" in m)
    failed = sorted(i for i, m in modes.items() if "_failed" in m)
    print(f"[iiif] {ok}/{len(entries)} pages in {elapsed:.1f}s "
          + (f"({have} from the earlier run) " if have else "")
          + f"(tiled: {tile_count}, single-shot downsamples observed: "
          f"{downsample_count}"
          + (f", failed: {len(failed)}" if failed else "")
          + "); assembling PDF...")

    page_paths = [results[i] for i in sorted(results) if results[i]]
    if not page_paths:
        raise SystemExit(f"ERROR: no pages downloaded. {_NO_PAGES_HINT}")

    # A failed page becomes a placeholder in its own place, so the pages
    # after it keep their numbers. PDF page numbers count only the pages
    # that go into the PDF (the _C2 canvases are skipped).
    ordered: List[str] = []
    missing: List[int] = []
    page_canvases: List[Optional[str]] = []
    for idx in sorted(results):
        if modes[idx] == "skipped_c2":
            continue
        page_canvases.append(entries[idx - 1]["canvas"] if results[idx] else None)
        if results[idx]:
            ordered.append(results[idx])
        else:
            ordered.append(_placeholder_page(tmpdir, idx, entries[idx - 1]["canvas"],
                                             page_paths[0], modes[idx]))
            missing.append(len(ordered))
    _assemble_pages_to_pdf(ordered, out_pdf)
    if missing:
        print(f"[iiif] WARNING: {len(missing)} page(s) could not be downloaded and are "
              f"placeholder pages in the PDF: {missing}. The other pages keep their "
              "page numbers. Run the download again to fill them in, and tell the "
              "user which pages are missing.")
        for idx in failed:
            print(f"[iiif]   canvas {entries[idx - 1]['canvas']}: {modes[idx]}")
    return {"pages": len(ordered), "missing": missing, "canvases": page_canvases}


def _placeholder_page(tmpdir: Path, idx: int, canvas: str, like: str, why: str) -> str:
    """A white page the size of `like`, saying which page is missing."""
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(like) as ref:
        size = ref.size
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=max(24, size[0] // 30))
    except TypeError:  # Pillow < 10.1 has no sized default font
        font = ImageFont.load_default()
    text = (f"PAGE NOT DOWNLOADED\n\nmanifest canvas {idx} ({canvas})\n"
            f"{why[:120]}\n\nRun the download again to fill it in.")
    draw.multiline_text((size[0] // 12, size[1] // 3), text, fill="black", font=font, spacing=12)
    path = tmpdir / f"page_{idx:04d}.missing.jpg"
    img.save(path, "JPEG", quality=80)
    return str(path)


# The durable cookie file auth.md describes, for --cookie auto.
DEFAULT_COOKIE = Path.home() / ".nbno" / "cookie.txt"
# nb.no cookies live 24-48 h. A stale file is well-formed, so nothing rejects
# it, and its 403s look like a geo or loan problem.
COOKIE_STALE_HOURS = 24


def nbsso_from_cookie_arg(cookie: str) -> str:
    """The nbsso pair from --cookie <file|auto>, with a warning when the file
    is old enough to have expired. Exits 4 when there is no usable file."""
    from geo_check import nbsso_from_cookie_file
    path = DEFAULT_COOKIE if cookie == "auto" else Path(cookie).expanduser()
    if not path.is_file():
        print(f"ERROR: no cookie file at {path}. Make one as auth.md describes "
              "(two lines: 'authorization=' and 'cookie=nbsso=<value>; _nblb=<value>'), "
              "or pass --nbsso.", file=sys.stderr)
        raise SystemExit(4)
    nbsso = nbsso_from_cookie_file(str(path))
    if not nbsso:
        print(f"ERROR: cookie file {path} has no 'cookie=' line with an nbsso= pair. "
              "Expected: 'cookie=nbsso=<value>; _nblb=<value>'.", file=sys.stderr)
        raise SystemExit(4)
    age_h = (time.time() - path.stat().st_mtime) / 3600
    if age_h >= COOKIE_STALE_HOURS:
        print(f"[auth] WARNING: cookie file is {age_h:.0f} h old; nb.no cookies expire "
              "after roughly 24-48 h. If pages 403, re-capture it before debugging "
              "geo or the loan.")
    print(f"[auth] using the nbsso cookie from {path}")
    return nbsso


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def usable_cpus() -> int:
    """CPUs this process may actually use. os.cpu_count() reports the host's
    cores; a sandbox limited by CPU affinity or a cgroup quota gets fewer."""
    n = os.cpu_count() or 1
    try:
        n = min(n, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            n = min(n, int(quota) // int(period))
    except (OSError, ValueError):
        pass
    return max(1, n)


# Pages being stitched from tiles at once (see _fetch_page_tiled).
_STITCH_SLOTS = threading.BoundedSemaphore(usable_cpus())


def default_ocr_jobs() -> int:
    """Parallel ocrmypdf workers: half the usable CPUs, at most 4. Every
    worker runs Ghostscript and a multi-threaded Tesseract, so one worker per
    core already oversubscribes; on a 2-vCPU Cowork sandbox the old default
    of 4 thrashed to ~24 s/page against ~4 s/page with 1."""
    return max(1, min(4, usable_cpus() // 2))


def ocr_env(jobs: int) -> dict:
    """Environment for ocrmypdf: cap Tesseract's OpenMP threads so that
    jobs x threads stays within the usable CPUs."""
    env = os.environ.copy()
    env.setdefault("OMP_THREAD_LIMIT", str(max(1, usable_cpus() // jobs)))
    return env


# Language models come from tessdata_fast, the set Debian/Ubuntu package.
# Tesseract has no Nynorsk model: `nor` covers Norwegian.
TESSDATA_URL = ("https://github.com/tesseract-ocr/tessdata_fast/raw/main/"
                "{code}.traineddata")


def _tessdata_dir() -> Path:
    """Where fetched language models live: beside _pylib, so they survive
    across Cowork bash calls the same way the pip installs do."""
    return _pylib_target().parent / "_tessdata"


def _list_langs() -> Tuple[set, Optional[Path]]:
    """Installed tesseract languages, and the tessdata dir they come from
    (read from the 'List of available languages in "<dir>"' header)."""
    out = subprocess.run(["tesseract", "--list-langs"],
                         capture_output=True, text=True, timeout=10)
    langs, source = set(), None
    for ln in (out.stdout + out.stderr).splitlines():
        ln = ln.strip()
        if ln.startswith("List of available"):
            m = re.search(r'"([^"]+)"', ln)
            if m:
                source = Path(m.group(1))
        elif ln and " " not in ln:
            langs.add(ln)
    if source is None or source.resolve() == _tessdata_dir().resolve():
        # No dir printed, or it is our own fetch dir (TESSDATA_PREFIX from an
        # earlier run): find the system one so its files get copied along.
        source = _guess_tessdata_dir() or source
    return langs, source


# Tesseract 4.x prints "List of available languages (2):" without the
# directory (seen on the Cowork local VM, 4.1.1, 2026-09-30). Without it
# _fetch_tessdata() copied nothing and pointed TESSDATA_PREFIX at a dir with
# only the fetched model, so tesseract could not even load eng.
_TESSDATA_GLOBS = (
    "/usr/share/tesseract-ocr/*/tessdata",
    "/usr/share/tesseract-ocr/tessdata",
    "/usr/share/tessdata",
    "/usr/local/share/tessdata",
    "/usr/local/share/tesseract-ocr/*/tessdata",
    "/opt/homebrew/share/tessdata",
)


def _guess_tessdata_dir() -> Optional[Path]:
    """The system tessdata dir (the first standard location holding any
    model), for when tesseract did not say where it is."""
    import glob
    for pattern in _TESSDATA_GLOBS:
        for c in sorted(glob.glob(pattern), reverse=True):
            if any(Path(c).glob("*.traineddata")):
                return Path(c)
    return None


def _fetch_tessdata(codes: List[str], system_dir: Optional[Path]) -> List[str]:
    """Download missing language models into a private tessdata dir and
    point TESSDATA_PREFIX at it. Returns the codes now present there.

    Cowork sandboxes have shipped with only eng+osd and no root for apt-get,
    while github.com is reachable. ocrmypdf needs more than .traineddata
    files, so the system dir's models, configs/, tessconfigs/ and pdf.ttf
    are copied along — whichever of them exist; tessconfigs/ is missing on
    some installs.
    """
    target = _tessdata_dir()
    target.mkdir(parents=True, exist_ok=True)
    if (system_dir and system_dir.is_dir()
            and system_dir.resolve() != target.resolve()):
        for item in system_dir.iterdir():
            dst = target / item.name
            if dst.exists():
                continue
            try:
                if item.is_dir() and item.name in ("configs", "tessconfigs"):
                    shutil.copytree(item, dst, copy_function=shutil.copyfile)
                elif item.suffix == ".traineddata" or item.name == "pdf.ttf":
                    shutil.copyfile(item, dst)
            except OSError as exc:
                print(f"[ocr] could not copy {item} ({exc})")
    present = []
    for code in codes:
        dst = target / f"{code}.traineddata"
        if not dst.exists():
            try:
                with urllib.request.urlopen(_request(TESSDATA_URL.format(code=code)),
                                            timeout=60) as resp:
                    data = resp.read()
            except (OSError, http.client.HTTPException) as exc:
                print(f"[ocr] could not fetch {code}.traineddata ({exc})")
                continue
            if len(data) < 100_000:   # an error page, not a model
                print(f"[ocr] no tessdata_fast model for {code!r}")
                continue
            dst.write_bytes(data)
        present.append(code)
    if present:
        os.environ["TESSDATA_PREFIX"] = str(target)
    return present


def tesseract_preflight(requested: str) -> str:
    """Make the requested language packs available, or degrade.

    A pack that is not installed is fetched from tessdata_fast into
    _tessdata/ (see _fetch_tessdata); a model fetched by an earlier run —
    or by ocr_chunked.py — is reused. Codes that still cannot be had are
    dropped with a warning. If *none* is available, falls back to `eng`
    (with a warning) when that is installed, and otherwise exits with the
    install hint rather than letting ocrmypdf fail on every page.
    """
    if shutil.which("tesseract") is None:
        return requested
    tdir = _tessdata_dir()
    if not os.environ.get("TESSDATA_PREFIX") and any(tdir.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(tdir)
    try:
        available, system_dir = _list_langs()
    except (subprocess.TimeoutExpired, OSError):
        return requested
    requested_codes = [c for c in requested.split("+") if c]
    missing = [c for c in requested_codes if c not in available]
    if missing:
        got = _fetch_tessdata(missing, system_dir)
        if got:
            print(f"[ocr] fetched {'+'.join(got)} from tessdata_fast into "
                  f"{tdir} (TESSDATA_PREFIX set)")
            try:
                available, _ = _list_langs()
            except (subprocess.TimeoutExpired, OSError):
                available |= set(got)
    kept = [c for c in requested_codes if c in available]
    missing = [c for c in requested_codes if c not in available]
    if missing:
        print(f"[ocr] tesseract is missing language pack(s): "
              f"{'+'.join(missing)} "
              f"(installed: {', '.join(sorted(available)) or '(none)'})")
        if kept:
            print(f"[ocr] degrading to: {'+'.join(kept)}")
            return "+".join(kept)
        if "eng" in available:
            print("[ocr] WARNING: no requested language available; falling "
                  "back to eng. Expect worse recognition of Norwegian text "
                  "— install with: apt-get install tesseract-ocr-nor")
            return "eng"
        raise SystemExit(
            f"ERROR: none of the requested tesseract pack(s) ({requested}) "
            "is installed or could be fetched, and eng is not available "
            "either. Install with: apt-get install tesseract-ocr-nor, or "
            "pass --ocr-langs with an installed code."
        )
    return requested

def _pylib_target() -> Path:
    """Persistent pip --target directory.

    pip --user installs go to ~/.local/, which Cowork wipes between bash
    invocations. Installing with --target into a workspace-relative path
    (default: outputs/_pylib via NBNO_OUT_DIR) survives across calls.
    Callers must add this to PYTHONPATH and outputs/_pylib/bin to PATH.
    """
    out = os.environ.get("NBNO_PYLIB")
    if out:
        return Path(out).expanduser().resolve()
    out_dir = os.environ.get("NBNO_OUT_DIR")
    if out_dir:
        return (Path(out_dir).expanduser().resolve() / "_pylib")
    return Path.home() / ".local" / "share" / "nbno" / "_pylib"


def _ensure_pylib_on_path() -> Path:
    target = _pylib_target()
    target.mkdir(parents=True, exist_ok=True)
    sys_path_entry = str(target)
    if sys_path_entry not in sys.path:
        sys.path.insert(0, sys_path_entry)
    bin_dir = target / "bin"
    bin_dir.mkdir(exist_ok=True)
    current_path = os.environ.get("PATH", "")
    if str(bin_dir) not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{current_path}"
    cur_pp = os.environ.get("PYTHONPATH", "")
    if sys_path_entry not in cur_pp.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            f"{sys_path_entry}{os.pathsep}{cur_pp}" if cur_pp else sys_path_entry
        )
    return target


# The pinned versions (requirements.txt beside this script, kept current by
# Dependabot): every install uses them as constraints.
CONSTRAINTS = Path(__file__).resolve().parent / "requirements.txt"


def pip_install_pinned(base_cmd: List[str], packages: List[str], log=print) -> int:
    """Run `base_cmd + packages` with the pinned versions as constraints.
    If pip cannot install a pinned version on this Python (a lock compiled
    for 3.10 meeting an older or much newer interpreter), retry with the
    newest versions rather than fail, and say so."""
    if not CONSTRAINTS.exists():
        return subprocess.call(base_cmd + packages)
    rc = subprocess.call(base_cmd + ["-c", str(CONSTRAINTS)] + packages)
    if rc != 0:
        log(f"[pip] WARNING: the pinned versions in {CONSTRAINTS.name} could not be installed "
            f"on Python {sys.version.split()[0]}; retrying {' '.join(packages)} without them")
        rc = subprocess.call(base_cmd + packages)
    return rc


def _pip_install_to_pylib(packages: List[str]) -> int:
    target = _ensure_pylib_on_path()
    cmd = [
        sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
        "--break-system-packages",
        "--target", str(target),
        "--upgrade",
    ]
    print(f"[pip] installing {' '.join(packages)} -> {target}")
    return pip_install_pinned(cmd, packages)


def _which_in_pylib(binary: str) -> Optional[str]:
    found = shutil.which(binary)
    if found:
        return found
    for sub in ("bin", "Scripts"):  # Scripts/ is pip's layout on Windows
        for name in (binary, binary + ".exe"):
            candidate = _pylib_target() / sub / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def add_nb_text_layer(canonical_id: str, pdf_path: Path,
                      page_canvases: List[Optional[str]],
                      nbsso: Optional[str], workers: int) -> bool:
    """Use nb.no's own OCR (ALTO) as the PDF's text layer and give each page
    its physical size. Returns False, having changed nothing, when the item
    does not serve ALTO to us — the caller then runs Tesseract."""
    import alto_text
    import shrink_pdf
    headers = {"cookie": nbsso} if nbsso else {}
    urn = urn_form(canonical_id)

    def read(url: str) -> bytes:
        return _read_url(url, headers, 30.0)

    try:
        index = alto_text.alto_index(urn, read)
    except (OSError, http.client.HTTPException, ValueError) as e:
        print(f"[text] could not reach nb.no's OCR index ({e}); using Tesseract")
        return False
    if index is None:
        print("[text] nb.no does not serve its OCR for this item (only "
              "public-domain books do); using Tesseract")
        return False
    wanted = [c for c in page_canvases if c and c in index]
    print(f"[text] fetching nb.no's OCR (ALTO) for {len(wanted)} pages...")
    altos = alto_text.fetch_alto_pages(urn, wanted, read, workers=min(workers, 8))
    if not altos:
        print("[text] no ALTO page could be read; using Tesseract")
        return False
    shrink_pdf._ensure_deps()   # pikepdf
    stats = alto_text.apply_alto(pdf_path, page_canvases, altos)
    print(f"[text] nb.no's OCR written to {stats['pages_with_text']} pages "
          f"({stats['words']} words); {stats['resized']} pages set to their "
          "physical size; Tesseract skipped")
    # Covers and inserts (C1, I1, C3 …) rarely have text; numbered pages should.
    lacking = [n for n, c in enumerate(page_canvases, start=1)
               if c and c.rsplit("_", 1)[-1].isdigit()
               and not (c in altos and altos[c].lines)]
    if lacking:
        shown = lacking[:20]
        print(f"[text] note: {len(lacking)} numbered page(s) have no nb.no text "
              f"(PDF pages {shown}{' …' if len(lacking) > 20 else ''}). If any of "
              "them has text on it, re-run with --ocr tesseract.")
    return True


def run_ocrmypdf(pdf_path: Path, languages: str = "nor",
                 jobs: Optional[int] = None) -> None:
    """Add a searchable text layer in place. Uses --skip-text so pages that
    already have text aren't re-OCRed.

    Auto-installs ocrmypdf to a persistent pip --target on first use
    (outputs/_pylib when NBNO_OUT_DIR is set; otherwise
    ~/.local/share/nbno/_pylib). Tesseract itself must be at the system
    level; a missing language pack is fetched by tesseract_preflight().

    For books whose OCR won't fit one bash call, use ocr_chunked.py instead.
    """
    # Always, not only when installing: an ocrmypdf found in _pylib/bin
    # cannot import its own package without _pylib on PYTHONPATH.
    _ensure_pylib_on_path()
    binary = _which_in_pylib("ocrmypdf")
    if binary is None:
        rc =_pip_install_to_pylib(["ocrmypdf"])
        binary = _which_in_pylib("ocrmypdf")
        if rc != 0 or binary is None:
            raise SystemExit(
                "ERROR: failed to install ocrmypdf. Install manually with: "
                f"pip install --target {_pylib_target()} "
                f"--break-system-packages -c {CONSTRAINTS} ocrmypdf"
            )
    languages = tesseract_preflight(languages)
    jobs = max(1, jobs) if jobs else default_ocr_jobs()
    # --output-type pdf: a plain PDF, not ocrmypdf's default PDF/A. The
    # PDF/A step needs Ghostscript and pikepdf's pdfa extras (a missing
    # jsonschema made ocrmypdf exit 15 in one user's run) and re-encodes the
    # pages, for an archival stamp a Zotero copy has no use for.
    cmd = [
        binary,
        "--language", languages,
        "--skip-text",
        "--optimize", "1",
        "--output-type", "pdf",
        "--jobs", str(jobs),
        "--quiet",
        str(pdf_path),
        str(pdf_path),
    ]
    print(f"[ocr] running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, env=ocr_env(jobs), stderr=subprocess.PIPE,
                          text=True, errors="replace")
    if proc.returncode != 0:
        # ocrmypdf's own last lines name the cause (a missing module, no
        # tesseract, a bad language code); the exit status alone does not.
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise SystemExit(
            f"ERROR: ocrmypdf exited with status {proc.returncode}"
            + (f":\n{tail}" if tail else ".")
        )


def probe_canvas_index(names: List[str]) -> Optional[int]:
    """Index of the canvas to probe: the middle numbered page, else the
    middle canvas that is not a _C2, else None. (geo_check.py has a copy.)"""
    numbered = [i for i, n in enumerate(names) if n.rsplit("_", 1)[-1].isdigit()]
    if not numbered:
        numbered = [i for i, n in enumerate(names) if not n.endswith("_C2")]
    return numbered[len(numbered) // 2] if numbered else None


# legalDepositReservationStatus when the caller holds the digital loan.
LOAN_TAKEN = "TAKENBYCURRENTUSER"


def probe_page_image(canonical_id: str, nbsso: Optional[str] = None,
                     timeout: float = 20.0) -> Optional[int]:
    """Ask the image resolver for one 1024 px tile of a mid-book page.

    Returns the HTTP status — 200 when nb.no serves it to this IP and
    session — or None when no probe could be made (manifest unreachable,
    network error). This is the one check that tells a non-Norwegian IP
    apart before downloading: manifests and accessInfo are served worldwide,
    and thumbnails are never gated, so only a real page tile answers it. It
    is the same request the download would make next, to nb.no only. The
    size matters: 256 px tiles are served to anyone (verified 2026-09-29 on
    a legal-deposit item, anonymously), 1024 px tiles are not. So does the
    page: an NB item with no loan was served its first pages anonymously
    while every later page failed (2026-11-26), hence a mid-book page.
    """
    hdr_api = {"cookie": nbsso} if nbsso else {}
    hdr_img = {"referer": f"https://www.nb.no/items/{urn_form(canonical_id)}"}
    if nbsso:
        hdr_img["cookie"] = nbsso
    try:
        canvases = _fetch_manifest(canonical_id, hdr_api,
                                   timeout)["sequences"][0]["canvases"]
    except (SystemExit, OSError, http.client.HTTPException, ValueError,
            KeyError, IndexError):
        return None
    pick = probe_canvas_index([c["@id"].split("/")[-1] for c in canvases])
    if pick is None:
        return None
    try:
        base = canvases[pick]["images"][0]["resource"]["service"]["@id"]
        _, size = _read_image(f"{base}/0,0,1024,1024/full/0/default.jpg", hdr_img, timeout)
    except urllib.error.HTTPError as e:
        return e.code
    except PageImageError:
        return 403   # an empty or non-image 200 is a refusal
    except (OSError, http.client.HTTPException, KeyError, IndexError):
        return None
    # A 200 with a smaller image than the tile asked for is nb.no refusing
    # quietly, as its resolver downsamples (geo_check.PROBE_SMALL).
    return 200 if max(size) >= 1020 else 403


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--id", required=True,
                    help="nb.no URN or canonical ID (e.g. digibok_2008051600041)")
    ap.add_argument("--out", required=True,
                    help="Output directory for the .pdf + .rdf pair.")
    ap.add_argument("--cookie", default=None, metavar="FILE|auto",
                    help="Cookie file in auth.md's format ('auto' = "
                         "~/.nbno/cookie.txt); its nbsso pair is used as --nbsso.")
    ap.add_argument("--bearer", default=None,
                    help="OPTIONAL bearer token for api.nb.no. Not needed — "
                         "api.nb.no authenticates by cookie — but accepted "
                         "for older DevTools captures that include one.")
    ap.add_argument("--nbsso", default=None,
                    help="nbsso=<value> cookie pair for the IIIF downloader; "
                         "the only credential FEIDE-licensed items actually "
                         "need. Not required for public or Bokhylla items.")
    ap.add_argument("--start", type=int, default=None,
                    help="First canvas to include (1-based position in the "
                         "manifest, covers included). Canvas numbers are not "
                         "printed page numbers.")
    ap.add_argument("--stop", type=int, default=None,
                    help="Last canvas to include (inclusive; clamped to the "
                         "book's length).")
    ap.add_argument("--size", choices=sorted(SIZES), default="half",
                    help="IIIF page size. half (default): ~1100 px wide, "
                         "~145 dpi — enough for OCR and for the bitonal "
                         "shrink, 4 tiles a page for in-copyright books. "
                         "full: the scan's own size, 12 tiles a page; only "
                         "when the user asks for full resolution.")
    ap.add_argument("--workers", type=int, default=12,
                    help="Parallel downloads (default 12).")
    ap.add_argument("--keep-images", action="store_true",
                    help="Also keep the downloaded page images, in "
                         "<out>/<basename>_images/ (page_0001.jpg, ...).")
    ap.add_argument("--no-rdf", dest="rdf", action="store_false",
                    help="No Zotero RDF or JSON: just the PDF.")
    # nb_download.py: --no-ocr --no-rdf, no shrink unless --shrink, and log
    # lines that do not talk about OCR nobody asked for.
    ap.add_argument("--download-only", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--tiles", choices=("auto", "always", "never"),
                    default="auto",
                    help="IIIF tile strategy. auto (default): one request "
                         "per page, tiles wherever it is refused or "
                         "downsampled (and for the rest of the book once a "
                         "few pages are refused). always: tiles for every page. never: "
                         "one request only, drop failures.")
    ap.add_argument("--no-ocr", action="store_true",
                    help="No text layer at all. Also skips the shrink (unless "
                         "--shrink is given), so ocr_chunked.py can OCR the "
                         "unshrunk pages afterwards.")
    ap.add_argument("--ocr", choices=("auto", "nb", "tesseract"), default="auto",
                    help="Where the text layer comes from. auto (default): "
                         "nb.no's own OCR when the item serves it (public-"
                         "domain books), else Tesseract. nb: the same, but "
                         "say so loudly when it falls back. tesseract: always "
                         "OCR ourselves.")
    ap.add_argument("--ocr-langs", default="nor",
                    help="Tesseract language string (default: nor; fetched "
                         "from tessdata_fast when not installed).")
    ap.add_argument("--ocr-jobs", type=int, default=None,
                    help="Parallel jobs for ocrmypdf (default: half the "
                         "usable CPUs, at most 4).")
    ap.add_argument("--no-shrink", dest="shrink", action="store_false",
                    help="Keep the downloaded page images as they are "
                         "(~250 KB/page at half size).")
    ap.add_argument("--shrink", dest="shrink", action="store_true",
                    help="Shrink even with --no-ocr (otherwise the default).")
    ap.set_defaults(shrink=None)   # resolved after parsing: on unless --no-ocr
    ap.add_argument("--shrink-mode", choices=("bitonal", "grey", "jpeg"),
                    default="bitonal",
                    help="bitonal (default): text pages as sharp black-and-"
                         "white (lossless CCITT G4, ~60-95 KB/page, ~25-37 MB for "
                         "400 pages); covers and photo pages stay JPEG. "
                         "grey: greyscale JPEG at the downloaded size "
                         "(~200 KB/page), for books where grey tones matter "
                         "(pencil notes, stamps, photos). jpeg: the pre-1.5 "
                         "shrink, JPEG at --shrink-max-width.")
    ap.add_argument("--shrink-quality", type=int, default=60,
                    help="JPEG quality for JPEG-encoded pages (default 60).")
    ap.add_argument("--shrink-max-width", type=int, default=None,
                    help="--shrink-mode jpeg only: resize images wider than "
                         "this (px), default 800. 0 disables resizing.")
    ap.add_argument("--shrink-keep-master", action="store_true",
                    help="Also keep the unshrunk OCRed PDF as "
                         "<basename>.original.pdf, so you can re-shrink "
                         "with other settings without re-downloading. "
                         "Off by default (it is ~100 MB for 400 pages); "
                         "kept anyway when OCR fails.")
    ap.add_argument("--shrink-no-keep-master", action="store_true",
                    help=argparse.SUPPRESS)   # the default now; kept for old commands
    ap.add_argument("--shrink-threshold-mb", type=int, default=150,
                    help="With --no-shrink, print a hint when the output "
                         "PDF exceeds this size in MB (default 150). "
                         "0 = never.")
    ap.add_argument("--force-auth", action="store_true",
                    help="Skip the access pre-check and download "
                         "regardless of accessInfo.")
    args = ap.parse_args(argv)
    if args.start is not None and args.start < 1:
        ap.error("--start must be 1 or more")
    if args.stop is not None and args.stop < (args.start or 1):
        ap.error("--stop must be at least --start")
    if args.download_only:
        args.no_ocr, args.rdf = True, False
    if args.shrink is None:
        # Bitonal pages have lost the grey levels Tesseract reads best, and
        # --no-ocr exists for "download now, OCR later".
        args.shrink = not args.no_ocr
    if args.cookie:
        if args.nbsso:
            print("[auth] note: --nbsso given, so --cookie is ignored")
        else:
            args.nbsso = nbsso_from_cookie_arg(args.cookie)

    canonical = normalise_id(args.id)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pin pip --target installs to the workspace so they survive across bash
    # invocations in Cowork (~/.local/ is wiped, outputs/ is not).
    os.environ.setdefault("NBNO_OUT_DIR", str(out_dir))

    print(f"[meta] fetching nb.no metadata for {canonical}...")
    blob = fetch_nb_metadata(canonical, nbsso=args.nbsso)
    book = normalize_metadata(blob)

    # Access pre-check: if accessInfo says FEIDE-restricted and the caller
    # didn't pass bearer/nbsso/cookie, fail fast with a clear message rather
    # than letting the IIIF resolver return 403 on every page.
    access = check_nb_access(blob)
    print(f"[access] accessAllowedFrom={access.access_allowed_from}; "
          f"viewability={access.viewability}; "
          f"requires_auth={access.requires_auth}")
    if access.login_text:
        print(f"[access] legalDepositLoginText: {access.login_text}")
    if access.geo_gated:
        print(f"[access] GEO-GATED: images are served only from "
              f"{access.access_allowed_from}.")
    if (access.access_allowed_from == "NORWAY" and access.viewability == "NONE"
            and not args.force_auth):
        # The catalogue answers per IP: NONE for a Bokhylla item means this
        # IP is not Norwegian (cloud sandbox 2026-11-27; ALL from Norway).
        raise SystemExit(
            "ERROR: nb.no will not let this IP read this Bokhylla item "
            "(accessAllowedFrom NORWAY, viewability NONE): the IP is not "
            "Norwegian.\n"
            "       No cookie helps. Download it from a Norwegian IP: the local "
            "route (SKILL.md Routing).\n"
            "       Override with --force-auth if you believe accessInfo is wrong.")
    have_auth = bool(args.bearer or args.nbsso)
    if access.requires_auth and not have_auth and not args.force_auth:
        raise SystemExit(
            f"ERROR: this item needs a credential this run does not have "
            f"({access.reason}).\n"
            "       Capture a session via SKILL.md Step 0 (built-in browser) "
            "or the fallbacks in auth.md,\n"
            "       then re-run with --nbsso or --cookie /path/to/cookie.txt.\n"
            "       An accessAllowedFrom=NB item also needs a digital loan "
            "the user takes in a browser first.\n"
            f"       Note this item is also geo-gated to "
            f"{access.access_allowed_from}: from a non-Norwegian IP no "
            "credential helps.\n"
            "       Override with --force-auth if you believe accessInfo is wrong."
        )
    # The catalogue was read with the nbsso cookie, so it shows this user's
    # loan. Without one, the first pages may still be served (a preview) and
    # every later page fails.
    loan = (blob.get("accessInfo") or {}).get("legalDepositReservationStatus")
    if (access.access_allowed_from == "NB" and args.nbsso and loan != LOAN_TAKEN
            and not args.force_auth):
        raise SystemExit(
            f"ERROR: no active digital loan for this item "
            f"(legalDepositReservationStatus: {loan or 'absent'}; needs {LOAN_TAKEN}).\n"
            "       Ask the user to take the loan in the browser pane (SKILL.md "
            "Step 0.6); if they have, the nbsso cookie may have expired "
            "(re-read it, Step 0.7).\n"
            "       Override with --force-auth if you believe accessInfo is wrong."
        )
    if access.geo_gated and not args.force_auth:
        status = probe_page_image(canonical, args.nbsso)
        if status == 200:
            print("[access] image probe: nb.no served a page tile to this "
                  "IP and session")
        elif status == 403:
            if access.access_allowed_from == "NB":
                why = ("either this IP is not Norwegian, or there is no active "
                       "digital loan, or the nbsso cookie has expired "
                       "(SKILL.md Step 0)")
            else:
                why = ("this IP is not Norwegian — Bokhylla items are served "
                       "only to Norwegian addresses, whoever is logged in")
            raise SystemExit(
                f"ERROR: nb.no refused a page tile (HTTP 403): {why}.\n"
                "       Every page would fail the same way, so nothing was "
                "downloaded.\n"
                "       Override with --force-auth if you believe the probe "
                "is wrong."
            )
        else:
            print(f"[access] image probe inconclusive "
                  f"({status or 'no response'}); continuing")

    base = compute_basename(book)
    if args.start or args.stop:
        # A partial copy must not overwrite (or be mistaken for) the full book.
        base += f"_c{args.start or 1}-{args.stop or 'end'}"
    pdf_name = f"{base}.pdf"
    rdf_name = f"{base}.rdf"
    pdf_path = out_dir / pdf_name
    print(f"[meta] basename: {base}")
    print(f"[meta] title:    {book.title}")
    author_list = ", ".join(f"{c.surname}, {c.given}".strip(", ")
                            for c in book.creators)
    print(f"[meta] authors:  {author_list or '(none)'}")
    print(f"[meta] year:     {book.date or book.year or '?'}    "
          f"publisher: {book.publisher or '?'}    "
          f"place: {book.place or '?'}")

    # ---- Download -----------------------------------------------------------
    # No credential at all for public-domain and (from Norway) Bokhylla
    # items; --nbsso alone for FEIDE items, as api.nb.no authenticates by
    # cookie. (Until 2.0 a --cookie file sent the download through the
    # third-party nbno CLI instead; it left out covers, could not make a PDF
    # of large maps, and fetched every page at full size.)
    creds = "+".join(k for k, v in (("nbsso", args.nbsso),
                                    ("bearer", args.bearer)) if v)
    print(f"[dl] downloading via IIIF ({creds or 'no credentials'}, "
          f"size={args.size}, tiles={args.tiles})")
    ocr_failed = ""
    missing_pages = download_via_iiif(
        canonical_id=canonical,
        out_pdf=pdf_path,
        bearer=args.bearer,
        nbsso=args.nbsso,
        size=args.size,
        workers=args.workers,
        tiles=args.tiles,
        start=args.start,
        stop=args.stop,
        keep_images=args.keep_images,
    )
    print(f"[dl] PDF: {pdf_path}  ({pdf_path.stat().st_size/1e6:.1f} MB)")

    # ---- Text layer ---------------------------------------------------------
    if args.no_ocr:
        if not args.download_only:
            print("[ocr] skipped (--no-ocr)")
    else:
        used_nb = False
        if args.ocr != "tesseract":
            used_nb = add_nb_text_layer(canonical, pdf_path, missing_pages["canvases"],
                                        args.nbsso, args.workers)
            if not used_nb and args.ocr == "nb":
                print("[text] WARNING: --ocr nb was asked for, but nb.no's OCR "
                      "is not available here; falling back to Tesseract.")
        if not used_nb:
            try:
                run_ocrmypdf(pdf_path, languages=args.ocr_langs, jobs=args.ocr_jobs)
                print(f"[ocr] PDF now searchable ({pdf_path.stat().st_size/1e6:.1f} MB)")
            except SystemExit as exc:
                # The pages are downloaded; losing them (and the RDF) over
                # OCR would be worse than delivering an image-only PDF.
                ocr_failed = str(exc)
                print(f"[ocr] FAILED, continuing without a text layer: {exc}")

    # ---- Shrink (image recompression) ---------------------------------------
    master_path = pdf_path.with_suffix(".original.pdf")
    keep_master = args.shrink and (args.shrink_keep_master or bool(ocr_failed))
    if args.shrink:
        import shrink_pdf as shrinkmod   # noqa: E402  (after sys.path mutation)
        size_before = pdf_path.stat().st_size

        print(f"[shrink] settings: mode={args.shrink_mode}, "
              f"quality={args.shrink_quality}"
              + (f", max_width={args.shrink_max_width or 800}"
                 if args.shrink_mode == "jpeg" else ""))
        print("[shrink] probing one middle page to estimate output size...")
        est = shrinkmod.estimate_output(
            pdf_path, args.shrink_quality, args.shrink_max_width,
            mode=args.shrink_mode,
        )
        if est["pages"]:
            print(f"[shrink] probe: page {est['probe_page']}/{est['pages']} "
                  f"-> {est['probe_bytes']/1e3:.0f} KB")
            print(f"[shrink] estimated output: "
                  f"~{est['estimated_total_bytes']/1e6:.0f} MB")

        # Keep the unshrunk PDF when asked, and always when OCR failed: the
        # shrunk pages (bitonal ones above all) OCR worse, and without this
        # copy a retry of the OCR would mean downloading the book again.
        if keep_master:
            shutil.copy2(str(pdf_path), str(master_path))
            print(f"[shrink] kept the unshrunk PDF as {master_path.name}"
                  + (" (OCR failed; retry the OCR on this copy)" if ocr_failed else ""))

        stats = shrinkmod.recompress(
            pdf_path, pdf_path,
            quality=args.shrink_quality,
            max_width=args.shrink_max_width,
            mode=args.shrink_mode,
        )
        print(shrinkmod.format_stats(stats))
        saved = size_before - stats["bytes_after"]
        pct = (saved / size_before * 100) if size_before else 0
        print(f"[shrink] {size_before/1e6:.1f} MB -> "
              f"{stats['bytes_after']/1e6:.1f} MB "
              f"(saved {saved/1e6:.1f} MB, {pct:.0f}%)")
    elif args.download_only:
        size_mb = pdf_path.stat().st_size / 1e6
        if size_mb > 50:
            print(f"[hint] PDF is {size_mb:.0f} MB. To shrink: shrink_pdf.py --pdf "
                  f"{pdf_path} --in-place (bitonal, for text pages); for maps, "
                  "photos and posters use --shrink-mode grey, or leave it as is "
                  "when the user asked for full resolution.")
    elif args.no_ocr:
        print(f"[shrink] skipped: the pages are as downloaded "
              f"({pdf_path.stat().st_size/1e6:.0f} MB), ready for OCR with "
              "ocr_chunked.py. To shrink (after any OCR): "
              f"shrink_pdf.py --pdf {pdf_path} --in-place")
    elif args.shrink_threshold_mb > 0:
        size_mb = pdf_path.stat().st_size / 1e6
        if size_mb > args.shrink_threshold_mb:
            print(f"[hint] PDF is {size_mb:.0f} MB. Run shrink_pdf.py on it "
                  "(or re-run without --no-shrink) to recompress the page "
                  "images: expect ~25-37 MB for a 400-page book.")

    # ---- RDF ----------------------------------------------------------------
    # Also writes <base>.zotero.json, the same item for Zoteus's
    # zotero_create_items (zotero-ready.md, "Direct import with Zoteus").
    if args.rdf:
        zotero_rdf.write_zotero_files(
            book_to_item(book), out_dir, base,
            pdf_filename=pdf_name,
            link_url=items_page_url(canonical),
            link_title="eBok (nb.no)",
            item_id=base.lower(),
        )

    print()
    print(f"Done. Final artefacts in {out_dir}:")
    print(f"  {pdf_name}")
    if args.rdf:
        print(f"  {rdf_name}   ← import this into Zotero")
        print(f"  {base}.zotero.json   ← the same item for Zoteus (zotero_create_items)")
    if missing_pages.get("images"):
        print(f"  {Path(missing_pages['images']).name}/   ← the page images")
    extras = []
    if keep_master and master_path.exists():
        extras.append(
            f"  {master_path.name}   ← unshrunk copy "
            + ("for retrying the OCR" if ocr_failed else "(delete to free "
               f"{master_path.stat().st_size/1e6:.0f} MB once the shrink is OK)")
        )
    pylib = out_dir / "_pylib"
    if pylib.exists():
        extras.append(
            f"  _pylib/   ← persistent pip install target "
            f"(keep; deleting forces a re-install next run)"
        )
    if (out_dir / "_tessdata").exists():
        extras.append("  _tessdata/   ← fetched Tesseract language models "
                      "(keep; deleting forces a re-download)")
    if extras:
        print()
        print("Also present:")
        for line in extras:
            print(line)
    if missing_pages["missing"]:
        print()
        print(f"WARNING: PDF pages {missing_pages['missing']} are placeholders — those "
              "pages could not be downloaded. Re-run the same command with the same "
              "--out to fill them in (the other pages are kept in "
              f"{pages_dir(pdf_path, args.size)} and not fetched again); "
              "until then, tell the user they are missing.")
        return 3
    if ocr_failed:
        print()
        print("WARNING: OCR failed, so the PDF has no text layer (the PDF and RDF "
              f"are otherwise complete): {ocr_failed}")
        if keep_master and master_path.exists():
            print(f"         The unshrunk pages are kept in {master_path.name}. After "
                  "fixing the cause, OCR that copy with ocr_chunked.py --pdf "
                  f"{master_path}, then shrink_pdf.py --pdf {master_path} --out "
                  f"{pdf_path} --mode {args.shrink_mode}, then delete it.")
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
