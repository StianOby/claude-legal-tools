#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traktater.py -- Hjelpeverktøy for norges-traktater-ferdigheten.

Henter data fra Lovdatas frie traktatregister:
  - Listing/sok: https://lovdata.no/register/traktater
  - Dokument:    https://lovdata.no/dokument/TRAKTAT/traktat/<id>

Bruk:
  python traktater.py search "Wien"                Søk
  python traktater.py search "" --year 1969        Alle traktater fra 1969
  python traktater.py search "" --country Sverige  Bilateralt med ett land
  python traktater.py meta 1948-12-09-1            Metadata for én traktat
  python traktater.py text 1948-12-09-1            Full norsk tekst
  python traktater.py article 1948-12-09-1 II      En bestemt artikkel
  python traktater.py countries                    Gyldige verdier til --country
  python traktater.py status                       Diagnose
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from html import unescape
from pathlib import Path

USER_AGENT = "norges-traktater-skill/0.2 (+https://lovdata.no)"
BASE = "https://lovdata.no"
REGISTER = f"{BASE}/register/traktater"
DOC_BASE = f"{BASE}/dokument/TRAKTAT/traktat"

LIST_TTL = 24 * 3600
DOC_TTL = 7 * 24 * 3600

# Body that contains less than this many characters of actual text is treated
# as "empty" for fallback purposes -- some Pro-only documents leave behind a
# tiny <a class="namedAnchor"></a> stub that would otherwise pass a naive
# .strip() check.
MIN_BODY_TEXT = 50

PAGE_SIZE = 20  # results per page in Lovdata's register listing


# -- Cache directory --------------------------------------------------------

def _data_root() -> Path:
    env = os.environ.get("NORGES_TRAKTATER_DATA_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "norges-traktater"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "norges-traktater"
    return Path.home() / ".cache" / "norges-traktater"


DATA = _data_root()
CACHE = DATA / "cache"


def _ensure_cache() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)


def _cache_key(url: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", url)[:200]
    return CACHE / f"{safe}.html"


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _fetch(url: str, ttl: int, no_cache: bool = False) -> str:
    _ensure_cache()
    cf = _cache_key(url)
    if not no_cache and cf.exists() and cf.stat().st_size > 0 \
            and (time.time() - cf.stat().st_mtime) < ttl:
        return cf.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ""
        raise
    _write_atomic(cf, html)
    return html


# -- ID normalisation -------------------------------------------------------

def normalize_id(raw: str) -> str:
    s = raw.strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2}-\d+)", s)
    if not m:
        raise ValueError(
            f"Kjente ikke igjen traktat-ID: {raw!r}. Formatet er YYYY-MM-DD-N "
            "(f.eks. 1948-12-09-1), eventuelt hele DokID-en eller URL-en."
        )
    return m.group(1)


# -- Register form values (year / country dropdowns) ------------------------

def _select_options(name: str, no_cache: bool = False) -> list:
    """The values Lovdata's own register dropdown offers for `name`."""
    html = _fetch(REGISTER, LIST_TTL, no_cache=no_cache)
    m = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', html, re.S)
    if not m:
        return []
    out = []
    for opt in re.findall(r"<option[^>]*>(.*?)</option>", m.group(1), re.S):
        val = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", opt))).strip()
        # "Alle land/parter" / "Alle år" are the no-filter entries.
        if val and not val.lower().startswith("alle"):
            out.append(val)
    return out


def countries(no_cache: bool = False) -> list:
    return _select_options("country", no_cache=no_cache)


def years(no_cache: bool = False) -> list:
    return _select_options("year", no_cache=no_cache)


def _resolve_option(kind: str, value: str, no_cache: bool = False) -> str:
    """Map a user-supplied --country/--year to the register's own spelling.

    Lovdata silently ignores an unknown value and returns the *whole*
    register, so an unchecked typo would look like a real result set.
    """
    options = countries(no_cache=no_cache) if kind == "country" else years(no_cache=no_cache)
    if not options:
        return value  # register markup changed; let the server decide
    for o in options:
        if o.lower() == value.strip().lower():
            return o
    close = difflib.get_close_matches(value, options, n=5, cutoff=0.6)
    hint = ("Mente du: " + ", ".join(close) + "?") if close else \
        ("Se hele listen med: python traktater.py countries"
         if kind == "country" else f"Gyldige år: {options[-1]}-{options[0]}.")
    raise SystemExit(
        f"Ukjent {kind}: {value!r}. Lovdata ville ha ignorert filteret og "
        f"returnert hele registeret. {hint}"
    )


# -- Registry search --------------------------------------------------------

def _hit_count(html: str):
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"([\d \s]{1,12})\s*treff", text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else None


def search(query="", year=None, country=None, context="tittel",
           max_results=20, no_cache=False):
    """Return {"total": <treff i registeret>, "results": [...]}.

    `total` is what Lovdata reports for the whole query, which is usually far
    more than `max_results` -- the caller should say so rather than implying
    the printed rows are everything.
    """
    sc_map = {"tittel": "I tittel", "tekst": "I teksten"}
    sc_value = sc_map.get(context.lower(), "I tittel")
    if country:
        country = _resolve_option("country", country, no_cache=no_cache)
    if year:
        year = _resolve_option("year", str(year), no_cache=no_cache)

    results = []
    seen = set()
    offset = 0
    total = None

    while len(results) < max_results:
        params = {}
        if query:
            params["search"] = query
            params["searchContext"] = sc_value
        if year:
            params["year"] = year
        if country:
            params["country"] = country
        if offset:
            params["offset"] = str(offset)
        url = f"{REGISTER}?{urllib.parse.urlencode(params)}" if params else REGISTER
        html = _fetch(url, LIST_TTL, no_cache=no_cache)
        if not html:
            break
        if total is None:
            total = _hit_count(html)

        rows = re.findall(
            r'<a\s+href="/dokument/TRAKTAT/traktat/(\d{4}-\d{2}-\d{2}-\d+)(?:\?[^"]*)?"[^>]*>'
            r'\s*<strong>\s*(.*?)\s*</strong>',
            html, flags=re.S,
        )
        if not rows:
            rows = re.findall(
                r'<a\s+href="/dokument/TRAKTAT/traktat/(\d{4}-\d{2}-\d{2}-\d+)(?:\?[^"]*)?"[^>]*>(.*?)</a>',
                html, flags=re.S,
            )

        new_count = 0
        for tid, inner in rows:
            if tid in seen:
                continue
            seen.add(tid)
            title = re.sub(r"<[^>]+>", " ", inner)
            title = unescape(re.sub(r"\s+", " ", title)).strip()
            results.append({"id": tid, "title": title, "year": tid[:4]})
            new_count += 1
            if len(results) >= max_results:
                break

        if new_count == 0:
            break
        if total is not None and len(seen) >= total:
            break
        if not re.search(r'href="\?[^"]*offset=\d+', html):
            break
        offset += PAGE_SIZE

    return {"total": total, "shown": len(results), "results": results}


# -- Document fetch / metadata ---------------------------------------------

def fetch_doc_html(tid, no_cache=False):
    return _fetch(f"{DOC_BASE}/{tid}", DOC_TTL, no_cache=no_cache)


def _td_to_text(raw):
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p\s*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(raw)
    text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text


def _format_parties(value):
    """Blank line between parties so a long partsliste stays readable."""
    lines = value.splitlines()
    out = []
    for ln in lines:
        if ln.startswith("Part:") and out:
            out.append("")
        out.append(ln)
    return "\n".join(out)


def parse_metadata(html):
    """Title plus the metadata table.

    The label comes from the row's own <th>, and the Lovdata field id from
    the <td id="metaField_...">, so there is no hand-maintained label table
    to drift out of date (and no chance of the same field appearing twice
    under two spellings of its label).
    """
    out = {}
    title_match = None
    metatitle = re.search(r'<td class="metaTitleText">(.*?)</td>', html, re.S)
    if metatitle:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", metatitle.group(1), re.S)
        if h1:
            title_match = h1.group(1)
    if not title_match:
        h1 = re.search(r'<h1 class="veryLongTitle">(.*?)</h1>', html, re.S)
        if h1:
            title_match = h1.group(1)
    if title_match:
        out["title"] = unescape(re.sub(r"\s+", " ",
                                       re.sub(r"<[^>]+>", "", title_match))).strip()

    ordered = {}
    fields = {}
    table = re.search(r'<table class="[^"]*\bmeta\b[^"]*"[^>]*>(.*?)</table>', html, re.S)
    if table:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(1), re.S):
            th = re.search(r"<th[^>]*>(.*?)</th>", row, re.S)
            td = re.search(r"<td[^>]*>(.*?)</td>", row, re.S)
            if not th or not td:
                continue
            label = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", th.group(1)))).strip()
            value = _td_to_text(td.group(1))
            if not label or not value:
                continue
            fid = re.search(r'id="metaField_([^"]+)"', row)
            if fid:
                fields[fid.group(1)] = value
                if fid.group(1) == "parter":
                    value = _format_parties(value)
            ordered.setdefault(label, value)
    if not ordered:
        # Fallback for a markup change: read the metaField cells directly.
        for m in re.finditer(r'id="metaField_([^"]+)"[^>]*>(.*?)</td>', html, re.S):
            fields[m.group(1)] = _td_to_text(m.group(2))
            ordered[m.group(1)] = fields[m.group(1)]

    out["metadata"] = ordered
    out["fields"] = fields
    return out


def get_meta(tid, no_cache=False):
    tid = normalize_id(tid)
    html = fetch_doc_html(tid, no_cache=no_cache)
    if not html:
        raise FileNotFoundError(f"Traktat {tid} ikke funnet på {DOC_BASE}/{tid}")
    meta = parse_metadata(html)
    meta["id"] = tid
    meta["url"] = f"{DOC_BASE}/{tid}"
    meta["has_text"] = _body_has_text(get_body_html(html))
    return meta


# -- Body / articles --------------------------------------------------------

# Lovdata bruker ikke <ul>/<li>: bokstav- og nummerpunkter er én-rads
# tabeller med klassen "listeItem" og en "leftMargin_N"-klasse som bærer
# nivået. Uten egen håndtering blir «a.» limt til teksten og punktene
# limt til hverandre («som sådan:a.å drepe medlemmer av gruppen;b.å ...»).
_LISTEITEM_RE = re.compile(
    r'<table[^>]*class="([^"]*\blisteItem\b[^"]*)"[^>]*>(.*?)</table>',
    re.S | re.I,
)
_TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def _cell_text(raw):
    raw = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))).strip()


def _listeitem_sub(m):
    cls, inner = m.group(1), m.group(2)
    lm = re.search(r"leftMargin_(\d+)", cls)
    indent = "  " * max(0, (int(lm.group(1)) if lm else 1) - 1)
    parts = [p for p in (_cell_text(c) for c in _CELL_RE.findall(inner)) if p]
    # No trailing newline: consecutive points should be consecutive lines,
    # not separated by a blank line.
    return "\n" + indent + " ".join(parts) if parts else "\n"


def _table_sub(m):
    """Tables are used for two different things in Lovdata's treaty markup.

    Numbered paragraphs (`<table data-id="AVSNITT_1">`) are single-cell
    tables and must read as ordinary prose; only genuinely multi-column
    tables become pipe rows.
    """
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S | re.I):
        cells = [_cell_text(c) for c in _CELL_RE.findall(row)]
        cells = [c for c in cells] if any(cells) else []
        if not cells:
            continue
        if len(cells) == 1:
            rows.append(cells[0])
        else:
            rows.append("| " + " | ".join(cells) + " |")
    return "\n" + "\n".join(rows) + "\n" if rows else "\n"


def _strip_html(s):
    s = re.sub(r'<a class="share-paragraf".*?</a>', "", s, flags=re.S)
    s = re.sub(r'<i [^>]+ss-icon[^>]*>.*?</i>', "", s, flags=re.S)
    s = re.sub(r'<span class="share-paragraf-title">.*?</span>', "", s, flags=re.S)
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    s = _LISTEITEM_RE.sub(_listeitem_sub, s)
    s = _TABLE_RE.sub(_table_sub, s)
    s = re.sub(r"<h(\d)[^>]*>", "\n\n", s)
    s = re.sub(r"</h\d>", "\n", s)
    s = re.sub(r"<p[^>]*>", "\n", s)
    s = re.sub(r"</p>", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n - ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def get_body_html(html):
    m = re.search(r'<div id="documentBody">(.*?)<ul class="pager"', html, re.S)
    if m:
        return m.group(1)
    m = re.search(r'<div id="documentBody">(.*)', html, re.S)
    return m.group(1) if m else ""


def _body_has_text(body_html):
    """True if the body contains real prose (more than a stub anchor)."""
    txt = _strip_html(body_html)
    return len(txt) >= MIN_BODY_TEXT


def get_text(tid, no_cache=False):
    tid = normalize_id(tid)
    html = fetch_doc_html(tid, no_cache=no_cache)
    if not html:
        raise FileNotFoundError(f"Traktat {tid} ikke funnet")
    body_html = get_body_html(html)
    if not _body_has_text(body_html):
        return {"id": tid, "url": f"{DOC_BASE}/{tid}", "body": "", "available": False}
    return {"id": tid, "url": f"{DOC_BASE}/{tid}",
            "body": _strip_html(body_html), "available": True}


def _roman(n):
    pairs = [(50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
             (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in pairs:
        while n >= v:
            out += s
            n -= v
    return out


def _normalize_article_key(raw):
    s = raw.strip()
    s = re.sub(r"^[Aa]rt(?:ikkel|\.|ikel)?\s*", "", s)
    s = s.strip().rstrip(".")
    candidates = []
    if not s:
        return candidates
    if s.isdigit():
        n = int(s)
        candidates.append(s)
        if 1 <= n <= 50:
            candidates.append(_roman(n).lower())
    else:
        candidates.append(s.lower())
        if re.fullmatch(r"[ivxl]+", s.lower()):
            order = {"i": 1, "v": 5, "x": 10, "l": 50}
            total, prev = 0, 0
            for ch in reversed(s.lower()):
                val = order[ch]
                total += -val if val < prev else val
                prev = val
            candidates.append(str(total))
    return candidates


def get_article(tid, art, no_cache=False):
    tid = normalize_id(tid)
    html = fetch_doc_html(tid, no_cache=no_cache)
    if not html:
        raise FileNotFoundError(f"Traktat {tid} ikke funnet")
    body_html = get_body_html(html)
    if not _body_has_text(body_html):
        return {"id": tid, "article": art, "body": "", "available": False,
                "url": f"{DOC_BASE}/{tid}"}
    keys = _normalize_article_key(art)
    if not keys:
        raise ValueError(f"Kunne ikke tolke artikkelnummer: {art!r}")
    for key in keys:
        start_re = re.compile(
            rf'<div[^>]+data-id="ARTIKKEL_{re.escape(key)}"[^>]*>', re.I)
        sm = start_re.search(body_html)
        if not sm:
            continue
        rest = body_html[sm.start():]
        nxt = re.search(
            r'<a[^>]+name="(?:ARTIKKEL_[^"]+|KAPITTEL_[^"]+)"', rest[1:])
        chunk = rest[: 1 + nxt.start()] if nxt else rest
        return {"id": tid, "article": art, "body": _strip_html(chunk),
                "available": True, "url": f"{DOC_BASE}/{tid}"}
    found = sorted(set(re.findall(r'ARTIKKEL_([a-zA-Z0-9_-]+)', body_html)))
    return {"id": tid, "article": art, "body": "", "available": False,
            "url": f"{DOC_BASE}/{tid}", "available_articles": found,
            "error": (f"Artikkel {art!r} ble ikke funnet. Tilgjengelige artikler: "
                      f"{', '.join(found) if found else '(ingen)'}.")}


# -- Pretty printers --------------------------------------------------------

def fmt_meta(meta):
    lines = []
    title = meta.get("title")
    if title:
        lines.append(title)
        lines.append("=" * min(len(title), 80))
    lines.append(f"ID:  {meta['id']}")
    lines.append(f"URL: {meta['url']}")
    if meta.get("has_text") is False:
        lines.append("Tekst: ikke publisert fritt på lovdata.no (bare metadata) "
                     "— se «Når kroppen er tom» i SKILL.md")
    lines.append("")
    for k, v in (meta.get("metadata") or {}).items():
        if "\n" in v:
            lines.append(f"{k}:")
            for ln in v.splitlines():
                lines.append(f"  {ln}" if ln else "")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def fmt_search(payload):
    rows = payload["results"]
    if not rows:
        return "(ingen treff)"
    out = [f"{r['id']}  {r['title']}" for r in rows]
    total = payload.get("total")
    if total and total > len(rows):
        out.append("")
        out.append(f"Viser {len(rows)} av {total} treff. "
                   f"Bruk --max for flere, eller avgrens søket.")
    elif total:
        out.append("")
        out.append(f"{total} treff totalt.")
    return "\n".join(out)


# -- CLI --------------------------------------------------------------------

def cmd_search(args):
    payload = search(args.query or "", year=args.year, country=args.country,
                     context=args.context, max_results=args.max,
                     no_cache=args.no_cache)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(fmt_search(payload))


def cmd_meta(args):
    meta = get_meta(args.id, no_cache=args.no_cache)
    if args.json:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print(fmt_meta(meta))


def lovdata_pointers(meta):
    """lovdata.no-lenker Lovdata selv oppgir i metadataene.

    For traktater som er inkorporert i norsk lov peker feltet «Original
    tekst» rett på loven som har teksten som vedlegg — for EMK er det
    menneskerettsloven, som ligger fritt tilgjengelig.
    """
    out = []
    seen = set()
    for label, value in (meta.get("metadata") or {}).items():
        for url in re.findall(r"https?://(?:www\.)?lovdata\.no/\S+", value):
            url = url.rstrip(".,;")
            if url in seen:
                continue
            seen.add(url)
            out.append((label, url))
    return out


def _pointer_lines(tid):
    try:
        meta = get_meta(tid)
    except Exception:
        return ""
    hits = lovdata_pointers(meta)
    if not hits:
        return ""
    lines = ["", "Lovdata oppgir selv disse lenkene for dette dokumentet:"]
    for label, url in hits:
        extra = ""
        m = re.search(r"/lov/(\d{4}-\d{2}-\d{2}-\d+)", url)
        if m:
            extra = (f"  -> hent teksten med lovdata-api: "
                     f"get \"NL/lov/{m.group(1)}\"")
        lines.append(f"  {label}: {url}{extra}")
    return "\n".join(lines) + "\n"


def cmd_text(args):
    res = get_text(args.id, no_cache=args.no_cache)
    if not res["available"]:
        sys.stderr.write(
            f"Tom kropp på den åpne lovdata.no-siden for {res['id']}.\n"
            f"URL: {res['url']}\n"
            + _pointer_lines(res["id"]) +
            "Teksten er ikke publisert fritt her. Prøv i denne rekkefølgen:\n"
            "  1. Er traktaten inkorporert i menneskerettsloven "
            "(EMK, SP, ØSK, CEDAW, CRC, CRPD)? Da ligger hele teksten fritt i\n"
            "     NL/lov/1999-05-21-30 — bruk lovdata-api-skill-en.\n"
            "  2. FN-deponerte traktater: untc-skill-en (originaltekst + partsliste).\n"
            "  3. EØS/EU-rettsakter: eurlex-skill-en.\n"
            "  4. Lovdata Pro (krever abonnement og Cowork): lovdata-pro-skill-en.\n")
        sys.exit(2)
    print(res["body"])


def cmd_article(args):
    res = get_article(args.id, args.article, no_cache=args.no_cache)
    if not res["available"]:
        if "error" in res:
            sys.stderr.write(res["error"] + "\n")
        else:
            sys.stderr.write(
                f"Tom kropp på den åpne lovdata.no-siden for {res['id']}.\n"
                f"URL: {res['url']}\n"
                + _pointer_lines(res["id"]) +
                "Se «Når kroppen er tom» i SKILL.md for hvilke kilder som "
                "har teksten (menneskerettsloven, untc, eurlex, lovdata-pro).\n")
        sys.exit(2)
    print(res["body"])


def cmd_countries(args):
    opts = countries(no_cache=args.no_cache)
    if args.query:
        q = args.query.lower()
        opts = [o for o in opts if q in o.lower()]
    print("\n".join(opts) if opts else "(ingen treff)")


def cmd_status(args):
    print(f"Cache-katalog: {CACHE}")
    print(f"Eksisterer: {CACHE.exists()}")
    if CACHE.exists():
        n = sum(1 for _ in CACHE.glob("*.html"))
        print(f"Cachede filer: {n}")
    try:
        html = _fetch(REGISTER, LIST_TTL, no_cache=args.no_cache)
        ok = "Norges traktater" in html or "register/traktater" in html
        print(f"Lovdata.no nåbar: {'ja' if ok else 'usikker'}")
        total = _hit_count(html)
        print(f"Traktater i registeret: {total if total is not None else 'ukjent'}")
        yrs = years(no_cache=args.no_cache)
        if yrs:
            print(f"Årganger: {yrs[-1]}-{yrs[0]} ({len(yrs)} år)")
        cs = countries(no_cache=args.no_cache)
        print(f"Land/parter i nedtrekkslisten: {len(cs)}")
        if total is None or not yrs or not cs:
            print("ADVARSEL: klarte ikke å lese alle feltene — "
                  "Lovdata kan ha endret markupen.")
    except Exception as e:
        print(f"Lovdata.no nåbar: nei ({e})")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-cache", action="store_true",
                   help="Ignorer cache, hent friskt")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="Søk i registeret")
    sp.add_argument("query", nargs="?", default="", help="Søkeord (kan være tom)")
    sp.add_argument("--year", help="Bare ett bestemt år")
    sp.add_argument("--country", help="Filtrer på motpart/land (norsk navn)")
    sp.add_argument("--context", default="tittel",
                    choices=["tittel", "tekst"],
                    help="Søk i tittel (standard) eller fulltekst")
    sp.add_argument("--max", type=int, default=20, help="Maks antall treff")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("meta", help="Metadata for én traktat")
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_meta)

    sp = sub.add_parser("text", help="Full norsk tekst for én traktat")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_text)

    sp = sub.add_parser("article", help="Hent én bestemt artikkel")
    sp.add_argument("id")
    sp.add_argument("article", help="Artikkelnummer")
    sp.set_defaults(func=cmd_article)

    sp = sub.add_parser("countries", help="List gyldige verdier til --country")
    sp.add_argument("query", nargs="?", help="Filtrer listen")
    sp.set_defaults(func=cmd_countries)

    sp = sub.add_parser("status", help="Diagnose")
    sp.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as e:
        raise SystemExit(str(e))
    except ValueError as e:
        raise SystemExit(str(e))
    except urllib.error.URLError as e:
        raise SystemExit(f"Nettverksfeil mot lovdata.no: {e}")


if __name__ == "__main__":
    main()
