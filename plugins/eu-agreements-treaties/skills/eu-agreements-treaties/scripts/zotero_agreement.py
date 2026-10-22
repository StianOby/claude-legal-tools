#!/usr/bin/env python3
"""
zotero_agreement.py — a Zotero-ready item for one agreement in the Council's
Treaties Office database.

    python3 zotero_agreement.py --record-b64 <b64> --out DIR

<b64> is the `b64` string `await __cs.zotero("<7-digit id>")` returns in the
browser tab: the database's record as base64 JSON (the database answers only
a real browser, so this script never contacts it). The rest comes from the EU Publications Office's SPARQL
endpoint (Cellar, the database behind EUR-Lex), which the cloud sandbox can
reach: the agreement's CELEX number, ELI, first OJ page and the English PDF.
Writes into DIR:

    <base>.pdf          the English text as published in the Official Journal
    <base>.rdf          Zotero RDF — drag into Zotero; the PDF must sit beside it
    <base>.zotero.json  the same item for Zoteus's zotero_create_items

The item is a Zotero `statute`, following the Dublin and Schengen items in
the shared group library "Norsk henvisningsstandard for rettsvitenskapelige
tekster - eksempler":

    nameOfAct    the title, without the database's editorial insertions
    code         "EUT 2001 L" (OJ year and series); "EUT L" for acts in the
                 act-by-act OJ (since October 2023)
    pages        "93/40" (issue/first page); "2024/2603" in the act-by-act OJ
    dateEnacted  the agreement-level entry into force; empty when not in force
    url          the ELI
    extra        type: treaty / available-date: <signature> / provisional
                 application / status / CELEX / Consilium ID / depositary

How the OJ publication is found: the database lists every OJ reference of an
agreement (its text, but also Council decisions, notices of entry into force,
corrigenda, amendments). Every CELEX number an agreement in those issues can
have is looked up at once (exact values: patterns take minutes on Cellar),
plus those numbered after the signature date (older agreements); candidates
are ranked by signature date, then title. The probe of 37 agreements
(2026-10-21, tests/eu-agreements-treaties/fixtures/probe-2026-10-21.json)
showed why each rule is needed.

A missing PDF is reported with a line starting "PDF NOT ATTACHED:"; a field
the sources could not supply, or a match to check, with "NOTE:".
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import zotero_rdf   # noqa: E402  (after sys.path mutation)

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
ENG = "<http://publications.europa.eu/resource/authority/language/ENG>"
XSD = "http://www.w3.org/2001/XMLSchema#"
UA = "claude-legal-tools eu-agreements-treaties (zotero_agreement.py)"
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


# --------------------------------------------------------------------------
# The database's record
# --------------------------------------------------------------------------

def clean_title(title: str) -> tuple:
    """(title, depositary, notes) without the database's editorial insertions:
    "- See 2014013 (EEA Agreement)", "(BG/ES/DA/…)", "(including the …)" and
    "(Deposited with the Government of …)", which becomes the depositary."""
    notes = []
    t = " ".join((title or "").split())
    t = re.sub(r"\s+-\s+See \d{7}\b.*$", "", t)
    t = re.sub(r"\s*\((?:[A-Z]{2}/)+[A-Z]{2}\)", "", t)
    m = re.search(r"\s*\(including (?:the )?[^()]*\)\.?$", t, flags=re.I)
    if m:
        notes.append("the database lists this record as a bundle of several instruments "
                     "(\"(including …)\"); the item describes the main agreement")
        t = t[:m.start()]
    dep = None
    m = re.search(r"\s*\((?:deposited with|depositary:?)\s+(?:the\s+)?([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$",
                  t, flags=re.I)
    if m:
        dep, t = m.group(1).strip(), t[:m.start()]
    return t.strip(" ."), dep, notes


def provisional_date(observations: Optional[str]) -> str:
    """'Provisional application as from 1 August 2016 (…)' or '… as of
    15/07/2026' -> ISO date; '' when there is none."""
    obs = observations or ""
    m = re.search(r"provisional(?:ly)? appli\w*[^.;]*?\b(?:as )?(?:from|of)\s+"
                  r"(\d{1,2})[ /.]([A-Za-z]+|\d{1,2})[ /.](\d{4})", obs, flags=re.I)
    if not m:
        return ""
    day, month, year = m.groups()
    month = _MONTHS.get(month.lower()) if not month.isdigit() else int(month)
    return f"{year}-{month:02d}-{int(day):02d}" if month else ""


def parse_oj(o: dict) -> Optional[dict]:
    """An OJ reference from __cs.zotero(): {series, year, issue | number,
    date}. Parsed again from its text when the helper could not."""
    if o.get("series") and o.get("year") and (o.get("issue") or o.get("number")) and o.get("date"):
        return o
    text = o.get("text") or ""
    d = re.search(r"\((\d{2})/(\d{2})/(\d{4})\)", text)
    if not d:
        return None
    date = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"
    m = re.match(r"([A-Z]),\s*(\d{4})/(\d+)", text)
    if m:
        return {"series": m.group(1), "year": m.group(2), "number": m.group(3), "date": date, "text": text}
    m = re.match(r"([A-Z])\s+(\d+[A-Z]?)\b", text)
    if m:
        return {"series": m.group(1), "year": d.group(3), "issue": m.group(2), "date": date, "text": text}
    return None


# --------------------------------------------------------------------------
# Cellar
# --------------------------------------------------------------------------

def sparql(query: str, timeout: int = 90) -> list:
    """POST (the CELEX lists are too long for a GET), with three retries:
    the endpoint answers 503 now and then under load (2026-10-22)."""
    body = urllib.parse.urlencode({"query": query, "format": "application/sparql-results+json"}).encode()
    for wait in (2, 5, 10, None):
        req = urllib.request.Request(SPARQL, data=body, headers={
            "Accept": "application/sparql-results+json", "User-Agent": UA,
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


def celex_candidates(ref: Optional[dict] = None, signature: str = "") -> list:
    """Every CELEX number an agreement can have in this OJ reference (or,
    for older agreements, numbered after its signature date), in sectors 1
    (treaties), 2 (international agreements) and 4 (other)."""
    if ref and ref.get("number"):
        return [f"{s}{ref['year']}A{int(ref['number']):05d}" for s in "124"]
    date = (ref or {}).get("date") or signature
    if not date:
        return []
    y, m, d = date.split("-")
    return [f"{s}{y}A{m}{d}({i:02d})" for s in "124" for i in range(1, 100)]


# The OJ issue an act was published in: number, year and, in its document
# id ("oj:JOL_1973_133_R"), the series. Older agreements have no other route
# to it: their CELEX number carries the signature date, not the OJ date.
_OJ_ISSUE = """
  OPTIONAL {{ ?work cdm:resource_legal_published_in_official-journal ?ojr .
             ?ojr cdm:official-journal_number ?ojnum ; cdm:official-journal_year ?ojyear ;
                  cdm:work_id_document ?ojid . FILTER(STRSTARTS(STR(?ojid), "oj:JO")) }}"""


def cellar_works(celexes: list) -> dict:
    """{celex: {title, type, eli, sig, page, ojnum, ojyear, ojid}} for the
    CELEX numbers that exist, English title and first OJ page included."""
    out = {}
    for i in range(0, len(celexes), 300):
        vals = " ".join(f'"{c}"^^<{XSD}string>' for c in celexes[i:i + 300])
        q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?type ?title ?eli ?sig ?page ?ojnum ?ojyear ?ojid WHERE {{
  VALUES ?celex {{ {vals} }}
  ?work cdm:resource_legal_id_celex ?celex ; cdm:resource_legal_type ?type .
  ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language {ENG} ;
        cdm:expression_title ?title .
  OPTIONAL {{ ?work cdm:resource_legal_eli ?eli }}
  OPTIONAL {{ ?work cdm:resource_legal_date_signature ?sig }}
  OPTIONAL {{ ?man cdm:manifestation_manifests_expression ?expr ;
                  cdm:manifestation_official-journal_part_page_first ?page }}{_OJ_ISSUE.format()}
}}"""
        for b in sparql(q):
            out.setdefault(b["celex"]["value"], {k: v["value"] for k, v in b.items()})
    return out


def works_signed_on(date: str) -> dict:
    """Fallback for an OJ reference with a wrong date in the database (seen:
    "L 350 (22/01/2016)" for 22 December): agreements signed that day."""
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?type ?title ?eli ?sig ?page ?ojnum ?ojyear ?ojid WHERE {{
  ?work cdm:resource_legal_date_signature "{date}"^^<{XSD}date> ;
        cdm:resource_legal_id_celex ?celex ; cdm:resource_legal_type ?type .
  BIND("{date}" AS ?sig)
  ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language {ENG} ;
        cdm:expression_title ?title .
  OPTIONAL {{ ?work cdm:resource_legal_eli ?eli }}
  OPTIONAL {{ ?man cdm:manifestation_manifests_expression ?expr ;
                  cdm:manifestation_official-journal_part_page_first ?page }}{_OJ_ISSUE.format()}
}}"""
    out = {}
    for b in sparql(q):
        out.setdefault(b["celex"]["value"], {k: v["value"] for k, v in b.items()})
    return out


def english_pdf_url(celex: str) -> Optional[str]:
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?mtype ?item WHERE {{
  ?work cdm:resource_legal_id_celex "{celex}"^^<{XSD}string> .
  ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language {ENG} .
  ?man cdm:manifestation_manifests_expression ?expr ; cdm:manifestation_type ?mtype .
  ?item cdm:item_belongs_to_manifestation ?man .
}}"""
    items = [(b["mtype"]["value"], b["item"]["value"]) for b in sparql(q)]
    for want in ("pdfa2a", "pdfa1a", "pdfa1b", "pdf", "pdfx"):
        for mtype, item in sorted(items):
            if mtype == want:
                # Cellar names its items http://; Zoteus on a hosted server
                # accepts only https links, which the same host serves.
                return re.sub(r"^http://", "https://", item)
    return None


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def key(title: str) -> str:
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\([^()]*\)", " ", t)
    return " ".join(re.findall(r"[a-z0-9]+", t))


def similarity(ours: str, theirs: str) -> float:
    """Cellar appends parts after " - " ("Agreement on the European Economic
    Area - Final Act - …", "… - Protocol 1 …") and sometimes shortens
    ("Air Transport Agreement"); compare the head, and count a title that
    is the start of the other as a strong match."""
    a, full, head = key(ours), key(theirs), key(theirs.split(" - ")[0])
    if a in (full, head):
        return 1.0
    # "Final Act of the … Conference - Annex 1: The Energy Charter Treaty - …"
    bare = re.sub(r"^the ", "", a)
    if any(re.sub(r"^the ", "", key(seg)) == bare for seg in re.split(r"\s+-\s+|:\s+", theirs)):
        return 1.0
    if len(head) >= 20 and (a.startswith(head) or head.startswith(a)):
        return 0.95
    return max(SequenceMatcher(None, a, head).ratio(), SequenceMatcher(None, a, full).ratio())


_NOT_NAMES = {
    "Agreement", "Agreements", "Protocol", "Protocols", "Convention", "Arrangement", "Exchange",
    "Letters", "Additional", "Supplementary", "Annex", "Annexes", "Final", "Act", "Joint",
    "Declaration", "Declarations", "Member", "States", "State", "Party", "Parties", "Part",
    "Article", "Articles", "The", "Cooperation", "Co-operation", "Memorandum", "Understanding",
}


def names(title: str) -> set:
    """Capitalised words after the first, lower-cased: the parties and other
    names. None from a title in capitals, where every word looks like one."""
    if not title or title.isupper():
        return set()
    # Abbreviations in brackets ("(EMCDDA)", "(US-EU-01)") are not parties.
    words = re.findall(r"[A-Z][\w'-]{2,}", re.sub(r"\([^()]*\)", " ", title))[1:]
    return {w.lower() for w in words if w not in _NOT_NAMES}


def name_conflict(ours: str, theirs: str) -> bool:
    """Each title names something the other does not mention at all: "… the
    European Union and Iceland laying down …" / "… and the Kingdom of Norway
    laying down …", signed the same day with otherwise identical titles. A
    title that only lacks names ("Air Transport Agreement") is no conflict,
    nor is a difference in case ("cross-servicing" / "Cross-Servicing")."""
    words_a, words_b = set(key(ours).split()), set(key(theirs).split())
    only_a = {n for n in names(ours) if not set(key(n).split()) <= words_b}
    only_b = {n for n in names(theirs) if not set(key(n).split()) <= words_a}
    return bool(only_a) and bool(only_b)


def contained(ours: str, theirs: str) -> float:
    """Share of our title's words in theirs: "Energy Charter Treaty" in
    "Final Act of the … Conference - Annex 1: The Energy Charter Treaty"."""
    a = set(w for w in key(ours).split() if len(w) > 2)
    b = set(key(theirs).split())
    return len(a & b) / len(a) if a else 0.0


def _page_int(w: dict) -> int:
    try:
        return int(w.get("page") or 10 ** 6)
    except ValueError:
        return 10 ** 6


def pick(rec: dict, works: dict) -> tuple:
    """(celex, work, sure) — the agreement itself among the candidates. A
    conflicting signature date rules a candidate out (Lugano 1988 against
    Lugano 2007); then signature date, title, an agreement (type A), and
    the lowest page (the main text before its protocols)."""
    sig = rec.get("signature")
    ranked = []
    for celex, w in works.items():
        s = None if not (sig and w.get("sig")) else w["sig"] == sig
        if s is False or name_conflict(rec["title"], w["title"]):
            continue
        sim = similarity(rec["title"], w["title"])
        # With the signature date confirmed, our title's words all being in
        # theirs also counts ("Agreement with Iceland and Norway concerning
        # the latters' association …" / "Agreement concluded by the Council
        # … and Iceland and Norway concerning the latters' association …").
        if s is True:
            sim = max(sim, 0.9 * contained(rec["title"], w["title"]))
        ranked.append((s is True, round(sim, 2), w.get("type") == "A", -_page_int(w), celex))
    if not ranked:
        return None, None, False
    ranked.sort(reverse=True)
    sig_ok, sim, _, _, celex = ranked[0]
    # 0.6: a related agreement signed the same day scored 0.50 (2014030).
    if not ((sig_ok and sim >= 0.6) or sim >= 0.8):
        return None, None, False
    return celex, works[celex], sig_ok and sim >= 0.8


# --------------------------------------------------------------------------
# The item
# --------------------------------------------------------------------------

def oj_citation(celex: str, work: dict, refs: list) -> tuple:
    """(code, pages) for the library's pattern: "EUT 2001 L" + "93/40", or
    "EUT L" + "2024/2603" in the act-by-act OJ."""
    m = re.fullmatch(r"\d(\d{4})A(\d{5})", celex)
    if m:   # act-numbered OJ: 22024A02603
        ref = next((r for r in refs if r.get("number") and int(r["number"]) == int(m.group(2))), None)
        series = ref["series"] if ref else "L"
        return f"EUT {series}", f"{m.group(1)}/{int(m.group(2))}"
    page = str(int(work["page"])) if (work.get("page") or "").isdigit() else None
    if work.get("ojnum") and work.get("ojyear") and work.get("ojid"):
        series = work["ojid"][len("oj:JO")]                 # oj:JOL_… / oj:JOC_…
        year, issue = work["ojyear"], work["ojnum"].lstrip("0") or work["ojnum"]
    else:
        # No issue in Cellar: the database's reference published on the
        # date the CELEX number carries, if there is one.
        m = re.fullmatch(r"\d(\d{4})A(\d{2})(\d{2})\(\d+\)", celex)
        oj_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
        ref = next((r for r in refs if r.get("date") == oj_date and r.get("issue")), None)
        if not ref:
            return None, None
        series, year, issue = ref["series"], ref["year"], ref["issue"].lstrip("0") or ref["issue"]
    return f"EUT {year} {series}", f"{issue}/{page}" if page else issue


def build_item(rec: dict, match: Optional[tuple], today: str = "") -> tuple:
    today = today or _dt.date.today().isoformat()
    notes = []
    title, depositary, title_notes = clean_title(rec.get("title") or "")
    notes += title_notes
    refs = [r for r in (parse_oj(o) for o in rec.get("oj") or []) if r]
    celex, work = (match or (None, None))[:2]
    if work and title.isupper():   # "REGIONAL CONVENTION ON …": Cellar has it in normal case
        title = work["title"].split(" - ")[0].strip()

    item = {"itemType": "statute", "nameOfAct": title}
    if celex:
        code, pages = oj_citation(celex, work, refs)
        if code:
            item["code"] = code
            item["pages"] = pages
            if "/" not in pages:
                notes.append("the first page of the agreement in the OJ issue is not in Cellar; add it by hand")
    else:
        listed = "; ".join(o.get("text", "").rstrip(";") for o in rec.get("oj") or []) or "none"
        notes.append("the OJ publication of the agreement could not be identified (OJ references in the "
                     f"database: {listed}); add the citation by hand")
    if rec.get("entry_into_force"):
        item["dateEnacted"] = rec["entry_into_force"]
    if (work or {}).get("eli"):
        item["url"] = work["eli"]
    elif celex:
        # Older agreements have no ELI; the EUR-Lex address by CELEX is the
        # stable link to the same text.
        item["url"] = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
    else:
        item["url"] = rec.get("url")
        notes.append("no ELI or CELEX found; the URL is the Treaties Office record")
    item["language"] = "English"

    extra = ["type: treaty"]
    if rec.get("signature"):
        extra.append(f"available-date: {rec['signature']}")
    prov = provisional_date(rec.get("observations"))
    if prov:
        extra.append(f"provisional application: {prov}")
    if not rec.get("entry_into_force"):
        extra.append(f"status: {'provisionally applied, ' if prov else ''}not in force (as of {today}; "
                     "EU perspective, Council Treaties Office)")
    if celex:
        extra.append(f"CELEX: {celex}")
    extra.append(f"Consilium: {rec['id']}")
    if depositary:
        extra.append(f"depositary: {depositary}")
    item["extra"] = "\n".join(extra)
    return item, notes


def basename(item: dict) -> str:
    """EUT_2016_L_141_3_Agreement_between_the_European_Union_Iceland…"""
    s = unicodedata.normalize("NFKD", item["nameOfAct"]).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    if len(s) > 60:
        s = s[:61].rsplit("_", 1)[0]
    cite = re.sub(r"[^A-Za-z0-9]+", "_", f"{item.get('code', '')} {item.get('pages', '')}").strip("_")
    return f"{cite}_{s}" if cite else s


def find_match(rec: dict) -> Optional[tuple]:
    # Match on the title without "(Deposited with the Government of …)" etc.
    rec = dict(rec, title=clean_title(rec.get("title") or "")[0])
    refs = [r for r in (parse_oj(o) for o in rec.get("oj") or []) if r]
    cands = []
    for r in refs:
        cands += celex_candidates(r)
    if rec.get("signature"):
        cands += celex_candidates(signature=rec["signature"])
    works = cellar_works(sorted(set(cands))) if cands else {}
    celex, work, sure = pick(rec, works)
    if not celex and rec.get("signature"):
        celex, work, sure = pick(rec, works_signed_on(rec["signature"]))
    return (celex, work, sure) if celex else None


def load_record(b64: Optional[str] = None, path: Optional[str] = None) -> dict:
    """The record from __cs.zotero(): its `b64` string (base64 UTF-8 JSON),
    or a JSON file."""
    if b64:
        return json.loads(base64.b64decode(b64.strip()).decode("utf-8"))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--record-b64", help="the `b64` string __cs.zotero(id) returned")
    src.add_argument("--record", help="a JSON file holding the decoded record")
    ap.add_argument("--out", required=True, help="Folder for the .pdf + .rdf pair.")
    args = ap.parse_args(argv)

    rec = load_record(b64=args.record_b64, path=args.record)
    if rec.get("is_proces_verbal"):
        raise SystemExit("this record is a Procès-Verbal of Rectification (a correction to language "
                         "versions), not an agreement: make the item for the agreement it corrects")

    try:
        match = find_match(rec)
    except OSError as e:
        print(f"NOTE: the EU Publications Office (Cellar) could not be reached ({e}); "
              "the item has no OJ citation, ELI or PDF")
        match = None
    item, notes = build_item(rec, match)
    if match and not match[2]:
        notes.append(f"matched to CELEX {match[0]} \"{match[1]['title'][:120]}\" on a weak title match; "
                     "check it is the same agreement")
    base = basename(item)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[meta] {item['nameOfAct']}")
    print(f"[meta] {item.get('code', '')} {item.get('pages', '')}  CELEX {match[0] if match else '—'}")
    print(f"[meta] entry into force: {item.get('dateEnacted') or 'none recorded'}")

    pdf_name, pdf_url, missing = None, None, "no English PDF of the agreement in Cellar"
    if match:
        try:
            pdf_url = english_pdf_url(match[0])
            if pdf_url:
                req = urllib.request.Request(pdf_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = r.read()
                if data.startswith(b"%PDF"):
                    pdf_name = f"{base}.pdf"
                    (out_dir / pdf_name).write_bytes(data)
                    print(f"[pdf] {out_dir / pdf_name}")
                else:
                    missing = "Cellar did not return a PDF"
        except OSError as e:
            missing = f"the PDF could not be downloaded from Cellar ({e})"
    else:
        missing = "the agreement's OJ publication could not be identified"
    for n in notes:
        print(f"NOTE: {n}")
    zotero_rdf.write_zotero_files(item, out_dir, base, pdf_filename=pdf_name, missing_reason=missing,
                                  item_id=re.sub(r"[^a-z0-9_]", "_", base.lower()), pdf_url=pdf_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
