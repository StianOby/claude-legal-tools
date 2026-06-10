# nbno — inspecting pages, OCR, and shrinking

Read this **before reading pages, OCRing a book, or shrinking a PDF** (it is
referenced from `SKILL.md` after Step 3). It covers visual page reading, the
`tesseract` / `TESSDATA_PREFIX` setup, the resumable `ocr_chunked.py` flow, and
`shrink_pdf.py`. Several gotchas here cause scrambled OCR, poster-size pages,
or sandbox timeouts if skipped.

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

- **`TESSDATA_PREFIX` needs more than just `.traineddata` files.** Pointing
  it at a bare `/tmp` with a downloaded `nor.traineddata` works for plain
  `tesseract` but **fails for `ocrmypdf`**, which also needs the `configs/`
  and `tessconfigs/` directories and `pdf.ttf` from the system tessdata dir.
  Build a complete prefix dir by copying those alongside your language data:

  ```bash
  TESS_SYS=/usr/share/tesseract-ocr/4.00/tessdata   # adjust version if needed
  mkdir -p /tmp/myts
  cp /tmp/nor.traineddata /tmp/myts/                 # your downloaded lang(s)
  cp "$TESS_SYS"/eng.traineddata /tmp/myts/
  cp "$TESS_SYS"/osd.traineddata /tmp/myts/
  cp -r "$TESS_SYS"/configs /tmp/myts/
  cp -r "$TESS_SYS"/tessconfigs /tmp/myts/
  cp "$TESS_SYS"/pdf.ttf /tmp/myts/
  export TESSDATA_PREFIX=/tmp/myts
  ```

  Confirm the system path with `dpkg -L tesseract-ocr-eng | grep tessdata`
  if `4.00` doesn't exist. Plain `tesseract` (visual-check OCR below) only
  needs the `.traineddata` files, so a bare `TESSDATA_PREFIX=/tmp` is fine
  there — the extra files matter specifically for the `ocrmypdf` pipeline.
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

Run **one invocation per bash tool call** — exit code 0 means done, exit
code 2 means partial (call it again):

```bash
python {SKILL_DIR}/scripts/ocr_chunked.py \
    --pdf "$PDF" \
    --langs nor+nno \
    --time-budget 35 \
    --jobs 4
```

> **⛔ Do NOT wrap this in a single-call `until … ; do … ; done` loop.**
> A single `ocr_chunked.py` invocation can itself exceed the 45 s sandbox
> timeout (one page's OCR may run past the `--time-budget`, which is only
> checked *between* pages). If you put the loop inside one bash call, that
> first iteration blows the tool timeout and you never regain control to
> re-invoke — the loop never iterates.
>
> The correct Cowork pattern is to **call the bash tool repeatedly, once per
> iteration**, inspecting the exit code (and progress output) between calls:
> re-run on exit 2, stop on exit 0. The per-page cache survives between
> calls, so every invocation makes forward progress. Keep `--time-budget`
> safely under the tool timeout (35 is a good default for a 45 s limit).

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

## Shrinking the output — `shrink_pdf.py`

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
