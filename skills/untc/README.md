# untc — UN Treaty Collection skill

A self-contained Claude skill for working with treaties published by
the UN Treaty Collection ([treaties.un.org](https://treaties.un.org)).
The skill knows the URL scheme of UNTC's static PDF publications and
fetches them directly — no Selenium, no JavaScript, no scraping of the
ASP.NET search frontend.

## What it can do

- Resolve a treaty name (e.g. "ICCPR", "Vienna Convention") to its
  MTDSG reference (e.g. `IV-4`, `XXIII-1`).
- Download the **MTDSG status document** for a multilateral treaty —
  the consolidated PDF with the participant table (signatures,
  ratifications, accessions), state-by-state reservations,
  declarations and objections, and the cross-reference into the UN
  Treaty Series.
- Download the **UNTS treaty text** for any UN-registered treaty,
  given the chapter-section ref (it auto-derives volume + registration
  number from the status doc) or directly via `--vol`/`--reg`.
- Extract searchable text from every PDF (via `pdftotext` or pypdf).
- Cache everything under `cache/` so repeat queries are instant.

## Layout

```
untc-skill/
├── SKILL.md             # the skill manifest Claude reads
├── README.md            # you are here
├── requirements.txt     # optional pypdf fallback only
├── scripts/
│   └── untc.py          # the CLI
└── cache/
    ├── index.json
    └── treaties/<chapter>/<ref>/{status,text}.{lang}.{pdf,txt}
```

## Requirements

- **Python 3.10+** (uses `dict | None` style type hints)
- **`pdftotext`** (from `poppler-utils`) is strongly preferred — it
  preserves the columnar participant table that the MTDSG PDFs use.
  On Debian/Ubuntu: `sudo apt install poppler-utils`. On macOS:
  `brew install poppler`. On Windows: install Xpdf or Poppler for
  Windows and add it to PATH.
- If `pdftotext` is unavailable, `pip install pypdf` provides a
  fallback (with worse table extraction).

## Quickstart

```bash
# one-time index build (~1–2 min, hits each MTDSG chapter page)
python3 scripts/untc.py index --refresh

# resolve a treaty by name
python3 scripts/untc.py lookup "vienna convention on the law of treaties"

# get everything for a treaty (status doc + text), in one go
python3 scripts/untc.py fetch ICCPR

# or directly by MTDSG reference
python3 scripts/untc.py fetch XXIII-1

# only the status doc (parties + reservations), in French
python3 scripts/untc.py status IV-4 --lang fr

# treaty text by UNTS volume + registration number
python3 scripts/untc.py text --vol 999 --reg 14668 --lang en
```

After `fetch ICCPR` you'll have:

```
cache/treaties/IV/IV-4/meta.json          # title, vol, regnum, parties...
cache/treaties/IV/IV-4/status.en.pdf      # 138-page MTDSG status doc
cache/treaties/IV/IV-4/status.en.txt      # extracted text (grep-able)
cache/treaties/IV/IV-4/text.en.pdf        # UNTS treaty text PDF
cache/treaties/IV/IV-4/text.en.txt        # extracted text
```

## Installing as a Claude skill

Skills are discovered from your skills directory. The simplest install
is a symlink (or copy) of this folder:

- macOS / Linux:
  `ln -s ~/Dropbox/Claude/UNTC/untc-skill ~/.claude/skills/untc`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\untc" "C:\Users\<you>\Dropbox\Claude\UNTC\untc-skill"`

Then in Claude Code or Cowork: `/skill: untc` or just describe the
task ("get me the ICCPR text") and the description in `SKILL.md`
will trigger it.

## URL schemes (reference)

| Document | URL pattern |
|---|---|
| MTDSG status | `https://treaties.un.org/doc/Publication/MTDSG/Volume {I,II}/Chapter {ROMAN}/{REF}.{lang}.pdf` |
| UNTS treaty text | `https://treaties.un.org/doc/Publication/UNTS/Volume {N}/volume-{N}-{I,II}-{regNum}-{Lang}.pdf` |
| Chapter index (used to build name→ref index) | `https://treaties.un.org/Pages/Treaties.aspx?id={N}&subid=A&clang=_{lang}` |

`{I,II}` for MTDSG volume: chapters I–XII live in Vol I, XIII–XXIX
in Vol II. `{I,II}` in the UNTS URL is the registration *series*: I
for treaties registered ex officio under article 102, II for treaties
filed and recorded.

## Known limits (MVP)

- Only English-language chapter index is harvested; if you query in
  another language, name lookup still works because it goes against the
  English titles in the index, but you can pass `--lang fr` etc. when
  downloading the actual PDFs.
- Bilateral treaties (UNTS series II only, no MTDSG entry) require
  passing `--vol` and `--reg` manually for now.
- "Depositary notifications" (CN-feed) and the structured parties /
  reservations breakdown are not yet implemented; the raw text inside
  the MTDSG status doc has them and is greppable.

## Acknowledgements

Inspiration from [zhiyzuo/UNTC-scraper](https://github.com/zhiyzuo/UNTC-scraper)
for the realisation that the search frontend is JS-driven (we sidestep
that by going directly to the published PDFs).
