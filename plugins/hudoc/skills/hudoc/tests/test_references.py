#!/usr/bin/env python3
"""How hudoc.py turns a user's reference into a HUDOC query: application
numbers ("no. 14038/88"), ECLIs, Lucene pass-through, and case names
narrowed by respondent state ("Kurt v. Turkey" must not find Kurt v.
Austria). The table in fixtures/references.json is shared with
tests/test_browser.js, so the CLI and the in-page helper query alike.

No network. Run with `python plugins/hudoc/skills/hudoc/tests/test_references.py`.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import hudoc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


refs = json.loads((HERE / "fixtures" / "references.json").read_text(encoding="utf-8"))
for ref, clause, fallback in refs:
    got_clause, _, got_fallback, _ = hudoc.reference_query(ref)
    check(ref, [got_clause, got_fallback], [clause, fallback])

# resolve() retries without the respondent when the narrowed query is empty.
calls = []


def fake_query(clause, **kw):
    calls.append(clause)
    if "respondent" in clause:
        return {"results": []}
    return {"results": [{"columns": {"itemid": "001-1", "docname": "CASE OF KURT v. X",
                                     "doctype": "HEJUD", "languageisocode": "ENG"}}]}


hudoc._query = fake_query
row = hudoc.resolve("Kurt v. Turkey")
check("fallback without respondent", (row["itemid"], calls),
      ("001-1", ['docname:Kurt AND respondent:"TUR"', "docname:Kurt"]))

# "Kurt v. Turkey" (live test, 2026-09): docname:Kurt also matches Özkurt,
# Bozkurt …, 213 hits. The 1998 judgment is past the first 50 rows, and a
# newer Özkurt judgment would win on date. Further pages are read, and a
# whole-word name match ranks first.
def kurt_rows():
    rows = [{"itemid": "001-145119", "docname": "CASE OF BELEK AND ÖZKURT v. TURKEY (No. 7)",
             "doctype": "HEJUD", "doctypebranch": "COMMITTEE", "languageisocode": "ENG",
             "kpdate": "2014-07-01T00:00:00"}]
    rows += [{"itemid": f"001-9{i:04d}", "docname": f"CASE OF BOZKURT {i} v. TURKEY",
              "doctype": "HEJUD", "doctypebranch": "CHAMBER", "languageisocode": "ENG",
              "kpdate": "2010-01-01T00:00:00"} for i in range(150)]
    rows.append({"itemid": "001-58198", "docname": "CASE OF KURT v. TURKEY",
                 "doctype": "HEJUD", "doctypebranch": "CHAMBER", "languageisocode": "ENG",
                 "kpdate": "1998-05-25T00:00:00"})
    rows += [{"itemid": f"001-8{i:04d}", "docname": f"CASE OF KIZILKURT {i} v. TURKEY",
              "doctype": "HEJUD", "doctypebranch": "CHAMBER", "languageisocode": "ENG",
              "kpdate": "2012-01-01T00:00:00"} for i in range(61)]
    return rows


KURT = kurt_rows()
starts = []


def paged_query(clause, start=0, length=20, **kw):
    starts.append(start)
    page = KURT[start:start + length]
    return {"resultcount": len(KURT), "results": [{"columns": c} for c in page]}


hudoc._query = paged_query
row = hudoc.resolve("Kurt v. Turkey")
check("Kurt v. Turkey finds the whole-word match past page 1", row["itemid"], "001-58198")
check("pages read up to the hit count", starts, [0, 50, 150])
check("whole-word match", [hudoc.name_matches({"docname": d}, ["Kurt"]) for d in
                           ["CASE OF KURT v. TURKEY", "CASE OF BELEK AND ÖZKURT v. TURKEY", "KURT c. TURQUIE"]],
      [True, False, True])
check("name leaves out 'and Others'", hudoc.reference_query("Lautsi and Others v. Italy [GC]")[3], ["Lautsi"])
check("one-letter applicant", hudoc.reference_query("A v. Norway")[3], ["A"])

print("%d failure(s)" % len(failures) if failures else "all ok")
sys.exit(1 if failures else 0)
