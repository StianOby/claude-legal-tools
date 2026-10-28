#!/usr/bin/env python3
"""efta_court.py — EFTA Court case law and procedural texts from eftacourt.int.

The site (relaunched October 2026) is a Vue app over an open JSON API at
api.eftacourt.int (the address comes from https://eftacourt.int/config.js).
The API returns every case and document in one response each, and has a
server-side full-text index over the documents' PDFs. Stdlib only; PDF text
comes from `pdftotext` (poppler) or else `pypdf`.

Cache layout (under the resolved cache dir):

  data.json                                  # the API collections, refreshed hourly
  cases/<KEY>/<type>-<LANG>.pdf|.txt|.json   # case documents (.json: source + method)
  texts/<slug>-<LANG>.pdf|.txt|.json         # procedural texts

All text files are UTF-8 regardless of the platform locale, and writes are
atomic (temp file + rename).
"""
from __future__ import annotations

import argparse
import hashlib
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_text import SPACES, finish, fold, mark_emphasis, mark_lists  # noqa: E402

SITE = "https://eftacourt.int"
DEFAULT_API = "https://api.eftacourt.int/api"
USER_AGENT = "efta-court-skill/2.0.0 (+https://github.com/StianOby/claude-legal-tools)"
FIRST_YEAR = 1994  # the EFTA Court's first case is E-1/94
DATA_TTL = 3600
# The API collections the skill reads. Others (press, members …) are not used.
COLLECTIONS = ("cases", "downloads", "procedures", "events", "settings", "eeftacourt")
SEARCH_CAP = 1000  # /search/documents never returns more IDs than this
SNIPPET_BATCH = 60  # the site's own batch size for /search/snippets

LANGS = {"English": "EN", "Norwegian": "NO", "German": "DE", "Icelandic": "IS",
         "Finnish": "FI", "Swedish": "SV", "French": "FR"}
COUNTRIES = {"Norway": "NO", "Iceland": "IS", "Liechtenstein": "LI", "Sweden": "SE", "Finland": "FI"}
# docType -> --type key. Press releases are left out on purpose (maintainer).
DOC_TYPES = {
    "Judgment": "judgment",
    "Report for the Hearing": "report",
    "Request for an Advisory Opinion": "request",
    "Notification": "notification",
    "Order of the Court": "order-court",
    "Order of the President": "order-president",
    "Information Note": "information-note",
    "Decision": "decision",
}
TYPE_ALIASES = {
    "advisory-opinion": "judgment", "opinion": "judgment", "ao": "judgment",
    "hearing-report": "report", "report-for-the-hearing": "report", "rh": "report",
    "request-ao": "request", "written-observations": "observations", "obs": "observations",
}
# Types that are the Court's own decisions, for cited-by.
DECISION_TYPES = {"judgment", "order-court", "order-president", "decision"}

# ---------------------------------------------------------------------------
# Cache directory, files


def cache_dir() -> Path:
    if env := os.environ.get("EFTA_COURT_CACHE_DIR"):
        p = Path(env)
    elif env := os.environ.get("XDG_CACHE_HOME"):
        p = Path(env) / "efta-court"
    elif sys.platform == "win32" and (la := os.environ.get("LOCALAPPDATA")):
        p = Path(la) / "efta-court"
    else:
        p = Path.home() / ".cache" / "efta-court"
    p.mkdir(parents=True, exist_ok=True)
    # 1.x (the WordPress site) kept index.json and per-case raw.html/meta.json;
    # none of it matches the new site, so it is removed once.
    if (p / "index.json").exists():
        (p / "index.json").unlink()
        shutil.rmtree(p / "cases", ignore_errors=True)
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


# ---------------------------------------------------------------------------
# HTTP


def _request(url: str, *, accept: str = "application/json", timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str) -> Any:
    return json.loads(_request(url))


_CONFIG_RE = re.compile(r"EFTA_API_URL\s*=\s*[\"']([^\"']+)[\"']")


def api_base_from_config(js: str) -> str | None:
    m = _CONFIG_RE.search(js)
    return m.group(1).rstrip("/") if m else None


def discover_api() -> str:
    """The API address the site itself uses (config.js is rewritten at each
    deploy), else the known one."""
    try:
        js = _request(f"{SITE}/config.js", accept="*/*", timeout=20).decode("utf-8", "replace")
        return api_base_from_config(js) or DEFAULT_API
    except (urllib.error.URLError, OSError):
        return DEFAULT_API


def storage_url(file_url: str, api: str) -> str:
    """Document files are always fetched from the API host's /storage path
    (maintainer's rule), whatever host the record names (the records say
    efta_back.on-forge.com)."""
    origin = re.sub(r"/api/?$", "", api)
    path = urllib.parse.urlsplit(file_url).path
    if not path.startswith("/storage/"):
        path = "/storage/imports/" + path.rsplit("/", 1)[-1]
    return origin + path


# ---------------------------------------------------------------------------
# Data: all collections, cached for an hour


def _slim(name: str, rows: Any) -> Any:
    """Drop what the skill never reads (event page modules, page images)."""
    if name == "events" and isinstance(rows, list):
        return [{k: v for k, v in e.items() if k not in ("modules", "image")} for e in rows]
    return rows


def load_data(refresh: bool = False) -> dict:
    p = cache_dir() / "data.json"
    old = None
    if _has_content(p):
        try:
            old = json.loads(_read(p))
        except json.JSONDecodeError:
            old = None
    if old and not refresh and time.time() - old.get("fetched_at", 0) < DATA_TTL:
        return old
    api = discover_api()
    try:
        with ThreadPoolExecutor(len(COLLECTIONS)) as ex:
            rows = list(ex.map(lambda n: fetch_json(f"{api}/{n}"), COLLECTIONS))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        if old:
            age = (time.time() - old.get("fetched_at", 0)) / 3600
            print(f"[warn] could not refresh from {api} ({e}); using the cached data from {age:.1f} h ago.",
                  file=sys.stderr)
            return old
        if isinstance(e, urllib.error.HTTPError) and e.code in (403, 405, 429, 503):
            raise SystemExit(f"{api} answered HTTP {e.code}. This source may be blocked from here.")
        raise SystemExit(f"Could not reach the EFTA Court API at {api}: {e}")
    data = {"fetched_at": time.time(), "api": api}
    data.update({n: _slim(n, r) for n, r in zip(COLLECTIONS, rows)})
    _write(p, json.dumps(data, ensure_ascii=False))
    return data


# ---------------------------------------------------------------------------
# Case numbers

_CASE_RE = re.compile(r"e?\s*-?\s*0*(\d+)\s*[-/_\s]\s*0*(\d+)", re.IGNORECASE)
# Compact form with no separator at all: E0825, E1415 -> number + 2-digit year
_COMPACT_RE = re.compile(r"^\s*e?\s*-?\s*(\d{1,2})(\d{2})\s*$", re.IGNORECASE)
_REF_NUM_RE = re.compile(r"E-0*(\d+)/(\d{2,4})", re.IGNORECASE)


def full_year(yy: int) -> int:
    """Map a 2-digit case year to a 4-digit year (94–99 -> 1990s)."""
    if yy >= 100:
        return yy
    return 1900 + yy if yy >= FIRST_YEAR % 100 else 2000 + yy


def normalise(case: str) -> str:
    """'E-08/26', 'e14-15', '14/15', 'E0825' -> canonical 'E-N/YY'."""
    m = _CASE_RE.search(case) or _COMPACT_RE.match(case)
    if not m:
        raise ValueError(f"Cannot parse case number: {case!r}")
    return f"E-{int(m.group(1))}/{int(m.group(2)) % 100:02d}"


def ref_numbers(ref: str) -> list[str]:
    """Every case number in a record's ref, canonical: 'Joined Cases E-31/24
    and E-32/24' -> ['E-31/24', 'E-32/24']; 'E-9/04 COSTS' -> ['E-9/04']."""
    out: list[str] = []
    for m in _REF_NUM_RE.finditer(ref or ""):
        c = f"E-{int(m.group(1))}/{int(m.group(2)) % 100:02d}"
        if c not in out:
            out.append(c)
    return out


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def case_year(rec: dict) -> int:
    nums = ref_numbers(rec.get("ref", ""))
    if nums:
        return full_year(int(nums[0].split("/")[1]))
    return int((rec.get("dateSubmitted") or "0")[:4] or 0)


def _sort_key(rec: dict):
    nums = ref_numbers(rec.get("ref", ""))
    n = int(nums[0][2:].split("/")[0]) if nums else 0
    return (-case_year(rec), -n, len(rec.get("ref", "")))


# ---------------------------------------------------------------------------
# Derived case fields


def procedure_code(rec: dict) -> str:
    """AO / INF / DA. The API's `type` says "Direct Action" for infringement
    actions too, so infringement is read from the procedure and the parties."""
    proc = (rec.get("procedure") or "").lower()
    parties = (rec.get("parties") or "").lower().strip()
    if rec.get("type") == "Advisory Opinion" or "advisory" in proc:
        return "AO"
    if "infringement" in proc or parties.startswith("efta surveillance authority v"):
        return "INF"
    if rec.get("type") == "Direct Action" or "annulment" in proc or "failure to act" in proc \
            or parties.endswith("v efta surveillance authority"):
        return "DA"
    return ""


_COURT_KEYS = (
    ("NO", ("norges", "norway", "norwegian", "borgarting", "agder", "frostating", "gulating", "hålogaland",
            "eidsivating", "oslo")),
    ("LI", ("liechtenstein", "fürstlich", "vaduz")),
    ("IS", ("iceland", "héraðsdómur", "landsréttur", "hæstiréttur", "reykjav")),
)


def country_code(rec: dict) -> str:
    """The EFTA State concerned: the referring court's country for AOs, else
    the State named in the parties (only when one is clearly named)."""
    if rec.get("source") in COUNTRIES:
        return COUNTRIES[rec["source"]]
    if rec.get("type") == "Advisory Opinion":
        # Some AOs have no source or referring court; the description names it.
        text = f"{rec.get('referringCourt') or ''} {strip_html(rec.get('description') or '')}".lower()
        for code, keys in _COURT_KEYS:
            if any(k in text for k in keys):
                return code
    p = (rec.get("parties") or "").lower()
    hits = [c for k, c in (("norway", "NO"), ("norwegian", "NO"), ("iceland", "IS"),
                           ("icelandic", "IS"), ("liechtenstein", "LI")) if k in p]
    return hits[0] if len(set(hits)) == 1 else ""


def case_page(rec: dict) -> str:
    """The public page for a case: the only link the skill gives to users."""
    return f"{SITE}/cases/{rec['id']}"


def strip_html(s: str) -> str:
    """Metadata HTML -> plain text, one paragraph per line."""
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).translate(SPACES)
    return "\n".join(x for x in (re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")) if x)


# ---------------------------------------------------------------------------
# Documents: three buckets, never mixed
#
# case  = listed in some case's `documents` (press releases dropped), plus the
#         written observations linked from case diaries
# text  = listed by a /procedures page or the e-EFTACourt page
# other = everything else (press) — never shown


def _lang_code(name: str | None) -> str:
    return LANGS.get(name or "", (name or "")[:2].upper())


def partition(data: dict) -> dict[str, str]:
    """doc id -> 'case' | 'text' for every document the skill shows."""
    by_id = {d["id"]: d for d in data.get("downloads", [])}
    out: dict[str, str] = {}
    for c in data.get("cases", []):
        for i in c.get("documents") or []:
            if i in by_id and by_id[i].get("docType") in DOC_TYPES:
                out[i] = "case"
    for p in data.get("procedures", []):
        for i in p.get("documents") or []:
            out.setdefault(i, "text")
    for e in data.get("eeftacourt", []):
        if e.get("document"):
            out.setdefault(e["document"], "text")
    return out


def _obs_id(url: str) -> str:
    return "obs-" + hashlib.md5(url.encode()).hexdigest()[:10]


def case_documents(rec: dict, data: dict) -> list[dict]:
    """The documents of one case record, in the API's order, then the
    written observations from the diary."""
    by_id = {d["id"]: d for d in data.get("downloads", [])}
    docs = []
    for i in rec.get("documents") or []:
        d = by_id.get(i)
        if not d or d.get("docType") not in DOC_TYPES:
            continue
        docs.append({"id": i, "type": DOC_TYPES[d["docType"]], "type_label": d["docType"],
                     "lang": _lang_code(d.get("language")), "date": d.get("date") or "",
                     "title": d.get("title") or "", "file": d.get("file") or "",
                     "record": rec["ref"], "record_id": rec["id"]})
    for e in rec.get("diary") or []:
        for o in e.get("docs") or []:
            if not isinstance(o, dict) or not o.get("url"):
                continue
            docs.append({"id": _obs_id(o["url"]), "type": "observations", "type_label": "Written observations",
                         "lang": "", "date": e.get("date") or "", "title": f"Written observations: {o.get('label', '')}",
                         "party": o.get("label", ""), "file": o["url"],
                         "record": rec["ref"], "record_id": rec["id"]})
    return docs


# ---------------------------------------------------------------------------
# Resolving a case


def resolve(query: str, data: dict) -> dict:
    """-> {'main': record, 'joined': [records], 'related': [records]}.

    An exact ref ('E-9/04 COSTS', 'Joined Cases E-31/24 and E-32/24') picks
    that record. A case number picks its own record; joined-case records
    that include it come along (the judgment of joined cases is only on the
    joined record), and COSTS / INT / revision records are named as related.
    """
    cases = data.get("cases", [])
    q = _squash(query)
    exact = [c for c in cases if _squash(c["ref"]) == q and not re.fullmatch(r"E-\d+/\d\d", c["ref"])]
    if exact:
        return {"main": exact[0], "joined": [], "related": []}
    canon = normalise(query)
    own = [c for c in cases if c["ref"] == canon]
    joined = [c for c in cases if len(ref_numbers(c["ref"])) > 1 and canon in ref_numbers(c["ref"])]
    related = [c for c in cases if c["ref"] != canon and ref_numbers(c["ref"]) == [canon]]
    if own:
        return {"main": own[0], "joined": joined, "related": related}
    if joined:
        return {"main": joined[0], "joined": joined[1:], "related": related}
    if related:
        return {"main": related[0], "joined": [], "related": related[1:]}
    raise SystemExit(f"No EFTA Court case {canon}. Check the number; `list` shows what exists.")


def documents_for(res: dict, data: dict) -> list[dict]:
    docs = case_documents(res["main"], data)
    for j in res["joined"]:
        docs += case_documents(j, data)
    for n, d in enumerate(docs, 1):
        d["n"] = n
    return docs


# ---------------------------------------------------------------------------
# Output


def case_summary(rec: dict) -> dict:
    return {
        "ref": rec["ref"], "parties": rec.get("parties") or "", "status": rec.get("status") or "",
        "procedure_code": procedure_code(rec), "type": rec.get("type") or "",
        "procedure": rec.get("procedure") or "", "country": country_code(rec),
        "referring_court": rec.get("referringCourt") or "", "language_of_case": rec.get("language") or "",
        "subject_matter": rec.get("subjectMatter") or [], "keywords": strip_html(rec.get("keywords") or ""),
        "description": strip_html(rec.get("description") or ""),
        "date_submitted": rec.get("dateSubmitted") or "", "hearing_date": rec.get("hearingDate") or "",
        "judgment_date": rec.get("judgmentDate") or "", "published_in": rec.get("publishedIn") or "",
        "case_page": case_page(rec),
        "diary": [{"date": e.get("date") or "", "event": strip_html(e.get("description") or "")}
                  for e in rec.get("diary") or []],
    }


def format_documents(docs: list[dict]) -> str:
    lines = []
    for d in docs:
        extra = f"  [{d['record']}]" if d.get("joined_from") else ""
        lines.append(f"  {d['n']:>2}. {d['type']:<16} {d['lang'] or '--':<3} {d['date'] or '':<10}  {d['title']}{extra}")
    return "\n".join(lines) or "  (no documents)"


def print_case(res: dict, data: dict) -> None:
    s = case_summary(res["main"])
    docs = documents_for(res, data)
    for d in docs:
        d["joined_from"] = d["record_id"] != res["main"]["id"]
    print(f"{s['ref']}  {s['parties']}")
    print(f"  Status: {s['status']}   Procedure: {s['procedure_code'] or '?'} ({s['procedure'] or s['type']})"
          + (f"   Country: {s['country']}" if s["country"] else ""))
    if s["referring_court"]:
        print(f"  Referring court: {s['referring_court']}   Language of the case: {s['language_of_case']}")
    for k, label in (("date_submitted", "Lodged"), ("hearing_date", "Hearing"), ("judgment_date", "Judgment")):
        if s[k]:
            print(f"  {label}: {s[k]}")
    if s["subject_matter"]:
        print(f"  Subject matter: {', '.join(s['subject_matter'])}")
    if s["keywords"]:
        print(f"  Keywords: {s['keywords']}")
    if s["published_in"]:
        print(f"  Published in: {s['published_in']} (no volume/page in the data)")
    print(f"  Case page: {s['case_page']}")
    for j in res["joined"]:
        print(f"  Joined: {j['ref']} — page {case_page(j)}")
    for r in res["related"]:
        print(f"  Related record: {r['ref']} (pass this ref to see it)")
    if s["description"]:
        print("\nAbout:\n  " + s["description"].replace("\n", "\n  "))
    if s["diary"]:
        print("\nDiary:")
        for e in s["diary"]:
            print(f"  {e['date']}  {e['event']}")
    print("\nDocuments (get with --doc N or --type T [--lang L]):")
    print(format_documents(docs))


# ---------------------------------------------------------------------------
# Download + text extraction

# How a cached .txt was made; a .txt made another way is extracted again.
# pdftotext (poppler) first: on the 1990s judgments pypdf splits words at
# irregular letter spacing ("statut ory", "intr a-EEA"). -raw keeps the PDF's
# lines and hyphens as printed.
EXTRACT_METHOD = "pdftotext -raw"


def extract_pdf_text(pdf: Path) -> tuple[str | None, str]:
    if shutil.which("pdftotext"):
        out = pdf.with_suffix(".txt.tmp")
        subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), str(out)], check=False,
                       stderr=subprocess.DEVNULL)
        if _has_content(out):
            text = _read(out)
            out.unlink()
            return text, EXTRACT_METHOD
    try:
        from pypdf import PdfReader  # type: ignore
    except ModuleNotFoundError:
        return None, ""
    try:
        reader = PdfReader(str(pdf))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return (text, "pypdf") if text.strip() else (None, "")
    except Exception as e:  # corrupt / encrypted PDF
        print(f"[pdf] pypdf failed on {pdf.name}: {e}", file=sys.stderr)
        return None, ""


def fetch_document(file_url: str, stem: Path, api: str) -> tuple[Path, Path | None]:
    """Download (if the cached copy is from another file) and extract.
    The sidecar <stem>.json records the source file and extraction method."""
    pdf, txt, side = stem.with_suffix(".pdf"), stem.with_suffix(".txt"), stem.with_suffix(".json")
    url = storage_url(file_url, api)
    meta = {}
    if _has_content(side):
        try:
            meta = json.loads(_read(side))
        except json.JSONDecodeError:
            meta = {}
    if meta.get("file") != urllib.parse.urlsplit(url).path or not _has_content(pdf):
        try:
            data = _request(url, accept="application/pdf,*/*", timeout=180)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Download failed: HTTP {e.code} for {url}")
        if not data.startswith(b"%PDF"):
            raise SystemExit(f"{url} did not return a PDF (blocked or moved?).")
        _write_bytes(pdf, data)
        meta = {"file": urllib.parse.urlsplit(url).path}
    if not _has_content(txt) or meta.get("method") != EXTRACT_METHOD:
        text, method = extract_pdf_text(pdf)
        if text:
            _write(txt, text)
            meta["method"] = method
        elif not _has_content(txt):
            txt = None
    _write(side, json.dumps(meta))
    return pdf, txt


def _key(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", ref).strip("-")


def doc_stem(docs: list[dict], d: dict) -> str:
    """'judgment-EN'; a second document of the same type and language gets
    its date, else its list number; observations are named by party."""
    if d["type"] == "observations":
        return "observations-" + (re.sub(r"[^A-Za-z0-9]+", "-", d.get("party", "")).strip("-")[:40] or str(d["n"]))
    base = f"{d['type']}-{d['lang'] or 'XX'}"
    same = [x for x in docs if x["type"] == d["type"] and x["lang"] == d["lang"]]
    if len(same) == 1:
        return base
    if d["date"] and sum(x["date"] == d["date"] for x in same) == 1:
        return f"{d['type']}-{d['date']}-{d['lang'] or 'XX'}"
    return f"{base}-{d['n']}"


def norm_type(t: str) -> str:
    t = re.sub(r"[\s_]+", "-", t.strip().lower())
    return TYPE_ALIASES.get(t, t)


def choose_doc(docs: list[dict], doc_type: str, lang: str, party: str | None = None) -> dict | None:
    """The document of this type in `lang` (else EN, else any, with a note).
    'order' matches both kinds of order; --party narrows observations."""
    want = norm_type(doc_type)
    cands = [d for d in docs if d["type"] == want or (want == "order" and d["type"].startswith("order-"))]
    if party:
        cands = [d for d in cands if party.casefold() in d.get("party", d["title"]).casefold()]
    if not cands:
        return None
    if want == "observations":
        if len(cands) > 1:
            print(f"[note] {len(cands)} sets of observations match; using the first. "
                  "Narrow with --party NAME or pick with --doc N.", file=sys.stderr)
        return cands[0]
    lang = lang.upper()
    for L in (lang, "EN"):
        same = [d for d in cands if d["lang"] == L]
        if same:
            if len(same) > 1:
                print(f"[note] {len(same)} {want!r} documents in {L}; using the last "
                      "(see the list without --type, and pick another with --doc N).", file=sys.stderr)
            if L != lang:
                print(f"[note] no {lang} version of {want!r}; using {L} "
                      f"(available: {', '.join(sorted({d['lang'] for d in cands if d['lang']}))}).", file=sys.stderr)
            return same[-1]
    print(f"[note] no {lang} or EN version of {want!r}; using {cands[0]['lang'] or '?'}.", file=sys.stderr)
    return cands[0]


# ---------------------------------------------------------------------------
# Server search


def server_search(q: str, api: str, lang: str | None = None) -> list[str]:
    url = f"{api}/search/documents?q={urllib.parse.quote(q)}"
    if lang:
        url += f"&lang={urllib.parse.quote(lang.upper())}"
    ids = fetch_json(url)
    return ids if isinstance(ids, list) else []


def snippets(q: str, ids: list[str], api: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(ids), SNIPPET_BATCH):
        batch = ids[i:i + SNIPPET_BATCH]
        url = f"{api}/search/snippets?q={urllib.parse.quote(q)}&ids={','.join(batch)}"
        try:
            for s in fetch_json(url) or []:
                out[s["id"]] = re.sub(r"\s+", " ", s.get("snippet") or "").strip()
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
    return out


def cap_warning(ids: list[str]) -> None:
    if len(ids) >= SEARCH_CAP:
        print(f"[warn] the server stops at {SEARCH_CAP} matching documents; results are incomplete. "
              "Narrow the query (a \"phrase\", more words, --lang).", file=sys.stderr)


_TERM_RE = re.compile(r'"([^"]+)"|(\S+)')


def meta_match(text: str, q: str) -> bool:
    """Local match with the server's rules: whole words, all terms,
    "phrases", prefix*."""
    t = fold(text).casefold()
    for phrase, word in _TERM_RE.findall(q):
        term = (phrase or word).casefold()
        if term.endswith("*"):
            pat = r"(?<!\w)" + re.escape(term[:-1])
        else:
            pat = r"(?<!\w)" + r"\s+".join(map(re.escape, term.split())) + r"(?!\w)"
        if not re.search(pat, t):
            return False
    return True


# ---------------------------------------------------------------------------
# Filters


def _filter(cases: list[dict], a: argparse.Namespace) -> list[dict]:
    out = []
    for c in cases:
        if getattr(a, "year", None) and case_year(c) != full_year(a.year):
            continue
        if getattr(a, "country", None) and country_code(c) != a.country.upper():
            continue
        if getattr(a, "procedure", None) and procedure_code(c) != a.procedure.upper():
            continue
        if getattr(a, "status", None) and (c.get("status") or "").lower() != a.status.lower():
            continue
        if getattr(a, "subject", None) and not any(a.subject.casefold() in s.casefold() for s in c.get("subjectMatter") or []):
            continue
        if getattr(a, "court", None) and a.court.casefold() not in (c.get("referringCourt") or "").casefold():
            continue
        if getattr(a, "party", None) and a.party.casefold() not in (c.get("parties") or "").casefold():
            continue
        if getattr(a, "language", None) and a.language.casefold() not in (c.get("language") or "").casefold():
            continue
        if getattr(a, "observer", None):
            obs = [e.get("description") or "" for e in c.get("diary") or []
                   if re.match(r"\s*written observations", e.get("description") or "", re.I)]
            if not any(a.observer.casefold() in o.casefold() for o in obs):
                continue
        out.append(c)
    return sorted(out, key=_sort_key)


def _row(c: dict) -> str:
    d = c.get("judgmentDate") or c.get("dateSubmitted") or ""
    subj = ", ".join(c.get("subjectMatter") or [])
    parties = (c.get("parties") or "").replace("\n", " ")
    return (f"{c['ref']:<14} {d:<10} {(c.get('status') or ''):<8} {procedure_code(c) or '-':<3} "
            f"{country_code(c) or '-':<2}  {parties[:90]}" + (f"  [{subj}]" if subj else ""))


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--year", type=int, help="year of the case number (2024 or 24)")
    p.add_argument("--country", help="NO, IS or LI (referring court's State; for ESA actions the State sued)")
    p.add_argument("--procedure", help="AO, INF or DA")
    p.add_argument("--status", choices=["pending", "decided"], type=str.lower)
    p.add_argument("--pending", dest="status", action="store_const", const="pending")
    p.add_argument("--decided", dest="status", action="store_const", const="decided")
    p.add_argument("--subject", help="subject-matter tag, substring (see `subjects`)")
    p.add_argument("--court", help="referring court, substring (Høyesterett, Borgarting, Landsréttur …)")
    p.add_argument("--party", help="substring of the parties")
    p.add_argument("--language", help="language of the case (Norwegian, German, Icelandic …)")
    p.add_argument("--observer", help="cases where written observations came from this (Liechtenstein, European Commission …)")


# ---------------------------------------------------------------------------
# Commands: cases


def cmd_case(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    res = resolve(a.case, data)
    if a.json:
        out = case_summary(res["main"])
        out["joined"] = [{"ref": j["ref"], "case_page": case_page(j)} for j in res["joined"]]
        out["related"] = [r["ref"] for r in res["related"]]
        out["documents"] = [{k: d[k] for k in ("n", "type", "lang", "date", "title", "record")}
                            for d in documents_for(res, data)]
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print_case(res, data)


def cmd_list(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    rows = _filter(data["cases"], a)
    if a.json:
        print(json.dumps([case_summary(c) | {"diary": None} for c in rows[:a.limit]], ensure_ascii=False, indent=1))
        return
    print(f"{len(rows)} case record(s){f'; showing {a.limit}' if len(rows) > a.limit else ''}.")
    for c in rows[:a.limit]:
        print(_row(c))


def cmd_subjects(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    counts: dict[str, int] = {}
    for c in _filter(data["cases"], a):
        for s in c.get("subjectMatter") or []:
            counts[s] = counts.get(s, 0) + 1
    for s, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{n:>4}  {s}")


def _cases_by_doc(data: dict) -> dict[str, dict]:
    return {i: c for c in data["cases"] for i in c.get("documents") or []}


def dedupe_hits(hits: list[dict]) -> list[dict]:
    """Joined cases from the 1990s carry the same PDF on the joined record
    and on each component (E-8/94, E-9/94, 'E-8/94 and E-9/94'). Keep each
    file once, on the record with the most case numbers; a record left
    with no documents (and no match in its own details) drops out."""
    owner: dict[str, dict] = {}
    for h in hits:
        for d in h["docs"]:
            key = urllib.parse.urlsplit(d["file"]).path
            cur = owner.get(key)
            if cur is None or len(ref_numbers(h["case"]["ref"])) > len(ref_numbers(cur["case"]["ref"])):
                owner[key] = h
    out = []
    for h in hits:
        h["docs"] = [d for d in h["docs"] if owner[urllib.parse.urlsplit(d["file"]).path] is h]
        if h["docs"] or h.get("meta"):
            out.append(h)
    return out


def _other_bucket_note(ids: list[str], buckets: dict[str, str], want: str, q: str) -> None:
    other = "text" if want == "case" else "case"
    n = sum(buckets.get(i) == other for i in ids)
    if n:
        cmd = f'texts search "{q}"' if other == "text" else f'search "{q}"'
        what = "procedural texts" if other == "text" else "case documents"
        print(f"\n(also {n} hit(s) in {what}: {cmd})")


def cmd_search(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    api = data["api"]
    pool = _filter(data["cases"], a)
    by_doc = _cases_by_doc(data)
    buckets = partition(data)
    type_want = norm_type(a.type) if a.type else None
    hits: dict[str, dict] = {}  # case id -> {"case", "meta", "docs"}
    for c in pool:
        text = " ".join([c["ref"], c.get("parties") or "", c.get("keywords") or "",
                         " ".join(c.get("subjectMatter") or []), c.get("referringCourt") or "",
                         strip_html(c.get("description") or "")])
        if meta_match(text, a.query):
            hits[c["id"]] = {"case": c, "meta": True, "docs": []}
    ids: list[str] = []
    if not a.meta_only:
        ids = server_search(a.query, api, a.lang)
        cap_warning(ids)
        pool_ids = {c["id"] for c in pool}
        docs_by_id = {d["id"]: d for c in pool for d in case_documents(c, data)}
        for i in ids:
            if buckets.get(i) != "case" or i not in docs_by_id:
                continue
            c = by_doc.get(i)
            if not c or c["id"] not in pool_ids:
                continue
            d = docs_by_id[i]
            if type_want and not (d["type"] == type_want or (type_want == "order" and d["type"].startswith("order-"))):
                continue
            hits.setdefault(c["id"], {"case": c, "meta": False, "docs": []})["docs"].append(d)
    found = dedupe_hits(list(hits.values()))
    if type_want:
        found = [h for h in found if h["docs"]]
    ordered = sorted(found, key=lambda h: _sort_key(h["case"]), reverse=a.oldest)
    shown = ordered[:a.limit]
    want_snip = []
    for h in shown:
        if h["docs"]:
            best = sorted(h["docs"], key=lambda d: (d["type"] != "judgment", d["lang"] != "EN"))[0]
            h["best"] = best
            want_snip.append(best["id"])
    snip = snippets(a.query, want_snip, api) if want_snip else {}
    if a.json:
        print(json.dumps([{"ref": h["case"]["ref"], "parties": h["case"].get("parties"),
                           "case_page": case_page(h["case"]), "metadata_match": h["meta"],
                           "documents": [f"{d['type']} {d['lang']}".strip() for d in h["docs"]],
                           "snippet": snip.get(h.get("best", {}).get("id", ""), "")} for h in shown],
                         ensure_ascii=False, indent=1))
        return
    print(f"{len(ordered)} case(s) match{f'; showing {a.limit}' if len(ordered) > a.limit else ''}"
          f"{'' if a.meta_only else f' ({len(ids)} document hit(s) on the server before filtering)'}.")
    for h in shown:
        print("\n" + _row(h["case"]))
        where = (["case details"] if h["meta"] else []) + sorted({f"{d['type']} {d['lang']}".strip() for d in h["docs"]})
        print(f"    matches in: {', '.join(where)}")
        s = snip.get(h.get("best", {}).get("id", ""))
        if s:
            print(f"    {h['best']['type']} {h['best']['lang']}: {s}")
    if not a.meta_only:
        _other_bucket_note(ids, buckets, "case", a.query)


_REP_RE = re.compile(r"\[(\d{4}(?:\s*[-–]\s*\d{2,4})?)\]\s*EFTA\s*(?:Ct\.?\s*Rep(?:orts?)?\.?|Court\s+Reports?|rep\.?)\s*(\d+)",
                     re.IGNORECASE)


def report_refs(snips: list[str], ref: str) -> dict[str, int]:
    """'[1994-1995] EFTA Ct. Rep. 17' references that follow `ref` in the
    snippets, tallied (later documents do not always agree)."""
    tally: dict[str, int] = {}
    pat = re.compile(re.escape(ref).replace("/", r"\s*/\s*") + r"(?!\d)", re.I)
    for s in snips:
        for m in pat.finditer(s):
            r = _REP_RE.search(s, m.end(), m.end() + 160)
            if r:
                vol = re.sub(r"\s+", "", r.group(1)).replace("–", "-")
                key = f"[{vol}] EFTA Ct. Rep. {r.group(2)}"
                tally[key] = tally.get(key, 0) + 1
    return dict(sorted(tally.items(), key=lambda x: -x[1]))


def cmd_cited_by(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    api = data["api"]
    res = resolve(a.case, data)
    nums = ref_numbers(a.case)
    canon = nums[0] if nums else normalise(a.case)
    own_ids = {res["main"]["id"]} | {c["id"] for c in res["joined"] + res["related"]}
    forms = [canon]
    num, yy = canon[2:].split("/")
    if len(num) == 1:
        forms.append(f"E-0{num}/{yy}")  # 2026 citations write E-08/26
    ids: list[str] = []
    for f in forms:
        for i in server_search(f'"{f}"', api):
            if i not in ids:
                ids.append(i)
    cap_warning(ids)
    by_doc = _cases_by_doc(data)
    buckets = partition(data)
    citing: dict[str, dict] = {}
    for i in ids:
        c = by_doc.get(i)
        if buckets.get(i) != "case" or not c or c["id"] in own_ids:
            continue
        d = next((x for x in case_documents(c, data) if x["id"] == i), None)
        if not d or (not a.all and d["type"] not in DECISION_TYPES):
            continue
        citing.setdefault(c["id"], {"case": c, "docs": []})["docs"].append(d)
    ordered = sorted(dedupe_hits(list(citing.values())), key=lambda h: _sort_key(h["case"]), reverse=True)
    pick = []
    for h in ordered:
        h["best"] = sorted(h["docs"], key=lambda d: (d["type"] != "judgment", d["lang"] != "EN"))[0]
        pick.append(h["best"]["id"])
    snip = snippets(f'"{canon}"', pick[:a.snippets], api)
    print(f"{res['main']['ref']} {res['main'].get('parties', '')}")
    print(f"Cited in {len(ordered)} other case(s)"
          f" ({'any document' if a.all else 'judgments, orders and decisions only; --all adds hearing reports, requests …'}):")
    for h in ordered[:a.limit]:
        print("\n" + _row(h["case"]))
        kinds = sorted({f"{d['type']} {d['lang']}".strip() for d in h["docs"]})
        print(f"    in: {', '.join(kinds)}")
        if h["best"]["id"] in snip:
            print(f"    {snip[h['best']['id']]}")
    reps = report_refs(list(snip.values()), canon)
    if reps:
        print("\nEFTA Court Report references for it in those snippets (as the citing documents give them; "
              "not verified, and they may disagree):")
        for k, n in reps.items():
            print(f"  {k}  ×{n}")


def cmd_get(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    res = resolve(a.case, data)
    docs = documents_for(res, data)
    if a.doc is None and not a.type:
        print(f"Documents for {res['main']['ref']} — pick one with --type T [--lang L] or --doc N:")
        print(format_documents(docs))
        return
    if a.doc is not None:
        if not 1 <= a.doc <= len(docs):
            raise SystemExit(f"--doc {a.doc}: {res['main']['ref']} has {len(docs)} document(s).")
        chosen = docs[a.doc - 1]
    else:
        chosen = choose_doc(docs, a.type, a.lang, a.party)
        if not chosen:
            raise SystemExit(f"No {a.type!r} document for {res['main']['ref']}. Available:\n" + format_documents(docs))
    stem = cache_dir() / "cases" / _key(chosen["record"]) / doc_stem(docs, chosen)
    pdf, txt = fetch_document(chosen["file"], stem, data["api"])
    rec = next(c for c in data["cases"] if c["id"] == chosen["record_id"])
    kind = f"{chosen['type']} {chosen['lang']}".strip()
    print(f"{chosen['title']}  ({kind}, {chosen['date'] or 'no date'})")
    print(f"PDF:  {pdf}")
    print(f"Text: {txt}" if txt else "Text: not extracted (no pdftotext or pypdf, or a scanned PDF)")
    print(f"Case page: {case_page(rec)}")


def cmd_calendar(a: argparse.Namespace) -> None:
    """Hearings, judgment dates, deadlines and court events, as the site's
    judicial calendar builds them."""
    data = load_data(a.refresh)
    start = date.today() - timedelta(days=a.past)
    end = date.today() + timedelta(days=a.days)
    items = []
    for c in data["cases"]:
        seen = set()
        for k, kind in (("hearingDate", "hearing"), ("judgmentDate", "judgment")):
            if c.get(k):
                items.append((c[k], kind, f"{c['ref']} — {kind}: {c.get('parties', '')[:80]}", case_page(c)))
                seen.add(c[k])
        for e in c.get("diary") or []:
            desc = strip_html(e.get("description") or "")
            if not e.get("date") or e["date"] in seen:
                continue
            if e.get("calendar") or e.get("category") == 1 or re.match(r"\s*deadline\b", desc, re.I):
                kind = "hearing" if re.search(r"\boral hearing\b", desc, re.I) or e.get("category") == 1 else "deadline"
                items.append((e["date"], kind, f"{c['ref']} — {desc[:110]}", case_page(c)))
    for e in data.get("events", []):
        if e.get("hidden") or not e.get("eventDate"):
            continue
        t = e.get("type") or ""
        kind = "hearing" if re.search(r"oral hearing|public sitting", t, re.I) else \
            "judgment" if re.search(r"delivery of judgment", t, re.I) else "event"
        if kind == "event" and not a.all:
            continue
        m = re.search(r"E-\d+/\d+", e.get("title") or "")
        if m and any(i[0] == e["eventDate"] and i[2].startswith(m.group(0) + " ") for i in items):
            continue
        items.append((e["eventDate"], kind, e.get("title") or "", f"{SITE}/events/{e['id']}"))
    for v in (data.get("settings") or {}).get("calendar_entries") or []:
        if v.get("date") and v.get("label"):
            items.append((v["date"], v.get("type") or "vacation", v["label"], f"{SITE}/calendar"))
    items = sorted(i for i in items if start.isoformat() <= i[0] <= end.isoformat())
    print(f"Calendar {start} – {end} ({len(items)} item(s)):")
    for d, kind, label, link in items:
        print(f"  {d}  {kind:<9} {label}\n              {link}")


# ---------------------------------------------------------------------------
# Procedural texts


def html_to_text(fragment: str) -> str:
    """A procedural page's HTML -> text under the repo's source-text rules:
    #/##/### headings, *italic*/**bold**, list markers, browser whitespace."""
    s = re.sub(r"<(script|style)\b.*?</\1>", "", fragment, flags=re.S | re.I)
    # HTML whitespace collapses as in a browser (a line break in the markup
    # is a space); U+00A0 is not HTML whitespace, SPACES handles it below.
    s = re.sub(r"[ \t\n\r\f]+", " ", s)

    def heading(m: re.Match) -> str:
        inner = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).translate(SPACES)
        inner = re.sub(r" +", " ", inner).strip()
        return f"\n\n{'#' * (max(2, int(m.group(1))) - 1)} {inner}\n\n" if inner else "\n\n"

    s = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", heading, s, flags=re.S | re.I)
    s = mark_lists(mark_emphasis(s))
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</?(p|div|ul|ol|table|tr|blockquote|li)\b[^>]*>", "\n\n", s, flags=re.I)
    s = re.sub(r"</t[dh]>", " | ", s, flags=re.I)
    s = finish(html.unescape(re.sub(r"<[^>]+>", "", s)).translate(SPACES))
    out, blank = [], True
    for line in (re.sub(r"[ \t]+", " ", x).strip() for x in s.split("\n")):
        if not line:
            if not blank:
                out.append("")
            blank = True
            continue
        out.append(line)
        blank = False
    return "\n".join(out).strip() + "\n"


def _base_title(t: str) -> str:
    return re.sub(r"\s*\((EN|NO|IS|DE|FI|SV|FR)\)\s*$", "", t or "").strip()


def texts_catalogue(data: dict) -> list[dict]:
    """The procedural texts, one entry per text with its language versions.
    A page whose own body is the text (the Surveillance and Court Agreement)
    is an HTML entry."""
    by_id = {d["id"]: d for d in data.get("downloads", [])}
    out: list[dict] = []

    def add(title: str, page: str, version: dict) -> None:
        for t in out:
            if t["title"] == title and t["page"] == page:
                t["versions"].append(version)
                return
        out.append({"title": title, "page": page, "versions": [version]})

    for p in sorted(data.get("procedures", []), key=lambda p: p.get("order") or 0):
        page = f"{SITE}/procedure/{p['id']}"
        docs = [by_id[i] for i in p.get("documents") or [] if i in by_id]
        for d in docs:
            add(_base_title(d["title"]), page, {"id": d["id"], "lang": _lang_code(d.get("language")), "file": d["file"]})
        body = p.get("body") or ""
        if not docs and len(re.sub(r"<[^>]+>", "", body)) > 2000:
            add(p["title"], page, {"id": p["id"], "lang": "EN", "html": body})
    for e in data.get("eeftacourt", []):
        d = by_id.get(e.get("document") or "")
        if d:
            add(_base_title(d["title"]), f"{SITE}/e-eftacourt",
                {"id": d["id"], "lang": _lang_code(d.get("language")), "file": d["file"]})
    for n, t in enumerate(out, 1):
        t["n"] = n
    return out


def choose_text(cat: list[dict], sel: str) -> dict:
    if sel.isdigit():
        n = int(sel)
        if not 1 <= n <= len(cat):
            raise SystemExit(f"There are {len(cat)} texts; see `texts list`.")
        return cat[n - 1]
    exact = [t for t in cat if _squash(t["title"]) == _squash(sel)]
    if exact:
        return exact[0]
    words = _squash(sel).split()
    hits = [t for t in cat if all(w in _squash(t["title"]) for w in words)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"No procedural text matches {sel!r}; see `texts list`.")
    hits.sort(key=lambda t: ("previous" in t["title"].lower(), len(t["title"])))
    raise SystemExit("Several texts match; pick one by number:\n"
                     + "\n".join(f"  {t['n']:>2}. {t['title']}" for t in hits))


def _text_stem(t: dict, lang: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", t["title"].lower()).strip("-")[:60]
    return cache_dir() / "texts" / f"{slug}-{lang}"


def _text_file(t: dict, v: dict, api: str) -> tuple[Path | None, Path]:
    stem = _text_stem(t, v["lang"])
    if "html" in v:
        txt = stem.with_suffix(".txt")
        _write(txt, html_to_text(v["html"]))
        return None, txt
    pdf, txt = fetch_document(v["file"], stem, api)
    return pdf, txt


def cmd_texts(a: argparse.Namespace) -> None:
    data = load_data(a.refresh)
    cat = texts_catalogue(data)
    if a.action == "list":
        for t in cat:
            langs = ", ".join(v["lang"] for v in t["versions"])
            print(f"  {t['n']:>2}. {t['title']}  [{langs}]{'  (web page text)' if 'html' in t['versions'][0] else ''}")
        return
    if a.action == "get":
        if not a.arg:
            raise SystemExit("texts get needs a number or title words (see `texts list`).")
        t = choose_text(cat, a.arg)
        lang = a.lang.upper()
        v = next((v for v in t["versions"] if v["lang"] == lang), None) or \
            next((v for v in t["versions"] if v["lang"] == "EN"), t["versions"][0])
        if v["lang"] != lang:
            print(f"[note] no {lang} version of {t['title']!r}; using {v['lang']} "
                  f"(available: {', '.join(x['lang'] for x in t['versions'])}).", file=sys.stderr)
        pdf, txt = _text_file(t, v, data["api"])
        print(f"{t['title']} ({v['lang']})")
        if pdf:
            print(f"PDF:  {pdf}")
        print(f"Text: {txt}" if txt else "Text: not extracted (no pdftotext or pypdf)")
        print(f"Page: {t['page']}")
        return
    # search
    if not a.arg:
        raise SystemExit('texts search needs a query, e.g. texts search "oral hearing"')
    buckets = partition(data)
    ids = server_search(a.arg, data["api"], a.lang if a.lang_given else None)
    cap_warning(ids)
    vid = {v["id"]: (t, v) for t in cat for v in t["versions"]}
    found = [vid[i] for i in ids if buckets.get(i) == "text" and i in vid]
    # The HTML texts are not in the server's index: search them here.
    for t in cat:
        for v in t["versions"]:
            if "html" in v and meta_match(html_to_text(v["html"]), a.arg):
                found.append((t, v))
    snip = snippets(a.arg, [v["id"] for _, v in found if "html" not in v], data["api"])
    print(f"{len(found)} procedural text version(s) match:")
    for t, v in found:
        print(f"\n  {t['n']:>2}. {t['title']} ({v['lang']})  {t['page']}")
        if v["id"] in snip:
            print(f"      {snip[v['id']]}")
    _other_bucket_note(ids, buckets, "text", a.arg)


# ---------------------------------------------------------------------------
# Misc


def cmd_update(a: argparse.Namespace) -> None:
    data = load_data(refresh=True)
    print(f"{len(data['cases'])} cases, {len(data['downloads'])} document records from {data['api']}.")


def cmd_status(a: argparse.Namespace) -> None:
    p = cache_dir()
    print(f"Cache: {p}")
    d = p / "data.json"
    if _has_content(d):
        data = json.loads(_read(d))
        age = (time.time() - data.get("fetched_at", 0)) / 60
        print(f"Data:  {len(data.get('cases', []))} cases from {data.get('api')}, fetched {age:.0f} min ago "
              f"(refreshed after {DATA_TTL // 60} min)")
    else:
        print("Data:  not fetched yet")
    print(f"PDF text: {'pdftotext' if shutil.which('pdftotext') else 'pypdf (if installed)'}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="efta_court.py", description="EFTA Court case law and procedural texts (eftacourt.int).")
    ap.add_argument("--refresh", action="store_true", help="re-fetch the API data even if the cache is fresh")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("case", aliases=["fetch"], help="one case: parties, status, dates, diary, documents")
    p.add_argument("case")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_case)

    p = sub.add_parser("list", help="filter all cases")
    _add_filters(p)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("subjects", help="subject-matter tags with case counts (takes the list filters)")
    _add_filters(p)
    p.set_defaults(func=cmd_subjects)

    p = sub.add_parser("search", help="full-text search of case documents (server) + case details")
    p.add_argument("query", help='words (all must match), "a phrase", prefix*')
    _add_filters(p)
    p.add_argument("--type", help="only hits in this document type (judgment, report, request, order …)")
    p.add_argument("--lang", help="only documents in EN, NO, IS or DE")
    p.add_argument("--meta-only", action="store_true", help="case details only, no full text")
    p.add_argument("--oldest", action="store_true", help="oldest cases first")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("cited-by", help="later cases whose judgments (or, with --all, any document) cite a case")
    p.add_argument("case")
    p.add_argument("--all", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--snippets", type=int, default=60, help="how many citing cases get a snippet (default 60)")
    p.set_defaults(func=cmd_cited_by)

    p = sub.add_parser("get", help="download a case document and extract its text")
    p.add_argument("case")
    p.add_argument("--type", help="judgment, report, request, notification, order, order-court, order-president, "
                                  "information-note, decision, observations")
    p.add_argument("--lang", default="EN", help="EN (default), NO, IS, DE")
    p.add_argument("--party", help="with --type observations: whose (Norway, Commission, ESA …)")
    p.add_argument("--doc", type=int, help="document number from the list")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("calendar", help="hearings, judgments and deadlines ahead (and --past days back)")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--past", type=int, default=0)
    p.add_argument("--all", action="store_true", help="include conferences and talks")
    p.set_defaults(func=cmd_calendar)

    p = sub.add_parser("texts", help="the Court's procedural texts: texts list | get N|WORDS [--lang] | search QUERY")
    p.add_argument("action", choices=["list", "get", "search"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--lang", default=None)
    p.set_defaults(func=cmd_texts)

    sub.add_parser("update", help="re-fetch the API data now").set_defaults(func=cmd_update)
    sub.add_parser("status", help="cache location and age").set_defaults(func=cmd_status)
    return ap


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.cmd == "texts":
        args.lang_given = args.lang is not None
        args.lang = args.lang or "EN"
    try:
        args.func(args)
    except ValueError as e:
        raise SystemExit(str(e))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from {e.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
