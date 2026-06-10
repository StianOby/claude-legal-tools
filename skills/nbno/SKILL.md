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

Three auth paths — pick one based on the item:

- **Option A — No auth (open content).** The default. Run `nbno_run.sh`
  without `--cookie`. Best for old books, sheet music, public-domain
  photos/maps, and `pliktmonografi_*` / `pliktperiodika_*` items. On HTTP
  401/403, fall back to Option B.
- **Option B — Cookie capture (FEIDE / Bokhylla).** Use when the item is
  in-copyright or the user mentions FEIDE, BankID, Vipps, or "logged in."
  Capture via playwright MCP (Cowork) or `capture_cookie.py` (durable file).
- **Option C — Manual cookie file (legacy).** The user already has a cookie
  text file from DevTools; pass it with `--cookie <path>`.

> **⛔ STOP — before any fetch of authenticated content (Option B/C) in
> Cowork, confirm the user has an active nb.no session.** Ask: *"Have you
> logged in to nb.no recently? If not, please log in now at <https://nb.no>
> in your browser,"* and wait for confirmation. If you skip this and the user
> is not logged in, **every fetch silently fails** (JS-required page or blank
> session) with no reliable way to detect it after the fact — wasting
> significant debugging time.

> **📄 Read [`auth.md`](auth.md) before you capture or use any cookie.** It
> has the exact playwright-MCP capture steps, the `capture_cookie.py` setup,
> the cookie-file format, the bearer-vs-`nbsso` auth-scope rules, and the
> lighter `_nblb` tip. Don't improvise auth from memory — the header details
> are exact and a wrong one yields a blank session or a silently downsampled
> image (HTTP 200), which is slow to debug.

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

A4_HEIGHT_IN = 297 / 25.4  # ≈ 11.69 — anchor each page's height to A4

def fetch_tiled(base, info, tile=1024):
    # Read per-canvas dimensions from THIS page's info.json — not a cached
    # cover size. Content pages (~2336×3368) are larger than the cover
    # (~1877×2560); using one fixed canvas size would tile only the top-left
    # corner and leave the rest of every page black.
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

# Assemble with per-page DPI so the PDF gets a correct A4 MediaBox.
# Pitfalls: PIL's save_all applies ONE resolution to all pages (default 72
# DPI → poster-size pages); img2pdf falls back to 96 DPI unless the DPI is
# *embedded in each JPEG* (its own dpi= argument is ignored when metadata
# exists). So bake the per-page DPI into each JPEG, then let img2pdf assemble.
import img2pdf  # pip install --break-system-packages img2pdf
dpi_paths = []
for _, p in sorted(results.items()):
    if not p:
        continue
    im = Image.open(p).convert("RGB")
    dpi = round(im.height / A4_HEIGHT_IN)
    dp = p.replace(".jpg", ".dpi.jpg")
    im.save(dp, "JPEG", quality=95, dpi=(dpi, dpi))
    dpi_paths.append(dp)
pdf = OUT_DIR / f"{ITEM_ID}.pdf"
with open(pdf, "wb") as fh:
    fh.write(img2pdf.convert(dpi_paths))
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

## Inspecting pages, OCR, and shrinking — see [`reading-ocr.md`](reading-ocr.md)

Once you have the PDF you may need to **read specific pages** (to find the
canvas offset or verify a passage), **OCR** the whole book, or **shrink** a
bloated output.

> **📄 Read [`reading-ocr.md`](reading-ocr.md) before doing any of these.**
> It covers visual page reading (render to PNG + Read tool — preferred over
> OCR), the `tesseract` / `TESSDATA_PREFIX` setup (`ocrmypdf` needs more than
> the bare `.traineddata` files), the resumable `ocr_chunked.py` flow (**must
> be driven by repeated bash calls — never a single-call `until` loop**), and
> `shrink_pdf.py`. Skipping it leads to scrambled OCR, poster-size pages, or
> sandbox timeouts.

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
- **PDF page sizing — embed per-page DPI, or pages come out poster-sized.**
  When assembling page images into a PDF, two traps produce a wrong (huge)
  MediaBox: (1) PIL's `Image.save(..., save_all=True)` applies a single
  resolution to every page and defaults to 72 DPI; (2) img2pdf falls back to
  96 DPI when a JPEG carries no DPI metadata, and **ignores its own `dpi=`
  argument** when the JPEG *does* carry metadata. The fix used by
  `zotero_book.py` and the inline recipe: derive each page's DPI from its real
  pixel height anchored to A4 (`dpi = round(height_px / (297/25.4))`), bake it
  into each JPEG with `img.save(..., dpi=(dpi, dpi))`, then assemble with
  img2pdf. The cover and content pages of an nb.no book are scanned at
  different pixel heights, so a single fixed DPI mis-sizes one or the other —
  always compute it per page. Also, when tiling a page, read **that canvas's**
  `width`/`height` from its own `info.json`; reusing the cover's dimensions
  fetches only the top-left corner of every content page and leaves the rest
  black.
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
  Option B again (procedure in [`auth.md`](auth.md)).
- *Auth used to work, now downloads fail with HTTP 401/403.* The cookie
  has expired (typical lifetime: 24–48h on nb.no). For the playwright MCP
  approach, repeat the network-request capture steps; for `capture_cookie.py`,
  re-run the script (both detailed in [`auth.md`](auth.md)).
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
  language you requested — `nno` is missing from many sandboxes. (OCR setup
  detailed in [`reading-ocr.md`](reading-ocr.md).)
- *`ocrmypdf: command not found` between bash calls.* `~/.local/bin` is
  wiped in Cowork between calls. The orchestrator installs to
  `<--out>/_pylib/` and prepends `<--out>/_pylib/bin` to `PATH`
  automatically; if you're running ocrmypdf by hand, install with
  `pip install --target outputs/_pylib --break-system-packages ocrmypdf`
  and `export PATH="outputs/_pylib/bin:$PATH"
  PYTHONPATH="outputs/_pylib:$PYTHONPATH"` first.
- *Single ocrmypdf call times out at 45 s on a long book.* Use
  `scripts/ocr_chunked.py`, calling the bash tool **repeatedly** (one
  invocation per call; re-run on exit 2, stop on exit 0) — same OCR quality,
  per-page cache, makes progress every call. Do **not** wrap it in a
  single-call `until … ; do … ; done` loop: one invocation can itself exceed
  45 s, so the loop times out on its first iteration and never re-runs.
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
  