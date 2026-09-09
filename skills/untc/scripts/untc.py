#!/usr/bin/env python3
"""
untc.py - UN Treaty Collection CLI.

Pure-HTTP fetcher for the multilateral treaties deposited with the
UN Secretary-General (MTDSG) and the UN Treaty Series (UNTS).
No Selenium, no JS - UNTC publishes its source documents at
predictable doc/Publication paths once you know the MTDSG reference
(e.g. "IV-4" for the ICCPR) or the UNTS volume + registration number.

Subcommands:
  index      Build/refresh the MTDSG chapter index (treaty title -> ref).
  lookup     Fuzzy-search the cached index by treaty title or acronym.
  status     Download the MTDSG status document (parties + reservations
             + declarations) for a given ref, e.g. status XXIII-1.
  text       Download the UNTS treaty text for a ref, or for any
             UNTS-registered treaty via --vol/--reg or --vol/--page.
             Falls back to slicing the full volume PDF when UNTC has no
             per-treaty file (common for recent volumes).
  volume     List the table of contents of a UNTS volume (registration
             numbers, titles, first pages) - the way to find any of the
             thousands of treaties that have no MTDSG entry.
  fetch      Combo: resolve a name or ref, download status, then text.
  show       Print the extracted text of a previously cached document.

Examples:
  untc.py index --refresh
  untc.py lookup "vienna convention on the law of treaties"
  untc.py status XXIII-1
  untc.py status IV-11-b
  untc.py text XXIII-1
  untc.py fetch ICCPR
  untc.py text --vol 999 --reg 14668
  untc.py text --vol 729 --page 161          # "729 UNTS 161" -> NPT
  untc.py volume 729 --search non-proliferation
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
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
_default_cache = Path.home() / ".cache" / "untc"
CACHE_DIR = Path(os.environ.get("UNTC_CACHE_DIR", _default_cache)).expanduser()
TREATIES_DIR = CACHE_DIR / "treaties"
UNTS_DIR = CACHE_DIR / "unts"
VOLUMES_DIR = UNTS_DIR / "volumes"
INDEX_PATH = CACHE_DIR / "index.json"
SEED_INDEX = SKILL_ROOT / "cache" / "index.json"

BASE = "https://treaties.un.org"
USER_AGENT = (
    "untc-skill/0.2 (+https://github.com/StianOby/claude-legal-tools) "
    "Python-urllib treaty research tool"
)

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18,
    "XIX": 19, "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23,
    "XXIV": 24, "XXV": 25, "XXVI": 26, "XXVII": 27, "XXVIII": 28,
    "XXIX": 29, "XXX": 30,
}
INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}


def mtdsg_volume_for_chapter(chapter_int):
    """Vol I covers chapters I-XII, Vol II covers chapters XIII-XXIX."""
    return "I" if chapter_int <= 12 else "II"


DEFAULT_CHAPTER_RANGE = range(1, 30)

# MTDSG status documents are published in English and French only.
STATUS_LANGS = ("en", "fr")
# UNTS per-treaty files: English, French, and "Other" (the remaining
# authentic texts - Arabic, Chinese, Russian, Spanish ... - in one file).
TEXT_LANGS = {"en": "English", "fr": "French", "other": "Other"}

# Common acronyms and short names. UNTC titles spell things out, but in
# practice users say "ICCPR" or "VCLT". An alias hit is resolved directly.
# Every ref below was checked against the live chapter pages (Sept 2026).
ALIASES = {
    "iccpr":   "IV-4",
    "iccpr-op1": "IV-5",
    "iccpr-op2": "IV-12",
    "icescr":  "IV-3",
    "cescr":   "IV-3",
    "icescr-op": "IV-3-a",
    "cerd":    "IV-2",
    "icerd":   "IV-2",
    "cedaw":   "IV-8",
    "cedaw-op": "IV-8-b",
    "cat":     "IV-9",
    "uncat":   "IV-9",
    "opcat":   "IV-9-b",
    "crc":     "IV-11",
    "opac":    "IV-11-b",
    "crc-opac": "IV-11-b",
    "opsc":    "IV-11-c",
    "crc-opsc": "IV-11-c",
    "crc-opic": "IV-11-d",
    "icrmw":   "IV-13",
    "cmw":     "IV-13",
    "crpd":    "IV-15",
    "crpd-op": "IV-15-a",
    "iced":    "IV-16",
    "icppd":   "IV-16",
    "ced":     "IV-16",
    "vclt":    "XXIII-1",
    "vcssrt":  "XXIII-2",
    "vcltsio": "XXIII-3",
    "vcdr":    "III-3",
    "vccr":    "III-6",
    "unclos":  "XXI-6",
    "losc":    "XXI-6",
    "rome statute": "XVIII-10",
    "icc statute":  "XVIII-10",
    "refugee convention": "V-2",
    "1951 refugee convention": "V-2",
    "stateless persons": "V-3",
    "genocide convention": "IV-1",
    "tpnw":    "XXVI-9",
    "ctbt":    "XXVI-4",
    "ottawa convention": "XXVI-5",
    "mine ban treaty": "XXVI-5",
    "apmbc":   "XXVI-5",
    "att":     "XXVI-8",
    "arms trade treaty": "XXVI-8",
    "unfccc":  "XXVII-7",
    "kyoto protocol": "XXVII-7-a",
    "paris agreement": "XXVII-7-d",
    "cbd":     "XXVII-8",
    "untoc":   "XVIII-12",
    "palermo convention": "XVIII-12",
    "uncac":   "XVIII-14",
}

# Well-known treaties that are registered in the UNTS but NOT deposited with
# the Secretary-General (so there is no MTDSG status document). This is only
# a convenience list of the most-requested ones; thousands of other UNTS-only
# treaties are reachable through `volume` / `text --vol --reg|--page`.
# (volume, registration number, title) - all URLs verified Sept 2026.
UNTS_ONLY = {
    "npt": (729, "10485", "Treaty on the Non-Proliferation of Nuclear Weapons"),
    "non-proliferation treaty": (729, "10485", "Treaty on the Non-Proliferation of Nuclear Weapons"),
    "geneva convention i": (75, "970", "Geneva Convention (I) for the Amelioration of the Condition of the Wounded and Sick in Armed Forces in the Field"),
    "geneva convention ii": (75, "971", "Geneva Convention (II) for the Amelioration of the Condition of Wounded, Sick and Shipwrecked Members of Armed Forces at Sea"),
    "geneva convention iii": (75, "972", "Geneva Convention (III) relative to the Treatment of Prisoners of War"),
    "geneva convention iv": (75, "973", "Geneva Convention (IV) relative to the Protection of Civilian Persons in Time of War"),
    "gc i": (75, "970", "Geneva Convention (I)"),
    "gc ii": (75, "971", "Geneva Convention (II)"),
    "gc iii": (75, "972", "Geneva Convention (III)"),
    "gc iv": (75, "973", "Geneva Convention (IV)"),
    "additional protocol i": (1125, "17512", "Protocol Additional to the Geneva Conventions of 12 August 1949, and relating to the Protection of Victims of International Armed Conflicts (Protocol I)"),
    "additional protocol ii": (1125, "17513", "Protocol Additional to the Geneva Conventions of 12 August 1949, and relating to the Protection of Victims of Non-International Armed Conflicts (Protocol II)"),
    "ap i": (1125, "17512", "Additional Protocol I"),
    "ap ii": (1125, "17513", "Additional Protocol II"),
}

# ---------------------------------------------------------------------------
# Small file helpers (UTF-8, atomic)
# ---------------------------------------------------------------------------

def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_json(path: Path, obj) -> None:
    _write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _has_content(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False

# ---------------------------------------------------------------------------
# HTTP (no third-party deps)
# ---------------------------------------------------------------------------

class DocumentNotFound(Exception):
    """UNTC answers a missing document with HTTP 200 and an HTML page."""


def http_get(url, *, binary=False, timeout=60, retries=2):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            return data if binary else data.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                break
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def download_pdf(url, dest: Path, *, force=False, timeout=180) -> Path:
    """Download a PDF atomically. Raises DocumentNotFound if the server
    returns something that is not a PDF (UNTC serves an HTML 'not found'
    page with status 200), and never leaves a bad file in the cache."""
    if _has_content(dest) and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            head = resp.read(1024)
            if not head.startswith(b"%PDF"):
                raise DocumentNotFound(url)
            with open(tmp, "wb") as f:
                f.write(head)
                shutil.copyfileobj(resp, f)
        os.replace(tmp, dest)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise DocumentNotFound(url) from e
        raise
    finally:
        if tmp.exists():
            tmp.unlink()
    return dest

# ---------------------------------------------------------------------------
# Reference parsing
# ---------------------------------------------------------------------------

# Forms used by UNTC itself (ViewDetails mtdsg_no= and the PDF file names):
#   IV-4         chapter-number
#   IV-11-b      chapter-number-letter   (optional protocols, amendments)
#   XI-B-16      chapter-subchapter-number (chapter XI has sub-chapters A-E)
#   XI-D-1-a     chapter-subchapter-number-letter
#   XI-B-16-1    chapter-subchapter-number-number (the UN vehicle
#                Regulations annexed to the 1958 Agreement, XI-B-16-0 ...)
# Also accepted on input: IV-11b, IV.11.b, iv-11-B.
REF_RE = re.compile(
    r"^([IVXLC]+)[-.](?:([A-Z])[-.])?(\d+)(?:[-.]?([A-Z]|\d+[A-Z]?))?$", re.I
)


@dataclass
class MTDSGRef:
    chapter_roman: str
    chapter_int: int
    subchapter: str      # "" or "A".."E"
    section: int
    suffix: str = ""     # "" / "a".."z" (protocols) / "1", "120", "0H" (XI-B-16 regulations)

    @classmethod
    def parse(cls, raw):
        s = raw.strip().replace(" ", "")
        m = REF_RE.match(s)
        if not m:
            raise ValueError(
                "bad MTDSG ref %r; expected forms like IV-4, XXIII-1, "
                "IV-11-b or XI-B-16" % raw
            )
        roman = m.group(1).upper()
        if roman not in ROMAN_TO_INT:
            raise ValueError("unknown chapter roman numeral: %s" % roman)
        suffix = m.group(4) or ""
        suffix = suffix.lower() if suffix.isalpha() else suffix.upper()
        return cls(roman, ROMAN_TO_INT[roman], (m.group(2) or "").upper(),
                   int(m.group(3)), suffix)

    @property
    def slug(self):
        """The ref exactly as UNTC writes it: IV-4, IV-11-b, XI-B-16."""
        parts = [self.chapter_roman]
        if self.subchapter:
            parts.append(self.subchapter)
        parts.append(str(self.section))
        if self.suffix:
            parts.append(self.suffix)
        return "-".join(parts)

    def __str__(self):
        return self.slug


def looks_like_ref(raw: str) -> bool:
    return bool(REF_RE.match(raw.strip().replace(" ", "")))

# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def url_chapter_index(chapter_int, subid="A", lang="en"):
    return "%s/Pages/Treaties.aspx?id=%d&subid=%s&clang=_%s" % (BASE, chapter_int, subid, lang)


def url_view_details(ref, lang="en"):
    """The human-readable treaty page on treaties.un.org."""
    return (
        "%s/Pages/ViewDetails.aspx?src=TREATY&mtdsg_no=%s&chapter=%d&clang=_%s"
        % (BASE, urllib.parse.quote(ref.slug), ref.chapter_int, lang)
    )


def url_mtdsg_status(ref, lang="en"):
    vol = mtdsg_volume_for_chapter(ref.chapter_int)
    return (
        "%s/doc/Publication/MTDSG/Volume%%20%s/Chapter%%20%s/%s.%s.pdf"
        % (BASE, vol, ref.chapter_roman, ref.slug, lang)
    )


def url_unts_text(volume, reg_num, lang="en", series="I"):
    return (
        "%s/doc/Publication/UNTS/Volume%%20%d/volume-%d-%s-%s-%s.pdf"
        % (BASE, volume, volume, series, reg_num, TEXT_LANGS[lang])
    )


def url_unts_volume(volume):
    return "%s/doc/Publication/UNTS/Volume%%20%d/v%d.pdf" % (BASE, volume, volume)

# ---------------------------------------------------------------------------
# Chapter index harvesting
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    ref: str
    chapter_int: int
    subchapter: str
    title: str
    place_date: str


_ANCHOR_RE = re.compile(
    r'<a[^>]+href="[^"]*mtdsg_no=([IVXLC]+(?:-[A-Z])?-\d+(?:-[a-z]|-\d+[A-Z]?)?)[^"]*"[^>]*>'
    r"([\s\S]{1,1500}?)</a>",
    re.I,
)


def parse_chapter_index(page_html, chapter_int):
    page_html = re.sub(r"<script[\s\S]*?</script>", "", page_html, flags=re.I)
    page_html = re.sub(r"<style[\s\S]*?</style>", "", page_html, flags=re.I)
    out = []
    seen = set()
    for m in _ANCHOR_RE.finditer(page_html):
        try:
            ref = MTDSGRef.parse(m.group(1))
        except ValueError:
            continue
        if ref.slug in seen:
            continue
        seen.add(ref.slug)
        inner = re.sub(r"<[^>]+>", " ", m.group(2))
        text = html.unescape(inner)
        # UNTC writes "Title.  Place, date" with two no-break spaces between.
        if "\xa0\xa0" in text:
            title, _, place = text.partition("\xa0\xa0")
        else:
            title, _, place = text.partition(".  ")
        title = re.sub(r"\s+", " ", title).strip().rstrip(".")
        place = re.sub(r"\s+", " ", place).strip().rstrip(".")
        out.append(IndexEntry(ref=ref.slug, chapter_int=chapter_int,
                              subchapter=ref.subchapter, title=title,
                              place_date=place))
    return out


def _seed_index_if_needed():
    """Copy the bundled snapshot to the cache dir if no live index exists yet."""
    if _has_content(INDEX_PATH) or not SEED_INDEX.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(SEED_INDEX), str(INDEX_PATH))


def build_index(*, refresh=False, polite_delay=0.4,
                chapter_range=DEFAULT_CHAPTER_RANGE):
    _seed_index_if_needed()
    if _has_content(INDEX_PATH) and not refresh:
        return _read_json(INDEX_PATH)
    index = []
    chapters_seen = []
    for ch in chapter_range:
        chapter_entries = []
        # Chapter XI is split into sub-chapters A-E, each on its own page
        # (subid=A, B, ...). Other chapters return the same list for every
        # subid, so we only continue past A when the refs carry a letter.
        for subid in "ABCDEFGH":
            url = url_chapter_index(ch, subid)
            try:
                page_html = http_get(url)
            except Exception as e:
                print("  chapter %d%s: skipped (%s)" % (ch, subid if subid != "A" else "", e),
                      file=sys.stderr)
                break
            entries = parse_chapter_index(page_html, ch)
            time.sleep(polite_delay)
            if not entries:
                break
            chapter_entries.extend(entries)
            if not entries[0].subchapter:
                break
        if not chapter_entries:
            continue
        chapters_seen.append(ch)
        index.extend(asdict(e) for e in chapter_entries)
        print("  chapter %2d: %d treaties" % (ch, len(chapter_entries)), file=sys.stderr)
    payload = {
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://treaties.un.org/Pages/Treaties.aspx",
        "chapters": chapters_seen,
        "treaties": index,
    }
    _write_json(INDEX_PATH, payload)
    return payload


def load_index():
    _seed_index_if_needed()
    if not _has_content(INDEX_PATH):
        raise SystemExit(
            "no cached index - run `untc.py index` first to build it."
        )
    return _read_json(INDEX_PATH)


def _norm_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def search_index(query, *, limit=10):
    """Return [(score, entry)] best-first. Scores: 1000 alias hit, 100 the
    whole query occurs in title/place, +50 title starts with it, +5 per
    matching word."""
    payload = load_index()
    q = _norm_query(query)
    q_tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    aliased_ref = ALIASES.get(q) or ALIASES.get(q.replace(" ", "-"))
    by_ref = {e["ref"]: e for e in payload["treaties"]}
    scored = []
    for entry in payload["treaties"]:
        hay = (entry["title"] + " " + entry["place_date"]).lower()
        score = 0
        if q in hay:
            score += 100
        for t in q_tokens:
            if re.search(r"\b" + re.escape(t) + r"\b", hay):
                score += 5
        if hay.startswith(q):
            score += 50
        if aliased_ref and entry["ref"] == aliased_ref:
            score += 1000
        if score:
            scored.append((score, entry))
    if aliased_ref and aliased_ref in by_ref and not any(
        e["ref"] == aliased_ref for _, e in scored
    ):
        scored.insert(0, (1000, by_ref[aliased_ref]))
    scored.sort(key=lambda x: (-x[0], len(x[1]["title"])))
    return scored[:limit]

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _pypdf_reader():
    try:
        from pypdf import PdfReader  # type: ignore
        return PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            return PdfReader
        except Exception:
            return None


def _pdf_pages_text(pdf_path: Path) -> Optional[list]:
    """Per-page text via pypdf, or None if pypdf is unavailable."""
    PdfReader = _pypdf_reader()
    if PdfReader is None:
        return None
    reader = PdfReader(str(pdf_path))
    return [(p.extract_text() or "") for p in reader.pages]


def _pdftotext(pdf_path: Path, txt_path: Path) -> bool:
    exe = shutil.which("pdftotext")
    if not exe:
        return False
    # Deliberately NOT -layout: the MTDSG status docs interleave their dot
    # leaders with the dates in layout mode and merge the two reservation
    # columns line by line, which makes the text unusable for grepping.
    r = subprocess.run([exe, "-enc", "UTF-8", str(pdf_path), str(txt_path)],
                       capture_output=True, text=True)
    return r.returncode == 0 and _has_content(txt_path)


def extract_text(pdf_path: Path, *, force=False) -> Path:
    """Extract a PDF to <same name>.txt. pypdf is preferred: on the MTDSG
    status documents it gives one clean row per participant and readable
    reservation text; pdftotext is the fallback."""
    txt_path = pdf_path.with_suffix(".txt")
    if _has_content(txt_path) and not force:
        return txt_path
    pages = _pdf_pages_text(pdf_path)
    if pages is not None and any(p.strip() for p in pages):
        _write_text(txt_path, "\n\f\n".join(pages))
        return txt_path
    if _pdftotext(pdf_path, txt_path):
        return txt_path
    if pages is None and not shutil.which("pdftotext"):
        raise SystemExit(
            "neither pypdf nor `pdftotext` is available; "
            "`pip install pypdf` (preferred) or install poppler-utils"
        )
    raise SystemExit("could not extract any text from %s" % pdf_path)

# ---------------------------------------------------------------------------
# MTDSG status doc handling
# ---------------------------------------------------------------------------

_LABELS = ("ENTRY INTO FORCE:", "REGISTRATION:", "STATUS:", "TEXT:", "Note:",
           "ENTRÉE EN VIGUEUR:", "ENREGISTREMENT:", "ÉTAT:", "TEXTE:", "Note :")
# "16 December 1966", "16 décembre 1966", "1er juillet 1968"; a footnote
# number is often glued to the year ("13 February 19461").
_DATE = r"\d{1,2}(?:er)?\s+[A-Za-zÀ-ÿ]+\s+\d{4}"
_DATE_LINE = _DATE + r"\d{0,2}\s*$"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_status_text(text):
    """Pull the header block of an MTDSG status document apart.

    The first page reads (pypdf order):
        4. INTERNATIONAL COVENANT ON CIVIL AND POLITICAL RIGHTS
        New York, 16 December 1966
        ENTRY INTO FORCE: 23 March 1976, in accordance with article 49 ...
        REGISTRATION: 23 March 1976, No. 14668.
        STATUS: Signatories: 74. Parties: 175.
        TEXT: United Nations, Treaty Series, vol. 999, p. 171 ...
    Labels and values are located by segment, with whole-header regex
    fallbacks for extractors that separate the label column.
    """
    out = {}
    head = text[:6000].replace(" ", " ").replace(" ", " ").replace("\xa0", " ")
    head = head.replace("\f", "\n")
    lines = [ln.rstrip() for ln in head.split("\n")]

    chap_m = re.search(r"CHAPTER\s+([IVXLC]+)\s*\n\s*([^\n]+)", head)
    if chap_m:
        out["chapter_roman"] = chap_m.group(1)
        out["chapter_heading"] = _clean(chap_m.group(2))

    # Title: "4. TITLE" or "11. b) Optional Protocol ..." possibly wrapped
    # onto following lines, ending at the place/date line or a label.
    title_lines: list = []
    for i, ln in enumerate(lines[:40]):
        m = re.match(r"^\s*(\d+)\.\s*(?:([a-z])\)\s*)?(\S.*)$", ln)
        if not m or len(m.group(3)) < 6 or ln.strip().startswith(_LABELS):
            continue
        if re.match(r"^\s*\d+\.\s+[A-Z][a-z]+\s+\d{4}\s*$", ln):
            continue  # a bare date such as "23. March 1976" is not a title
        title_lines.append(m.group(3))
        for nxt in lines[i + 1:i + 6]:
            s = nxt.strip()
            if (not s or s == "." or s.startswith(_LABELS)
                    or re.search(_DATE_LINE, s)):
                break
            title_lines.append(s)
        break
    if title_lines:
        out["title"] = _clean(" ".join(title_lines)).rstrip(".")

    pd_m = re.search(r"^\s*([A-Z][^\n]*?),\s*(" + _DATE + r")\d{0,2}\s*$", head, re.M)
    if pd_m:
        out["place"] = _clean(pd_m.group(1))
        out["date"] = pd_m.group(2)

    # Segment the header by its labels.
    seg = {}
    positions = []
    for lab in _LABELS:
        p = head.find(lab)
        if p >= 0:
            positions.append((p, lab))
    part_pos = head.find("Participant")
    if part_pos > 0:
        positions.append((part_pos, "Participant"))
    positions.sort()
    for k, (p, lab) in enumerate(positions):
        end = positions[k + 1][0] if k + 1 < len(positions) else len(head)
        seg[lab] = head[p + len(lab):end]

    eif = seg.get("ENTRY INTO FORCE:", "")
    if _clean(eif):
        out["entry_into_force"] = _clean(eif)

    reg_src = seg.get("REGISTRATION:", "") or head
    reg_m = re.search(r"(" + _DATE + r")\s*,\s*No\.?\s*([\d]+)", reg_src)
    if not reg_m:
        reg_m = re.search(r"(" + _DATE + r")\s*,\s*No\.?\s*([\d]+)", head)
    if reg_m:
        out["registration_date"] = reg_m.group(1)
        out["registration_number"] = reg_m.group(2)

    stat_src = seg.get("STATUS:", "") or head
    sig_m = re.search(r"Signatories:\s*(\d+)", stat_src) or re.search(r"Signatories:\s*(\d+)", head)
    par_m = re.search(r"Parties:\s*(\d+)", stat_src) or re.search(r"Parties:\s*(\d+)", head)
    if sig_m:
        out["signatories"] = int(sig_m.group(1))
    if par_m:
        out["parties"] = int(par_m.group(1))

    text_src = seg.get("TEXT:", "") or seg.get("TEXTE:", "") or head[:part_pos if part_pos > 0 else None]
    vol_m = re.search(r"vol\.?\s*(\d{1,5})\s*,\s*p\.?\s*(\d{1,5})", text_src, re.I)
    if not vol_m:
        vol_m = re.search(r"vol\.?\s*(\d{1,5})\s*,\s*p\.?\s*(\d{1,5})", head, re.I)
    if vol_m:
        out["unts_volume"] = int(vol_m.group(1))
        out["unts_page"] = int(vol_m.group(2))
    else:
        # Recent treaties: "Treaty Series, vol. 3370." with no page yet.
        vol_only = re.search(r"Treaty\s+Series\s*,\s*vol\.?\s*(\d{1,5})", text_src, re.I)
        if vol_only:
            out["unts_volume"] = int(vol_only.group(1))
    if _clean(seg.get("TEXT:", "")):
        out["text_note"] = _clean(seg["TEXT:"])[:400]
    return out


def treaty_dir(ref):
    return TREATIES_DIR / ref.chapter_roman / ref.slug


def _check_status_lang(lang):
    if lang not in STATUS_LANGS:
        raise SystemExit(
            "MTDSG status documents exist only in %s (got %r)"
            % ("/".join(STATUS_LANGS), lang)
        )


def fetch_status(ref, *, lang="en", force=False):
    _check_status_lang(lang)
    out_dir = treaty_dir(ref)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / ("status.%s.pdf" % lang)
    url = url_mtdsg_status(ref, lang)
    try:
        download_pdf(url, pdf, force=force)
    except DocumentNotFound:
        raise SystemExit(
            "no MTDSG status document at %s\n"
            "Check the ref on %s - optional protocols use the form IV-11-b, "
            "chapter XI refs the form XI-B-16." % (url, url_view_details(ref))
        )
    txt = extract_text(pdf, force=force)
    text = txt.read_text(encoding="utf-8", errors="replace")
    meta = parse_status_text(text)
    meta["ref"] = ref.slug
    meta["lang"] = lang
    meta["status_pdf"] = str(pdf)
    meta["status_txt"] = str(txt)
    meta["source_url"] = url
    meta["details_url"] = url_view_details(ref)
    meta["fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(out_dir / ("meta.%s.json" % lang), meta)
    if lang == "en":
        _write_json(out_dir / "meta.json", meta)
    return meta

# ---------------------------------------------------------------------------
# UNTS volumes (table of contents + slicing) - the route to UNTS-only treaties
# ---------------------------------------------------------------------------

def volume_pdf(volume: int, *, force=False) -> Path:
    pdf = VOLUMES_DIR / ("v%d.pdf" % volume)
    try:
        download_pdf(url_unts_volume(volume), pdf, force=force)
    except DocumentNotFound:
        raise SystemExit("no volume PDF at %s (does UNTS volume %d exist?)"
                         % (url_unts_volume(volume), volume))
    return pdf


def volume_pages(volume: int, *, force=False) -> list:
    """Per-page text of the whole volume, cached as JSON next to the PDF."""
    cache = VOLUMES_DIR / ("v%d.pages.json" % volume)
    if _has_content(cache) and not force:
        return _read_json(cache)
    pdf = volume_pdf(volume, force=force)
    pages = _pdf_pages_text(pdf)
    if pages is None:
        # pdftotext fallback: split on form feeds
        tmp = pdf.with_suffix(".txt")
        if not _pdftotext(pdf, tmp):
            raise SystemExit("cannot extract text from %s (install pypdf)" % pdf)
        pages = tmp.read_text(encoding="utf-8", errors="replace").split("\f")
    pages = [p.replace(" ", " ").replace("\xa0", " ") for p in pages]
    _write_json(cache, pages)
    return pages


_TOC_ENTRY_RE = re.compile(r"No\.\s*(\d{3,6})\s*\.\s*", re.I)
# French contents entries are written "No 10483." (no full stop after No)
_TOC_FRENCH_RE = re.compile(r"(?:TABLE\s+DES\s+MATI|\bNo\s+\d{3,6}\s*\.)", re.I)
_TOC_HEADER_RE = re.compile(
    r"^\s*(?:[IVXL]+\s+)?United Nations\s*[-\u2014\u2013]+\s*Treaty Series[^\n]*$"
    r"|^\s*Volume\s+\d+,\s*Table of Contents\s*$"
    r"|^\s*Pages?\s*$"
    r"|^\s*[IVXL]+\s*$",
    re.I | re.M,
)


def volume_toc(volume: int, *, force=False) -> list:
    """Parse the English table of contents: [{reg, title, page}, ...].
    Entries under ANNEX A (later actions on earlier treaties) are included
    and flagged with "annex": "A"."""
    pages = volume_pages(volume, force=force)
    start = None
    for i, p in enumerate(pages[:20]):
        if re.search(r"TABLE\s+OF\s+CONTENTS", p, re.I):
            start = i
            break
    if start is None:
        return []
    toc = []
    for p in pages[start:start + 60]:
        if _TOC_ENTRY_RE.search(p) and not re.search(r"TABLE\s+DES\s+MATI", p, re.I):
            toc.append(_TOC_HEADER_RE.sub("", p))
            continue
        if _TOC_FRENCH_RE.search(p) or not p.strip():
            continue  # French contents page (they alternate with English in
                      # older volumes) or a blank verso - keep going
        if toc:
            break
    text = "\n".join(toc)
    text = text.replace("\f", "\n")
    entries = []
    annex = ""
    splits = list(_TOC_ENTRY_RE.finditer(text))
    for k, m in enumerate(splits):
        chunk_end = splits[k + 1].start() if k + 1 < len(splits) else len(text)
        chunk = text[m.end():chunk_end]
        before = text[max(0, m.start() - 400):m.start()]
        if re.search(r"ANNEX\s+A", before):
            annex = "A"
        elif re.search(r"ANNEX\s+B", before):
            annex = "B"
        elif re.search(r"ANNEX\s+C", before):
            annex = "C"
        chunk = re.split(r"\n\s*ANNEX\s+[ABC]\b", chunk, maxsplit=1, flags=re.I)[0]
        pm = re.search(r"(\d{1,4})\s*$", chunk.strip())
        page = int(pm.group(1)) if pm else None
        body = chunk.strip()[:pm.start()] if pm else chunk
        body = re.sub(r"\.{2,}|(?:\.\s){2,}", " ", body)
        entries.append({
            "reg": m.group(1),
            "title": _clean(body).rstrip(". "),
            "page": page,
            "annex": annex,
        })
    return entries


def _page_starts_with_reg(page_text: str, reg: str) -> bool:
    head = page_text.lstrip()[:200]
    return re.search(r"(^|\n)\s*No\.\s*%s\b" % re.escape(reg), head) is not None


def locate_in_volume(pages: list, reg: str, toc_end_hint: int = 0):
    """Return (start_idx, end_idx) of the pages holding registration `reg`.
    The treaty starts on the first page (after the contents) whose text opens
    with "No. <reg>" and ends where the next "No. <other>" page or ANNEX A
    begins."""
    start = None
    for i in range(toc_end_hint, len(pages)):
        if _page_starts_with_reg(pages[i], reg):
            start = i
            break
    if start is None:
        return None
    end = len(pages)
    for j in range(start + 1, len(pages)):
        head = pages[j].lstrip()[:200]
        m = re.search(r"(^|\n)\s*No\.\s*(\d{3,6})\b", head)
        if m and m.group(2) != reg:
            end = j
            break
        if re.match(r"\s*ANNEX\s+[ABC]\b", head):
            end = j
            break
    return start, end


def _toc_end_index(pages: list) -> int:
    for i, p in enumerate(pages[:60]):
        if re.search(r"TABLE\s+DES\s+MATI", p, re.I):
            # skip through the French contents too
            for j in range(i, min(i + 40, len(pages))):
                if not _TOC_ENTRY_RE.search(pages[j]):
                    return j
            return i + 1
    return 0


def resolve_page_to_reg(volume: int, page: int) -> Optional[dict]:
    """Map a printed page number (as in a citation '729 UNTS 161') to the
    contents entry that starts at or before that page."""
    best = None
    for e in volume_toc(volume):
        if e["annex"] or e["page"] is None:
            continue
        if e["page"] <= page and (best is None or e["page"] > best["page"]):
            best = e
    return best


def fetch_text(ref=None, *, volume=None, reg_num=None, page=None, lang="en",
               force=False, series="I"):
    if lang not in TEXT_LANGS:
        raise SystemExit("--lang for text must be one of %s" % "/".join(TEXT_LANGS))
    resolved_from = None
    if volume is None or (reg_num is None and page is None):
        if ref is None:
            raise ValueError("need a ref, or --vol with --reg or --page")
        meta_path = treaty_dir(ref) / "meta.json"
        if not meta_path.exists():
            fetch_status(ref, lang="en", force=False)
        meta = _read_json(meta_path)
        volume = volume or meta.get("unts_volume")
        reg_num = reg_num or meta.get("registration_number")
        page = page or meta.get("unts_page")
        if volume is None or (reg_num is None and page is None):
            raise SystemExit(
                "could not determine UNTS volume/registration from the "
                "status doc for %s; pass --vol/--reg manually" % ref
            )
    if reg_num is None:
        hit = resolve_page_to_reg(volume, page)
        if not hit:
            raise SystemExit("no contents entry at or before p. %d in volume %d; "
                             "run `untc.py volume %d` to see the contents" % (page, volume, volume))
        reg_num = hit["reg"]
        resolved_from = {"page": page, "toc_entry": hit}
    reg_num = str(reg_num)

    out_dir = treaty_dir(ref) if ref is not None else UNTS_DIR / ("v%d-%s-%s" % (volume, series, reg_num))
    out_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "ref": ref.slug if ref else None,
        "volume": volume,
        "registration_number": reg_num,
        "series": series,
        "lang": lang,
    }
    if resolved_from:
        info["resolved_from"] = resolved_from

    # 1. Per-treaty PDF (exists for most older volumes)
    url = url_unts_text(volume, reg_num, lang, series=series)
    pdf = out_dir / ("text.%s.pdf" % lang)
    try:
        download_pdf(url, pdf, force=force)
        txt = extract_text(pdf, force=force)
        info.update({"via": "treaty-pdf", "text_pdf": str(pdf),
                     "text_txt": str(txt), "source_url": url})
        return info

    except DocumentNotFound:
        pass

    # 2. Slice the full volume PDF (the only file for many recent volumes).
    try:
        pages = volume_pages(volume, force=force)
    except SystemExit as e:
        hint = ""
        if ref is not None:
            hint = ("\nThe certified true copy of the text is linked from the treaty's "
                    "details page: %s" % url_view_details(ref))
        raise SystemExit(
            "no per-treaty PDF at %s and UNTS volume %d is not published on "
            "treaties.un.org yet (%s).%s" % (url, volume, e, hint)
        )
    loc = locate_in_volume(pages, reg_num, _toc_end_index(pages))
    if loc is None:
        raise SystemExit(
            "no per-treaty PDF at %s and registration No. %s was not found "
            "inside the volume PDF %s; run `untc.py volume %d` to inspect "
            "the contents" % (url, reg_num, url_unts_volume(volume), volume)
        )
    start, end = loc
    txt = out_dir / ("text.%s.txt" % lang)
    header = ("[UNTS volume %d, registration No. %s - pages %d-%d of the "
              "volume PDF %s; all language versions in sequence]\n\n"
              % (volume, reg_num, start + 1, end, url_unts_volume(volume)))
    _write_text(txt, header + "\n\f\n".join(pages[start:end]))
    info.update({
        "via": "volume-pdf",
        "text_pdf": str(volume_pdf(volume)),
        "pdf_pages": [start + 1, end],
        "text_txt": str(txt),
        "source_url": url_unts_volume(volume),
        "note": "no per-treaty file; text sliced from the volume PDF "
                "(contains every authentic language in sequence)",
    })
    return info

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_index(args):
    payload = build_index(refresh=args.refresh)
    print("index: %d treaties across %d chapters -> %s" %
          (len(payload["treaties"]), len(payload["chapters"]), INDEX_PATH))


def cmd_lookup(args):
    q = _norm_query(args.query)
    if q in UNTS_ONLY:
        vol, reg, title = UNTS_ONLY[q]
        print("  UNTS only  %s" % title)
        print("             -- not deposited with the UN Secretary-General: no "
              "MTDSG status doc. Text: `untc.py text --vol %d --reg %s`" % (vol, reg))
    hits = search_index(args.query, limit=args.limit)
    if not hits and q not in UNTS_ONLY:
        print("(no matches; the treaty may not be deposited with the "
              "Secretary-General - try `untc.py volume <N>` with a UNTS "
              "citation, or `untc.py index --refresh`)")
        return
    for score, h in hits:
        print("  %-10s  %s" % (h["ref"], h["title"]))
        if h.get("place_date"):
            print("              -- %s" % h["place_date"])


def cmd_status(args):
    ref = MTDSGRef.parse(args.ref)
    meta = fetch_status(ref, lang=args.lang, force=args.force)
    _print_json(meta)


def cmd_text(args):
    ref = MTDSGRef.parse(args.ref) if args.ref else None
    if ref is None and args.vol is None:
        raise SystemExit("give a ref, or --vol with --reg or --page")
    info = fetch_text(
        ref=ref, volume=args.vol, reg_num=args.reg, page=args.page,
        lang=args.lang, force=args.force, series=args.series,
    )
    _print_json(info)


def cmd_volume(args):
    entries = volume_toc(args.volume, force=args.force)
    if not entries:
        raise SystemExit("could not parse a table of contents for volume %d" % args.volume)
    if args.search:
        s = args.search.lower()
        entries = [e for e in entries if s in e["title"].lower()]
    if args.json:
        _print_json({"volume": args.volume, "source_url": url_unts_volume(args.volume),
                     "entries": entries})
        return
    print("UNTS volume %d - %d entries (%s)" % (args.volume, len(entries), url_unts_volume(args.volume)))
    for e in entries:
        tag = ("  [annex %s]" % e["annex"]) if e["annex"] else ""
        print("  No. %-7s p. %-5s %s%s" % (e["reg"], e["page"] if e["page"] is not None else "?",
                                           e["title"][:110], tag))


def cmd_fetch(args):
    raw = args.query.strip()
    q = _norm_query(raw)
    if q in UNTS_ONLY:
        vol, reg, title = UNTS_ONLY[q]
        print("resolved %r -> UNTS vol. %d No. %s (%s); not deposited with the "
              "Secretary-General, so there is no MTDSG status document"
              % (raw, vol, reg, title), file=sys.stderr)
        lang = args.lang if args.lang in TEXT_LANGS else "en"
        info = fetch_text(volume=vol, reg_num=reg, lang=lang, force=args.force)
        info["title"] = title
        _print_json({"status": None, "text": info})
        return
    if looks_like_ref(raw):
        ref = MTDSGRef.parse(raw)
    else:
        hits = search_index(raw, limit=5)
        if not hits:
            raise SystemExit("no treaty matched %r; try `untc.py lookup`, or "
                             "`untc.py volume <N>` for a UNTS-only treaty." % raw)
        score, top = hits[0]
        tied = [h for sc, h in hits if sc == score]
        words = [t for t in re.split(r"\W+", q) if len(t) > 2]
        if score < 100 or (len(tied) > 1 and len(words) <= 1):
            why = ("no title contains it" if score < 100
                   else "%d titles match equally well" % len(tied))
            lines = ["%r is ambiguous - %s. Candidates:" % (raw, why)]
            lines += ["  %-10s %s" % (h["ref"], h["title"][:100]) for _, h in hits]
            lines.append("re-run with the ref, e.g. `untc.py fetch %s`" % hits[0][1]["ref"])
            raise SystemExit("\n".join(lines))
        ref = MTDSGRef.parse(top["ref"])
        print("resolved %r -> %s: %s" % (raw, ref, top["title"]), file=sys.stderr)
        if len(tied) > 1:
            print("  (other candidates: %s)" % ", ".join(
                "%s %s" % (h["ref"], h["title"][:60]) for h in tied[1:4]), file=sys.stderr)
    status = fetch_status(ref, lang=args.lang, force=args.force)
    text_info = None
    if not args.no_text:
        try:
            text_info = fetch_text(ref=ref, lang=args.lang, force=args.force)
        except SystemExit as e:
            text_info = {"error": str(e)}
        except Exception as e:  # network etc.
            text_info = {"error": "%s: %s" % (type(e).__name__, e)}
    _print_json({"status": status, "text": text_info})


def cmd_show(args):
    if args.vol is not None:
        if args.reg is None:
            raise SystemExit("--vol needs --reg")
        base = UNTS_DIR / ("v%d-I-%s" % (args.vol, args.reg))
        txt = base / ("text.%s.txt" % args.lang)
    else:
        if not args.ref:
            raise SystemExit("give a ref, or --vol and --reg")
        ref = MTDSGRef.parse(args.ref)
        base = treaty_dir(ref)
        name = "status" if args.kind == "status" else "text"
        txt = base / ("%s.%s.txt" % (name, args.lang))
    if not txt.exists():
        raise SystemExit("not cached: %s - run `untc.py status`/`text` first" % txt)
    sys.stdout.write(txt.read_text(encoding="utf-8", errors="replace"))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="untc.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index", help="build/refresh chapter index")
    p_idx.add_argument("--refresh", action="store_true")
    p_idx.set_defaults(func=cmd_index)

    p_look = sub.add_parser("lookup", help="search the cached index")
    p_look.add_argument("query")
    p_look.add_argument("--limit", type=int, default=10)
    p_look.set_defaults(func=cmd_lookup)

    p_st = sub.add_parser("status", help="download MTDSG status doc")
    p_st.add_argument("ref", help="MTDSG ref like XXIII-1, IV-11-b or XI-B-16")
    p_st.add_argument("--lang", default="en", choices=list(STATUS_LANGS))
    p_st.add_argument("--force", action="store_true")
    p_st.set_defaults(func=cmd_status)

    p_tx = sub.add_parser("text", help="download UNTS treaty text")
    p_tx.add_argument("ref", nargs="?", help="MTDSG ref (or use --vol with --reg/--page)")
    p_tx.add_argument("--vol", type=int, help="UNTS volume number")
    p_tx.add_argument("--reg", help="UNTS registration number")
    p_tx.add_argument("--page", type=int, help="first page as cited, e.g. 161 for '729 UNTS 161'")
    p_tx.add_argument("--series", default="I", choices=["I", "II"],
                      help="I = registered, II = filed and recorded")
    p_tx.add_argument("--lang", default="en", choices=list(TEXT_LANGS))
    p_tx.add_argument("--force", action="store_true")
    p_tx.set_defaults(func=cmd_text)

    p_vol = sub.add_parser("volume", help="list a UNTS volume's table of contents")
    p_vol.add_argument("volume", type=int)
    p_vol.add_argument("--search", help="case-insensitive substring of the title")
    p_vol.add_argument("--json", action="store_true")
    p_vol.add_argument("--force", action="store_true")
    p_vol.set_defaults(func=cmd_volume)

    p_fe = sub.add_parser("fetch", help="resolve name/ref and grab status+text")
    p_fe.add_argument("query", help="ref like XXIII-1 OR a name like ICCPR")
    p_fe.add_argument("--lang", default="en", choices=list(STATUS_LANGS))
    p_fe.add_argument("--no-text", action="store_true",
                      help="only download the status doc")
    p_fe.add_argument("--force", action="store_true")
    p_fe.set_defaults(func=cmd_fetch)

    p_sh = sub.add_parser("show", help="print a cached extracted-text file")
    p_sh.add_argument("ref", nargs="?")
    p_sh.add_argument("--kind", default="status", choices=["status", "text"])
    p_sh.add_argument("--lang", default="en")
    p_sh.add_argument("--vol", type=int)
    p_sh.add_argument("--reg")
    p_sh.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except urllib.error.URLError as e:
        raise SystemExit("network error: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
