#!/usr/bin/env python3
"""
eurlex_fetch.py — fetch an EU legal document from EUR-Lex when the eurlex MCP
cannot retrieve it (404 "Document not found" or 50 000-char truncation).

Strategy:
    1. GET http://publications.europa.eu/resource/celex/<CELEX>.<LANG>
       with Accept: text/html  (works for older judgments with static HTML)
    2. If 404: same URL with Accept: application/xml
       (newer judgments expose only the GENDOC2XHTML rendering of FMX4 here)
    3. If both 404: Accept: application/pdf, then extract text with pypdf

Results are cached under ~/.cache/eurlex/<CELEX>_<LANG>/.

Usage:
    python3 eurlex_fetch.py 62002CJ0371                 # ENG, plain text to stdout
    python3 eurlex_fetch.py 62016CJ0569 --lang ENG --plain
    python3 eurlex_fetch.py 62016CJ0569 --raw           # the raw HTML/XHTML/PDF text
    python3 eurlex_fetch.py 62016CJ0569 --info          # source + cache paths only
    python3 eurlex_fetch.py 62016CJ0569 --no-cache      # bypass cache, refetch
"""
from __future__ import annotations

import argparse
import html as html_lib
import os
import pathlib
import re
import sys
from typing import Optional

import time

import requests  # type: ignore[import-untyped]

USER_AGENT = "Mozilla/5.0 (eurlex/1.0)"
TIMEOUT = 30
# Seconds to wait after HTTP 202 before each retry (CELLAR renders on-the-fly)
_RETRY_DELAYS = [5, 10, 10]
CACHE_ROOT = pathlib.Path(
    os.environ.get("EURLEX_CACHE")
    or pathlib.Path.home() / ".cache" / "eurlex"
)

LANG_CODES = {
    "EN": "ENG", "ENG": "ENG",
    "FR": "FRA", "FRA": "FRA",
    "DE": "DEU", "DEU": "DEU",
    "ES": "SPA", "SPA": "SPA",
    "IT": "ITA", "ITA": "ITA",
    "NL": "NLD", "NLD": "NLD",
    "DA": "DAN", "DAN": "DAN",
    "SV": "SWE", "SWE": "SWE",
    "FI": "FIN", "FIN": "FIN",
    "PL": "POL", "POL": "POL",
}


def _norm_lang(lang: str) -> str:
    code = LANG_CODES.get(lang.upper())
    if not code:
        raise SystemExit(f"Unknown language {lang!r}; use ENG, FRA, DEU, etc.")
    return code


def _cache_dir(celex: str, lang: str) -> pathlib.Path:
    d = CACHE_ROOT / f"{celex}_{lang}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _strip_to_plain(markup: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>",  " ", text,   flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>",                "\n", text,  flags=re.I)
    text = re.sub(r"</p\s*>",                  "\n\n", text, flags=re.I)
    text = re.sub(r"</li\s*>",                 "\n", text,  flags=re.I)
    text = re.sub(r"<[^>]+>",                  " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+",       " ", text)
    text = re.sub(r"\n[ \t]+",     "\n", text)
    text = re.sub(r"\n{3,}",       "\n\n", text)
    return text.strip()


def _try_fetch(celex: str, lang: str, accept: str) -> Optional[bytes]:
    url = f"http://publications.europa.eu/resource/celex/{celex}.{lang}"
    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    for attempt in range(1 + len(_RETRY_DELAYS)):
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        except requests.RequestException as e:
            print(f"[fetch] {accept} -> network error: {e}", file=sys.stderr)
            return None
        if r.status_code == 200 and r.content:
            return r.content
        if r.status_code == 202 and attempt < len(_RETRY_DELAYS):
            delay = _RETRY_DELAYS[attempt]
            print(
                f"[fetch] {accept} -> HTTP 202 (rendition being generated), "
                f"retrying in {delay}s ({attempt + 1}/{len(_RETRY_DELAYS)})...",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue
        print(
            f"[fetch] {accept} -> HTTP {r.status_code} ({len(r.content)} bytes)",
            file=sys.stderr,
        )
        return None
    return None


def _pdf_to_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as e:
        raise SystemExit(
            "pypdf is required for PDF fallback. Install with: "
            "pip install pypdf"
        ) from e
    import io
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)


def fetch(celex: str, lang: str = "ENG", use_cache: bool = True) -> dict:
    """
    Returns a dict with keys:
        celex, language, source ('html' | 'xhtml' | 'pdf'),
        raw_path, plain_path, plain_text
    Raises SystemExit on hard failure.
    """
    lang = _norm_lang(lang)
    celex = celex.strip().upper()
    cache = _cache_dir(celex, lang)

    raw_html  = cache / "raw.html"
    raw_xhtml = cache / "raw.xhtml"
    raw_pdf   = cache / "raw.pdf"
    plain     = cache / "plain.txt"
    source_marker = cache / "source.txt"

    if use_cache and plain.exists() and source_marker.exists():
        return {
            "celex": celex,
            "language": lang,
            "source": source_marker.read_text().strip(),
            "raw_path": str(_pick_existing([raw_html, raw_xhtml, raw_pdf])),
            "plain_path": str(plain),
            "plain_text": plain.read_text(encoding="utf-8"),
        }

    # 1) HTML
    blob = _try_fetch(celex, lang, "text/html")
    if blob:
        text = blob.decode("utf-8", "replace")
        raw_html.write_text(text, encoding="utf-8")
        plain_text = _strip_to_plain(text)
        plain.write_text(plain_text, encoding="utf-8")
        source_marker.write_text("html")
        return _result(celex, lang, "html", raw_html, plain, plain_text)

    # 2) XHTML rendition (FMX4 -> GENDOC2XHTML)
    blob = _try_fetch(celex, lang, "application/xml")
    if blob:
        text = blob.decode("utf-8", "replace")
        raw_xhtml.write_text(text, encoding="utf-8")
        plain_text = _strip_to_plain(text)
        plain.write_text(plain_text, encoding="utf-8")
        source_marker.write_text("xhtml")
        return _result(celex, lang, "xhtml", raw_xhtml, plain, plain_text)

    # 3) PDF
    blob = _try_fetch(celex, lang, "application/pdf")
    if blob:
        raw_pdf.write_bytes(blob)
        plain_text = _pdf_to_text(blob)
        plain.write_text(plain_text, encoding="utf-8")
        source_marker.write_text("pdf")
        return _result(celex, lang, "pdf", raw_pdf, plain, plain_text)

    curia_url = _celex_to_curia_url(celex, lang)
    if curia_url:
        curia_hint = (
            f"Try Curia directly:\n  {curia_url}\n"
            f"Or: python3 eurlex_curia_fetch.py {celex} --lang {lang}"
        )
    else:
        curia_hint = "Try curia.europa.eu (InfoCuria search) or the printed Reports of Cases."
    raise SystemExit(
        f"All CELLAR endpoints failed for CELEX {celex} (lang={lang}).\n{curia_hint}"
    )


def _celex_to_curia_url(celex: str, lang: str = "ENG") -> Optional[str]:
    """Return an InfoCuria search URL for a CJEU CELEX (e.g. 62021CJ0488 → C-488/21)."""
    m = re.match(r'^6(\d{4})CJ(\d+)$', celex.upper())
    if not m:
        return None
    year, num = m.group(1), int(m.group(2))
    case = f"C-{num}/{year[2:]}"
    curia_lang = {
        "ENG": "EN", "FRA": "FR", "DEU": "DE", "SPA": "ES",
        "ITA": "IT", "NLD": "NL", "DAN": "DA", "SWE": "SV",
        "FIN": "FI", "POL": "PL",
    }.get(lang, "EN")
    return (
        f"https://curia.europa.eu/juris/liste.jsf"
        f"?num={case.replace('/', '%2F')}&language={curia_lang}"
    )


def _result(celex, lang, source, raw_p, plain_p, text):
    return {
        "celex": celex,
        "language": lang,
        "source": source,
        "raw_path": str(raw_p),
        "plain_path": str(plain_p),
        "plain_text": text,
    }


def _pick_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description="EUR-Lex CELEX fetcher (fallback to MCP)")
    ap.add_argument("celex", help="CELEX identifier, e.g. 62002CJ0371")
    ap.add_argument("--lang", default="ENG", help="Language: ENG (default), FRA, DEU, etc.")
    ap.add_argument("--plain", action="store_true", help="Print plain-text body (default)")
    ap.add_argument("--raw",   action="store_true", help="Print raw HTML/XHTML body instead of plain text")
    ap.add_argument("--info",  action="store_true", help="Print source + paths only, no body")
    ap.add_argument("--no-cache", action="store_true", help="Bypass cache and refetch")
    args = ap.parse_args(argv)

    res = fetch(args.celex, args.lang, use_cache=not args.no_cache)

    if args.info:
        for k in ("celex", "language", "source", "raw_path", "plain_path"):
            print(f"{k}: {res[k]}")
        print(f"plain_chars: {len(res['plain_text'])}")
        return 0

    if args.raw:
        # Read raw from disk so PDF case becomes binary-safe via plain.txt
        path = pathlib.Path(res["raw_path"])
        if path.suffix == ".pdf":
            sys.stderr.write("[raw] PDF source: emitting extracted text instead\n")
            sys.stdout.write(res["plain_text"])
        else:
            sys.stdout.write(path.read_text(encoding="utf-8"))
        return 0

    sys.stdout.write(res["plain_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
