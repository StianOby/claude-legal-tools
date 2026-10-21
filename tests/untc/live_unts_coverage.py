#!/usr/bin/env python3
"""Live check (network, not run by CI): search MTDSG titles in UNTS Online
with the same function `lookup` uses, and report how many are found with the
exact title ranked first or with a matching conclusion date ("found"), or
only as a record that contains the title, such as "Amendments to the United
Nations Regulation No. 23 …" ("related": regulations, annexes and some
amendments are registered under their parent agreement).

    python tests/untc/live_unts_coverage.py            # a sample of 40 titles
    python tests/untc/live_unts_coverage.py --all      # all ~670 (about 40 min)

Baseline 2026-10-21, all 670: 667 found or related (the exact title first,
or for UN vehicle regulations a related record under the 1958 Agreement).
Not found: III-2-5 and III-2-7A (annexes registered under the parent
convention, A-521) and XVIII-10-g (2019 Rome Statute amendment, not yet
registered). A drop below that means the site's search or markup changed.
"""

import json
import random
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc"
sys.path.insert(0, str(SKILL / "scripts"))
import untc  # noqa: E402

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
KNOWN_MISSES = {"III-2-5", "III-2-7A", "XVIII-10-g"}


def concluded(place_date):
    import re
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", place_date or "")
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return "%02d/%02d/%s" % (int(m.group(1)), MONTHS.index(m.group(2).lower()) + 1, m.group(3))


def main():
    treaties = json.loads((SKILL / "cache" / "index.json").read_text(encoding="utf-8"))["treaties"]
    if "--all" not in sys.argv:
        random.seed(1)
        treaties = random.sample(treaties, 40)
    found = related = missed = 0
    for e in treaties:
        mode, count, rows = untc.unts_find(e["title"], limit=500)
        key = untc._title_key(untc.unts_query_text(e["title"]))
        date = concluded(e.get("place_date"))
        ok = bool(rows) and (untc._title_key(rows[0]["title"]) in (key, untc._title_key(e["title"]))
                             or any(r["concluded"] == date for r in rows))
        if ok:
            found += 1
        elif rows and key in untc._title_key(rows[0]["title"]):
            related += 1
            print("  related %s: %s -> %s %s" % (e["ref"], e["title"][:60], rows[0]["reg"], rows[0]["title"][:60]))
        else:
            missed += 1
            print("  %s %s: %s (%s, %s records)" % ("known" if e["ref"] in KNOWN_MISSES else "MISS",
                                                    e["ref"], e["title"][:80], mode, count))
        time.sleep(0.5)
    print("%d found, %d related, %d not found, of %d" % (found, related, missed, found + related + missed))
    unexpected = missed - sum(1 for e in treaties if e["ref"] in KNOWN_MISSES)
    sys.exit(1 if unexpected > 0 else 0)


if __name__ == "__main__":
    main()
