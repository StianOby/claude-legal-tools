# nbno — direct IIIF downloading

Supplementary to [`SKILL.md`](SKILL.md) Step 3. Read it for **whole-book
downloads** with the fast in-process downloader, for the **inline recipe**
(driving nb.no's IIIF API by hand, without the skill's scripts on disk), and
for the **mechanics** behind the resolver's gotchas.

## Fast path — `download_via_iiif()` (recommended for whole books)

For full-book `digibok_*` downloads, bypass `nbno_run.sh` entirely and use
the in-process IIIF downloader. It fetches pages directly via the IIIF API
with `ThreadPoolExecutor(12)` and is roughly **20× faster** than batching
through the CLI (~200 pages in ~10 s vs ~25 s startup + 1–2 s/page).

**Preferred: use the orchestrator's downloader directly.**
`scripts/zotero_book.py:download_via_iiif()` already handles every gotcha
listed in this file:

- tries both `/items/<id>/manifest` *and* `/iiif/URN:NBN:no-nb_<id>/manifest`
  (the first returns 404 for a substantial share of items — including plain
  `digibok_*`, e.g. `digibok_2014050705024` — so the fallback is routine, not
  an edge case; never hand-roll a single-endpoint manifest fetch);
- fetches every page at **half size** (`size="half"`, ~1100 px wide): the
  resolver serves full size and 1/2, 1/4, … of it, and silently
  downsamples any other width (asking for `1024,` on a page that lists
  `[1136, 568, …]` returns 568 px). Half size OCRs within 0.4 % of full
  size and needs a third of the requests (2026-10-23); `size="full"` gets
  the scan's own size;
- asks for the page in one request (`/full/pct:50/`) for public-domain
  items, and as `regionByPx` tiles scaled down by the server (2048-px
  regions returned at 1024, 4 a page) for everything else, which gets no
  single image above 1/4 size; a one-request page that comes back smaller
  than the canvas says is fetched again as tiles;
- skips the `_C2` back cover automatically;
- retries timeouts, dropped connections, 429 and 5xx on every request, and
  gives failed pages a second, slower pass;
- never drops a page: one that cannot be downloaded becomes a placeholder
  page saying so, **in its own place**, so every later page keeps its page
  number. It returns `{"pages": N, "missing": [PDF page numbers]}`, and
  `zotero_book.py` exits with status 3 and a warning when `missing` is not
  empty. Tell the user which pages are placeholders and re-run to fill
  them; never quote or cite from a placeholder page.

**Auth arguments are all optional.** `api.nb.no` authenticates by cookie, so
there is no bearer token to capture — `bearer=None` is the normal case and
`nbsso` alone is what FEIDE-licensed items need. Public-domain and Bokhylla
items need neither.

```python
import sys
sys.path.insert(0, "{SKILL_DIR}/scripts")
from zotero_book import download_via_iiif
from pathlib import Path
import tempfile

OUT_DIR = tempfile.mkdtemp()   # scratch; copy the final PDF to outputs (`SKILL.md` Step 4)

# Public domain, or Bokhylla from a Norwegian IP — no credentials at all.
result = download_via_iiif(
    canonical_id="digibok_2008051600041",
    out_pdf=Path(OUT_DIR) / "book.pdf",
    size="half",            # default; "full" only when asked for full resolution
    workers=12,
    public_domain=False,    # accessInfo.isPublicDomain: False goes straight to tiles
)

# FEIDE-licensed item, after the user has taken the digital loan (`SKILL.md` Step 0).
download_via_iiif(
    canonical_id="digibok_2014050705024",
    out_pdf=Path(OUT_DIR) / "book.pdf",
    nbsso="nbsso=<value>",   # bearer is not needed and defaults to None
    public_domain=False,
)
```

> **Anything that is not public domain gets no single image above 1/4
> size.** `/full/pct:25/` (~560 px) is served to Bokhylla and legal-deposit
> items; `/full/pct:50/` and larger return 403. Larger pages come only as
> tiles: any region, scaled by the server to at most 1024 px a side
> (`/0,0,2048,2048/1024,/0/default.jpg` works, `/0,0,2048,2048/full/` is
> 403). `zotero_book.py` reads `accessInfo.isPublicDomain` and goes straight
> to tiles when it is false (checked 2026-10-23).
>
> **Canvases within a book differ in size** (1562, 1571 and 2024 px wide in
> the same volume; left and right pages often differ), so sizes are asked
> for as a fraction of each canvas (`pct:50`), never as one width for the
> whole book. Smaller output comes from the shrink step after OCR
> (`SKILL.md` Step 4), not from asking for a narrower width.

**Driving the IIIF API by hand?** If `zotero_book.py` is not available (e.g.
you don't have the skill directory on disk), the full inline recipe lives in
[`iiif-download.md`](iiif-download.md), together with the mechanics behind
the resolver's silent downsampling, per-canvas tiling, per-page PDF DPI, and
the `_C2` back cover. **Read it before hand-rolling a download** — every one
of those gotchas yields a plausible-looking but wrong result (HTTP 200 with a
half-size image, black page bottoms, poster-sized PDF pages).

---

## Auth recap

`api.nb.no` authenticates by cookie — there is no bearer token. Public-domain
and Bokhylla items need no credential at all (Bokhylla needs a Norwegian IP, so run this in the local shell — SKILL.md **Routing**);
FEIDE-licensed items need `nbsso` plus an active digital loan. Anything that
is not public domain gets no single image above 1/4 size; larger pages come
as tiles. See [`auth.md`](auth.md) for the full table.

---

**Minimal inline recipe** (use only when calling `zotero_book.py` is not an
option — e.g. you don't have the skill directory on disk):

```python
import io, json, os, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
import tempfile
from pathlib import Path
from PIL import Image

ITEM_ID = "digibok_2008051600041"   # ← replace
NBSSO   = ""                        # ← "nbsso=<value>", FEIDE-licensed items only;
                                    #   leave empty for public domain / Bokhylla
OUT_DIR = Path(tempfile.mkdtemp()) / ITEM_ID   # scratch; copy the finished PDF to outputs
OUT_DIR.mkdir(parents=True, exist_ok=True)

# api.nb.no serves manifests to anyone and authenticates by cookie — there is
# no bearer token. Sending nbsso to the API too makes accessInfo reflect the
# user's own session.
REFERER = f"https://www.nb.no/items/URN:NBN:no-nb_{ITEM_ID}"
HDR_API = {"cookie": NBSSO} if NBSSO else {}
HDR_IMG = {"referer": REFERER}
if NBSSO:
    HDR_IMG["cookie"] = NBSSO

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

A4_HEIGHT_IN = 297 / 25.4  # ≈ 11.69 — anchor each page's height to A4
SCALE = 2                  # half size; 1 = full size

def fetch_tiled(base, info, scale=SCALE):
    # Read per-canvas dimensions from THIS page's info.json — not a cached
    # cover size. Content pages (~2336×3368) are larger than the cover
    # (~1877×2560); using one fixed canvas size would tile only the top-left
    # corner and leave the rest of every page black. Each tile is a region
    # of 1024*scale px that the server returns scaled to 1024.
    full_w, full_h = int(info["width"]), int(info["height"])
    step = 1024 * scale
    canvas = Image.new("RGB", (-(-full_w // scale), -(-full_h // scale)), "white")
    for y in range(0, full_h, step):
        for x in range(0, full_w, step):
            tw, th = min(step, full_w - x), min(step, full_h - y)
            size = "full" if scale == 1 else f"{-(-tw // scale)},"
            url = f"{base}/{x},{y},{tw},{th}/{size}/0/default.jpg"
            req = urllib.request.Request(url, headers=HDR_IMG)
            with urllib.request.urlopen(req, timeout=30) as r:
                canvas.paste(Image.open(io.BytesIO(r.read())).convert("RGB"),
                             (x // scale, y // scale))
    buf = io.BytesIO(); canvas.save(buf, "JPEG", quality=92); return buf.getvalue()

canvases = fetch_manifest()["sequences"][0]["canvases"]
entries = [(c["@id"].split("/")[-1], c["images"][0]["resource"]["service"]["@id"],
            int(c.get("width") or 0)) for c in canvases]

def fetch_page(idx_entry):
    idx, (name, base, canvas_w) = idx_entry
    if name.endswith("_C2"): return idx, None
    size = "full" if SCALE == 1 else f"pct:{100 // SCALE}"
    url = f"{base}/full/{size}/0/default.jpg"
    try:
        req = urllib.request.Request(url, headers=HDR_IMG)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code != 403: raise
        # Not public domain: tiles.
        info = _get_json(f"{base}/info.json", HDR_IMG)
        data = fetch_tiled(base, info)
    # Verify the one request wasn't silently downsampled.
    if canvas_w and Image.open(io.BytesIO(data)).size[0] < -(-canvas_w // SCALE) - 4:
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

Keep each Python call inside the bash tool's timeout (default 120 s; ask
for more, but calls have been cut off at about 178 s even with 600 s
requested). Do not count on scratch space or `~` surviving
to the next call in Cowork; keep anything you need later under the outputs
directory.

---

## The four gotchas, and why they exist

### 1. The resolver silently downsamples above its listed sizes

Asking for `/full/1024,/0/default.jpg` on an item whose `info.json` lists only
`[502, 251, …]` returns a **502-wide image with HTTP 200** and no warning.
Treating that as 1024-wide (e.g. assuming 300 DPI for OCR) produces unusable
output. The listed sizes are the scan's full size halved again and again
(`[1136, 568, 284, …]` for a 2272-px page), and they vary per canvas — left
and right pages, and the cover, differ. So ask for a fraction of each
canvas (`pct:50`), not one width for the whole book, **and** verify the
returned image's dimensions with PIL afterwards. Picking "the largest
listed width ≤ 1024" from one canvas, as the skill did before 1.5.0 unless
`--tiles always` was passed, gave ~560 px pages (~50 dpi on A4), and on
books whose canvases differ, every other page at full size.

### 2. Tiling must use *that canvas's* dimensions

Read `width`/`height` from the page's own `info.json`. Content pages
(~2336×3368) are larger than the cover (~1877×2560); reusing one cached
canvas size fetches only the top-left corner of every content page and leaves
the rest black.

### 3. PDF page sizing — embed per-page DPI or pages come out poster-sized

Two traps produce a wrong (huge) MediaBox:

- PIL's `Image.save(..., save_all=True)` applies a **single** resolution to
  every page and defaults to 72 DPI.
- img2pdf falls back to 96 DPI when a JPEG carries no DPI metadata, and
  **ignores its own `dpi=` argument** when the JPEG *does* carry metadata.

The fix, used by `zotero_book.py` and the recipe above: derive each page's DPI
from its real pixel height anchored to A4 (`dpi = round(height_px / (297/25.4))`),
bake it into each JPEG with `img.save(..., dpi=(dpi, dpi))`, then assemble with
img2pdf. Cover and content pages are scanned at different pixel heights, so a
single fixed DPI mis-sizes one or the other — always compute it per page.

### 4. Canvas ids are heterogeneous, and `_C2` is always restricted

A single book mixes `_C1`, `_I1`, `_0001`…, `_C3`, `_C2`. Always take ids from
the manifest; never construct them. The final canvas `_C2` (back cover) is
systematically restricted at any width — skip it silently, do not retry.

### Bonus: two manifest endpoints

`/catalog/v1/items/<id>/manifest` 404s for a substantial share of items and
`/catalog/v1/iiif/URN:NBN:no-nb_<id>/manifest` serves them instead. This is
**not** a `pliktmonografi`-only quirk — plain `digibok` items hit it too
(`digibok_2014050705024` is one). Always try both, in that order, on 404. A
single-endpoint fetch dies with `KeyError: 'sequences'` on the 404 body.
