# hudoc skill

Pure-Python skill that lets Claude look up and download European Court of
Human Rights case law from the HUDOC database — full text, the official PDF,
structured metadata, and citation chains. Standard library only; `pypdf`
(or poppler's `pdftotext`) is used only for the rare items that exist
solely as PDF.

See `SKILL.md` for the full workflow guide. Quick test:

```bash
python3 scripts/hudoc.py fetch "Soering v. UK" --format text
python3 scripts/hudoc.py search '(article:"8") AND (respondent:"NOR") AND (doctypebranch:GRANDCHAMBER)' -n 5
python3 scripts/hudoc.py citations "Big Brother Watch v. UK"
```

## Layout

```
hudoc/
├── SKILL.md
├── README.md
├── scripts/
│   ├── hudoc.py            # single self-contained CLI; stdlib only
│   └── browser/
│       └── hudoc.js        # in-page fallback for the Cowork built-in browser
└── references/
    └── query-fields.md     # HUDOC Lucene query syntax + field reference
```

Offline tests live in the repository at `tests/hudoc/`, not in the plugin (they do not ship to users): `python tests/hudoc/test_html.py`, `python tests/hudoc/test_references.py`, `node tests/hudoc/test_browser.js`.

## Where the text comes from

The text of a judgment is taken from the HTML that HUDOC's own reading view
shows (`hudoc.echr.coe.int/eng?i=<itemid>`), converted to plain text: one
paragraph per block, judgment paragraph numbers ("88.") and heading numbers
("II.", "A.") kept, footnotes marked `[fn N]` in the body and listed at the
end. Items that HUDOC holds only as a PDF fall back to text extracted from
the PDF.

HUDOC builds that HTML on its own server from the Court's Word file, with a
full Word converter, so numbering, line breaks and non-breaking hyphens
("paragraphs 142‑49", "ECHR 2006‑XI") come out as the Court wrote them.

HUDOC sits behind Cloudflare, which often answers the CLI with a "Just a
moment…" challenge — the document download above all — and which requests it
challenges changes from minute to minute. In Cowork the skill then switches to
the built-in browser: `scripts/browser/hudoc.js` is pasted into a HUDOC tab and
does the same lookups from there, converting the same HTML to exactly the text
the CLI would have produced (the tests check the two against each other).

Downloads are cached outside the skill folder, under `$HUDOC_CACHE_DIR` if
set and otherwise `~/.cache/hudoc/items/<itemid>/`.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `hudoc` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `hudoc.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

Then in Cowork: describe the task ("find Soering v UK")
and the description in `SKILL.md` will trigger it.

## Acknowledgement

The metadata field set and the document type codes were first taken from
the maastrichtlawtech
[`echr-extractor`](https://github.com/maastrichtlawtech/echr-extractor)
library. This skill does something different (interactive lookup and
filtered search, not corpus extraction) and is standalone (no third-party
Python dependencies).

## API notes

HUDOC has no official API. The skill uses three undocumented but stable
endpoints:

- `GET /app/query/results` — JSON metadata + Lucene-style search.
  **Requires** the `X-Requested-With: XMLHttpRequest` header — without it
  the CDN serves a generic 404.
- `GET /app/conversion/docx/html/body?library=ECHR&id=<itemid>` — the HTML
  of the reading view, the text source. Answers 204 with no body when the
  item has no HTML (PDF-only items). No auth.
- `GET /app/conversion/pdf/?library=ECHR&id=<itemid>` — the official PDF.
  No auth.

If an endpoint stops working, smoke-test with curl:

```bash
curl -H "X-Requested-With: XMLHttpRequest" \
  "https://hudoc.echr.coe.int/app/query/results?query=(contentsitename=ECHR)+AND+(itemid:%22001-57619%22)&select=itemid,docname,appno&start=0&length=1"
```

A working response is a `{"resultcount":1,"results":[...]}` JSON blob.
