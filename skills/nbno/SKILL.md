---
name: nbno
description: >
  Use this skill any time the user wants to download or work with material from
  Nasjonalbiblioteket (the Norwegian National Library, nb.no). Triggers include:
  links to nb.no or urn.nb.no, mentions of "Nasjonalbiblioteket", "Bokhylla",
  "FEIDE login to nb.no", "digibok", "digavis", "digifoto", "digitidsskrift",
  "digikart", "digimanus", or "digiprogramrapport"; URN identifiers like
  "URN:NBN:no-nb_digibok_..."; and natural-language requests such as "last ned
  boka fra nb.no", "fetch this old Norwegian newspaper", "get the PDF of this
  nb.no item", "log in to nb.no with FEIDE and download X", or "save these
  pages from Nasjonalbiblioteket". Covers books, newspapers, photos, journals,
  maps, manuscripts, sheet music, posters, and programme reports. Do NOT use
  for: Lovdata legal texts (use the lovdata skill), generic web scraping, or
  downloading content the user has no right to access.
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

> **pliktmonografi / pliktperiodika items: try no-auth first.**
> Legal-deposit material (`pliktmonografi_*`, `pliktperiodika_*`) is often
> accessible without any authentication — its access model appears to differ
> from Bokhylla in-copyright content. Always attempt Option A first for these
> IDs. Only escalate to Option B or C if the download returns an empty PDF or
> HTTP 401/403 errors.

### Option A — No auth (open content)

The default. Run `nbno_run.sh` without `--cookie`. Best when the user pasted
a URN for an old book, sheet music, public-domain photo, or any
`pliktmonografi_*` / `pliktperiodika_*` item. If the download fails with HTTP
401/403, fall back to Option B.

### Option B — Cookie capture (recommended for FEIDE / Bokhylla)

Use this when the item is in-copyright (Bokhylla) or the user mentions
FEIDE, BankID, Vipps, or "logged in."

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
this Python downloader. It fetches pages directly via the IIIF API with
`ThreadPoolExecutor(12)` and is roughly **20× faster** than batching through
the CLI (~200 pages in ~10 s vs ~25 s startup + 1–2 s/page). Use this path
any time the user needs more than ~7 pages of Bokhylla content.

Requires: `BEARER` (from the `authorization` header captured in Step 2 Option
B, steps 3–4) and `NBSSO` (the `nbsso=<value>` cookie from the same capture,
step 5 — just the `nbsso=...` portion of the full cookie string).

```python
import json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from PIL import Image

ITEM_ID = "digibok_2008051600041"   # ← replace
NBSSO   = "nbsso=<value>"           # ← just the nbsso=... part
BEARER  = "<token>"                 # ← bearer token for api.nb.no
OUT_DIR = f"/tmp/nbno_direct/{ITEM_ID}"
START   = 1     # 1-based, inclusive; None = first page
STOP    = None  # 1-based, inclusive; None = last page

MANIFEST_CACHE = f"/tmp/nbno_pages/{ITEM_ID}/manifest_urls.json"
REFERER = f"https://www.nb.no/items/URN:NBN:no-nb_{ITEM_ID}"
HDR_API = {"authorization": BEARER}
HDR_IMG = {"cookie": NBSSO, "referer": REFERER}

def fetch_canvas_urls():
    cache = Path(MANIFEST_CACHE)
    if cache.exists():
        return json.loads(cache.read_text())
    url = f"https://api.nb.no/catalog/v1/items/{ITEM_ID}/manifest"
    manifest = requests.get(url, headers=HDR_API, timeout=30).json()
    canvases = manifest["sequences"][0]["canvases"]
    entries = []
    for c in canvases:
        canvas_name = c["@id"].split("/")[-1]
        base = c["images"][0]["resource"]["service"]["@id"]
        entries.append({"canvas": canvas_name, "base_url": base})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(entries, indent=2))
    return entries

def download_page(entry, idx):
    if entry["canvas"].endswith("_C2"):          # back cover always 403
        return idx, None
    url = f"{entry['base_url']}/full/608,/0/default.jpg"  # 608px is the max allowed width
    r = requests.get(url, headers=HDR_IMG, timeout=30)
    if r.status_code == 403:
        return idx, None
    r.raise_for_status()
    path = f"{OUT_DIR}/page_{idx:04d}.jpg"
    Path(path).write_bytes(r.content)
    return idx, path

os.makedirs(OUT_DIR, exist_ok=True)
entries = fetch_canvas_urls()
total = len(entries)
start_i = (START or 1) - 1
stop_i  = (STOP  or total)
subset  = list(enumerate(entries[start_i:stop_i], start=start_i + 1))

print(f"Downloading pages {start_i+1}–{stop_i} ({len(subset)} total)...")
t0 = time.time()
results = {}
with ThreadPoolExecutor(max_workers=12) as pool:
    for idx, path in pool.map(lambda x: download_page(*x), subset):
        results[idx] = path
print(f"Done in {time.time()-t0:.1f}s")

pages = [Image.open(results[i]).convert("RGB")
         for i in sorted(results) if results[i]]
if pages:
    pdf_path = f"{OUT_DIR}/{ITEM_ID}.pdf"
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:])
    print(f"PDF: {pdf_path}")
```

The manifest canvas list is cached to `MANIFEST_CACHE` after the first fetch —
subsequent runs skip the round-trip. The back cover (`_C2`) is skipped
automatically. Keep each Python call under ~40 s; `/tmp` is wiped if the
sandbox restarts after a timeout.

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

## Important caveats — surface these to the user when relevant

- **Geo-restriction.** A large share of nb.no's collection (especially
  Bokhylla / in-copyright material) is nominally geo-restricted to Norwegian
  IP addresses. However, 403 errors from the sandbox are more commonly caused
  by wrong URL format (e.g. `pct:75` or `full` instead of a width like `608,`)
  or wrong auth headers than by actual IP-based blocking. With the correct
  setup — `608,` width + `nbsso` cookie + correct `referer` — sandbox
  downloads succeed from non-Norwegian IPs. **Check auth and URL format before
  assuming geo-restriction.** If errors persist after fixing those, then a
  Norwegian session cookie from the user's own network is likely required.
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
  For `pliktmonografi_*` / `pliktperiodika_*` items, **do not assume auth is
  required**: legal-deposit material is often accessible without a cookie.
  Retry with no `--cookie` flag before escalating to the FEIDE flow.
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
  `pliktmonografi_...` or `pliktperiodika_...`. **Try no-auth first** —
  legal-deposit items are often accessible without FEIDE. The content search
  API will not work for these items regardless of auth; download and read the
  pages directly.
- *Last page (back cover) always returns 403.* The final canvas of Bokhylla
  books has the ID suffix `_C2` and is systematically restricted at any width.
  Skip it silently — do not retry. The direct IIIF downloader already handles
  this automatically.
  