#!/usr/bin/env python3
"""Lovdata Pro fetcher.

Subcommands
-----------
- login   : open a real browser, let the user log in interactively (SSO/FEIDE
            supported), save the session as storage_state.json.
- status  : print where state is stored and whether the saved session still
            authenticates against lovdata.no/pro.
- resolve : translate a human reference ("HR-2016-2554-P", "Ot.prp. nr. 3
            (1998-99)", "Innst. 521 L (2024-2025)") into a Lovdata Pro path
            <COLLECTION>/<TYPE>/<SLUG>. Tries direct slug rules first, falls
            back to driving the Pro search SPA when needed.
- search  : run a Pro search, print top hits as JSON.
- get     : fetch a document and emit it as markdown / json / html / pdf.

The skill never stores user credentials. Login is delegated to the browser.

Dependencies (install once, in the user's shell):
    pip install playwright beautifulsoup4 html2text
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# --- Lazy optional imports ---------------------------------------------------

def _need(mod, hint=""):
    print(
        f"error: missing python package '{mod}'.\n"
        f"  install: pip install {mod}\n"
        f"  {hint}",
        file=sys.stderr,
    )
    sys.exit(2)


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ModuleNotFoundError:
        _need("playwright", "Then run: python -m playwright install chromium")


def _import_bs4():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ModuleNotFoundError:
        _need("beautifulsoup4")


def _import_html2text():
    try:
        import html2text
        return html2text
    except ModuleNotFoundError:
        _need("html2text")


# --- State directory ---------------------------------------------------------

def state_dir():
    """Resolution order matches the sister `lovdata` skill."""
    env = os.environ.get("LOVDATA_PRO_DATA_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "lovdata-pro"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "lovdata-pro"
    return Path.home() / ".cache" / "lovdata-pro"


def storage_state_path():
    return state_dir() / "storage_state.json"


# --- Reference parsing -------------------------------------------------------

# Year-pair encoding observed from real Lovdata Pro slugs:
#   (2024-2025) -> 202425 (full first year + last 2 of second)
#   (1998-99)   -> 199899
#   (1961-62)   -> 196162
_YEAR_PAIR = re.compile(r"\(?\s*(\d{4})\s*[-–/]\s*(\d{2,4})\s*\)?")


def _encode_session(years):
    m = _YEAR_PAIR.search(years)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)[-2:]}"


@dataclass
class Reference:
    collection: str
    type: str
    slug: str
    alt_collections: tuple = ()
    raw: str = ""

    @property
    def path(self):
        return f"{self.collection}/{self.type}/{self.slug}"

    @property
    def candidates(self):
        out = [self.path]
        for c in self.alt_collections:
            out.append(f"{c}/{self.type}/{self.slug}")
        return out


def parse_reference(ref):
    """Best-effort parse of a Norwegian legal citation.

    Returns None when the citation form needs runtime search (Rt., RG, etc.).

    Forms supported:
        HR-2016-2554-P                  -> HRSIV/avgjorelse/hr-2016-2554-p (alt HRSTR)
        LG-2008-135938                  -> LGSIV/avgjorelse/lg-2008-135938 (alt LGSTR)
        LB/LA/LE/LF/LG/LH-YYYY-N        -> <COURT>SIV/avgjorelse/...
        TR-YYYY-N                       -> TRSIV/avgjorelse/tr-...
        Ot.prp. nr. N (YYYY-YY)         -> PROP/forarbeid/otprp-N-YYYYYY (alt OTPRP)
        Prop. N L (YYYY-YY)             -> PROP/forarbeid/prop-N-l-YYYYYY
        Innst. N L (YYYY-YY)            -> INNST/forarbeid/inns-N-l-YYYYYY
        NOU YYYY: N                     -> NOU/forarbeid/nou-YYYY-N
        <COL>/<TYPE>/<SLUG>             -> passed through unchanged

    Trailing parenthetical names like "(Holship)" or "(Finanger I)" are
    stripped before pattern-matching, but session-year spans like
    "(2024-2025)" are preserved.
    """
    s = ref.strip()
    raw = s
    # Strip a trailing parenthetical name suffix when it doesn't look like a
    # year span. Year spans contain only digits, hyphens, and en-dashes.
    s_for_parse = re.sub(r"\s*\((?![\d–\-]+\))[^)]*\)\s*$", "", s).strip()

    # Already-resolved path
    m = re.fullmatch(r"([A-Z]+)/(avgjorelse|forarbeid)/([a-z0-9\-]+)", s_for_parse, re.I)
    if m:
        return Reference(m.group(1).upper(), m.group(2).lower(), m.group(3).lower(), raw=raw)

    # Modern Supreme Court: HR-YYYY-NNNN-X
    m = re.fullmatch(r"HR-(\d{4})-(\d+)-([A-Z])", s_for_parse, re.I)
    if m:
        slug = f"hr-{m.group(1)}-{m.group(2)}-{m.group(3).lower()}"
        return Reference("HRSIV", "avgjorelse", slug,
                         alt_collections=("HRSTR",), raw=raw)

    # Lagmannsrett: LB/LA/LE/LF/LG/LH-YYYY-N
    m = re.fullmatch(r"(LB|LA|LE|LF|LG|LH)-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        court = m.group(1).upper()
        slug = f"{court.lower()}-{m.group(2)}-{m.group(3)}{m.group(4).lower()}"
        return Reference(f"{court}SIV", "avgjorelse", slug,
                         alt_collections=(f"{court}STR",), raw=raw)

    # Tingrett TR-YYYY-N
    m = re.fullmatch(r"TR-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        slug = f"tr-{m.group(1)}-{m.group(2)}{m.group(3).lower()}"
        return Reference("TRSIV", "avgjorelse", slug,
                         alt_collections=("TRSTR",), raw=raw)

    # Ot.prp. nr. N (YYYY-YY) - matches both "prp" and the typo "prop"
    m = re.match(r"Ot\.?\s*pr[op]p?\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return Reference("PROP", "forarbeid",
                             f"otprp-{m.group(1)}-{sess}",
                             alt_collections=("OTPRP",), raw=raw)

    # Prop. N L|S|... (YYYY-YY)
    m = re.match(r"Prop\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"prop-{n}-{kind}-{sess}" if kind else f"prop-{n}-{sess}"
            return Reference("PROP", "forarbeid", slug, raw=raw)

    # Innst. N L|S|... (YYYY-YY) - collection INNST, slug uses 'inns-'
    m = re.match(r"Innst\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"inns-{n}-{kind}-{sess}" if kind else f"inns-{n}-{sess}"
            return Reference("INNST", "forarbeid", slug, raw=raw)

    # NOU YYYY: N (also "NOU YYYY:N" or "NOU YYYY N")
    m = re.match(r"NOU\s*(\d{4})\s*[:\s]\s*(\d+[A-Za-z]?)", s, re.I)
    if m:
        return Reference("NOU", "forarbeid",
                         f"nou-{m.group(1)}-{m.group(2).lower()}", raw=raw)

    return None


# --- Browser plumbing --------------------------------------------------------

LOVDATA_PRO = "https://lovdata.no/pro/"
LOGGED_IN_HASH = "#myPage"
LOGGED_IN_TITLE_FRAGMENT = "Min side"


def _has_state():
    return storage_state_path().exists()


def _new_context(p, headless=True):
    browser = p.chromium.launch(headless=headless)
    if _has_state():
        return browser.new_context(storage_state=str(storage_state_path()))
    return browser.new_context()


def _is_logged_in(page):
    page.goto(LOVDATA_PRO, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => location.hash === '#myPage' || /Logg inn/i.test(document.title) || /[Ii]nnlogging/i.test(document.body.innerText)",
            timeout=8000,
        )
    except Exception:
        pass
    title = page.title() or ""
    url = page.url or ""
    return LOGGED_IN_TITLE_FRAGMENT in title and LOGGED_IN_HASH in url


# --- Login -------------------------------------------------------------------

def cmd_login(args):
    sync_playwright = _import_playwright()
    state_dir().mkdir(parents=True, exist_ok=True)
    print(f"Saving session to: {storage_state_path()}", file=sys.stderr)
    print("Opening browser. Complete login (incl. SSO/FEIDE), then return here.", file=sys.stderr)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOVDATA_PRO, wait_until="domcontentloaded")
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            try:
                if LOGGED_IN_TITLE_FRAGMENT in (page.title() or "") and LOGGED_IN_HASH in (page.url or ""):
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print("Timed out waiting for login.", file=sys.stderr)
            browser.close()
            return 1
        context.storage_state(path=str(storage_state_path()))
        print(f"Saved session to {storage_state_path()}.", file=sys.stderr)
        browser.close()
    return 0


# --- Status ------------------------------------------------------------------

def cmd_status(args):
    print(f"State dir: {state_dir()}")
    print(f"Storage state: {storage_state_path()} ({'exists' if _has_state() else 'missing'})")
    if not _has_state():
        print("Not logged in. Run: lovdata_pro.py login")
        return 1
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        ctx = _new_context(p, headless=True)
        page = ctx.new_page()
        ok = _is_logged_in(page)
        ctx.browser.close()
    print("Logged in." if ok else "Saved session no longer valid. Re-run: lovdata_pro.py login")
    return 0 if ok else 1


# --- Fetch helpers -----------------------------------------------------------

def _fetch(page, url):
    js = """
    async (url) => {
        const r = await fetch(url, { credentials: 'include' });
        return { status: r.status, body: await r.text() };
    }
    """
    res = page.evaluate(js, url)
    return res["status"], res["body"]


_NOT_FOUND_TITLE = re.compile(r"feilmelding", re.I)
_REDIRECT_STUB_TITLE = re.compile(r"^\s*LovdataPro\s*$", re.I)


def _looks_like_real_doc(html):
    if len(html) < 5000:
        return False
    title_m = re.search(r"<title>([^<]+)</title>", html)
    title = (title_m.group(1) if title_m else "").strip()
    if _NOT_FOUND_TITLE.search(title):
        return False
    if _REDIRECT_STUB_TITLE.match(title):
        return False
    return True


def _doc_url(path):
    return f"https://lovdata.no/pro/document/{path}/*"


def _try_paths(page, paths):
    for path in paths:
        url = _doc_url(path)
        status, html = _fetch(page, url)
        if status == 200 and _looks_like_real_doc(html):
            return path, html
    return None


def _spa_search_top_hits(page, query, n=10):
    page.goto("https://lovdata.no/pro/#search", wait_until="domcontentloaded")
    page.fill("#quickSearchField-input", query)
    page.press("#quickSearchField-input", "Enter")
    try:
        page.wait_for_selector("a[href^='#document/']", timeout=10000)
    except Exception:
        return []
    hrefs = page.evaluate(
        "() => Array.from(document.querySelectorAll('a[href^=\"#document/\"]')).map(a => a.getAttribute('href'))"
    )
    out = []
    seen = set()
    for h in hrefs:
        m = re.match(r"#document/([^/]+)/([^/?#]+)/([^/?#]+)", h)
        if not m:
            continue
        path = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        if path in seen:
            continue
        seen.add(path)
        rn_m = re.search(r"rowNumber=(\d+)", h)
        out.append({"path": path, "raw_href": h, "rowNumber": int(rn_m.group(1)) if rn_m else None})
        if len(out) >= n:
            break
    return out


def cmd_resolve(args):
    parsed = parse_reference(args.ref)
    if parsed:
        print(json.dumps({
            "input": args.ref,
            "parsed": True,
            "candidates": parsed.candidates,
        }, indent=2, ensure_ascii=False))
        return 0
    if args.no_search:
        print(json.dumps({"input": args.ref, "parsed": False, "needs_search": True},
                         indent=2, ensure_ascii=False))
        return 1
    if not _has_state():
        print("error: not logged in. Run `lovdata_pro.py login` first.", file=sys.stderr)
        return 1
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        ctx = _new_context(p, headless=True)
        page = ctx.new_page()
        if not _is_logged_in(page):
            ctx.browser.close()
            print("error: saved session expired. Re-run `lovdata_pro.py login`.", file=sys.stderr)
            return 1
        hits = _spa_search_top_hits(page, args.ref, n=args.search_n)
        ctx.browser.close()
    print(json.dumps({"input": args.ref, "parsed": False, "search_hits": hits},
                     indent=2, ensure_ascii=False))
    return 0 if hits else 1


def cmd_search(args):
    if not _has_state():
        print("error: not logged in. Run `lovdata_pro.py login` first.", file=sys.stderr)
        return 1
    sync_playwright = _import_playwright()
    with sync_playwright() as p:
        ctx = _new_context(p, headless=True)
        page = ctx.new_page()
        if not _is_logged_in(page):
            ctx.browser.close()
            print("error: saved session expired. Re-run `lovdata_pro.py login`.", file=sys.stderr)
            return 1
        hits = _spa_search_top_hits(page, args.query, n=args.n)
        ctx.browser.close()
    print(json.dumps(hits, indent=2, ensure_ascii=False))
    return 0


# --- HTML -> markdown --------------------------------------------------------

def _strip_noise(soup):
    for sel in [".documentButtonsBar", "#textNotes", ".commentBubble",
                ".shareLinkButton", ".writeNoteButton", "script", "style"]:
        for el in soup.select(sel):
            el.decompose()


def _extract_metadata(soup):
    """Read the key/value metadata table from #documentMeta.

    Lovdata's #documentMeta wrapper holds multiple tables: a title table,
    the key/value metadata table (Instans / Dato / Publisert / Stikkord /
    Sammendrag / Henvisninger / ...), and a buttons toolbar. We pick the
    table whose rows look like genuine key/value pairs and skip the rest.
    """
    meta = {}
    meta_div = soup.select_one("#documentMeta") or soup.select_one("#documentBody") or soup
    for table in meta_div.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True)
            val = cells[1].get_text(" ", strip=True)
            if key and val:
                rows.append((key, val))
        # A real metadata table has >= 3 rows where the first cell is a
        # short label. Title tables and toolbars don't qualify.
        if len(rows) >= 3 and all(len(k) <= 40 for k, _ in rows):
            for k, v in rows:
                meta[k] = v
            return meta
    return meta


def _html_to_markdown(html):
    html2text = _import_html2text()
    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    h.protect_links = True
    h.ignore_images = True
    return h.handle(html)


def render(html, fmt):
    BeautifulSoup = _import_bs4()
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    body = soup.select_one("#lovdataDocument") or soup.select_one("#documentBody") or soup.body
    if body is None:
        body = soup
    if fmt == "html":
        return str(body)
    if fmt == "markdown":
        return _html_to_markdown(str(body)).strip() + "\n"
    if fmt == "json":
        title_m = re.search(r"<title>([^<]+)</title>", html)
        return json.dumps({
            "title": (title_m.group(1).strip() if title_m else None),
            "metadata": _extract_metadata(soup),
            "markdown": _html_to_markdown(str(body)).strip(),
        }, indent=2, ensure_ascii=False)
    raise ValueError(f"unknown format: {fmt}")


# --- Get ---------------------------------------------------------------------

def cmd_get(args):
    if not _has_state():
        print("error: not logged in. Run `lovdata_pro.py login` first.", file=sys.stderr)
        return 1
    parsed = parse_reference(args.ref)
    candidates = parsed.candidates if parsed else []
    sync_playwright = _import_playwright()

    with sync_playwright() as p:
        ctx = _new_context(p, headless=True)
        page = ctx.new_page()
        if not _is_logged_in(page):
            ctx.browser.close()
            print("error: saved session expired. Re-run `lovdata_pro.py login`.", file=sys.stderr)
            return 1

        hit = _try_paths(page, candidates) if candidates else None
        if hit is None:
            hits = _spa_search_top_hits(page, args.ref, n=5)
            if not hits:
                ctx.browser.close()
                hint = ""
                # Forarbeider before the late 1960s are typically not in Pro.
                if re.search(r"\(\s*19[0-5]\d", args.ref) or re.search(r"\(\s*196[0-7]", args.ref):
                    hint = " (this document predates Lovdata Pro's forarbeid coverage; very old Ot.prp./Innst./St.prp. may not be available)"
                print(f"error: no document found for '{args.ref}'"
                      f"{hint}. Direct slugs failed and Pro search returned no results.",
                      file=sys.stderr)
                return 1
            top = hits[0]["path"]
            print(f"info: direct slug not found. Using top search hit: {top}",
                  file=sys.stderr)
            html_hit = _try_paths(page, [top])
            if not html_hit:
                ctx.browser.close()
                print(f"error: search-top hit '{top}' did not load. Hits were: "
                      + json.dumps(hits, ensure_ascii=False),
                      file=sys.stderr)
                return 1
            hit = html_hit

        path, html = hit
        if args.format == "pdf":
            doc_page = ctx.new_page()
            doc_page.goto(_doc_url(path), wait_until="networkidle")
            out = args.output or f"{path.replace('/', '_')}.pdf"
            doc_page.pdf(path=out, format="A4", print_background=True)
            doc_page.close()
            print(out)
            ctx.browser.close()
            return 0

        out_text = render(html, args.format)
        ctx.browser.close()

    if args.output:
        Path(args.output).write_text(out_text, encoding="utf-8")
        print(args.output)
    else:
        sys.stdout.write(out_text)
    return 0


# --- CLI ---------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="lovdata_pro.py",
        description="Fetch Norwegian case law and forarbeider from Lovdata Pro.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="Open a browser; complete login interactively.")
    p_login.add_argument("--timeout", type=int, default=300,
                         help="Seconds to wait for login completion (default 300).")
    p_login.set_defaults(func=cmd_login)

    p_status = sub.add_parser("status", help="Show state-dir info and probe the saved session.")
    p_status.set_defaults(func=cmd_status)

    p_resolve = sub.add_parser("resolve",
                               help="Print the Lovdata Pro path for a reference (no fetch).")
    p_resolve.add_argument("ref")
    p_resolve.add_argument("--no-search", action="store_true",
                           help="Do not fall back to runtime search if ambiguous.")
    p_resolve.add_argument("--search-n", type=int, default=5)
    p_resolve.set_defaults(func=cmd_resolve)

    p_search = sub.add_parser("search", help="Run a Pro search and print top hits as JSON.")
    p_search.add_argument("query")
    p_search.add_argument("-n", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    p_get = sub.add_parser("get", help="Fetch a document by reference or path.")
    p_get.add_argument("ref")
    p_get.add_argument("--format", choices=["markdown", "json", "html", "pdf"],
                       default="markdown")
    p_get.add_argument("-o", "--output",
                       help="Write to file (default: stdout for non-PDF).")
    p_get.set_defaults(func=cmd_get)

    return p


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
