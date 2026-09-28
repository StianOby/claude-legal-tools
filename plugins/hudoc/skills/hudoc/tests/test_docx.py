#!/usr/bin/env python3
"""DOCX-to-text conversion in hudoc.py, on the same synthetic fixtures that
tests/test_browser.js runs through the in-page helper — the two must produce
the same text, so a paragraph number or footnote marker read in the browser
is the one the CLI cache has.

No network. Run with `python plugins/hudoc/skills/hudoc/tests/test_docx.py`.
"""

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


MINI_TEXT = (
    "CASE OF TEST v. NORWAY\n\n"
    "1. The applicant & his wife complained [fn 1].\n\n"
    "(a) a sub-paragraph that belongs to paragraph 1\n\n"
    "II.  ALLEGED VIOLATION OF ARTICLE 8\n\n"
    "2. The Court reiterates “margin of appreciation” [fn 2].\n\n"
    "A text box: inside\n\n"
    "FOR THESE REASONS, THE COURT\n\n"
    "1. Holds, unanimously, that there has been a violation of Article 8;\n\n"
    "FOOTNOTES\n\n"
    "[fn 1] See Smith v. Norway, no. 1/01. Second paragraph of the note.\n\n"
    "[fn 2] Case-law cited.\n"
)

print("DOCX conversion")
check("deflated zip", hudoc.docx_to_text(HERE / "fixtures" / "mini.docx"), MINI_TEXT)
check("stored zip", hudoc.docx_to_text(HERE / "fixtures" / "mini-stored.docx"), MINI_TEXT)
# A paragraph inside a text box used to be printed twice: once as part of
# its outer paragraph and once on its own.
check("text box text appears once",
      hudoc.docx_to_text(HERE / "fixtures" / "mini.docx").count("inside"), 1)

if failures:
    print("\n%d failure(s)" % len(failures))
    sys.exit(1)
print("\nall passed")
