# nbno — direct IIIF downloading

Supplementary to [`SKILL.md`](SKILL.md) Step 3. Load this file only when you
need the **inline recipe** (driving nb.no's IIIF API by hand, without the
skill's scripts on disk) or the **mechanics** behind the four gotchas the
orchestrator already handles for you.

If `{SKILL_DIR}/scripts/zotero_book.py` is available, you do not need this
file: `download_via_iiif()` handles every gotcha below. Step 3 of `SKILL.md`
shows the call.

## Auth recap

`api.nb.no` authenticates by cookie — there is no bearer token. Public-domain
and Bokhylla items need no credential at all (Bokhylla needs a Norwegian IP);
FEIDE-licensed items need `nbsso` plus an active digital loan. Anything that
is not public domain is **tiles-only** — single-shot `/full/<w>,/` returns 403
at every width. See [`auth.md`](auth.md) for the full table.

---

**Minimal inline recipe** (use only when calling `zotero_book.py` is not an
option — e.g. you don't have the skill directory on disk):

```python
import io, json, os, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ITEM_ID = "digibok_2008051600041"   # ← replace
NBSSO   = ""                        # ← "nbsso=<value>", FEIDE-licensed items only;
                                    #   leave empty for public domain / Bokhylla
OUT_DIR = Path(f"/tmp/nbno_direct/{ITEM_ID}")
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

---

## The four gotchas, and why they exist

### 1. The resolver silently downsamples above its listed sizes

Asking for `/full/1024,/0/default.jpg` on an item whose `info.json` lists only
`[502, 251, …]` returns a **502-wide image with HTTP 200** and no warning.
Treating that as 1024-wide (e.g. assuming 300 DPI for OCR) produces unusable
output. Always GET `info.json` first and pick a width from `sizes[]`, **and**
verify the returned image's dimensions with PIL afterwards — the listed sizes
vary per canvas, so a width validated on the cover can still be downsampled on
a content page.

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
