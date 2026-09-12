# nbno — download from Nasjonalbiblioteket (nb.no)

A self-contained Claude skill for downloading books, newspapers, photos,
journals, maps, and manuscripts from [Nasjonalbiblioteket](https://nb.no)
(the Norwegian National Library). The skill wraps the
[`nbno`](https://github.com/Lanjelin/NBNO.py) CLI tool by Lanjelin, which
uses nb.no's IIIF API to fetch page images and assemble them into a PDF.

## What it can do

- Resolve URN identifiers (`URN:NBN:no-nb_digibok_...`) to canonical IDs.
- Download any nb.no item type: books (`digibok`), newspapers (`digavis`),
  photos (`digifoto`), journals (`digitidsskrift`), maps (`digikart`),
  manuscripts (`digimanus`), programme reports (`digiprogramrapport`),
  and legal-deposit material (`pliktmonografi`, `pliktperiodika`).
- Authenticate with nb.no via FEIDE/BankID/Vipps to access in-copyright
  legal-deposit content — from the Cowork built-in browser where available,
  otherwise a manual cookie file.
- Download partial page ranges to keep batches fast.
- Assemble all pages into a single PDF and discard the intermediate images.

## Layout

```
nbno/
├── SKILL.md                   # the skill manifest Claude reads (lean router)
├── auth.md                    # authentication procedures (referenced by SKILL.md)
├── reading-ocr.md             # page reading, OCR, and PDF-shrink procedures
├── zotero-ready.md            # full Zotero-ready (PDF + OCR + RDF) workflow
├── iiif-download.md           # inline IIIF recipe + the resolver's gotchas
├── README.md                  # you are here
└── scripts/
    ├── nbno_run.sh            # download wrapper
    ├── nb_search.py           # find an item id from author/title/year (open catalogue)
    ├── geo_check.py           # print egress IP + accessInfo as nb.no sees them
    ├── zotero_book.py         # orchestrator: download → OCR → Zotero RDF
    ├── build_zotero_rdf.py    # Zotero RDF generation
    ├── ocr_chunked.py         # resumable, sandbox-friendly OCR
    ├── shrink_pdf.py          # JPEG-recompress an OCRed PDF in place
    └── browser/
        └── nbno_auth.js       # in-page helper for the built-in browser
```

SKILL.md is kept deliberately lean — it routes to `auth.md`,
`reading-ocr.md`, `iiif-download.md` and `zotero-ready.md` so only the
procedures relevant to a given task are loaded into Claude's context.

## Requirements

- **Bash** (for `nbno_run.sh`) — pre-installed on macOS/Linux; on Windows
  use Git Bash or WSL.
- **`nbno` CLI** — the wrapper installs it automatically on first run via
  `pip install --break-system-packages nbno`. If auto-install fails, run
  that command manually.
- **Nothing else.** Cookie capture uses the Cowork built-in browser where
  available; everywhere else you paste two cookie values from DevTools.

## Quickstart

```bash
# find the id from a reference (edition = year; "Utdrag av" hits are excerpts)
python scripts/nb_search.py "Eckhoff Rettskildelære" --year 2001

# open content (no login needed) — e.g. a pre-1900 book
bash scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/tmp/nbno_out"

# specific page range (canvas numbers, 1-based)
bash scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/tmp/nbno_out" \
  --start 10 --stop 16

# FEIDE-licensed content (after capturing nbsso and taking the digital loan)
bash scripts/nbno_run.sh \
  --id "digibok_2014050705024" \
  --out "/tmp/nbno_out" \
  --cookie auto \
  --start 1 --stop 7 \
  --resize 75
```

The wrapper always passes `--pdf` to `nbno` and removes the per-page image
folder after the PDF is assembled.

## Wrapper flags

| Flag | Purpose |
|---|---|
| `--id <ID>` | Canonical nb.no ID or full URN (required) |
| `--out <dir>` | Output directory for the PDF (required) |
| `--cookie auto` | Use saved auth at `~/.nbno/cookie.txt` |
| `--cookie <path>` | Use saved auth at an explicit path |
| `--start N` | First canvas to download (1-based) |
| `--stop N` | Last canvas to download (inclusive) |
| `--resize N` | Scale pages to N% of original size (50–75 for large books) |
| `--title` | Fetch the item's real title and use it as folder name |
| `--cover` | Download the cover separately |
| `--keep-images` | Keep the per-page images, moved to `<out>/<ID>_images/` |

Exit codes: `0` success, `1` bad arguments, `2` nbno install/run failure,
`3` no PDF produced (auth/geo issue), `4` cookie file missing, unreadable, or
without a usable `cookie=` line.

## Authentication

Less is needed than you might expect. `api.nb.no` authenticates by cookie, so
**there is no bearer token to capture**, and access divides cleanly by item
class (verified 2026-09-06 from a Norwegian IP):

| Item class | `accessAllowedFrom` | Credential needed | Image requests |
|---|---|---|---|
| Public domain | `EVERYWHERE` | **none** | single-shot or tiles |
| Bokhylla | `NORWAY` | **none** — a Norwegian IP is the whole requirement | tiles only |
| Legal deposit (`license: copyrighted`) | `NB` | **`nbsso`** + an active digital loan | tiles only |

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
manual DevTools cookie. Claude Code CLI has no built-in browser and lands on
the manual route, which costs one copy-paste:

1. Log in to nb.no in your own browser and open the item. Accept the digital
   loan if prompted.
2. DevTools (F12) → **Application** → **Cookies** → `https://www.nb.no`.
3. Copy the `nbsso` value into `~/.nbno/cookie.txt`:
   ```
   authorization=
   cookie=nbsso=<value>; _nblb=<value>
   ```
4. Use `--cookie auto` (or `--nbsso "nbsso=<value>"`).

Cookies typically live 24–48 hours; re-copy when downloads start failing with
auth errors. Note that a FEIDE-licensed item needs you in a browser for the
digital loan anyway, so this adds nothing to the trip.

### Option C — Manual cookie file

Supply a cookie text file captured from DevTools (Application → Cookies →
nb.no — you need `nbsso`; `_nblb` grants nothing on its own):

```
authorization=
cookie=nbsso=<value>; _nblb=<value>
```

The `authorization` line may be empty or omitted — the wrapper strips an
empty one before the `nbno` CLI sees it. Pass the file with
`--cookie /path/to/cookie.txt`.

## Identifying items

`nbno` expects IDs of the form `<type>_<key>`, e.g. `digibok_2008051600041`.
The key may itself contain underscores — newspaper issues are
`digavis_aftenposten_morgen_1_20150107_156_7_2`, journals
`digitidsskrift_2021052683055_001`.

- **URN** — `URN:NBN:no-nb_digibok_2008051600041` → strip `URN:NBN:no-nb_` → `digibok_2008051600041`. The wrapper does this automatically.
- **Items URL** — `https://www.nb.no/items/<opaque-hash>` — the hash is not the ID. Click "Referere/Sitere" on nb.no to get the URN.
- **Already canonical** — use directly.

## Page range and performance notes

`--start`/`--stop` refer to IIIF canvas numbers (1-based), not printed page
numbers. On a first run, download canvases 1–7 and inspect the page footer to
determine the offset between canvas numbers and printed pages.

In a Cowork bash sandbox the 45 s bash timeout is a *default*: pass an
explicit timeout (up to ~600 s) and a full book downloads in one call. If you
do batch, each batch has ~25 s startup overhead and each page adds ~1–2 s. Always
write output to `/tmp`, not a mounted workspace directory — files in mounted
directories cannot be overwritten from bash.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `nbno` and click
  **Install**. Click **Update** on the marketplace later to get new versions.
- *Claude Code:* `/plugin marketplace add StianOby/claude-legal-tools`, then
  `/plugin install nbno@claude-legal-tools`.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `nbno.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code, for development):**

- macOS / Linux:
  `ln -s /path/to/nbno ~/.claude/skills/nbno`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\nbno" "C:\path\to\nbno"`

Then in Claude Code: paste an nb.no URN or describe the task ("download this
book from nb.no") and the trigger description in `SKILL.md` will activate the
skill automatically.

## Caveats

- **Geo-restriction.** Items with `accessAllowedFrom: NORWAY` or `NB` serve
  page images only to Norwegian IPs, and no cookie changes that. The skill
  cannot bypass it. Both the sandbox and the browser pane egress from your own
  machine's IP, so a VPN on your machine covers both — your call, not the
  skill's.
- **Copyright.** Access to Bokhylla is granted to individuals under a
  specific agreement and does not permit redistribution. The built-in
  browser keeps a persistent profile, so a later session can download under
  your FEIDE identity without a fresh login — the same agreement still
  applies.
- **Rate limiting.** `nbno` is multi-threaded by default. If downloads fail
  with HTTP errors, retry with a smaller `--start`/`--stop` range.
- **Content search API.** The nb.no content search API does not work for
  `pliktmonografi` items even when authenticated — download and read pages
  directly instead.
