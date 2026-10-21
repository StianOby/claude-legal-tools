#!/usr/bin/env python3
"""Offline tests for lookup in scripts/untc.py: MTDSG index first, then the
live UNTS Online title search (stubbed here), and only when both miss is an
old index rebuilt; NO MATCH names the index date; a partial rebuild never
shrinks the index; UNTS result pages parse in both markups.
Run: python tests/untc/test_index_age.py
"""

import io
import json
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

os.environ["UNTC_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc" / "scripts"))
import untc  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def stamp(days_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days_ago * 86400))


OLD_TREATY = {"ref": "IV-4", "title": "International Covenant on Civil and Political Rights",
              "place_date": "New York, 16 December 1966"}
NEW_TREATY = {"ref": "XXI-10", "title": "Agreement on marine biological diversity of areas beyond national jurisdiction",
              "place_date": "New York, 19 June 2023"}


def write_index(days_ago, treaties):
    untc.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    untc.INDEX_PATH.write_text(json.dumps({"fetched_utc": stamp(days_ago), "source": "x",
                                           "chapters": [4], "treaties": treaties}), encoding="utf-8")


UNTS_HITS = {}      # query -> rows the stubbed UNTS search returns
unts_calls = []


def fake_unts_find(query, limit=10):
    unts_calls.append(query)
    rows = UNTS_HITS.get(query, [])
    return "phrase", str(len(rows)), rows[:limit]


untc.unts_find = fake_unts_find


def lookup(query):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        untc.cmd_lookup(SimpleNamespace(query=query, limit=5))
    return out.getvalue(), err.getvalue()


print("index_age_days()")
check("10 days", round(untc.index_age_days({"fetched_utc": stamp(10)})), 10)
check("missing stamp is infinitely old", untc.index_age_days({}), float("inf"))

print("a miss in both the index and UNTS rebuilds an old index and finds the new treaty")
rebuilds = []


def fake_build(refresh=False, **kw):
    rebuilds.append(refresh)
    write_index(0, [OLD_TREATY, NEW_TREATY])
    return untc._read_json(untc.INDEX_PATH)


untc.build_index = fake_build
write_index(30, [OLD_TREATY])
out, err = lookup("marine biological diversity")
check("rebuilt once", rebuilds, [True])
check("found after the rebuild", "XXI-10" in out, True)

print("a miss on a fresh index does not rebuild, and says the index date")
rebuilds.clear()
out, err = lookup("no such treaty zzqx")
check("no rebuild", rebuilds, [])
check("NO MATCH names the index date", "MTDSG index (as of " + stamp(0)[:10] in out, True)

print("a treaty outside MTDSG is found in UNTS, without rebuilding an old index")
rebuilds.clear()
write_index(30, [OLD_TREATY])
UNTS_HITS["waiver of refunds"] = [{"reg": "I-37181", "title": "Agreement between Norway and Germany on the waiver of refunds",
                                   "objid": "080000028008dd46", "concluded": "28/05/1999", "eif": "31/03/2000",
                                   "type": "Bilateral"}]
out, err = lookup("waiver of refunds")
check("UNTS hit shown", "I-37181" in out and "unts-details 080000028008dd46" in out, True)
check("labelled as outside MTDSG", "Not in the MTDSG index" in out, True)
check("no rebuild", rebuilds, [])

print("a stale index cannot hide a newer SG-deposited treaty that UNTS finds")
NEW_IN_FORCE = dict(NEW_TREATY, title="Agreement under the Convention on the Law of the Sea on marine biodiversity")


def build_with_new(refresh=False, **kw):
    rebuilds.append(refresh)
    write_index(0, [OLD_TREATY, NEW_IN_FORCE])
    return untc._read_json(untc.INDEX_PATH)


untc.build_index = build_with_new
UNTS_HITS["marine biodiversity"] = [{"reg": "I-58000", "title": NEW_IN_FORCE["title"], "objid": "0800000280aaaaaa",
                                     "concluded": time.strftime("%d/%m/%Y", time.gmtime(time.time() - 5 * 86400)),
                                     "eif": "", "type": "Open Multilateral"}]
rebuilds.clear()
write_index(30, [OLD_TREATY])
out, err = lookup("marine biodiversity")
check("newer multilateral UNTS hit: index rebuilt", rebuilds, [True])
check("… and reported as the MTDSG treaty, not 'Not in the MTDSG index'",
      ("XXI-10" in out, "Not in the MTDSG index" in out), (True, False))

rebuilds.clear()
write_index(30, [OLD_TREATY])
UNTS_HITS["old multilateral"] = [dict(UNTS_HITS["waiver of refunds"][0], type="Closed Multilateral", concluded="01/02/1999")]
out, err = lookup("old multilateral")
check("multilateral concluded long before the index: no rebuild", rebuilds, [])
recent_bilateral = dict(UNTS_HITS["waiver of refunds"][0], concluded=time.strftime("%d/%m/%Y"))
UNTS_HITS["recent bilateral"] = [recent_bilateral]
out, err = lookup("recent bilateral")
check("recent bilateral: no rebuild", rebuilds, [])

def offline_build(refresh=False, **kw):
    raise untc.urllib.error.URLError("offline")


untc.build_index = offline_build
write_index(30, [OLD_TREATY])
out, err = lookup("marine biodiversity")
check("failed rebuild: UNTS hit shown with a CAUTION and a coverage warning",
      ("CAUTION: I-58000" in out, "COVERAGE WARNING" in err), (True, True))
untc.build_index = fake_build

print("unts-details flags a treaty deposited with the Secretary-General")


class FakeOpener:
    def __init__(self, page):
        self.page = page

    def open(self, *a, **kw):
        return io.BytesIO(self.page.encode("utf-8"))


DETAILS = ("<td>Registration Number</td><td>14668</td><td>Title</td><td>International Covenant</td>"
           "<td>Participant(s)</td><td>Places/dates of conclusion</td><td>Place</td><td>Date</td><td>New York</td>"
           "<td>16/12/1966</td><td>EIF information</td><td>23 March 1976</td><td>Authentic texts</td><td>English</td>"
           "<td>Depositary</td><td>{dep}</td><td>Registration Date</td><td>ex officio 23 March 1976</td>"
           "<td>Subject terms</td><td>Agreement type</td><td>Multilateral</td><td>UNTS Volume Number</td>"
           "<td>999 (p.171)</td><td>Publication format</td>")
saved = untc._unts_state["opener"]
untc._unts_state["opener"] = FakeOpener(DETAILS.format(dep="Secretary-General of the United Nations"))
d = untc.unts_details("0800000280004bf5")
check("SG depositary: mtdsg true, with a note", (d["mtdsg"], "status" in d.get("note", ""), d["unts_volume"], d["unts_page"]),
      (True, True, 999, 171))
untc._unts_state["opener"] = FakeOpener(DETAILS.format(dep="Government of the United States of America"))
check("other depositary: mtdsg false", untc.unts_details("0800000280004bf5")["mtdsg"], False)
untc._unts_state["opener"] = saved

print("an MTDSG hit never calls UNTS")
unts_calls.clear()
write_index(0, [OLD_TREATY])
out, err = lookup("International Covenant on Civil and Political Rights")
check("IV-4 found", "IV-4" in out, True)
check("UNTS not searched", unts_calls, [])

print("a failed rebuild gives a coverage warning")


def failing_build(refresh=False, **kw):
    raise untc.urllib.error.URLError("offline")


untc.build_index = failing_build
write_index(30, [OLD_TREATY])
out, err = lookup("marine biological diversity")
check("coverage warning", "COVERAGE WARNING" in err and stamp(30)[:10] in err, True)

print("a partial rebuild never shrinks the index")
import importlib  # noqa: E402
untc = importlib.reload(untc)  # undo the build_index stubs above

CH4_OLD = {"ref": "IV-4", "chapter_int": 4, "subchapter": "", "title": "ICCPR", "place_date": "x"}
CH6_OLD = {"ref": "VI-19", "chapter_int": 6, "subchapter": "", "title": "Single Convention", "place_date": "x"}
CH4_NEW = {"ref": "IV-16", "chapter_int": 4, "subchapter": "", "title": "Disappearances", "place_date": "x"}


def write_full_index(days_ago, treaties):
    untc.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    untc.INDEX_PATH.write_text(json.dumps({"fetched_utc": stamp(days_ago), "source": "x",
                                           "chapters": [4, 6], "treaties": treaties}), encoding="utf-8")


def stub_pages(pages):
    """pages: chapter -> list of entry dicts, or an Exception to raise."""
    def http_get(url, **kw):
        ch = int(url.split("id=")[1].split("&")[0])
        if isinstance(pages.get(ch), Exception):
            raise pages[ch]
        return str(ch)

    def parse(page_html, ch):
        return [untc.IndexEntry(**e) for e in pages.get(ch, [])]
    untc.http_get = http_get
    untc.parse_chapter_index = parse


write_full_index(30, [CH4_OLD, CH6_OLD])
stub_pages({4: [CH4_OLD, CH4_NEW], 6: untc.urllib.error.URLError("timeout")})
err = io.StringIO()
with redirect_stderr(err):
    payload = untc.build_index(refresh=True, polite_delay=0, chapter_range=[4, 6])
refs = sorted(e["ref"] for e in payload["treaties"])
check("failed chapter kept from the old index", refs, ["IV-16", "IV-4", "VI-19"])
check("index keeps the old date", payload["fetched_utc"], stamp(30))
check("stale chapters recorded", payload.get("stale_chapters"), [6])
check("coverage warning", "COVERAGE WARNING" in err.getvalue(), True)

write_full_index(30, [CH4_OLD, CH6_OLD])
stub_pages({4: [CH4_OLD], 6: []})
with redirect_stderr(io.StringIO()):
    payload = untc.build_index(refresh=True, polite_delay=0, chapter_range=[4, 6])
check("a chapter that suddenly lists nothing is kept too", sorted(e["ref"] for e in payload["treaties"]),
      ["IV-4", "VI-19"])

write_full_index(30, [CH4_OLD, CH6_OLD])
stub_pages({4: untc.urllib.error.URLError("down"), 6: untc.urllib.error.URLError("down")})
try:
    with redirect_stderr(io.StringIO()):
        untc.build_index(refresh=True, polite_delay=0, chapter_range=[4, 6])
    got = "no error"
except untc.urllib.error.URLError:
    got = "URLError"
check("nothing fetched: error, index untouched", (got, json.loads(untc.INDEX_PATH.read_text(encoding="utf-8"))["fetched_utc"]),
      ("URLError", stamp(30)))

write_full_index(0, [CH4_OLD, CH6_OLD])
stub_pages({4: [CH4_OLD, CH4_NEW], 6: [CH6_OLD]})
with redirect_stderr(io.StringIO()):
    payload = untc.build_index(refresh=True, polite_delay=0, chapter_range=[4, 6])
check("a full rebuild gets today's date and no stale chapters",
      (payload["fetched_utc"][:10], "stale_chapters" in payload), (stamp(0)[:10], False))

print("UNTS Online pages: rows in both markups, query text")
ROW = ('<tr align="left" valign="top"><td {w20}>I-37181</td><td title="Agreement between the Government of the Kingdom of '
       'Norway and the Government of the Federal Republic of Germany" {w18}>Agreement between...</td><td><div></div>'
       '<a href="/Pages/showDetails.aspx?objid=080000028008dd46&amp;clang=_en">See Details</a></td>'
       '<td {w15}>28/05/1999</td><td {w15}>31/03/2000</td><td {w18}>Bilateral</td><td class="invisible">1</td></tr>')
for name, attrs in [("style markup", dict(w20='style="width:20%;"', w18='style="width:18%;"', w15='style="width:15%;"')),
                    ("width markup", dict(w20='width="20%"', w18='width="18%"', w15='width="15%"'))]:
    page = '<table id="dgSearch"><tr class="thead-one"><th>Registration</th></tr>' + ROW.format(**attrs) + "</table>"
    rows = untc.parse_unts_rows(page)
    check(name, [(r["reg"], r["objid"], r["concluded"], r["eif"], r["type"], r["title"][-15:]) for r in rows],
          [("I-37181", "080000028008dd46", "28/05/1999", "31/03/2000", "Bilateral", "Republic of Germany"[-15:])])
check("query drops a trailing parenthetical",
      untc.unts_query_text("Charter of the United Nations (deposited in the archives of the Government of the United States)"),
      "Charter of the United Nations")
long_title = "Agreement " + "concerning the very long title " * 6
q = untc.unts_query_text(long_title)
check("query cut to 100 characters at a word", (len(q) <= 100, long_title.startswith(q), not q.endswith(" ")), (True, True, True))

print("unts_find falls back: phrase, all words, then without an 'adopted …' clause")
untc = importlib.reload(untc)
searches = []


def fake_search(q, mode="phrase", **kw):
    searches.append((mode, q))
    if mode == "phrase" and q == "Amendment to the Montreal Protocol on Substances that Deplete the Ozone Layer":
        return "2", [{"reg": "A-26369", "title": q, "objid": "1" * 16, "concluded": "17/09/1997", "eif": "",
                      "type": "Open Multilateral"},
                     {"reg": "A-26369", "title": "Procès-verbal of rectification of the " + q, "objid": "2" * 16,
                      "concluded": "05/08/2018", "eif": "", "type": "Open Multilateral"}]
    return "0", []


untc.unts_search = fake_search
mode, count, rows = untc.unts_find("Amendment to the Montreal Protocol on Substances that Deplete the Ozone Layer "
                                   "adopted by the Ninth Meeting of the Parties")
check("three attempts, in order", [m for m, _ in searches], ["phrase", "all", "phrase"])
check("found with the shortened phrase, exact title first", (mode, rows[0]["concluded"]), ("phrase-short", "17/09/1997"))

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
