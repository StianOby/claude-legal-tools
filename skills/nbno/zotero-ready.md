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

Read `SKILL.md` first for the underlying nb.no concepts: ID forms (Step 1),
authentication options (Step 2), the IIIF download paths and their
gotchas (Step 3), and the shrink/OCR helpers. This file documents the
orchestrator on top of those.

## What the orchestrator does

`scripts/zotero_book.py` runs the full pipeline:

1. **Resolve the ID** — accepts URN form, canonical ID, or `digibok_…`.
2. **Fetch metadata** from `https://api.nb.no/catalog/v1/items/<URN>`. Pulls
   title, subtitle, creators (role detection: aut/cre → author, edt →
   editor, trl → translator), publisher, place, year, language, ISBN, and
   page count.
3. **Access pre-check.** Inspects `accessInfo.viewability` and
   `accessInfo.legalDepositLoginText` from the catalog response. If either
   signals FEIDE/Bokhylla restriction and no auth (bearer/nbsso/cookie) was
   passed, the script exits with a clear error instead of starting a doomed
   no-auth download. Override with `--force-auth` if you have reason to
   believe `accessInfo` is wrong.
4. **Compute the basename**: `AUTHOR_TITLE_(YEAR)`, ASCII-folded and
   filesystem-safe. The first author's surname wins; falls back to the first
   organisation/contributor; "Unknown" / "n.d." as last resort.
5. **Download the full PDF.** Two paths:
   - **Fast IIIF (preferred for big books):** with `--bearer` + `--nbsso`
     the in-process `ThreadPoolExecutor(12)` downloader takes over. It
     tries both manifest endpoints (`/items/…` and `/iiif/URN:…`), reads
     `info.json` to pick a width the resolver will actually serve, verifies
     returned dimensions, and falls back to native-resolution
     `regionByPx` tiles (1024×1024) when the single-shot request is
     refused or silently downsampled. `--tiles always` forces tiled mode
     for every page; `--tiles never` disables fallback.
   - **`nbno_run.sh` fallback:** any time `--bearer`/`--nbsso` aren't given.
     Honours `--cookie` if Bokhylla auth is needed.
6. **OCR with `ocrmypdf`**, language pack `nor+nno` by default.
   - Auto-installs `ocrmypdf` to a persistent pip --target so the binary
     survives across Cowork bash invocations. By default the target is
     `<--out>/_pylib`; override with `NBNO_PYLIB=/some/path`. `~/.local/`
     would be wiped between bash calls and is not used.
   - System packages required: `tesseract-ocr`, `tesseract-ocr-nor`, and
     ideally `tesseract-ocr-nno`. The `nno` pack is missing in some Cowork
     sandboxes — `tesseract_preflight()` auto-degrades to `nor` and warns.
   - Uses `--skip-text` so already-OCRed pages aren't re-processed.
   - Pass `--no-ocr` to skip. For books too big for the 45 s sandbox, use
     `scripts/ocr_chunked.py` separately after the download — same quality,
     resumable per-page cache.
7. **Emit the Zotero RDF** via `scripts/build_zotero_rdf.py`. The RDF
   references the PDF by its bare filename, so the .rdf and .pdf must sit
   side by side at import time.

## How to invoke it

```bash
# Open-content book, no auth (works for pre-1900 / pliktmonografi)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR"

# Bokhylla book with the fast IIIF path (captured via playwright MCP / capture_cookie.py)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --bearer "$BEARER" \
  --nbsso "nbsso=$NBSSO" \
  --resize 1024

# Same book, slower wrapper fallback (no in-process IIIF)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --cookie auto

# Skip OCR (useful for re-runs when the PDF is already searchable)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --no-ocr

# Big book: download with --no-ocr in one call, then run the chunked OCR
# driver in a loop. Each call makes progress; cache survives between calls.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --bearer "$BEARER" --nbsso "nbsso=$NBSSO" \
  --no-ocr

until python {SKILL_DIR}/scripts/ocr_chunked.py \
    --pdf "$OUT_DIR"/AUTHOR_TITLE_*.pdf \
    --langs nor+nno --time-budget 35 --jobs 4; do :; done

# In-copyright content where the resolver downsamples single-shot requests.
# --tiles always forces native-res tiles for every page (slower but correct).
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --bearer "$BEARER" --nbsso "nbsso=$NBSSO" \
  --tiles always

# Same again, but recompress images after OCR — typical result is ~50%
# smaller with no OCR variance.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --bearer "$BEARER" --nbsso "nbsso=$NBSSO" \
  --tiles always --shrink
```

New flags worth knowing about:

| flag | purpose |
| --- | --- |
| `--tiles {auto,always,never}` | IIIF fallback strategy. `auto` (default) tiles on 403 or silent downsample; `always` tiles every page; `never` disables fallback. |
| `--ocr-jobs N`   | parallel jobs for ocrmypdf (default 4) |
| `--force-auth`   | skip the `accessInfo` pre-check; attempt the chosen path regardless |
| `--no-ocr`       | skip OCR (use with `ocr_chunked.py` afterwards for big books) |
| `--shrink`       | recompress embedded images as JPEG after OCR. Defaults target ~50 MB on a 350-page book. Copies the OCRed master to `<basename>.original.pdf` before rewriting in place. |
| `--shrink-quality N` | JPEG quality for `--shrink` (default 70 — tuned for ~143 KB/page on text-heavy nb.no scans) |
| `--shrink-max-width N` | resize images wider than N px before re-encoding (default 900). 0 disables resizing. |
| `--shrink-no-keep-master` | do not copy the OCRed master to `<basename>.original.pdf` before shrinking. Discouraged on first runs — re-shrinking an already-shrunk file compounds JPEG artefacts. |
| `--shrink-threshold-mb N` | print a hint suggesting `--shrink` when the output exceeds N MB (default 500; 0 disables) |

Output:

```
$OUT_DIR/
  AUTHOR_TITLE_(YEAR).pdf           # OCRed, searchable (shrunk if --shrink)
  AUTHOR_TITLE_(YEAR).rdf           # Zotero RDF — drag-and-drop import
  AUTHOR_TITLE_(YEAR).original.pdf  # only if --shrink: OCRed master,
                                    # kept so you can re-shrink with
                                    # different settings without
                                    # compounding JPEG artefacts.
```

**Delete the `.original.pdf` once the workflow is fully done.** It is
the OCRed master from before the lossy shrink — keep it only while you
might still want to try different `--shrink-quality` / `--shrink-max-width`
settings. Once you've imported the `.rdf` into Zotero and confirmed the
shrunk PDF is satisfactory, remove `<basename>.original.pdf` to free disk
space (typically 300–800 MB per book). It is never referenced by the RDF
and has no role in the final deliverable.

## Sandbox notes

- The Cowork bash sandbox has a 45-second per-call timeout. `zotero_book.py`
  is a single long-running Python process; for full Bokhylla books, split
  the work into a `--no-ocr` download call followed by `ocr_chunked.py`
  invoked in a loop until it exits 0.
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
- ocrmypdf requires Tesseract + Norwegian language packs at the system
  level. The Cowork sandbox typically has `tesseract-ocr-nor` but **not**
  `tesseract-ocr-nno`; `tesseract_preflight()` detects this and degrades
  `nor+nno` → `nor` with a warning. On the user's own machine, install
  both: `apt-get install tesseract-ocr tesseract-ocr-nor tesseract-ocr-nno`
  (Debian/Ubuntu) or `brew install tesseract-lang` (macOS).
- **Windows users: run the orchestrator under WSL2**, not native Windows.
  `zotero_book.py`'s wrapper fallback shells out to `bash`/`nbno_run.sh`,
  the auto-install passes `--break-system-packages` (a PEP 668 flag
  rejected by Windows pip), and the apt language packs above don't exist
  on native Windows. Under WSL2 (Ubuntu) the Linux instructions apply
  unchanged. If WSL2 is not available, the **only** native-Windows path
  that works is the fast IIIF route with `--bearer --nbsso --no-ocr` and
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
- *`ocrmypdf` complains about missing Norwegian data.* Install the
  language packs at the system level.
- *Cookies expire mid-download.* Follow `SKILL.md` Step 2's re-capture
  flow and re-run.
