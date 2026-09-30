#!/usr/bin/env python3
"""Offline tests for nb_search.py: the [NEWEST] flag only appears when the hits
span more than one year. Run: python tests/test_nb_search.py
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
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
