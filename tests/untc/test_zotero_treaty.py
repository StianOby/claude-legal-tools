#!/usr/bin/env python3
"""Offline tests for scripts/zotero_treaty.py (no network): entry-into-force
wordings, registration series, League of Nations treaties, titles, parents,
and UNCLOS as in the shared group library's UNCLOS example. The variants
are the ones found in a probe of 99 records (2026-10-21): 83 MTDSG status
documents across all chapters and 6 UNTS-only treaties.
Run: python tests/untc/test_zotero_treaty.py
"""

import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ["UNTC_CACHE_DIR"] = tempfile.mkdtemp()
SKILL = Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc"
sys.path.insert(0, str(SKILL / "scripts"))
import zotero_rdf  # noqa: E402
import zotero_treaty as zt  # noqa: E402

TODAY = "2026-10-21"
failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("entry into force")
check("plain", zt.parse_eif("27 January 1980, in accordance with article 84(1)."),
      {"date": "1980-01-27", "provisional": "", "readable": True})
check("ICCPR: first date", zt.parse_eif(
    "23 March 1976, in accordance with article 49 , for all provisions except those of "
    "article 41; 28 March 1979 for the provisions of article 41")["date"], "1976-03-23")
check("provisional then definitive (XIX-18)", zt.parse_eif(
    "provisionally on 1 January 1978, in accordance with article 75(2) and definitively on "
    "2 January 1980, in accordance with article 75(1) . The Agreement was extended by ..."),
    {"date": "1980-01-02", "provisional": "1978-01-01", "readable": True})
check("provisional only", zt.parse_eif("provisionally on 1 October 2001, in accordance with article 45"),
      {"date": "", "provisional": "2001-10-01", "readable": True})
check("garbled (XIX-36) is not guessed", zt.parse_eif(
    ". The Agreement was extended until 11 April 1998 and 11 April 2000, respectively, by ..."),
    {"date": "", "provisional": "", "readable": False})
check("none", zt.parse_eif(None)["date"], "")
check("UNTS record form", zt.parse_eif("21 October 1950 , in accordance with article 58")["date"], "1950-10-21")
check("dd/mm/yyyy", zt.iso("12/08/1949"), "1949-08-12")

print("registration series and League of Nations volumes")
check("series I", zt._series_from_pdfs(["https://x/UNTS/Volume%2075/volume-75-I-970-English.pdf"]), "I")
check("series II", zt._series_from_pdfs(["https://x/UNTS/Volume%2015/volume-15-II-102-English.pdf"]), "II")
check("annex A", zt._series_from_pdfs(
    ["https://x/UNTS/No%20Volume/33941/A-33941-080000028066150b.pdf"]), "A")
check("League", zt._series_from_pdfs(["https://x/UNTS/LON/Volume%20139/v139.pdf"]), "LoN")
check("LNTS volume", zt._lnts_volume(["https://x/UNTS/LON/Volume%20139/v139.pdf"]), 139)

print("UNCLOS as in the group library's example")
item, notes = zt.build_item(
    title="United Nations Convention on the Law of the Sea", conclusion="1982-12-10",
    eif_text="16 November 1994, in accordance with article 308(1).", registered=True,
    reg_full="I-31363", depositary=zt.SG, volume=1833, page=3, lnts_volume=None,
    url="https://treaties.un.org/Pages/ViewDetails.aspx?src=TREATY&mtdsg_no=XXI-6&chapter=21&clang=_en",
    ref="XXI-6", short_title=zt.SHORT_TITLES["XXI-6"], today=TODAY)
library = {"nameOfAct": "United Nations Convention on the Law of the Sea", "code": "UNTS",
           "codeNumber": "1833", "pages": "3", "dateEnacted": "1994-11-16",
           "shortTitle": "UNCLOS", "language": "English"}
check("fields the example has", {k: item.get(k) for k in library}, library)
check("extra", item["extra"].split("\n"),
      ["type: treaty", "available-date: 1982-12-10", "MTDSG: XXI-6",
       "depositary: Secretary-General of the United Nations", "UN registration no.: I-31363"])
check("no notes", notes, [])

print("the variants")
nif, notes = zt.build_item(title="X", conclusion="2025-12-15", eif_text=None, registered=False,
                           reg_full=None, depositary=zt.SG, volume=None, page=None,
                           lnts_volume=None, url="u", today=TODAY)
check("not in force: no date, status line", ("dateEnacted" in nif, nif["extra"].split("\n")[-2]),
      (False, "status: not in force (as of 2026-10-21)"))
prov, _ = zt.build_item(title="X", conclusion="2000-01-01",
                        eif_text="provisionally on 1 October 2001, in accordance with article 45",
                        registered=True, reg_full="I-1", depositary=zt.SG, volume=1, page=1,
                        lnts_volume=None, url="u", today=TODAY)
check("provisional only", ("dateEnacted" in prov, "provisional application: 2001-10-01" in prov["extra"],
                           "status: provisionally applied, not definitively in force (as of 2026-10-21)"
                           in prov["extra"]), (False, True, True))
lon, notes = zt.build_item(title="International Agreement for the suppression of the \"White Slave Traffic\"",
                           conclusion="1904-05-18", eif_text="18 July 1905, in accordance with article 8.",
                           registered=True, reg_full="LoN-11", depositary=zt.SG, volume=None,
                           page=None, lnts_volume=1, url="u", ref="VII-8", today=TODAY)
check("League: LNTS + volume", (lon["code"], lon["codeNumber"], "pages" in lon), ("LNTS", "1", False))
check("League: registration line", "League of Nations registration no.: 11" in lon["extra"], True)
check("League: note on the page", len(notes), 1)
annex, notes = zt.build_item(title="Annex I", conclusion="1948-07-10", eif_text="", registered=True,
                             reg_full="I-521", depositary=zt.SG, volume=33, page=290,
                             lnts_volume=None, url="u", today=TODAY)
check("registered, no date: no 'not in force'", ("status:" in annex["extra"], len(notes)), (False, 1))
tpnw, notes = zt.build_item(title="Treaty on the Prohibition of Nuclear Weapons", conclusion="2017-07-07",
                            eif_text="22 January 2021, in accordance with article 15.", registered=True,
                            reg_full="I-56487", depositary=zt.SG, volume=3370, page=None,
                            lnts_volume=None, url="u", today=TODAY)
check("volume without page", (tpnw["codeNumber"], "pages" in tpnw, len(notes)), ("3370", False, 1))
check("basename", zt.basename(item), "UNTS_1833_3_UNCLOS")

print("titles and parents")
check("deposited note -> depositary", zt.clean_title(
    "Charter of the United Nations (deposited in the archives of the Government of the United States of America)"),
    ("Charter of the United Nations", "Government of the United States of America"))
check("footnote mark", zt.clean_title("International Sugar Agreement, 1977*")[0], "International Sugar Agreement, 1977")
index = {e["ref"]: e for e in json.loads((SKILL / "cache" / "index.json").read_text(encoding="utf-8"))["treaties"]}
for ref, want in [("IV-9-b", "IV-9"), ("XI-B-16-171", "XI-B-16"), ("III-2-1", "III-2"),
                  ("IV-4", None), ("XI-B-16", None)]:
    check(f"parent of {ref}", zt.parent_ref(ref, index), want)

print(f"all {len(index)} MTDSG index titles")
bad = []
for ref, e in index.items():
    t, dep = zt.clean_title(e["title"])
    if t.endswith(("*", " ")) or "deposited in the archives" in t or not t:
        bad.append(ref)
    it, _ = zt.build_item(title=t, conclusion="", eif_text=None, registered=True, reg_full=None,
                          depositary=dep, volume=None, page=None, lnts_volume=None, url="u",
                          ref=ref, today=TODAY)
    ET.fromstring(zotero_rdf.build_rdf(it))
check("every title clean and every item renders", bad, [])

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
