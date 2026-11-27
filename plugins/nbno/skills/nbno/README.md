# nbno — download from Nasjonalbiblioteket (nb.no)

A self-contained Claude skill for downloading books, newspapers, photos,
journals, maps, and manuscripts from [Nasjonalbiblioteket](https://nb.no)
(the Norwegian National Library). It fetches page images from nb.no's IIIF
API and assembles them into a PDF, with OCR and a Zotero item on request.
Until version 2.0 it wrapped the [`nbno`](https://github.com/Lanjelin/NBNO.py)
CLI tool by Lanjelin, whose work showed the way through nb.no's API.

## What it can do

- Resolve URN identifiers (`URN:NBN:no-nb_digibok_...`) to canonical IDs.
- Download any nb.no item type: books (`digibok`), newspapers (`digavis`),
  photos and posters (`digifoto`), journals (`digitidsskrift`), maps
  (`digikart`), manuscripts and letters (`digimanus`), programme reports
  (`digiprogramrapport`), and legal-deposit material (`pliktmonografi`,
  `pliktperiodika`).
- Authenticate with nb.no via FEIDE/BankID/Vipps to access in-copyright
  legal-deposit content — from the Cowork built-in browser where available,
  otherwise a manual cookie file.
- Download partial page ranges to keep batches fast, and resume a download
  that was cut off.
- Assemble all pages into a single PDF (optionally keeping the page images).

## Layout

```
nbno/
├── SKILL.md                   # the skill manifest Claude reads (lean router)
├── auth.md                    # authentication procedures (referenced by SKILL.md)
├── reading-ocr.md             # page reading, OCR, and PDF-shrink procedures
├── zotero-ready.md            # full Zotero-ready (PDF + OCR + RDF) workflow
├── iiif-download.md           # the downloader, inline IIIF recipe, resolver gotchas
├── troubleshooting.md         # caveats and troubleshooting
├── local-route.md             # shared: running steps on the user's computer (cloud Cowork)
├── README.md                  # you are here
├── scripts/
│   ├── nb_download.py         # download any item as a PDF
│   ├── nb_search.py           # find an item id from author/title/year (open catalogue)
│   ├── geo_check.py           # egress IP + accessInfo + a page-tile probe (is this IP allowed?)
│   ├── zotero_book.py         # orchestrator: download → text layer → shrink → Zotero RDF
│   ├── alto_text.py           # nb.no's own OCR (ALTO) as the PDF text layer
│   ├── zotero_rdf.py          # Zotero RDF + item JSON (copy of shared/zotero-rdf/)
│   ├── ocr_chunked.py         # resumable, sandbox-friendly OCR
│   ├── shrink_pdf.py          # recompress an OCRed PDF (bitonal G4 / grey / JPEG)
│   └── browser/
│       └── nbno_auth.js       # in-page helper for the built-in browser
```

Offline tests live in the repository at `tests/nbno/`, not in the plugin (they do not ship to users): `python tests/nbno/test_*.py` (needs Pillow; pypdf for the page-size test; pikepdf and numpy for the shrink tests).

SKILL.md is kept deliberately lean — it routes to `auth.md`,
`reading-ocr.md`, `iiif-download.md`, `zotero-ready.md`, `troubleshooting.md`
and `local-route.md` so only the
procedures relevant to a given task are loaded into Claude's context.

## Requirements

- **Python 3** — the scripts install what they need (Pillow, img2pdf, and
  for OCR and shrinking ocrmypdf, pikepdf, numpy) on first use, with the
  pinned versions in `scripts/requirements.txt` (kept current by Dependabot).
- **Nothing else.** Cookie capture uses the Cowork built-in browser where
  available; everywhere else you paste two cookie values from DevTools.

## Quickstart

```bash
# find the id from a reference (edition = year; "Utdrag av" hits are excerpts)
python scripts/nb_search.py "Eckhoff Rettskildelære" --year 2001

# open content (no login needed) — e.g. a pre-1900 book
OUT=$(mktemp -d)   # scratch dir; copy the finished PDF to outputs afterwards
python scripts/nb_download.py --id "digibok_2008051600041" --out "$OUT"

# specific canvas range (1-based manifest positions, covers included)
python scripts/nb_download.py --id "digibok_2008051600041" --out "$OUT" --start 10 --stop 16

# FEIDE-licensed content (after capturing nbsso and taking the digital loan)
python scripts/nb_download.py --id "digibok_2014050705024" --out "$OUT" --cookie auto
```

## Download flags

| Flag | Purpose |
|---|---|
| `--id <ID>` | Canonical nb.no ID or full URN (required) |
| `--out <dir>` | Output directory for the PDF (required) |
| `--cookie auto` / `--cookie <path>` | Use the nbsso cookie saved at `~/.nbno/cookie.txt` / an explicit path |
| `--nbsso "nbsso=<v>"` | The cookie pair itself |
| `--start N` / `--stop N` | Canvas range (1-based, inclusive); the file gets a `_c<N>-<M>` suffix |
| `--size half\|full` | Half size (default, ~145 dpi on a book page) or the scan's own size |
| `--keep-images` | Also keep the page images in `<out>/<basename>_images/` |
| `--shrink` | Recompress the page images (see `reading-ocr.md`) |

The PDF is named `AUTHOR_TITLE_(YEAR).pdf`. Exit codes: `0` success, `3` some
pages could not be downloaded (placeholder pages in their place), `4` cookie
file missing or without a usable `nbsso`, `1` any other error. The pages
downloaded so far stay in `<out>/_pages/` until the PDF is complete:
re-running the same command with the same `--out` fetches only the rest.

`zotero_book.py` takes the same flags and adds OCR, shrinking and the Zotero
RDF (see `zotero-ready.md`).

## Authentication

Less is needed than you might expect. `api.nb.no` authenticates by cookie, so
**there is no bearer token to capture**, and access divides cleanly by item
class (verified 2026-09-06 from a Norwegian IP):

| Item class | `accessAllowedFrom` | Credential needed | Image requests |
|---|---|---|---|
| Public domain | `EVERYWHERE` | **none** | single-shot or tiles |
| Bokhylla | `NORWAY` | **none** — a Norwegian IP is the whole requirement | single-shot first, else tiles |
| Legal deposit (`license: copyrighted`) | `NB` | **`nbsso`** + an active digital loan | single-shot first, else tiles |

Geo is enforced at the **image resolver**, not the API: from a non-Norwegian
IP the manifest and `accessInfo` return 200 and every page image returns 403,
no matter who is logged in. Check first:

```bash
python scripts/geo_check.py --id digibok_2008051600041 [--nbsso "nbsso=<v>"]
```

FEIDE-licensed items additionally need a **digital loan**, taken by the user
in a browser (the dialog reads *"Ved å klikke OK vil du foreta et
tidsbegrenset digitalt lån"*). It is time-limited and consumes one of the
item's licences, so the skill never clicks OK on the user's behalf.

### Option A — No auth (open content, and Bokhylla from Norway)

Run without `--cookie`. If page images 403, check `accessAllowedFrom` and
your IP *before* reaching for a cookie.

### Option B — Session capture (FEIDE-licensed items only)

In Claude Desktop/Cowork the skill captures `nbsso` from the **built-in
browser** (`SKILL.md` Step 0, using `scripts/browser/nbno_auth.js`). Because
the safety classifier blocks cookie reads that Claude initiates on its own,
it will ask you to type a sentence naming the action first — that is expected,
not a bug.

Fallback ladder when the built-in browser is unavailable: Claude in Chrome →
manual DevTools cookie. A client with no built-in browser lands on
the manual route, which costs one copy-paste:

1. Log in to nb.no in your own browser and open the item. Accept the digital
   loan if prompted.
2. DevTools (F12) → **Application** → **Cookies** → `https://www.nb.no`.
3. Copy the `nbsso` value into `~/.nbno/cookie.txt`:
   ```
   cookie=nbsso=<value>; _nblb=<value>
   ```
4. Use `--cookie auto` (or `--nbsso "nbsso=<value>"`).

Cookies typically live 24–48 hours; re-copy when downloads start failing with
auth errors (the scripts warn when the file is over 24 hours old). Note that
a FEIDE-licensed item needs you in a browser for the digital loan anyway, so
this adds nothing to the trip.

### Option C — Manual cookie file

Supply a cookie text file captured from DevTools (Application → Cookies →
nb.no — you need `nbsso`; `_nblb` grants nothing on its own), with the line
`cookie=nbsso=<value>; _nblb=<value>`. An `authorization=` line, as older
captures have, is ignored. Pass the file with `--cookie /path/to/cookie.txt`.

## Identifying items

IDs have the form `<type>_<key>`, e.g. `digibok_2008051600041`.
The key may itself contain underscores — newspaper issues are
`digavis_aftenposten_morgen_1_20150107_156_7_2`, journals
`digitidsskrift_2021052683055_001`.

- **URN** — `URN:NBN:no-nb_digibok_2008051600041` → strip `URN:NBN:no-nb_` → `digibok_2008051600041`. The scripts do this automatically.
- **Items URL** — `https://www.nb.no/items/<opaque-hash>` — the hash is not the ID. Click "Referere/Sitere" on nb.no to get the URN.
- **Already canonical** — use directly.

## Page range and performance notes

`--start`/`--stop` refer to positions in the item's IIIF manifest (1-based,
covers included), not printed page numbers. On a first run, download
canvases 1–7 and inspect the page footer to determine the offset between
canvas numbers and printed pages.

In a Cowork bash session the bash timeout defaults to 120 s. Pass an
explicit long timeout, but expect a call to be cut off at about 170 s
whatever you ask for. A full book still downloads in one call (424 pages
in about 105 s); whole-book OCR does not (use `ocr_chunked.py`). A download
that is cut off resumes when re-run. Write output to a scratch directory
(`mktemp -d`) and copy the finished PDF to the outputs directory afterwards.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `nbno` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `nbno.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

Then in Cowork: paste an nb.no URN or describe the task ("download this
book from nb.no") and the trigger description in `SKILL.md` will activate the
skill automatically.

## Caveats

- **Geo-restriction.** Items with `accessAllowedFrom: NORWAY` or `NB` serve
  page images only to Norwegian IPs, and no cookie changes that. The skill
  cannot bypass it. In a cloud Cowork session the shell runs in Anthropic's
  cloud (not a Norwegian IP), so the skill downloads such items through the
  sandboxed local shell on your own computer instead (the Claude desktop app
  must be open, with a folder connected); results land in
  `<connected folder>/nbno/<id>/`. See `local-route.md`.
- **Copyright.** Access to Bokhylla is granted to individuals under a
  specific agreement and does not permit redistribution. The built-in
  browser keeps a persistent profile, so a later session can download under
  your FEIDE identity without a fresh login — the same agreement still
  applies.
- **Rate limiting.** Downloads are multi-threaded and retry rate limits and
  server errors. Pages that still fail become placeholder pages (exit 3);
  re-run the same command with the same `--out` to fill them in.
- **Content search API.** The nb.no content search API does not work for
  `pliktmonografi` items even when authenticated — download and read pages
  directly instead.
