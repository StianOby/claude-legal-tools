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

doc = fitz.open("<path to the PDF>")   # e.g. "$OUT/<item>.pdf" from the download step
page = doc[0]  # 0-based index; canvas N = index N-1
mat = fitz.Matrix(1, 1)  # 1× scale → approx 1652 × 2272 px from a --resize 75 PDF
pix = page.get_pixmap(matrix=mat)
pix.save("<WORK>/page_01.png")   # WORK = a mktemp -d scratch dir
```

Then use the Read tool on that PNG. Rendering at 1× from a
`--resize 75` PDF gives approximately 1652 × 2272 px, which stays within
the Read tool's ~2000 px limit. Do **not** use `fitz.Matrix(1.5, 1.5)` or
higher from a 75%-resize PDF — the result (~2479 × 3409 px) exceeds the
limit. If 1× images are still too large, resize with PIL before saving:

```python
from PIL import Image
img = Image.open("<WORK>/page_01.png")
img = img.resize((img.width // 2, img.height // 2))
img.save("<WORK>/page_01_small.png")
```

### OCR via tesseract (if needed)

OCR is possible but requires extra setup. Only use it when you need
machine-readable text rather than a visual check.

- **The Norwegian model is often missing, and the scripts fetch it.** Cowork
  sandboxes have shipped with only `eng` and `osd`, and `apt-get` fails
  there (no root). `tesseract_preflight()` in `zotero_book.py` and
  `ocr_chunked.py` handles this: it downloads `nor.traineddata` from
  `github.com/tesseract-ocr/tessdata_fast`, puts it in `<out>/_tessdata/`
  beside `_pylib/` together with the system tessdata dir's models,
  `configs/`, `tessconfigs/` (when present) and `pdf.ttf`, and sets
  `TESSDATA_PREFIX` to it. Later calls reuse that dir. Do not build a
  prefix by hand for the scripts. Codes that cannot be fetched are dropped
  with a warning. If none of the requested codes is available, the scripts
  fall back to `eng`. If even `eng` is missing, they exit with an install
  hint.
- **There is no Nynorsk model.** Tesseract ships only `nor`, which covers
  both written forms. There is no `nno` model and no `tesseract-ocr-nno`
  package. The default is `nor`.
- **Running `tesseract` by hand without `nor`:** plain `tesseract` needs
  only the `.traineddata` file, so
  `TS=$(mktemp -d); curl -sLo "$TS/nor.traineddata" https://github.com/tesseract-ocr/tessdata_fast/raw/main/nor.traineddata`
  plus `TESSDATA_PREFIX="$TS"` is enough. `ocrmypdf` also needs
  `configs/` and `pdf.ttf` in the same dir. The system dir is the path in
  the first line of `tesseract --list-langs` (e.g.
  `/usr/share/tesseract-ocr/4.00/tessdata`). Copy whatever exists there, and
  expect `tessconfigs/` to be missing on some installs. Scratch dirs (`/tmp`) are wiped
  between calls in Cowork, so redo this in the same call.
- Use `--psm 6` (uniform block of text) rather than `--psm 1` (the OSD
  model may not be available).
- Process one page per bash call to stay within the sandbox timeout.

### OCR for whole books — `ocr_chunked.py`

`scripts/ocr_chunked.py` is a resumable wrapper around ocrmypdf for books
whose OCR does not fit one bash call. That is most books: on a 2-vCPU
Cowork sandbox Tesseract manages about **13 pages a minute**, so a 400-page
book takes about 30 minutes over roughly 12 calls. Its input must be an
unshrunk PDF (bitonal pages OCR worse): `zotero_book.py --no-ocr` leaves
the pages unshrunk for this reason.

1. Split input into per-page PDFs (cached under
   `<pdf_dir>/.ocr_cache/<stem>/<hash>/pages/`).
2. OCR each page with `ocrmypdf --skip-text` (full quality — same preprocess,
   deskew, optimise as a one-shot run), cached under `…/ocred/`.
3. Stop launching new pages when the time budget expires; exit with code 2
   (partial). At most `--jobs` pages are in flight at a time, so one call
   lasts about `--time-budget` plus the slowest page still running — not
   until the whole book is done.
4. On the call that finishes the last page, merge with pikepdf and exit 0.

Run **one invocation per bash tool call**. Exit code 0 means done, and 2
means partial, so call it again. Exit code 1 means no page could be OCRed
in this call. The script prints ocrmypdf's last error; fix that error
instead of re-running.

```bash
python {SKILL_DIR}/scripts/ocr_chunked.py --pdf "$PDF"
```

The defaults are `--langs nor` and `--time-budget 140`. **Keep the budget
at about 150 s or below.** Cowork has cut a bash call off at about 178 s
even when a 600 s timeout was requested. Still request a long tool timeout (e.g.
600000 ms) so the default one does not cut the call off first.

**Do not pipe it through `tail` or `head`.** Its output is a handful of
lines, and a pipe replaces the script's exit code with `tail`'s: a failed
or partial run then reports 0. If you must pipe, read `${PIPESTATUS[0]}`.

**After exit 0, shrink.** The chunked flow works on unshrunk pages, so the
merged PDF is ~100 MB for 400 pages. Run this in its own bash call:
`python {SKILL_DIR}/scripts/shrink_pdf.py --pdf "$PDF" --in-place` (add
`--mode grey` if the user wants grey tones kept). It takes about 15 s per
100 pages. `--in-place` keeps the filename the Zotero RDF points at.

Leave `--jobs` at its default (half the usable CPUs, at most 4 — 1 on a
2-vCPU sandbox). Each worker runs Ghostscript plus multi-threaded Tesseract;
more workers than that thrash the CPU (a 2-vCPU sandbox with `--jobs 4`
went from ~4 s to ~24 s per page, with complete stalls).

> **⛔ Do NOT wrap this in a single-call `until … ; do … ; done` loop.**
> The loop would have to finish inside one bash call's timeout, which is
> the very limit the chunking exists to get around; when it runs out, you
> lose control mid-loop with no report of how far it got.
>
> The correct Cowork pattern is to **call the bash tool repeatedly, once per
> iteration**, inspecting the exit code (and progress output) between calls:
> re-run on exit 2, stop on exit 0 or 1. The per-page cache survives
> between calls, so every invocation makes forward progress. The budget is
> checked only *between* pages, so a call lasts the budget plus the slowest
> page still running. That is why the budget has to stay under the ~178 s
> cut-off and not at it.

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

An unshrunk book is ~250 KB a page at half size (several hundred MB at
full size). **Do not re-OCR to shrink** — the text layer is already
correct and re-OCR'ing wastes minutes per book. Instead, recompress the
embedded images:

```bash
python {SKILL_DIR}/scripts/shrink_pdf.py --pdf book.pdf [--mode grey]
```

Modes, measured on three law books (1907, 1964, 1997) on 2026-10-23:

| `--mode` | text pages | KB/page | 400 pages | use for |
| --- | --- | --- | --- | --- |
| `bitonal` (default) | black and white, CCITT G4 (lossless), scaled up 2× from half size | ~60 | ~25 MB | everything, unless grey tones matter |
| `grey` | greyscale JPEG q60 at the downloaded size | ~200 | ~80 MB | pencil notes, stamps, illustrations the user cares about |
| `jpeg` | JPEG q60 at 800 px (the pre-1.5 default) | ~110 | ~45 MB | only if asked; soft on small print |

How `bitonal` works:

- **Thresholding is adaptive** (Sauvola: each pixel against its own
  ~2.7 mm surroundings), so yellowed paper, uneven light and the shadow
  near the spine come out white, and faint print stays black. A global
  threshold fails on exactly those old pages.
- **Picture pages stay JPEG.** A page where more than 1 % of the ~11 mm
  blocks are mostly mid-grey (covers, photos, marbled endpapers) is kept
  as a greyscale JPEG, or colour for colour covers. Text, line drawings,
  maps and tables have mid-grey only at the edges of strokes and go
  bitonal. The outermost blocks are ignored, as old scans have a dark edge.
- **Pages below 100 dpi stay JPEG**: thresholding nb.no's quarter-size
  pages (~70 dpi) makes letters blotchy.
- **What it loses:** grey tones on text pages. Pencil underlining turns
  into solid black lines, stamps into outlines, and a small photo on a text
  page (under 1 % of the page) turns into black and white. Say so when you
  deliver the PDF if the book has annotations; offer `--shrink-mode grey`.
- **Not JBIG2.** JBIG2 would be ~30 % smaller still, but needs the
  jbig2enc program, which neither Cowork nor Windows has and which has to
  be built from source. Its lossy mode can swap similar characters (the
  Xerox 6/8 case), which a legal source cannot risk. G4 needs only Pillow.

This walks each page's image XObjects and replaces the streams. The OCR
text layer, page tree and bookmarks are untouched. 1-bit images are
skipped, so running it twice leaves bitonal pages alone. It takes about
15 s per 100 pages.

**Probe-and-extrapolate.** Before each run, `shrink_pdf.py` recompresses
one middle page and prints the estimated total output size
(`page × n_pages × 0.95`). The "halve dimensions, halve size" heuristic
falls apart for typographic detail, so always trust the probe rather
than a guess. Pass `--probe-only` to print just the estimate and exit
without writing.

**Never overwrites the input by default.** Output goes to a sibling
`<stem>_<mode>.pdf` (the filename encodes the settings). Re-encoding an
already-shrunk file compounds JPEG artefacts, so leaving the unshrunk
master in place lets you experiment with settings non-destructively. Use
`--in-place` to overwrite.

`zotero_book.py` runs this step by default after OCR (`--shrink-mode`,
`--shrink-quality`). It rewrites the PDF in place because the Zotero RDF
points at the canonical filename, and keeps no unshrunk copy unless you
pass `--shrink-keep-master` or OCR failed (saved as
`<basename>.original.pdf`). `--no-shrink` skips the step; the orchestrator
then prints a hint if the PDF exceeds `--shrink-threshold-mb` (default
150).

## Canvas numbers vs printed pages

> **Determine the canvas-to-printed-page offset before targeting a range.**
> `--start`/`--stop` refer to IIIF canvas numbers (1-based sequence), not
> necessarily printed page numbers. On a first run, download canvases 1–7
> and inspect the page footer or header text (e.g. an InDesign filename
> suffix like `...indd 5` on canvas 5 confirms an offset of zero). Once the
> offset is known, calculate the correct canvas numbers before requesting a
> specific printed-page range.
