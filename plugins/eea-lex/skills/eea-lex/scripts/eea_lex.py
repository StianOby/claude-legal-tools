#!/usr/bin/env python3
"""eea_lex.py — EEA status of EU acts, EEA Joint Committee Decisions (JCDs)
and the current texts of the EEA Agreement, from EFTA (www.efta.int).

Self-contained CLI with no required third-party dependencies. PDF text
extraction uses the system `pdftotext` binary if present, otherwise `pypdf`.

www.efta.int is behind a Cloudflare challenge that is applied to every
User-Agent starting with "Mozilla/"; an honest tool UA gets the real pages
(probes 2026-10-23, docs/eea-lex.md). So the script always sends its own UA,
waits a second between requests to the site, follows at most 3 redirects
and treats a page that redirects to itself (proposal factsheets) as not
found. A challenge ends the run with exit code 3 and a BLOCKED message;
SKILL.md then switches to the browser route.

Cache layout (under the resolved cache dir):

  facets.json                       # EEA-Lex search facets (status, annex, ...)
  lists/index.json                  # yearly JCD list URLs
  lists/<YYYY>.pdf / .txt           # yearly list of adopted JCDs
  jcd/<YYYY>/<NNN>-<YYYY><l>.pdf    # JCD PDFs (l = '', g, i, n) and .txt
  agreement/index.json              # main part, annex and protocol URLs
  agreement/<part>.pdf / .txt       # current EEA Agreement texts
  art103/awaited.pdf / .txt         # JCDs awaiting constitutional requirements

All text files are UTF-8; writes are atomic (temp file + rename).
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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
USER_AGENT = f"eea-lex-skill/{VERSION} (+https://github.com/StianOby/claude-legal-tools)"
BASE = "https://www.efta.int"
LEX = f"{BASE}/eea-lex"
FILES = f"{BASE}/sites/default/files/documents/legal-texts/eea/other-legal-documents"
JCD_LISTS_PAGE = f"{BASE}/about-efta/legal-documents/adopted-joint-committee-decisions/105051"
LEGAL_TEXTS_PAGE = f"{BASE}/about-efta/legal-documents/eea-legal-texts"
ANNEXES_PAGE = f"{BASE}/about-efta/legal-documents/eea-legal-texts/annexes-agreement"
PROTOCOLS_PAGE = f"{BASE}/about-efta/legal-documents/adopted-joint-committee-decisions/105046"
AWAITED_PDF = f"{FILES}/list-of-awaited-notifications/list-awaited-notifications.pdf"
SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"

DAY = 24 * 3600
# Seconds between two requests to www.efta.int.
POLITE_DELAY = 1.0
MAX_REDIRECTS = 3

JCD_LANGS = {"EN": ("English", ""), "DE": ("German", "g"), "IS": ("Icelandic", "i"), "NO": ("Norwegian", "n")}
FLAGS = {"eu": "EU", "is": "Iceland", "li": "Liechtenstein", "no": "Norway"}
STATES = {"IS": "Iceland", "FL": "Liechtenstein", "N": "Norway"}


class NotFound(Exception):
    pass


class Challenged(Exception):
    pass


# ---------------------------------------------------------------------------
# Cache directory and file helpers

def cache_dir() -> Path:
    if env := os.environ.get("EEA_LEX_CACHE_DIR"):
        p = Path(env)
    elif env := os.environ.get("XDG_CACHE_HOME"):
        p = Path(env) / "eea-lex"
    elif sys.platform == "win32" and (la := os.environ.get("LOCALAPPDATA")):
        p = Path(la) / "eea-lex"
    else:
        p = Path.home() / ".cache" / "eea-lex"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def _write_bytes(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def _has_content(p: Path) -> bool:
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


def _age(p: Path) -> float:
    try:
        return time.time() - p.stat().st_mtime
    except OSError:
        return float("inf")


# ---------------------------------------------------------------------------
# HTTP

class _Redirects(urllib.request.HTTPRedirectHandler):
    """At most MAX_REDIRECTS hops; a page that redirects to itself is not
    found. Proposal factsheets (/eea-lex/<node id>) do that, and following
    the loop once ended in a 429."""
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl.split("#")[0] == req.full_url.split("#")[0]:
            raise NotFound(f"{req.full_url} redirects to itself")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Redirects)
_last_request = 0.0


def is_challenge(code: int, headers, body: bytes) -> bool:
    if code == 403 and headers is not None and headers.get("cf-mitigated"):
        return True
    return code in (403, 503) and (b"Just a moment" in body[:5000] or b"challenge-platform" in body[:20000])


def _request(url: str, *, accept: str = "*/*", timeout: int = 60) -> bytes:
    global _last_request
    polite = url.startswith(BASE)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(2):
        if polite and (wait := POLITE_DELAY - (time.time() - _last_request)) > 0:
            time.sleep(wait)
        try:
            with _OPENER.open(req, timeout=timeout) as resp:
                data = resp.read()
            if polite and b"<title>Just a moment" in data[:3000]:
                raise Challenged(url)
            return data
        except urllib.error.HTTPError as e:
            body = e.read() or b""
            if is_challenge(e.code, e.headers, body):
                raise Challenged(url)
            if e.code in (404, 410):
                raise NotFound(url)
            if e.code in (429, 502, 503, 504) and attempt == 0:
                time.sleep(15 if e.code == 429 else 3)
                continue
            raise
        finally:
            if polite:
                _last_request = time.time()
    raise AssertionError("unreachable")


def fetch_text(url: str) -> str:
    return _request(url, accept="text/html,application/xhtml+xml").decode("utf-8", errors="replace")


def cached_file(p: Path, url: str, max_age: float, *, refresh: bool = False) -> Path:
    """The file at `url`, cached at `p` for `max_age` seconds. When a refresh
    fails on the network, an older copy is used with a note on stderr."""
    if not refresh and _has_content(p) and _age(p) < max_age:
        return p
    try:
        _write_bytes(p, _request(url, accept="application/pdf,text/html,*/*", timeout=180))
    except (urllib.error.URLError, TimeoutError) as e:
        if not _has_content(p):
            raise
        stamp = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        print(f"[note] could not refresh {url} ({e}); using the copy from {stamp}", file=sys.stderr)
    return p


# ---------------------------------------------------------------------------
# PDF text

def extract_pdf_text(pdf: Path) -> str | None:
    """Text of a PDF with pages separated by form feeds, cached in <pdf>.txt
    until the PDF changes. pdftotext -raw keeps the line order the parsers
    below expect; pypdf is the fallback."""
    txt = pdf.with_suffix(".txt")
    if _has_content(txt) and txt.stat().st_mtime >= pdf.stat().st_mtime:
        return _read(txt)
    text = None
    if shutil.which("pdftotext"):
        subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), str(txt)], check=False,
                       stderr=subprocess.DEVNULL)
        if _has_content(txt):
            text = _read(txt)
    if text is None:
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(str(pdf))
            text = "\f".join(page.extract_text() or "" for page in reader.pages)
        except ModuleNotFoundError:
            return None
        except Exception as e:  # corrupt / encrypted PDF
            print(f"[pdf] pypdf failed on {pdf.name}: {e}", file=sys.stderr)
            return None
        if not text.strip():
            return None
        _write(txt, text)
    return text


# ---------------------------------------------------------------------------
# Small parsing helpers

def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _abs(url: str) -> str:
    return urllib.parse.urljoin(BASE + "/", html.unescape(url).strip())


def iso_date(d: str) -> str:
    """'06/02/2026' or '06.02.2026' -> '2026-02-06'; anything else unchanged."""
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", d.strip())
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else d.strip()


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _full_year(y: int) -> int:
    if y >= 100:
        return y
    return 1900 + y if y >= 50 else 2000 + y


def roman(n: int) -> str:
    out = ""
    for v, s in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


# ---------------------------------------------------------------------------
# Identifiers

CELEX_RE = re.compile(r"^\s*([0-9])(\d{4})([A-Z]{1,2})(\d{4})(\(\d+\))?\s*$", re.IGNORECASE)
_ACT_TYPES = (("directive", "L"), ("regulation", "R"), ("decision", "D"), ("recommendation", "H"))


def act_to_celex(s: str) -> str | None:
    """CELEX for an EU act cited by type and number ('Regulation 2016/679',
    'Directive 95/46/EC', 'Regulation (EC) No 1234/2007'), or None.

    Directives are year/number throughout; regulations and decisions are
    number/year before 2015 ('No 1234/2007') and year/number since."""
    low = s.lower()
    letter = next((c for word, c in _ACT_TYPES if word in low), None)
    m = re.search(r"(?<![\d/])(\d{1,4})/(\d{1,4})(?![\d])", s)
    if not letter or not m:
        return None
    a, b = m.group(1), m.group(2)
    if letter == "L":
        year, num = a, b
    elif re.search(r"\bno\.?\s*$", low[:m.start()]):
        num, year = a, b
    elif len(a) == 4 and 1952 <= int(a) <= datetime.now().year + 1:
        year, num = a, b
    elif len(b) == 4 or (len(a) > 2 and len(b) == 2):
        num, year = a, b
    else:
        year, num = a, b
    return f"3{_full_year(int(year))}{letter}{int(num):04d}"


def parse_jcd_number(s: str) -> tuple[int, int]:
    m = re.search(r"(\d{1,3})\s*/\s*(\d{4}|\d{2})(?!\d)", s)
    if not m:
        raise SystemExit(f"Cannot read a JCD number from {s!r}; write it as NNN/YYYY, e.g. 154/2018.")
    return int(m.group(1)), _full_year(int(m.group(2)))


# ---------------------------------------------------------------------------
# Factsheet

def parse_factsheet(raw: str, url: str = "") -> dict:
    out: dict[str, Any] = {"url": url}
    if m := re.search(r"<h1[^>]*>\s*Factsheet\s*-\s*([^<]+?)\s*</h1>", raw):
        out["id"] = m.group(1).strip()
    if m := re.search(r'field--name-field-english-title.*?abstract-text">(.*?)</div>', raw, re.S):
        out["title"] = _strip_html(m.group(1))
    out["status"] = ""
    if m := re.search(r'timeline-item active">.*?timeline-text">(.*?)</div>', raw, re.S):
        out["status"] = _strip_html(m.group(1))
    out["stages"] = [_strip_html(x) for x in re.findall(r'timeline-text">(.*?)</div>', raw, re.S)]

    docs_at = raw.find('class="lex-documents-section"')
    hist_at = raw.find('class="lex-history-section"')
    end_at = raw.find('class="disclaimer"')
    head = raw[:docs_at if docs_at > 0 else hist_at if hist_at > 0 else len(raw)]
    fields: dict[str, list[str]] = {}
    for m in re.finditer(r'<div class="field-label">(.*?)</div>(.*?)(?=<div class="field-label">|\Z)', head, re.S):
        items = [_strip_html(x) for x in re.findall(r'<div\s+class="field-item">(.*?)</div>', m.group(2), re.S)]
        fields[_strip_html(m.group(1))] = [x for x in items if x]
    out["legal_status"] = " ".join(fields.get("Legal status", []))
    out["areas"] = fields.get("Area (EEA Agreement)", [])
    out["protocols"] = next((v for k, v in fields.items() if k.lower().startswith("protocol")), [])
    out["jcd"] = " ".join(fields.get("Joint committee decision (JCD)", []))
    out["in_force_in_eea"] = " ".join(fields.get("In force in the EEA", []))
    out["other_fields"] = {k: v for k, v in fields.items() if k not in (
        "Legal status", "Area (EEA Agreement)", "Joint committee decision (JCD)", "In force in the EEA")
        and not k.lower().startswith("protocol")}

    def links(fragment: str) -> list[dict]:
        return [{"label": _strip_html(t), "url": _abs(u)}
                for u, t in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', fragment, re.S)]

    documents = []
    if docs_at > 0:
        section = raw[docs_at:hist_at if hist_at > docs_at else end_at if end_at > 0 else len(raw)]
        for block in section.split('data-component-id="storyworx:lex-document"')[1:]:
            flag = re.search(r'class="flag-(\w+)"', block)
            desc = re.search(r'lex-document-description">(.*?)</div>', block, re.S)
            code = flag.group(1) if flag else ""
            documents.append({"flag": code, "language": FLAGS.get(code, code),
                              "title": _strip_html(desc.group(1)) if desc else "",
                              "links": links(block)})
    out["documents"] = documents

    history = []
    if hist_at > 0:
        section = raw[hist_at:end_at if end_at > hist_at else len(raw)]
        for block in section.split('data-component-id="storyworx:lex-history-item"')[1:]:
            d = re.search(r'metadata__date">(.*?)<', block, re.S)
            lab = re.search(r'metadata__label">(.*?)</span>', block, re.S)
            history.append({"date": iso_date(_strip_html(d.group(1))) if d else "",
                            "event": _strip_html(lab.group(1)) if lab else "",
                            "links": links(block)})
    out["history"] = history
    return out


def factsheet_summary(fs: dict) -> str:
    lines = [f"{fs.get('id', '?')} — {fs.get('title', '')}", "=" * 70,
             f"EEA-Lex status:  {fs.get('status') or '-'}",
             f"Legal status:    {fs.get('legal_status') or '-'}"]
    if fs.get("areas"):
        lines.append(f"Area:            {'; '.join(fs['areas'])}")
    if fs.get("protocols"):
        lines.append(f"Protocol:        {'; '.join(fs['protocols'])}")
    lines += [f"JCD:             {fs.get('jcd') or '-'}",
              f"In force in EEA: {fs.get('in_force_in_eea') or '-'}"]
    for k, v in (fs.get("other_fields") or {}).items():
        lines.append(f"{k}: {'; '.join(v)}")
    lines.append(f"URL:             {fs.get('url', '')}")
    if fs.get("history"):
        lines += ["", "History (as listed, newest first):"]
        for h in fs["history"]:
            lines.append(f"  {h['date']:10}  {h['event']}")
            for ln in h["links"]:
                lines.append(f"              {ln['label']}  <{ln['url']}>")
    if fs.get("documents"):
        lines += ["", "Documents:"]
        for d in fs["documents"]:
            lines.append(f"  [{d['language']}] {d['title']}")
            for ln in d["links"]:
                lines.append(f"      {ln['label']}  <{ln['url']}>")
    return "\n".join(lines) + "\n"


def fetch_factsheet(celex: str) -> dict:
    url = f"{LEX}/{celex.lower()}"
    return parse_factsheet(fetch_text(url), url)


# ---------------------------------------------------------------------------
# Listing (search) and facets

def parse_facets(raw: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for m in re.finditer(r'href="/eea-lex\?f%5B0%5D=([a-z_]+)%3A([^"&]+)"[^>]*>(.*?)</a>', raw, re.S):
        facet, fid, label = m.group(1), urllib.parse.unquote(m.group(2)), _strip_html(m.group(3))
        cm = re.fullmatch(r"(.*?)\s*\((\d+)\)", label)
        entry = {"id": fid, "label": cm.group(1) if cm else label, "count": int(cm.group(2)) if cm else None}
        if entry not in out.setdefault(facet, []):
            out[facet].append(entry)
    return out


def get_facets(refresh: bool = False) -> dict[str, list[dict]]:
    p = cache_dir() / "facets.json"
    if not refresh and _has_content(p) and _age(p) < DAY:
        return json.loads(_read(p))
    facets = parse_facets(fetch_text(LEX))
    if not facets.get("case_status"):
        raise SystemExit("Could not read the search facets from the EEA-Lex page; the page layout may have changed.")
    _write(p, json.dumps(facets, indent=1, ensure_ascii=False))
    return facets


STATUS_ALIASES = {
    "proposed": "proposed act", "proposal": "proposed act",
    "scrutiny": "under scrutiny",
    "draft": "draft joint committee decision",
    "pending": "entry into force of joint committee decision",
    "in-force": "and in force", "inforce": "and in force", "in force": "and in force",
    "incorporated": "and in force",
    "no-longer": "no longer in force", "repealed": "no longer in force", "expired": "no longer in force",
}


def _pick(entries: list[dict], match, what: str, given: str) -> dict:
    hits = [e for e in entries if match(e)]
    if len(hits) == 1:
        return hits[0]
    choices = "\n".join(f"  {e['label']}" for e in entries)
    if not hits:
        raise SystemExit(f"No {what} matches {given!r}. Choices:\n{choices}")
    raise SystemExit(f"{given!r} matches several {what} values:\n" + "\n".join(f"  {e['label']}" for e in hits))


def resolve_filters(facets: dict, *, status=None, annex=None, protocol=None, type_=None, year=None) -> list[tuple[str, str]]:
    out = []
    if status:
        want = STATUS_ALIASES.get(status.lower().strip(), status.lower().strip())
        e = _pick(facets.get("case_status", []), lambda e: want in e["label"].lower(), "status", status)
        out.append(("case_status", e["id"]))
    if annex:
        code = annex.strip().upper().removeprefix("ANNEX").strip()
        head, _, sub = code.partition(".")
        if head.isdigit():
            head = roman(int(head))
        code = f"{head}.{sub}" if sub else head
        e = _pick(facets.get("area_agreement", []), lambda e: e["label"].upper().startswith(code + " "),
                  "annex/area", annex)
        out.append(("area_agreement", e["id"]))
    if protocol:
        num = re.sub(r"\D", "", protocol)

        def pmatch(e):
            lead = re.match(r"(\d+)", e["label"])
            return bool(lead and num and int(lead.group(1)) == int(num))
        e = _pick(facets.get("protocol", []), pmatch, "protocol", protocol)
        out.append(("protocol", e["id"]))
    if type_:
        e = _pick(facets.get("celex_type", []), lambda e: e["label"].lower() == type_.lower(), "act type", type_)
        out.append(("celex_type", e["id"]))
    if year:
        out.append(("adoption_date_eu", str(year)))
    return out


SORTS = {
    "relevance": "rel_DESC", "jcd": "decision_DESC", "jcd-asc": "decision_ASC",
    "adopted": "adoption_DESC", "adopted-asc": "adoption_ASC",
    "proposal": "proposal_DESC", "proposal-asc": "proposal_ASC",
    "entry": "entry_DESC", "entry-asc": "entry_ASC",
}
PER_PAGE = (6, 12, 24, 36, 48, 60)


def search_url(keyword: str | None, filters: list[tuple[str, str]], *, sort: str | None = None,
               per_page: int = 24, page: int = 0) -> str:
    params: list[tuple[str, str]] = []
    if keyword:
        params.append(("keyword", keyword))
    for i, (facet, fid) in enumerate(filters):
        params.append((f"f[{i}]", f"{facet}:{fid}"))
    per = min(PER_PAGE, key=lambda n: (abs(n - per_page), -n))
    params.append(("items_per_page", str(per)))
    s = SORTS.get(sort or "", sort) if sort else ("rel_DESC" if keyword else "decision_DESC")
    params.append(("sort_bef_combine", s))
    if page:
        params.append(("page", str(page)))
    return f"{LEX}?{urllib.parse.urlencode(params)}"


def parse_listing(raw: str) -> dict:
    total = pages = 0
    if m := re.search(r'pagination-count">\s*(\d+) items? / (\d+) pages?', raw):
        total, pages = int(m.group(1)), int(m.group(2))
    start = raw.find("<h2>Search results</h2>")
    end = raw.find("view-pagination_bottom", start)
    body = raw[start:end] if start >= 0 else ""
    items = []
    for card in body.split('<div class="views-row">')[1:]:
        href = re.search(r'href="/eea-lex/([^"#]+)"', card)
        if not href:
            continue
        ident = href.group(1)
        sub = re.search(r'lex-teaser-subtitle">(.*?)</h5>', card, re.S)
        titles = {}
        for flag, desc in re.findall(r'class="flag-(\w+)"></div>\s*<div class="lex-teaser-description">(.*?)</div>',
                                     card, re.S):
            titles[flag] = _strip_html(desc)
        is_celex = bool(CELEX_RE.match(ident))
        items.append({"id": ident.upper() if is_celex else ident, "celex": is_celex,
                      "document": _strip_html(sub.group(1)) if sub else "",
                      "title": titles.get("eu", ""), "title_no": titles.get("no", ""),
                      "url": f"{LEX}/{ident}"})
    if not total and not items and "views-row" not in raw and "Search results" not in raw:
        if 'view-id-lex_search' not in raw:
            raise SystemExit("The EEA-Lex result page has an unexpected layout; open the URL in the browser.")
    return {"total": total, "pages": pages, "items": items}


def search(keyword=None, filters=(), **kw) -> dict:
    url = search_url(keyword, list(filters), **kw)
    res = parse_listing(fetch_text(url))
    res["url"] = url
    return res


def _celex_from_keyword(s: str) -> tuple[str | None, list[dict]]:
    """Find the act a free-text identifier names, through the keyword
    search: the card whose EU title starts with the cited number."""
    res = search(s, [], per_page=24)
    num = re.search(r"\d{1,4}/\d{1,4}", s)
    hits = []
    for it in res["items"]:
        head = it["title"][:120]
        if num and re.search(rf"(?<![\d/]){re.escape(num.group(0))}(?![\d/])", head) and it["celex"]:
            hits.append(it)
    if len(hits) == 1:
        return hits[0]["id"], res["items"]
    return None, res["items"]


# ---------------------------------------------------------------------------
# JCD lists

def jcd_list_urls(refresh: bool = False) -> dict[str, str]:
    p = cache_dir() / "lists" / "index.json"
    if not refresh and _has_content(p) and _age(p) < DAY:
        return json.loads(_read(p))
    raw = fetch_text(JCD_LISTS_PAGE)
    urls = {}
    for u, t in re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', raw, re.S | re.I):
        m = re.match(r"(\d{4})\s+List", _strip_html(t))
        if m:
            urls[m.group(1)] = _abs(u)
    if not urls:
        raise SystemExit(f"No yearly JCD lists found on {JCD_LISTS_PAGE}; the page layout may have changed.")
    _write(p, json.dumps(urls, indent=1))
    return urls


def jcd_list_text(year: int, refresh: bool = False) -> tuple[str, str] | None:
    urls = jcd_list_urls(refresh)
    url = urls.get(str(year))
    if not url:
        return None
    # The current year's list grows after every Joint Committee meeting.
    max_age = DAY if year >= datetime.now().year - 1 else 30 * DAY
    pdf = cached_file(cache_dir() / "lists" / f"{year}.pdf", url, max_age, refresh=refresh)
    text = extract_pdf_text(pdf)
    if text is None:
        raise SystemExit("Could not extract text from the JCD list: install poppler-utils (pdftotext) or pypdf.")
    return text, url


_DATE = r"\d{2}/\d{2}/\d{4}"
# '/+': the 2025 list prints JCD 232 as "232//2025".
_ROW_RE = re.compile(rf"^(\d+) (\d{{3}})/+(\d{{4}}) ({_DATE})(?: ({_DATE}))?(?: (.*))?$")
# Five digits: decisions of the Administrative Commission for social
# security (32024D06842).
_CELEX_LINE = re.compile(r"^([0-9]\d{4}[A-Z]{1,2}\d{4,5}(?:\(\d+\))?)(?:\s+(.*))?$")
_REPORT_DATE = re.compile(r"^\d{1,2} [A-Z][a-z]+ \d{4}$")


def _join_row_cells(text: str) -> list[str]:
    """Stripped lines, with the cells that start a row on one line.
    pdftotext -raw already gives '1 001/2026 06/02/2026 07/02/2026 OJ L,';
    pypdf gives each cell on its own line ('1', '001/2026', '06/02/2026',
    ...) and splits the heading 'No EEA JCD' after 'No'."""
    raw = [ln.strip() for ln in text.replace("\f", "\n").splitlines()]
    out, i = [], 0
    while i < len(raw):
        ln = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if ln == "No" and nxt.startswith("EEA JCD"):
            out.append(f"No {nxt}")
            i += 2
            continue
        if ln.isdigit() and re.fullmatch(r"\d{3}/+\d{4}", nxt):
            parts = [ln, nxt]
            i += 2
            while i < len(raw) and len(parts) < 4 and re.fullmatch(_DATE, raw[i]):
                parts.append(raw[i])
                i += 1
            out.append(" ".join(parts))
            continue
        out.append(ln)
        i += 1
    return out


def _strip_report_noise(text: str, header_end) -> tuple[list[str], dict]:
    """Lines of an EFTA report PDF without its page furniture: the column
    headings (from 'No EEA JCD' to the line header_end accepts), the
    report-title block (from 'Period starts at:' to 'Report no:'), the page
    number before 'Report no:', subcommittee headings and totals."""
    meta: dict[str, Any] = {}
    out: list[str] = []
    skip = None
    for line in _join_row_cells(text):
        if skip == "header":
            if header_end(line):
                skip = None
            continue
        if skip == "title":
            # Reports before ~2015 have no 'Report no:' line; the next
            # page's column headings end the block instead.
            if line.startswith("No EEA JCD"):
                skip = "header"
                continue
            if _REPORT_DATE.match(line):
                meta.setdefault("report_date", line)
            elif re.fullmatch(_DATE, line):
                meta.setdefault("period", []).append(iso_date(line))
            if line.startswith("Report no:"):
                skip = None
            continue
        if not line:
            continue
        if line.startswith("No EEA JCD"):
            skip = "header"
            continue
        if line.startswith("Period starts at:"):
            skip = "title"
            continue
        if line.startswith("Report no:"):
            if out and out[-1].isdigit():
                out.pop()
            continue
        if line.startswith("Subcommittee") or line.startswith("No Subcommittee") or line.startswith("Total number of"):
            if line.startswith("Total number of"):
                meta.setdefault("totals", []).append(line)
            continue
        out.append(line)
    return out, meta


_PUB_FRAGMENT = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4}|^p\. ?\d|^\d+, )")
_ACT_TITLE_START = re.compile(r"^(?:Commission|Council|Regulation|Directive|Decision|Delegated|Implementing)\b")


def parse_jcd_list(text: str) -> dict:
    """Rows of a yearly list of adopted JCDs (EFTA report 5.1, 2010 on).

    Each row: jcd, adoption, eif (confirmed entry into force, may be empty),
    oj and supplement (publication refs, empty until published), annex
    (annex or protocol amended) and acts [{celex, title, compliance_eu}]."""
    lines, meta = _strip_report_noise(text, lambda ln: ln == "Date EU")
    rows: list[dict] = []
    row = None
    mode = None
    for line in lines:
        if m := _ROW_RE.match(line):
            row = {"no": int(m.group(1)), "jcd": f"{int(m.group(2))}/{m.group(3)}",
                   "adoption": iso_date(m.group(4)), "eif": iso_date(m.group(5) or ""),
                   "oj": "", "supplement": "", "annex": "", "acts": []}
            rows.append(row)
            mode = None
            line = m.group(6) or ""
            if not line:
                continue
        if row is None:
            continue
        if cm := _CELEX_LINE.match(line):
            title = cm.group(2) or ""
            dm = re.search(rf"\s*({_DATE})$", title)
            row["acts"].append({"celex": cm.group(1), "title": title[:dm.start()] if dm else title,
                                "compliance_eu": iso_date(dm.group(1)) if dm else ""})
            mode = "act"
            continue
        if mode == "act":
            act = row["acts"][-1]
            if re.fullmatch(_DATE, line) and not act["compliance_eu"]:
                act["compliance_eu"] = iso_date(line)
            elif dm := re.search(rf"\s({_DATE})$", line):
                act["title"] = f"{act['title']} {line[:dm.start()]}".strip()
                act["compliance_eu"] = act["compliance_eu"] or iso_date(dm.group(1))
            else:
                act["title"] = f"{act['title']} {line}".strip()
            continue
        if mode == "annex" and _ACT_TITLE_START.match(line):
            # An act with no CELEX number yet (seen: a Commission decision
            # amending C(2015) 8005 in JCD 218/2026).
            dm = re.search(rf"\s*({_DATE})$", line)
            row["acts"].append({"celex": "", "title": line[:dm.start()] if dm else line,
                                "compliance_eu": iso_date(dm.group(1)) if dm else ""})
            mode = "act"
            continue
        if line.startswith("OJ"):
            mode = "oj"
        elif line.startswith("EEA Supplement"):
            mode = "supplement"
        elif line.startswith("Annex") or line.startswith("Protocol"):
            mode = "annex"
        elif mode == "annex" and _PUB_FRAGMENT.search(line):
            mode = "supplement" if row["supplement"] else "oj"
        if mode in ("oj", "supplement", "annex"):
            row[mode] = f"{row[mode]} {line}".strip()
    for r in rows:
        for k in ("oj", "supplement", "annex"):
            r[k] = re.sub(r"\s+", " ", r[k])
        for a in r["acts"]:
            a["title"] = re.sub(r"(\w)- (\w)", r"\1-\2", re.sub(r"\s+", " ", a["title"]))
    meta["rows"] = rows
    return meta


# ---------------------------------------------------------------------------
# JCD documents and Cellar

def jcd_pdf_url(n: int, year: int, lang: str = "EN") -> str:
    folder, suffix = JCD_LANGS[lang]
    return f"{FILES}/adopted-joint-committee-decisions/{year}%20-%20{folder}/{n:03d}-{year}{suffix}.pdf"


def get_jcd_pdf(n: int, year: int, lang: str = "EN", refresh: bool = False) -> tuple[Path, str]:
    url = jcd_pdf_url(n, year, lang)
    p = cache_dir() / "jcd" / str(year) / f"{n:03d}-{year}{JCD_LANGS[lang][1]}.pdf"
    return cached_file(p, url, 3650 * DAY, refresh=refresh), url


def jcd_pdf_header(text: str, n: int, year: int) -> dict:
    """Adoption date and title from the first page of an English JCD. The
    1990s decisions print the year with two digits ('No 10/95')."""
    flat = re.sub(r"\s+", " ", text[:4000])
    out = {}
    m = re.search(rf"No {n}/(?:{year}|{year % 100:02d}) of (\d{{1,2}}) ([A-Za-z]+) (\d{{4}}) (.*?)"
                  r"(?: THE EEA JOINT COMMITTEE|$)", flat)
    if m and m.group(2).lower() in _MONTHS:
        out["adoption"] = f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        out["title"] = f"Decision of the EEA Joint Committee {m.group(0).split(' THE EEA')[0]}".strip()
    return out


def sparql(query: str, timeout: int = 60) -> list:
    body = urllib.parse.urlencode({"query": query, "format": "application/sparql-results+json"}).encode()
    for wait in (2, 5, None):
        req = urllib.request.Request(SPARQL, data=body, headers={
            "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or wait is None:
                raise
        except (urllib.error.URLError, TimeoutError):
            if wait is None:
                raise
        time.sleep(wait)
    return []


def cellar_jcd(n: int, year: int, adoption: str) -> dict | None:
    """The JCD's Cellar record (CELEX 2YYYYD####, English title), found by
    its adoption date and the number in its title; None if Cellar has none
    yet. A query takes about 0.2 s (2026-10-23)."""
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title WHERE {{
  ?work cdm:work_date_document "{adoption}"^^<http://www.w3.org/2001/XMLSchema#date> ;
        cdm:resource_legal_id_celex ?celex .
  FILTER(STRSTARTS(STR(?celex), "2"))
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> ;
        cdm:expression_title ?title .
  FILTER(CONTAINS(STR(?title), "EEA Joint Committee"))
}}"""
    return match_cellar_title(sparql(q), n, year)


def match_cellar_title(bindings: list, n: int, year: int) -> dict | None:
    pat = re.compile(rf"\bNo\W{{0,3}}0*{n}/(?:{year}|{year % 100:02d})(?!\d)")
    for b in bindings:
        title = b["title"]["value"]
        if pat.search(title):
            return {"celex": b["celex"]["value"], "title": re.sub(r"\s+", " ", title.replace("\xa0", " "))}
    return None


def lookup_jcd(n: int, year: int, *, lang: str = "EN", text: bool = False, cellar: bool = True,
               refresh: bool = False) -> dict:
    out: dict[str, Any] = {"jcd": f"{n}/{year}", "pdf_url": jcd_pdf_url(n, year, lang), "notes": []}
    listed = jcd_list_text(year, refresh)
    if listed:
        ltext, lurl = listed
        out["list_url"] = lurl
        parsed = parse_jcd_list(ltext)
        out["list_report_date"] = parsed.get("report_date", "")
        row = next((r for r in parsed["rows"] if r["jcd"] == f"{n}/{year}"), None)
        if row:
            out.update({k: row[k] for k in ("adoption", "eif", "oj", "supplement", "annex", "acts")})
        elif not parsed["rows"]:
            # 1994-2005: a table whose columns pdftotext scrambles (a row
            # read for 11/2005 belonged to another decision), so it is not
            # quoted; the JCD's own PDF and Cellar give the facts.
            out["notes"].append(f"EFTA's {year} list has an older layout that is not read here; dates and "
                                "title come from the JCD itself. The list (PDF) has the publication refs.")
        else:
            out["notes"].append(f"Not in EFTA's {year} list of adopted JCDs (report of "
                                f"{out['list_report_date'] or 'unknown date'}); the list is updated "
                                "some weeks after each Joint Committee meeting.")
    else:
        out["notes"].append(f"EFTA has no list of adopted JCDs for {year}.")

    need_pdf = text or not out.get("adoption")
    if need_pdf:
        try:
            en_pdf, _ = get_jcd_pdf(n, year, "EN", refresh)
            en_text = extract_pdf_text(en_pdf) or ""
            head = jcd_pdf_header(en_text, n, year)
            out.setdefault("adoption", head.get("adoption", ""))
            if not out.get("adoption"):
                out["adoption"] = head.get("adoption", "")
            out["title"] = head.get("title", "")
        except NotFound:
            if not out.get("adoption"):
                raise SystemExit(f"No JCD {n}/{year} on www.efta.int: it is not in the {year} list and "
                                 f"there is no PDF at {jcd_pdf_url(n, year)}. It may not have been adopted yet.")
            out["notes"].append("EFTA's English PDF of this JCD was not found.")
    if text:
        try:
            pdf, url = get_jcd_pdf(n, year, lang, refresh)
            out["pdf"], out["pdf_url"] = str(pdf), url
            body = extract_pdf_text(pdf)
            out["text_file"] = str(pdf.with_suffix(".txt")) if body else ""
            if not body:
                out["notes"].append("Text extraction failed: install poppler-utils (pdftotext) or pypdf.")
        except NotFound:
            out["notes"].append(f"No {JCD_LANGS[lang][0]} PDF of this JCD on www.efta.int.")
            out["pdf_url"] = ""

    if cellar and out.get("adoption"):
        try:
            out["cellar"] = cellar_jcd(n, year, out["adoption"])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            out["cellar"] = None
            out["notes"].append(f"Cellar could not be asked ({e}); say that the OJ status is unchecked.")
            out["cellar_error"] = True
    return out


def jcd_summary(j: dict) -> str:
    lines = [f"EEA Joint Committee Decision No {j['jcd']}", "=" * 70]
    if j.get("title"):
        lines.append(f"Title:        {j['title']}")
    lines += [f"Adopted:      {j.get('adoption') or '-'}",
              f"Entry into force (confirmed): {j.get('eif') or '-'}"]
    if "oj" in j:
        # EFTA's yearly lists are regenerated irregularly (the 2025 list was
        # still the one of 5.12.2025 in October 2026), so an empty column
        # only means "not in the list"; Cellar below says whether it is out.
        none = f"(none in EFTA's list of {j.get('list_report_date') or '?'})"
        lines += [f"OJ:           {j['oj'] or none}",
                  f"EEA Suppl.:   {j['supplement'] or none}",
                  f"Amends:       {j.get('annex') or '-'}"]
    if j.get("acts"):
        lines.append("Acts incorporated or concerned:")
        for a in j["acts"]:
            lines.append(f"  {a['celex']}  {a['title']}" + (f"  (EU compliance date {a['compliance_eu']})"
                                                            if a.get("compliance_eu") else ""))
    if "cellar" in j:
        c = j["cellar"]
        if c:
            lines.append(f"In the OJ (Cellar): CELEX {c['celex']} — {c['title']}")
            lines.append("  -> authentic text: use the eurlex skill with this CELEX number.")
        elif not j.get("cellar_error"):
            lines.append("Cellar: no record yet -> not yet in the OJ on EUR-Lex; the EFTA PDF below is the text to use.")
    lines.append(f"EFTA PDF:     {j.get('pdf_url') or '-'}")
    if j.get("text_file"):
        lines.append(f"TEXT:         {j['text_file']}")
    if j.get("list_url"):
        dated = f" (report of {j['list_report_date']})" if j.get("list_report_date") else ""
        lines.append(f"Source list:  {j['list_url']}{dated}")
    for n in j.get("notes", []):
        lines.append(f"[note] {n}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# EEA Agreement texts

def agreement_index(refresh: bool = False) -> dict:
    p = cache_dir() / "agreement" / "index.json"
    if not refresh and _has_content(p) and _age(p) < DAY:
        return json.loads(_read(p))
    idx: dict[str, Any] = {"main": None, "annexes": {}, "protocols": {}}
    raw = fetch_text(LEGAL_TEXTS_PAGE)
    for u, t in re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', raw, re.S | re.I):
        if "Main%20Text" in u or "Main Text" in u:
            idx["main"] = {"url": _abs(u), "title": "Main part of the EEA Agreement"}
            break
    raw = fetch_text(ANNEXES_PAGE)
    for u, t in re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', raw, re.S | re.I):
        if m := re.search(r"/annex(\d+)([a-z]?)\.pdf$", u, re.I):
            idx["annexes"][f"{int(m.group(1))}{m.group(2).lower()}"] = {"url": _abs(u), "title": _strip_html(t)}
    raw = fetch_text(PROTOCOLS_PAGE)
    for u, t in re.findall(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', raw, re.S | re.I):
        label = _strip_html(t)
        if m := re.match(r"Protocol (\d+)([a-z]?)\b", label, re.I):
            idx["protocols"].setdefault(f"{int(m.group(1))}{m.group(2).lower()}", {"url": _abs(u), "title": label})
    if not idx["annexes"] or not idx["protocols"]:
        raise SystemExit("Could not read the annex/protocol links from www.efta.int; the pages may have changed.")
    _write(p, json.dumps(idx, indent=1, ensure_ascii=False))
    return idx


def _roman_to_int(s: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50}
    s = s.upper()
    if not s or any(c not in vals for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


def agreement_parts(idx: dict, part: str, number: str | None) -> list[tuple[str, dict]]:
    if part == "main":
        if not idx.get("main"):
            raise SystemExit("The main text link was not found on the EEA legal texts page.")
        return [("main", idx["main"])]
    if not number:
        raise SystemExit(f"Give the {part} number, e.g. `agreement {part} 11`.")
    m = re.fullmatch(r"\s*([0-9]+|[IVXL]+)\s*([a-c]?)\s*", number, re.I)
    if not m:
        raise SystemExit(f"Cannot read {part} number {number!r}.")
    n = int(m.group(1)) if m.group(1).isdigit() else _roman_to_int(m.group(1))
    sub = m.group(2).lower()
    table = idx["annexes" if part == "annex" else "protocols"]
    if sub or f"{n}" in table:
        key = f"{n}{sub}"
        if key not in table:
            raise SystemExit(f"No {part} {number} on www.efta.int. Available: {', '.join(table)}")
        return [(f"{part}{key}", table[key])]
    keys = [k for k in table if re.fullmatch(rf"{n}[a-z]", k)]
    if not keys:
        raise SystemExit(f"No {part} {number} on www.efta.int. Available: {', '.join(table)}")
    return [(f"{part}{k}", table[k]) for k in keys]


_PAGE_HEADER = re.compile(r"^(?:Updated\s+)?\d{1,2}\.\d{1,2}\.\d{4}\s*-?\s*EEA AGREEMENT")


def version_date(text: str) -> str:
    m = re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", text[:300])
    return iso_date(m.group(0)) if m else ""


def celex_pattern(celex: str) -> re.Pattern:
    """How the annexes print a CELEX number: '32016 R 0679' since 2000,
    '387 L 0372' before."""
    m = CELEX_RE.match(celex)
    if not m:
        raise ValueError(celex)
    sector, year, typ, num = m.group(1), m.group(2), m.group(3).upper(), m.group(4)
    return re.compile(rf"(?<!\d){sector}\s?(?:{year}|{year[2:]})\s*{typ}\s*{num}(?!\d)")


def phrase_re(q: str) -> re.Pattern:
    """q in text that keeps the PDF's line breaks: a space matches any
    whitespace, and a word may break at a hyphen and a line end."""
    brk = r"(?:-[ \t]*\n\s*)?"
    parts = []
    for word in q.split():
        chars = [r"-\s*" if c == "-" else re.escape(c) for c in word]
        parts.append(brk.join(chars))
    return re.compile(r"\s+".join(parts), re.IGNORECASE)


_ENTRY_START = re.compile(r"^(?:\d+[a-z]*\.(?:\{\d+\})?\s|\[\s*\]|[A-Z]{1,4}\.\s|CHAPTER|PART|ACTS OF WHICH)")


def find_in_text(text: str, query: str, max_hits: int = 10) -> list[dict]:
    """Hits for a CELEX number (the whole annex entry, with the footnotes it
    cites, which say which JCD inserted or amended it) or a phrase (a few
    lines around each hit). Pages are counted from the PDF's form feeds."""
    is_celex = bool(CELEX_RE.match(query))
    pat = celex_pattern(query) if is_celex else phrase_re(query)
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    hits: list[dict] = []
    seen_lines: set[int] = set()
    for m in pat.finditer(text):
        li = max(i for i, o in enumerate(offsets) if o <= m.start())
        if li in seen_lines:
            continue
        page = text.count("\f", 0, m.start()) + 1
        if is_celex:
            start = li
            while start > 0 and not _ENTRY_START.match(lines[start].lstrip("\f")) and li - start < 6 \
                    and not lines[start].lstrip().startswith("-"):
                start -= 1
            # Footnotes sit at the foot of each page, up to the next page
            # header; they are left out here and quoted separately below.
            excerpt, in_notes = [], False
            for j in range(start, min(len(lines), li + 60)):
                ln = lines[j].lstrip("\f")
                if _PAGE_HEADER.match(ln):
                    in_notes = False
                    continue
                if re.match(r"^\{\d+\}\s", ln):
                    in_notes = True
                if in_notes:
                    continue
                # The entry runs to the next numbered point; its "as amended
                # by:" indents and adaptations belong to it.
                if j > li and _ENTRY_START.match(ln):
                    break
                excerpt.append(ln)
            seen_lines.update(range(start, li + 1))
        else:
            excerpt = [lines[j].lstrip("\f") for j in range(max(0, li - 2), min(len(lines), li + 3))]
            seen_lines.add(li)
        marks = []
        for x in re.findall(r"\{(\d+)\}", "\n".join(excerpt)):
            if x not in marks:
                marks.append(x)
        hits.append({"page": page, "excerpt": "\n".join(excerpt).strip(),
                     "footnotes": {x: footnote(lines, x) for x in marks}})
        if len(hits) >= max_hits:
            break
    return hits


def footnote(lines: list[str], mark: str) -> str:
    out = []
    for i, ln in enumerate(lines):
        ln = ln.lstrip("\f")
        if ln.startswith(f"{{{mark}}} "):
            out.append(ln)
            for nxt in lines[i + 1:i + 6]:
                nxt = nxt.lstrip("\f")
                if not nxt.strip() or nxt.startswith("{") or _PAGE_HEADER.match(nxt) or _ENTRY_START.match(nxt):
                    break
                out.append(nxt)
            break
    return " ".join(out)


def get_agreement(part: str, number: str | None, find: str | None, max_hits: int, refresh: bool) -> list[dict]:
    idx = agreement_index(refresh)
    results = []
    for key, info in agreement_parts(idx, part, number):
        pdf = cached_file(cache_dir() / "agreement" / f"{key}.pdf", info["url"], DAY, refresh=refresh)
        text = extract_pdf_text(pdf)
        r = {"part": key, "title": info["title"], "url": info["url"], "pdf": str(pdf),
             "text_file": str(pdf.with_suffix(".txt")) if text else "",
             "version_date": version_date(text or "")}
        if find and text:
            r["query"] = find
            r["hits"] = find_in_text(text, find.strip().upper() if CELEX_RE.match(find) else find, max_hits)
        results.append(r)
    return results


def agreement_summary(results: list[dict]) -> str:
    lines = []
    for r in results:
        lines += [f"{r['part']}: {r['title']}", f"  Version (page header): {r['version_date'] or '?'}",
                  f"  URL:  {r['url']}", f"  TEXT: {r['text_file'] or '(extraction failed: install pdftotext or pypdf)'}"]
        if "hits" in r:
            if not r["hits"]:
                lines.append(f"  No match for {r['query']!r}.")
            for h in r["hits"]:
                lines.append(f"  --- p. {h['page']}")
                lines += [f"  {x}" for x in h["excerpt"].splitlines()]
                for mark, note in h["footnotes"].items():
                    if note:
                        lines.append(f"    footnote {note}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Art. 103: JCDs awaiting constitutional requirements

_AWAIT_ROW = re.compile(rf"^(\d+) (\d{{3}})/+(\d{{4}}) ({_DATE}) ({_DATE})(?: (.*))?$")


def parse_awaited(text: str) -> dict:
    """Rows of EFTA report 5.2.2: JCDs whose entry into force waits for at
    least one EEA EFTA State's constitutional requirements (Art. 103 EEA).

    Each row: jcd, adoption, six_month_expiry, states [{state, date}] (the
    list's 'Date of delay' column, paired with the states when the counts
    agree), annex, acts [celex]."""
    lines, meta = _strip_report_noise(text, lambda ln: ln.endswith("Celex No"))
    rows, cur = [], None
    for line in lines:
        if m := _AWAIT_ROW.match(line):
            cur = {"no": int(m.group(1)), "jcd": f"{int(m.group(2))}/{m.group(3)}",
                   "adoption": iso_date(m.group(4)), "six_month_expiry": iso_date(m.group(5)),
                   "_pre": [], "annex": "", "acts": []}
            rows.append(cur)
            line = m.group(6) or ""
            if not line:
                continue
        if cur is None:
            continue
        if _CELEX_LINE.match(line) and " " not in line:
            cur["acts"].append(line)
            continue
        if cur["acts"]:
            continue
        am = re.search(r"\b(Annex|Protocol)\b", line)
        if cur["annex"]:
            cur["annex"] = f"{cur['annex']} {line}"
        elif am:
            cur["_pre"].append(line[:am.start()])
            cur["annex"] = line[am.start():]
        else:
            cur["_pre"].append(line)
    for r in rows:
        pre = " ".join(r.pop("_pre"))
        states = re.findall(r"\b(IS|FL|N)\b", pre)
        dates = [iso_date(d) for d in re.findall(_DATE, pre)]
        if len(dates) == len(states):
            r["states"] = [{"state": s, "name": STATES[s], "date_of_delay": d} for s, d in zip(states, dates)]
        else:
            r["states"] = [{"state": s, "name": STATES[s], "date_of_delay": ""} for s in states]
            if dates:
                r["dates_of_delay_unpaired"] = dates
        r["annex"] = r["annex"].strip()
    meta["rows"] = rows
    return meta


_STATE_ALIASES = {"is": "IS", "iceland": "IS", "island": "IS", "li": "FL", "fl": "FL", "liechtenstein": "FL",
                  "no": "N", "n": "N", "norway": "N", "norge": "N"}


def cmd_pending103(args) -> None:
    pdf = cached_file(cache_dir() / "art103" / "awaited.pdf", AWAITED_PDF, 6 * 3600, refresh=args.refresh)
    text = extract_pdf_text(pdf)
    if text is None:
        raise SystemExit("Could not extract text from the list: install poppler-utils (pdftotext) or pypdf.")
    data = parse_awaited(text)
    rows = data["rows"]
    if args.state:
        code = _STATE_ALIASES.get(args.state.lower())
        if not code:
            raise SystemExit("--state takes IS, LI or NO.")
        rows = [r for r in rows if any(s["state"] == code for s in r["states"])]
    if args.jcd:
        n, y = parse_jcd_number(args.jcd)
        rows = [r for r in rows if r["jcd"] == f"{n}/{y}"]
    if args.json:
        print(json.dumps({"report_date": data.get("report_date", ""), "url": AWAITED_PDF, "rows": rows},
                         indent=2, ensure_ascii=False))
        return
    print(f"JCDs awaiting fulfilment of constitutional requirements (Art. 103 EEA)")
    print(f"EFTA report 5.2.2 of {data.get('report_date') or '?'} — {AWAITED_PDF}")
    for t in data.get("totals", []):
        print(f"  ({t})")
    print()
    if not rows:
        print("No matching JCD in the list.")
    for r in rows:
        waiting = ", ".join(s["name"] + (f" (date of delay {s['date_of_delay']})" if s["date_of_delay"] else "")
                            for s in r["states"])
        print(f"{r['jcd']:9} adopted {r['adoption']}, six-month period ends {r['six_month_expiry']}")
        print(f"          awaiting: {waiting or '?'}")
        if r.get("dates_of_delay_unpaired"):
            print(f"          dates of delay (could not be paired with states): {', '.join(r['dates_of_delay_unpaired'])}")
        print(f"          {r['annex']}")
        print(f"          acts: {', '.join(r['acts'])}")


# ---------------------------------------------------------------------------
# Commands

def cmd_factsheet(args) -> None:
    ident = args.act.strip()
    if m := re.search(r"/eea-lex/([^/?#\s]+)", ident):
        ident = m.group(1)
    celex = None
    if m := CELEX_RE.match(ident):
        celex = ident.upper()
    elif re.fullmatch(r"\d{5,7}", ident):
        try:
            fetch_text(f"{LEX}/{ident}")
        except NotFound:
            raise SystemExit(f"EEA-Lex item {ident} has no factsheet (proposals redirect to themselves). "
                             "Use `search` to see its listing card.")
        celex = ident
    else:
        celex = act_to_celex(ident)
    fs = None
    if celex:
        try:
            fs = fetch_factsheet(celex)
        except NotFound:
            print(f"[note] no factsheet at {LEX}/{celex.lower()}; trying the keyword search", file=sys.stderr)
    if fs is None:
        found, items = _celex_from_keyword(ident)
        if not found:
            if not items:
                raise SystemExit(f"EEA-Lex has nothing for {args.act!r}. The act may have no EEA relevance, "
                                 "or not be registered yet.")
            print(f"No single factsheet for {args.act!r}. EEA-Lex keyword hits:")
            for it in items[:12]:
                print(f"  {it['id']:12} {it['document'] + '  ' if it['document'] else ''}{it['title'][:150]}")
            print("Run `factsheet <CELEX>` for one of them. Items without a CELEX number are proposals, "
                  "which have no factsheet.")
            sys.exit(1)
        fs = fetch_factsheet(found)
    if args.json:
        print(json.dumps(fs, indent=2, ensure_ascii=False))
    else:
        print(factsheet_summary(fs))


def cmd_search(args) -> None:
    facets = get_facets(args.refresh) if any((args.status, args.annex, args.protocol, args.type)) else {}
    filters = resolve_filters(facets, status=args.status, annex=args.annex, protocol=args.protocol,
                              type_=args.type, year=args.year)
    res = search(args.keyword, filters, sort=args.sort, per_page=args.limit, page=args.page)
    if args.details:
        for it in res["items"]:
            if it["celex"]:
                try:
                    fs = fetch_factsheet(it["id"])
                    it.update({k: fs.get(k) for k in ("status", "jcd", "in_force_in_eea", "areas")})
                except NotFound:
                    it["status"] = "(no factsheet)"
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return
    print(f"{res['total']} items / {res['pages']} pages (page {args.page + 1})  {res['url']}")
    for it in res["items"]:
        doc = f"{it['document']}  " if it["document"] else ""
        kind = "" if it["celex"] else "[proposal, no factsheet] "
        print(f"{it['id']:12} {kind}{doc}{it['title']}")
        if it.get("status"):
            print(f"{'':12} status: {it['status']}; JCD {it.get('jcd') or '-'}; "
                  f"in force in EEA: {it.get('in_force_in_eea') or '-'}")


def cmd_facets(args) -> None:
    facets = get_facets(args.refresh)
    if args.json:
        print(json.dumps(facets, indent=2, ensure_ascii=False))
        return
    for name in ("case_status", "celex_type", "protocol", "area_agreement"):
        print(f"{name}:")
        for e in facets.get(name, []):
            print(f"  {e['id']:>6}  {e['label']}" + (f" ({e['count']})" if e["count"] is not None else ""))


def cmd_jcd(args) -> None:
    n, year = parse_jcd_number(args.number)
    lang = args.lang.upper()
    if lang not in JCD_LANGS:
        raise SystemExit(f"--lang takes {', '.join(JCD_LANGS)}.")
    j = lookup_jcd(n, year, lang=lang, text=args.text, cellar=not args.no_cellar, refresh=args.refresh)
    if args.json:
        print(json.dumps(j, indent=2, ensure_ascii=False))
    else:
        print(jcd_summary(j))


def cmd_agreement(args) -> None:
    res = get_agreement(args.part, args.number, args.find, args.max, args.refresh)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(agreement_summary(res))


def cmd_status(args) -> None:
    d = cache_dir()
    print(f"cache dir: {d}")
    for sub in ("lists", "jcd", "agreement", "art103"):
        files = [p for p in (d / sub).rglob("*.pdf")] if (d / sub).exists() else []
        print(f"  {sub:10} {len(files)} PDFs")
    print(f"pdftotext: {shutil.which('pdftotext') or '(not found; pypdf fallback)'}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eea-lex", description="EEA status of EU acts, EEA Joint Committee "
                                "Decisions and the EEA Agreement texts, from EFTA (www.efta.int).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    common.add_argument("--refresh", action="store_true", help="Ignore cached copies.")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("factsheet", parents=[common], help="EEA-Lex factsheet of an EU act.")
    f.add_argument("act", help='CELEX (32016R0679), "Regulation 2016/679", "Directive 95/46/EC", or an EEA-Lex URL.')

    s = sub.add_parser("search", parents=[common], help="Search EEA-Lex.")
    s.add_argument("--keyword", "-k", help="Free text, CELEX, COM/C/D number.")
    s.add_argument("--status", help="proposed, scrutiny, draft, pending, in-force, no-longer (or label text).")
    s.add_argument("--annex", help="Annex or sub-area, e.g. XI, 11, XI.III.")
    s.add_argument("--protocol", help="Protocol number, e.g. 31.")
    s.add_argument("--type", help="Regulation, Directive, Decision, Recommendation, Other.")
    s.add_argument("--year", type=int, help="Year of EU adoption.")
    s.add_argument("--sort", help="relevance, jcd, jcd-asc, adopted, adopted-asc, proposal, proposal-asc, entry, entry-asc.")
    s.add_argument("--limit", type=int, default=24, help="Results per page: 6, 12, 24, 36, 48 or 60.")
    s.add_argument("--page", type=int, default=0, help="Zero-based page number.")
    s.add_argument("--details", action="store_true", help="Also fetch each hit's factsheet (status, JCD); 1 request per hit.")

    sub.add_parser("facets", parents=[common], help="List the search filters EEA-Lex offers, with ids and counts.")

    j = sub.add_parser("jcd", parents=[common], help="An EEA Joint Committee Decision: dates, acts, OJ status, text.")
    j.add_argument("number", help="NNN/YYYY, e.g. 154/2018.")
    j.add_argument("--lang", default="EN", help="EN, DE, IS or NO (for --text).")
    j.add_argument("--text", action="store_true", help="Download the EFTA PDF and extract its text.")
    j.add_argument("--no-cellar", action="store_true", help="Skip the Cellar (EUR-Lex) check.")

    a = sub.add_parser("agreement", parents=[common], help="Current EEA Agreement text: main part, an annex or a protocol.")
    a.add_argument("part", choices=("main", "annex", "protocol"))
    a.add_argument("number", nargs="?", help="Annex (11, XI, 13b) or protocol (31, 38c) number.")
    a.add_argument("--find", help="CELEX number (shows the annex entry and its footnotes) or a phrase.")
    a.add_argument("--max", type=int, default=10, help="Maximum hits per part (default 10).")

    q = sub.add_parser("pending103", parents=[common], help="JCDs awaiting constitutional requirements (Art. 103).")
    q.add_argument("--state", help="IS, LI or NO.")
    q.add_argument("--jcd", help="Only this JCD (NNN/YYYY).")

    sub.add_parser("status", help="Cache location and tools.")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    handlers = {"factsheet": cmd_factsheet, "search": cmd_search, "facets": cmd_facets, "jcd": cmd_jcd,
                "agreement": cmd_agreement, "pending103": cmd_pending103, "status": cmd_status}
    try:
        handlers[args.cmd](args)
    except Challenged as e:
        print(f"BLOCKED: www.efta.int answered {e} with a Cloudflare challenge. Do not retry from Bash; "
              "use the browser route in SKILL.md.", file=sys.stderr)
        return 3
    except NotFound as e:
        print(f"Not found: {e}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Network error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
