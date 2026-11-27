#!/usr/bin/env python3
"""Offline tests for nb_search.py: the [NEWEST] flag only appears when the hits
span more than one year. Run: python tests/nbno/test_nb_search.py
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
import nb_search as ns  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def item(i, year):
    return {"id": f"id{i}", "metadata": {"title": f"T{i}", "originInfo": {"issued": year}},
            "accessInfo": {}}


def run(years, extra=()):
    ns.search = lambda *a, **k: {"page": {"totalElements": len(years)},
                                 "_embedded": {"items": [item(i, y) for i, y in enumerate(years)]}}
    out = io.StringIO()
    with redirect_stdout(out):
        ns.main(["x", *extra])
    return out.getvalue()


print("nb_search filters")
check("one year", ns.year_filter("1867"), "1867")
check("a range", ns.year_filter("1850-1899"), "[1850 TO 1899]")
for bad in ("18x", "1850-", "1850-99"):
    try:
        ns.year_filter(bad)
        check(f"rejects {bad!r}", False, True)
    except ValueError:
        check(f"rejects {bad!r}", True, True)
urls = []
ns._get = lambda url, timeout=30.0: urls.append(url) or {}
real_search = ns.search


def filters(**kw):
    urls.clear()
    real_search("x", **kw)
    from urllib.parse import parse_qs, urlparse
    return [f for f in parse_qs(urlparse(urls[0]).query).get("filter", []) if not f.startswith("mediatype")]


check("no filter by default", filters(), [])
check("year range", filters(year="1850-1899"), ["year:[1850 TO 1899]"])
check("--access everywhere: public and digitised",
      filters(access="everywhere"), ["contentClasses:public", "digital:Ja"])
check("--access norway", filters(access="norway"), ["contentClasses:bokhylla", "digital:Ja"])
check("--access nb", filters(access="nb"), ["contentClasses:restricted", "digital:Ja"])
check("--digitised", filters(digitised=True), ["digital:Ja"])

print("nb_search: an undigitised hit has no access class")
ns.search = lambda *a, **k: {"page": {"totalElements": 1}, "_embedded": {"items": [
    {"metadata": {"title": "T"}, "accessInfo": {"accessAllowedFrom": "EVERYWHERE",
                                               "viewability": "ALL", "isDigital": False}}]}}
out = io.StringIO()
with redirect_stdout(out):
    ns.main(["x"])
check("says not digitised", "access: none - not digitised" in out.getvalue(), True)
check("does not say EVERYWHERE for it", "access: EVERYWHERE  viewability" in out.getvalue(), False)

print("nb_search newest flag")
check("same year: no flag (text)", "NEWEST" in run(["2001", "2001", "2001"], ["--year", "2001"]), False)
check("same year: no flag (json)",
      [h["newest"] for h in json.loads(run(["2001", "2001"], ["--json"]))["hits"]], [False, False])
check("mixed years: flag on the newest only (text)", run(["1990", "2005", "1998"]).count("NEWEST"), 1)
check("mixed years: json",
      [(h["year"], h["newest"]) for h in json.loads(run(["1990", "2005", "2005"], ["--json"]))["hits"]],
      [("2005", True), ("2005", True), ("1990", False)])
check("single hit: no flag", "NEWEST" in run(["2005"]), False)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
