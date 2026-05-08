#!/usr/bin/env python3
"""
untc.py - UN Treaty Collection CLI.

Pure-HTTP fetcher for the multilateral treaties deposited with the
UN Secretary-General (MTDSG) and the UN Treaty Series (UNTS).
No Selenium, no JS - UNTC publishes its source documents at
predictable doc/Publication paths once you know the MTDSG reference
(e.g. "IV-4" for the ICCPR) or the UNTS volume+registration number.

Subcommands:
  index      Build/refresh the MTDSG chapter index (treaty title -> ref).
  lookup     Fuzzy-search the cached index by treaty title.
  status     Download the MTDSG status document (parties + reservations
             + declarations) for a given ref, e.g. status XXIII-1.
  text       Download the UNTS treaty text PDF for a given ref. The
             volume and registration number are read out of the
             status document; you can also pass --vol / --reg directly.
  fetch      Combo: resolve a name or ref, download status, then text.
  show       Print the extracted text of a previously cached document.

Examples:
  untc.py index --refresh
  untc.py lookup "vienna convention on the law of treaties"
  untc.py status XXIII-1
  untc.py text XXIII-1
  untc.py fetch ICCPR
  untc.py text --vol 999 --reg 14668 --lang en
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
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CACHE_DIR = SKILL_ROOT / "cache"
TREATIES_DIR = CACHE_DIR / "treaties"
INDEX_PATH = CACHE_DIR / "index.json"

BASE = "https://treaties.un.org"
USER_AGENT = (
    "untc-skill/0.1 (+https://github.com/) "
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


DEFAULT_CHAPTER_RANGE = range(1, 31)

LANG_CODES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "ru": "Russian",
    "ar": "Arabic",
    "zh": "Chinese",
}

# Common acronyms and short names. UNTC titles spell things out, but in
# practice users will say "ICCPR" or "VCLT". A direct alias hit pins the
# corresponding ref to the top of the lookup result.
ALIASES = {
    "iccpr":   "IV-4",
    "icescr":  "IV-3",
    "cescr":   "IV-3",
    "cerd":    "IV-2",
    "icerd":   "IV-2",
    "cedaw":   "IV-8",
    "cat":     "IV-9",
    "uncat":   "IV-9",
    "crc":     "IV-11",
    "icrmw":   "IV-13",
    "cmw":     "IV-13",
    "crpd":    "IV-15",
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
    "npt":     "XXVI-5",
    "ctbt":    "XXVI-4",
}

# ---------------------------------------------------------------------------
# Tiny HTTP helper (no third-party deps)
# ---------------------------------------------------------------------------

def http_get(url, *, binary=False, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", errors="replace")


def download_to(url, dest, *, force=False, timeout=60):
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.replace(dest)
    return dest

# ---------------------------------------------------------------------------
# Reference parsing
# ---------------------------------------------------------------------------

REF_RE = re.compile(r"^([IVXLCDM]+)-(\d+)([A-Za-z]?)$")


@dataclass
class MTDSGRef:
    chapter_roman: str
    chapter_int: int
    section: int
    suffix: str = ""

    @classmethod
    def parse(cls, raw):
        s = raw.strip().upper().replace(" ", "")
        m = REF_RE.match(s)
        if not m:
            raise ValueError(
                "bad MTDSG ref %r; expected forms like 'IV-4' or 'XXIII-1'" % raw
            )
        roman, sect, suf = m.group(1), int(m.group(2)), m.group(3).lower()
        if roman not in ROMAN_TO_INT:
            raise ValueError("unknown chapter roman numeral: %s" % roman)
        return cls(roman, ROMAN_TO_INT[roman], sect, suf)

    def __str__(self):
        return "%s-%d%s" % (self.chapter_roman, self.section, self.suffix.upper())

    @property
    def slug(self):
        return "%s-%d%s" % (self.chapter_roman, self.section, self.suffix)

# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def url_chapter_index(chapter_int, lang="en"):
    return "%s/Pages/Treaties.aspx?id=%d&subid=A&clang=_%s" % (BASE, chapter_int, lang)


def url_view_details(ref, lang="en"):
    return (
        "%s/Pages/ViewDetails.aspx?src=TREATY&mtdsg_no=%s&chapter=%d&clang=_%s"
        % (BASE, urllib.parse.quote(str(ref)), ref.chapter_int, lang)
    )


def url_mtdsg_status(ref, lang="en"):
    vol = mtdsg_volume_for_chapter(ref.chapter_int)
    return (
        "%s/doc/Publication/MTDSG/Volume%%20%s/Chapter%%20%s/%s.%s.pdf"
        % (BASE, vol, ref.chapter_roman, ref.slug.upper(), lang)
    )


def url_unts_text(volume, reg_num, lang_full="English", series="I"):
    return (
        "%s/doc/Publication/UNTS/Volume%%20%d/volume-%d-%s-%s-%s.pdf"
        % (BASE, volume, volume, series, reg_num, lang_full)
    )

# ---------------------------------------------------------------------------
# Chapter index harvesting
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    ref: str
    chapter_int: int
    title: str
    place_date: str


def parse_chapter_index(html, chapter_int):
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.I)
    out = []
    seen = set()
    pattern = re.compile(
        r'<a[^>]+href="[^"]*mtdsg_no=([IVXLCDM]+-\d+[a-zA-Z]?)[^"]*"[^>]*>'
        r"([\s\S]{1,800}?)</a>",
        re.I,
    )
    for m in pattern.finditer(html):
        ref = m.group(1).upper()
        if ref in seen:
            continue
        seen.add(ref)
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", " ", inner)
        text = (text.replace("&nbsp;", " ")
                    .replace("&amp;", "&")
                    .replace("&#39;", "'"))
        text = re.sub(r"\s+", " ", text).strip()
        title, _, place = text.partition(".")
        title = title.strip()
        place = place.strip().rstrip(".") or text
        out.append(IndexEntry(ref=ref, chapter_int=chapter_int,
                              title=title, place_date=place))
    return out


def build_index(*, refresh=False, polite_delay=0.4,
                chapter_range=DEFAULT_CHAPTER_RANGE):
    if INDEX_PATH.exists() and not refresh:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    index = []
    chapters_seen = []
    for ch in chapter_range:
        url = url_chapter_index(ch)
        try:
            html = http_get(url)
        except Exception as e:
            print("  chapter %d: skipped (%s)" % (ch, e), file=sys.stderr)
            continue
        entries = parse_chapter_index(html, ch)
        if not entries:
            continue
        chapters_seen.append(ch)
        for e in entries:
            index.append(asdict(e))
        print("  chapter %2d: %d treaties" % (ch, len(entries)), file=sys.stderr)
        time.sleep(polite_delay)
    payload = {
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "https://treaties.un.org/Pages/Treaties.aspx",
        "chapters": chapters_seen,
        "treaties": index,
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return payload


def load_index():
    if not INDEX_PATH.exists():
        raise SystemExit(
            "no cached index - run `untc.py index` first to build it."
        )
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def search_index(query, *, limit=10):
    payload = load_index()
    q = query.lower().strip()
    q_tokens = [t for t in re.split(r"\W+", q) if t]
    aliased_ref = ALIASES.get(q)
    by_ref = {e["ref"]: e for e in payload["treaties"]}
    scored = []
    for entry in payload["treaties"]:
        hay = (entry["title"] + " " + entry["place_date"]).lower()
        score = 0
        if q in hay:
            score += 100
        for t in q_tokens:
            if t in hay:
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
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text(pdf_path, *, force=False):
    txt_path = pdf_path.with_suffix(".txt")
    if txt_path.exists() and txt_path.stat().st_size > 0 and not force:
        return txt_path
    if shutil.which("pdftotext"):
        cmd = ["pdftotext", "-layout", "-enc", "UTF-8",
               str(pdf_path), str(txt_path)]
        subprocess.run(cmd, check=True)
        return txt_path
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as e:
            raise SystemExit(
                "neither `pdftotext` nor pypdf/PyPDF2 are available; "
                "install poppler-utils or `pip install pypdf`"
            ) from e
    reader = PdfReader(str(pdf_path))
    txt_path.write_text(
        "\n\n".join(p.extract_text() or "" for p in reader.pages),
        encoding="utf-8",
    )
    return txt_path

# ---------------------------------------------------------------------------
# MTDSG status doc handling
# ---------------------------------------------------------------------------

VOL_REG_RE = re.compile(r"vol\.?\s*(\d{1,5})\s*,\s*p\.?\s*(\d{1,5})", re.I)
REGISTRATION_RE = re.compile(
    r"REGISTRATION:\s*(?:[\s\S]{0,80}?No\.?\s*)(\d{3,6})", re.I,
)


def parse_status_text(text):
    out = {}
    head = text[:1500]
    chap_m = re.search(r"CHAPTER\s+([IVXLCDM]+)\s*\n([^\n]+)\n", head)
    if chap_m:
        out["chapter_roman"] = chap_m.group(1)
        out["chapter_heading"] = chap_m.group(2).strip()
        head = head[chap_m.end():]
    title_m = re.search(r"\s*\d+\.\s*([A-Z][^\n]{8,200})", head)
    if title_m:
        out["title"] = title_m.group(1).strip().rstrip(".")
    vol_m = VOL_REG_RE.search(text)
    if vol_m:
        out["unts_volume"] = int(vol_m.group(1))
        out["unts_page"] = int(vol_m.group(2))
    reg_m = REGISTRATION_RE.search(text)
    if reg_m:
        out["registration_number"] = reg_m.group(1)
    sig_m = re.search(r"Signatories:\s*(\d+)", text)
    par_m = re.search(r"Parties:\s*(\d+)", text)
    if sig_m:
        out["signatories"] = int(sig_m.group(1))
    if par_m:
        out["parties"] = int(par_m.group(1))
    eif_m = re.search(r"ENTRY INTO FORCE:\s*\n+\s*([^\n]+)", text)
    if eif_m:
        out["entry_into_force"] = eif_m.group(1).strip()
    return out


def treaty_dir(ref):
    return TREATIES_DIR / ref.chapter_roman / ref.slug.upper()


def fetch_status(ref, *, lang="en", force=False):
    if lang not in LANG_CODES:
        raise ValueError("unknown lang %r; one of %s" % (lang, list(LANG_CODES)))
    out_dir = treaty_dir(ref)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / ("status.%s.pdf" % lang)
    download_to(url_mtdsg_status(ref, lang), pdf, force=force)
    txt = extract_text(pdf, force=force)
    text = txt.read_text(encoding="utf-8", errors="replace")
    meta = parse_status_text(text)
    meta["ref"] = str(ref)
    meta["lang"] = lang
    meta["status_pdf"] = str(pdf)
    meta["status_txt"] = str(txt)
    meta["source_url"] = url_mtdsg_status(ref, lang)
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return meta


def fetch_text(ref=None, *, volume=None, reg_num=None, lang="en",
               force=False, series="I"):
    if volume is None or reg_num is None:
        if ref is None:
            raise ValueError("need either ref or (volume, reg_num)")
        meta_path = treaty_dir(ref) / "meta.json"
        if not meta_path.exists():
            fetch_status(ref, lang=lang, force=False)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if volume is None:
            volume = meta.get("unts_volume")
        if reg_num is None:
            reg_num = meta.get("registration_number")
        if volume is None or reg_num is None:
            raise SystemExit(
                "could not determine UNTS volume/registration from "
                "status doc for %s; pass --vol/--reg manually" % ref
            )
    lang_full = LANG_CODES[lang]
    url = url_unts_text(volume, reg_num, lang_full, series=series)
    if ref is not None:
        out_dir = treaty_dir(ref)
    else:
        out_dir = TREATIES_DIR / "_unts" / ("v%d-%s-%s" % (volume, series, reg_num))
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / ("text.%s.pdf" % lang)
    download_to(url, pdf, force=force)
    txt = extract_text(pdf, force=force)
    return {
        "ref": str(ref) if ref else None,
        "volume": volume,
        "registration_number": reg_num,
        "lang": lang,
        "text_pdf": str(pdf),
        "text_txt": str(txt),
        "source_url": url,
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_index(args):
    payload = build_index(refresh=args.refresh)
    print("index: %d treaties across %d chapters -> %s" %
          (len(payload["treaties"]), len(payload["chapters"]), INDEX_PATH))


def cmd_lookup(args):
    hits = search_index(args.query, limit=args.limit)
    if not hits:
        print("(no matches; try `untc.py index --refresh` first)")
        return
    for h in hits:
        print("  %-10s  %s" % (h["ref"], h["title"]))
        if h.get("place_date"):
            print("              -- %s" % h["place_date"])


def cmd_status(args):
    ref = MTDSGRef.parse(args.ref)
    meta = fetch_status(ref, lang=args.lang, force=args.force)
    print(json.dumps(meta, indent=2, ensure_ascii=False))


def cmd_text(args):
    ref = MTDSGRef.parse(args.ref) if args.ref else None
    info = fetch_text(
        ref=ref, volume=args.vol, reg_num=args.reg,
        lang=args.lang, force=args.force, series=args.series,
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_fetch(args):
    raw = args.query.strip()
    if REF_RE.match(raw.upper().replace(" ", "")):
        ref = MTDSGRef.parse(raw)
    else:
        hits = search_index(raw, limit=5)
        if not hits:
            raise SystemExit("no treaty matched %r; try `untc.py lookup`." % raw)
        ref = MTDSGRef.parse(hits[0]["ref"])
        print("resolved %r -> %s: %s" % (raw, ref, hits[0]["title"]),
              file=sys.stderr)
    status = fetch_status(ref, lang=args.lang, force=args.force)
    text_info = None
    if not args.no_text:
        try:
            text_info = fetch_text(ref=ref, lang=args.lang, force=args.force)
        except Exception as e:
            text_info = {"error": str(e)}
    print(json.dumps({"status": status, "text": text_info},
                     indent=2, ensure_ascii=False))


def cmd_show(args):
    ref = MTDSGRef.parse(args.ref)
    base = treaty_dir(ref)
    name = "status" if args.kind == "status" else "text"
    txt = base / ("%s.%s.txt" % (name, args.lang))
    if not txt.exists():
        raise SystemExit(
            "not cached: %s - run `untc.py %s %s` first" % (txt, name, ref)
        )
    sys.stdout.write(txt.read_text(encoding="utf-8", errors="replace"))


def main(argv=None):
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
    p_st.add_argument("ref", help="MTDSG ref like XXIII-1")
    p_st.add_argument("--lang", default="en", choices=list(LANG_CODES))
    p_st.add_argument("--force", action="store_true")
    p_st.set_defaults(func=cmd_status)

    p_tx = sub.add_parser("text", help="download UNTS treaty text PDF")
    p_tx.add_argument("ref", nargs="?", help="MTDSG ref (or use --vol/--reg)")
    p_tx.add_argument("--vol", type=int)
    p_tx.add_argument("--reg", help="UNTS registration number")
    p_tx.add_argument("--series", default="I", choices=["I", "II"])
    p_tx.add_argument("--lang", default="en", choices=list(LANG_CODES))
    p_tx.add_argument("--force", action="store_true")
    p_tx.set_defaults(func=cmd_text)

    p_fe = sub.add_parser("fetch", help="resolve name/ref and grab status+text")
    p_fe.add_argument("query", help="ref like XXIII-1 OR a name like ICCPR")
    p_fe.add_argument("--lang", default="en", choices=list(LANG_CODES))
    p_fe.add_argument("--no-text", action="store_true",
                      help="only download the status doc")
    p_fe.add_argument("--force", action="store_true")
    p_fe.set_defaults(func=cmd_fetch)

    p_sh = sub.add_parser("show", help="cat a cached extracted-text file")
    p_sh.add_argument("ref")
    p_sh.add_argument("--kind", default="status", choices=["status", "text"])
    p_sh.add_argument("--lang", default="en", choices=list(LANG_CODES))
    p_sh.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
