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

When the Zoteus MCP tools (`zotero_*`) are available, the same item can
instead go straight into the user's library: see **Direct import with
Zoteus** below. Unless the user has already said which they want, ask once:
an RDF file to drag into Zotero, or straight into their library.

**Whichever route, tell the user when the item ends up without its PDF** —
see **When the PDF is not attached**.

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
     including plain digibok, and `/iiif/URN:…` serves them) and fetches
     every page at **half size** (`--size half`, ~1100 px wide, ~145 dpi):
     one request per page for public-domain items, four server-scaled
     `regionByPx` tiles for the rest (nb.no gives them no single image
     above quarter size), and tiles wherever a single image is refused or
     silently downsampled. `--size full` fetches the scan's own size (12
     tiles a page, 3× the time); only when the user asks for full
     resolution. Half size OCRed within 0.4 % of full size on three law
     books (2026-10-23). `--tiles always` forces tiles for every page;
     `--tiles never` disables them.
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
   - Uses `--skip-text` so already-OCRed pages aren't re-processed, and
     `--output-type pdf` (a plain PDF; ocrmypdf's default PDF/A needs
     Ghostscript and extra pikepdf modules, and re-encodes the pages).
   - Pass `--no-ocr` to skip. This **also skips the shrink** unless you add
     `--shrink`: bitonal pages OCR worse than the downloaded ones. A
     book of more than about 30 pages will not OCR within one Cowork bash
     call (Tesseract does about 13 pages a minute, and calls die at about
     178 s). For those, download with `--no-ocr`, run
     `scripts/ocr_chunked.py` (one call per chunk), then
     `shrink_pdf.py --in-place`. The quality is the same, and the per-page
     cache makes it resumable.
   - If OCR fails, the run goes on (exit 5): the PDF is shrunk and
     delivered without a text layer, and the unshrunk PDF is kept as
     `<basename>.original.pdf` so the OCR can be retried without a new
     download (SKILL.md Step 4, **OCR failed**).
7. **Shrink** the page images with `scripts/shrink_pdf.py`
   (`--shrink-mode`, see the table below). The default, `bitonal`, turns
   text pages into sharp black and white (lossless CCITT G4, scaled up 2×
   from the half-size pages, ~60 KB a page) and keeps covers, photos and
   marbled endpapers as JPEG. `grey` keeps every page as a greyscale JPEG
   at the downloaded size (~200 KB a page) for books where grey tones
   matter: pencil notes, stamps, illustrations.
8. **Emit the Zotero RDF** via `scripts/zotero_rdf.py` (shared with other
   skills; the canonical copy is `shared/zotero-rdf/` in the repo). It also
   writes `<basename>.zotero.json`: the same item as Zotero JSON, for the
   Zoteus route. The RDF references the PDF by its bare filename, so the
   .rdf and .pdf must sit side by side at import time.
   - Every item type is exported as a Zotero **Book**, newspapers and
     journals included: Zotero has no "newspaper issue" type, and
     `newspaperArticle` / `magazineArticle` describe a single article, not a
     whole issue. A newspaper issue gets its full date (`1870-08-17`) in the
     date field and the city (`Oslo`, not nb.no's `Norge;Oslo;;Oslo;;;;`)
     as place. Tell the user to change the item type in Zotero if they
     want something else; nothing else in the record depends on it.

## How to invoke it

`NORWAY`/`NB` items run all of this in the local shell
(SKILL.md **Routing**): same commands with `<dir>/scripts/…` and
`--out <dir>/out`, after checking `command -v tesseract` — if it is missing,
add `--no-ocr` and tell the user the PDF has no text layer. `EVERYWHERE`
items stay in the cloud sandbox as below.

**Exit codes:** 0 done; 3 some pages are placeholders (re-run to fill them);
5 OCR failed — the PDF (without a text layer) and the RDF are still written,
and the unshrunk pages are kept as `<basename>.original.pdf`: tell the user,
try to fix the cause and retry from that copy (SKILL.md Step 4, **OCR
failed**); if it cannot be fixed, deliver and say the PDF is not searchable.

**Part of a book:** `--start N --stop M` (1-based canvas numbers, inclusive,
as in `nbno_run.sh`; not printed page numbers). The files get a
`_c<N>-<M>` suffix so a partial copy never overwrites the full book. The
Zotero record still describes the whole book — tell the user the PDF is an
excerpt.

```bash
OUT_DIR=$(mktemp -d)   # scratch; copy the PDF + RDF to outputs and share them (see SKILL.md Step 4)
# Open-content book, no auth (works for pre-1900 / pliktmonografi)
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR"

# Bokhylla book from a Norwegian IP — no credential at all. Not public
# domain, so pages come as tiles (the script decides; no flag needed).
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2009010704007 \
  --out "$OUT_DIR"

# FEIDE-licensed book: nbsso only (no bearer), after the user has taken the
# digital loan in a browser. See SKILL.md Step 0.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2014050705024 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO"

# Grey tones kept (pencil notes, stamps, illustrations): greyscale JPEG pages
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2009010704007 \
  --out "$OUT_DIR" \
  --shrink-mode grey

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

# Big book: download with --no-ocr in one call (--no-ocr skips the shrink
# too, so the OCR sees the downloaded pages), then OCR in chunks.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" \
  --nbsso "nbsso=$NBSSO" \
  --no-ocr

# Then ONE of these per bash tool call, re-running while it exits 2
# (default budget 140 s; do not pipe it — the pipe hides the exit code):
python {SKILL_DIR}/scripts/ocr_chunked.py \
    --pdf "$OUT_DIR/Author_Title_(Year).pdf"

# After exit 0, shrink in its own call (keeps the filename the RDF uses;
# add --mode grey if the book was fetched with --shrink-mode grey in mind):
python {SKILL_DIR}/scripts/shrink_pdf.py \
    --pdf "$OUT_DIR/Author_Title_(Year).pdf" --in-place
```

New flags worth knowing about:

| flag | purpose |
| --- | --- |
| `--size {half,full}` | IIIF page size. `half` (default): ~1100 px wide, ~145 dpi, enough for OCR and the bitonal shrink. `full`: the scan's own size, 3× the requests; only when the user asks for full resolution. |
| `--tiles {auto,always,never}` | IIIF tile strategy. `auto` (default): one request per page for public-domain items, tiles for the rest and wherever one request is refused or downsampled; `always` tiles every page; `never` disables tiles. |
| `--ocr-jobs N`   | parallel jobs for ocrmypdf (default: half the usable CPUs, at most 4) |
| `--force-auth`   | skip the `accessInfo` pre-check and the page-tile probe; attempt the chosen path regardless |
| `--ocr {auto,nb,tesseract}` | where the text layer comes from. `auto` (default): nb.no's own OCR when the item serves it (public-domain books), else Tesseract. `nb`: the same, but warn loudly on fallback. `tesseract`: always OCR ourselves. |
| `--no-ocr`       | no text layer at all, and no shrink (unless `--shrink`), so `ocr_chunked.py` gets the downloaded pages afterwards |
| `--ocr-langs L`  | Tesseract languages (default `nor`; fetched from tessdata_fast when missing) |
| `--shrink-mode {bitonal,grey,jpeg}` | `bitonal` (default): text pages as black-and-white CCITT G4, covers and photo pages as JPEG; ~25 MB for 400 pages. Faint pencil turns black and stamps become outlines. `grey`: greyscale JPEG at the downloaded size, ~80 MB for 400 pages — when the user wants grey tones kept. `jpeg`: the pre-1.5 shrink (JPEG at 800 px, soft on small print). |
| `--no-shrink`    | keep the downloaded page images as they are (~250 KB a page) |
| `--shrink-quality N` | JPEG quality for JPEG-encoded pages (default 60) |
| `--shrink-max-width N` | `--shrink-mode jpeg` only: resize images wider than N px (default 800; 0 disables) |
| `--shrink-keep-master` | also keep the unshrunk OCRed PDF as `<basename>.original.pdf` (~100 MB for 400 pages), so you can re-shrink with other settings without re-downloading. Kept anyway when OCR fails. |
| `--shrink-threshold-mb N` | with `--no-shrink`, print a hint when the output exceeds N MB (default 150; 0 disables) |

Output:

```
$OUT_DIR/
  AUTHOR_TITLE_(YEAR).pdf           # OCRed, searchable, shrunk
                                    # (unless --no-shrink)
  AUTHOR_TITLE_(YEAR).rdf           # Zotero RDF — drag-and-drop import
  AUTHOR_TITLE_(YEAR).zotero.json   # the same item for Zoteus; not for the user
  AUTHOR_TITLE_(YEAR).original.pdf  # only with --shrink-keep-master, or
                                    # when OCR failed: the unshrunk PDF
```

The `.original.pdf` is never referenced by the RDF. When OCR failed, it is
the copy to retry the OCR on; otherwise delete it once the user is happy
with the shrunk PDF. Give the user the `.pdf` and `.rdf` only.

The `.rdf` finds the PDF only when the two files sit in the same folder, so
always say this when you hand them over, in these words:

> Download both files into the same folder first, then drag the `.rdf` into
> Zotero from there. If you open the `.rdf` straight from this chat, Zotero
> imports the book without its PDF.

For a local-route book the two files are already together in
`<connected folder>/nbno/<id>/`. Say instead: "Drag the `.rdf` into Zotero
from `<that folder>`; the PDF next to it is attached automatically." If the
user would rather skip that step and the Zoteus tools are available, offer
the direct import below.

### A PDF over 30 MiB

The script prints `LARGE PDF:` when the PDF is over 30 MiB, the most
`SendUserFile` and `device_commit_files` take. The PDF then cannot leave the
cloud sandbox, so:

nb.no has no public PDF link, so Zoteus cannot fetch it either. With the
default bitonal shrink a book stays under the limit up to about 500 pages
(~25 MB for 400); `--shrink-mode grey` (~80 MB for 400 pages) and very long
books go over it.

- **A local-route book** (`NORWAY` / `NB`) is made in the connected folder
  already: it never needs to leave the sandbox. Tell the user to drag the
  `.rdf` into Zotero from `<connected folder>/nbno/<id>/`, or attach the PDF
  by path in the Zoteus route.
- **A book made in the cloud sandbox** (`EVERYWHERE`): offer to make it
  again on the user's computer, through the local route (SKILL.md
  **Routing**, step 2 — the same commands; the item is open to every IP, so
  only the place it is made changes). The PDF and `.rdf` then end up
  together in the connected folder. If the local route cannot run, deliver
  the `.rdf` alone and give the nb.no link: the user can download the book
  there and attach it to the item.

## Direct import with Zoteus

Use this route when the `zotero_*` tools are present and the user wants the
book straight in their library. Run `zotero_book.py` exactly as above first;
it writes `<basename>.zotero.json`, which holds `items` (the book), `web_link`
and `pdf`. Then:

1. `zotero_whoami`: is the Zotero desktop app reachable? If not, Zoteus
   writes through the cloud, which needs a Zotero API key; say so if it fails.
2. **Library.** The user's own library unless they name a group or a
   collection. For a group, take its numeric `library_id` from
   `zotero_groups` and pass it with `library_type: "group"`. Take collection
   keys from `zotero_list_collections` for the same library.
3. **Duplicates.** `zotero_search_items` with the ISBN when the item has
   one (it also finds copies entered by hand), otherwise the surname and a
   title word, with `itemType: "book"`. If an existing item
   looks like the same book, show it and ask before creating another.
4. **Ask before writing:** "Save *<title>* (<year>) to <library / collection>?"
5. `zotero_create_items` with the `items` array from the JSON unchanged (add
   `collections` if a collection was chosen). Note the new item's key.
6. **Web link:** `zotero_create_items` again with the `web_link` object, its
   `parentItem` set to that key. If Zoteus refuses it, say so and give the
   user the nb.no link. It is not worth retrying.
7. **PDF:** nb.no has no public PDF URL, so follow **Attaching a PDF that
   is only in the cloud** below. If that cannot be done, deliver the PDF as
   in SKILL.md Step 4 and follow **When the PDF is not attached**.
8. Report what was made: library, collection, Web Link yes/no, PDF yes/no.

## Attaching a PDF that is only in the cloud

Zoteus runs on the user's computer, so `zotero_attach_file` takes a file only
from a `url` it can download or a `path` on that computer. A PDF the script
made in the cloud sandbox gets there through the connected folder (verified
2026-10-21 with a 22 MB UNTS slice):

1. Load the tools with one ToolSearch call:
   `select:mcp__remote-devices__get_device_info,mcp__remote-devices__device_commit_files,mcp__remote-devices__device_request_folder_access`.
   If they are not there, follow **When the PDF is not attached**.
2. **Over 30 MB → stop here** and follow **When the PDF is not attached**:
   that is the copying cap.
3. Copy the PDF to `/mnt/user-data/outputs/` (`device_commit_files` takes
   files only from there, or a `fileUuid` from an earlier `SendUserFile`).
4. **Folder:** `get_device_info` → `connectedFolders`, which gives the real
   path on the user's computer (e.g. `C:\Users\…\Claude-legal-work`). With
   more than one, ask which. With none, ask the user which folder to connect
   (offer the folders you have seen exist, plus "another folder") and request
   exactly that one with `device_request_folder_access`; if they decline,
   follow **When the PDF is not attached**.
5. `device_commit_files` with `devicePath` = `<folder>\nbno\<base>.pdf`
   (the folder as `connectedFolders` spells it; the subfolder is created).
6. `zotero_attach_file` with `parent` = the item key, `path` = the path the
   commit reports under `written`, `title` "Full Text PDF".
7. Zotero stores its own copy, so the file in `<folder>\nbno\` is no
   longer needed. Do not delete it (deleting in the connected folder is off
   unless the user turns it on): tell the user it is there and can be
   deleted.

A local-route book is already in the connected folder
(`$HOME/mnt/<folder>/nbno/<id>/` in the local shell): skip steps 2–5 and
attach it with `path` = the same file under the folder's real path from
`get_device_info` (`<folder>\nbno\<id>\<file>`). The 30 MB cap does not
apply to it.

## When the PDF is not attached

The user must always learn that an item has no PDF, so they can add it
themselves. This applies when:

- a script prints a line starting `PDF NOT ATTACHED:`;
- the Zoteus route created the item but did not attach the PDF (step 7
  skipped, or `zotero_attach_file` failed);
- the `.rdf` reaches the user without its `.pdf` next to it, for example
  because `SendUserFile` refused a PDF over 30 MiB, or the PDF went to a
  different folder from the RDF. If the user says the item came in without
  its PDF, the usual cause is a `.rdf` opened straight from the chat.

Say it in the reply, not only in the log: which item, where the PDF is (the
outputs folder, `<connected folder>/nbno/<id>/`, or "not sent: too large"),
and how to add it: in Zotero, drag the PDF onto the item, or right-click
the item → *Add Attachment* → *Attach Stored Copy of File*. For the RDF
route, add that both files must be saved in the same folder **before**
dragging in the `.rdf`. Otherwise the import still works, but the PDF has to
be added by hand.

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

To correct the metadata (e.g. an editor that nb.no flagged as author), edit
the item in `<basename>.zotero.json`. It is Zotero's own JSON: `creators`
entries are `{creatorType, firstName, lastName}` or `{creatorType, name}`,
and field names are Zotero's (`title`, `edition`, `numPages`, `ISBN` …).
Then re-render the RDF. The Web Link is read from the JSON:

```bash
python {SKILL_DIR}/scripts/zotero_rdf.py \
  --item-json "$OUT_DIR/Author_Title_(Year).zotero.json" \
  --pdf-filename "Author_Title_(Year).pdf" \
  --out "$OUT_DIR/Author_Title_(Year).rdf"
```

For the Zoteus route, pass the edited `items` to `zotero_create_items`, or
fix the item afterwards with `zotero_update_item`.

## Troubleshooting (Zotero-specific)

- *Zotero imports the book entry but not the PDF.* The .rdf must be in the
  same folder as the .pdf at import time. Drag the .rdf (not the .pdf) into
  Zotero. If you move the files between steps, redo the move so both end up
  paired again — or add the PDF to the imported item by hand.
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
