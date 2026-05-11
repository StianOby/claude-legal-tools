#!/usr/bin/env python3
"""
eurlex_curia_fetch.py — fetch a CJEU judgment from InfoCuria when EUR-Lex
CELLAR endpoints have failed (e.g. persistent HTTP 202 or all-formats 404).

CELLAR and Curia use independent document stores. Judgments unavailable on
CELLAR (or still being rendered there) are often immediately available on
InfoCuria.

URL pattern:
    Search:  https://curia.europa.eu/juris/liste.jsf?num=C-488%2F21&language=EN
    Doc:     https://curia.europa.eu/juris/document/document_print.jsf?docid=<ID>&doclang=EN&part=1

Results are cached alongside eurlex_fetch.py output at:
    ~/.cache/eurlex/<CELEX>_<LANG>/curia.html  (raw HTML)
    ~/.cache/eurlex/<CELEX>_<LANG>/curia.txt   (plain text)
    ~/.cache/eurlex/<CELEX>_<LANG>/curia_docid.txt

Usage:
    python3 eurlex_curia_fetch.py 62021CJ0488
    python3 eurlex_curia_fetch.py "C-488/21" --lang EN
    python3 eurlex_curia_fetch.py 62021CJ0488 --info
    python3 eurlex_curia_fetch.py 62021CJ0488 --no-cache
"""
from __future__ import annotations

import argparse
import html as html_lib
import os
import pathlib
import re
import sys
from typing import Optional

import requests  # type: ignore[import-untyped]

USER_AGENT = "Mozilla/5.0 (eurlex/1.0)"
TIMEOUT = 30
CURIA_BASE = "https://curia.europa.eu"
CACHE_ROOT = pathlib.Path(
    os.environ.get("EURLEX_CACHE")
    or pathlib.Path.home() / ".cache" / "eurlex"
)

# 3-letter → 2-letter Curia language codes
_LANG_TO_CURIA = {
    "ENG": "EN", "FRA": "FR", "DEU": "DE", "SPA": "ES",
    "ITA": "IT", "NLD": "NL", "DAN": "DA", "SWE": "SV",
    "FIN": "FI", "POL": "PL",
}
# Accept both 2- and 3-letter inputs; normalise to 3-letter
_LANG_NORM = {
    "EN": "ENG", "ENG": "ENG", "FR": "FRA", "FRA": "FRA",
    "DE": "DEU", "DEU": "DEU", "ES": "SPA", "SPA": "SPA",
    "IT": "ITA", "ITA": "ITA", "NL": "NLD", "NLD": "NLD",
    "DA": "DAN", "DAN": "DAN", "SV": "SWE", "SWE": "SWE",
    "FI": "FIN", "FIN": "FIN", "PL": "POL", "POL": "POL",
}


def _norm_lang(lang: str) -> str:
    code = _LANG_NORM.get(lang.upper())
    if not code:
        raise SystemExit(f"Unknown language {lang!r}; use EN/ENG, FR/FRA, DE/DEU, etc.")
    return code


def _celex_to_case(celex: str) -> Optional[str]:
    """62021CJ0488 → C-488/21"""
    m = re.match(r'^6(\d{4})CJ(\d+)$', celex.upper())
    if not m:
        return None
    year, num = m.group(1), int(m.group(2))
    return f"C-{num}/{year[2:]}"


def _case_to_celex(case: str) -> Optional[str]:
    """C-488/21 → 62021CJ0488 (approximate; used for cache dir naming)."""
    m = re.match(r'^C-(\d+)/(\d{2})$', case.upper())
    if not m:
        return None
    num, year2 = int(m.group(1)), m.group(2)
    return f"620{year2}CJ{num:04d}"


def _search_docid(case_num: str, curia_lang: str) -> Optional[str]:
    """Search InfoCuria for a case; return the first matching docid string."""
    encoded_case = case_num.replace("/", "%2F")
    search_url = f"{CURIA_BASE}/juris/liste.jsf?num={encoded_case}&language={curia_lang}"
    print(f"[curia] searching: {search_url}", file=sys.stderr)
    try:
        r = requests.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"[curia] search error: {e}", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"[curia] search HTTP {r.status_code}", file=sys.stderr)
        return None

    # Look for document links: href="...document.jsf?...docid=265596...doclang=EN..."
    matches = re.findall(
        rf'/document/document\.jsf[^"]*?docid=(\d+)[^"]*doclang={re.escape(curia_lang)}',
        r.text, re.I,
    )
    if not matches:
        # Fall back: any docid inside a document.jsf link (language-agnostic)
        matches = re.findall(r'/document/document\.jsf[^"]*?docid=(\d+)', r.text)
    if not matches:
        print("[curia] no document links found in search results", file=sys.stderr)
        return None

    docid = matches[0]
    print(f"[curia] found docid={docid}", file=sys.stderr)
    return docid


def _fetch_doc_html(docid: str, curia_lang: str) -> Optional[bytes]:
    """Fetch the printable HTML rendition of an InfoCuria document by docid."""
    url = (
        f"{CURIA_BASE}/juris/document/document_print.jsf"
        f"?docid={docid}&doclang={curia_lang}&part=1&occ=first&mode=lst"
    )
    print(f"[curia] fetching: {url}", file=sys.stderr)
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"[curia] fetch error: {e}", file=sys.stderr)
        return None
    if r.status_code != 200 or not r.content:
        print(f"[curia] HTTP {r.status_code} ({len(r.content)} bytes)", file=sys.stderr)
        return None
    return r.content


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


def _cache_dir(celex: str, lang: str) -> pathlib.Path:
    d = CACHE_ROOT / f"{celex}_{lang}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(celex_or_case: str, lang: str = "ENG", use_cache: bool = True) -> dict:
    """
    Fetch a CJEU judgment from InfoCuria by CELEX or case number.

    Returns a dict: celex, case_num, language, docid, raw_path, plain_path, plain_text.
    Raises SystemExit on failure.
    """
    lang = _norm_lang(lang)
    curia_lang = _LANG_TO_CURIA[lang]

    inp = celex_or_case.strip()
    if re.match(r'^6\d{4}CJ\d+$', inp, re.I):
        celex = inp.upper()
        case_num = _celex_to_case(celex)
        if not case_num:
            raise SystemExit(f"Cannot parse CELEX {celex!r} as a CJEU case number")
    elif re.match(r'^C-\d+/\d{2,4}$', inp, re.I):
        case_num = inp.upper()
        celex = _case_to_celex(case_num) or case_num.replace("/", "_").replace("-", "")
    else:
        raise SystemExit(
            f"Input {inp!r} is neither a CJEU CELEX (e.g. 62021CJ0488) "
            f"nor a case number (e.g. C-488/21)"
        )

    cache = _cache_dir(celex, lang)
    raw_path   = cache / "curia.html"
    plain_path = cache / "curia.txt"
    docid_path = cache / "curia_docid.txt"

    if use_cache and plain_path.exists() and docid_path.exists():
        return {
            "celex": celex,
            "case_num": case_num,
            "language": lang,
            "docid": docid_path.read_text().strip(),
            "raw_path": str(raw_path),
            "plain_path": str(plain_path),
            "plain_text": plain_path.read_text(encoding="utf-8"),
        }

    docid = _search_docid(case_num, curia_lang)
    if not docid:
        encoded = case_num.replace("/", "%2F")
        raise SystemExit(
            f"No document found on Curia for {case_num} (lang={curia_lang}).\n"
            f"Search manually: {CURIA_BASE}/juris/liste.jsf?num={encoded}&language={curia_lang}"
        )

    blob = _fetch_doc_html(docid, curia_lang)
    if not blob:
        raise SystemExit(
            f"Found docid={docid} on Curia but could not fetch the document.\n"
            f"Try manually: {CURIA_BASE}/juris/document/document_print.jsf"
            f"?docid={docid}&doclang={curia_lang}&part=1"
        )

    html_text  = blob.decode("utf-8", "replace")
    plain_text = _strip_to_plain(html_text)

    raw_path.write_text(html_text, encoding="utf-8")
    plain_path.write_text(plain_text, encoding="utf-8")
    docid_path.write_text(docid)

    return {
        "celex": celex,
        "case_num": case_num,
        "language": lang,
        "docid": docid,
        "raw_path": str(raw_path),
        "plain_path": str(plain_path),
        "plain_text": plain_text,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="InfoCuria CJEU judgment fetcher (last-resort fallback)")
    ap.add_argument("celex", help="CELEX (62021CJ0488) or case number (C-488/21)")
    ap.add_argument("--lang",     default="ENG", help="Language: EN/ENG (default), FR/FRA, DE/DEU, etc.")
    ap.add_argument("--plain",    action="store_true", help="Print plain text (default)")
    ap.add_argument("--raw",      action="store_true", help="Print raw HTML instead of plain text")
    ap.add_argument("--info",     action="store_true", help="Print metadata only, no body")
    ap.add_argument("--no-cache", action="store_true", help="Bypass cache and refetch")
    args = ap.parse_args(argv)

    res = fetch(args.celex, args.lang, use_cache=not args.no_cache)

    if args.info:
        for k in ("celex", "case_num", "language", "docid", "raw_path", "plain_path"):
            print(f"{k}: {res[k]}")
        print(f"plain_chars: {len(res['plain_text'])}")
        return 0

    if args.raw:
        sys.stdout.write(pathlib.Path(res["raw_path"]).read_text(encoding="utf-8"))
        return 0

    sys.stdout.write(res["plain_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
