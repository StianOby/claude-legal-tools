#!/usr/bin/env python3
"""Tests for quote_check.py: quotations compared with saved passages.

Run with `python tests/kildesjekk/test_quote_check.py`.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "kildesjekk" / "skills" / "kildesjekk" / "scripts"))

import quote_check as qc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


def ev(passage, emphasis=False, outcome="found"):
    return {"outcome": outcome, "passage": passage, "emphasis_known": emphasis}


PASSAGE = ("The Court considers that the first and foremost restriction imposed "
           "by international law upon a State is that it may not exercise its "
           "power in any form in the territory of another State. In this sense "
           "jurisdiction is certainly territorial; it cannot be exercised by a "
           "State outside its territory except by virtue of a permissive rule.")

print("wording")
r = qc.check_row('"jurisdiction is certainly territorial"', ev(PASSAGE))
check("a verbatim quotation is exact", r["verdict"], "exact")
r = qc.check_row("«jurisdiction is\n   certainly" + qc.NBSP + "territorial»", ev(PASSAGE))
check("line breaks and non-breaking spaces are layout", r["verdict"], "exact")
r = qc.check_row('"juris' + qc.SOFT_HYPHEN + 'diction is certainly territorial"', ev(PASSAGE))
check("a soft hyphen is ignored", r["verdict"], "exact")

r = qc.check_row('"jurisdiction is clearly territorial"', ev(PASSAGE))
check("a changed word is a difference", r["verdict"], "differs")
d = r["parts"][0]["differences"]
check("and it is named", [(x["quotation"], x["source"]) for x in d],
      [("clearly", "certainly")])
check("with the words before it", d[0]["after"].endswith("jurisdiction is"), True)

r = qc.check_row('"jurisdiction is territorial"', ev(PASSAGE))
check("a dropped word is a difference", r["verdict"], "differs")
check("shown as a word only the source has",
      [(x["quotation"], x["source"]) for x in r["parts"][0]["differences"]],
      [("", "certainly")])

r = qc.check_row('"Jurisdiction is certainly territorial"', ev(PASSAGE))
check("a changed capital is a difference", r["verdict"], "differs")

r = qc.check_row('"the principle of sovereign equality of all members"', ev(PASSAGE))
check("a quotation that is not there", r["verdict"], "not_in_passage")

print("word boundaries")
r = qc.check_row("«rimelig»", ev("Avtalen var åpenbart urimelig etter loven."))
check("a match inside a longer word is not exact", r["verdict"], "differs")
check("and the longer word is shown",
      [(x["quotation"], x["source"]) for x in r["parts"][0]["differences"]],
      [("rimelig", "urimelig")])
r = qc.check_row('"permissive rule"', ev(PASSAGE))
check("a quotation may stop before the full stop", r["verdict"], "exact")

print("ellipses and insertions")
r = qc.check_row('"it may not exercise its power […] in the territory of another State"',
                 ev(PASSAGE))
check("an ellipsis splits the quotation", r["verdict"], "exact")
check("and is counted", r["parts"][0]["omissions"], 1)
r = qc.check_row('"jurisdiction is certainly territorial ... it may not exercise its power"',
                 ev(PASSAGE))
check("parts in the wrong order are a difference", r["verdict"], "differs")
r = qc.check_row('"[J]urisdiction is certainly territorial"', ev(PASSAGE))
check("a bracketed capital is a convention", r["verdict"], "exact")
check("and the insertion is listed", r["parts"][0]["insertions"], ["J"])
r = qc.check_row('"it [the State] may not exercise its power"', ev(PASSAGE))
check("a bracketed clarification", (r["verdict"], r["parts"][0]["insertions"]),
      ("exact", ["the State"]))
r = qc.check_row('"it may not exercise its power […] in the lands of another State"',
                 ev(PASSAGE))
check("a difference after an ellipsis is still found", r["verdict"], "differs")

print("quotation marks")
src = "The Court held that the ‘effective control’ test applied."
r = qc.check_row('"the "effective control" test applied"', ev(src))
check("other marks around a quote in the quote", r["verdict"], "marks_only")
r = qc.check_row("“the ‘effective control’ test applied”", ev(src))
check("the same marks are exact", r["verdict"], "exact")
r = qc.check_row("«jurisdiction is certainly territorial» «permissive rule»", ev(PASSAGE))
check("two quotations in one cell", (r["verdict"], len(r["parts"])), ("exact", 2))
r = qc.check_row("«jurisdiction is certainly territorial» «permissive norm»", ev(PASSAGE))
check("the worst of them decides", r["verdict"], "differs")

print("emphasis")
marked = "The Court held that it was *certainly* territorial and **not** universal."
r = qc.check_row('"it was *certainly* territorial"', ev(marked, emphasis=True))
check("the same italics", (r["verdict"], r["emphasis"]), ("exact", "same"))
r = qc.check_row('"it was certainly territorial"', ev(marked, emphasis=True))
check("italics the quotation lacks", (r["verdict"], r["emphasis"]), ("exact", "differs"))
check("the source is shown with its markers",
      r["parts"][0]["source_text"], "it was *certainly* territorial")
r = qc.check_row('"it was certainly *territorial*"', ev(marked, emphasis=True))
check("italics on another word", r["emphasis"], "differs")
r = qc.check_row('"**not** universal"', ev(marked, emphasis=True))
check("bold", (r["verdict"], r["emphasis"]), ("exact", "same"))
whole = "*The whole sentence is in italics here.*"
r = qc.check_row('"*sentence is in italics*"', ev(whole, emphasis=True))
check("part of a longer italic stretch", (r["verdict"], r["emphasis"]), ("exact", "same"))
r = qc.check_row('"it was *certainly* territorial"',
                 ev("it was certainly territorial", emphasis=False))
check("text without emphasis: wording only", (r["verdict"], r["emphasis"]),
      ("exact", "not_compared"))

print("rows without a comparison")
check("no quotation", qc.check_row("", ev(PASSAGE))["verdict"], "no_quotation")
check("no passage", qc.check_row('"x"', ev("", outcome="not_here"))["verdict"], "no_passage")

print("evidence files")
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    good = tmp / qc.evidence_name("text p. 22a")
    good.write_text(
        "key: text p. 22a\noutcome: found\nsource: Zotero ABCD1234\nroute: zoteus\n"
        "locator: p. 19\npinpoint_matches: yes\nemphasis_known: no\ntools_tried:\n"
        "note: scanned book,\n  OCR text\n--- passage ---\n" + PASSAGE + "\n\nSecond paragraph.\n",
        encoding="utf-8")
    record, problems = qc.read_evidence(good, "text p. 22a")
    check("a well-formed file has no problems", problems, [])
    check("the passage keeps its paragraphs", record["passage"].endswith("\n\nSecond paragraph."), True)
    check("a field may run over two lines", record["note"], "scanned book, OCR text")
    check("names differ for keys that look alike",
          qc.evidence_name("2.1a") != qc.evidence_name("2 1a"), True)

    _, problems = qc.read_evidence(good, "text p. 22b")
    check("the wrong key is caught", any("expected" in p for p in problems), True)
    _, problems = qc.read_evidence(tmp / "missing.txt", "1")
    check("a missing file is caught", len(problems), 1)
    empty = tmp / "empty.txt"
    empty.write_text("key: 3\noutcome: found\nsource: Zotero X\nlocator: p. 1\n--- passage ---\n\n",
                     encoding="utf-8")
    _, problems = qc.read_evidence(empty, "3")
    check("found with an empty passage is caught", any("empty" in p for p in problems), True)
    nothere = tmp / "nothere.txt"
    nothere.write_text("key: 4\noutcome: not_here\ntools_tried: zotero_search_items by author and title\n",
                       encoding="utf-8")
    _, problems = qc.read_evidence(nothere, "4")
    check("not_here needs no passage", problems, [])
    lazy = tmp / "lazy.txt"
    lazy.write_text("key: 5\noutcome: unavailable\n", encoding="utf-8")
    _, problems = qc.read_evidence(lazy, "5")
    check("unavailable must say what was tried", any("tools_tried" in p for p in problems), True)

    print("the CLI")
    batch = tmp / "b.json"
    quotes = tmp / "quotes" / "b.json"
    batch.write_text(json.dumps({"batch": "b", "quotes_file": str(quotes), "rows": [
        {"key": "text p. 22a", "quoted": '"jurisdiction is clearly territorial"',
         "evidence_file": str(good)},
        {"key": "4", "quoted": "", "evidence_file": str(nothere)},
    ]}), encoding="utf-8")
    check("exit 0 when all evidence is usable", qc.main([str(batch)]), 0)
    out = json.loads(quotes.read_text(encoding="utf-8"))
    check("the quotes file has a row per key",
          [(r["key"], r["verdict"]) for r in out["rows"]],
          [("text p. 22a", "differs"), ("4", "no_quotation")])
    batch.write_text(json.dumps({"batch": "b", "quotes_file": str(quotes), "rows": [
        {"key": "9", "quoted": "", "evidence_file": str(tmp / "none.txt")}]}), encoding="utf-8")
    check("exit 1 when evidence is missing", qc.main([str(batch)]), 1)

print()
if failures:
    print("%d failing check(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all checks passed")
