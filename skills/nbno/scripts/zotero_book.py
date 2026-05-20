#!/usr/bin/env python3
"""
zotero_book.py — download a book from nb.no, OCR it, and emit a Zotero-ready
RDF + PDF pair.

Run from the nbno skill's scripts/ folder (or copy alongside nbno_run.sh):

    python zotero_book.py \\
        --id URN:NBN:no-nb_digibok_2008051600041 \\
        --out /path/to/outputs/folder \\
        [--cookie auto | --cookie /path/cookie.txt] \\
        [--bearer "<token>" --nbsso "nbsso=<value>"] \\
        [--resize 75] \\
        [--no-ocr]

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
       - If --bearer + --nbsso are supplied, use the fast IIIF downloader
         in-process (recommended for big books).
       - Otherwise shell out to nbno_run.sh, with --cookie if provided.
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
_TYPE_RE = re.compile(
    r"^(digibok|digavis|digifoto|digitidsskrift|digikart|digimanus|"
    r"digiprogramrapport|pliktmonografi|pliktperiodika)_[0-9A-Za-z]+$"
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
            f"ERROR: '{s}' is not a canonical nb.no media ID. "
            "Expected something like 'digibok_2008051600041'."
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


def fetch_nb_metadata(canonical_id: str, timeout: float = 30.0) -> dict:
    """Hit api.nb.no for the JSON metadata blob."""
    url = f"https://api.nb.no/catalog/v1/items/{urn_form(canonical_id)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    if title_infos:
        title = (title_infos[0].get("title") or md.get("title", "")).strip()
        subtitle = (title_infos[0].get("subTitle") or "").strip()
    else:
        title = (md.get("title") or "").strip()
        subtitle = ""

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
    publisher = (origin.get("publisher") or "").strip()
    place = (
        (md.get("geographic") or {}).get("placeString")
        or (md.get("geographic") or {}).get("city")
        or ""
    ).strip()
    if place in {"S.l.", "s.l.", "[S.l.]"}:
        place = ""   # "sine loco" — no real value to keep

    lang_code = ""
    for entry in md.get("languages") or []:
        code = (entry.get("code") or "").strip().lower()
        if code:
            lang_code = _LANG_TO_ZOTERO.get(code, code)
            break

    isbn = ""
    for ident in (md.get("identifiers") or {}).get("isbn") or []:
        isbn = ident if isinstance(ident, str) else str(ident)
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
        language=lang_code,
        isbn=isbn,
        num_pages=num_pages,
        extra="\n".join(extras),
    )


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------

_FS_SAFE = re.compile(r"[^A-Za-z0-9._\-()]+")


def _slug(s: str, maxlen: int = 60) -> str:
    """ASCII-fold + collapse to underscore-separated tokens."""
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _FS_SAFE.sub("_", s).strip("_")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("_")
    return s or "Untitled"


def compute_basename(book: rdfmod.NormalizedBook) -> str:
    """Compose AUTHOR_TITLE_(YEAR), filesystem-safe.

    Picks the first author's surname; falls back to the first creator of any
    kind, then "Unknown".
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
    if not surname:
        surname = "Unknown"
    title_for_name = book.title.split(":")[0]  # drop subtitle
    year = (book.year or "n.d.").strip()
    return f"{_slug(surname, 30)}_{_slug(title_for_name, 60)}_({_slug(year, 8)})"


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def download_via_iiif(
    canonical_id: str,
    out_pdf: Path,
    bearer: str,
    nbsso: str,
    resize_width: int = 1024,
    workers: int = 12,
) -> None:
    """Fast in-process downloader. Mirrors the SKILL.md fast-path recipe.

    Pulls the IIIF manifest, downloads each canvas at the given width, and
    stitches everything into a single PDF. Skips the back cover (_C2).
    """
    from concurrent.futures import ThreadPoolExecutor
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Pillow is required for the in-process IIIF downloader. "
            "Install with: pip install --break-system-packages Pillow"
        ) from exc

    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix="nbno_zotero_"))
    referer = f"https://www.nb.no/items/{urn_form(canonical_id)}"
    hdr_api = {"authorization": bearer}
    hdr_img = {"cookie": nbsso, "referer": referer}

    # Manifest
    manifest_url = f"https://api.nb.no/catalog/v1/items/{canonical_id}/manifest"
    req = urllib.request.Request(manifest_url, headers=hdr_api)
    with urllib.request.urlopen(req, timeout=30) as resp:
        manifest = json.loads(resp.read().decode("utf-8"))
    canvases = manifest["sequences"][0]["canvases"]

    entries: List[Dict[str, str]] = []
    for c in canvases:
        canvas_name = c["@id"].split("/")[-1]
        base = c["images"][0]["resource"]["service"]["@id"]
        entries.append({"canvas": canvas_name, "base_url": base})

    print(f"[iiif] manifest has {len(entries)} canvases; downloading...")

    def fetch_page(idx_entry: Tuple[int, Dict[str, str]]) -> Tuple[int, Optional[str]]:
        idx, entry = idx_entry
        if entry["canvas"].endswith("_C2"):
            return idx, None
        url = f"{entry['base_url']}/full/{resize_width},/0/default.jpg"
        req = urllib.request.Request(url, headers=hdr_img)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return idx, None
            raise
        path = tmpdir / f"page_{idx:04d}.jpg"
        path.write_bytes(data)
        return idx, str(path)

    t0 = time.time()
    results: Dict[int, Optional[str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, path in pool.map(
            fetch_page, list(enumerate(entries, start=1))
        ):
            results[idx] = path
    print(f"[iiif] done in {time.time()-t0:.1f}s; assembling PDF...")

    page_paths = [results[i] for i in sorted(results) if results[i]]
    if not page_paths:
        raise SystemExit("ERROR: no pages downloaded — check bearer/nbsso.")

    images = [Image.open(p).convert("RGB") for p in page_paths]
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(str(out_pdf), save_all=True, append_images=images[1:])
    # Clean up images now that the PDF is built.
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

def run_ocrmypdf(pdf_path: Path, languages: str = "nor+nno") -> None:
    """Add a searchable text layer in place. Uses --skip-text so pages that
    already have text aren't re-OCRed.

    Auto-installs ocrmypdf on first use. Tesseract and the Norwegian
    language packs must be present at the system level — on Debian/Ubuntu:
        sudo apt-get install tesseract-ocr tesseract-ocr-nor tesseract-ocr-nno
    """
    if shutil.which("ocrmypdf") is None:
        print("[ocr] installing ocrmypdf (one-time)...")
        rc = subprocess.call(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--break-system-packages", "ocrmypdf"]
        )
        if rc != 0 or shutil.which("ocrmypdf") is None:
            raise SystemExit(
                "ERROR: failed to install ocrmypdf. Install manually with: "
                "pip install --break-system-packages ocrmypdf"
            )
    cmd = [
        "ocrmypdf",
        "--language", languages,
        "--skip-text",            # don't redo pages that already have text
        "--optimize", "1",        # mild lossless optimisation
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
                         "Used by the nbno_run.sh fallback path.")
    ap.add_argument("--bearer", default=None,
                    help="Bearer token for api.nb.no — enables the fast IIIF "
                         "in-process downloader. Pair with --nbsso.")
    ap.add_argument("--nbsso", default=None,
                    help="nbsso=<value> cookie pair for IIIF image fetches.")
    ap.add_argument("--resize", type=int, default=None,
                    help="Page width in pixels for IIIF (default 1024) or "
                         "percentage for nbno_run.sh (suggested 75).")
    ap.add_argument("--workers", type=int, default=12,
                    help="Parallel downloaders for the IIIF path (default 12).")
    ap.add_argument("--no-ocr", action="store_true",
                    help="Skip the OCR step.")
    ap.add_argument("--ocr-langs", default="nor+nno",
                    help="Tesseract language string (default: nor+nno).")
    ap.add_argument("--skill-scripts-dir", default=str(_HERE),
                    help="Path to the nbno skill's scripts/ folder "
                         "(used to locate nbno_run.sh).")
    args = ap.parse_args(argv)

    canonical = normalise_id(args.id)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[meta] fetching nb.no metadata for {canonical}...")
    blob = fetch_nb_metadata(canonical)
    book = normalize_metadata(blob)

    base = compute_basename(book)
    pdf_name = f"{base}.pdf"
    rdf_name = f"{base}.rdf"
    pdf_path = out_dir / pdf_name
    rdf_path = out_dir / rdf_name
    print(f"[meta] basename: {base}")
    print(f"[meta] title:    {book.title}")
    print(f"[meta] authors:  "
          + ", ".join(f"{c.surname}, {c.given}".strip(", ")
                      for c in book.creators) or "(none)")
    print(f"[meta] year:     {book.year or '?'}    "
          f"publisher: {book.publisher or '?'}    "
          f"place: {book.place or '?'}")

    # ---- Download -----------------------------------------------------------
    if args.bearer and args.nbsso:
        print("[dl] using fast IIIF in-process downloader (bearer+nbsso)")
        download_via_iiif(
            canonical_id=canonical,
            out_pdf=pdf_path,
            bearer=args.bearer,
            nbsso=args.nbsso,
            resize_width=args.resize or 1024,
            workers=args.workers,
        )
    else:
        print("[dl] falling back to nbno_run.sh wrapper")
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
        run_ocrmypdf(pdf_path, languages=args.ocr_langs)
        print(f"[ocr] PDF now searchable ({pdf_path.stat().st_size/1e6:.1f} MB)")
    else:
        print("[ocr] skipped (--no-ocr)")

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
    print(f"Done. Two paired files in {out_dir}:")
    print(f"  {pdf_name}")
    print(f"  {rdf_name}   ← import this into Zotero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
