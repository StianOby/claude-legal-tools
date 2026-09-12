#!/usr/bin/env python3
"""
zotero_book.py — download a book from nb.no, OCR it, and emit a Zotero-ready
RDF + PDF pair.

Run from the nbno skill's scripts/ folder (or copy alongside nbno_run.sh):

    python zotero_book.py \\
        --id URN:NBN:no-nb_digibok_2008051600041 \\
        --out /path/to/outputs/folder \\
        [--cookie auto | --cookie /path/cookie.txt] \\
        [--nbsso "nbsso=<value>"] [--bearer "<token>"] \\
        [--resize 75] \\
        [--no-ocr]

Auth, in short: `api.nb.no` authenticates by cookie, so `--nbsso` alone is
enough and `--bearer` is optional (kept for older DevTools captures that
happen to include one). Public-domain and Bokhylla items need no cookie at
all — Bokhylla only needs a Norwegian IP. FEIDE-licensed items need `--nbsso`
*and* an active digital loan taken by the user in a browser.

What it produces:

    <out>/AUTHOR_TITLE_(YEAR).pdf      — OCRed (nor+nno) by default
    <out>/AUTHOR_TITLE_(YEAR).rdf      — Zotero RDF, references the PDF
                                         as an imported-file attachment
                                         and the nb.no URL as a Web Link
                                         titled "eBok (nb.no)".

The Zotero "URL" metadata field is intentionally left blank — the only link
to nb.no lives as a Web Link attachment on the imported item.

Pipeline:
  1. Resolve --id into a canonical nb.no item ID (digibok_NNN…).
  2. Fetch metadata from https://api.nb.no/catalog/v1/items/<URN>.
  3. Compute AUTHOR_TITLE_(YEAR) and the destination PDF path.
  4. Download the full book PDF.
       - Default: the fast IIIF downloader in-process. It needs no
         credential for public-domain items or Bokhylla from a Norwegian
         IP, and takes --nbsso (and/or --bearer) for FEIDE-licensed ones.
         --tiles and --workers only apply on this path.
       - --cookie <file|auto> selects the nbno_run.sh wrapper instead (the
         cookie-file workflow from auth.md). --downloader overrides both.
  5. Run ocrmypdf (-l nor+nno) unless --no-ocr.
  6. Render the Zotero RDF via build_zotero_rdf.build_rdf.

Designed to stream progress (each step prints a single line) so the user can
follow along in a Cowork session even when individual phases take a while.
Each subprocess call has its own timeout.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make the sibling build_zotero_rdf module importable regardless of the
# directory we're invoked from.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import build_zotero_rdf as rdfmod   # noqa: E402  (after sys.path mutation)


# ---------------------------------------------------------------------------
# ID handling
# ---------------------------------------------------------------------------

_URN_PREFIXES = ("URN:NBN:no-nb_", "urn:nbn:no-nb_", "urn:nbn:no-nb:")
# Underscores are part of many real ids, not just a separator after the
# type: newspapers are digavis_aftenposten_morgen_1_20150107_156_7_2 and
# journals digitidsskrift_2021052683055_001. Keep this in step with the
# identical patterns in nbno_run.sh and scripts/browser/nbno_auth.js.
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
_EDITOR_ROLES = {"edt"}
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
    elif viewability == "NONE" and allowed_from != "EVERYWHERE":
        # Keep the old signal as a backstop for item classes we haven't
        # characterised, but never let it fire on an item the API says is
        # readable from everywhere.
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
    req = urllib.request.Request(url, headers=headers)
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


def normalize_metadata(api_blob: dict) -> rdfmod.NormalizedBook:
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

    creators: List[rdfmod.Creator] = []
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
            creators.append(rdfmod.Creator(
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
    return rdfmod.NormalizedBook(
        title=title,
        subtitle=subtitle,
        creators=creators,
        publisher=publisher,
        place=place,
        year=year,
        date=date,
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


def compute_basename(book: rdfmod.NormalizedBook) -> str:
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
            req = urllib.request.Request(url, headers=hdr_api)
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


def _fetch_iiif_info(base_url: str, hdr_img: Dict[str, str],
                     timeout: float = 15.0) -> dict:
    """GET <base_url>/info.json — the IIIF Image API descriptor.

    Returns a dict with at least `width`, `height`, and `sizes` (a list of
    {width, height} entries that the resolver will actually serve without
    silently downsampling).
    """
    url = f"{base_url}/info.json"
    req = urllib.request.Request(url, headers=hdr_img)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_iiif_width(info: dict, target_width: int) -> int:
    """Pick the largest sizes[] entry ≤ target_width.

    nb.no's IIIF resolver silently downsamples requests above its listed
    sizes (e.g. asking for 1024 returns 502 wide, mangling OCR). The fix is
    to only ever request a width that's explicitly listed in info.json.
    """
    listed = sorted(
        {int(s["width"]) for s in (info.get("sizes") or []) if s.get("width")},
        reverse=True,
    )
    if not listed:
        return target_width
    for w in listed:
        if w <= target_width:
            return w
    return listed[-1]


def _fetch_page_singleshot(
    base_url: str, width: int, hdr_img: Dict[str, str],
    timeout: float = 30.0,
) -> Tuple[Optional[bytes], Optional[Tuple[int, int]]]:
    """Single /full/<w>,/0/default.jpg request. Returns (bytes, (w,h)).

    The (w,h) tuple is the *actual* size of the returned image as measured by
    PIL — callers compare it with the requested width to detect silent
    downsampling. Returns (None, None) on 403/404.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Pillow is required. Install with: "
            "pip install --break-system-packages Pillow"
        ) from exc
    import io
    url = f"{base_url}/full/{width},/0/default.jpg"
    try:
        req = urllib.request.Request(url, headers=hdr_img)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None, None
        raise
    actual = Image.open(io.BytesIO(data)).size
    return data, actual


def _fetch_page_tiled(
    base_url: str, info: dict, hdr_img: Dict[str, str],
    tile_size: int = 1024, timeout: float = 30.0,
) -> Optional[bytes]:
    """Fetch a canvas as 1024×1024 regionByPx tiles and stitch with PIL.

    Used when the single-shot /full/<w>,/ request is denied (403) or
    silently downsampled. The IIIF resolver typically allows native-resolution
    regionByPx requests up to ~1024 on a side even when it refuses a full
    single-shot request — which is the difference between unusable and clean
    OCR for in-copyright material.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Pillow is required. Install with: "
            "pip install --break-system-packages Pillow"
        ) from exc
    import io
    full_w = int(info.get("width") or 0)
    full_h = int(info.get("height") or 0)
    if full_w <= 0 or full_h <= 0:
        return None
    canvas = Image.new("RGB", (full_w, full_h), "white")
    for y in range(0, full_h, tile_size):
        for x in range(0, full_w, tile_size):
            tw = min(tile_size, full_w - x)
            th = min(tile_size, full_h - y)
            url = f"{base_url}/{x},{y},{tw},{th}/full/0/default.jpg"
            try:
                req = urllib.request.Request(url, headers=hdr_img)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    tile = Image.open(io.BytesIO(resp.read())).convert("RGB")
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    return None
                raise
            canvas.paste(tile, (x, y))
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
    from PIL import Image

    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        import img2pdf  # noqa: F401
    except ImportError:
        print("[pdf] installing img2pdf (one-time)...")
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
    resize_width: int = 1024,
    workers: int = 12,
    tiles: str = "auto",
) -> None:
    """Fast in-process downloader.

    Pulls the IIIF manifest, downloads each canvas at the largest listed
    width ≤ resize_width, verifies the returned image actually has that
    width (the resolver silently downsamples otherwise), and falls back to
    native-resolution tiles when single-shot is refused.

    Auth is optional. `api.nb.no` serves manifests and metadata without any
    credential and otherwise authenticates by cookie, so `bearer` is never
    required — when it is absent the `nbsso` cookie is sent to api.nb.no as
    well, which is what makes the response reflect the user's own session.
    Public-domain and Bokhylla items need no credential at all (Bokhylla
    needs a Norwegian IP instead); only FEIDE-licensed items require `nbsso`
    plus a digital loan the user has taken in a browser.

    tiles ∈ {"auto", "always", "never"}:
      - auto:   single-shot first, tile only on 403 or dimension mismatch
      - always: skip single-shot entirely; tile every page
      - never:  single-shot only; pages that fail are dropped
    """
    from concurrent.futures import ThreadPoolExecutor

    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix="nbno_zotero_"))
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

    entries: List[Dict[str, str]] = []
    for c in canvases:
        canvas_name = c["@id"].split("/")[-1]
        base = c["images"][0]["resource"]["service"]["@id"]
        entries.append({"canvas": canvas_name, "base_url": base})

    # resize_width only governs the single-shot path. Tiled pages are fetched
    # as native-resolution regionByPx tiles and come out at each canvas's own
    # full size, so under tiles="always" the width is not a cap on anything.
    chosen_width = resize_width
    if tiles == "always":
        print(f"[iiif] manifest has {len(entries)} canvases; tiles=always "
              "— every page fetched as native-resolution tiles "
              f"(--resize {resize_width} does not apply)")
    else:
        print(f"[iiif] manifest has {len(entries)} canvases; "
              f"target width {resize_width}, tiles={tiles}")

        # info.json shape varies very little between canvases of the same
        # item, so peek at the first usable canvas to learn the resolver's
        # listed sizes and pick a width that won't be silently downsampled.
        # Skipped entirely under tiles="always": chosen_width is unused there,
        # so probing would cost a round-trip and print a width that caps
        # nothing.
        info_probe: Optional[dict] = None
        for e in entries:
            if e["canvas"].endswith("_C2"):
                continue
            try:
                info_probe = _fetch_iiif_info(e["base_url"], hdr_img)
                chosen_width = _pick_iiif_width(info_probe, resize_width)
                break
            except urllib.error.HTTPError:
                continue
        if info_probe is None:
            print("[iiif] WARNING: could not fetch info.json for any canvas; "
                  "using requested width unchecked.")
        elif chosen_width != resize_width:
            print(f"[iiif] requested {resize_width}px; resolver lists "
                  f"{sorted({int(s['width']) for s in info_probe.get('sizes') or []})} "
                  f"→ using {chosen_width}px to avoid silent downsample.")

    # Every page reports how it was fetched and the caller tallies the modes;
    # counting inside the workers would race (12 threads, non-atomic +=).
    def fetch_page(idx_entry: Tuple[int, Dict[str, str]]) -> Tuple[int, Optional[str], str]:
        idx, entry = idx_entry
        if entry["canvas"].endswith("_C2"):
            return idx, None, "skipped_c2"

        info: Optional[dict] = None
        data: Optional[bytes] = None
        mode = "single"

        if tiles == "always":
            try:
                info = _fetch_iiif_info(entry["base_url"], hdr_img)
            except urllib.error.HTTPError:
                return idx, None, "no_info"
            data = _fetch_page_tiled(entry["base_url"], info, hdr_img)
            mode = "tiled"
        else:
            data, actual = _fetch_page_singleshot(
                entry["base_url"], chosen_width, hdr_img,
            )
            if data is not None and actual is not None:
                aw = actual[0]
                if aw < chosen_width - 4:  # tolerate 1–2px rounding
                    mode = "single_downsampled"
                    if tiles == "auto":
                        # Silent downsample → fall back to tiles for clean res.
                        try:
                            info = _fetch_iiif_info(entry["base_url"], hdr_img)
                        except urllib.error.HTTPError:
                            info = None
                        if info is not None:
                            tiled = _fetch_page_tiled(
                                entry["base_url"], info, hdr_img,
                            )
                            if tiled is not None:
                                data = tiled
                                mode = "tiled_after_downsample"
            elif tiles == "auto":
                # 403/404 on single-shot → try tiles.
                try:
                    info = _fetch_iiif_info(entry["base_url"], hdr_img)
                except urllib.error.HTTPError:
                    info = None
                if info is not None:
                    data = _fetch_page_tiled(entry["base_url"], info, hdr_img)
                    if data is not None:
                        mode = "tiled_after_403"

        if data is None:
            return idx, None, mode + "_failed"
        path = tmpdir / f"page_{idx:04d}.jpg"
        path.write_bytes(data)
        return idx, str(path), mode

    t0 = time.time()
    results: Dict[int, Optional[str]] = {}
    modes: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, path, mode in pool.map(
            fetch_page, list(enumerate(entries, start=1))
        ):
            results[idx] = path
            modes.append(mode)
    elapsed = time.time() - t0
    ok = sum(1 for v in results.values() if v)
    tile_count = sum(1 for m in modes if m.startswith("tiled"))
    downsample_count = sum(1 for m in modes if "downsampled" in m or "downsample" in m)
    failed = [m for m in modes if m.endswith("_failed")]
    print(f"[iiif] {ok}/{len(entries)} pages in {elapsed:.1f}s "
          f"(tiled: {tile_count}, single-shot downsamples observed: "
          f"{downsample_count}"
          + (f", failed: {len(failed)}" if failed else "")
          + "); assembling PDF...")

    page_paths = [results[i] for i in sorted(results) if results[i]]
    if not page_paths:
        raise SystemExit(
            "ERROR: no pages downloaded. Check, in this order: (1) is the "
            "egress IP Norwegian? accessAllowedFrom NORWAY/NB items 403 on "
            "every page regardless of login; (2) for a FEIDE-licensed item, "
            "has the user taken the digital loan in a browser "
            "(legalDepositReservationStatus == TAKENBYCURRENTUSER) and is "
            "--nbsso set?"
        )

    _assemble_pages_to_pdf(page_paths, out_pdf)
    for p in page_paths:
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        tmpdir.rmdir()
    except OSError:
        pass


def download_via_wrapper(
    canonical_id: str,
    out_pdf: Path,
    cookie: Optional[str],
    resize: Optional[int],
    skill_scripts_dir: Path,
) -> None:
    """Shell out to nbno_run.sh — the bash wrapper that ships with the skill."""
    wrapper = skill_scripts_dir / "nbno_run.sh"
    if not wrapper.exists():
        raise SystemExit(
            f"ERROR: nbno_run.sh not found at {wrapper}. "
            "Pass --skill-scripts-dir if the script lives elsewhere."
        )
    workdir = out_pdf.parent / f"_nbno_{canonical_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = ["bash", str(wrapper),
           "--id", canonical_id,
           "--out", str(workdir)]
    if cookie:
        cmd += ["--cookie", cookie]
    if resize:
        cmd += ["--resize", str(resize)]
    print(f"[wrapper] running: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit(f"ERROR: nbno_run.sh exited with status {rc}.")
    pdfs = sorted(workdir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"ERROR: nbno_run.sh produced no PDF in {workdir}.")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdfs[0]), str(out_pdf))
    # Clean up the working directory.
    shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def tesseract_preflight(requested: str) -> str:
    """Check which of the requested tesseract languages are installed.

    Returns a `+`-joined language string with only available codes. Warns
    and degrades gracefully — typical Cowork case is `nor` installed but
    `nno` missing. If *none* are available, falls back to `eng` (with a
    warning) when that is installed, and otherwise exits with the install
    hint rather than letting ocrmypdf fail on every page.
    """
    if shutil.which("tesseract") is None:
        return requested
    try:
        out = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return requested
    available = {
        ln.strip() for ln in (out.stdout + out.stderr).splitlines()
        if ln.strip() and not ln.startswith("List of available")
    }
    requested_codes = [c for c in requested.split("+") if c]
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
                  "— install with: apt-get install tesseract-ocr-nor "
                  "tesseract-ocr-nno")
            return "eng"
        raise SystemExit(
            f"ERROR: none of the requested tesseract pack(s) ({requested}) "
            "is installed and eng is not available either. Install with: "
            "apt-get install tesseract-ocr-nor tesseract-ocr-nno, or pass "
            "--ocr-langs with an installed code."
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
    if str(bin_dir) not in current_path.split(":"):
        os.environ["PATH"] = f"{bin_dir}:{current_path}"
    cur_pp = os.environ.get("PYTHONPATH", "")
    if sys_path_entry not in cur_pp.split(":"):
        os.environ["PYTHONPATH"] = (
            f"{sys_path_entry}:{cur_pp}" if cur_pp else sys_path_entry
        )
    return target


def _pip_install_to_pylib(packages: List[str]) -> int:
    target = _ensure_pylib_on_path()
    cmd = [
        sys.executable, "-m", "pip", "install", "--quiet",
        "--break-system-packages",
        "--target", str(target),
        "--upgrade",
    ] + packages
    print(f"[pip] installing {' '.join(packages)} -> {target}")
    return subprocess.call(cmd)


def _which_in_pylib(binary: str) -> Optional[str]:
    found = shutil.which(binary)
    if found:
        return found
    candidate = _pylib_target() / "bin" / binary
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def run_ocrmypdf(pdf_path: Path, languages: str = "nor+nno",
                 jobs: int = 4) -> None:
    """Add a searchable text layer in place. Uses --skip-text so pages that
    already have text aren't re-OCRed.

    Auto-installs ocrmypdf to a persistent pip --target on first use
    (outputs/_pylib when NBNO_OUT_DIR is set; otherwise
    ~/.local/share/nbno/_pylib). Tesseract and language packs must be at
    the system level — on Debian/Ubuntu:
        apt-get install tesseract-ocr tesseract-ocr-nor tesseract-ocr-nno
    The nno pack is missing in some Cowork sandboxes; tesseract_preflight()
    will warn and degrade to nor in that case.

    For books that won't fit a 45s sandbox window, use ocr_chunked.py instead.
    """
    binary = _which_in_pylib("ocrmypdf")
    if binary is None:
        print("[ocr] installing ocrmypdf (one-time)...")
        rc = _pip_install_to_pylib(["ocrmypdf"])
        binary = _which_in_pylib("ocrmypdf")
        if rc != 0 or binary is None:
            raise SystemExit(
                "ERROR: failed to install ocrmypdf. Install manually with: "
                f"pip install --target {_pylib_target()} "
                "--break-system-packages ocrmypdf"
            )
    languages = tesseract_preflight(languages)
    cmd = [
        binary,
        "--language", languages,
        "--skip-text",
        "--optimize", "1",
        "--jobs", str(jobs),
        "--quiet",
        str(pdf_path),
        str(pdf_path),
    ]
    print(f"[ocr] running: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit(
            f"ERROR: ocrmypdf exited with status {rc}. "
            "Make sure tesseract-ocr + Norwegian language packs are installed."
        )


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--id", required=True,
                    help="nb.no URN or canonical ID (e.g. digibok_2008051600041)")
    ap.add_argument("--out", required=True,
                    help="Output directory for the .pdf + .rdf pair.")
    ap.add_argument("--cookie", default=None,
                    help="Cookie file path (or 'auto' for ~/.nbno/cookie.txt). "
                         "Selects the nbno_run.sh wrapper, which is the only "
                         "path that reads it.")
    ap.add_argument("--downloader", choices=("auto", "iiif", "wrapper"),
                    default="auto",
                    help="auto (default): in-process IIIF unless --cookie is "
                         "given without --nbsso/--bearer. iiif / wrapper "
                         "force one path.")
    ap.add_argument("--bearer", default=None,
                    help="OPTIONAL bearer token for api.nb.no. Not needed — "
                         "api.nb.no authenticates by cookie — but accepted "
                         "for older DevTools captures that include one.")
    ap.add_argument("--nbsso", default=None,
                    help="nbsso=<value> cookie pair for the IIIF downloader; "
                         "the only credential FEIDE-licensed items actually "
                         "need. Not required for public or Bokhylla items.")
    ap.add_argument("--resize", type=int, default=None,
                    help="Page width in pixels for IIIF (default 1024) or "
                         "percentage for nbno_run.sh (suggested 75).")
    ap.add_argument("--workers", type=int, default=12,
                    help="Parallel downloaders for the IIIF path (default 12).")
    ap.add_argument("--tiles", choices=("auto", "always", "never"),
                    default="auto",
                    help="IIIF tile-fallback strategy. auto (default): "
                         "single-shot first, tile on 403 or silent downsample. "
                         "always: native-res tiles for every page. never: "
                         "single-shot only, drop failures.")
    ap.add_argument("--no-ocr", action="store_true",
                    help="Skip the OCR step.")
    ap.add_argument("--ocr-langs", default="nor+nno",
                    help="Tesseract language string (default: nor+nno).")
    ap.add_argument("--ocr-jobs", type=int, default=4,
                    help="Parallel jobs for ocrmypdf (default 4).")
    ap.add_argument("--shrink", action="store_true",
                    help="Recompress embedded images (JPEG) after OCR. "
                         "Lossy. With the default settings (q70 + 900 px) "
                         "a 350-page book lands around 50 MB. Without this "
                         "flag, a hint is printed when the output PDF "
                         "exceeds --shrink-threshold-mb.")
    ap.add_argument("--shrink-quality", type=int, default=70,
                    help="JPEG quality for --shrink (default 70 — tuned "
                         "for ~143 KB/page on text-heavy nb.no scans).")
    ap.add_argument("--shrink-max-width", type=int, default=900,
                    help="Resize images wider than this (px) before "
                         "re-encoding (default 900). 0 disables resizing.")
    ap.add_argument("--shrink-no-keep-master", action="store_true",
                    help="Do not preserve the OCRed master at "
                         "<basename>.original.pdf before overwriting. By "
                         "default the master is kept so you can re-shrink "
                         "with different settings without compounding "
                         "JPEG artefacts.")
    ap.add_argument("--shrink-threshold-mb", type=int, default=500,
                    help="Suggest --shrink when output PDF exceeds this "
                         "size in MB (default 500). 0 = never suggest.")
    ap.add_argument("--force-auth", action="store_true",
                    help="Skip the access pre-check and attempt the chosen "
                         "download path regardless of accessInfo.")
    ap.add_argument("--skill-scripts-dir", default=str(_HERE),
                    help="Path to the nbno skill's scripts/ folder "
                         "(used to locate nbno_run.sh).")
    args = ap.parse_args(argv)

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
              f"{access.access_allowed_from}. If this machine's IP is not "
              "Norwegian, every page will 403 regardless of login — run "
              "geo_check.py to see the IP nb.no sees.")
    have_auth = bool(args.bearer or args.nbsso or args.cookie)
    if access.requires_auth and not have_auth and not args.force_auth:
        raise SystemExit(
            f"ERROR: this item needs a credential this run does not have "
            f"({access.reason}).\n"
            "       Capture a session via SKILL.md Step 0 (built-in browser) "
            "or the fallbacks in auth.md,\n"
            "       then re-run with --nbsso (fast IIIF) or "
            "--cookie /path/to/cookie.txt (wrapper).\n"
            "       An accessAllowedFrom=NB item also needs a digital loan "
            "the user takes in a browser first.\n"
            f"       Note this item is also geo-gated to "
            f"{access.access_allowed_from}: from a non-Norwegian IP no "
            "credential helps.\n"
            "       Override with --force-auth if you believe accessInfo is wrong."
        )

    base = compute_basename(book)
    pdf_name = f"{base}.pdf"
    rdf_name = f"{base}.rdf"
    pdf_path = out_dir / pdf_name
    rdf_path = out_dir / rdf_name
    print(f"[meta] basename: {base}")
    print(f"[meta] title:    {book.title}")
    author_list = ", ".join(f"{c.surname}, {c.given}".strip(", ")
                            for c in book.creators)
    print(f"[meta] authors:  {author_list or '(none)'}")
    print(f"[meta] year:     {book.date or book.year or '?'}    "
          f"publisher: {book.publisher or '?'}    "
          f"place: {book.place or '?'}")

    # ---- Download -----------------------------------------------------------
    # The IIIF path is the default: it works with no credential at all for
    # public-domain and (from Norway) Bokhylla items, and --nbsso alone is
    # enough for FEIDE items because api.nb.no authenticates by cookie. The
    # wrapper is chosen only by an explicit --cookie file (or --downloader
    # wrapper) — it used to be the silent default whenever no --nbsso/--bearer
    # was given, which made `--tiles always` a no-op for exactly the Bokhylla
    # case that needs tiles.
    if args.downloader == "auto":
        use_iiif = not args.cookie or bool(args.nbsso or args.bearer)
    else:
        use_iiif = args.downloader == "iiif"
    if use_iiif:
        creds = "+".join(k for k, v in (("nbsso", args.nbsso),
                                        ("bearer", args.bearer)) if v)
        print(f"[dl] using fast IIIF in-process downloader "
              f"({creds or 'no credentials'}, tiles={args.tiles})")
        if args.cookie:
            print("[dl] note: --cookie is only read by the nbno_run.sh wrapper; "
                  "pass --nbsso for the IIIF path, or --downloader wrapper")
        download_via_iiif(
            canonical_id=canonical,
            out_pdf=pdf_path,
            bearer=args.bearer,
            nbsso=args.nbsso,
            resize_width=args.resize or 1024,
            workers=args.workers,
            tiles=args.tiles,
        )
    else:
        print("[dl] using nbno_run.sh wrapper"
              + (" (--cookie given)" if args.cookie else "")
              + ("; --tiles/--workers do not apply here"
                 if args.tiles != "auto" or args.workers != 12 else ""))
        download_via_wrapper(
            canonical_id=canonical,
            out_pdf=pdf_path,
            cookie=args.cookie,
            resize=args.resize,
            skill_scripts_dir=Path(args.skill_scripts_dir).resolve(),
        )
    print(f"[dl] PDF: {pdf_path}  ({pdf_path.stat().st_size/1e6:.1f} MB)")

    # ---- OCR ----------------------------------------------------------------
    if not args.no_ocr:
        run_ocrmypdf(pdf_path, languages=args.ocr_langs, jobs=args.ocr_jobs)
        print(f"[ocr] PDF now searchable ({pdf_path.stat().st_size/1e6:.1f} MB)")
    else:
        print("[ocr] skipped (--no-ocr)")

    # ---- Shrink (lossy image recompression) ---------------------------------
    if args.shrink:
        import shrink_pdf as shrinkmod   # noqa: E402  (after sys.path mutation)
        size_before = pdf_path.stat().st_size

        print(f"[shrink] settings: quality={args.shrink_quality}, "
              f"max_width={args.shrink_max_width or 'none'}")
        print("[shrink] probing one middle page to estimate output size...")
        est = shrinkmod.estimate_output(
            pdf_path, args.shrink_quality, args.shrink_max_width,
        )
        if est["pages"]:
            print(f"[shrink] probe: page {est['probe_page']}/{est['pages']} "
                  f"-> {est['probe_bytes']/1e3:.0f} KB")
            print(f"[shrink] estimated output: "
                  f"~{est['estimated_total_bytes']/1e6:.0f} MB")

        # Preserve the OCRed master before in-place rewrite. Re-encoding an
        # already-shrunk file compounds JPEG artefacts; keeping the master
        # means experimenting with different settings is non-destructive.
        # User can delete <basename>.original.pdf once happy with the shrink.
        master_path = pdf_path.with_suffix(".original.pdf")
        if not args.shrink_no_keep_master:
            shutil.copy2(str(pdf_path), str(master_path))
            print(f"[shrink] preserved master at {master_path.name}")

        stats = shrinkmod.recompress(
            pdf_path, pdf_path,
            quality=args.shrink_quality,
            max_width=args.shrink_max_width,
        )
        saved = size_before - stats["bytes_after"]
        pct = (saved / size_before * 100) if size_before else 0
        print(f"[shrink] {size_before/1e6:.1f} MB -> "
              f"{stats['bytes_after']/1e6:.1f} MB "
              f"(saved {saved/1e6:.1f} MB, {pct:.0f}%)")
        if not args.shrink_no_keep_master:
            print(f"[shrink] master kept at {master_path.name} — delete it "
                  "once you're happy with the shrunk version.")
    elif args.shrink_threshold_mb > 0:
        size_mb = pdf_path.stat().st_size / 1e6
        if size_mb > args.shrink_threshold_mb:
            print(f"[hint] PDF is {size_mb:.0f} MB. Re-run with --shrink to "
                  "recompress embedded images (default settings target "
                  "~143 KB/page; expect ~50 MB for a 350-page book).")

    # ---- RDF ----------------------------------------------------------------
    nb_url = items_page_url(canonical)
    rdf_xml = rdfmod.build_rdf(
        book,
        pdf_filename=pdf_name,
        nb_url=nb_url,
        item_id=base.lower(),
    )
    rdf_path.write_text(rdf_xml, encoding="utf-8")
    print(f"[rdf] {rdf_path}")

    print()
    print(f"Done. Final artefacts in {out_dir}:")
    print(f"  {pdf_name}")
    print(f"  {rdf_name}   ← import this into Zotero")
    extras = []
    master_path = pdf_path.with_suffix(".original.pdf")
    if args.shrink and not args.shrink_no_keep_master and master_path.exists():
        extras.append(
            f"  {master_path.name}   ← OCRed master (delete to free "
            f"{master_path.stat().st_size/1e6:.0f} MB once the shrink is OK)"
        )
    pylib = out_dir / "_pylib"
    if pylib.exists():
        extras.append(
            f"  _pylib/   ← persistent pip install target "
            f"(keep; deleting forces a re-install next run)"
        )
    if extras:
        print()
        print("Also present:")
        for line in extras:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
