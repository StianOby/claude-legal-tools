#!/usr/bin/env python3
"""Offline tests for the icj CLI (no network): state resolution, case
search (word matching, nicknames, accents), the case-page cache TTL, and
error handling. Case titles are real ones from icj-cij.org.
Run: python tests/test_icj.py
"""

import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

os.environ["ICJ_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _common  # noqa: E402
import cases  # noqa: E402
import icj  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("resolve_state")
for inp, want in [("uk", "gb"), ("UK", "gb"), ("United Kingdom", "gb"), ("no", "no"),
                  ("Norway", "no"), ("gb", "gb"), ("ivory coast", "ci"), ("Narnia", None)]:
    check(repr(inp), _common.resolve_state(inp), want)

TITLES = [
    (192, "Application of the Convention on the Prevention and Punishment of the Crime of Genocide in the Gaza Strip (South Africa v. Israel)", "Contentious"),
    (187, "Obligations of States in respect of Climate Change", "Advisory"),
    (182, "Allegations of Genocide under the Convention on the Prevention and Punishment of the Crime of Genocide (Ukraine v. Russian Federation)", "Contentious"),
    (169, "Legal Consequences of the Separation of the Chagos Archipelago from Mauritius in 1965", "Advisory"),
    (148, "Whaling in the Antarctic (Australia v. Japan: New Zealand intervening)", "Contentious"),
    (131, "Legal Consequences of the Construction of a Wall in the Occupied Palestinian Territory", "Advisory"),
    (124, "Territorial and Maritime Dispute (Nicaragua v. Colombia)", "Contentious"),
    (122, "Application for Revision of the Judgment of 11 July 1996 in the Case concerning Application of the Convention on the Prevention and Punishment of the Crime of Genocide (Bosnia and Herzegovina v. Yugoslavia)", "Contentious"),
    (139, "Request for Interpretation of the Judgment of 31 March 2004 in the Case concerning Avena and Other Mexican Nationals (Mexico v. United States of America)", "Contentious"),
    (128, "Avena and Other Mexican Nationals (Mexico v. United States of America)", "Contentious"),
    (97, "Request for an Examination of the Situation in Accordance with Paragraph 63 of the Court's Judgment of 20 December 1974 in the Nuclear Tests (New Zealand v. France) Case", "Contentious"),
    (92, "Gabčíkovo-Nagymaros Project (Hungary/Slovakia)", "Contentious"),
    (59, "Nuclear Tests (New Zealand v. France)", "Contentious"),
    (58, "Nuclear Tests (Australia v. France)", "Contentious"),
    (91, "Application of the Convention on the Prevention and Punishment of the Crime of Genocide (Bosnia and Herzegovina v. Serbia and Montenegro)", "Contentious"),
    (70, "Military and Paramilitary Activities in and against Nicaragua (Nicaragua v. United States of America)", "Contentious"),
    (64, "United States Diplomatic and Consular Staff in Tehran (United States of America v. Iran)", "Contentious"),
    (105, "Legality of Use of Force (Serbia and Montenegro v. Belgium)", "Contentious"),
    (100, "Difference Relating to Immunity from Legal Process of a Special Rapporteur of the Commission on Human Rights", "Advisory"),
]
cases.list_all = lambda force_refresh=False: {
    "source_url": "x", "fetched_at": 0, "count_total": len(TITLES),
    "cases": [{"case_id": i, "title": t, "kind": k, "year_introduced": "", "year_concluded": ""}
              for i, t, k in TITLES]}


def ids(q):
    return [c["case_id"] for c in cases.search(q)["cases"]]


print("cases search")
check("Bosnia Genocide (words in any order)", ids("Bosnia Genocide"), [91, 122])
check("Israeli Wall (nickname)", ids("Israeli Wall"), [131])
check("nickname plus 'advisory opinion'", ids("Israeli Wall advisory opinion"), [131])
check("Chagos", ids("Chagos"), [169])
check("Whaling-saken (Norwegian suffix)", ids("Whaling-saken"), [148])
check("Nicaragua nickname first", ids("Nicaragua")[0], 70)
check("Nicaragua v. Colombia is not the nickname", ids("Nicaragua v. Colombia"), [124])
check("USA alias", ids("Nicaragua v. USA"), [70])
check("prefix: Russia -> Russian Federation", ids("Ukraine v. Russia"), [182])
check("accents ignored", ids("Gabcikovo"), [92])
check("Tehran hostages", ids("Tehran hostages"), [64])
check("full title with 'US'", ids("US Diplomatic and Consular Staff in Tehran"), [64])
check("person's name (Cumaraswamy)", ids("Cumaraswamy"), [100])
check("former name Yugoslavia", ids("Yugoslavia v. Belgium"), [105])
check("the case before its interpretation", ids("Avena"), [128, 139])
check("the cases before a later request", ids("Nuclear Tests"), [59, 58, 97])
check("kind is searchable", ids("climate advisory"), [187])
r = cases.search("Lotus")
check("no hit has a hint pointing to PCIJ", (r["count_returned"], "pcij" in r.get("hint", "")), (0, True))

print("case pages use the short TTL")
seen = {}
cases._fetch_cached = lambda url, force_refresh=False, ttl=None: seen.update(ttl=ttl) or ("<html></html>", None, False)
cases.fetch_cached("https://www.icj-cij.org/case/1")
check("ttl is one day", seen["ttl"], 24 * 3600)

print("errors")


def boom(url, **kw):
    raise RuntimeError(f"GET {url} failed: <urlopen error [Errno 11001] getaddrinfo failed>")


_common.http_get = boom
cases._fetch_cached = _common.fetch_cached
err, out = io.StringIO(), io.StringIO()
with redirect_stderr(err), redirect_stdout(out):
    code = icj.main(["cases", "show", "82", "--force-refresh"])
check("network error: exit 1", code, 1)
check("network error: one line, no traceback",
      (err.getvalue().startswith("icj: error: GET"), "Traceback" in err.getvalue()), (True, False))

print("pdf file names")
R = "https://www.icj-cij.org/sites/default/files/case-related/70/"
p = cases._parse_pdf_filename(R + "070-19841126-JUD-01-00-EN.pdf")
check("zero-padded id parses", (p or {}).get("doc_type"), "jud")
check("lang lower-cased", (p or {}).get("lang"), "en")
check("mismatched id rejected", cases._parse_pdf_filename(R + "071-19841126-JUD-01-00-EN.pdf"), None)
check("numeric name not parsed", cases._parse_pdf_filename(R + "9617.pdf"), None)

print("pleadings inside mixed subpages (case 70, /jurisdiction-admissibility)")


def item(label, fname):
    it = {"label": label, "url": R + fname}
    parsed = cases._parse_pdf_filename(R + fname)
    if parsed:
        it["doc_type"] = parsed["doc_type"]
    return it


kept, pleadings = cases._split_pleadings([
    item("Memorial of Nicaragua", "9617.pdf"),
    item("Counter-Memorial of the United States of America", "9627.pdf"),
    item("Verbatim record 1984", "070-19841008-ORA-01-00-BI.pdf"),
    item("Judgment of 26 November 1984", "070-19841126-JUD-01-00-EN.pdf"),
    item("French", "070-19841126-JUD-01-00-FR.pdf"),
    item("Written Observations on the Declaration of Intervention", "9623.pdf"),
    item("French", "9622.pdf"),
    item("Declaration of Intervention of the Republic of El Salvador", "9625.pdf"),
    item("French", "9624.pdf"),
])
check("kept", [k["label"] for k in kept],
      ["Judgment of 26 November 1984", "French",
       "Declaration of Intervention of the Republic of El Salvador", "French"])
check("pleadings", len(pleadings), 5)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
