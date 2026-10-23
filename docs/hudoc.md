# hudoc: where the judgment text comes from

Since hudoc 1.3.0 (2026-10-23) the text of a judgment is converted from the
HTML of HUDOC's reading view (`/app/conversion/docx/html/body`), with the
official PDF as the fallback for items that have no HTML. Up to 1.2.x the
skill downloaded the Word file (`/app/conversion/docx/`) and extracted the
text itself; that route and the `fetch --format docx` option are gone.

## Why the change

Probes on 2026-10-23 compared both routes on Soering v. UK (001-57619),
Big Brother Watch v. UK [GC] (001-210077), a legal summary (002-14597), a
decision (001-252272) and an old item (001-1).

- **The HTML is made from the same Word file**, by HUDOC's server-side Word
  converter (the endpoint path says so), so it is not an independent source;
  but that converter handles Word features the skill's own extraction did not.
- **The home-made DOCX extraction lost text.** On Big Brother Watch:
  - auto-numbered headings lost their numbers ("I. BACKGROUND" →
    "BACKGROUND", "A.", "1.", "(a)" likewise);
  - non-breaking hyphens vanished, which corrupted references:
    "paragraphs 142‑49" → "14249", "ECHR 2006‑XI" → "2006XI";
  - line breaks inside a paragraph vanished ("GovernmentMr C. Wickremasinghe",
    the judges' list run together).
- **Everything else matched word for word**, including every judgment
  paragraph number (those are typed text in both), and Soering was identical
  apart from footnote markers.
- **Smaller download:** with gzip the HTML is about half the DOCX
  (Soering 44 KB vs 89 KB, Big Brother Watch 195 KB vs 398 KB). Uncompressed
  it is larger, so `hudoc.py` now sends `Accept-Encoding: gzip`.
- **Same availability:** an item without a DOCX (e.g. a fresh French judgment,
  001-253363) also has no HTML — the endpoint answers 204 with no body — so
  nothing was lost by dropping the DOCX route. Both endpoints get the same
  Cloudflare challenges.

## Rule: as little conversion as possible

The repo-wide rule in CLAUDE.md (set 2026-10-23, from this work): take the
text out of the markup, show what the reader sees, and change nothing else.
Here, the converter never adds, normalises or replaces the Court's
characters. It writes out what the page draws (list numbers, emphasis,
superscript) and turns non-breaking spaces into plain ones (see below).
Search tolerance belongs in the search (the browser helper's `grep()`
matches a typed "-" against a non-breaking hyphen and skips emphasis
markers), not in the text.

## Quirks of the HTML, and how the converter handles them

- Some headings are `<ol start="2" type="I"><li>…</li></ol>`: the number is
  left to the browser, so the converter writes it out ("II. …").
- Word Symbol/Wingdings characters arrive as private-use code points
  (`&#xf0b7;`, `&#xf09f;` bullets; `&#xf02a;` an asterisk). The common ones
  are mapped to `•`, `▪`, `*`, …; others are left as they are.
- Footnote references are `<a href="#_ftnN">[label]</a>` and the notes are
  `<div id="_ftnN">` blocks at the end; N is Word's footnote id. The text
  uses the printed label, not the id: in old judgments that gave the
  Registry's notes a custom mark ("*"), the ids run ahead of the printed
  numbers (Soering: ids 3–13 are printed 1–11), and the 1.2.x DOCX route,
  which used the ids, gave wrong footnote numbers for citing. The label is
  used exactly as printed — Soering's two Registry notes are both `[fn *]`
  and pair with their notes in order; a missing label falls back to the id.
  In modern judgments (Big Brother Watch: 180 notes) label and id are the
  same.
- Whitespace collapses as in a browser (tabs and line breaks in the HTML
  source, runs of spaces), and paragraphs of nothing but spaces (empty
  spacers) are dropped. Every other character is kept: non-breaking hyphens
  (U+2011, as in "paragraphs 142‑49") and soft hyphens stay.

## Non-breaking spaces become plain spaces

hudoc turns non-breaking spaces (U+00A0, U+202F) into plain spaces. This
began as a hudoc exception and became the repo-wide rule (CLAUDE.md), by
the maintainer's decision (2026-10-23), for these reasons:

- **Most are layout, not text.** Big Brother Watch has 2,853. About 60 %
  imitate Word's tabs and indents: two after every paragraph number
  ("13.␣␣The applicants"), seven after a heading number, indents in old
  judgments ("␣␣␣Foreign and Commonwealth Office"). The rest are the
  Court's typography ("Rule 59 §␣1", "nos.␣58170/13", "Mr␣C. Wickremasinghe").
- **They get in the way of searching.** Claude greps the cached text in the
  sandbox, and a typed "§ 1" does not match "§␣1". Matching them needs a
  UTF-8 locale and `.` in place of the space, which is easy to get wrong.
- **Nothing a reader sees is lost.** A non-breaking space only stops a line
  break; plain text has no line wrapping to stop.

Non-breaking *hyphens* are not spaces: they are kept, and
SKILL.md tells Claude to search them with `.` in a UTF-8 locale. A
comparison of the two treatments, with excerpts, was published as an
artifact during the 1.3.0 work.

## Emphasis and superscript (1.4.0)

Italic and bold are part of a judgment's meaning (case names, Latin terms,
the operative "*Holds*", the Court's own emphasis in quotations), and an
exact citation keeps them, so the text writes them as `*italic*` and
`**bold**` (maintainer's decision, 2026-10-23; the markers follow
`shared/source-text/source_text.py`). HUDOC's Word converter never uses
`<i>` or `<b>`: it sets `font-style:italic` and `font-weight:bold` in classes
of the page's `<style>` (`.sA36B60A1 { font-family:Arial; font-style:italic }`),
on spans and on whole paragraphs (italic headings), and turns them off
inside (`font-style:normal`). The converter reads those classes and keeps a
stack of open elements, so each piece of text gets the style a browser
would give it. Raised text (`vertical-align:super`) that is not a footnote
reference becomes superscript (`1^st^`, `10⁻³`).

On Soering, Big Brother Watch and a legal summary, removing the markers
gives back the 1.3.0 text exactly (Big Brother Watch: about 1,560 marker
characters). Numbered section headings are italic or bold ("*1. Bulk
interception*"), so 52 headings in Big Brother Watch no longer pass for
the start of a judgment paragraph. `paragraph()` tests its heading pattern
on the text without markers. Underline (`text-decoration:underline`) is not
marked, and `text-transform:uppercase` is not applied: the letters stay as
typed, since the heading's style already shows that it is a heading
(maintainer's decision, 2026-10-23).

Text cached by 1.3.0 (no `judgment.format` beside it) is rebuilt from the
cached HTML on the next `fetch`, without asking HUDOC again.

## Python and browser converters

`html_to_text` in `hudoc.py` and `htmlToText` in `scripts/browser/hudoc.js`
walk the markup with the same token regex (not a DOM parser) so their output
is identical; `tests/hudoc/test_html.py` and `tests/hudoc/test_browser.js`
check both against one fixture, and the five documents above were compared
byte for byte when the converter was written.

Text cached by 1.2.x (recognised by the `judgment.docx` beside it) is
rebuilt from the HTML on the next `fetch`. A Cloudflare challenge on the
HTML request is reported as such and never triggers the PDF fallback: the
HTML exists, and the PDF's text is weaker and would stay cached.
