# untc — UN Treaty Collection skill

A self-contained Claude skill for working with treaties published by
the UN Treaty Collection ([treaties.un.org](https://treaties.un.org)).
The skill knows the URL scheme of UNTC's static PDF publications and
fetches them directly — no Selenium, no JavaScript, no scraping of the
ASP.NET search frontend.

## What it can do

- Resolve a treaty name or acronym (e.g. "ICCPR", "Vienna Convention",
  "OPCAT") to its MTDSG reference (e.g. `IV-4`, `XXIII-1`, `IV-9-b`).
- Download the **MTDSG status document** for a multilateral treaty
  deposited with the Secretary-General — the consolidated PDF with the
  participant table (signatures, ratifications, accessions),
  state-by-state reservations, declarations and objections, and the
  cross-reference into the UN Treaty Series.
- Download the **UNTS treaty text** for any UN-registered treaty: by
  MTDSG ref (volume and registration number are read from the status
  doc), by `--vol`/`--reg`, or by `--vol`/`--page` from an ordinary
  citation such as *729 UNTS 161*. When UNTC has no per-treaty file
  (common for recent volumes) the text is sliced out of the full volume
  PDF instead.
- List the **table of contents of any UNTS volume** — the route to the
  thousands of bilateral and multilateral treaties that are registered
  with the UN but not deposited with the Secretary-General (and so have
  no MTDSG entry).
- Extract searchable text from every PDF (pypdf, with `pdftotext` as
  fallback) and cache everything so repeat queries are instant.

## Layout

```
untc/
├── SKILL.md             # the skill manifest Claude reads
├── README.md            # you are here
├── requirements.txt     # pypdf
├── cache/
│   └── index.json       # bundled snapshot of the MTDSG chapter index (670 treaties)
├── evals/
└── scripts/
    └── untc.py          # the CLI
```

Nothing is written inside the skill folder. All downloads and extracted
text go to `~/.cache/untc/` (override with `$UNTC_CACHE_DIR`):

```
~/.cache/untc/index.json                          # title -> ref index (seeded from cache/index.json)
~/.cache/untc/treaties/<chapter>/<ref>/meta.json  # parsed metadata (English)
~/.cache/untc/treaties/<chapter>/<ref>/status.{en,fr}.{pdf,txt}
~/.cache/untc/treaties/<chapter>/<ref>/text.{en,fr,other}.{pdf,txt}
~/.cache/untc/unts/v<vol>-I-<reg>/text.*.{pdf,txt} # texts fetched by --vol/--reg
~/.cache/untc/unts/volumes/v<vol>.pdf             # full volume PDFs (+ .pages.json text)
```

## Requirements

- **Python 3.8+**, standard library only for HTTP.
- **`pypdf`** (`pip install pypdf`) is the preferred text extractor: on
  the MTDSG status documents it produces one clean row per participant
  and readable reservation text. `pdftotext` (poppler-utils) is used
  only as a fallback; in its layout mode the dot leaders of the
  participant table interleave with the dates, so prefer pypdf.

## Quickstart

```bash
# resolve a treaty by name (uses the bundled index; no crawl)
python3 scripts/untc.py lookup "vienna convention on the law of treaties"

# get everything for a treaty (status doc + text), in one go
python3 scripts/untc.py fetch ICCPR

# or directly by MTDSG reference (optional protocols: IV-11-b; chapter XI: XI-B-16)
python3 scripts/untc.py fetch XXIII-1
python3 scripts/untc.py status IV-9-b

# only the status doc (parties + reservations), in French
python3 scripts/untc.py status IV-4 --lang fr

# treaty text by UNTS volume + registration number, or by citation page
python3 scripts/untc.py text --vol 999 --reg 14668
python3 scripts/untc.py text --vol 729 --page 161        # "729 UNTS 161" -> NPT

# what is in a UNTS volume?
python3 scripts/untc.py volume 729 --search non-proliferation

# refresh the MTDSG index (about 35 page fetches, 1-2 minutes)
python3 scripts/untc.py index --refresh
```

After `fetch ICCPR` you'll have:

```
~/.cache/untc/treaties/IV/IV-4/meta.json          # title, place/date, vol, regnum, parties...
~/.cache/untc/treaties/IV/IV-4/status.en.pdf      # 140-page MTDSG status doc
~/.cache/untc/treaties/IV/IV-4/status.en.txt      # extracted text (grep-able)
~/.cache/untc/treaties/IV/IV-4/text.en.pdf        # UNTS treaty text PDF
~/.cache/untc/treaties/IV/IV-4/text.en.txt        # extracted text
```

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `untc` and click
  **Install**. Click **Update** on the marketplace later to get new versions.
- *Claude Code:* `/plugin marketplace add StianOby/claude-legal-tools`, then
  `/plugin install untc@claude-legal-tools`.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `untc.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code, for development):**

- macOS / Linux:
  `ln -s /path/to/untc ~/.claude/skills/untc`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\untc" "C:\path\to\untc"`

Then in Claude Code or Cowork: describe the task ("get me the ICCPR text")
and the description in `SKILL.md` will trigger it.

## URL schemes (reference)

| Document | URL pattern |
|---|---|
| MTDSG status | `https://treaties.un.org/doc/Publication/MTDSG/Volume {I,II}/Chapter {ROMAN}/{REF}.{en,fr}.pdf` |
| UNTS treaty text | `https://treaties.un.org/doc/Publication/UNTS/Volume {N}/volume-{N}-{I,II}-{regNum}-{English,French,Other}.pdf` |
| UNTS full volume | `https://treaties.un.org/doc/Publication/UNTS/Volume {N}/v{N}.pdf` |
| Treaty details page | `https://treaties.un.org/Pages/ViewDetails.aspx?src=TREATY&mtdsg_no={REF}&chapter={n}&clang=_en` |
| Chapter index (used to build name→ref index) | `https://treaties.un.org/Pages/Treaties.aspx?id={n}&subid={A..E}&clang=_en` |

`{I,II}` for MTDSG volume: chapters I–XII live in Vol I, XIII–XXIX in
Vol II (chapter XI, including its sub-chapters, is in Vol I). `{I,II}`
in the UNTS URL is the registration *series*: I for treaties registered
under Article 102, II for treaties filed and recorded.

`{REF}` is written exactly as UNTC writes it: `IV-4`, `IV-11-b`
(optional protocol / amendment), `XI-B-16` (chapter XI sub-chapter),
`XI-B-16-1` (UN vehicle Regulations annexed to the 1958 Agreement).

A missing document is served as an HTML page with HTTP 200; the CLI
checks for a real PDF and reports "no MTDSG status document at …".

## Known limits

- MTDSG status documents exist in English and French only. Per-treaty
  UNTS files exist as English, French and "Other" (the remaining
  authentic texts in one file); many recent volumes have no per-treaty
  files at all, and the newest volumes (e.g. vol. 3370 for the TPNW)
  are not yet published as PDFs — the CLI then points to the treaty's
  details page, where the certified true copy is linked.
- The volume table of contents is parsed from the volume PDF's own
  contents pages (OCR for older volumes); a page number may occasionally
  be missing, in which case `text --vol N --reg M` still works.
- Only the English chapter index is harvested for name lookup; the
  `lookup` fuzzy match is title-based, so use `index --refresh` if a
  treaty adopted after the snapshot date is missing.
- Structured extraction of the parties table and reservations into JSON
  is not implemented; the extracted status text is one row per state and
  greppable.

## Acknowledgements

Inspiration from [zhiyzuo/UNTC-scraper](https://github.com/zhiyzuo/UNTC-scraper)
for the realisation that the search frontend is JS-driven (we sidestep
that by going directly to the published PDFs).
