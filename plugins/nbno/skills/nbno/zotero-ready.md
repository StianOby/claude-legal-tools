# nbno — Zotero-ready book workflow

Supplementary to [`SKILL.md`](SKILL.md). Load this file when the user asks
for a **Zotero-ready** book from nb.no, an **RDF with the PDF attached**,
"import this into Zotero with one click", "OCR and import this book", or
similar phrasing.

The end state is a paired `.pdf` + `.rdf` in the user's outputs folder;
dragging the `.rdf` into Zotero produces a Book item with full metadata,
an attached searchable PDF, and a single Web Link attachment titled
**"eBok (nb.no)"**. The Zotero **URL** metadata field is left blank by
design — the link lives only as the Web Link attachment.

Read `SKILL.md` first for the underlying nb.no concepts: the browser session
and access classification (Step 0), ID forms (Step 1), authentication options
(Step 2), the IIIF download paths and their gotchas (Step 3), and the
shrink/OCR helpers. This file documents the orchestrator on top of those.

**Auth in one line:** `--bearer` is optional and normally unavailable —
`api.nb.no` authenticates by cookie. Public-domain and Bokhylla items need no
credential (Bokhylla needs a Norwegian IP); FEIDE-licensed items need
`--nbsso` plus a digital loan the user takes in a browser.

## What the orchestrator does

`scripts/zotero_book.py` runs the full pipeline:

1. **Resolve the ID** — accepts URN form, canonical ID, or `digibok_…`.
2. **Fetch metadata** from `https://api.nb.no/catalog/v1/items/<URN>`. Pulls
   title, subtitle, creators (role detection: aut/cre → author, edt →
   editor, trl → translator), publisher, place, year, language, ISBN, and
   page count.
3. **Access pre-check.** Keys on `accessInfo.accessAllowedFrom` — the one
   access field that is not session-dependent. If it says `NB` (legal
   deposit) and no auth (nbsso/bearer/cookie) was passed,
   the script exits with a clear error instead of starting a doomed no-auth
   download. Override with `--force-auth` if you have reason to believe
   `accessInfo` is wrong. `accessInfo` is IP- and session-dependent, so the
   pre-check sends `--nbsso` when you supply it and sees what the user's own
   session sees. For a geo-gated item (`accessAllowedFrom: NORWAY` / `NB`),
   the script then asks the image resolver for one 1024 px page tile, the
   same request the download makes next. A 403 stops the run before
   anything is downloaded. On `NORWAY` that means the IP is not Norwegian.
   On `NB` it means the IP is not Norwegian, there is no active loan, or the
   cookie has expired. `--force-auth` skips the probe as well.
4. **Compute the basename**: `AUTHOR_TITLE_(YEAR)`, ASCII-folded
   (æ ø å → ae oe aa) and filesystem-safe. The first author's surname wins;
   falls back to the first organisation/contributor; with no creator at all
   (newspaper issues, anonymous works) the author part is simply omitted —
   `VG_(1868-1923)_1870.08.17_(1870)`. "n.d." stands in for a missing year.
5. **Download the full PDF.** Two paths:
   - **Fast IIIF (preferred for big books):** with `--nbsso` (`--bearer` is
     optional and rarely available) the in-process
     `ThreadPoolExecutor(12)` downloader takes over. It
     tries both manifest endpoints (`/items/…` 404s on many items,
     including plain digibok, and `/iiif/URN:…` serves them), reads
     `info.json` to pick a width the resolver will actually serve, verifies
     returned dimensions, and falls back to native-resolution
     `regionByPx` tiles (1024×1024) when the single-shot request is
     refused or silently downsampled. `--tiles always` forces tiled mode
     for every page; `--tiles never` disables fallback.
   - **Which path runs:** the IIIF downloader is the default and needs no
     credential for public-domain or (from Norway) Bokhylla items. The
     `nbno_run.sh` wrapper runs only when `--cookie` is given without
     `--nbsso`/`--bearer`, or with `--downloader wrapper`; `--tiles` and
     `--workers` have no effect on the wrapper, and the `[dl]` line says
     which path was chosen.
6. **Text layer.** Two sources, picked automatically (`--ocr auto`):
   - **nb.no's own OCR**, when the item serves it. nb.no OCRed its scans
     with ABBYY and publishes the result as ALTO XML, word by word, at
     `api.nb.no/catalog/v1/metadata/<URN>/altos`. **Public-domain books serve
     it to anyone; Bokhylla and FEIDE-licensed books answer 401 even with a
     logged-in session and an active loan** (verified 2026-09-29). Where it
     is available, `scripts/alto_text.py` writes every word as invisible text
     at its ALTO position and sets each page to the physical size ALTO
     records — the same thing nb.no's own "PDF with text" downloads contain.
     No Tesseract, so it takes seconds instead of minutes, and old type such
     as Fraktur comes out better. It is the same OCR nb.no's search uses, so
     it has the same errors (`§` often reads as `8`). Numbered pages without
     nb.no text are listed in the log; re-run with `--ocr tesseract` if any
     of them has text on it.
   - **Tesseract via `ocrmypdf`** for everything else (and with
     `--ocr tesseract`), language `nor` by default. Tesseract has no
     Nynorsk model; `nor` covers both written forms. When the sandbox lacks
     `nor`, it is fetched from tessdata_fast into `<--out>/_tessdata/` (see
     `reading-ocr.md`).
   - Auto-installs `ocrmypdf` to a persistent pip --target so the binary
     survives across Cowork bash invocations. By default the target is
     `<--out>/_pylib`; override with `NBNO_PYLIB=/some/path`. `~/.local/`
     is not used: Cowork wipes it between bash calls.
   - System package required: `tesseract-ocr`. The language model is
     fetched if missing. If it cannot be fetched, the script falls back to
     `eng` with a warning.
   - Uses `--skip-text` so already-OCRed pages aren't re-processed.
   - Pass `--no-ocr` to skip. This **also skips the shrink** unless you add
     `--shrink`. Shrinking first would leave 800 px pages that OCR badly. A
     book of more than about 30 pages will not OCR within one Cowork bash
     call (Tesseract does about 13 pages a minute, and calls die at about
     178 s). For those, download with `--no-ocr`, run
     `scripts/ocr_chunked.py` (one call per chunk), then
     `shrink_pdf.py --in-place`. The quality is the same, and the per-page
     cache makes it resumable.
7. **Emit the Zotero RDF** via `scripts/build_zotero_rdf.py`. The RDF
   references the PDF by its bare filename, so the .rdf and .pdf must sit
   side by side at import time.
   - Every item type is exported as a Zotero **Book**, newspapers and
     journals included: Zotero has no "newspaper issue" type, and
     `newspaperArticle` / `magazineArticle` describe a single article, not a
     whole issue. A newspaper issue gets its full date (`1870-08-17`) in the
     date field and the city (`Oslo`, not nb.no's `Norge;Oslo;;Oslo;;;;`)
     as place. Tell the user to change the item type in Zotero if they
     want something else; nothing else in the record depends on it.

## How to invoke it

```bash
OUT_DIR=$(mktemp -d)   # scratch; copy the PDF + RDF to outputs and share them (see SKILL.md Step 4)
# Open-content book, no auth (works for pre-1900 / pliktmonografi)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR"

# Bokhylla book from a Norwegian IP — no credential at all, but tiles-only.
# (No --cookie, so this runs the IIIF path; expect a "[dl] using fast IIIF"
# line. Before 2026-09 it silently ran the wrapper and ignored --tiles.)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --tiles always --resize 1024

# FEIDE-licensed book: nbsso only (no bearer), after the user has taken the
# digital loan in a browser. See SKILL.md Step 0.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2014050705024 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO" \
  --tiles always --resize 1024

# Same book, slower wrapper path (no in-process IIIF; --cookie selects it)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --cookie auto

# Skip OCR (useful for re-runs when the PDF is already searchable)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --no-ocr

# Big book: download with --no-ocr in one call (full resolution: --no-ocr
# skips the shrink too), then OCR in chunks.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO" \
  --no-ocr

# Then ONE of these per bash tool call, re-running while it exits 2
# (default budget 140 s; do not pipe it — the pipe hides the exit code):
python {SKILL_DIR}/scripts/ocr_chunked.py \
    --pdf "$OUT_DIR/Author_Title_(Year).pdf"

# After exit 0, shrink in its own call (keeps the filename the RDF uses):
python {SKILL_DIR}/scripts/shrink_pdf.py \
    --pdf "$OUT_DIR/Author_Title_(Year).pdf" --in-place

# In-copyright content where the resolver downsamples single-shot requests.
# --tiles always forces native-res tiles for every page (slower but correct).
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO" \
  --tiles always

# Same again, but recompress images after OCR — typical result is ~50%
# smaller with no OCR variance.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO" \
  --tiles always
```

New flags worth knowing about:

| flag | purpose |
| --- | --- |
| `--tiles {auto,always,never}` | IIIF fallback strategy. `auto` (default) tiles on 403 or silent downsample; `always` tiles every page; `never` disables fallback. **`always` ignores `--resize`** — tiles are fetched at each canvas's native resolution, so pages come out full-size whatever width you asked for. |
| `--ocr-jobs N`   | parallel jobs for ocrmypdf (default: half the usable CPUs, at most 4) |
| `--force-auth`   | skip the `accessInfo` pre-check and the page-tile probe; attempt the chosen path regardless |
| `--ocr {auto,nb,tesseract}` | where the text layer comes from. `auto` (default): nb.no's own OCR when the item serves it (public-domain books), else Tesseract. `nb`: the same, but warn loudly on fallback. `tesseract`: always OCR ourselves. |
| `--no-ocr`       | no text layer at all, and no shrink (unless `--shrink`), so `ocr_chunked.py` gets full-resolution pages afterwards |
| `--ocr-langs L`  | Tesseract languages (default `nor`; fetched from tessdata_fast when missing) |
| `--no-shrink`    | keep full-resolution page images. By default they are recompressed as JPEG after OCR (~60 MB for a 500-page book; lossy). Use only when the user asks for full resolution. |
| `--shrink-quality N` | JPEG quality for the shrink (default 60 — about 120 KB/page on text-heavy nb.no scans) |
| `--shrink-max-width N` | resize images wider than N px before re-encoding (default 800). 0 disables resizing. `--shrink-max-width 700 --shrink-quality 50` is ~25 % smaller but soft on small print; `900`/`70` gives more detail. |
| `--shrink-keep-master` | also keep the full-resolution OCRed PDF as `<basename>.original.pdf` (often 300–800 MB), so you can re-shrink with other settings without re-downloading |
| `--shrink-threshold-mb N` | with `--no-shrink`, print a hint when the output exceeds N MB (default 150; 0 disables) |

Output:

```
$OUT_DIR/
  AUTHOR_TITLE_(YEAR).pdf           # OCRed, searchable, shrunk
                                    # (unless --no-shrink)
  AUTHOR_TITLE_(YEAR).rdf           # Zotero RDF — drag-and-drop import
  AUTHOR_TITLE_(YEAR).original.pdf  # only with --shrink-keep-master:
                                    # full-resolution OCRed master
```

The `.original.pdf` exists only if you asked for it. It is never referenced
by the RDF; once the user is happy with the shrunk PDF, delete it to free
300–800 MB.

## Sandbox notes

- **Plan for about 170 s per bash call.** The default timeout is 120 s.
  Request the 600 s maximum anyway, but calls have been cut off at about
  178 s with 600 s requested. Downloads fit: a 173-canvas tiled book took
  about 40 s, and a 424-page book about 105 s. Tesseract OCR of a whole
  book does not fit. Use `--no-ocr` for the download call, then
  `ocr_chunked.py` (budget ≤ 150 s) and `shrink_pdf.py --in-place`.
  `nohup … &` does **not** survive the call returning: the process is
  killed and its log stays empty, so never background-and-poll.
- **Sandbox timeouts may keep work running in the background.** When a
  bash call reports `Command timed out after 45000ms`, the killed Python
  process can still flush files to disk for several seconds after control
  returns. Two consequences:
  1. Resumable batches must re-enumerate cache state on every invocation,
     not trust the previous call's reported counts. `ocr_chunked.py` does
     this correctly (it `glob`s `ocred/` fresh on every call).
  2. The flushed files can be structurally corrupt (e.g. tesseract killed
     mid-write yields a PDF whose pages tree has no `/Kids`). The
     `pikepdf.open` validation pass at the top of every `ocr_chunked.py`
     run detects and deletes these, so the next batch regenerates them
     instead of carrying broken pages through to the final merge.
- **Persistent installs.** `pip --user` writes to `~/.local/`, which Cowork
  wipes between bash invocations. Both `zotero_book.py` and `ocr_chunked.py`
  install dependencies (ocrmypdf, pikepdf) via `pip install --target` into
  `<--out>/_pylib/` instead, which lives under the workspace and survives
  across calls. `nbno_run.sh` does the same for the `nbno` CLI. Override
  the target with `NBNO_PYLIB=/some/abs/path` if you want a shared install
  across runs. The bin dir (`<target>/bin/`) is prepended to `PATH` and
  the target itself to `PYTHONPATH` automatically.
- ocrmypdf requires Tesseract at the system level. The Norwegian model has
  been missing in Cowork sandboxes, which ship only `eng`/`osd`, and there
  is no root to install it. `tesseract_preflight()` fetches `nor` into
  `<--out>/_tessdata/` and sets `TESSDATA_PREFIX`. Keep that dir like
  `_pylib/`. On the user's own machine, install
  `apt-get install tesseract-ocr tesseract-ocr-nor` (Debian/Ubuntu) or
  `brew install tesseract-lang` (macOS).
- **Windows users: run the orchestrator under WSL2**, not native Windows.
  `zotero_book.py`'s wrapper fallback shells out to `bash`/`nbno_run.sh`,
  the auto-install passes `--break-system-packages` (a PEP 668 flag
  rejected by Windows pip), and the apt language packs above don't exist
  on native Windows. Under WSL2 (Ubuntu) the Linux instructions apply
  unchanged. If WSL2 is not available, the **only** native-Windows path
  that works is the fast IIIF route with `--nbsso --no-ocr` and
  OCR done separately afterwards.
- The RDF and PDF must arrive in the same folder for Zotero's import to find
  the attachment. The orchestrator always writes them together in `--out`.

## Customising the metadata

If you need to tweak the fetched metadata before the RDF is written (e.g.
correct an editor that nb.no flagged as author), the recommended pattern is
to call the orchestrator with `--no-ocr` and inspect the printed metadata,
then re-run `build_zotero_rdf.py` directly against a hand-edited JSON dump:

```bash
python -c "
from zotero_book import normalise_id, fetch_nb_metadata, normalize_metadata
import json, dataclasses
book = normalize_metadata(fetch_nb_metadata(normalise_id('digibok_2008051600041')))
d = dataclasses.asdict(book)
d['creators'] = [dataclasses.asdict(c) for c in book.creators]
print(json.dumps(d, indent=2, ensure_ascii=False))
" > book.json

# Edit book.json by hand, then:
python {SKILL_DIR}/scripts/build_zotero_rdf.py \
  --book-json book.json \
  --pdf-filename Author_Title_(Year).pdf \
  --nb-url https://www.nb.no/items/URN:NBN:no-nb_digibok_2008051600041 \
  --out Author_Title_(Year).rdf
```

## Troubleshooting (Zotero-specific)

- *Zotero imports the book entry but not the PDF.* The .rdf must be in the
  same folder as the .pdf at import time. Drag the .rdf (not the .pdf) into
  Zotero. If you move the files between steps, redo the move so both end up
  paired again.
- *"Web Link" attachment shows up but the title is the URL.* You're running
  an older Zotero. Newer versions read the `dc:title` of the linked-URL
  attachment correctly. Workaround: edit the attachment title in Zotero
  after import.
- *Norwegian characters look garbled in author names.* The .rdf is always
  UTF-8; the issue is usually that the metadata source is stale. Re-run with
  `--no-ocr` to refresh from the nb.no API and re-emit the .rdf.
- *`ocrmypdf` complains about missing Norwegian data.* The automatic fetch
  failed; the log says why, for example no network to github.com. Install
  `tesseract-ocr-nor`, or fetch the model by hand as in `reading-ocr.md`.
- *Cookies expire mid-download.* Re-read the cookie (`SKILL.md` Step 0 step 7
  with the browser, or re-copy `nbsso` from DevTools) and re-run. If the item is
  FEIDE-licensed, check the digital loan is still active before blaming the
  cookie — loans are time-limited too.
- *Every page 403s although the login is fine.* Geo, not auth. For
  geo-gated items `zotero_book.py` now stops before downloading with `nb.no
  refused a page tile`, and `scripts/geo_check.py --id <id>` shows the same
  probe. On a `NORWAY` item the IP is the problem, so don't retry.
