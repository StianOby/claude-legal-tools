#!/usr/bin/env python3
"""
coe.py - Council of Europe Treaty Office CLI.

Pure-HTTP fetcher for the European Treaty Series (ETS) and Council of
Europe Treaty Series (CETS) - the conventions listed at
https://www.coe.int/en/web/conventions/full-list.

Talks directly to the Treaty Office's React-portlet backend at
https://conventions-ws.coe.int/WS_LFRConventions/, the same JSON API
the official site uses. No Selenium, no JS evaluation - just GET/POST
with a static API token harvested from the public page.

Subcommands:
  index        Build/refresh the master index of all treaties.
  lookup       Fuzzy-search the cached index by name or CETS number.
  text         Download the treaty text for a given CETS number.
  report       Download the Explanatory Report.
  signatures   Download the chart of signatures and ratifications.
  declarations Download the declarations and reservations.
  fetch        Combo: resolve, then download all four (text + report
               + signatures + declarations).
  show         Print the cached extracted text of a previously
               downloaded document.

Examples:
  coe.py index --refresh
  coe.py lookup ECHR
  coe.py fetch 005          # ECHR
  coe.py fetch ECHR
  coe.py fetch "Istanbul Convention"
  coe.py signatures 210
  coe.py declarations 005
  coe.py show 005 --kind text

All cache files are written and read as UTF-8 regardless of platform
locale, and writes are atomic (temp file + rename), so an interrupted
run never leaves a truncated file that later looks like a cache hit.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

_default_cache = Path.home() / ".cache" / "ets"
CACHE_DIR = Path(os.environ.get("ETS_CACHE_DIR", _default_cache))
TREATIES_DIR = CACHE_DIR / "treaties"
INDEX_PATH = CACHE_DIR / "index.json"
SEED_INDEX = Path(__file__).resolve().parent.parent / "data" / "index.json"

API_BASE = "https://conventions-ws.coe.int/WS_LFRConventions/"
# Public token embedded in the Treaty Office page source. Required as
# the `token:` HTTP header on every request to the WCF service. Static.
API_TOKEN = "hfghhgp2q5vgwg1hbn532kw71zgtww7e"

USER_AGENT = (
    "ets-skill/0.2 "
    "(treaty research tool, Python-urllib)"
)

# The conventions-ws.coe.int server still serves a small DH key. We
# need to drop OpenSSL to SECLEVEL=0 and allow unsafe legacy
# renegotiation to talk to it. The same context is deliberately used
# for rm.coe.int (the document host): it sits behind Cloudflare, which
# answers 403 to Python's default TLS client hello but accepts this
# one (verified Sept 2026). Certificate verification stays on.
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.set_ciphers("DEFAULT@SECLEVEL=0")
SSL_CONTEXT.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

# Treaty Office uses 3-letter ISO language codes internally. UI codes
# are the Liferay locale (en_GB, fr_FR, ...). The mapping here matches
# what window.langue holds in the live page.
LANG_CODE = {
    "en": "ENG",
    "fr": "FRE",
    "de": "GER",
    "it": "ITA",
    "ru": "RUS",
}
DEFAULT_LANG = "en"

# Common short names / acronyms that users will say. The lookup
# command checks aliases first to give a deterministic top hit before
# fuzzy-matching by title. Keys are lower-cased.
ALIASES = {
    # Flagship human rights / criminal law / cybercrime
    "echr":               "005",
    "european convention on human rights": "005",
    "european convention of human rights": "005",
    "convention on human rights": "005",
    "ecpt":               "126",
    "cpt":                "126",
    "anti-torture":       "126",
    "anti torture":       "126",
    "european convention against torture": "126",
    "cybercrime":         "185",
    "budapest convention": "185",
    "convention on cybercrime": "185",
    "istanbul":           "210",
    "istanbul convention": "210",
    "violence against women": "210",
    "lanzarote":          "201",
    "lanzarote convention": "201",
    "child sexual exploitation": "201",
    # Bioethics / medical
    "oviedo":             "164",
    "oviedo convention":  "164",
    "biomedicine":        "164",
    "bioethics":          "164",
    # Data protection
    "convention 108":     "108",
    "data protection":    "108",
    "data protection convention": "108",
    "108+":               "223",
    "convention 108+":    "223",
    # Environment / heritage
    "bern":               "104",
    "bern convention":    "104",
    "wildlife":           "104",
    "faro":               "199",
    "granada":            "121",
    "valletta":           "143",
    # Sports / corruption
    "anti-doping":        "135",
    "macolin":            "215",
    "match-fixing":       "215",
    "corruption":         "173",
    "criminal law convention on corruption": "173",
    "money laundering":   "141",
    "warsaw convention":  "198",
    "trafficking":        "197",
    "human trafficking":  "197",
    # Constitutional / institutional
    "statute":            "001",
    "council of europe statute": "001",
    "social charter":     "035",
    "european social charter": "035",
    "revised social charter": "163",
    # Selected protocols
    "echr p1":            "009",
    "echr p4":            "046",
    "echr p6":            "114",
    "echr p7":            "117",
    "echr p12":           "177",
    "echr p13":           "187",
    "echr p15":           "213",
    "echr p16":           "214",
}

# Subset of fields we promote to a flat per-treaty meta.json. Keeps the
# common factual answers (entry into force, place of signature, the
# four PDF URLs) fast to access without re-parsing the whole index.
META_FIELDS = [
    "Numero_traite",
    "Nom_commun_ENG",
    "Libelle_titre_ENG",
    "Libelle_titre_FRE",
    "Date_ste",
    "Date_vigueur_ste",
    "Code_lieu_ste",
    "Numero_enreg_onu",
    "Date_enreg_onu",
    "Numero_traite_parent",
    "Lien_pdf_traite_ENG",
    "Lien_pdf_traite_FRE",
    "Lien_pdf_traite_GER",
    "Lien_pdf_traite_ITA",
    "Lien_pdf_traite_RUS",
    "Lien_pdf_rapex_ENG",
    "Lien_pdf_rapex_FRE",
    "Lien_html_traite_ENG",
    "Lien_html_rapex_ENG",
    "Mention",
]


# ---------------------------------------------------------------------------
# UTF-8, atomic file helpers
# ---------------------------------------------------------------------------

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
    """A cache file counts as present only if it is non-empty."""
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


def _load_json(p: Path):
    return json.loads(_read(p))


def _dump_json(p: Path, obj) -> None:
    _write(p, json.dumps(obj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _open(url, *, method="GET", body=None, accept="application/json"):
    """Open `url` against the conventions-ws backend with the right
    TLS context, headers and (optional) JSON body."""
    headers = {
        "token": API_TOKEN,
        "Accept": accept,
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(body).encode("utf-8")
    else:
        body_bytes = None
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    return urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=60)


def api_get(endpoint, params=None, lang=DEFAULT_LANG):
    """GET https://...WS_LFRConventions/<endpoint>?... → parsed JSON."""
    p = dict(params or {})
    p["langue"] = LANG_CODE.get(lang, "ENG")
    qs = urllib.parse.urlencode(p, safe=",")
    url = API_BASE + endpoint.lstrip("/") + "?" + qs
    with _open(url) as r:
        return json.load(r)


def api_post(endpoint, body, lang=DEFAULT_LANG):
    """POST a JSON body. Used by api/traites/search."""
    body = dict(body)
    body.setdefault("langue", LANG_CODE.get(lang, "ENG"))
    url = API_BASE + endpoint.lstrip("/")
    with _open(url, method="POST", body=body) as r:
        return json.load(r)


def download_document(url, stem: Path):
    """Download a treaty document into the cache.

    rm.coe.int serves most documents as PDF, but some (notably
    non-official translations) are HTML pages. The real type is
    detected from the Content-Type header and the file's magic bytes,
    and the file is saved as `<stem>.pdf` or `<stem>.html`. Returns
    (path, kind) where kind is 'pdf' or 'html'. If a file of either
    kind is already cached it is returned without a request.
    """
    # Not with_suffix(): the stem already ends in ".<lang>" and must be kept.
    pdf_p = stem.with_name(stem.name + ".pdf")
    html_p = stem.with_name(stem.name + ".html")
    if _has_content(pdf_p):
        return pdf_p, "pdf"
    if _has_content(html_p):
        return html_p, "html"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,*/*"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r:
        data = r.read()
        ctype = (r.headers.get("Content-Type") or "").lower()
    if data.startswith(b"%PDF"):
        _write_bytes(pdf_p, data)
        return pdf_p, "pdf"
    if "html" in ctype or data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        _write_bytes(html_p, data)
        return html_p, "html"
    raise SystemExit(
        f"{url} returned neither a PDF nor an HTML page (Content-Type: {ctype or '?'}); "
        "nothing cached."
    )


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|h\d|li|tr)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def extract_text(doc_path: Path, kind: str):
    """Extract plain text from a cached document. For PDFs prefer the
    system `pdftotext` (poppler), which produces nicer column-aware
    output than pypdf; fall back to pypdf. HTML pages are stripped
    directly. Returns the .txt path, or None if no extractor worked."""
    txt_path = doc_path.with_suffix(".txt")
    if _has_content(txt_path):
        return txt_path
    if kind == "html":
        _write(txt_path, _html_to_text(_read(doc_path)))
        return txt_path
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        tmp = txt_path.with_name(txt_path.name + ".tmp")
        proc = subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(doc_path), str(tmp)],
            check=False, capture_output=True, text=True,
        )
        if proc.returncode == 0 and _has_content(tmp):
            os.replace(tmp, txt_path)
            return txt_path
        tmp.unlink(missing_ok=True)
        sys.stderr.write(f"WARN: pdftotext failed on {doc_path.name} "
                         f"({proc.stderr.strip() or 'exit ' + str(proc.returncode)}); trying pypdf\n")
    # Fallback: pypdf (slower, less accurate on multi-column layouts)
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.stderr.write(
            "WARN: neither pdftotext nor pypdf could extract text. "
            "Install poppler-utils or `pip install pypdf`.\n"
        )
        return None
    try:
        reader = PdfReader(str(doc_path))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # corrupt / encrypted PDF
        sys.stderr.write(f"WARN: pypdf failed on {doc_path.name}: {e}\n")
        return None
    if not text.strip():
        sys.stderr.write(f"WARN: no extractable text in {doc_path.name} (scanned?)\n")
        return None
    _write(txt_path, text)
    return txt_path


# ---------------------------------------------------------------------------
# CETS number normalisation + ref resolution
# ---------------------------------------------------------------------------

def normalize_num(s):
    """Coerce '5', '005', 'CETS 5', 'ETS no. 5' into the canonical
    3-digit form ('005') used by the Treaty Office."""
    if s is None:
        return None
    s = str(s).strip().lower()
    s = re.sub(r"^(cets|ets|treaty|convention)\b[^0-9]*", "", s)
    s = re.sub(r"^no\.?\s*", "", s)
    s = re.sub(r"^[#\s]+", "", s)
    m = re.match(r"^0*([0-9]{1,3})$", s)
    if m:
        return f"{int(m.group(1)):03d}"
    return None


def _haystack(t) -> str:
    """The searchable text for one index record — shared by `lookup`
    and by the resolver used by fetch/text/... so they agree."""
    return " ".join(filter(None, [
        (t.get("Nom_commun_ENG") or ""),
        (t.get("Libelle_titre_ENG") or ""),
        (t.get("Mention") or ""),
    ])).lower()


def _alias_for(query: str):
    q = query.strip().lower()
    if q in ALIASES:
        return ALIASES[q]
    qs = re.sub(r"[^\w\s+]", " ", q)
    qs = re.sub(r"\s+", " ", qs).strip()
    return ALIASES.get(qs)


def lookup_ref(query):
    """Resolve a free-form query to a CETS number ('005').

    Order of resolution:
      1. Direct numeric (5 / 005 / "ETS 005")
      2. Aliases dict (ECHR, Istanbul, ...)
      3. Fuzzy match against the cached index (Libelle_titre_ENG +
         Nom_commun_ENG + Mention)

    Returns (ref, score, source). Raises SystemExit if nothing matches.
    """
    if query is None:
        raise SystemExit("lookup_ref: empty query")
    n = normalize_num(query)
    if n:
        return (n, 100, "numeric")
    alias = _alias_for(query)
    if alias:
        return (alias, 100, "alias")
    q = query.strip().lower()
    idx = load_index_or_die()
    best = []
    for t in idx:
        ref = t.get("Numero_traite")
        haystack = _haystack(t)
        # Cheap word-set Jaccard score, biased by substring containment
        qw = set(q.split())
        hw = set(haystack.split())
        if not qw or not hw:
            continue
        inter = len(qw & hw)
        if inter == 0 and q not in haystack:
            continue
        contain = 1.0 if q in haystack else 0.0
        score = 100 * (inter / max(len(qw), 1)) + 50 * contain
        best.append((score, ref, t.get("Libelle_titre_ENG", "")))
    if not best:
        raise SystemExit(f"No treaty matches '{query}'. Try `coe.py lookup ...`.")
    best.sort(reverse=True)
    return (best[0][1], int(best[0][0]), "fuzzy")


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _seed_index_if_needed() -> None:
    """Copy the bundled snapshot to the cache dir if no live index exists yet."""
    if _has_content(INDEX_PATH) or not SEED_INDEX.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _write(INDEX_PATH, _read(SEED_INDEX))


def refresh_index(lang=DEFAULT_LANG):
    """Fetch the full treaty list from the API and write index.json."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body = {
        "CodePays": None,
        "NumsSte": [],
        "AnneeOuverture": None,
        "AnneeVigueur": None,
        "CodeLieuSTE": None,
        "CodeMatieres": [],
        "TitleKeywords": [],
    }
    print("fetching api/traites/search …", file=sys.stderr)
    data = api_post("api/traites/search", body, lang=lang)
    print(f"received {len(data)} treaties", file=sys.stderr)
    _dump_json(INDEX_PATH, data)
    print(f"wrote {INDEX_PATH}", file=sys.stderr)
    return data


def cmd_index(args):
    """Build/refresh the master treaty index."""
    _seed_index_if_needed()
    if _has_content(INDEX_PATH) and not args.refresh:
        idx = _load_json(INDEX_PATH)
        print(f"index already cached: {len(idx)} treaties at {INDEX_PATH}")
        print("(use --refresh to rebuild from the live API)")
        return
    refresh_index(lang=args.lang)


def load_index_or_die():
    _seed_index_if_needed()
    if not _has_content(INDEX_PATH):
        raise SystemExit(
            "No cached index. Run: coe.py index"
        )
    return _load_json(INDEX_PATH)


def find_treaty_in_index(idx, ref):
    for t in idx:
        if t.get("Numero_traite") == ref:
            return t
    return None


def resolve_treaty(ref_query, lang=DEFAULT_LANG):
    """Resolve a query to (ref, record). If the number is not in the
    cached index (bundled seed or stale cache), refresh once from the
    live API before giving up — new CETS numbers appear a few times a
    year."""
    idx = load_index_or_die()
    ref, _, _ = lookup_ref(ref_query)
    t = find_treaty_in_index(idx, ref)
    if t is None:
        print(f"ref {ref} not in cached index — refreshing from the live API …", file=sys.stderr)
        try:
            idx = refresh_index(lang=lang)
        except (urllib.error.URLError, OSError) as e:
            raise SystemExit(f"ref {ref} not in index and refresh failed: {e}")
        t = find_treaty_in_index(idx, ref)
    if t is None:
        raise SystemExit(f"ref {ref} not in index (live index has {len(idx)} treaties, "
                         f"highest number {max(x.get('Numero_traite') or '000' for x in idx)})")
    return ref, t


# ---------------------------------------------------------------------------
# Per-treaty meta + payloads
# ---------------------------------------------------------------------------

def treaty_dir(ref):
    d = TREATIES_DIR / ref
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_meta(ref, treaty):
    """Promote a slim subset of fields to meta.json for fast lookup."""
    meta = {k: treaty.get(k) for k in META_FIELDS}
    meta["source_url"] = (
        f"https://www.coe.int/en/web/conventions/full-list"
        f"?module=treaty-detail&treatynum={ref}"
    )
    p = treaty_dir(ref) / "meta.json"
    _dump_json(p, meta)
    return p


def cmd_lookup(args):
    """Fuzzy / alias-based search of the cached index."""
    idx = load_index_or_die()
    q = args.query.strip().lower()
    n = normalize_num(args.query)
    alias = _alias_for(args.query)
    scored = {}  # ref -> (score, label)

    def label(t):
        common = t.get("Nom_commun_ENG") or ""
        title = t.get("Libelle_titre_ENG") or ""
        return f"{common} — {title}" if common and common != title else title

    for t in idx:
        ref = t.get("Numero_traite")
        haystack = _haystack(t)
        score = 0
        if n and ref == n:
            score = 1000
        if alias and ref == alias:
            score = max(score, 1000)
        if q in haystack:
            score += 100
        for w in q.split():
            if w in haystack:
                score += 5
        if score:
            scored[ref] = (score, label(t))
    hits = sorted(((s, ref, lbl) for ref, (s, lbl) in scored.items()), reverse=True)
    if not hits:
        print(f"no match for '{args.query}'")
        return
    for score, ref, title in hits[: args.limit]:
        print(f"  {ref}  {title}")


def _pick_url(t, field: str, lang: str):
    """Return (url, lang_used) for a document field ('traite' or
    'rapex'), falling back to English — and saying so — when the
    requested language is not published."""
    code = LANG_CODE.get(lang, "ENG")
    url = t.get(f"Lien_pdf_{field}_{code}")
    if url:
        return url, lang
    url = t.get(f"Lien_pdf_{field}_ENG")
    if url and lang != "en":
        print(f"note: no {lang} version of the {'treaty text' if field == 'traite' else 'Explanatory Report'} "
              f"for {t.get('Numero_traite')}; using the English one (saved as *.en.*)", file=sys.stderr)
        return url, "en"
    return url, lang


def cmd_text(args):
    """Download the treaty text for one ref + extract."""
    ref, t = resolve_treaty(args.ref, lang=args.lang)
    write_meta(ref, t)
    url, lang_used = _pick_url(t, "traite", args.lang)
    if not url:
        raise SystemExit(f"treaty {ref}: no document URL in index ({t.get('Libelle_titre_ENG')})")
    stem = treaty_dir(ref) / f"text.{lang_used}"
    print(f"downloading {url} -> {stem}.*", file=sys.stderr)
    doc, kind = download_document(url, stem)
    txt = extract_text(doc, kind)
    print(json.dumps({
        "ref": ref,
        "title": t.get("Libelle_titre_ENG"),
        "lang": lang_used,
        "format": kind,
        "document": str(doc),
        "txt": str(txt) if txt else None,
        "source_url": url,
    }, indent=2, ensure_ascii=False))


def cmd_report(args):
    """Download the Explanatory Report for one ref + extract."""
    ref, t = resolve_treaty(args.ref, lang=args.lang)
    write_meta(ref, t)
    url, lang_used = _pick_url(t, "rapex", args.lang)
    if not url:
        print(f"treaty {ref}: no Explanatory Report published "
              f"({t.get('Libelle_titre_ENG')})", file=sys.stderr)
        return
    stem = treaty_dir(ref) / f"report.{lang_used}"
    print(f"downloading {url} -> {stem}.*", file=sys.stderr)
    doc, kind = download_document(url, stem)
    txt = extract_text(doc, kind)
    print(json.dumps({
        "ref": ref,
        "kind": "explanatory_report",
        "lang": lang_used,
        "format": kind,
        "document": str(doc),
        "txt": str(txt) if txt else None,
        "source_url": url,
    }, indent=2, ensure_ascii=False))


def _format_signatures(sigs):
    """Reduce the deeply-nested signatures payload to a grep-friendly
    plain-text table. The API returns three buckets (member states,
    non-member states, organisations) inside an outer list."""
    lines = []
    if not isinstance(sigs, list):
        return ""
    bucket_names = ["Member states", "Non-member states", "Organisations"]
    for i, bucket in enumerate(sigs):
        name = bucket_names[i] if i < len(bucket_names) else f"Group {i}"
        if not isinstance(bucket, list) or not bucket:
            continue
        lines.append(f"\n=== {name} ===")
        for row in bucket:
            country = row.get("LibPaysOrga") or row.get("CodePays") or "?"
            sig = (row.get("DateSignature") or "")[:10]
            cons = (row.get("DateConsentement") or "")[:10]
            eif = (row.get("DateEntreeVigueur") or "")[:10]
            den = (row.get("DateDenonciation") or "")[:10]
            den_eif = (row.get("DateEffetDenonciation") or "")[:10]
            sus = (row.get("DateSuspension") or "")[:10]
            note = []
            if sig: note.append(f"sig={sig}")
            if cons: note.append(f"rat/acc={cons}")
            if eif: note.append(f"eif={eif}")
            if den: note.append(f"denounced={den}")
            if den_eif: note.append(f"den.eif={den_eif}")
            if sus: note.append(f"suspended={sus}")
            flags = []
            if row.get("Reserves"): flags.append("R")
            if row.get("Declarations"): flags.append("D")
            if row.get("Objections"): flags.append("O")
            if row.get("Territoires"): flags.append("T")
            if row.get("Communications"): flags.append("C")
            tag = f"[{''.join(flags)}]" if flags else "   "
            lines.append(f"  {country:<40} {tag} " + " ".join(note))
    return "\n".join(lines).lstrip() + "\n"


def cmd_signatures(args):
    """Download the chart of signatures and ratifications for one ref."""
    ref, t = resolve_treaty(args.ref, lang=args.lang)
    write_meta(ref, t)
    print(f"fetching signatures for {ref} …", file=sys.stderr)
    sigs = api_get("api/signatures", {"NumSte": ref}, lang=args.lang)
    p_json = treaty_dir(ref) / f"signatures.{args.lang}.json"
    _dump_json(p_json, sigs)
    p_txt = treaty_dir(ref) / f"signatures.{args.lang}.txt"
    _write(p_txt, _format_signatures(sigs))
    counts = [len(b) if isinstance(b, list) else 0 for b in (sigs or [])]
    print(json.dumps({
        "ref": ref,
        "title": t.get("Libelle_titre_ENG"),
        "buckets": counts,
        "json": str(p_json),
        "txt": str(p_txt),
        "source_url": (
            f"https://www.coe.int/en/web/conventions/full-list"
            f"?module=signatures-by-treaty&treatynum={ref}"
        ),
    }, indent=2, ensure_ascii=False))


def _strip_html(s):
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _article_key(art: str):
    """Sort articles numerically ('2' before '10'), keeping non-numeric
    labels such as 'Ex-25' after the numbered ones."""
    m = re.match(r"^\s*(\d+)", art or "")
    return (0, int(m.group(1)), art) if m else (1, 0, art or "")


def _format_declarations(decls):
    """Group declarations by state, then by article, in a grep-friendly
    plain-text layout."""
    if not isinstance(decls, list):
        return ""
    by_state = {}
    for d in decls:
        cp = d.get("code_Pays") or {}
        state = cp.get("Value") if isinstance(cp, dict) else None
        org = (d.get("code_Organisation") or {}).get("Libelle")
        if isinstance(org, str) and org.strip().lower() in ("", "null"):
            org = None  # the API sends the literal string "Null" for "no organisation"
        key = state or org or "(no state)"
        by_state.setdefault(key, []).append(d)
    out = []
    for state in sorted(by_state):
        out.append(f"\n=== {state} ===")
        items = by_state[state]

        def sortkey(it):
            return (_article_key(it.get("numero_Article") or ""), it.get("date_Effet") or "")
        for d in sorted(items, key=sortkey):
            nature = d.get("nature_Dec") or ""
            article = d.get("numero_Article") or ""
            eff = (d.get("date_Effet") or "")[:10]
            withdrawn = (d.get("date_Effet_Retrait") or "")[:10]
            head = f"  [{nature}] art. {article}  effect={eff}"
            if withdrawn:
                head += f"  withdrawn={withdrawn}"
            out.append(head)
            txt = _strip_html(d.get("texte_Decl") or "")
            for line in txt.split("\n"):
                if line.strip():
                    out.append(f"      {line.strip()}")
            out.append("")
    return "\n".join(out).lstrip() + "\n"


def cmd_declarations(args):
    """Download all declarations and reservations for one ref.

    The API requires `codeNature`. Passing 0 returns every kind
    (declaration, reservation, derogation, denunciation, withdrawal,
    territorial application, ...)."""
    ref, t = resolve_treaty(args.ref, lang=args.lang)
    write_meta(ref, t)
    print(f"fetching declarations for {ref} …", file=sys.stderr)
    decls = api_get(
        "api/conventions/getDeclarations",
        {"numSte": ref, "codeNature": 0},
        lang=args.lang,
    )
    p_json = treaty_dir(ref) / f"declarations.{args.lang}.json"
    _dump_json(p_json, decls)
    p_txt = treaty_dir(ref) / f"declarations.{args.lang}.txt"
    _write(p_txt, _format_declarations(decls))
    # Tally by nature for the summary line
    natures = {}
    for d in decls or []:
        natures[d.get("nature_Dec") or "?"] = natures.get(d.get("nature_Dec") or "?", 0) + 1
    print(json.dumps({
        "ref": ref,
        "title": t.get("Libelle_titre_ENG"),
        "count": len(decls) if isinstance(decls, list) else 0,
        "by_nature": natures,
        "json": str(p_json),
        "txt": str(p_txt),
        "source_url": (
            f"https://www.coe.int/en/web/conventions/full-list"
            f"?module=declarations-by-treaty&numSte={ref}"
        ),
    }, indent=2, ensure_ascii=False))


def cmd_fetch(args):
    """Combo: resolve a name/number, then pull all four artefacts."""
    ref, score, source = lookup_ref(args.ref)
    print(f"resolved '{args.ref}' -> {ref} (via {source}, score {score})", file=sys.stderr)
    sub = argparse.Namespace(ref=ref, lang=args.lang)
    cmd_text(sub)
    cmd_report(sub)
    cmd_signatures(sub)
    cmd_declarations(sub)


def cmd_show(args):
    """Cat a previously cached extracted-text file."""
    ref, _, _ = lookup_ref(args.ref)
    suffix = {
        "text":         f"text.{args.lang}.txt",
        "report":       f"report.{args.lang}.txt",
        "signatures":   f"signatures.{args.lang}.txt",
        "declarations": f"declarations.{args.lang}.txt",
        "meta":         "meta.json",
    }.get(args.kind)
    if suffix is None:
        raise SystemExit(f"unknown kind: {args.kind}")
    p = treaty_dir(ref) / suffix
    if not _has_content(p):
        raise SystemExit(f"not cached: {p}\n(run `coe.py fetch {ref}` first)")
    sys.stdout.write(_read(p))


# ---------------------------------------------------------------------------
# argparse plumbing
# ---------------------------------------------------------------------------

def main():
    # Treaty titles and declaration texts contain characters outside
    # cp1252; never let the console encoding turn a successful fetch
    # into a crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        prog="coe.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="build/refresh the master treaty index")
    p.add_argument("--refresh", action="store_true",
                   help="re-download even if cached")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=list(LANG_CODE))
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("lookup", help="fuzzy-search the cached index")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_lookup)

    for name, func, helptext in [
        ("text",         cmd_text,         "download treaty text (PDF, or HTML for some translations)"),
        ("report",       cmd_report,       "download Explanatory Report"),
        ("signatures",   cmd_signatures,   "download chart of signatures and ratifications"),
        ("declarations", cmd_declarations, "download declarations and reservations"),
    ]:
        p = sub.add_parser(name, help=helptext)
        p.add_argument("ref", help="CETS number or name (e.g. 005, ECHR, 'Istanbul Convention')")
        p.add_argument("--lang", default=DEFAULT_LANG, choices=list(LANG_CODE))
        p.set_defaults(func=func)

    p = sub.add_parser("fetch", help="resolve and download all four artefacts")
    p.add_argument("ref")
    p.add_argument("--lang", default=DEFAULT_LANG, choices=list(LANG_CODE))
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("show", help="cat a cached extracted-text file")
    p.add_argument("ref")
    p.add_argument("--kind", default="text",
                   choices=["text", "report", "signatures", "declarations", "meta"])
    p.add_argument("--lang", default=DEFAULT_LANG, choices=list(LANG_CODE))
    p.set_defaults(func=cmd_show)

    args = ap.parse_args()
    try:
        return args.func(args)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from {e.url}: {e.reason}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"Network error: {e}")


if __name__ == "__main__":
    main()
