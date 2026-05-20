---
name: nbno
description: >
  Use any time the user wants to download or work with material from
  Nasjonalbiblioteket (Norwegian National Library, nb.no). Triggers: links to
  nb.no or urn.nb.no; mentions of "Nasjonalbiblioteket", "Bokhylla", "FEIDE
  login to nb.no", "digibok", "digavis", "digifoto", "digitidsskrift",
  "digikart", "digimanus", "digiprogramrapport"; URN ids like
  "URN:NBN:no-nb_digibok_..."; requests like "last ned boka fra nb.no", "get
  the PDF of this nb.no item", "log in to nb.no with FEIDE and download X".
  Covers books, newspapers, photos, journals, maps, manuscripts, sheet music,
  posters, programme reports. ALSO use for "Zotero-ready" requests
  ("Zotero-ready book", "nb.no book into Zotero", "Zotero RDF for nb.no",
  "OCR and import this book") — triggers the PDF + OCR + Zotero RDF workflow.
  Do NOT use for: Lovdata legal texts (use the lovdata skill), generic web
  scraping, or content the user has no right to access.
---

# nbno — download from Nasjonalbiblioteket (nb.no)

This skill wraps the [`nbno`](https://github.com/Lanjelin/NBNO.py) CLI tool by
Lanjelin, which uses nb.no's IIIF API to download books, newspapers, photos,
journals, maps, manuscripts, etc. as page images and assemble them into a PDF.

The user's preferences for this skill:

- **Output**: PDF only. The wrapper always builds a PDF and removes per-page
  images automatically — do **not** pass `--pdf` yourself (it is an unknown
  argument to the wrapper and will cause an error).
- **Auth**: Prompt every time. Before each run, ask the user which of the
  three auth paths in **Step 2** to take. The default cookie location is
  `~/.nbno/cookie.txt`, populated by the `capture_cookie.py` script.

## Prerequisites

- **`{SKILL_DIR}`** — replace this placeholder with the path printed in
  "Base directory for this skill:" at the top of your context.
- **`nbno` CLI** — the wrapper installs it automatically on first run via
  `pip install --break-system-packages nbno`. If auto-install fails, run
  that command manually before proceeding.

---

## Step 1 — Identify the media ID

`nbno --id <ID>` requires an ID of the form `<type>_<digits>`, e.g.
`digibok_2008051600041`. There are three common ways the user may give you
the item:

1. **Citation / URN** — `URN:NBN:no-nb_digibok_2008051600041` → strip
   `URN:NBN:no-nb_` → `digibok_2008051600041`. The wrapper does this for
   you automatically; you can paste either form.
2. **Items URL** — `https://www.nb.no/items/<opaque-hash>?...`. The opaque
   hash is **not** the ID nbno expects. Resolve it by either (a) clicking
   "Referere/Sitere" on nb.no and copying the URN, or (b) fetching the
   items page and extracting the URN from its metadata. If you only have
   the opaque URL, ask the user for the URN/Referere string rather than
   guess.
3. **Already canonical** — the user pastes `digibok_2008051600041` directly
   → use as-is.

Supported `type` prefixes: `digibok` (books, sheet music), `digavis`
(newspapers), `digifoto` (photos, posters), `digitidsskrift` (journals),
`digikart` (maps), `digimanus` (letters, manuscripts, music manuscripts),
`digiprogramrapport` (programme reports), `pliktmonografi` /
`pliktperiodika` (legal-deposit material).

---

## Step 2 — Decide on authentication

Most pre-1900 books and out-of-copyright photos/maps work without login.
In-copyright Bokhylla content needs a logged-in nb.no session **and** access
from a Norwegian IP. Ask the user which of the three paths to take.

> **Check `accessInfo` before guessing.**
> The catalog endpoint
> `https://api.nb.no/catalog/v1/items/URN:NBN:no-nb_<id>` returns an
> `accessInfo` block. Two fields are decisive:
>
> - `viewability == "NONE"` → auth is mandatory; a no-auth fetch will fail.
> - non-empty `accessInfo.legalDepositLoginText` (e.g. "4 lisenser for
>   Feide-brukere…") → FEIDE auth is mandatory.
>
> `zotero_book.py` performs this check automatically and refuses to start a
> no-auth download in those cases (override with `--force-auth`). When
> driving the IIIF API directly, GET the catalog response first and
> short-circuit to Option B if either signal is present. This is more
> reliable than the old "pliktmonografi: try no-auth first" heuristic —
> some pliktmonografi items are FEIDE-restricted, some aren't, and
> `accessInfo` tells you which.

### Option A — No auth (open content)

The default. Run `nbno_run.sh` without `--cookie`. Best when the user pasted
a URN for an old book, sheet music, public-domain photo, or any
`pliktmonografi_*` / `pliktperiodika_*` item. If the download fails with HTTP
401/403, fall back to Option B.

### Option B — Cookie capture (recommended for FEIDE / Bokhylla)

Use this when the item is in-copyright (Bokhylla) or the user mentions
FEIDE, BankID, Vipps, or "logged in."

> **⛔ STOP — MANDATORY BEFORE ANY FETCH IN COWORK MODE**
>
> Before running any fetch or navigation command, you **must** confirm the
> user has an active Nasjonalbiblioteket session. Do this first, every time:
>
> 1. Ask the user: *"Have you logged in to nb.no recently? If not,
>    please log in now at <https://nb.no> in your browser."*
> 2. Wait for confirmation before proceeding.
>
> **If you skip this step and the user is not logged in, every fetch will
> silently fail** (returning a JS-required page or a blank session error)
> and the resulting debugging will waste significant time. There is no
> reliable way to detect a missing session after the fact.

#### Primary method for Cowork sessions — playwright MCP

In a Cowork session the most practical approach is to capture the cookie
directly via the `mcp__playwright__*` tools.

> **Before proceeding: check that Playwright MCP is installed.**
> Look for `mcp__playwright__*` tools in your available tool set. If they
> are absent, stop and tell the user:
>
> > "This method requires the **Playwright MCP** server — a browser
> > automation layer that lets Claude drive a real Chromium window and
> > inspect its network traffic. Without it I cannot capture the nb.no
> > authentication cookie automatically.
> >
> > Install it from the official repository:
> > [github.com/microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
> >
> > Once installed and connected to your Claude session (you may need to
> > restart the session), come back and I will continue from here."
>
> Do not proceed with steps 1–6 until `mcp__playwright__*` tools are
> confirmed available. Fall back to Option B (`capture_cookie.py`) or
> Option C (manual cookie file) if the user cannot install the MCP.

1. Navigate to nb.no and let the user complete login in the visible window.
2. Ask the user to open the book page in the viewer.
3. Call `mcp__playwright__browser_network_requests` filtered on `api.nb.no`
   to list recent requests.
4. Find the `manifest?fields=...` entry; call
   `mcp__playwright__browser_network_request` with `part: "request-headers"`
   on that entry to retrieve the `authorization` token.
5. Retrieve the cookie string separately with
   `mcp__playwright__browser_evaluate` using `() => document.cookie`.
6. Write both values to a two-line file (e.g. `/tmp/cookie.txt`):
   ```
   authorization=<token>
   cookie=<full cookie string>
   ```
   Pass this path as `--cookie /tmp/cookie.txt` to the wrapper.

> **Auth scope:** The `authorization` bearer token captured above is valid
> only for `api.nb.no` (the manifest API). The IIIF image resolver at
> `www.nb.no/services/image/resolver/` ignores the bearer token entirely —
> it authenticates via the `nbsso` session cookie plus a correct `referer`
> header. Both values are needed: bearer for the manifest, nbsso for images.

Cookies on nb.no live roughly 24–48 hours. When downloads start failing
with auth errors, repeat steps 3–6 to refresh the token.

#### Alternative for repeated or automated use — `capture_cookie.py`

The skill ships a script at `scripts/capture_cookie.py` that opens a real
Chromium window, lets the user complete FEIDE/BankID/Vipps login
interactively, and writes the captured `authorization` + `cookie` headers
to `~/.nbno/cookie.txt`. This approach is better when you expect to run
multiple sessions and want a durable cookie file.

The script must run on the user's own machine (it needs a visible browser —
the sandbox has no display). On first run:

```bash
pip install playwright
playwright install chromium
python {SKILL_DIR}/scripts/capture_cookie.py
```

After capture, the user has `~/.nbno/cookie.txt` (Windows:
`C:\Users\<name>\.nbno\cookie.txt`). To make that file reachable from the
sandbox, ask the user to either:

1. Mount their `.nbno/` folder via `request_cowork_directory` (cleanest —
   works for repeat runs), or
2. Upload `cookie.txt` once into the session (you can then pass the upload
   path to `--cookie`).

Then invoke the wrapper with `--cookie auto` (resolves to
`~/.nbno/cookie.txt` inside the sandbox — adjust the path accordingly if
the cookie is mounted/uploaded elsewhere, in which case pass
`--cookie /path/to/cookie.txt` explicitly).

### Option C — Manual cookie file (legacy)

If the user already has a cookie text file from DevTools, accept its path
and pass it through with `--cookie <path>`. Format (per nbno's README):

```
authorization=<token>
cookie=<full cookie header>
```

The user obtains it from DevTools → Network → `manifest?fields=...` →
Request Headers, while logged in.

---

## Step 3 — Download options

### Fast path — direct IIIF downloader (recommended for full Bokhylla books)

For full-book `digibok_*` downloads, bypass `nbno_run.sh` entirely and use
the in-process IIIF downloader. It fetches pages directly via the IIIF API
with `ThreadPoolExecutor(12)` and is roughly **20× faster** than batching
through the CLI (~200 pages in ~10 s vs ~25 s startup + 1–2 s/page).

**Preferred: use the orchestrator's downloader directly.**
`scripts/zotero_book.py:download_via_iiif()` already handles every gotcha
listed in this file:

- tries both `/items/<id>/manifest` *and* `/iiif/URN:NBN:no-nb_<id>/manifest`
  (the second form is required for some pliktmonografi items where the
  first returns 404);
- fetches `info.json` to pick a width the resolver will actually serve at
  the requested resolution (the resolver silently downsamples otherwise —
  asking for `608,` on a book that only lists `[502, 251, …]` returns a
  502px image which makes OCR unusable);
- verifies the returned image dimensions with PIL and, on mismatch, falls
  back to native-resolution `regionByPx` 1024×1024 tiles stitched together;
- skips the `_C2` back cover automatically.

```python
import sys
sys.path.insert(0, "{SKILL_DIR}/scripts")
from zotero_book import download_via_iiif
from pathlib import Path

download_via_iiif(
    canonical_id="digibok_2008051600041",
    out_pdf=Path("/tmp/nbno_direct/book.pdf"),
    bearer="<token>",
    nbsso="nbsso=<value>",
    resize_width=1024,    # listed sizes will be checked; actual cap may be lower
    workers=12,
    tiles="auto",         # "always" to force tiled, "never" to disable fallback
)
```

**Minimal inline recipe** (use only when calling `zotero_book.py` is not an
option — e.g. you don't have the skill directory on disk):

```python
import io, json, os, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ITEM_ID = "digibok_2008051600041"   # ← replace
NBSSO   = "nbsso=<value>"           # ← just the nbsso=... part
BEARER  = "<token>"                 # ← bearer token for api.nb.no
OUT_DIR = Path(f"/tmp/nbno_direct/{ITEM_ID}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

REFERER = f"https://www.nb.no/items/URN:NBN:no-nb_{ITEM_ID}"
HDR_API = {"authorization": BEARER}
HDR_IMG = {"cookie": NBSSO, "referer": REFERER}

def _get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def fetch_manifest():
    for url in (
        f"https://api.nb.no/catalog/v1/items/{ITEM_ID}/manifest",
        f"https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb_{ITEM_ID}/manifest",
    ):
        try:
            return _get_json(url, HDR_API)
        except urllib.error.HTTPError as e:
            if e.code != 404: raise
    raise SystemExit("manifest not found on either endpoint")

def pick_width(info, target):
    sizes = sorted({int(s["width"]) for s in info.get("sizes") or [] if s.get("width")},
                   reverse=True)
    for w in sizes:
        if w <= target: return w
    return sizes[-1] if sizes else target

def fetch_tiled(base, info, tile=1024):
    full_w, full_h = int(info["width"]), int(info["height"])
    canvas = Image.new("RGB", (full_w, full_h), "white")
    for y in range(0, full_h, tile):
        for x in range(0, full_w, tile):
            tw, th = min(tile, full_w - x), min(tile, full_h - y)
            url = f"{base}/{x},{y},{tw},{th}/full/0/default.jpg"
            req = urllib.request.Request(url, headers=HDR_IMG)
            with urllib.request.urlopen(req, timeout=30) as r:
                canvas.paste(Image.open(io.BytesIO(r.read())).convert("RGB"), (x, y))
    buf = io.BytesIO(); canvas.save(buf, "JPEG", quality=92); return buf.getvalue()

canvases = fetch_manifest()["sequences"][0]["canvases"]
entries = [(c["@id"].split("/")[-1], c["images"][0]["resource"]["service"]["@id"])
           for c in canvases]

# Probe info.json once; nb.no's resolver is consistent across canvases.
probe_info = _get_json(f"{entries[0][1]}/info.json", HDR_IMG)
width = pick_width(probe_info, target=1024)
print(f"resolver lists widths; using {width}px (target was 1024)")

def fetch_page(idx_entry):
    idx, (name, base) = idx_entry
    if name.endswith("_C2"): return idx, None
    url = f"{base}/full/{width},/0/default.jpg"
    try:
        req = urllib.request.Request(url, headers=HDR_IMG)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code != 403: raise
        # Fall back to native-res tiles.
        info = _get_json(f"{base}/info.json", HDR_IMG)
        data = fetch_tiled(base, info)
    # Verify single-shot wasn't silently downsampled.
    if Image.open(io.BytesIO(data)).size[0] < width - 4:
        info = _get_json(f"{base}/info.json", HDR_IMG)
        data = fetch_tiled(base, info)
    path = OUT_DIR / f"page_{idx:04d}.jpg"
    path.write_bytes(data)
    return idx, str(path)

t0 = time.time()
with ThreadPoolExecutor(max_workers=12) as pool:
    results = dict(pool.map(fetch_page, enumerate(entries, start=1)))
print(f"downloaded in {time.time()-t0:.1f}s")

pages = [Image.open(p).convert("RGB") for _, p in sorted(results.items()) if p]
pdf = OUT_DIR / f"{ITEM_ID}.pdf"
pages[0].save(pdf, save_all=True, append_images=pages[1:])
print(pdf)
```

Keep each Python call under ~40 s; `/tmp` is wiped if the sandbox restarts
after a timeout.

### Standard path — `nbno_run.sh` wrapper (short ranges / non-Bokhylla)

Use `nbno_run.sh` for non-Bokhylla content or when you only need a short page
range (≤ 7 pages of `digibok_*`).

> **Fetch only what you need.**
> Use `--start <int>` and `--stop <int>` to limit the download to a page
> range. Downloading a full book when you only need a few pages is slow,
> expensive, and stresses nb.no's servers. Always ask the user which pages
> they need before running without these flags.
>
> **Keep each batch to ≤ 7 pages** when running in the Cowork bash sandbox.
> Each `nbno_run.sh` invocation has a fixed startup overhead of ~25 s
> (manifest fetch, item resolution, etc.); each additional page adds ~1–2 s.
> The sandbox timeout is 45 s. Batches of 7 pages complete reliably; 8 is
> risky; 10+ almost always times out (the process may still finish in the
> background, but the PDF will not be immediately available).
>
> Examples:
> - Single page: `--start 42 --stop 42`
> - A short batch: `--start 10 --stop 16`
> - Full book: omit both flags (slow — prefer batches)

> **Use `/tmp` for `--out`, not a mounted workspace directory.**
> If `--out` points to a mounted workspace folder and a PDF with the same
> name already exists there, `nbno_run.sh` will fail with
> `mv: unable to remove target: Operation not permitted` — files written to
> the mounted workspace cannot be overwritten or deleted from bash. Always
> pass `--out /tmp/nbno_out` (or any path under `/tmp`). After the download,
> copy the PDF to the workspace with Python if needed, using a unique name:
> ```python
> import shutil
> shutil.copy2("/tmp/nbno_out/<item>.pdf", "/path/to/workspace/<unique-name>.pdf")
> ```

> **Determine the canvas-to-printed-page offset before targeting a range.**
> `--start`/`--stop` refer to IIIF canvas numbers (1-based sequence), not
> necessarily printed page numbers. On a first run, download canvases 1–7
> and inspect the page footer or header text (e.g. an InDesign filename
> suffix like `...indd 5` on canvas 5 confirms an offset of zero). Once the
> offset is known, calculate the correct canvas numbers before requesting a
> specific printed-page range.

```bash
bash {SKILL_DIR}/scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/tmp/nbno_out" \
  [--cookie auto | --cookie /path/to/cookie.txt] \
  [--start 1 --stop 7] \
  [--resize 75] \
  [--title]
```

Useful nbno flags the wrapper passes through:

| flag | purpose |
| --- | --- |
| `--title`        | fetch the item's real title and use it as folder name |
| `--start N`      | first canvas to download (1-based)                    |
| `--stop N`       | last canvas to download (inclusive)                   |
| `--resize N`     | percentage of original size — use 50–75 for big books |
| `--cover`        | also download the cover separately                    |
| `--keep-images`  | skip deletion of the per-page image folder            |
| `--cookie auto`  | use saved auth at `~/.nbno/cookie.txt` (Bokhylla)     |
| `--cookie PATH`  | use saved auth at an explicit path                    |

After the wrapper completes you'll have a single `.pdf` in `/tmp/nbno_out`.
The wrapper has already removed the per-page image folder unless the user
passed `--keep-images`.

---

## Inspecting pages — visual reading vs OCR

When you need to read specific page content (e.g. to determine the canvas
offset, verify a source, or check a passage), rendering pages to PNG and
reading them with Claude's image-reading capability (the Read tool) is
faster and more reliable than OCR.

### Visual reading (recommended)

```python
import fitz  # PyMuPDF

doc = fitz.open("/tmp/nbno_out/<item>.pdf")
page = doc[0]  # 0-based index; canvas N = index N-1
mat = fitz.Matrix(1, 1)  # 1× scale → approx 1652 × 2272 px from a --resize 75 PDF
pix = page.get_pixmap(matrix=mat)
pix.save("/tmp/page_01.png")
```

Then use the Read tool on `/tmp/page_01.png`. Rendering at 1× from a
`--resize 75` PDF gives approximately 1652 × 2272 px, which stays within
the Read tool's ~2000 px limit. Do **not** use `fitz.Matrix(1.5, 1.5)` or
higher from a 75%-resize PDF — the result (~2479 × 3409 px) exceeds the
limit. If 1× images are still too large, resize with PIL before saving:

```python
from PIL import Image
img = Image.open("/tmp/page_01.png")
img = img.resize((img.width // 2, img.height // 2))
img.save("/tmp/page_01_small.png")
```

### OCR via tesseract (if needed)

OCR is possible but requires extra setup. Only use it when you need
machine-readable text rather than a visual check.

- Download `nor.traineddata` (and `osd.traineddata`) to `/tmp` and set
  `TESSDATA_PREFIX=/tmp` before running tesseract.
- Use `--psm 6` (uniform block of text) rather than `--psm 1` (the OSD
  model may not be available).
- Process one page per bash call to stay within the sandbox timeout.
- The `nno` (Norwegian Nynorsk) language pack is missing from many Cowork
  sandboxes — only `nor` is preinstalled. The orchestrator's
  `tesseract_preflight()` helper auto-degrades to whichever requested codes
  are actually available; when running tesseract by hand, list languages
  with `tesseract --list-langs` first.

### OCR for whole books — `ocr_chunked.py`

`scripts/ocr_chunked.py` is a resumable wrapper around ocrmypdf designed
for the 45-second Cowork bash limit:

1. Split input into per-page PDFs (cached under
   `<pdf_dir>/.ocr_cache/<stem>/<hash>/pages/`).
2. OCR each page with `ocrmypdf --skip-text` (full quality — same preprocess,
   deskew, optimise as a one-shot run), cached under `…/ocred/`.
3. Stop launching new pages when the time budget is about to expire; exit
   with code 2 (partial).
4. On the call that finishes the last page, merge with pikepdf and exit 0.

```bash
# Loop until done. Each iteration makes progress; cache survives between calls.
until python {SKILL_DIR}/scripts/ocr_chunked.py \
    --pdf "$PDF" \
    --langs nor+nno \
    --time-budget 35 \
    --jobs 4; do
  echo "partial — re-running..."
done
```

Quality is identical to a single-shot ocrmypdf run because each page goes
through the same pipeline; only the orchestration is chunked. The cache key
includes the input's mtime + size, so re-downloading the PDF correctly
invalidates the cache.

On each invocation `ocr_chunked.py` opens every cached page with
`pikepdf.open` first; any file that fails the check (typically: tesseract
killed mid-write by a previous timeout) is deleted and regenerated on this
pass. On the call that finishes the last page, the per-page cache is
deleted automatically — pass `--keep-intermediates` to retain it for
debugging.

### Shrinking the output — `shrink_pdf.py`

OCR'd PDFs from the IIIF-tile path are often huge (700–900 MB for a
~300-page book) because each page is embedded as a lossless Flate-PNG.
**Do not re-OCR to shrink** — the text layer is already correct and
re-OCR'ing wastes minutes per book. Instead, recompress the embedded
images in place:

```bash
python {SKILL_DIR}/scripts/shrink_pdf.py --pdf book.pdf
```

Defaults are tuned for **~50 MB on a 350-page text-heavy book**
(`--quality 70 --max-width 900`, i.e. ~143 KB/page). Override either
flag if you want a different quality/size tradeoff.

This walks each page's image XObjects, re-encodes as JPEG at the given
quality, and replaces the streams. The OCR text layer, page tree, and
bookmarks are untouched. 1-bit monochrome images are skipped (JPEG would
grow them and degrade them visibly). On a typical IIIF-tile book the
defaults take ~30 s and produce ~50 MB output.

**Probe-and-extrapolate.** Before each run, `shrink_pdf.py` recompresses
one middle page and prints the estimated total output size
(`page × n_pages × 0.95`). The "halve dimensions, halve size" heuristic
falls apart for typographic detail, so always trust the probe rather
than a guess. Pass `--probe-only` to print just the estimate and exit
without writing.

**Never overwrites the input by default.** Output goes to a sibling
`<stem>_q70_w900.pdf` (the filename encodes the settings). Re-encoding
an already-shrunk file compounds JPEG artefacts, so leaving the
high-quality master in place lets you experiment with settings
non-destructively. Use `--in-place` to overwrite.

`zotero_book.py` also exposes this as `--shrink` with the same defaults
(`--shrink-quality 70 --shrink-max-width 900`). Because the orchestrator
keeps the canonical filename for the Zotero RDF, `--shrink` rewrites the
PDF in place — but **copies the OCRed master to `<basename>.original.pdf`
first** so re-shrinking with different settings starts from the
high-quality version, not the already-shrunk one. Pass
`--shrink-no-keep-master` to skip the copy. Without `--shrink`, the
orchestrator prints a one-line hint if the output PDF exceeds
`--shrink-threshold-mb` (default 500). Re-running `zotero_book.py
--shrink` after the fact is also fine — the master copy makes
experimentation safe.

---

## Step 4 — Hand the file back

Copy the PDF from `/tmp/nbno_out` to the user's outputs directory and share
it with a `computer://` link, e.g.:

```
[View your PDF](computer:///.../outputs/nbno/<digibok_xxx>.pdf)
```

Do not narrate the contents of the PDF beyond what's needed; let the user
open it.

---

## Zotero-ready book workflow

Trigger whenever the user asks for a **Zotero-ready** book from nb.no, an
**RDF with the PDF attached**, "import this into Zotero with one click",
"OCR and import this book", or similar phrasing.

The full pipeline (orchestrator script, every flag, sandbox notes, metadata
customisation, Zotero-specific troubleshooting) lives in
[`zotero-ready.md`](zotero-ready.md) next to this file. **Read it before
running** — it covers the access pre-check, the chunked-OCR flow for big
books, and the `--shrink` post-step. Quick start:

```bash
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --bearer "$BEARER" --nbsso "nbsso=$NBSSO"
```

Output is a `.pdf` + `.rdf` pair in `$OUT_DIR`; drag the `.rdf` into
Zotero. For Bokhylla / pliktmonografi content, follow Step 2 above to
capture bearer + nbsso first.

---

## Important caveats — surface these to the user when relevant

- **Geo-restriction.** A large share of nb.no's collection (especially
  Bokhylla / in-copyright material) is nominally geo-restricted to Norwegian
  IP addresses. However, 403 errors from the sandbox are more commonly caused
  by wrong URL format (e.g. `pct:75` or `full` instead of an explicit width)
  or wrong auth headers than by actual IP-based blocking. With the correct
  setup — a width drawn from `info.json`'s `sizes[]` array + `nbsso` cookie
  + correct `referer` — sandbox downloads succeed from non-Norwegian IPs.
  **Check auth and URL format before assuming geo-restriction.** If errors
  persist after fixing those, then a Norwegian session cookie from the
  user's own network is likely required.
- **Resolver silently downsamples requests above its listed sizes.** Asking
  for `/full/1024,/0/default.jpg` on an item whose `info.json` only lists
  `[502, 251, …]` returns a 502-wide image with `HTTP 200` and no warning.
  Treating that as a 1024-wide image (e.g. assuming 300 DPI for OCR)
  produces unusable output. Always GET `info.json` first and pick a width
  from `sizes[]`, or verify the returned image's dimensions with PIL after
  download. The orchestrator handles both automatically; for inline
  recipes, follow the pattern in **Step 3 — Fast path**.
- **Native-resolution tiles work when single-shot doesn't.** When the
  resolver refuses `/full/<w>,/` for in-copyright/licensed content,
  `regionByPx` requests up to 1024×1024 are routinely allowed at native
  resolution. The orchestrator's `--tiles auto` falls back to tiling
  whenever single-shot returns 403 or is silently downsampled. Use
  `--tiles always` to force tiling from the start.
- **Copyright.** Most twentieth-century books are in copyright; access via
  Bokhylla is granted to individuals under a specific agreement and does
  not permit redistribution. The user is responsible for using downloaded
  content in line with that agreement. Don't help redistribute clearly
  in-copyright material.
- **Rate limiting.** nbno is multi-threaded by default. If a download
  fails with HTTP errors, retry with fewer workers or a smaller page
  range (`--start`/`--stop`).
- **Size.** A full novel scanned at 100% can be 200–500 MB. Suggest
  `--resize 60` if the user just wants something readable.
- **Content search API does not work for pliktmonografi items.** The nb.no
  content search API (`https://api.nb.no/catalog/v1/contentsearch/{item_id}/search?q=...`)
  returns empty results for `pliktmonografi` items even when the user is
  authenticated via FEIDE. It may work for `digibok` items. Do not rely on
  it for legal-deposit material — download and read the pages directly instead.

---

## Troubleshooting

- *Command not found `nbno`.* See **Prerequisites** above.
- *Empty PDF / no images downloaded.* For `digibok` / Bokhylla content this
  is almost always an auth or geo issue — go to Step 2 and use Option B or C.
  For `pliktmonografi_*` / `pliktperiodika_*` items, GET the catalog
  response and inspect `accessInfo.legalDepositLoginText` /
  `accessInfo.viewability` — those fields decide whether FEIDE auth is
  required (see Step 2's "Check `accessInfo` before guessing" callout).
  The orchestrator does this automatically; pass `--force-auth` to override.
- *`--cookie auto` errors with "no cookie file found".* The wrapper looked
  at `~/.nbno/cookie.txt` and didn't find one. Either the user hasn't run
  `capture_cookie.py` yet, or they ran it on their own machine but
  haven't mounted/uploaded the file into the sandbox. Walk them through
  Step 2 Option B again.
- *Auth used to work, now downloads fail with HTTP 401/403.* The cookie
  has expired (typical lifetime: 24–48h on nb.no). For the playwright MCP
  approach, repeat the network-request capture steps. For `capture_cookie.py`,
  re-run the script.
- *`mv: unable to remove target: Operation not permitted`.* You used a
  mounted workspace directory for `--out` and a same-named PDF already
  exists there. Switch to `--out /tmp/nbno_out` and copy afterward with
  `shutil.copy2`.
- *Wrapper times out / PDF not created.* Your `--start`/`--stop` range
  was too wide. The sandbox has a 45 s timeout; keep batches to ≤ 7 pages.
- *User pasted a `nb.no/items/<hash>` URL.* That hash is opaque; ask for
  the Referere/Sitere string (URN) instead. Don't guess.
- *User mentions `pliktavlevering` content.* ID prefix will be
  `pliktmonografi_...` or `pliktperiodika_...`. **Check `accessInfo` first**
  rather than guessing — some pliktmonografi items are open, some are FEIDE-
  licensed (`legalDepositLoginText` non-empty / `viewability: NONE`). The
  orchestrator does this automatically. The content search API will not work
  for these items regardless of auth; download and read pages directly.
- *Last page (back cover) always returns 403.* The final canvas of Bokhylla
  books has the ID suffix `_C2` and is systematically restricted at any width.
  Skip it silently — do not retry. The direct IIIF downloader already handles
  this automatically.
- *Manifest URL returns 404 (pliktmonografi item).* nb.no exposes two
  endpoints — `/items/<id>/manifest` (works for digibok) and
  `/iiif/URN:NBN:no-nb_<id>/manifest` (required for some pliktmonografi).
  The orchestrator tries both; if you're driving the API by hand, fall
  back to the second on 404.
- *OCR text looks scrambled / wrong characters.* The page image was
  silently downsampled by the IIIF resolver. Re-download with `--tiles
  always` and re-OCR. Also confirm `tesseract --list-langs` includes every
  language you requested — `nno` is missing from many sandboxes.
- *`ocrmypdf: command not found` between bash calls.* `~/.local/bin` is
  wiped in Cowork between calls. The orchestrator installs to
  `<--out>/_pylib/` and prepends `<--out>/_pylib/bin` to `PATH`
  automatically; if you're running ocrmypdf by hand, install with
  `pip install --target outputs/_pylib --break-system-packages ocrmypdf`
  and `export PATH="outputs/_pylib/bin:$PATH"
  PYTHONPATH="outputs/_pylib:$PYTHONPATH"` first.
- *Single ocrmypdf call times out at 45 s on a long book.* Use
  `scripts/ocr_chunked.py` in a `until … ; do :; done` loop — same OCR
  quality, per-page cache, makes progress every call.
- *Output PDF is huge (>500 MB).* The bloat is image encoding, not OCR.
  Run `scripts/shrink_pdf.py --pdf book.pdf` (or re-run `zotero_book.py`
  with `--shrink`) to JPEG-recompress the embedded images in place. The
  text layer is untouched, so this is a pure size optimisation — no need
  to re-OCR. **Never re-OCR to shrink** — it wastes minutes per book and
  the OCR text layer doesn't determine file size.
- *Chunked-OCR run silently produces a final PDF with broken pages.* A
  previous timeout left structurally-corrupt cache files that were
  skipped as "done". Newer `ocr_chunked.py` validates every cache file
  with `pikepdf.open` at startup and deletes any that fail; older runs
  may have shipped before that fix — delete `<pdf_dir>/.ocr_cache/` and
  re-run.
  