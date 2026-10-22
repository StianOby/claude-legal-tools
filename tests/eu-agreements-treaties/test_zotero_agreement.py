#!/usr/bin/env python3
"""Offline tests for scripts/zotero_agreement.py (no network). Each matching
rule is pinned with the case from the 2026-10-21 probe of 37 Consilium
records (fixtures/probe-2026-10-21.json) that made it necessary; the Cellar
candidates are trimmed copies of what the endpoint returned.
`live_cellar_match.py` re-runs the whole probe against Cellar.
Run: python tests/eu-agreements-treaties/test_zotero_agreement.py
"""

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "eu-agreements-treaties" / "skills" / "eu-agreements-treaties"
sys.path.insert(0, str(SKILL / "scripts"))
import zotero_agreement as za  # noqa: E402

PROBE = {r["id"]: r for r in json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "probe-2026-10-21.json").read_text(encoding="utf-8"))}
TODAY = "2026-10-22"
failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def w(title, sig=None, page=None, type_="A", **kw):
    return dict(title=title, sig=sig, page=page, type=type_, **kw)


print("the record from __cs.zotero()")
import base64  # noqa: E402
rec_in = {"id": "2017039", "title": "Procès-verbal of rectification … latters' association", "oj": []}
b64 = base64.b64encode(json.dumps(rec_in, ensure_ascii=False).encode("utf-8")).decode()
check("base64 UTF-8 JSON round trip", za.load_record(b64=b64 + "\n"), rec_in)

print("titles")
check("cross-reference", za.clean_title(
    "Agreement in the form of an Exchange of Letters … the European Economic Area - See 2014013 (EEA Agreement)")[0],
    "Agreement in the form of an Exchange of Letters … the European Economic Area")
check("language list", za.clean_title("Procès-verbal of rectification to the Agreement (BG/ES/DA/EL/IT)")[0],
      "Procès-verbal of rectification to the Agreement")
check("depositary", za.clean_title("Energy Charter Treaty (Deposited with the Government of the Portuguese Republic)"),
      ("Energy Charter Treaty", "Government of the Portuguese Republic", []))
t, _, notes = za.clean_title(PROBE["2007059"]["title"])
check("bundle: title cut, note", (t.endswith("European Economic Area"), len(notes)), (True, 1))

print("provisional application")
for obs, want in [("Provisional application as from 1 August 2016 (1st day of the first month …)", "2016-08-01"),
                  ("Provisional application as from 21/06/2011 (except Austria, see Declaration)", "2011-06-21"),
                  ("Provisional application as of 15/07/2026 - See Art. 336(2)", "2026-07-15"),
                  ("Provisional application between the EU & Norway as from 1 May 2011", "2011-05-01"),
                  ("Convention opened for signature on 15 June 2011.", ""), (None, "")]:
    check((obs or "None")[:50], za.provisional_date(obs), want)

print("OJ references")
check("old", za.parse_oj({"text": "L 141 (28/05/2016);"}),
      {"series": "L", "year": "2016", "issue": "141", "date": "2016-05-28", "text": "L 141 (28/05/2016);"})
check("letter suffix", za.parse_oj({"text": "C 74E (20/03/2008);"})["issue"], "74E")
check("act-numbered", za.parse_oj({"text": "L, 2024/02603 (08/10/2024);"})["number"], "02603")
check("act-numbered CELEX", za.celex_candidates({"year": "2024", "number": "02603"}),
      ["12024A02603", "22024A02603", "42024A02603"])
cands = za.celex_candidates({"date": "2016-05-28", "issue": "141"})
check("dated CELEX: sectors 1/2/4, (01)-(99)", (len(cands), cands[0], cands[-1]),
      (297, "12016A0528(01)", "42016A0528(99)"))
check("signature-dated CELEX (older agreements)", za.celex_candidates(signature="1972-12-19")[99], "21972A1219(01)")

print("picking the agreement itself")
lugano = {"title": PROBE["1988055"]["title"], "signature": "1988-09-16"}
celex, _, _ = za.pick(lugano, {"22009A0610(01)": w(
    "Convention on jurisdiction and the recognition and enforcement of judgments in civil and commercial matters",
    sig="2007-10-30", page="0005")})
check("a conflicting signature date rules out (Lugano 1988 vs 2007)", celex, None)
iceland = {"title": PROBE["2026004"]["title"], "signature": "2026-03-26"}
celex, _, _ = za.pick(iceland, {"22026A02323": w(
    "Agreement between the European Union and the Kingdom of Norway laying down the rules for participation of "
    "the Kingdom of Norway in the GOVSATCOM component of the Union Space Programme", sig="2026-03-26")})
check("a name conflict rules out (Iceland vs Norway, same day)", celex, None)
eea = {"title": "Agreement on the European Economic Area", "signature": "1992-05-02"}
celex, work, sure = za.pick(eea, {
    "21994A0103(01)": w("Agreement on the European Economic Area - Final Act - Joint Declarations", "1992-05-02", "0003"),
    "21994A0103(02)": w("Agreement on the European Economic Area - Protocol 1 on horizontal adaptations", "1992-05-02", "0037"),
    "21994A0103(40)": w("Agreement on the European Economic Area - Protocol 39 on the ECU", "1992-05-02", "0208")})
check("the main text before its protocols (EEA, p. 3)", (celex, sure), ("21994A0103(01)", True))
ect = {"title": "Energy Charter Treaty", "signature": "1994-12-17"}
celex, _, _ = za.pick(ect, {
    "21994A1231(51)": w("Final Act of the European Energy Charter Conference - Statement submitted by the European "
                        "Communities to the Secretariat of the Energy Charter", "1994-12-17", "0003"),
    "21994A1231(52)": w("Final Act of the Conference on the European Energy Charter - Annex 1: The Energy Charter Treaty",
                        "1994-12-17", "0024")})
check("a title segment equal to ours wins (Energy Charter Treaty, p. 24)", celex, "21994A1231(52)")
air = {"title": PROBE["2011036"]["title"], "signature": None}
celex, _, sure = za.pick(air, {
    "22011A1029(01)": w("Air Transport Agreement", "2011-06-16", "0003"),
    "22011A1029(02)": w("Ancillary Agreement between the European Union and its Member States, of the first part, "
                        "Iceland, of the second part, and the Kingdom of Norway, of the third part, on the application "
                        "of the Air Transport Agreement", "2011-06-21", "0016")})
check("Cellar's short title (Air Transport Agreement), flagged weak", (celex, sure), ("22011A1029(01)", False))
acsa = {"title": PROBE["2016062"]["title"], "signature": "2016-12-06"}
celex, _, _ = za.pick(acsa, {"22016A1222(01)": w(
    "Acquisition and Cross-Servicing Agreement between the European Union and the United States of America (US-EU-01)",
    "2016-12-06", "0003")})
check("case and bracketed abbreviations are no name conflict (ACSA)", celex, "22016A1222(01)")
schengen = {"title": PROBE["1999025"]["title"], "signature": "1999-05-18"}
celex, _, _ = za.pick(schengen, {"21999A0710(02)": w(
    "Agreement concluded by the Council of the European Union and the Republic of Iceland and the Kingdom of Norway "
    "concerning the latters' association with the implementation, application and development of the Schengen acquis",
    "1999-05-18", "0036")})
check("same signature date, our words all in theirs (Schengen 1999)", celex, "21999A0710(02)")
croatia = {"title": za.clean_title(PROBE["2014030"]["title"])[0], "signature": "2014-04-11"}
celex, _, _ = za.pick(croatia, {"22014A0611(01)": w(
    "Agreement on the participation of the Republic of Croatia in the European Economic Area and three related agreements",
    "2014-04-11", "0005")})
check("a related agreement signed the same day is not enough (2014030)", celex, None)
check("all-capitals titles have no names to compare", za.names(PROBE["2010035"]["title"]), set())

print("citation and item")
check("old OJ from Cellar's issue", za.oj_citation("21972A1219(01)", w("x", page="0002", ojnum="133", ojyear="1973",
                                                                       ojid="oj:JOL_1973_133_R"), []),
      ("EUT 1973 L", "133/2"))
check("act-numbered OJ", za.oj_citation("22024A02603", w("x"), [za.parse_oj({"text": "L, 2024/02603 (08/10/2024);"})]),
      ("EUT L", "2024/2603"))
check("issue without page", za.oj_citation("22016A0528(01)", w("x", ojnum="141", ojyear="2016", ojid="oj:JOL_2016_141_R"), []),
      ("EUT 2016 L", "141"))
rec = PROBE["2016032"]
item, notes = za.build_item(rec, ("22016A0528(01)", w(
    "Agreement between the European Union, Iceland, the Principality of Liechtenstein and the Kingdom of Norway on an "
    "EEA Financial Mechanism 2014-2021", "2016-05-03", "0003", eli="http://data.europa.eu/eli/agree_internation/2016/837(1)/oj",
    ojnum="141", ojyear="2016", ojid="oj:JOL_2016_141_R_0002"), True), today=TODAY)
check("item as the library's Dublin/Schengen pattern", {k: item[k] for k in ("code", "pages", "dateEnacted", "url", "language")},
      {"code": "EUT 2016 L", "pages": "141/3", "dateEnacted": "2017-09-01",
       "url": "http://data.europa.eu/eli/agree_internation/2016/837(1)/oj", "language": "English"})
check("extra", item["extra"].split("\n"), ["type: treaty", "available-date: 2016-05-03",
                                           "provisional application: 2016-08-01", "CELEX: 22016A0528(01)",
                                           "Consilium: 2016032"])
air_item, _ = za.build_item(PROBE["2011036"], None, today=TODAY)
check("not in force, provisionally applied: status line", air_item["extra"].split("\n")[-2],
      "status: provisionally applied, not in force (as of 2026-10-22; EU perspective, Council Treaties Office)")
check("no match: Consilium URL and a note", (air_item["url"].startswith("https://www.consilium"), "code" in air_item),
      (True, False))
old, _ = za.build_item(PROBE["2003104"], ("22004A0429(04)", w("x", "2003-10-14", "0081", ojnum="130", ojyear="2004",
                                                            ojid="oj:JOL_2004_130_R"), True), today=TODAY)
check("no ELI: EUR-Lex by CELEX", old["url"], "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:22004A0429(04)")
check("basename", za.basename(item), "EUT_2016_L_141_3_Agreement_between_the_European_Union_Iceland_the")

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
