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
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import calendar
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
# `text --lang`: the six UN languages by code, or any language a volume prints
# a text in, by its English name as the marker gives it ("norwegian"). The
# UN's per-treaty files come in three: English, French, and "Other" for the
# rest, which is cut to the language asked for.
TEXT_LANG_CODES = {"ar": "arabic", "zh": "chinese", "ru": "russian", "es": "spanish"}
TEXT_FILES = {"en": "English", "fr": "French"}

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
    "nato": (34, "541", "North Atlantic Treaty"),
    "north atlantic treaty": (34, "541", "North Atlantic Treaty"),
    "chicago convention": (15, "102", "Convention on International Civil Aviation"),
    "convention on international civil aviation": (15, "102", "Convention on International Civil Aviation"),
    "antarctic treaty": (402, "5778", "The Antarctic Treaty"),
    "outer space treaty": (610, "8843", "Treaty on Principles Governing the Activities of States in the Exploration and Use of Outer Space, including the Moon and Other Celestial Bodies"),
    "statute of the council of europe": (87, "1168", "Statute of the Council of Europe"),
    "council of europe statute": (87, "1168", "Statute of the Council of Europe"),
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
        % (BASE, volume, volume, series, reg_num, TEXT_FILES.get(lang, "Other"))
    )


def text_lang(raw: str) -> str:
    """en, fr, or a language name ("arabic") from a --lang value."""
    lang = " ".join(str(raw).split()).lower()
    lang = {"english": "en", "french": "fr"}.get(lang, TEXT_LANG_CODES.get(lang, lang))
    if lang == "other":
        raise SystemExit("--lang other is gone: give the language (ar, zh, ru, es, or a "
                         "name such as norwegian), or --full for every language")
    if not re.fullmatch(r"[a-z][a-z\- ]{1,30}", lang):
        raise SystemExit("--lang takes en, fr, ar, zh, ru, es or a language name "
                         "(e.g. norwegian), not %r" % raw)
    return lang


def lang_slug(lang: str) -> str:
    """The language as file names give it: en, fr, ar, zh, ru, es, norwegian."""
    return {v: k for k, v in TEXT_LANG_CODES.items()}.get(lang, lang.replace(" ", "-"))


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
    # A rebuild must never shrink the index: a chapter whose page fails (or
    # suddenly lists nothing) keeps its entries from the previous index, and
    # the index keeps the previous date so the next miss tries again.
    previous = _read_json(INDEX_PATH) if _has_content(INDEX_PATH) else {"treaties": []}
    old_by_chapter = {}
    for e in previous.get("treaties", []):
        old_by_chapter.setdefault(e.get("chapter_int"), []).append(e)
    index = []
    chapters_seen = []
    kept_old = []
    for ch in chapter_range:
        chapter_entries = []
        failed = False
        # Chapter XI is split into sub-chapters A-E, each on its own page
        # (subid=A, B, ...). Other chapters return the same list for every
        # subid, so we only continue past A when the refs carry a letter.
        for subid in "ABCDEFGH":
            url = url_chapter_index(ch, subid)
            try:
                page_html = http_get(url)
            except Exception as e:
                print("  chapter %d%s: failed (%s)" % (ch, subid if subid != "A" else "", e),
                      file=sys.stderr)
                failed = True
                break
            entries = parse_chapter_index(page_html, ch)
            time.sleep(polite_delay)
            if not entries:
                break
            chapter_entries.extend(entries)
            if not entries[0].subchapter:
                break
        old = old_by_chapter.get(ch, [])
        if old and (failed or not chapter_entries):
            print("  chapter %2d: kept %d treaties from the previous index (%s)"
                  % (ch, len(old), index_date(previous)), file=sys.stderr)
            chapters_seen.append(ch)
            index.extend(old)
            kept_old.append(ch)
            continue
        if not chapter_entries:
            continue
        chapters_seen.append(ch)
        index.extend(asdict(e) for e in chapter_entries)
        print("  chapter %2d: %d treaties" % (ch, len(chapter_entries)), file=sys.stderr)
    if not index or (previous.get("treaties") and len(kept_old) == len(chapters_seen)):
        raise urllib.error.URLError("no chapter page could be fetched; the index is unchanged")
    payload = {
        "fetched_utc": (previous.get("fetched_utc") if kept_old else None)
        or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://treaties.un.org/Pages/Treaties.aspx",
        "chapters": chapters_seen,
        "treaties": index,
    }
    if kept_old:
        payload["stale_chapters"] = kept_old
        print("COVERAGE WARNING: chapters %s could not be refreshed and are as of %s; "
              "the index keeps that date, so the next miss tries again."
              % (", ".join(str(c) for c in kept_old), index_date(previous)), file=sys.stderr)
    _write_json(INDEX_PATH, payload)
    return payload


def load_index():
    _seed_index_if_needed()
    if not _has_content(INDEX_PATH):
        raise SystemExit(
            "no cached index - run `untc.py index` first to build it."
        )
    return _read_json(INDEX_PATH)


# A title search that finds nothing rebuilds an index older than this before
# answering NO MATCH: a treaty deposited since the index was made would
# otherwise be reported as "not deposited with the Secretary-General".
INDEX_MAX_AGE_DAYS = 7


def index_date(payload) -> str:
    return (payload.get("fetched_utc") or "")[:10] or "an unknown date"


def index_age_days(payload) -> float:
    try:
        t = calendar.timegm(time.strptime(payload["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ"))
    except (KeyError, ValueError, TypeError):
        return float("inf")
    return (time.time() - t) / 86400


def concluded_after_index(row, payload, margin_days=30) -> bool:
    """True if a UNTS hit was concluded after the MTDSG index was built
    (less a margin). Only such a treaty can be missing from the index while
    being deposited with the Secretary-General; anything older that is
    SG-deposited is in it."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})$", (row.get("concluded") or "").strip())
    built = payload.get("fetched_utc")
    if not m or not built:
        return True          # unknown dates: cannot rule it out
    try:
        concluded = calendar.timegm((int(m.group(3)), int(m.group(2)), int(m.group(1)), 0, 0, 0))
        built_t = calendar.timegm(time.strptime(built, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        return True
    return concluded >= built_t - margin_days * 86400


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
# UNTS Online: live title search over every registered treaty
# ---------------------------------------------------------------------------
# The MTDSG index covers only the ~670 treaties deposited with the
# Secretary-General. Everything else registered with the UN (bilaterals,
# treaties with other depositaries: tens of thousands) is reached through
# UNTS Online's title search, an ASP.NET form: GET it once for its hidden
# state, then post the title. The result rows carry the full title in a
# `title` attribute and an object id for showDetails.aspx, which gives the
# UNTS volume and page (and so `text --vol/--page`). Treaties are registered
# only once in force, so a treaty not yet in force is in MTDSG but not here.

UNTS_SEARCH_URL = BASE + "/Pages/UNTSOnline.aspx?id=2&clang=_en"
UNTS_DETAILS_URL = BASE + "/Pages/showDetails.aspx?objid=%s&clang=_en"
_UNTS_P = "ctl00$ctl00$ContentPlaceHolder1$ContentPlaceHolderInnerPage$"
UNTS_TITLE_MAX = 100          # the form's maxlength
UNTS_MODES = {"phrase": "cnd3", "all": "cnd2", "any": "cnd1"}
_unts_state = {"opener": None, "form": None}


def _unts_opener():
    if _unts_state["opener"] is None:
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        op.addheaders = [("User-Agent", USER_AGENT)]
        _unts_state["opener"] = op
    return _unts_state["opener"]


def _hidden_fields(page_html):
    out = {}
    for m in re.finditer(r'<input[^>]+type="hidden"[^>]*>', page_html):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[html.unescape(n.group(1))] = html.unescape(v.group(1)) if v else ""
    return out


def unts_query_text(title):
    """A title cut to the form's 100 characters at a word boundary, without
    a trailing parenthetical (MTDSG adds e.g. '(deposited in the archives
    of ...)', which UNTS titles do not have)."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) > UNTS_TITLE_MAX:
        t = t[:UNTS_TITLE_MAX].rsplit(" ", 1)[0]
    return t


def unts_search(title, *, mode="phrase", timeout=120):
    """One UNTS Online title search. Returns (record_count_text, rows) with
    rows as {reg, title, objid, concluded, eif, type}; at most 500 rows
    (the site's largest page)."""
    op = _unts_opener()
    for attempt in range(2):
        if _unts_state["form"] is None:
            _unts_state["form"] = op.open(UNTS_SEARCH_URL, timeout=60).read().decode("utf-8", "replace")
        data = _hidden_fields(_unts_state["form"])
        data.update({_UNTS_P + "txtTitle": unts_query_text(title), _UNTS_P + "Adv_srch": UNTS_MODES[mode],
                     _UNTS_P + "btnSubmit": "Search", _UNTS_P + "drpPageSize": "500"})
        req = urllib.request.Request(UNTS_SEARCH_URL, data=urllib.parse.urlencode(data).encode())
        try:
            page = op.open(req, timeout=timeout).read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError:
            if attempt:
                raise
            _unts_state["form"] = None   # stale form state: fetch it again once
    count = re.search(r"Record Count\s*:\s*([\d,+]+)", page)
    return (count.group(1) if count else "0"), parse_unts_rows(page)


def parse_unts_rows(page):
    """Result rows from a UNTS Online page. The cell attributes vary between
    responses (style="width:20%;" or width="20%"), so rows are read by cell
    position: reg | title (full text in the title attribute) | details link |
    concluded | in force | type | hidden cells."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        if "showDetails.aspx?objid=" not in tr:
            continue
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if len(cells) < 6:
            continue
        title_attr = re.search(r'title="([^"]*)"', cells[1][0])
        objid = re.search(r"objid=([0-9a-f]+)", tr)
        text = lambda i: html.unescape(re.sub(r"<[^>]+>", "", cells[i][1])).strip()
        rows.append({"reg": text(0),
                     "title": html.unescape(title_attr.group(1)).strip() if title_attr else text(1),
                     "objid": objid.group(1) if objid else "",
                     "concluded": text(3), "eif": text(4), "type": text(5)})
    return rows


def _title_key(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# MTDSG titles sometimes carry the circumstances of adoption, which UNTS
# titles leave out.
_TRAILING_CLAUSE = re.compile(r"\s+(?:adopted|done|signed|concluded|opened for signature)\b.*$", re.I)


def unts_find(query, *, limit=10):
    """Phrase search first, then 'all these words' if the phrase finds
    nothing (punctuation and spacing differ between sources: 'Articles 23,27'
    vs '23, 27'), then the phrase without a trailing 'adopted …' / 'done at …'
    clause (MTDSG: 'Amendment to the Montreal Protocol … adopted by the Ninth
    Meeting of the Parties'; UNTS: the title alone). Exact title matches
    first, then titles starting with the query, then the site's order.
    Tested against all 670 MTDSG titles (2026-10-21, tests/untc/
    live_unts_coverage.py): 667 found with the exact title first (or, for UN
    vehicle regulations, as a related record under the 1958 Agreement); the
    3 misses are not registered (not in force) or annexes registered under
    their parent convention.
    Returns (mode, record_count_text, rows)."""
    mode = "phrase"
    count, rows = unts_search(query, mode=mode)
    if not rows:
        words = " ".join(w for w in _title_key(unts_query_text(query)).split() if len(w) > 3)
        if words:
            mode = "all"
            count, rows = unts_search(words, mode=mode)
    if not rows:
        short = _TRAILING_CLAUSE.sub("", unts_query_text(query)).strip()
        if short and short != unts_query_text(query):
            mode = "phrase-short"
            query = short
            count, rows = unts_search(short, mode="phrase")
    key = _title_key(unts_query_text(query))

    def rank(r):
        t = _title_key(r["title"])
        return (0 if t == key else 1 if t.startswith(key) else 2)
    rows = sorted(rows, key=rank)
    return mode, count, rows[:limit]


def _details_field(text, label, nxt):
    m = re.search(re.escape(label) + r"\s*\|\s*(.*?)\s*\|\s*" + re.escape(nxt), text)
    return m.group(1).strip(" |") if m else None


PARTICIPANTS_CAVEAT = (
    "These are the actions registered with the UN Secretariat (UNTS Annex A), not a "
    "depositary's status list. For a treaty whose depositary is not the UN Secretary-General, "
    "an action reaches this list only if the depositary or a party registers it - often years "
    "late, sometimes never - so the list can be incomplete or out of date, and it holds no "
    "reservations or declarations. Tell the user so, and point to the depositary's own record "
    "for anything that matters. For a treaty deposited with the Secretary-General, use the "
    "MTDSG status document (`status <ref>`) instead.")


def _record_cells(page):
    """{label: (texts, hrefs)} from the record's <th>label</th><td>value</td>
    rows: the pieces of text in the cell, and its links."""
    out = {}
    for th, td in re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", page, re.S):
        label = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", th)).split())
        if not label or label in out:
            continue
        texts = [" ".join(html.unescape(x).split()) for x in re.split(r"<[^>]+>", td)]
        hrefs = [html.unescape(h) for h in re.findall(r'href="([^"#][^"]*)"', td)
                 if not h.startswith(("javascript", "mailto"))]
        out[label] = ([t for t in texts if t], [h if h.startswith("http") else BASE + h for h in hrefs])
    return out


def _participants(page):
    """Rows of the record's actions table: participant, action, date of
    notification/deposit, date of effect."""
    i = page.find('id="dgActions"')
    if i < 0:
        return []
    table = page[i:page.find("</table>", i)]
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 4:
            rows.append({"participant": cells[0], "action": cells[1],
                         "date": cells[2] or None, "effect": cells[3] or None})
    return rows


def unts_details(objid, *, participants=False):
    """The UNTS record behind a search hit: registration number, title,
    conclusion, entry into force, depositary, authentic texts, publication
    format, UNTS volume and page, and the text PDFs. The participants table
    (megabytes for a big multilateral) only with participants=True."""
    if not re.fullmatch(r"[0-9a-f]{16}", objid or ""):
        raise SystemExit("unts-details needs the 16-character object id a search hit shows (objid)")
    url = UNTS_DETAILS_URL % objid
    page = _unts_opener().open(url, timeout=120).read().decode("utf-8", "replace")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "|", body))
    text = re.sub(r"\s*\|\s*(\|\s*)+", " | ", text)
    i = text.find("Registration Number")
    text = text[i:] if i >= 0 else text
    vol = _details_field(text, "UNTS Volume Number", "Publication format") or ""
    vm = re.match(r"(\d+)\s*\(p\.\s*(\d+)\)", vol)
    pdfs = sorted(set(m for m in re.findall(r'href="([^"]+\.pdf)"', page)))
    out = {
        "objid": objid,
        "registration_number": _details_field(text, "Registration Number", "Title"),
        "title": _details_field(text, "Title", "Participant(s)"),
        "conclusion": ", ".join(x.strip() for x in (_details_field(text, "Places/dates of conclusion", "EIF information")
                                                    or "").replace("Place | Date |", "").split("|") if x.strip()) or None,
        "entry_into_force": _details_field(text, "EIF information", "Authentic texts"),
        "depositary": _details_field(text, "Depositary", "Registration Date"),
        "registration_date": _details_field(text, "Registration Date", "Subject terms"),
        "agreement_type": _details_field(text, "Agreement type", "UNTS Volume Number"),
        "unts_volume": int(vm.group(1)) if vm else None,
        "unts_page": int(vm.group(2)) if vm else None,
        "unts_volume_raw": vol or None,
        "text_pdfs": [p if p.startswith("http") else BASE + p for p in pdfs],
        "details_url": url,
    }
    if out["unts_volume"] and out["unts_page"]:
        out["text_command"] = "untc.py text --vol %d --page %d" % (out["unts_volume"], out["unts_page"])
    cells = _record_cells(page)
    # a nested table, one language per cell: read from the flattened text
    out["authentic_texts"] = [x.strip() for x in (_details_field(text, "Authentic texts", "Attachments")
                                                  or "").split("|") if x.strip()] or None
    out["publication_format"] = " ".join(cells.get("Publication format", ([], []))[0]) or None
    for key, label in (("certificate_of_registration", "Certificate Of Registration"),
                       ("text_documents", "Text document(s)"), ("maps", "Map(s)"),
                       ("corrigenda", "Corrigendum/Addendum/Note"), ("attachments", "Attachments")):
        hrefs = cells.get(label, ([], []))[1]
        if key == "attachments":
            out[key] = "; ".join(cells.get(label, ([], []))[0]) or None
            if hrefs:
                out["attachment_pdfs"] = hrefs
        else:
            out[key] = hrefs
    table = _participants(page)
    out["participants_count"] = len(table)
    if participants:
        out["participants"] = table
        out["participants_caveat"] = PARTICIPANTS_CAVEAT
    out["mtdsg"] = "secretary-general of the united nations" in (out["depositary"] or "").lower()
    if out["mtdsg"]:
        out["note"] = ("Deposited with the UN Secretary-General, so it has an MTDSG status document "
                       "(parties, reservations): find its MTDSG ref with `untc.py lookup \"<title>\"` "
                       "(which rebuilds an old index if needed) and run `status <ref>`.")
    return out


UNTS_ADVANCED_URL = BASE + "/Pages/AdvanceSearch.aspx?tab=UNTS&clang=_en"


def _unts_find_reg_once(reg, timeout):
    # The advanced search is an ASP.NET form: pick "Treaty", then the
    # "Registration Number" attribute (a from/to range), add it to the
    # criteria, search. Four postbacks on one session; a session reused for
    # a second lookup was reset by the server (2026-11-02), so each lookup
    # gets its own.
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", USER_AGENT)]

    def post(page, fields):
        data = _hidden_fields(page)
        data.update(fields)
        req = urllib.request.Request(UNTS_ADVANCED_URL, data=urllib.parse.urlencode(data).encode())
        return op.open(req, timeout=timeout).read().decode("utf-8", "replace")

    obj, attr = _UNTS_P + "drpSearchObj", _UNTS_P + "drpAttribute"
    page = op.open(UNTS_ADVANCED_URL, timeout=timeout).read().decode("utf-8", "replace")
    page = post(page, {"__EVENTTARGET": obj, obj: "ts_treaty"})
    page = post(page, {"__EVENTTARGET": attr, obj: "ts_treaty", attr: "registration_number"})
    page = post(page, {obj: "ts_treaty", attr: "registration_number", _UNTS_P + "txtFromNum": reg,
                       _UNTS_P + "txtToNum": reg, _UNTS_P + "btnAdd": "Add to Search Criteria"})
    page = post(page, {obj: "ts_treaty", _UNTS_P + "btnSubmit": "Search"})
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        m = re.search(r"showDetails\.aspx\?objid=([0-9a-f]{16})", tr)
        if not m:
            continue
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if len(cells) < 6:
            continue
        text = lambda i: " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cells[i][1])).split())
        full = re.search(r'title="([^"]*)"', cells[0][0] + cells[0][1])
        rows.append({"reg": text(1), "title": html.unescape(full.group(1)).strip() if full else text(0),
                     "objid": m.group(1), "registered": text(2), "type": text(3),
                     "concluded": text(4), "volume": text(5)})
    return rows


def unts_find_reg(reg, *, timeout=120):
    """UNTS records under registration number `reg`: the treaty itself
    (I-44910) and the later actions recorded against it (A-44910: protocols,
    amendments, rectifications). Rows {reg, title, objid, registered, type,
    concluded, volume}."""
    last = None
    for attempt in range(3):
        try:
            return _unts_find_reg_once(str(reg), timeout)
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise last  # type: ignore[misc]


def unts_record(volume, reg, series="I", out_dir: Optional[Path] = None, *, force=False) -> dict:
    """The treaty's UNTS record (unts_details), found by registration number
    and cached as record.json for 7 days. Never raises: {"error": ...} when
    the site cannot be reached or has no record, so the text still comes."""
    cache = out_dir / "record.json" if out_dir else None
    if cache and _has_content(cache) and not force:
        rec = _read_json(cache)
        if time.time() - rec.get("_fetched", 0) < 7 * 86400:
            return rec
    try:
        rows = unts_find_reg(reg)
        want = "%s-%s" % (series, reg)
        own = [r for r in rows if r["reg"] == want]
        if volume and len(own) > 1:
            own = [r for r in own if r["volume"] == str(volume)] or own
        if not own:
            return {"error": "no UNTS record registered as %s" % want}
        rec = unts_details(own[0]["objid"])
        rec["related"] = [{k: r[k] for k in ("reg", "title", "objid", "registered")}
                          for r in rows if r["objid"] != own[0]["objid"]]
    except Exception as e:  # network, markup change: the text route goes on without it
        return {"error": "UNTS record not reachable (%s: %s)" % (type(e).__name__, e)}
    rec["_fetched"] = time.time()
    if cache:
        _write_json(cache, rec)
    return rec


def print_unts_rows(rows):
    for r in rows:
        print("  %-10s %s" % (r["reg"], r["title"]))
        print("             -- concluded %s, in force %s, %s; details: untc.py unts-details %s"
              % (r["concluded"] or "?", r["eif"] or "?", r["type"] or "?", r["objid"]))


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


def short_pages(heights: list, ratio: float = 0.85) -> list:
    """Indices of pages well below the file's median height. Some per-treaty
    PDFs carry a page cropped short: in volume-34-I-541 (NATO) printed p. 246
    is 491 pt tall against 657 for the rest, and the second paragraph of
    Article 5 is simply missing from it. The full volume PDF has the page."""
    if len(heights) < 3:
        return []
    median = sorted(heights)[len(heights) // 2]
    return [i for i, h in enumerate(heights) if h < ratio * median]


def _short_page_report(pdf_path: Path) -> Optional[list]:
    """[{pdf_page, printed_page, height, median}] for short pages, or None."""
    PdfReader = _pypdf_reader()
    if PdfReader is None:
        return None
    try:
        reader = PdfReader(str(pdf_path))
        heights = [float(p.mediabox.height) for p in reader.pages]
    except Exception:
        return None
    idx = short_pages(heights)
    if not idx:
        return None
    median = sorted(heights)[len(heights) // 2]
    out = []
    for i in idx:
        text = reader.pages[i].extract_text() or ""
        out.append({"pdf_page": i + 1, "printed_page": printed_page_of(text),
                    "height": round(heights[i]), "median": round(median)})
    return out


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


# The UN regenerates MTDSG status PDFs as depositary actions come in, so a
# cached one is re-downloaded once it is older than this.
STATUS_MAX_AGE_DAYS = 7


def pdf_document_date(pdf: Path) -> Optional[str]:
    """The date the PDF says it was generated (/ModDate, else
    /CreationDate) as YYYY-MM-DD, read from the raw file so no PDF library
    is needed. MTDSG status PDFs carry no "status as at" line; this is
    the date their participant list reflects."""
    try:
        raw = pdf.read_bytes()
    except OSError:
        return None
    for key in (rb"/ModDate", rb"/CreationDate"):
        m = re.search(key + rb"\s*\(D:(\d{4})(\d{2})(\d{2})", raw)
        if m:
            return "-".join(g.decode() for g in m.groups())
    return None


def fetch_status(ref, *, lang="en", force=False):
    _check_status_lang(lang)
    out_dir = treaty_dir(ref)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / ("status.%s.pdf" % lang)
    url = url_mtdsg_status(ref, lang)
    if not force and _has_content(pdf):
        age_days = (time.time() - pdf.stat().st_mtime) / 86400
        if age_days > STATUS_MAX_AGE_DAYS:
            print("cached status document is %d days old - downloading the current one"
                  % age_days, file=sys.stderr)
            force = True
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
    # When the cached PDF was downloaded (not when this command ran), and
    # the date the UN generated it: the date to give for "status as at".
    meta["fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pdf.stat().st_mtime))
    meta["status_date"] = pdf_document_date(pdf)
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
    # The page column is the last thing OCR gets right: a dropped column of
    # dot leaders leaves the date at the end of the entry, so "signed ... on
    # 6 March 1946" is read as page 1946. Anything past the volume's last
    # folio is noise, not a page.
    cap = max_printed_page(pages)
    if cap:
        for e in entries:
            if e["page"] is not None and e["page"] > cap:
                e["page"] = None
    return entries


# A half-title page is a short line holding nothing but the registration
# number. OCR mangles the "No." on it often enough to matter - volume 999
# renders the ICCPR's as "lo. 14668" - so match any brief prefix, not the
# literal word.
_HALF_TITLE_RE = re.compile(r"^\s*[A-Za-z][A-Za-z0-9]{0,2}\s*[.,]?\s*(\d{3,6})\s*$")


def _first_line(page_text: str) -> str:
    return page_text.lstrip().split("\n", 1)[0].strip()


def _page_starts_with_reg(page_text: str, reg: str) -> bool:
    head = page_text.lstrip()[:200]
    if re.search(r"(^|\n)\s*No\.\s*%s\b" % re.escape(reg), head):
        return True
    m = _HALF_TITLE_RE.match(_first_line(page_text))
    return m is not None and m.group(1) == reg


_DOT_LEADER_RE = re.compile(r"\.{3,}|(?:\.\s){3,}")
_ANY_REG_RE = re.compile(r"(?:^|\n)\s*Nos?\.?\s*(\d{3,6})\b")


def _is_contents_page(page_text: str) -> bool:
    """A contents or index page lists several "No. NNN" entries with dot
    leaders; the opening page of a treaty does neither. The running header
    and the section title on a contents page can push a "No. <reg>" line
    into the first 200 characters, so _page_starts_with_reg alone matches
    them - volume 15's contents for section II matched No. 102 (the Chicago
    Convention) 300 pages before the text itself."""
    if re.search(r"TABLE\s+(?:OF\s+CONTENTS|DES\s+MATI)", page_text, re.I):
        return True
    if not _DOT_LEADER_RE.search(page_text):
        return False
    return len(set(_ANY_REG_RE.findall(page_text))) >= 2


def _opens_with_reg(page_text: str, reg: str) -> bool:
    """"No. <reg>" is the whole first line - the treaty's half-title page."""
    first = _first_line(page_text)
    if re.match(r"No\.?\s*%s\b" % re.escape(reg), first):
        return True
    m = _HALF_TITLE_RE.match(first)
    return m is not None and m.group(1) == reg


def locate_in_volume(pages: list, reg: str, toc_end_hint: int = 0):
    """Return (start_idx, end_idx) of the pages holding registration `reg`.
    The treaty starts on the first page (after the contents) whose text opens
    with "No. <reg>" and ends where the next "No. <other>" page or ANNEX A
    begins."""
    cands = [i for i in range(toc_end_hint, len(pages))
             if _page_starts_with_reg(pages[i], reg)
             and not _is_contents_page(pages[i])]
    if not cands:
        return None
    start = cands[0]
    for i in cands:  # prefer the half-title over a body page's running header
        if _opens_with_reg(pages[i], reg):
            start = i
            break
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


_RUNNING_HEAD_RE = re.compile(
    r"United\s+Nations|Nations\s+Unies|Treaty\s+Series|Recuei\w*\s+des\s+Trait", re.I)


def printed_page_of(page_text: str) -> Optional[int]:
    """The printed folio from a UNTS running header, or None. Verso headers
    read "296 United Nations - Treaty Series 1948", recto headers
    "1948 Nations Unies - Recueil des Traites 297", so the folio is whichever
    of the two numbers is not the year. Volumes never run to 1900 pages, so
    a number in the year range is always the year. Newer volumes head every
    page "Volume 2515, I-44910" (A-... for Annex A; vol. 3200 has a
    non-breaking hyphen) and put the folio on the next line that is not
    blank. The UN's files for volumes not yet out head them "I-56487" alone,
    with the file's own page numbers."""
    lines = [l.strip() for l in page_text.split("\n") if l.strip()][:2]
    head = lines[0] if lines else ""
    if re.match(r"(?:Volume\s+\d+\s*,\s*)?(?:[IVX]+|A)\s*[^\w\s,]\s*\d+$", head):
        m = re.match(r"(\d{1,4})$", lines[1]) if len(lines) > 1 else None
        return int(m.group(1)) if m else None
    if not head or not _RUNNING_HEAD_RE.search(head):
        return None
    cands = []
    lead = re.match(r"(\d{1,4})\b", head)
    if lead:
        cands.append(int(lead.group(1)))
    trail = re.search(r"\b(\d{1,4})\s*$", head)
    if trail:
        cands.append(int(trail.group(1)))
    for c in cands:
        if not 1900 <= c <= 2100:
            return c
    return None


def max_printed_page(pages: list) -> Optional[int]:
    """The highest folio printed in the volume - anything above it in a
    parsed contents entry is OCR noise (a year, usually)."""
    seen = [printed_page_of(p) for p in pages]
    seen = [n for n in seen if n is not None]
    return max(seen) if seen else None


def index_for_printed_page(pages: list, page: int) -> Optional[int]:
    """PDF index of the printed page `page`, from the running headers. Body
    pages map 1:1 onto folios, so the nearest header fixes the offset for the
    pages that carry none (half-titles, blank versos)."""
    best = None
    for i, p in enumerate(pages):
        n = printed_page_of(p)
        if n is None:
            continue
        if n == page:
            return i
        d = abs(n - page)
        if best is None or d < best[0]:
            best = (d, i - n)
    if best is None:
        return None
    idx = page + best[1]
    return idx if 0 <= idx < len(pages) else None


def _reg_at_index(pages: list, idx: int, back: int = 200) -> Optional[str]:
    """The registration number whose text covers PDF page `idx`: the nearest
    "No. NNN" heading at or before it, skipping contents pages."""
    for i in range(idx, max(-1, idx - back), -1):
        if _is_contents_page(pages[i]):
            continue
        m = _HALF_TITLE_RE.match(_first_line(pages[i]))
        if m:
            return m.group(1)
        m = _ANY_REG_RE.search(pages[i].lstrip()[:200])
        if m:
            return m.group(1)
    return None


def resolve_page_to_reg(volume: int, page: int, *, force=False) -> Optional[dict]:
    """Map a printed page number (as in a citation '729 UNTS 161') to the
    registration number printed there.

    The volume's own running headers are authoritative; the parsed contents
    are only a cross-check, because the page column is regularly lost to OCR
    in the early volumes (volume 15 yields "p. ?" for No. 102 and reads the
    year 1946 as a page for No. 227, which made a lookup of 15 UNTS 295 -
    the Chicago Convention - resolve to No. 243 instead)."""
    return _resolve_page(volume_pages(volume, force=force),
                         volume_toc(volume, force=force), page)


def _resolve_page(pages: list, toc: list, page: int) -> Optional[dict]:
    """The logic of resolve_page_to_reg, with the volume already in hand."""
    toc_hit = None
    for e in toc:
        if e["annex"] or e["page"] is None:
            continue
        if e["page"] <= page and (toc_hit is None or e["page"] > toc_hit["page"]):
            toc_hit = e

    idx = index_for_printed_page(pages, page)
    reg = _reg_at_index(pages, idx) if idx is not None else None
    if reg is None:
        if toc_hit is None:
            return None
        hit = dict(toc_hit, via="contents")
        hit["warning"] = ("resolved from the parsed contents only; no running "
                          "header for p. %d in the volume PDF" % page)
        return hit

    hit = {"reg": reg, "page": page, "annex": "", "via": "running-head",
           "pdf_page": idx + 1, "title": ""}
    for e in toc:
        if e["reg"] == reg:
            hit["title"] = e["title"]
            break
    if toc_hit is not None and toc_hit["reg"] != reg:
        hit["warning"] = ("the parsed contents put p. %d under No. %s (%s); "
                          "the running headers put it under No. %s"
                          % (page, toc_hit["reg"], toc_hit["title"][:60], reg))
    return hit


# ---------------------------------------------------------------------------
# The parts of a registration
# ---------------------------------------------------------------------------
#
# A registration holds much more than one treaty text: the registration note,
# the parties and their reservations as at registration, the text in every
# authentic language, other instruments registered under the same number, the
# signatures, and the Secretariat's translations where English or French is
# not authentic. The CRPD (vol. 2515) runs to 190 pages, 27 of them English.
# The per-treaty files are no cleaner: the ICCPR's "English" file (vol. 999)
# carries 26 pages of signatures and 20 of reservations per instrument.
# label_pages() tags each page; select_pages() keeps the registration note
# and the text in the language asked for.

# "[ENGLISH TEXT - TEXTE ANGLAIS]", "[ ARABIC TEXT - TEXTE ARABE ]", as OCR
# renders them "[BYELORUSSIAN XEXX - TEXXE BIELORUSSE]", and from about
# vol. 3100 "[ TEXT IN ENGLISH - TEXTE EN ANGLAIS ]".
_LANG_MARKER_RE = re.compile(
    r"\[\s*(?:TEXT\s+IN\s+([A-Z][A-Za-z\- ]{2,30}?)\s*[^\w\s\]]{1,3}\s*TEXTE\s+EN\s+[^\]\n]{2,40}"
    r"|(?!TEXT\s|TRA[DN])([A-Z][A-Za-z\- ]{2,30}?)\s+[A-Z]{3,5}(?:\s*[^\w\s\]]{1,3}\s*|\s+)[A-Z]{4,6}"
    r"\s+[^\]\n]{2,40})\]")
# Older volumes also print the marker bare, OCR'd in mixed case, at the head
# of the first page: "No. 3237. JAPANESE TEXT - TEXTE JAPONAIS",
# "No. 5757. KoREAN TEXT - TExTE CORAE,".
_BARE_MARKER_RE = re.compile(
    r"^\s*(?:No\.?\s*\d+\.\s*)?([A-Za-z][A-Za-z\- ]{2,30}?)\s+TEXT\s*[^\w\s]{1,3}\s*TEXTE\s+\S+",
    re.I)
# Treaties registered but not printed: "Not published herein in accordance
# with article 12(2) of the General Assembly regulations ...", or in older
# volumes printed as a title only, "Publication effected in accordance with
# article 12(2) ...".
_NOT_PUBLISHED_RE = re.compile(
    r"Not\s+published\s+(?:herein|in\s+print)|Publication\s+effected\s+in\s+accordance", re.I)
# "[TRANSLATION - TRADUCTION]", "[TRADUCTION - TRANSLATION]", "[TRANSLATION]",
# "[ TRANSLATION IN FRENCH - TRADUCTION EN FRANCAIS ]"
_TRANSLATION_RE = re.compile(
    r"\[\s*(TRA[A-Z]{5,9})(?:\s+IN\s+([A-Z]+))?\s*[*'`]?\s*"
    r"(?:(?:[^\w\s\]]{1,3}\s*)?TRA[A-Z]{5,9}(?:\s+EN\s+[^\]\n]{2,20}?)?\s*[*'`]?\s*)?\]")
_RTL_LANGS = {"arabic", "hebrew", "persian", "farsi", "urdu"}
_HEAD_LINE_RE = re.compile(
    r"^\s*(?:(?:Vol(?:ume|\.)\s*\d+\s*,\s*)?(?:[IVX1l]+|A)\s*[^\w\s,]\s*\d+|\d{1,4}"
    r"|.*(?:Treaty\s*\.?\s*Series|Recue\w*\s+des\s+Trait).*)\s*$", re.I)
_PARTIES_RE = re.compile(
    r"^\s*Participants?\s+(?:Ratification|Accession|Signature|Acceptance|Approval"
    r"|Succession|Definitive|Consent)", re.I | re.M)
_RESERVATIONS_RE = re.compile(
    r"DECLARATIONS?\s+AND\s+RESERVA|RESERVATIONS?\s+AND\s+DECLARA"
    r"|D.CLARATIONS?\s+ET\s+R.SERVES"
    r"|\b(?:reservations?|(?:interpretative\s+)?declarations?|objections?)"
    r"\s+made\s+(?:up)?on\b"
    r"|\bR.serves?\s+(?:et\s+d.clarations?\s+)?faites?\s+lors\b", re.I)
_REGISTRATION_RE = re.compile(
    r"^\s*(?:No|N[o0°])\.?\s*\d{3,6}\s*$|(?:Authentic|Official)\s+texts?|\bRegistered\b"
    r"|Registration\s+with|Enregistr|Came\s+into\s+force|Entry\s+into\s+force", re.I | re.M)
_SIGNATORIES_RE = re.compile(r"LIST\s+OF\s+SIGNATORIES|LISTE\s+DES\s+SIGNATAIRES", re.I)
# Facsimile signature pages: "FOR AFGHANISTAN:" over "POUR L'AFGHANISTAN:".
# Upper case only, so that "For the Government of ...:" closing a text
# does not count.
_FOR_RE = re.compile(r"^\s*F[O0o][RBHUru]\s+(?:THE\s+)?[A-Z][^\n]*:", re.M)
_POUR_RE = re.compile(r"^\s*P[O0o][UuC][RrHMm]\s+[A-Z][^\n]*:", re.M)
_ARTICLE_LINE_RE = re.compile(
    r"^\s*(?:Article|Art[ií]cul[oa]|PREAMBLE|PR.AMBULE)\b", re.I | re.M)
_STOPWORDS = {
    "en": set("the of and shall which with this be by any its or such".split()),
    "fr": set("le les des et du aux une est sur dans par ses qui".split()),
    "spanish": set("el los las del y por con una sus para".split()),
    # Dutch shares "of" and "be" with English, so it needs its own set to
    # stay out of the English text (vol. 232, No. 3233).
    "dutch": set("het van een voor niet zijn wordt worden deze overeenkomst".split()),
    "german": set("der die das und den dem zu mit nicht wird werden".split()),
}
LANG_NAMES = {"en": "English", "fr": "French", "other": "unidentified-language"}


def lang_name(lang: str) -> str:
    return LANG_NAMES.get(lang) or (lang or "unknown-language").capitalize()


def _body_lines(page_text: str) -> list:
    """The page's lines without the running head, folio and footer line."""
    lines = [l for l in page_text.split("\n") if l.strip()]
    for _ in range(3):
        if lines and _HEAD_LINE_RE.match(lines[0]):
            lines.pop(0)
    for _ in range(2):
        if lines and _HEAD_LINE_RE.match(lines[-1]):
            lines.pop()
    return lines


def _text_lang(text: str, min_chars: int = 150) -> Optional[str]:
    """en, fr, spanish, mixed (English and French side by side), other
    (Cyrillic, CJK, OCR noise, ...), or None for a page with little or no
    text layer - a scan, a blank verso."""
    words = re.findall(r"[^\W\d_]+", text.lower())
    if sum(len(w) for w in words) < min_chars:
        return None
    n = {k: sum(w in s for w in words) for k, s in _STOPWORDS.items()}
    tot = sum(n.values())
    if tot < 8:
        return "other"
    if n["en"] >= 0.7 * tot:
        return "en"
    if n["fr"] >= 0.7 * tot:
        return "fr"
    for lang in ("spanish", "dutch", "german"):
        if n[lang] >= 0.6 * tot:
            return lang
    if n["en"] >= 0.25 * tot and n["fr"] >= 0.25 * tot:
        return "mixed"
    return "other"


def _marker_lang(name: str) -> str:
    name = " ".join(name.split()).lower()
    return {"english": "en", "french": "fr"}.get(name, name)


def _is_signature_page(body: str) -> bool:
    if _SIGNATORIES_RE.search(body):
        return True
    return bool(_FOR_RE.search(body) and _POUR_RE.search(body)
                and not _ARTICLE_LINE_RE.search(body)
                and sum(c.isalpha() for c in body) < 1800)


def label_pages(pages: list, authentic: Optional[set] = None) -> list:
    """One label per page of a registration (pages[0] is its first page):
    a set of (part, lang) pairs. part is registration, parties, reservations,
    signatures, text or translation; lang is en, fr, a language name, or None
    for the parts that are not a text.

    Pages are read in order and a part runs on until the next heading or
    language marker, so a scanned page with no text layer takes the label of
    the page before it. Arabic is bound right to left: its marker sits on the
    last page of its block, and the pages before it are relabelled.

    Older volumes print a Secretariat translation on the pages facing the
    authentic text, with one marker at the start, so an unmarked page is
    told apart by its language: the registration note's authentic languages
    decide, else whether that language has had a translation marker."""
    labels = []
    state = ("registration", None)
    inherited = set()
    authentic = authentic or (authentic_languages(pages[0]) if pages else None)
    translated = set()

    def part_for(lang):
        if authentic and lang in ("en", "fr", "spanish"):
            return "text" if LANG_NAMES.get(lang, lang).lower() in authentic else "translation"
        return "translation" if lang in translated else "text"

    for i, page in enumerate(pages):
        lines = _body_lines(page)
        body = "\n".join(lines)
        head = "\n".join(lines[:3])
        # A per-treaty file need not open with the registration note: the
        # "Other" files start straight into the first language.
        if i == 0 and _REGISTRATION_RE.search(body[:800]):
            labels.append({("registration", None)})
            # The note is one page: what follows unmarked and unreadable is
            # a text (CJK in the OCR'd volumes, a scan in the newer ones).
            state = ("text", "other")
            continue
        if _PARTIES_RE.search(head):
            state = ("parties", None)
        elif _RESERVATIONS_RE.search(head):
            state = ("reservations", None)
        elif _is_signature_page(body):
            state = ("signatures", None)
        else:
            markers = sorted(
                [(m.start(), m.end(), "text", _marker_lang(m.group(1) or m.group(2)))
                 for m in _LANG_MARKER_RE.finditer(body)]
                + [(m.start(), m.end(), "translation",
                    _marker_lang(m.group(2)) if m.group(2)
                    else "en" if m.group(1).startswith("TRANS") else "fr")
                   for m in _TRANSLATION_RE.finditer(body)])
            if not markers:
                pos = 0
                for line in lines[:3]:
                    m = _BARE_MARKER_RE.match(line)
                    if m:
                        markers = [(pos, pos + len(line), "text", _marker_lang(m.group(1)))]
                        break
                    pos += len(line) + 1
            top = markers[0] if markers and not body[:markers[0][0]].strip() else None
            lang = _text_lang(body)
            if state[0] in ("parties", "reservations", "signatures") \
                    and not (top and top[2] == "text"):
                # A reservation quotes its original under a language marker,
                # so only a marker opening the page ends the section - or,
                # in the older volumes, an unmarked page of treaty text.
                if not markers and lang in ("en", "fr", "spanish") \
                        and _ARTICLE_LINE_RE.search(body):
                    state = (part_for(lang), lang)
                elif lang is None:
                    inherited.add(i)
                labels.append({state})
                continue
            if not markers:
                if lang is None:
                    inherited.add(i)
                elif lang == "mixed":
                    labels.append({(part_for("en"), "en"), (part_for("fr"), "fr")})
                    state = (part_for("en"), "en")
                    continue
                elif lang != "other" or state[1] is None:
                    state = (part_for(lang), lang)
                labels.append({state})
                continue
            # Split the page at its markers; each piece has its own label.
            label = set()
            if not top and _text_lang(body[:markers[0][0]], 40) is not None:
                label.add((_block(state), state[1] or (lang if lang in ("en", "fr") else "other")))
            for k, (s, e, part, mlang) in enumerate(markers):
                piece = body[e:markers[k + 1][0] if k + 1 < len(markers) else len(body)]
                plang = _text_lang(piece, 40)
                if part == "translation":
                    mlang = plang if plang in ("en", "fr") else mlang
                    translated.add(mlang)
                state = (part, mlang)
                label.add(state)
                if part == "text" and mlang in _RTL_LANGS and k == 0 and top:
                    j = i - 1
                    while j in inherited:
                        labels[j] = {state}
                        j -= 1
            labels.append(label)
            continue
        labels.append({state})
    _relabel_quoted_reservations(labels)
    return labels


def _relabel_quoted_reservations(labels: list) -> None:
    """A declaration quoted in its original under a marker that opens the
    page, with its heading only in the scan (the TPNW's Cook Islands
    declaration, vol. 3370), reads as a short text block followed by the
    next reservation's heading. Relabel such a block - at most 3 pages,
    straight before a reservations page - but only when the same language
    has a text block later on, so the treaty text itself is never lost."""
    i = 0
    while i < len(labels):
        lab = labels[i]
        if len(lab) != 1 or next(iter(lab))[0] != "text":
            i += 1
            continue
        j = i
        while j + 1 < len(labels) and labels[j + 1] == lab:
            j += 1
        nxt = labels[j + 1] if j + 1 < len(labels) else set()
        later = any(lab <= labels[k] for k in range(j + 2, len(labels)))
        if j - i < 3 and ("reservations", None) in nxt and later:
            for k in range(i, j + 1):
                labels[k] = {("reservations", None)}
        i = j + 1


def _block(state) -> str:
    return state[0] if state[0] in ("text", "translation") else "text"


def authentic_languages(registration_page: str) -> Optional[set]:
    """{"english", "french", ...} from the registration note's "Authentic
    texts:" line, or None when the page has none (most older volumes)."""
    m = re.search(r"(?:Authentic|Official)\s+texts?\s*:\s*(.+?)(?:\.|Registr|Enregistr|$)",
                  registration_page, re.I | re.S)
    if not m:
        return None
    return {w.lower() for w in re.findall(r"[A-Za-z]+", m.group(1))
            if w.lower() not in ("and", "the")}


def select_pages(labels: list, lang: str, authentic: Optional[set] = None):
    """Indices of the pages to keep for --lang, or None when the text in that
    language cannot be found.

    The registration note always stays, with the text in that language of
    every instrument registered under the number. Where English or French
    is not authentic, the authentic texts and the Secretariat's translation
    into it; other languages have no translations."""
    def match(l):
        return l == lang

    texts = {l for lab in labels for (p, l) in lab if p == "text"}
    if lang in ("en", "fr"):
        name = LANG_NAMES[lang].lower()
        is_authentic = (name in authentic) if authentic else lang in texts
    else:
        is_authentic = True
    if is_authentic:
        want = lambda p, l: p == "text" and match(l)
    else:
        want = lambda p, l: (p == "text" and l is not None) or (p == "translation" and l == lang)
    keep = [i for i, lab in enumerate(labels) if any(want(p, l) for p, l in lab)]
    if not keep:
        return None
    return sorted(set(keep) | {i for i, lab in enumerate(labels) if ("registration", None) in lab})


def describe_label(label: set) -> str:
    def one(p, l):
        if p == "registration":
            return "registration note"
        if p == "parties":
            return "parties as at registration"
        if p == "reservations":
            return "reservations and declarations"
        if p == "signatures":
            return "signatures"
        name = lang_name(l)
        return "%s %s" % (name, "translation (Secretariat)" if p == "translation" else "text")
    return " + ".join(sorted(one(p, l) for p, l in label))


def _runs(idxs: list) -> list:
    """[[first, last], ...] of consecutive integers."""
    out = []
    for i in idxs:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def _printed_span(pages: list, first: int, last: int) -> Optional[list]:
    """Printed folios of pages[first..last], extrapolated over the pages that
    carry none (half-titles, blank versos)."""
    nums = [(i, printed_page_of(pages[i])) for i in range(first, last + 1)]
    nums = [(i, n) for i, n in nums if n is not None]
    if not nums:
        return None
    return [nums[0][1] - (nums[0][0] - first), nums[-1][1] + (last - nums[-1][0])]


def registration_parts(pages: list, labels: list, keep: Optional[list],
                       offset: int = 0) -> list:
    """The runs of the registration with what each holds, its PDF and
    printed pages (offset = PDF index of pages[0]) and whether it is kept."""
    parts = []
    for i, lab in enumerate(labels):
        desc = describe_label(lab)
        kept = keep is None or i in keep
        if parts and parts[-1]["part"] == desc and parts[-1]["kept"] == kept:
            parts[-1]["_last"] = i
        else:
            parts.append({"part": desc, "kept": kept, "_first": i, "_last": i})
    for p in parts:
        first, last = p.pop("_first"), p.pop("_last")
        p["pdf_pages"] = [offset + first + 1, offset + last + 1]
        p["printed_pages"] = _printed_span(pages, first, last)
    return parts


def write_pdf_pages(src: Path, idxs: list, dest: Path) -> bool:
    """Pages idxs (0-based) of src into dest; False without pypdf."""
    try:
        from pypdf import PdfReader, PdfWriter  # type: ignore
    except ImportError:
        return False
    reader, writer = PdfReader(str(src)), PdfWriter()
    for i in idxs:
        writer.add_page(reader.pages[i])
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    with open(tmp, "wb") as f:
        writer.write(f)
    os.replace(tmp, dest)
    return True


def _cut(pages: list, offset: int, lang: str, full: bool, src_pdf: Path,
         stem: Path, source_label: str, rerun: str, authentic: Optional[set] = None,
         publication: Optional[str] = None) -> dict:
    """Pick the pages of one registration (pages = its pages, offset = the
    PDF index of the first), write <stem>.txt and, when it differs from
    src_pdf, <stem>.cut.pdf. Returns the fields fetch_text reports.
    authentic and publication come from the UNTS record when it was reached;
    without them the registration note is read."""
    authentic = authentic or (authentic_languages(pages[0]) if pages else None)
    labels = label_pages(pages, authentic)
    keep = None
    if not full:
        keep = select_pages(labels, lang, authentic)
    trimmed = keep is not None and len(keep) < len(pages)
    idxs = keep if keep is not None else list(range(len(pages)))
    parts = registration_parts(pages, labels, keep if trimmed else None, offset)
    kept_desc = sorted({p["part"] for p in parts if p["kept"]})
    left_out = [p for p in parts if not p["kept"]]

    if full:
        what = "the whole registration: every language and part"
    else:
        what = ", ".join(kept_desc)
    head = ["[%s - %s; PDF pages %s of %s]" % (
        source_label, what,
        ", ".join("%d-%d" % (a + offset + 1, b + offset + 1) for a, b in _runs(idxs)),
        src_pdf.name)]
    if left_out:
        head.append("[Left out: %s. For these: %s]" % ("; ".join(
            "%s (printed pp. %s)" % (p["part"], "%d-%d" % tuple(p["printed_pages"])
                                     if p["printed_pages"] else "?")
            for p in left_out), rerun))
    out, prev = [], None
    for i in idxs:
        if prev is not None and i != prev + 1:
            out.append("[... PDF pages %d-%d left out ...]" % (prev + offset + 2, i + offset))
        out.append(pages[i])
        prev = i
    txt = stem.with_name(stem.name + ".txt")
    _write_text(txt, "\n".join(head) + "\n\n" + "\n\f\n".join(out))

    info = {"text_txt": str(txt), "parts": parts, "trimmed": trimmed}
    if publication and "partial" in publication.lower():
        info["partial_publication"] = (
            "the UNTS record says Partial Publication: the Secretariat left parts of this "
            "treaty out of the printed text (often long technical annexes)")
    if (publication and "limited" in publication.lower()) \
            or any(_NOT_PUBLISHED_RE.search(p) for p in pages[:2]):
        info["not_published"] = (
            "the UNTS registers this treaty but does not print its text (article 12(2) "
            "of the General Assembly regulations on registration): the volume holds only "
            "the registration note, at most with the title. The text must come from "
            "another source, such as a party's treaty series")
    elif keep is None and not full and lang not in ("en", "fr"):
        found = sorted({lang_name(l) for lab in labels for p, l in lab if p == "text"})
        raise SystemExit(
            "no %s text in %s; it holds: %s. Give --lang one of those (English and "
            "French as en / fr), or --full for every language"
            % (lang_name(lang), source_label, ", ".join(found) or "no language text"))
    elif keep is None and not full:
        info["warning"] = ("could not find the %s text in the registration, so the whole "
                           "registration was kept (every language and part)"
                           % lang_name(lang))
    if trimmed or offset or len(idxs) != _pdf_page_count(src_pdf):
        cut = stem.with_name(stem.name + ".cut.pdf")
        if write_pdf_pages(src_pdf, [i + offset for i in idxs], cut):
            info["text_pdf"] = str(cut)
    else:
        info["text_pdf"] = str(src_pdf)
    # A page whose text layer is only its running head is a scan.
    scans = [i for i in idxs if i and _text_lang("\n".join(_body_lines(pages[i])), 40) is None
             and not _LANG_MARKER_RE.search(pages[i])]
    scans += [i for i in idxs if i and _LANG_MARKER_RE.search(pages[i])
              and len("".join(_body_lines(pages[i]))) < 120]
    if scans and len(scans) >= max(2, len(idxs) // 4):
        runs = ", ".join("%d-%d" % (a + offset + 1, b + offset + 1) for a, b in _runs(sorted(scans)))
        info["scanned_pages"] = runs
        info["warning"] = ((info.get("warning", "") + "; ") if info.get("warning") else "") + (
            "%d of the %d pages are scans with no text layer (PDF pages %s): the text file "
            "does not hold their text. Read those pages of %s as images instead, and never "
            "fill the gap from memory" % (len(scans), len(idxs), runs,
                                          info.get("text_pdf", src_pdf)))
    return info


def _pdf_page_count(pdf: Path) -> Optional[int]:
    PdfReader = _pypdf_reader()
    if PdfReader is None:
        return None
    try:
        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def fetch_text(ref=None, *, volume=None, reg_num=None, page=None, lang="en",
               force=False, series="I", from_volume=False, full=False):
    lang = text_lang(lang)
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
            raise SystemExit("nothing found at p. %d in volume %d; "
                             "run `untc.py volume %d` to see the contents" % (page, volume, volume))
        reg_num = hit["reg"]
        resolved_from = {"page": page, "entry": hit}
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

    # The UNTS record: authentic languages and publication format without
    # OCR, and the files that exist, so nothing is guessed. Without it (site
    # down, no record) the text still comes, as before.
    record = unts_record(volume, reg_num, series, out_dir, force=force)
    authentic = {a.lower() for a in record.get("authentic_texts") or []} or None
    publication = record.get("publication_format")
    docs = record.get("text_documents")
    if record.get("error"):
        info["record_error"] = record["error"]
    else:
        info["record"] = {k: record.get(k) for k in (
            "details_url", "authentic_texts", "publication_format", "attachments")}
        if record.get("related"):
            info["record"]["related"] = ["%s %s" % (r["reg"], r["title"]) for r in record["related"]]
    part_url = next((d for d in docs or [] if "/Part/" in d and "/No%20Volume/" not in d), None)
    no_volume_url = next((d for d in docs or [] if "/No%20Volume/" in d), None)

    # 1. Per-treaty PDF (exists for most older volumes)
    url = url_unts_text(volume, reg_num, lang, series=series)
    pdf = out_dir / ("text.%s.pdf" % ({"en": "en", "fr": "fr"}.get(lang, "other")))
    if ref is not None:
        cmd = "untc.py text %s" % ref.slug
    else:
        cmd = "untc.py text --vol %d --reg %s" % (volume, reg_num)
    rerun = ("`%s --full` gives the whole registration; `--lang en|fr|ar|zh|ru|es` "
             "or a language name (e.g. `--lang norwegian`) another language version" % cmd)
    try:
        if from_volume or (docs is not None and not any(
                d.endswith("-%s.pdf" % TEXT_FILES.get(lang, "Other")) for d in docs)):
            raise DocumentNotFound(url)   # the record lists no such file
        download_pdf(url, pdf, force=force)
        info.update({"via": "treaty-pdf", "source_pdf": str(pdf), "source_url": url})
        pages = _pdf_pages_text(pdf)
        if pages is None or not any(p.strip() for p in pages):
            # pdftotext only: no per-page text to pick parts from
            txt = extract_text(pdf, force=True)
            info.update({"text_pdf": str(pdf), "text_txt": str(txt), "trimmed": False,
                         "note": "pypdf is missing, so the file was not cut to the %s "
                                 "text; it holds every part the UN put in it"
                                 % lang_name(lang)})
        else:
            pages = [p.replace("\xa0", " ") for p in pages]
            slug = {"en": "en", "fr": "fr"}.get(lang, "other") if full else lang_slug(lang)
            stem = out_dir / ("text.%s.full" % slug if full else "text.%s" % slug)
            info.update(_cut(pages, 0, lang, full, pdf, stem,
                             "UNTS volume %d, registration No. %s, per-treaty %s file %s"
                             % (volume, reg_num, TEXT_FILES.get(lang, "Other"), url), rerun,
                             authentic, publication))
        short = _short_page_report(pdf)
        if short:
            info["short_pages"] = short
            where = ", ".join(
                "PDF p. %d (printed p. %s, %d pt)" % (
                    s["pdf_page"], s["printed_page"] or "?", s["height"])
                for s in short)
            first = next((s["printed_page"] for s in short if s["printed_page"]),
                         None)
            info["warning"] = (
                "the per-treaty PDF has page(s) shorter than the rest (median "
                "%d pt): %s. A short page may be cropped and missing text. "
                "Before quoting from it, compare the full volume: `untc.py text "
                "--vol %d --reg %s --from-volume`%s"
                % (short[0]["median"], where, volume, reg_num,
                   " and read printed p. %d" % first if first else ""))
        return info

    except DocumentNotFound:
        pass

    def from_file(file_url, name, via, note):
        """The registration's own file with every language (a 'Part' file
        in the volume, or a 'No Volume' file before the volume is out)."""
        dest = out_dir / name
        download_pdf(file_url, dest, force=force)
        fpages = _pdf_pages_text(dest)
        if not fpages:
            return False
        fpages = [p.replace("\xa0", " ") for p in fpages]
        stem = out_dir / ("text.full" if full else "text.%s" % lang_slug(lang))
        info.update({"via": via, "source_pdf": str(dest), "source_url": file_url, "note": note,
                     "printed_pages": _printed_span(fpages, 0, len(fpages) - 1)})
        info.update(_cut(fpages, 0, lang, full, dest, stem,
                         "UNTS volume %s, registration No. %s, %s" % (volume, reg_num, file_url),
                         rerun, authentic, publication))
        return True

    # 2. The registration's own file in the volume, all languages: far
    # smaller than the volume (vol. 3000, No. 52110: 10 KB against the
    # whole volume).
    if part_url and not from_volume:
        try:
            if from_file(part_url, "text.part.pdf", "part-pdf",
                         "the registration's own file from the UNTS record (every language)"):
                return info
        except DocumentNotFound:
            pass

    # 3. Slice the full volume PDF.
    try:
        pages = volume_pages(volume, force=force)
    except SystemExit as e:
        if no_volume_url:
            try:
                if from_file(no_volume_url, "text.novolume.pdf", "no-volume-pdf",
                             "UNTS volume %s is not published yet; this is the UN's own file of "
                             "the registration, with its own page numbers, not the UNTS pages"
                             % volume):
                    return info
            except DocumentNotFound:
                pass
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
    # The printed folios of the slice: what the citation gives, and the one
    # thing that shows at a glance whether the right pages were found.
    printed_range = _printed_span(pages, start, end - 1)
    page_warning = None
    if page is not None and printed_range and not (
            printed_range[0] - 2 <= page <= printed_range[1]):
        page_warning = (
            "the citation gives p. %d but the located text runs from printed "
            "p. %d to p. %d; check `untc.py volume %d` before quoting"
            % (page, printed_range[0], printed_range[1], volume))
    # With --from-volume, keep the per-treaty extraction (text.<lang>.txt)
    # apart from the volume slice.
    stem = out_dir / ("text.volume" if from_volume else "text")
    stem = stem.with_name(stem.name + (".full" if full else ".%s" % lang_slug(lang)))
    info.update({
        "via": "volume-pdf",
        "source_pdf": str(volume_pdf(volume)),
        "pdf_pages": [start + 1, end],
        "printed_pages": printed_range,
        "source_url": url_unts_volume(volume),
        "note": ("--from-volume: " if from_volume else "no per-treaty file; ")
                + "cut from the volume PDF",
    })
    info.update(_cut(pages[start:end], start, lang, full, volume_pdf(volume), stem,
                     "UNTS volume %d, registration No. %s, cut from the volume PDF %s"
                     % (volume, reg_num, url_unts_volume(volume)), rerun,
                     authentic, publication))
    if page_warning:
        info["warning"] = ((info["warning"] + "; ") if info.get("warning") else "") + page_warning
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
    payload = load_index()
    if q not in UNTS_ONLY and (not hits or hits[0][0] < 100):
        # Not deposited with the Secretary-General (or not in this index):
        # search every registered treaty live in UNTS Online.
        try:
            mode, count, rows = unts_find(args.query, limit=args.limit)
        except (urllib.error.URLError, OSError, ValueError) as e:
            mode, count, rows = None, "0", []
            print("UNTS Online title search failed (%s)." % e, file=sys.stderr)
        # A multilateral hit concluded after the index was built may be a
        # treaty deposited with the SG that the index predates (in force, so
        # registered, but unknown to the index): rebuild an old index before
        # calling it "not in MTDSG".
        newer = [r for r in rows if "multilateral" in (r.get("type") or "").lower()
                 and concluded_after_index(r, payload)]
        if newer and index_age_days(payload) > INDEX_MAX_AGE_DAYS:
            print("UNTS has multilateral treaties concluded after the MTDSG index (as of %s) "
                  "was made (%s) - rebuilding the index from treaties.un.org (about a minute) "
                  "before deciding they are not deposited with the Secretary-General ..."
                  % (index_date(payload), ", ".join(r["reg"] for r in newer[:3])), file=sys.stderr)
            try:
                payload = build_index(refresh=True)
                hits = search_index(args.query, limit=args.limit)
                newer = [r for r in newer if concluded_after_index(r, payload)]
            except (urllib.error.URLError, OSError, ValueError) as e:
                print("COVERAGE WARNING: could not rebuild the index (%s); it is as of %s. "
                      "The UNTS hits concluded after that date may be deposited with the "
                      "Secretary-General and have a status document - check `unts-details` "
                      "(depositary) and tell the user." % (e, index_date(payload)), file=sys.stderr)
        if rows and not (hits and hits[0][0] >= 100):
            print("Not in the MTDSG index (as of %s), so no MTDSG status document. "
                  "Registered in the UNTS (title search, %s match, %s record(s); "
                  "best first):" % (index_date(payload), {"phrase": "phrase", "all": "all-words",
                                                         "phrase-short": "shortened-phrase"}.get(mode, mode), count))
            print_unts_rows(rows)
            for r in newer:
                print("  CAUTION: %s was concluded after the index date; if `unts-details %s` "
                      "names the UN Secretary-General as depositary, it has an MTDSG status "
                      "document after all." % (r["reg"], r["objid"]))
            return
        # Found nowhere: maybe newly deposited with the SG and not yet in force
        # (so not registered yet). Only then is an old index worth rebuilding.
        if not rows and index_age_days(payload) > INDEX_MAX_AGE_DAYS:
            print("no match in the MTDSG index (as of %s) or in UNTS Online - rebuilding "
                  "the index from treaties.un.org (about a minute) ..." % index_date(payload), file=sys.stderr)
            try:
                payload = build_index(refresh=True)
                hits = search_index(args.query, limit=args.limit)
            except (urllib.error.URLError, OSError, ValueError) as e:
                print("COVERAGE WARNING: could not rebuild the index (%s); searched the "
                      "index as of %s. Treaties deposited since then are missing - tell "
                      "the user." % (e, index_date(payload)), file=sys.stderr)
    if q in UNTS_ONLY:
        # The built-in entry is the answer; word overlaps with SG-deposited
        # titles (NATO -> the Baltic cetaceans agreement) only mislead.
        hits = [(s, h) for s, h in hits if s >= 100]
        if not hits:
            return
    elif not hits or hits[0][0] < 100:
        print("NO MATCH: %r is neither in the MTDSG index (as of %s) nor in a UNTS "
              "Online title search. Try other words from the title (`untc.py "
              "unts-search \"<words>\" --words`), or find its UNTS citation (e.g. "
              "'34 UNTS 243' = volume 34, page 243) and run `untc.py text --vol "
              "<volume> --page <page>`. A treaty not yet in force is not registered "
              "in the UNTS." % (args.query.strip(), index_date(payload)))
        if hits:
            print("Titles sharing only some words (almost certainly NOT the "
                  "treaty asked for):")
    for score, h in hits:
        print("  %-10s  %s" % (h["ref"], h["title"]))
        if h.get("place_date"):
            print("              -- %s" % h["place_date"])


def cmd_unts_search(args):
    if args.words:
        mode = "any" if args.any else "all"
        count, rows = unts_search(args.query, mode=mode)
        rows = rows[: args.limit]
    else:
        mode, count, rows = unts_find(args.query, limit=args.limit)
    if args.json:
        _print_json({"query": args.query, "mode": mode, "record_count": count, "results": rows})
        return
    if not rows:
        print("no UNTS record has %r in its title (%s match)" % (args.query, mode))
        return
    print("%s record(s), %s match; showing %d, best first:" % (count, mode, len(rows)))
    print_unts_rows(rows)


def cmd_unts_details(args):
    objid = args.objid
    if not objid:
        if not args.reg:
            raise SystemExit("give an objid, or --reg N (with --series II for filed and recorded)")
        want = "%s-%s" % (args.series, args.reg)
        rows = [r for r in unts_find_reg(args.reg) if r["reg"] == want]
        if not rows:
            raise SystemExit("no UNTS record registered as %s" % want)
        objid = rows[0]["objid"]
    _print_json(unts_details(objid, participants=args.participants))


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
        from_volume=args.from_volume, full=args.full,
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
        info = fetch_text(volume=vol, reg_num=reg, lang=args.lang, force=args.force,
                          full=args.full)
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
            text_info = fetch_text(ref=ref, lang=args.lang, force=args.force,
                                   full=args.full)
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

    p_us = sub.add_parser("unts-search", help="live title search over all UNTS-registered treaties")
    p_us.add_argument("query", help="title or part of it (up to 100 characters are used)")
    p_us.add_argument("--words", action="store_true", help="match all these words instead of the phrase")
    p_us.add_argument("--any", action="store_true", help="with --words: match any of the words")
    p_us.add_argument("--limit", type=int, default=10)
    p_us.add_argument("--json", action="store_true")
    p_us.set_defaults(func=cmd_unts_search)

    p_ud = sub.add_parser("unts-details", help="UNTS record of a search hit: volume, page, PDFs")
    p_ud.add_argument("objid", nargs="?", help="the object id a search hit shows")
    p_ud.add_argument("--reg", help="or the registration number (e.g. 44910)")
    p_ud.add_argument("--series", default="I", choices=["I", "II"])
    p_ud.add_argument("--participants", action="store_true",
                      help="add the actions registered with the UN (signatures, ratifications "
                           "...), with the caveat that must go to the user")
    p_ud.set_defaults(func=cmd_unts_details)

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
    p_tx.add_argument("--lang", default="en",
                      help="en (default), fr, ar, zh, ru, es, or the English name of "
                           "another language the treaty is printed in, e.g. norwegian")
    p_tx.add_argument("--force", action="store_true")
    p_tx.add_argument("--from-volume", action="store_true",
                      help="slice the full volume PDF even if a per-treaty PDF "
                           "exists (for a per-treaty PDF with a cropped page)")
    p_tx.add_argument("--full", action="store_true",
                      help="the whole registration: every language, the signatures, and the "
                           "parties and reservations as at registration (default: the "
                           "registration note and the text in --lang)")
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
    p_fe.add_argument("--full", action="store_true",
                      help="the whole registration: every language, the signatures, and the "
                           "parties and reservations as at registration (default: the "
                           "registration note and the text in --lang)")
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
