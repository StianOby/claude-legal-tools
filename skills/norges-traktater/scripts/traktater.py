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
  python traktater.py status                       Diagnose
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
from html import unescape
from pathlib import Path

USER_AGENT = "norges-traktater-skill/0.1 (+https://lovdata.no)"
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


def _fetch(url: str, ttl: int, no_cache: bool = False) -> str:
    _ensure_cache()
    cf = _cache_key(url)
    if not no_cache and cf.exists() and (time.time() - cf.stat().st_mtime) < ttl:
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
    cf.write_text(html, encoding="utf-8")
    return html


# -- ID normalisation -------------------------------------------------------

def normalize_id(raw: str) -> str:
    s = raw.strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2}-\d+)", s)
    if not m:
        raise ValueError(f"Kjente ikke igjén traktat-ID: {raw!r}")
    return m.group(1)


# -- Registry search --------------------------------------------------------

def search(query="", year=None, country=None, context="tittel",
           max_results=20, no_cache=False):
    sc_map = {"tittel": "I tittel", "tekst": "I teksten"}
    sc_value = sc_map.get(context.lower(), "I tittel")

    results = []
    seen = set()
    offset = 0
    page_size = 20

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
        if not re.search(r'href="\?[^"]*offset=\d+', html):
            break
        offset += page_size

    return results


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


LABEL_MAP = {
    "dato": "Ident",
    "status": "Status",
    "korttittel": "Korttittel",
    "tittel": "Tittel (norsk)",
    "tittelOrginal": "Tittel (originalspråk)",
    "undertegningsdato": "Avtalens undertegningsdato",
    "undertegningssted": "Avtalens undertegningssted",
    "ikraft": "Avtalens ikrafttredelsesdato",
    "undertegningsDatoNorge": "Undertegningsdato Norge",
    "ikraftNorge": "Ikrafttredelsesdato Norge",
    "depositar": "Depositar",
    "undertegningsfullmakt": "Fullmakt til undertegning",
    "saksgang": "Stortinget",
    "ratifikasjonDato": "Ratifikasjon, godkjennelse, godtakelse",
    "deponeringsDato": "Dato for dep. av rat.dok. el.likn.",
    "publisert": "Publisert",
    "fnregistrering": "FN-registrering",
    "merknad": "Merknad",
    "endret": "Endringer/tillegg",
    "stikkord": "Emne",
    "departement": "Fagdepartement",
    "parter": "Parter",
}


def parse_metadata(html):
    out = {}
    # Title is inside <td class="metaTitleText"> -- find any <h1> there.
    title_match = None
    metatitle = re.search(r'<td class="metaTitleText">(.*?)</td>', html, re.S)
    if metatitle:
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', metatitle.group(1), re.S)
        if h1:
            title_match = h1.group(1)
    if not title_match:
        h1 = re.search(r'<h1 class="veryLongTitle">(.*?)</h1>', html, re.S)
        if h1:
            title_match = h1.group(1)
    if title_match:
        out["title"] = unescape(re.sub(r"\s+", " ",
                                       re.sub(r"<[^>]+>", "", title_match))).strip()
    fields = {}
    for m in re.finditer(r'id="metaField_([^"]+)"[^>]*>(.*?)</td>', html, re.S):
        fields[m.group(1)] = _td_to_text(m.group(2))
    ordered = {}
    for k, v in fields.items():
        ordered[LABEL_MAP.get(k, k)] = v
    out["metadata"] = ordered
    return out


def parse_metadata_from_full_table(html):
    table = re.search(r'<table class=" meta"[^>]*>(.*?)</table>', html, re.S)
    out = {}
    if not table:
        return out
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(1), re.S):
        ths = re.findall(r"<th[^>]*>(.*?)</th>", row, re.S)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if not ths or not tds:
            continue
        label = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", ths[0]))).strip()
        if not label:
            continue
        val = _td_to_text(tds[-1])
        if val:
            out[label] = val
    return out


def get_meta(tid, no_cache=False):
    tid = normalize_id(tid)
    html = fetch_doc_html(tid, no_cache=no_cache)
    if not html:
        raise FileNotFoundError(f"Traktat {tid} ikke funnet på {DOC_BASE}/{tid}")
    primary = parse_metadata(html)
    extra = parse_metadata_from_full_table(html)
    merged = dict(primary.get("metadata") or {})
    for k, v in extra.items():
        merged.setdefault(k, v)
    primary["metadata"] = merged
    primary["id"] = tid
    primary["url"] = f"{DOC_BASE}/{tid}"
    return primary


# -- Body / articles --------------------------------------------------------

def _strip_html(s):
    s = re.sub(r'<a class="share-paragraf".*?</a>', "", s, flags=re.S)
    s = re.sub(r'<i [^>]+ss-icon[^>]*>.*?</i>', "", s, flags=re.S)
    s = re.sub(r'<span class="share-paragraf-title">.*?</span>', "", s, flags=re.S)
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
    s = re.sub(r"<h(\d)[^>]*>", "\n\n", s)
    s = re.sub(r"</h\d>", "\n", s)
    s = re.sub(r"<p[^>]*>", "\n", s)
    s = re.sub(r"</p>", "", s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n - ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def get_body_html(html):
    m = re.search(r'<div id="documentBody">(.*?)<ul class="pager"', html, re.S)
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
    lines.append("")
    for k, v in (meta.get("metadata") or {}).items():
        if "\n" in v:
            lines.append(f"{k}:")
            for ln in v.splitlines():
                lines.append(f"  {ln}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def fmt_search(rows):
    if not rows:
        return "(ingen treff)"
    return "\n".join(f"{r['id']}  {r['title']}" for r in rows)


# -- CLI --------------------------------------------------------------------

def cmd_search(args):
    rows = search(args.query or "", year=args.year, country=args.country,
                  context=args.context, max_results=args.max,
                  no_cache=args.no_cache)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(fmt_search(rows))


def cmd_meta(args):
    meta = get_meta(args.id, no_cache=args.no_cache)
    if args.json:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print(fmt_meta(meta))


def cmd_text(args):
    res = get_text(args.id, no_cache=args.no_cache)
    if not res["available"]:
        sys.stderr.write(
            f"Tom kropp på den åpne lovdata.no-siden for {res['id']}.\n"
            f"Selve teksten er sannsynligvis bare tilgjengelig via Lovdata Pro.\n"
            f"URL: {res['url']}\n"
            "Bruk lovdata-pro-skill-en for å hente teksten, eller fall tilbake til\n"
            "depositarens originalkilde (untc/eurlex).\n")
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
                "Bruk lovdata-pro-skill-en for å hente artikkelen.\n")
        sys.exit(2)
    print(res["body"])


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
    except Exception as e:
        print(f"Lovdata.no nåbar: nei ({e})")


def main(argv=None):
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

    sp = sub.add_parser("status", help="Diagnose")
    sp.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
