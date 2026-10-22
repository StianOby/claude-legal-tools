#!/usr/bin/env python3
"""Live check (network; not run by CI): match every record of the
2026-10-21 probe (fixtures/probe-2026-10-21.json, 37 Consilium records) to
Cellar with scripts/zotero_agreement.py, and compare with the CELEX numbers
verified by hand on 2026-10-22. None = no citation is the right answer
(primary law, numbering outside the date scheme, not in Cellar). About a
minute; Cellar answers 503 now and then, which the script retries.
Run: python tests/eu-agreements-treaties/live_cellar_match.py
"""

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "eu-agreements-treaties" / "skills" / "eu-agreements-treaties"
sys.path.insert(0, str(SKILL / "scripts"))
import zotero_agreement as za  # noqa: E402

EXPECTED = {
    "1972004": None,              # Accession Treaty 1972: Cellar has the wrong signature date (1970-04-22)
    "1988055": "41988A0592",      # Lugano 1988: sector 4, found by its OJ issue
    "1989038": "21989A1013(03)", "1989084": "21990A0421(03)", "1993016": "21993A0501(05)",
    "1995044": "21995A0808(01)", "1999025": "21999A0710(02)", "2002082": "22002A1217(01)",
    "2003104": "22004A0429(04)", "2004060": "22004A1209(01)", "2006042": "22006A1212(01)",
    "2007059": "22007A0825(05)", "2010017": "22010A1029(01)", "2011036": "22011A1029(01)",
    "2014030": None,              # exchange of letters not in Cellar on its own
    "2016032": "22016A0528(01)", "2017003": "22019A0128(01)", "2019005": "22020A0303(01)",
    "2024009": "22024A02603",
    "2026004": "22026A02350",     # the Iceland agreement, in Cellar since 2026-10-21 (before: no match, not Norway's)
    "2006052": "22006A1016(01)", "2010035": "22013A0226(01)", "2018049": "22019A0524(02)",
    "2009066": "22012A0413(01)", "1992045": "21994A0103(01)", "1994093": "21994A1231(52)",
    "1978002": "21975A1114(01)", "1972002": "21972A1219(01)", "1993118": "21994A0625(01)",
    "2025010": "22025A02480", "2014074": "22014A1230(01)", "2024003": "22024A01214",
    "2016062": "22016A1222(01)", "2026009": "22026A01562",
}

records = json.loads((Path(__file__).resolve().parent / "fixtures" / "probe-2026-10-21.json").read_text(encoding="utf-8"))
bad = 0
for rec in records:
    if rec["is_proces_verbal"]:
        continue
    m = za.find_match(rec)
    got = m[0] if m else None
    want = EXPECTED[rec["id"]]
    ok = got == want
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {rec['id']} {got or '—':16} {'' if ok else f'(want {want})'}")
print(f"{bad} mismatch(es)" if bad else "all match")
sys.exit(1 if bad else 0)
