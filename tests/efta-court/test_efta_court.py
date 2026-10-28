#!/usr/bin/env python3
"""Offline tests for scripts/efta_court.py (no network). The fixtures have
the shape of the api.eftacourt.int records (October 2026), with private
parties anonymised. Run: python tests/efta-court/test_efta_court.py
"""

import argparse
import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

os.environ["EFTA_COURT_CACHE_DIR"] = tempfile.mkdtemp()
SKILL = Path(__file__).resolve().parents[2] / "plugins" / "efta-court" / "skills" / "efta-court"
sys.path.insert(0, str(SKILL / "scripts"))
import efta_court as ec  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def raises(fn):
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            fn()
    except SystemExit:
        return True
    return False


FILE = "https://efta_back.on-forge.com/storage/imports/{}.pdf"


def dl(i, doc_type, lang="English", title="", date="2024-01-01", category="Cases", file=None):
    return {"id": i, "title": title or f"{doc_type} ({ec.LANGS.get(lang, 'XX')})", "category": category,
            "docType": doc_type, "language": lang, "date": date, "file": file or FILE.format(i), "showDate": True}


def case(i, ref, parties, docs, **kw):
    rec = {"id": i, "ref": ref, "parties": parties, "status": "Decided", "type": "Advisory Opinion",
           "procedure": "Request for an advisory opinion", "source": "Norway", "referringCourt": "",
           "language": "Norwegian", "subjectMatter": [], "keywords": "", "description": "", "diary": [],
           "dateSubmitted": "", "hearingDate": "", "judgmentDate": "", "publishedIn": "", "documents": docs}
    rec.update(kw)
    return rec


DOWNLOADS = [
    dl("dc-1-0", "Notification"), dl("dc-1-1", "Judgment"), dl("dc-1-2", "Judgment", "Norwegian"),
    dl("dc-1-3", "Press Release"), dl("dc-1-4", "Order of the Court"), dl("dc-1-5", "Order of the President"),
    dl("dc-1-6", "Report for the Hearing", date="2023-07-28"), dl("dc-1-7", "Report for the Hearing", date=None),
    dl("dc-2-0", "Notification"), dl("dc-3-0", "Notification"),
    dl("dc-4-0", "Judgment", file=FILE.format("same")), dl("dc-5-0", "Judgment", file=FILE.format("same")),
    dl("dc-6-0", "Order of the Court"),
    dl("pd-1", "Press Release", category="Press", title="Judgment in Case E-1/24 – Person A v Company B"),
    dl("pd-2", "Judgment", category="Press", title="Judgment in Case E-1/24"),
    dl("pd-8855", "Press Release", category="Press", title="EFTA Court Texts (EN)"),
    dl("pd-8859", "Press Release", "Norwegian", category="Press", title="EFTA Court Texts (NO)"),
    dl("pr-doc-rules-of-procedure-0", "Legal Text", category="Procedure", title="Rules of Procedure (EN)", date=None),
    dl("pr-doc-rules-of-procedure-2", "Legal Text", "Norwegian", category="Procedure", title="Rules of Procedure (NO)", date=None),
    dl("pr-doc-previous-rules-of-procedure-0", "Legal Text", category="Procedure",
       title="Rules of Procedure of the EFTA Court (EN)", date=None),
    dl("pr-doc-rules-of-procedure-4", "Legal Text", category="Procedure",
       title="Decision of the Court on remote oral hearings", date=None),
    dl("ee-doc", "Guide", category="e-EFTACourt", title="e-EFTACourt Portal – User Guide", date=None),
    dl("d1003", "Notification", title="25_25_PR_DE"),
]
OBS = "https://efta_back.on-forge.com/storage/imports/obs1.pdf"
CASES = [
    case("c-wp-1", "E-1/24", "Person A v Company B",
         ["dc-1-0", "dc-1-1", "dc-1-2", "dc-1-3", "dc-1-4", "dc-1-5", "dc-1-6", "dc-1-7"],
         diary=[{"date": "2024-03-01", "category": 0, "description": "Written observations received from the Government of Norway",
                 "docs": [{"url": OBS, "label": "Government of Norway"}]},
                {"date": "2024-03-02", "category": 0, "description": "Written observations received from the European Commission",
                 "docs": [{"url": OBS.replace("obs1", "obs2"), "label": "European Commission"}]}]),
    case("c-wp-2", "E-7/24", "Person C", ["dc-2-0"], source="Liechtenstein"),
    case("c-wp-3", "Joined Cases E-1/24 and E-7/24", "Person A v Company B", ["dc-3-0"]),
    case("c-wp-4", "E-8/94", "Company D v Company E", ["dc-4-0"]),
    case("c-wp-5", "E-8/94 and E-9/94", "Company D v Company E", ["dc-5-0"]),
    case("c-wp-6", "E-9/04 COSTS", "EFTA Surveillance Authority v Company F", ["dc-6-0"], type="Other",
         procedure=None, source=""),
    case("c-wp-7", "E-2/26", "EFTA Surveillance Authority v Iceland", [], type="Direct Action",
         procedure="Infringement Proceedings", source="", status="Pending"),
    case("c-wp-8", "E-3/26", "Company G v EFTA Surveillance Authority", [], type="Direct Action",
         procedure="Action for annulment", source=""),
    case("c-wp-9", "E-4/26", "Company H v Company I", [], source="", referringCourt="",
         description="<p>Request from the Princely Court of Appeal (Fürstliches Obergericht), Liechtenstein</p>"),
]
PROCEDURES = [
    {"id": "pr-rules-of-procedure", "title": "Rules of Procedure", "order": 2, "body": "",
     "documents": ["pr-doc-rules-of-procedure-0", "pr-doc-rules-of-procedure-2"]},
    {"id": "pr-previous-rules-of-procedure", "title": "Previous Rules of Procedure", "order": 3, "body": "",
     "documents": ["pr-doc-previous-rules-of-procedure-0"]},
    {"id": "pr-decisions-on-procedural-issues", "title": "Decisions", "order": 6, "body": "",
     "documents": ["pr-doc-rules-of-procedure-4"]},
    {"id": "pr-collection-of-procedural-texts", "title": "Collection", "order": 7, "body": "<p>short</p>",
     "documents": ["pd-8855", "pd-8859"]},
    {"id": "pr-surveillance-and-court-agreement", "title": "Surveillance and Court Agreement", "order": 0,
     "body": "<h3>Article 1</h3>\n<p>" + "The EFTA States shall establish a Court. " * 60 + "</p>", "documents": []},
]
DATA = {"api": "https://api.eftacourt.int/api", "cases": CASES, "downloads": DOWNLOADS,
        "procedures": PROCEDURES, "eeftacourt": [{"id": "ee-1", "document": "ee-doc"}], "events": [], "settings": {}}

print("user agent")
check("not Mozilla/", ec.USER_AGENT.startswith("Mozilla/"), False)
check("not Python-urllib/", ec.USER_AGENT.startswith("Python-urllib/"), False)
check("names the skill", ec.USER_AGENT.startswith("efta-court-skill/"), True)
version = __import__("json").loads((SKILL.parents[1] / ".claude-plugin" / "plugin.json").read_text("utf-8"))["version"]
check("UA carries the plugin version", f"efta-court-skill/{version} " in ec.USER_AGENT, True)

print("API address and document URLs")
check("config.js", ec.api_base_from_config('window.EFTA_API_URL = "https://api.eftacourt.int/api";'),
      "https://api.eftacourt.int/api")
check("config.js, trailing slash, single quotes", ec.api_base_from_config("window.EFTA_API_URL='https://x.example/api/'"),
      "https://x.example/api")
check("config.js without it", ec.api_base_from_config("var a = 1;"), None)
check("on-forge file -> API host", ec.storage_url(FILE.format("abc"), "https://api.eftacourt.int/api"),
      "https://api.eftacourt.int/storage/imports/abc.pdf")
check("bare file name", ec.storage_url("NYPvbPsQ.pdf", "https://api.eftacourt.int/api"),
      "https://api.eftacourt.int/storage/imports/NYPvbPsQ.pdf")
check("moved API host is followed", ec.storage_url(FILE.format("abc"), "https://new.example/api"),
      "https://new.example/storage/imports/abc.pdf")

print("case numbers")
for raw in ["E-14/15", "e-14/15", "E14-15", "e 14/15", "E-14-15", "14/15", "E1415"]:
    check(repr(raw), ec.normalise(raw), "E-14/15")
for raw in ["E-08/26", "E-8/26", "e-8-26", "E0826"]:
    check(repr(raw), ec.normalise(raw), "E-8/26")
check("1990s year", ec.full_year(94), 1994)
check("2000s year", ec.full_year(5), 2005)
for ref, want in [("Joined Cases E-31/24 and E-32/24", ["E-31/24", "E-32/24"]),
                  ("E-5/04, E-6/04, and E-7/04", ["E-5/04", "E-6/04", "E-7/04"]),
                  ("E-8/94 and E-9/94", ["E-8/94", "E-9/94"]),
                  ("E-9/04 Costs II", ["E-9/04"]), ("E-2/12 INT", ["E-2/12"]), ("E-6/94r", ["E-6/94"])]:
    check(f"ref_numbers {ref!r}", ec.ref_numbers(ref), want)

print("resolving a case")
r = ec.resolve("E-1/24", DATA)
check("own record", r["main"]["id"], "c-wp-1")
check("joined record comes along", [j["id"] for j in r["joined"]], ["c-wp-3"])
check("padded number", ec.resolve("E-01/24", DATA)["main"]["id"], "c-wp-1")
check("exact COSTS ref", ec.resolve("e-9/04 costs", DATA)["main"]["id"], "c-wp-6")
check("number of a COSTS-only case", ec.resolve("E-9/04", DATA)["main"]["id"], "c-wp-6")
check("component without own record -> joined", ec.resolve("E-9/94", DATA)["main"]["id"], "c-wp-5")
check("unknown case", raises(lambda: ec.resolve("E-99/99", DATA)), True)
docs = ec.documents_for(r, DATA)
check("documents numbered across records", [d["n"] for d in docs], list(range(1, len(docs) + 1)))
check("joined record's documents follow", docs[-1]["record"], "Joined Cases E-1/24 and E-7/24")

print("derived fields")
proc = {c["ref"]: ec.procedure_code(c) for c in CASES}
check("AO", proc["E-1/24"], "AO")
check("infringement (type says Direct Action)", proc["E-2/26"], "INF")
check("annulment", proc["E-3/26"], "DA")
check("COSTS record of an ESA action", proc["E-9/04 COSTS"], "INF")
cc = {c["ref"]: ec.country_code(c) for c in CASES}
check("source", (cc["E-1/24"], cc["E-7/24"]), ("NO", "LI"))
check("State sued", cc["E-2/26"], "IS")
check("no State named", cc["E-3/26"], "")
check("AO without source: from the description", cc["E-4/26"], "LI")
check("case page", ec.case_page(CASES[0]), "https://eftacourt.int/cases/c-wp-1")

print("buckets")
b = ec.partition(DATA)
check("case document", b.get("dc-1-1"), "case")
check("press release on a case dropped", b.get("dc-1-3"), None)
check("press item dropped", (b.get("pd-1"), b.get("pd-2")), (None, None))
check("procedural text", b.get("pr-doc-rules-of-procedure-0"), "text")
check("collection filed as press -> text", b.get("pd-8855"), "text")
check("e-EFTACourt guide", b.get("ee-doc"), "text")
check("stray notification dropped", b.get("d1003"), None)
check("no ID in two buckets", len(set(b)), len(b))

print("case documents")
types = [d["type"] for d in ec.case_documents(CASES[0], DATA)]
check("types, press release left out, observations last", types,
      ["notification", "judgment", "judgment", "order-court", "order-president", "report", "report",
       "observations", "observations"])
check("languages", [d["lang"] for d in ec.case_documents(CASES[0], DATA)][:3], ["EN", "EN", "NO"])


def choose(t, lang="EN", party=None):
    err = io.StringIO()
    with redirect_stderr(err):
        d = ec.choose_doc(docs, t, lang, party)
    return (d["id"] if d else None), err.getvalue()


check("judgment NO", choose("judgment", "NO")[0], "dc-1-2")
check("advisory-opinion alias", choose("advisory-opinion")[0], "dc-1-1")
check("order-court", choose("order-court")[0], "dc-1-4")
check("order matches both kinds", choose("order")[0] in ("dc-1-4", "dc-1-5"), True)
check("hearing report alias", choose("hearing report")[0] in ("dc-1-6", "dc-1-7"), True)
check("several reports: note", "--doc" in choose("report")[1], True)
did, note = choose("judgment", "IS")
check("fallback to EN", did, "dc-1-1")
check("fallback says so", "no IS version" in note, True)
check("press release not offered", choose("press-release")[0], None)
check("observations by party", choose("observations", party="commission")[0], ec._obs_id(OBS.replace("obs1", "obs2")))
check("observations, several: note", "--party" in choose("observations")[1], True)

print("cache file names")
stems = [ec.doc_stem(docs, d) for d in docs]
check("unique type+lang", stems[1], "judgment-EN")
check("same type+lang, own date", stems[5], "report-2023-07-28-EN")
check("same type+lang, no date", stems[6], "report-EN-7")
check("observations by party", stems[7], "observations-Government-of-Norway")
check("all distinct", len(set(stems)), len(stems))

print("duplicate files on joined records")
hits = [{"case": CASES[3], "docs": ec.case_documents(CASES[3], DATA), "meta": False},
        {"case": CASES[4], "docs": ec.case_documents(CASES[4], DATA), "meta": False}]
check("kept once, on the joined record", [h["case"]["ref"] for h in ec.dedupe_hits(hits)], ["E-8/94 and E-9/94"])

print("local matching (server rules)")
text = "Holship Norge AS – Collective action – Freedom of establishment"
for q, want in [("collective action", True), ('"collective action"', True), ('"action collective"', False),
                ("collect", False), ("collect*", True), ("holship establishment", True), ("holship lotus", False)]:
    check(repr(q), ec.meta_match(text, q), want)

print("server cap")
err = io.StringIO()
with redirect_stderr(err):
    ec.cap_warning(["x"] * 1000)
check("warns at 1000", "incomplete" in err.getvalue(), True)
err = io.StringIO()
with redirect_stderr(err):
    ec.cap_warning(["x"] * 999)
check("quiet below", err.getvalue(), "")

print("EFTA Court Report references in snippets")
snips = ["… see Case E-1/94 Restamark [1994-1995] EFTA Ct. Rep. 15, paragraph 24 …",
         "… Sak E-1/94 Restamark [1994-1995] EFTA Court Report 17. 24 Sak C-8/74 …",
         "… Case E-1/94 Restamark [1994–1995] EFTA Ct. Rep. 15 …",
         "… Case E-11/94 Other [1995] EFTA Ct. Rep. 99 …"]
check("tallied, other case ignored", ec.report_refs(snips, "E-1/94"),
      {"[1994-1995] EFTA Ct. Rep. 15": 2, "[1994-1995] EFTA Ct. Rep. 17": 1})

print("HTML text (source-text rules)")
out = ec.html_to_text('<h2>ESA / <i>Court</i> Agreement</h2>\n<p>THE REPUBLIC OF\nICELAND,<br />\nAND <i>NORWAY</i>'
                      '&nbsp;</p><p>&nbsp;</p><ol><li>first</li><li>second</li></ol><ul><li>dot</li></ul><h3>Article 1</h3>')
check("heading, emphasis-free", out.splitlines()[0], "# ESA / Court Agreement")
check("markup line break is a space; <br> a line", "THE REPUBLIC OF ICELAND,\nAND *NORWAY*" in out, True)
check("list numbers and bullets", ("1. first" in out, "2. second" in out, "- dot" in out), (True, True, True))
check("h3 -> ##", out.rstrip().endswith("## Article 1"), True)
check("no non-breaking spaces", "\xa0" in out, False)

print("procedural texts")
cat = ec.texts_catalogue(DATA)
titles = [t["title"] for t in cat]
check("catalogue", titles, ["Surveillance and Court Agreement", "Rules of Procedure", "Rules of Procedure of the EFTA Court",
                            "Decision of the Court on remote oral hearings", "EFTA Court Texts",
                            "e-EFTACourt Portal – User Guide"])
check("language versions grouped", [v["lang"] for v in cat[1]["versions"]], ["EN", "NO"])
check("page link", cat[1]["page"], "https://eftacourt.int/procedure/pr-rules-of-procedure")
check("SCA is an HTML entry", "html" in cat[0]["versions"][0], True)
check("e-EFTACourt page", cat[-1]["page"], "https://eftacourt.int/e-eftacourt")
check("by number", ec.choose_text(cat, "3")["title"], "Rules of Procedure of the EFTA Court")
check("exact title wins", ec.choose_text(cat, "rules of procedure")["title"], "Rules of Procedure")
check("words", ec.choose_text(cat, "remote hearings")["title"], "Decision of the Court on remote oral hearings")
check("ambiguous words -> list", raises(lambda: ec.choose_text(cat, "procedure")), True)
check("no match", raises(lambda: ec.choose_text(cat, "lotus")), True)

print("list filters")
ns = argparse.Namespace(year=None, country=None, procedure=None, status=None, subject=None, court=None,
                        party=None, language=None, observer="commission")
check("--observer", [c["ref"] for c in ec._filter(CASES, ns)], ["E-1/24"])
ns.observer, ns.status = None, "pending"
check("--pending", [c["ref"] for c in ec._filter(CASES, ns)], ["E-2/26"])
ns.status, ns.year = None, 94
check("--year 94", [c["ref"] for c in ec._filter(CASES, ns)], ["E-8/94", "E-8/94 and E-9/94"])

print("1.x cache is removed")
root = Path(os.environ["EFTA_COURT_CACHE_DIR"])
(root / "index.json").write_text("{}")
(root / "cases" / "E-14-15").mkdir(parents=True, exist_ok=True)
(root / "cases" / "E-14-15" / "raw.html").write_text("<html>")
ec.cache_dir()
check("index.json and old case pages gone", ((root / "index.json").exists(), (root / "cases").exists()), (False, False))

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
