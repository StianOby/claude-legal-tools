#!/usr/bin/env python3
"""Offline tests for scripts/traktater.py (no network): article-number
parsing, article lookup on a synthetic document, cache keys and --no-cache
placement. Run: python tests/test_traktater.py
"""

import os
import sys
import tempfile

os.environ["NORGES_TRAKTATER_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import traktater as t  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("article keys")
for raw, want in [
    ("2", ["2", "ii"]),
    ("II", ["ii", "2"]),
    ("IV", ["iv", "4"]),
    ("Artikkel II", ["ii", "2"]),
    ("art. 33", ["33", "xxxiii"]),
    ("Art 33", ["33", "xxxiii"]),
    ("Article 2", ["2", "ii"]),
    ("article II.", ["ii", "2"]),
    ("1 A", ["1a", "1", "i"]),
    ("Article 1 A", ["1a", "1", "i"]),
    ("4a", ["4a", "4", "iv"]),
    ("1(b)", ["1b", "1", "i"]),
    ("8 bis", ["8bis", "8", "viii"]),
    ("II A", ["iia", "ii", "2"]),
    ("1_1", ["1_1"]),
    ("", []),
]:
    check(repr(raw), t._normalize_article_key(raw), want)

DOC = """<html><div id="documentBody">
<a name="ARTIKKEL_1"></a><div data-id="ARTIKKEL_1"><h2>Artikkel 1</h2>
<p>A. I denne konvensjonen betyr «flyktning» enhver person som har rett nok tekst her.</p>
<p>B. Andre ledd av artikkel 1 med mer tekst for å passere grensen.</p></div>
<a name="ARTIKKEL_2"></a><div data-id="ARTIKKEL_2"><h2>Artikkel 2</h2><p>Andre artikkel.</p></div>
<a name="ARTIKKEL_10"></a><div data-id="ARTIKKEL_10"><h2>Artikkel 10</h2><p>Tiende.</p></div>
<a name="ARTIKKEL_1_1"></a><div data-id="ARTIKKEL_1_1"><h2>Artikkel 1</h2><p>Protokollens første artikkel.</p></div>
</div><ul class="pager"></ul></html>"""
t.fetch_doc_html = lambda tid, no_cache=False: DOC

print("article lookup")
r = t.get_article("1951-07-28-1", "Article 2")
check("English prefix finds article 2", (r["available"], "Andre artikkel" in r["body"]), (True, True))
r = t.get_article("1951-07-28-1", "1 A")
check("1 A falls back to article 1", (r["available"], "flyktning" in r["body"], "Protokollens" in r["body"]),
      (True, True, False))
check("fallback carries a note", "hele artikkel 1" in r.get("note", ""), True)
r = t.get_article("1951-07-28-1", "2")
check("plain lookup has no note", "note" in r, False)
r = t.get_article("1951-07-28-1", "1_1")
check("suffixed key finds the protocol article", "Protokollens" in r["body"], True)
r = t.get_article("1951-07-28-1", "99")
check("available articles in document order", r["available_articles"], ["1", "2", "10", "1_1"])

print("cache keys")
base = "https://lovdata.no/register/traktater?search=" + "x" * 300
k1 = t._cache_key(base + "&offset=20").name
k2 = t._cache_key(base + "&offset=40").name
check("long URLs that share a prefix get different files", k1 != k2, True)
check("long key stays short", len(k1) <= 210, True)
short = "https://lovdata.no/dokument/TRAKTAT/traktat/1948-12-09-1"
check("short URL key unchanged", t._cache_key(short).name, "https_lovdata_no_dokument_TRAKTAT_traktat_1948_12_09_1.html")

print("--no-cache placement")
seen = {}
t.cmd_meta = lambda args: seen.update(no_cache=args.no_cache)
for argv, want in [
    (["meta", "1948-12-09-1"], False),
    (["--no-cache", "meta", "1948-12-09-1"], True),
    (["meta", "1948-12-09-1", "--no-cache"], True),
    (["meta", "--no-cache", "1948-12-09-1"], True),
]:
    seen.clear()
    # main() binds cmd_meta via set_defaults at parse time, so patch first.
    t.main(argv)
    check(" ".join(argv), seen.get("no_cache"), want)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
