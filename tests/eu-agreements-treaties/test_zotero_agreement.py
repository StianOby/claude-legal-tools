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
lugano_issue = {"41988A0592": w("88/592/EEC: Convention on jurisdiction and the enforcement of judgments in civil "
                                "and commercial matters - Done at Lugano on 16 September 1988", page="0009"),
                "31988D0591": w("88/591/ECSC, EEC, Euratom: Council Decision of 24 October 1988 establishing a Court "
                                "of First Instance", type_="D", page="0001")}
celex, _, _ = za.pick({"title": PROBE["1988055"]["title"], "signature": "1988-09-16"}, lugano_issue)
check("a reference prefix is no part of the title (Lugano 1988, found by its OJ issue)", celex, "41988A0592")
acc94 = {"11994N/TXT": w("ACT concerning the conditions of accession of the Kingdom of Norway, the Republic of Austria, "
                         "the Republic of Finland and the Kingdom of Sweden and the adjustments to the Treaties",
                         "1994-06-24", "0009"),
         "11994N/TTE/02": w("TREATY between the Kingdom of Belgium, the Kingdom of Denmark, … concerning the accession "
                            "of the Kingdom of Norway, the Republic of Austria, the Republic of Finland and the Kingdom "
                            "of Sweden to the European Union - Article 2", "1994-06-24", "0013"),
         "11994N/PRO/03": w("ACT concerning the conditions of accession … - Protocol No 3", "1994-06-24", "0352")}
treaty94 = {"title": "Treaty between the Kingdom of Belgium, the Kingdom of Denmark, … concerning the accession of the "
                     "Kingdom of Norway, the Republic of Austria, the Republic of Finland and the Kingdom of Sweden to "
                     "the European Union", "signature": "1994-06-24"}
celex, _, sure = za.pick(treaty94, acc94)
check("a part of a treaty gives way to its whole text, /TXT, flagged (1994 accession)", (celex, sure), ("11994N/TXT", False))
celex, _, _ = za.pick({"title": "Treaty concerning the accession of Norway", "signature": "1994-06-24"},
                      {"11994N/TXT": acc94["11994N/TXT"], "11994N/PRO/03": acc94["11994N/PRO/03"]})
check("primary law with an unlike title: /TXT when the signature date agrees", celex, "11994N/TXT")
celex, _, _ = za.pick({"title": "Treaty concerning the accession of Norway", "signature": "1972-01-22"},
                      {"11972B/TXT": w("Documents concerning the accession to the European Communities of the Kingdom "
                                       "of Denmark, Ireland, the Kingdom of Norway and the United Kingdom", "1970-04-22",
                                       "0005")})
check("…but not against Cellar's own signature date (1972: 1970-04-22 in Cellar; not worked around)", celex, None)

print("citation and item")
# The library's Dublin item (ZRVR9TTR, as the EUR-Lex translator saves it):
# "OJ 2001 L", 93, "40-47", event-date 2001-04-03 — Cellar's values for
# 22001A0403(01), 2026-11-09.
check("Dublin as in the library", za.oj_citation("22001A0403(01)", w(
    "x", page="0040", plast="0047", ojnum="093", ojyear="2001", ojid="oj:JOL_2001_093_R", ojdate="2001-04-03"), []),
      {"code": "OJ 2001 L", "codeNumber": "93", "pages": "40-47", "oj_date": "2001-04-03"})
check("old OJ: the OJ date from the database's reference when Cellar has none", za.oj_citation(
    "21972A1219(01)", w("x", page="0002", ojnum="133", ojyear="1973", ojid="oj:JOL_1973_133_R"),
    [za.parse_oj({"text": "L 133 (21/05/1973);"})]),
      {"code": "OJ 1973 L", "codeNumber": "133", "pages": "2", "oj_date": "1973-05-21"})
# Cellar's own act date first (22026A00757, the Energy Charter item: the
# EUR-Lex translator gives event-date 2026-03-27 too)
check("act-numbered OJ: Cellar's act date", za.oj_citation("22026A00757", w("x", actdate="2026-03-27"), []),
      {"code": "OJ L", "pages": "2026/757", "oj_date": "2026-03-27"})
check("act-numbered OJ", za.oj_citation("22024A02603", w("x"), [za.parse_oj({"text": "L, 2024/02603 (08/10/2024);"})]),
      {"code": "OJ L", "pages": "2024/2603", "oj_date": "2024-10-08"})
check("act-numbered OJ C: \"C/\" as in the translator", za.oj_citation(
    "52024A03400", w("x"), [za.parse_oj({"text": "C, 2024/03400 (10/06/2024);"})]),
      {"code": "OJ C", "pages": "C/2024/3400", "oj_date": "2024-06-10"})
# The translator's 1956 ECSC case (21956A0507(01)): "OJ 1957", 7; Cellar's
# values 2026-11-09 (no page in Cellar)
check("ECSC OJ: no series", za.oj_citation("21956A0507(01)", w(
    "x", ojnum="7", ojyear="1957", ojid="oj:JOA_1957_007_R", ojdate="1957-02-21"), []),
      {"code": "OJ 1957", "codeNumber": "7", "oj_date": "1957-02-21"})
check("OJ before 1968: no series", za.oj_citation("21963A0720(01)", w(
    "x", page="1431", plast="1457", ojnum="093", ojyear="1964", ojid="oj:JOP_1964_093_R", ojdate="1964-06-11"), [])["code"],
      "OJ 1964")
check("issue without page or date", za.oj_citation("22016A0528(01)", w("x", ojnum="141", ojyear="2016",
                                                                         ojid="oj:JOL_2016_141_R"), []),
      {"code": "OJ 2016 L", "codeNumber": "141"})
check("last page equal to the first: one page", za._pages({"page": "0005", "plast": "0005"}), "5")
rec = PROBE["2016032"]
item, notes = za.build_item(rec, ("22016A0528(01)", w(
    "Agreement between the European Union, Iceland, the Principality of Liechtenstein and the Kingdom of Norway on an "
    "EEA Financial Mechanism 2014-2021", "2016-05-03", "0003", eli="http://data.europa.eu/eli/agree_internation/2016/837(1)/oj",
    plast="0010", ojnum="141", ojyear="2016", ojid="oj:JOL_2016_141_R_0002", ojdate="2016-05-28"), True), today=TODAY)
check("item as the library's Dublin/Schengen pattern",
      {k: item.get(k) for k in ("code", "codeNumber", "pages", "dateEnacted", "url", "language")},
      {"code": "OJ 2016 L", "codeNumber": "141", "pages": "3-10", "dateEnacted": "2017-09-01",
       # The ELI is kept although EUR-Lex fails to resolve suffixed ones (2026-10-22).
       "url": "http://data.europa.eu/eli/agree_internation/2016/837(1)/oj", "language": "en"})
check("no notes when the citation is complete", notes, [])
eea_item, _ = za.build_item(PROBE["1992045"], ("21994A0103(01)", w(
    "Agreement on the European Economic Area - Final Act", "1992-05-02", "0003",
    eli="http://data.europa.eu/eli/agree_internation/1994/1/oj", ojnum="1", ojyear="1994", ojid="oj:JOL_1994_001_R"), True),
    today=TODAY)
check("a plain ELI is used too (EEA)", eea_item["url"], "http://data.europa.eu/eli/agree_internation/1994/1/oj")
check("extra", item["extra"].split("\n"), ["type: treaty", "available-date: 2016-05-03", "event-date: 2016-05-28",
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
check("basename", za.basename(item), "OJ_2016_L_141_3_Agreement_between_the_European_Union_Iceland_the")
old2, old_notes = za.build_item(PROBE["2003104"], ("22004A0429(04)", w("x", "2003-10-14", ojnum="130", ojyear="2004",
                                                                       ojid="oj:JOL_2004_130_R"), True), today=TODAY)
check("no OJ date in Cellar: the database's reference to the same issue (L 130 (29/04/2004))",
      "event-date: 2004-04-29" in old2["extra"].split("\n"), True)
check("missing pages are reported", [n.split(";")[0] for n in old_notes],
      ["the pages of the agreement in the OJ issue are not in Cellar"])
_, nodate_notes = za.build_item({"id": "0000000", "title": "x", "oj": []}, ("22016A0528(01)", w(
    "x", page="0003", ojnum="141", ojyear="2016", ojid="oj:JOL_2016_141_R"), True), today=TODAY)
check("missing OJ date is reported", [n.split(";")[0] for n in nodate_notes],
      ["the OJ date is not in Cellar or the database"])
aba, aba_notes = za.build_item({"id": "2026004", "title": "x", "oj": []}, ("22026A02350", w("x"), True), today=TODAY)
check("act-by-act OJ without a date: no event-date, no note",
      (any(l.startswith("event-date") for l in aba["extra"].split("\n")), aba_notes), (False, []))

print("agreements without an English version (before 1973)")
L = "http://publications.europa.eu/resource/authority/language/"
# Cellar's rows for 21963A0720(01)/(02), 2026-11-09 (trimmed): no English;
# the 1956 ECSC agreement has an English title but pages only in French.
merged = za._merge({
    "21963A0720(01)": [
        {"celex": "21963A0720(01)", "lang": L + "DEU", "title": "Abkommen über die Assoziation …", "sig": "1963-07-20",
         "page": "1431", "plast": "1457", "type": "A"},
        {"celex": "21963A0720(01)", "lang": L + "FRA", "type": "A", "sig": "1963-07-20", "page": "1431", "plast": "1457",
         "title": "Convention d'association entre la Communauté économique européenne et les États africains et "
                  "malgache associés à cette Communauté /* Signée à Yaoundé le 20 juillet 1963 */"}],
    "21963A0720(02)": [
        {"celex": "21963A0720(02)", "lang": L + "FRA", "type": "A", "sig": "1963-07-20", "page": "1458",
         "title": "Accord relatif aux produits relevant de la Communauté européenne du charbon et de l'acier"}],
    "21956A0507(01)": [
        {"celex": "21956A0507(01)", "lang": L + "ENG", "type": "A", "sig": "1956-05-07",
         "title": "Consultation Agreement between the Swiss Confederation and the High Authority …"},
        {"celex": "21956A0507(01)", "lang": L + "FRA", "type": "A", "sig": "1956-05-07", "page": "0085", "plast": "0087",
         "title": "Accord de consultation …", "ojnum": "7"}]})
check("merge: French before German", (merged["21963A0720(01)"]["lang"], merged["21963A0720(01)"]["title"][:10]),
      ("FRA", "Convention"))
check("merge: English title, French pages, work fields from any row",
      {k: merged["21956A0507(01)"].get(k) for k in ("lang", "page", "plast", "ojnum")},
      {"lang": "ENG", "page": "0085", "plast": "0087", "ojnum": "7"})
yaounde = {"id": "x", "title": "Convention of Association between the European Economic Community and the "
                               "African and Malagasy States associated with that Community", "signature": "1963-07-20"}
check("two signed that day: the one of the same kind (Convention, not Accord), to check",
      za.pick(yaounde, {k: merged[k] for k in ("21963A0720(01)", "21963A0720(02)")})[0::2],
      ("21963A0720(01)", False))
check("…the Accord for an Agreement",
      za.pick(dict(yaounde, title="Agreement on products within the province of the ECSC"),
              {k: merged[k] for k in ("21963A0720(01)", "21963A0720(02)")})[0],
      "21963A0720(02)")
check("two of the same kind: no match",
      za.pick(dict(yaounde, title="Protocol on something"),
              {k: merged[k] for k in ("21963A0720(01)", "21963A0720(02)")})[0], None)
check("one signed that day: matched whatever its kind",
      za.pick(dict(yaounde, title="Protocol on something"), {"21963A0720(02)": merged["21963A0720(02)"]})[0],
      "21963A0720(02)")
check("a different signature date: no match",
      za.pick(dict(yaounde, signature="1963-07-21"), {"21963A0720(01)": merged["21963A0720(01)"]})[0], None)
y_item, _ = za.build_item(dict(yaounde, oj=[]), ("21963A0720(01)", dict(
    merged["21963A0720(01)"], ojnum="093", ojyear="1964", ojid="oj:JOP_1964_093_R", ojdate="1964-06-11"), False),
    today=TODAY)
check("no English: the database's title, Language of the text, OJ without series",
      {k: y_item.get(k) for k in ("nameOfAct", "language", "code", "codeNumber", "pages")},
      {"nameOfAct": yaounde["title"], "language": "fr", "code": "OJ 1964", "codeNumber": "93", "pages": "1431-1457"})

print("status line")
ended = dict(merged["21963A0720(01)"], ojnum="093", ojyear="1964", ojid="oj:JOP_1964_093_R", ojdate="1964-06-11")
for ends, want in ((["1975-01-31"], True), (["9999-12-31"], False), (["1001-01-01"], False),
                   (["2099-01-01"], False), ([], False)):
    check(f"past end of validity {ends}: ended={want}", za._ended(dict(ended, ends=ends), TODAY), want)
e_item, _ = za.build_item(dict(yaounde, oj=[], entry_into_force="1964-06-01"),
                          ("21963A0720(01)", dict(ended, ends=["1969-05-31"]), False), today=TODAY)
check("in force once, ended: the translator's line", e_item["extra"].split("\n")[-3:-2], ["status: not in force"])
n_item, _ = za.build_item(dict(yaounde, oj=[]), ("21963A0720(01)", dict(ended, ends=["1969-05-31"]), False),
                          today=TODAY)
check("one status line only", sum(l.startswith("status:") for l in n_item["extra"].split("\n")), 1)
check("merge keeps every end date", za._merge({"x": [{"celex": "x", "title": "t", "end": "2001-01-01"},
                                                     {"celex": "x", "title": "t", "end": "9999-12-31"}]})["x"]["ends"],
      ["2001-01-01", "9999-12-31"])

print("user agent")
version = json.loads((SKILL.parents[1] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
check("UA carries the plugin version", za.UA.startswith(f"eu-agreements-treaties-skill/{version} "), True)
check("UA names the repo", "github.com/StianOby/claude-legal-tools" in za.UA, True)
check("UA not Mozilla/ or Python-urllib/", za.UA.startswith(("Mozilla/", "Python-urllib/")), False)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
