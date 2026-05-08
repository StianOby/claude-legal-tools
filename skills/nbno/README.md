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
  Bokhylla content.
- Download partial page ranges to keep batches fast.
- Assemble all pages into a single PDF and discard the intermediate images.

## Layout

```
nbno/
├── SKILL.md                   # the skill manifest Claude reads
├── README.md                  # you are here
└── scripts/
    ├── nbno_run.sh            # download wrapper
    └── capture_cookie.py      # interactive FEIDE login cookie capture
```

## Requirements

- **Bash** (for `nbno_run.sh`) — pre-installed on macOS/Linux; on Windows
  use Git Bash or WSL.
- **`nbno` CLI** — the wrapper installs it automatically on first run via
  `pip install --break-system-packages nbno`. If auto-install fails, run
  that command manually.
- **Python 3** with `playwright` — only needed for `capture_cookie.py`
  (cookie capture for FEIDE login). Install:
  ```bash
  pip install playwright
  playwright install chromium
  ```

## Quickstart

```bash
# open content (no login needed) — e.g. a pre-1900 book
bash scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/tmp/nbno_out"

# specific page range (canvas numbers, 1-based)
bash scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/tmp/nbno_out" \
  --start 10 --stop 16

# in-copyright Bokhylla content (after running capture_cookie.py)
bash scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
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
| `--keep-images` | Skip deletion of the per-page image folder |

Exit codes: `0` success, `1` bad arguments, `2` nbno install/run failure,
`3` no PDF produced (auth/geo issue), `4` cookie file missing.

## Authentication

Most pre-1900 books and public-domain material work without login. In-copyright
Bokhylla content requires a logged-in nb.no session **and** a Norwegian IP.

### Option A — No auth (open content)

Run without `--cookie`. If the download returns HTTP 401/403, use Option B.

### Option B — Cookie capture (FEIDE / Bokhylla)

Run `capture_cookie.py` on your local machine to open a Chromium window, let
you complete FEIDE/BankID/Vipps login interactively, and write the captured
`authorization` and `cookie` headers to `~/.nbno/cookie.txt`:

```bash
pip install playwright && playwright install chromium
python scripts/capture_cookie.py
```

Cookies typically live 24–48 hours. Re-run the script when downloads start
failing with auth errors.

### Option C — Manual cookie file

Supply a cookie text file captured from DevTools (Network → `manifest?fields=...`
→ Request Headers while logged in):

```
authorization=<token>
cookie=<full cookie header>
```

Pass it with `--cookie /path/to/cookie.txt`.

## Identifying items

`nbno` expects IDs of the form `<type>_<digits>`, e.g. `digibok_2008051600041`.

- **URN** — `URN:NBN:no-nb_digibok_2008051600041` → strip `URN:NBN:no-nb_` → `digibok_2008051600041`. The wrapper does this automatically.
- **Items URL** — `https://www.nb.no/items/<opaque-hash>` — the hash is not the ID. Click "Referere/Sitere" on nb.no to get the URN.
- **Already canonical** — use directly.

## Page range and performance notes

`--start`/`--stop` refer to IIIF canvas numbers (1-based), not printed page
numbers. On a first run, download canvases 1–7 and inspect the page footer to
determine the offset between canvas numbers and printed pages.

In a Cowork bash sandbox (45 s timeout), keep batches to **≤ 7 pages**. Each
batch has ~25 s startup overhead; each additional page adds ~1–2 s. Always
write output to `/tmp`, not a mounted workspace directory — files in mounted
directories cannot be overwritten from bash.

## Installing as a Claude skill

Skills are discovered from your skills directory. The simplest install is a
symlink (or copy) of this folder:

- macOS / Linux:
  `ln -s /path/to/nbno ~/.claude/skills/nbno`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\nbno" "C:\path\to\nbno"`

Then in Claude Code: paste an nb.no URN or describe the task ("download this
book from nb.no") and the trigger description in `SKILL.md` will activate the
skill automatically.

## Caveats

- **Geo-restriction.** Much of nb.no's collection is only accessible from
  Norwegian IP addresses. The skill cannot bypass this; the user needs a
  Norwegian session cookie or a VPN-routed cookie.
- **Copyright.** Access to Bokhylla is granted to individuals under a
  specific agreement and does not permit redistribution.
- **Rate limiting.** `nbno` is multi-threaded by default. If downloads fail
  with HTTP errors, retry with a smaller `--start`/`--stop` range.
- **Content search API.** The nb.no content search API does not work for
  `pliktmonografi` items even when authenticated — download and read pages
  directly instead.
