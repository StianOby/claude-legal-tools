#!/usr/bin/env python3
"""Offline tests for scripts/eea_lex.py (no network): the User-Agent,
citation-to-CELEX, factsheet / listing / facet parsing, the yearly JCD lists
and the Art. 103 report (pdftotext and pypdf text), annex entries, JCD PDF
headers, Cellar title matching and the redirect / challenge rules.
Fixtures were cut from www.efta.int on 2026-10-23 and hold act titles and
dates only, no personal data. Run: python tests/eea-lex/test_eea_lex.py
"""

import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

os.environ["EEA_LEX_CACHE_DIR"] = tempfile.mkdtemp()
SKILL = Path(__file__).resolve().parents[2] / "plugins" / "eea-lex" / "skills" / "eea-lex"
sys.path.insert(0, str(SKILL / "scripts"))
import eea_lex as el  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
failures = 0


def fixture(name):
    return (FIX / name).read_text(encoding="utf-8")


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("user agent")
version = json.loads((SKILL.parents[1] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
check("UA carries the plugin version", el.USER_AGENT.startswith(f"eea-lex-skill/{version} "), True)
check("UA never starts with Mozilla/", el.USER_AGENT.startswith("Mozilla"), False)
check("UA never starts with Python-urllib/", el.USER_AGENT.startswith("Python-urllib"), False)
check("UA names the repo", "github.com/StianOby/claude-legal-tools" in el.USER_AGENT, True)

print("citation -> CELEX")
for cite, want in [
    ("Regulation 2016/679", "32016R0679"),
    ("Regulation (EU) 2016/679", "32016R0679"),
    ("Directive 95/46/EC", "31995L0046"),
    ("Directive (EU) 2019/1152", "32019L1152"),
    ("Regulation (EC) No 1907/2006", "32006R1907"),
    ("Commission Regulation (EU) No 611/2013", "32013R0611"),
    ("Council Decision 94/373/EC", "31994D0373"),
    ("Commission Implementing Decision (EU) 2021/914", "32021D0914"),
    ("GDPR", None),
]:
    check(cite, el.act_to_celex(cite), want)

print("JCD numbers")
for s, want in [("154/2018", (154, 2018)), ("No 10/95", (10, 1995)), ("JCD 001/2026", (1, 2026))]:
    check(s, el.parse_jcd_number(s), want)

print("factsheet")
fs = el.parse_factsheet(fixture("factsheet_32016r0679.html"), "https://www.efta.int/eea-lex/32016r0679")
check("id", fs["id"], "32016R0679")
check("status", fs["status"], "Incorporated into the EEA Agreement and in force")
check("areas", fs["areas"], ["XI Electronic Communication, Audiovisual Services and Information Society",
                             "XI.III Data Protection"])
check("jcd", fs["jcd"], "154/2018")
check("in force", fs["in_force_in_eea"], "Yes")
check("document flags", [d["flag"] for d in fs["documents"]], ["eu", "is", "li", "no"])
check("Norwegian JCD link", fs["documents"][3]["links"][1]["url"].endswith("2018%20-%20Norwegian/154-2018n.pdf"), True)
check("history newest first", (fs["history"][0]["date"], fs["history"][-1]["date"]), ("2018-07-20", "2012-01-25"))
check("Art. 103 event", any("Art. 103" in h["event"] and h["date"] == "2018-07-19" for h in fs["history"]), True)

print("listing")
res = el.parse_listing(fixture("search_keyword_2016-679.html"))
check("total", (res["total"], res["pages"]), (178, 30))
check("first card", (res["items"][0]["id"], res["items"][0]["celex"]), ("32021D0914", True))
prop = el.parse_listing(fixture("search_status_proposed.html"))["items"][0]
check("proposal card", (prop["id"], prop["celex"], prop["document"]), ("327538", False, "COM(2025) 102"))

print("facets and search URL")
facets = el.parse_facets(fixture("facets.html"))
check("status ids", sorted(e["id"] for e in facets["case_status"]), ["11", "12", "14", "3", "5", "9"])
check("filters", el.resolve_filters(facets, status="pending", annex="XI.III", protocol="31",
                                    type_="regulation", year=2024),
      [("case_status", "11"), ("area_agreement", "2071"), ("protocol", "1836"),
       ("celex_type", "Regulation"), ("adoption_date_eu", "2024")])
check("annex by arabic number", el.resolve_filters(facets, annex="11"), [("area_agreement", "1906")])
check("protocol with leading zero", el.resolve_filters(facets, protocol="5"), [("protocol", "2081")])
check("search URL", el.search_url("data", [("case_status", "14")], per_page=20),
      "https://www.efta.int/eea-lex?keyword=data&f%5B0%5D=case_status%3A14&items_per_page=24&sort_bef_combine=rel_DESC")

print("JCD lists")
a = el.parse_jcd_list(fixture("jcd_list_2026_pdftotext.txt"))
b = el.parse_jcd_list(fixture("jcd_list_2026_pypdf.txt"))
check("report date", a["report_date"], "01 October 2026")
check("rows", len(a["rows"]), 14)
check("pdftotext == pypdf (fields)", [{k: v for k, v in r.items() if k != "acts"} for r in a["rows"]],
      [{k: v for k, v in r.items() if k != "acts"} for r in b["rows"]])
check("pdftotext == pypdf (CELEX)", [[x["celex"] for x in r["acts"]] for r in a["rows"]],
      [[x["celex"] for x in r["acts"]] for r in b["rows"]])
r1 = a["rows"][0]
check("JCD 1/2026", (r1["jcd"], r1["adoption"], r1["eif"], r1["oj"], r1["supplement"], r1["annex"]),
      ("1/2026", "2026-02-06", "2026-02-07", "OJ L, 2026/933, 21.5.2026", "EEA Supplement No 34, 21.5.2026, p. 1",
       "Annex I Veterinary and Phytosanitary Matters"))
check("JCD 1/2026 act", (r1["acts"][0]["celex"], r1["acts"][0]["compliance_eu"]), ("32025R0917", "2025-06-09"))
r287 = next(r for r in a["rows"] if r["jcd"] == "287/2026")
check("JCD 287/2026 unpublished", (r287["eif"], r287["oj"], r287["acts"][0]["celex"]), ("", "", "32023R0956"))
r218 = next(r for r in a["rows"] if r["jcd"] == "218/2026")
check("act without CELEX", (r218["annex"], r218["acts"][0]["celex"], r218["acts"][0]["title"][:34]),
      ("Annex XIII Transport", "", "Commission Implementing Decision ."))
c = el.parse_jcd_list(fixture("jcd_list_2025_pages.txt"))
check("'232//2025' row", [r["jcd"] for r in c["rows"]].count("232/2025"), 1)
check("five-digit CELEX", next(r for r in c["rows"] if r["jcd"] == "208/2025")["acts"][0]["celex"], "32024D06842")
d = el.parse_jcd_list(fixture("jcd_list_2010_pages.txt"))
check("2010 layout (no 'Report no:')", [r["jcd"] for r in d["rows"]], [f"{n}/2010" for n in range(1, 7)])

print("Art. 103 report")
for name in ("awaited_pdftotext.txt", "awaited_pypdf.txt"):
    w = el.parse_awaited(fixture(name))
    check(f"{name}: rows and acts", (len(w["rows"]), sum(len(r["acts"]) for r in w["rows"])), (47, 59))
    r = next(r for r in w["rows"] if r["jcd"] == "70/2026")
    check(f"{name}: 70/2026", (r["six_month_expiry"], r["states"], r["acts"]),
          ("2026-09-20", [{"state": "N", "name": "Norway", "date_of_delay": "2026-10-12"}], ["32024R0568"]))
    r = next(r for r in w["rows"] if r["jcd"] == "154/2026")
    check(f"{name}: 154/2026 states", [s["state"] for s in r["states"]], ["IS", "FL"])
    check(f"{name}: report date", w["report_date"], "23 October 2026")

print("agreement texts")
text = fixture("annex11_pages.txt")
check("version date", el.version_date(text), "2026-09-25")
hit = el.find_in_text(text, "32016R0679")[0]
check("GDPR entry starts at point 5e", hit["excerpt"].startswith("5e.{117} 32016 R 0679"), True)
check("adaptations kept", "(g) In Article 46(2)(d)" in hit["excerpt"], True)
check("no footnote text inside excerpt", "e.i.f. 20.7.2018" in hit["excerpt"], False)
check("footnote names the JCD", "replaced by Decision 154/2018" in hit["footnotes"]["117"], True)
old = el.find_in_text(text, "31987L0372")[0]
check("pre-2000 CELEX form", old["excerpt"].startswith("1. 387 L 0372"), True)
check("'as amended by' indent kept", "32009 L 0114" in old["excerpt"], True)
check("phrase across line break", bool(el.find_in_text(text, "Protocol 1 on horizontal adaptations")), True)

print("translations")
sup = fixture("translation_32019L1152-NO_pages.txt")
check("Supplement copy", el.describe_translation(sup, "32019L1152")["kind"], "supplement")
check("Supplement pages", [el.supplement_page(p) for p in sup.split("\f")],
      ["No 21, p. 917", "No 21, p. 925", "No 21, p. 926"])
art = el.find_article(sup, "NO", "2", "32019L1152")
check("Artikkel 2 found", (art["pdf_pages"], art["text"].splitlines()[:2]), ([2], ["Artikkel 2", "Definisjoner"]))
check("page headers left out", any("EØS-tillegget til Den europeiske" in x for x in art["text"].splitlines()), False)
con = fixture("translation_32016R0679-NO_pages.txt")
check("consolidated copy", el.describe_translation(con, "32016R0679"),
      {"kind": "consolidated", "consolidated_as_of": "2022-03-03",
       "published_in": "EØS-tillegget nr. 46 av 19.7.2018, s. 6"})
art = el.find_article(con, "NO", "6", "32016R0679")
check("Artikkel 6 ends before Artikkel 7", (art["pdf_pages"], art["text"].splitlines()[-1].startswith("e) om det foreligger")),
      ([2, 3], True))
check("consolidated footer left out", any(x.startswith("32016R0679") for x in art["text"].splitlines()), False)
check("no Artikkel 99", el.find_article(con, "NO", "99", "32016R0679"), None)
check("translation link", el.translation_link(fs, "NO")["url"].endswith("/norwegian/n32016R0679.pdf"), True)

print("JCD PDF headers and Cellar")
check("317/2026", el.jcd_pdf_header(fixture("jcd_317-2026_p1.txt"), 317, 2026)["adoption"], "2026-10-23")
h = el.jcd_pdf_header(fixture("jcd_010-1995_p1.txt"), 10, 1995)
check("10/95 two-digit year", (h["adoption"], h["title"][:44]), ("1995-01-27", "Decision of the EEA Joint Committee No 10/95"))
nbsp = "\xa0"
binds = [{"celex": {"value": "22026D0934"}, "title": {"value": f"Decision of the EEA Joint Committee No{nbsp}51/2026 of 6{nbsp}February 2026"}},
         {"celex": {"value": "22026D0933"}, "title": {"value": f"Decision of the EEA Joint Committee No{nbsp}1/2026 of 6{nbsp}February 2026"}}]
check("Cellar match with NBSP, not 51/2026", el.match_cellar_title(binds, 1, 2026)["celex"], "22026D0933")
check("Cellar no match", el.match_cellar_title(binds, 11, 2026), None)

print("HTTP rules")
check("max redirects", el._Redirects.max_redirections, 3)
req = urllib.request.Request("https://www.efta.int/eea-lex/327538")
try:
    el._Redirects().redirect_request(req, None, 301, "Moved", {}, "https://www.efta.int/eea-lex/327538")
    check("self-redirect is not found", "followed", "NotFound")
except el.NotFound:
    check("self-redirect is not found", "NotFound", "NotFound")
check("challenge by header", el.is_challenge(403, {"cf-mitigated": "challenge"}, b""), True)
check("challenge by body", el.is_challenge(403, {}, b"<title>Just a moment...</title>"), True)
check("plain 403 is not a challenge", el.is_challenge(403, {}, b"Forbidden"), False)

print()
if failures:
    print(f"{failures} failure(s)")
    sys.exit(1)
print("all ok")
