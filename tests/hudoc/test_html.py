#!/usr/bin/env python3
"""HTML-to-text conversion in hudoc.py, on the same synthetic fixture that
tests/test_browser.js runs through the in-page helper — the two must produce
the same text, so a paragraph number or footnote marker read in the browser
is the one the CLI cache has.

No network. Run with `python tests/hudoc/test_html.py`.
"""

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "plugins" / "hudoc" / "skills" / "hudoc"
sys.path.insert(0, str(SKILL / "scripts"))

import hudoc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


# Same string as MINI_TEXT in tests/test_browser.js.
MINI_TEXT = (
    "CASE OF TEST v. NORWAY\n\n"
    "1. The applicant & his wife complained [fn *].\n\n"
    "(a) a sub-paragraph that belongs to paragraph 1 [fn 1]\n\n"
    "II. ALLEGED VIOLATION OF ARTICLE 8\n\n"
    "2. The Court reiterates “margin of appreciation” [fn *], see paragraphs 142\N{NON-BREAKING HYPHEN}49 and ECHR 2006\N{NON-BREAKING HYPHEN}XI.\n\n"
    "• A bulleted point\n\n"
    "a. first lettered point\n\n"
    "b. second lettered point\n\n"
    "Mr A. Judge, President,\nMr B. Judge, judges,\n\n"
    "Application no.\n\n"
    "Applicant\n\n"
    "1/01\n\n"
    "Person A\n\n"
    "FOR THESE REASONS, THE COURT\n\n"
    "1. Holds, unanimously, that there has been a violation of Article 8;\n\n"
    "FOOTNOTES\n\n"
    "[fn *] See Smith v. Norway, no. 1/01. Second paragraph of the note.\n\n"
    "[fn *] Case-law cited.\n\n"
    "[fn 1] The first numbered note.\n"
)

print("HTML conversion")
html = (HERE / "fixtures" / "mini.html").read_text(encoding="utf-8")
check("mini.html", hudoc.html_to_text(html), MINI_TEXT)
check("CRLF in the markup is whitespace too",
      hudoc.html_to_text(html.replace("his\nwife", "his\r\nwife")), MINI_TEXT)
check("list labels", [hudoc._list_label(n, k) for n, k in ((4, "I"), (14, "i"), (2, "A"), (27, "a"), (3, "1"))],
      ["IV", "xiv", "B", "aa", "3"])
check("unknown entity left as is", hudoc._html_unescape("&copy; &amp; &#65;"), "&copy; & A")

check("PDF link for the user (same as pdfUrl in hudoc.js)", hudoc.pdf_url("001-4"),
      "https://hudoc.echr.coe.int/app/conversion/pdf/?library=ECHR&id=001-4&filename=001-4.pdf")

print("fetch_text() routes")
PDF = b"%PDF-1.4 fake"


def route(answers, before=None):
    """Run fetch_text() against canned answers {endpoint: bytes | Exception}
    in a fresh cache; return (outcome, endpoints asked, files left)."""
    with tempfile.TemporaryDirectory() as tmp:
        hudoc.ITEMS_DIR = Path(tmp)
        d = hudoc._item_dir("001-1")
        for name, content in (before or {}).items():
            (d / name).write_text(content, encoding="utf-8")
        asked = []

        def download(url):
            key = "html" if url.startswith(hudoc.HTML_URL) else "pdf"
            asked.append(key)
            a = answers[key]
            if isinstance(a, Exception):
                raise a
            return a

        hudoc._download = download
        hudoc.pdf_to_text = lambda p: "PDF TEXT\n"
        try:
            out = hudoc.fetch_text("001-1").read_text(encoding="utf-8")
        except hudoc.ChallengeError:
            out = "challenge"
        except RuntimeError:
            out = "error"
        return out, asked, sorted(p.name for p in d.iterdir())


check("HTML is the text source",
      route({"html": html.encode("utf-8"), "pdf": PDF}), (MINI_TEXT, ["html"], ["judgment.html", "judgment.txt"]))
check("no HTML (204, empty): the PDF",
      route({"html": b"", "pdf": PDF}), ("PDF TEXT\n", ["html", "pdf"], ["judgment.pdf", "judgment.txt"]))
check("a challenge is never a reason to use the PDF",
      route({"html": hudoc.ChallengeError("cf"), "pdf": PDF}), ("challenge", ["html"], []))
check("neither: an error",
      route({"html": b"", "pdf": b""}), ("error", ["html", "pdf"], []))
check("text cached by 1.2.x (DOCX beside it) is rebuilt",
      route({"html": html.encode("utf-8"), "pdf": PDF}, {"judgment.docx": "PK", "judgment.txt": "old"}),
      (MINI_TEXT, ["html"], ["judgment.html", "judgment.txt"]))
check("cached text is reused",
      route({"html": html.encode("utf-8"), "pdf": PDF}, {"judgment.html": "<p>x</p>", "judgment.txt": "cached"}),
      ("cached", [], ["judgment.html", "judgment.txt"]))

if failures:
    print("\n%d failure(s)" % len(failures))
    sys.exit(1)
print("\nall passed")
