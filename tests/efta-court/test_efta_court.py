#!/usr/bin/env python3
"""Offline tests for scripts/efta_court.py (no network): document-label
parsing, --type matching, cache file names, and the re-fetch of cached
pages for cases that were still pending. Labels are real ones from
eftacourt.int case pages. Run: python tests/efta-court/test_efta_court.py
"""

import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr

os.environ["EFTA_COURT_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugins", "efta-court", "skills", "efta-court", "scripts"))
import efta_court as ec  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("document labels")
for label, want in [
    ("14/15 Judgment 19/04/2016 EN", ("judgment", "19/04/2016", "EN")),
    ("8/26 Request AO 06/05/2026 NO", ("request", "06/05/2026", "NO")),
    ("12/23 Request AO EN", ("request", "", "EN")),
    ("1/24 Report for the Hearing EN", ("report", "", "EN")),
    ("2/11 RH 08/04/2013 NO", ("report", "08/04/2013", "NO")),
    ("3/04 RH Rev 04/04/2013 EN", ("report", "04/04/2013", "EN")),
    ("5/22 - Judgment DE", ("judgment", "", "DE")),
    ("15/10 Order of the President 08/04/2013 EN", ("order", "08/04/2013", "EN")),
    ("16/20 Press Release 23/11/2021 IS", ("press-release", "23/11/2021", "IS")),
    ("6/25 Information Note 04/08/2025", ("information-note", "04/08/2025", "")),
    ("9/97 Advisory Opinion 02/04/2013 IS", ("advisory-opinion", "02/04/2013", "IS")),
    ("1/94 Judgment 16/12/1994 FI", ("judgment", "16/12/1994", "FI")),
]:
    d = ec._parse_doc_label(label)
    check(label, (d["type"], d["date"], d["lang"]), want)


def doc(label):
    return {"label": label, "url": f"https://x/{label}", **ec._parse_doc_label(label)}


DOCS = [doc(x) for x in [
    "2/23 Notification 25/04/2023 EN",
    "2/23 Order 01/06/2023 EN",
    "2/23 Costs Order 01/09/2023 EN",
    "2/23 Report for the Hearing 28/07/2023 DE",
    "2/23 Report for the Hearing 28/07/2023 EN",
    "2/23 Report for the Hearing EN",
    "2/23 Judgment 25/01/2024 EN",
    "2/23 Judgment 25/01/2024 NO",
    "2/23 Something unparseable",
]]


def choose(t, lang="EN"):
    err = io.StringIO()
    with redirect_stderr(err):
        d = ec._choose_doc(DOCS, t, lang)
    return (d["label"] if d else None), err.getvalue()


print("--type matching")
check("order does not match costs order", choose("order")[0], "2/23 Order 01/06/2023 EN")
check("costs-order", choose("costs-order")[0], "2/23 Costs Order 01/09/2023 EN")
check("'costs order' with a space", choose("costs order")[0], "2/23 Costs Order 01/09/2023 EN")
check("alias 'hearing report'", choose("hearing report")[0], "2/23 Report for the Hearing 28/07/2023 EN")
check("unparsed label never matches", choose("unparseable")[0], None)
check("missing type", choose("opinion-aag")[0], None)
label, note = choose("judgment", "NO")
check("requested language used", (label, note), ("2/23 Judgment 25/01/2024 NO", ""))
label, note = choose("judgment", "IS")
check("fallback to EN", label, "2/23 Judgment 25/01/2024 EN")
check("fallback says so", "no IS version" in note, True)
label, note = choose("report", "EN")
check("several matches: note points to --doc", "--doc" in note, True)

print("cache file names")
stem = lambda i: ec._doc_stem(DOCS, DOCS[i])  # noqa: E731
check("unique type+lang keeps the short name", stem(6), "judgment-EN")
check("same type+lang, own date", stem(4), "report-2023-07-28-EN")
check("same type+lang, no date", stem(5), "report-EN-6")
check("other language unaffected", stem(3), "report-DE")
check("all stems distinct", len({stem(i) for i in range(len(DOCS))}), len(DOCS))

print("pending pages are re-fetched")
PENDING = '<span class="c-case-meta-type">Status:</span> Pending'
DECIDED = '<span class="c-case-meta-type">Status:</span> Decided'
entry = {"case_number": "E-9/26", "case_numbers": ["E-9/26"], "slug": "e-09-26", "plain": True,
         "url": "https://eftacourt.int/cases/e-09-26/", "sources": [], "country": "", "procedure": "",
         "status": None, "parties": ""}
idx = {"fetched_at": ec._now_iso(), "cases": [entry]}
fetches = []
page = {"html": PENDING}
ec.fetch_text = lambda url: fetches.append(url) or page["html"]

check("first fetch", ec.fetch_case("E-9/26", idx=idx, persist=False)["status"], "Pending")
page["html"] = DECIDED
check("fresh pending page comes from cache", (ec.fetch_case("E-9/26", idx=idx, persist=False)["status"], len(fetches)),
      ("Pending", 1))
raw = ec.cache_dir() / "cases" / "E-9-26" / "raw.html"
old = time.time() - ec.PENDING_TTL - 60
os.utime(raw, (old, old))
check("old pending page is re-fetched", (ec.fetch_case("E-9/26", idx=idx, persist=False)["status"], len(fetches)),
      ("Decided", 2))
os.utime(raw, (old, old))
check("old decided page stays cached", (ec.fetch_case("E-9/26", idx=idx, persist=False)["status"], len(fetches)),
      ("Decided", 2))

print("index age")
check("fresh index", ec._index_age({"fetched_at": ec._now_iso()}) < 5, True)
check("old index", ec._index_age({"fetched_at": "2020-01-01T00:00:00Z"}) > ec.INDEX_TTL, True)
check("missing timestamp counts as stale", ec._index_age({}), float("inf"))

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
