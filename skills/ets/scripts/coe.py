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
  text         Download the treaty text PDF for a given CETS number.
  report       Download the Explanatory Report PDF.
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
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CACHE_DIR = SKILL_ROOT / "cache"
TREATIES_DIR = CACHE_DIR / "treaties"
INDEX_PATH = CACHE_DIR / "index.json"

API_BASE = "https://conventions-ws.coe.int/WS_LFRConventions/"
# Public token embedded in the Treaty Office page source. Required as
# the `token:` HTTP header on every request to the WCF service. Static.
API_TOKEN = "hfghhgp2q5vgwg1hbn532kw71zgtww7e"

USER_AGENT = (
    "ets-skill/0.1 "
    "(treaty research tool, Python-urllib)"
)

# The conventions-ws.coe.int server still serves a small DH key. We
# need to drop OpenSSL to SECLEVEL=0 and allow unsafe legacy
# renegotiation to talk to it. Only this one host needs it.
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
    "Lien_pdf_rapex_ENG",
    "Lien_pdf_rapex_FRE",
    "Lien_html_traite_ENG",
    "Lien_html_rapex_ENG",
    "Mention",
]


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


def download_pdf(url, dest):
    """Download a PDF from rm.coe.int (or anywhere) into `dest`."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest  # idempotent cache
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    req = urllib.request.Request(url, headers=headers)
    # rm.coe.int doesn't need the SECLEVEL=0 dance, but using the same
    # context is harmless.
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=120) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)
    return dest


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path, txt_path=None):
    """Extract text from a PDF, preferring the system `pdftotext`
    (poppler) which produces nicer column-aware output than pypdf."""
    if txt_path is None:
        txt_path = pdf_path.with_suffix(".txt")
    if txt_path.exists() and txt_path.stat().st_size > 0:
        return txt_path
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path), str(txt_path)],
            check=True,
        )
        return txt_path
    # Fallback: pypdf (slower, less accurate on multi-column layouts)
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.stderr.write(
            "WARN: neither pdftotext nor pypdf is available; cannot "
            "extract text. Install poppler-utils or `pip install pypdf`.\n"
        )
        return None
    reader = PdfReader(str(pdf_path))
    with txt_path.open("w", encoding="utf-8") as f:
        for page in reader.pages:
            f.write(page.extract_text() or "")
            f.write("\n\n")
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


def lookup_ref(query):
    """Resolve a free-form query to a CETS number ('005').

    Order of resolution:
      1. Direct numeric (5 / 005 / "ETS 005")
      2. Aliases dict (ECHR, Istanbul, ...)
      3. Fuzzy match against the cached index (Libelle_titre_ENG +
         Nom_commun_ENG)

    Returns (ref, score, source). Raises SystemExit if nothing matches.
    """
    if query is None:
        raise SystemExit("lookup_ref: empty query")
    n = normalize_num(query)
    if n:
        return (n, 100, "numeric")
    q = query.strip().lower()
    if q in ALIASES:
        return (ALIASES[q], 100, "alias")
    # Stripped alias (no punctuation)
    qs = re.sub(r"[^\w\s]", " ", q)
    qs = re.sub(r"\s+", " ", qs).strip()
    if qs in ALIASES:
        return (ALIASES[qs], 100, "alias")
    # Fuzzy: build a list of (score, ref, title) over the cached index
    if not INDEX_PATH.exists():
        raise SystemExit(
            "Index not built yet. Run: coe.py index\n"
            f"(missing {INDEX_PATH})"
        )
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    best = []
    for t in idx:
        ref = t.get("Numero_traite")
        haystack = " ".join(filter(None, [
            (t.get("Nom_commun_ENG") or ""),
            (t.get("Libelle_titre_ENG") or ""),
            (t.get("Mention") or ""),
        ])).lower()
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

def cmd_index(args):
    """Build/refresh the master treaty index."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_PATH.exists() and not args.refresh:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        print(f"index already cached: {len(idx)} treaties at {INDEX_PATH}")
        print("(use --refresh to rebuild)")
        return
    body = {
        "CodePays": None,
        "NumsSte": [],
        "AnneeOuverture": None,
        "AnneeVigueur": None,
        "CodeLieuSTE": None,
        "CodeMatieres": [],
        "TitleKeywords": [],
    }
    print("fetching api/traites/search …")
    data = api_post("api/traites/search", body, lang=args.lang)
    print(f"received {len(data)} treaties")
    INDEX_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"wrote {INDEX_PATH}")


def load_index_or_die():
    if not INDEX_PATH.exists():
        raise SystemExit(
            "No cached index. Run: coe.py index"
        )
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def find_treaty_in_index(idx, ref):
    for t in idx:
        if t.get("Numero_traite") == ref:
            return t
    return None


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
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return p


def cmd_lookup(args):
    """Fuzzy / alias-based search of the cached index."""
    idx = load_index_or_die()
    q = args.query.strip().lower()
    n = normalize_num(args.query)
    hits = []
    for t in idx:
        ref = t.get("Numero_traite")
        title = t.get("Libelle_titre_ENG") or ""
        common = t.get("Nom_commun_ENG") or ""
        haystack = (title + " " + common).lower()
        score = 0
        if n and ref == n:
            score = 1000
        if q in haystack:
            score += 100
        for w in q.split():
            if w in haystack:
                score += 5
        if score:
            hits.append((score, ref, common or title))
    # Boost any direct alias hit
    if q in ALIASES:
        hits.append((1000, ALIASES[q], "(alias hit)"))
    hits.sort(reverse=True)
    if not hits:
        print(f"no match for '{args.query}'")
        return
    for score, ref, title in hits[: args.limit]:
        print(f"  {ref}  {title}")


def cmd_text(args):
    """Download the treaty text PDF for one ref + extract."""
    idx = load_index_or_die()
    ref, _, _ = lookup_ref(args.ref)
    t = find_treaty_in_index(idx, ref)
    if t is None:
        raise SystemExit(f"ref {ref} not in index")
    write_meta(ref, t)
    url = t.get(f"Lien_pdf_traite_{LANG_CODE.get(args.lang, 'ENG')}") or t.get("Lien_pdf_traite_ENG")
    if not url:
        raise SystemExit(f"treaty {ref}: no PDF URL in index ({t.get('Libelle_titre_ENG')})")
    pdf = treaty_dir(ref) / f"text.{args.lang}.pdf"
    print(f"downloading {url} -> {pdf}")
    download_pdf(url, pdf)
    txt = extract_pdf_text(pdf)
    print(json.dumps({
        "ref": ref,
        "title": t.get("Libelle_titre_ENG"),
        "pdf": str(pdf),
        "txt": str(txt) if txt else None,
        "source_url": url,
    }, indent=2))


def cmd_report(args):
    """Download the Explanatory Report PDF for one ref + extract."""
    idx = load_index_or_die()
    ref, _, _ = lookup_ref(args.ref)
    t = find_treaty_in_index(idx, ref)
    if t is None:
        raise SystemExit(f"ref {ref} not in index")
    write_meta(ref, t)
    url = t.get(f"Lien_pdf_rapex_{LANG_CODE.get(args.lang, 'ENG')}") or t.get("Lien_pdf_rapex_ENG")
    if not url:
        print(f"treaty {ref}: no Explanatory Report published "
              f"({t.get('Libelle_titre_ENG')})", file=sys.stderr)
        return
    pdf = treaty_dir(ref) / f"report.{args.lang}.pdf"
    print(f"downloading {url} -> {pdf}")
    download_pdf(url, pdf)
    txt = extract_pdf_text(pdf)
    print(json.dumps({
        "ref": ref,
        "kind": "explanatory_report",
        "pdf": str(pdf),
        "txt": str(txt) if txt else None,
        "source_url": url,
    }, indent=2))


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
    return "\n".join(lines).lstrip()


def cmd_signatures(args):
    """Download the chart of signatures and ratifications for one ref."""
    idx = load_index_or_die()
    ref, _, _ = lookup_ref(args.ref)
    t = find_treaty_in_index(idx, ref)
    if t is None:
        raise SystemExit(f"ref {ref} not in index")
    write_meta(ref, t)
    print(f"fetching signatures for {ref} …")
    sigs = api_get("api/signatures", {"NumSte": ref}, lang=args.lang)
    p_json = treaty_dir(ref) / f"signatures.{args.lang}.json"
    p_json.write_text(json.dumps(sigs, indent=2, ensure_ascii=False))
    p_txt = treaty_dir(ref) / f"signatures.{args.lang}.txt"
    p_txt.write_text(_format_signatures(sigs))
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
    }, indent=2))


def _strip_html(s):
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


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
        key = state or org or "(no state)"
        by_state.setdefault(key, []).append(d)
    out = []
    for state in sorted(by_state):
        out.append(f"\n=== {state} ===")
        items = by_state[state]
        # Sort: by article number then date
        def sortkey(it):
            art = it.get("numero_Article") or ""
            return (art, it.get("date_Effet") or "")
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
    return "\n".join(out).lstrip()


def cmd_declarations(args):
    """Download all declarations and reservations for one ref.

    The API requires `codeNature`. Passing 0 returns every kind
    (declaration, reservation, derogation, denunciation, withdrawal,
    territorial application, ...)."""
    idx = load_index_or_die()
    ref, _, _ = lookup_ref(args.ref)
    t = find_treaty_in_index(idx, ref)
    if t is None:
        raise SystemExit(f"ref {ref} not in index")
    write_meta(ref, t)
    print(f"fetching declarations for {ref} …")
    decls = api_get(
        "api/conventions/getDeclarations",
        {"numSte": ref, "codeNature": 0},
        lang=args.lang,
    )
    p_json = treaty_dir(ref) / f"declarations.{args.lang}.json"
    p_json.write_text(json.dumps(decls, indent=2, ensure_ascii=False))
    p_txt = treaty_dir(ref) / f"declarations.{args.lang}.txt"
    p_txt.write_text(_format_declarations(decls))
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
    }, indent=2))


def cmd_fetch(args):
    """Combo: resolve a name/number, then pull all four artefacts."""
    if not INDEX_PATH.exists():
        # Auto-build the index on first run
        print("(no cached index — building one first)")
        ns = argparse.Namespace(refresh=False, lang=args.lang)
        cmd_index(ns)
    ref, score, source = lookup_ref(args.ref)
    print(f"resolved '{args.ref}' -> {ref} (via {source}, score {score})")
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
    if not p.exists():
        raise SystemExit(f"not cached: {p}\n(run `coe.py fetch {ref}` first)")
    sys.stdout.write(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# argparse plumbing
# ---------------------------------------------------------------------------

def main():
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
        ("text",         cmd_text,         "download treaty text PDF"),
        ("report",       cmd_report,       "download Explanatory Report PDF"),
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
    return args.func(args)


if __name__ == "__main__":
    main()
