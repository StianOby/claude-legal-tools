#!/usr/bin/env python3
"""Offline tests for scripts/zotero_treaty.py (no network): every treaty in
the saved Treaty Office index (fixtures/index.json, 234 records from ETS 1 of
1949 to CETS 232 of 2026) becomes a clean Zotero statute item, and the ECHR
comes out as in the shared group library's ECHR example.
Run: python tests/ets/test_zotero_treaty.py
"""

import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ["ETS_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "ets" / "skills" / "ets" / "scripts"))
import zotero_rdf  # noqa: E402
import zotero_treaty as zt  # noqa: E402

INDEX = json.loads((Path(__file__).resolve().parent / "fixtures" / "index.json").read_text(encoding="utf-8"))
BY_NUM = {t["Numero_traite"]: t for t in INDEX}
TODAY = "2026-10-21"

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("ECHR as in the group library's example")
echr = zt.treaty_to_item(BY_NUM["005"], TODAY)
check("item", echr, {
    "itemType": "statute",
    "nameOfAct": "Convention for the Protection of Human Rights and Fundamental Freedoms",
    "publicLawNumber": "ETS No. 5",
    "dateEnacted": "1953-09-03",
    "shortTitle": "ECHR",
    "url": "https://www.coe.int/en/web/conventions/full-list?module=treaty-detail&treatynum=005",
    "language": "English",
    "extra": "type: treaty\navailable-date: 1950-11-04\nUN registration no.: 2889",
})
check("basename", zt.basename(echr), "ETS_5_ECHR")

print("numbers")
for num, want in [("001", "ETS No. 1"), ("012A", "ETS No. 12A"), ("061B", "ETS No. 61B"),
                  ("193", "ETS No. 193"), ("194", "CETS No. 194"), ("232", "CETS No. 232")]:
    check(num, zt.treaty_number(num), want)

print("protocols, treaties not in force, odd titles")
p11 = zt.treaty_to_item(BY_NUM["155"], TODAY)
check("integrated amending protocol", p11["history"],
      "Parent treaty: ETS No. 5 (this amending protocol is integrated into it)")
check("(*) removed", p11["nameOfAct"].endswith("established thereby"), True)
p12 = zt.treaty_to_item(BY_NUM["177"], TODAY)
check("other protocol", p12["history"], "Parent treaty: ETS No. 5")
ai = zt.treaty_to_item(BY_NUM["225"], TODAY)
check("not in force: no dateEnacted", "dateEnacted" in ai, False)
check("not in force: status line", "status: not in force (as of 2026-10-21)" in ai["extra"], True)
check("(CETS 230) removed", zt.treaty_to_item(BY_NUM["230"], TODAY)["nameOfAct"].endswith("in the form of Series"), True)
check("(CETS No 231) removed", "CETS" in zt.treaty_to_item(BY_NUM["231"], TODAY)["nameOfAct"], False)
check("basename cut at a word",
      zt.basename(zt.treaty_to_item(BY_NUM["225"], TODAY)),
      "CETS_225_Council_of_Europe_Framework_Convention_on_Artificial")

print(f"all {len(INDEX)} treaties")
bad_title, bad_date, bad_extra, bad_rdf = [], [], [], []
for t in INDEX:
    it = zt.treaty_to_item(t, TODAY)
    if re.search(r"\((C?ETS)|\(\*\)", it["nameOfAct"]) or it["nameOfAct"] != it["nameOfAct"].strip():
        bad_title.append(t["Numero_traite"])
    if bool(it.get("dateEnacted")) != bool(t.get("Date_vigueur_ste")):
        bad_date.append(t["Numero_traite"])
    if not it["extra"].startswith("type: treaty\navailable-date: "):
        bad_extra.append(t["Numero_traite"])
    try:
        ET.fromstring(zotero_rdf.build_rdf(it))
    except Exception:
        bad_rdf.append(t["Numero_traite"])
check("no number left in any title", bad_title, [])
check("dateEnacted exactly when in force", bad_date, [])
check("every Extra has type and available-date", bad_extra, [])
check("every item renders as RDF", bad_rdf, [])
check("34 not in force", sum("status: not in force" in zt.treaty_to_item(t, TODAY)["extra"] for t in INDEX), 34)
check("basenames unique", len({zt.basename(zt.treaty_to_item(t, TODAY)) for t in INDEX}), len(INDEX))

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
