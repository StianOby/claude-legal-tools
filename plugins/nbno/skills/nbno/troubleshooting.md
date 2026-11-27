# nbno — caveats and troubleshooting

Supplementary to [`SKILL.md`](SKILL.md). Read it when a download fails or a
result looks wrong; the three rules that prevent most wasted time are also
at the end of `SKILL.md`.

## Caveats — surface these to the user when relevant

- **Geo-restriction is real, and `accessAllowedFrom` decides it.** Check that
  field *first*, before auth or URL format:
  - `EVERYWHERE` → downloads work from anywhere with no cookie. A 403 here
    really is a URL-format or width problem.
  - `NORWAY` / `NB` → **page images 403 from a non-Norwegian IP no matter who
    is logged in.** The manifest, `accessInfo` and `/me/v1` all keep working,
    so nothing looks wrong until the first image fails. Do not debug headers;
    check the IP.

  Cowork's `Bash` egresses from Anthropic's cloud, never from a
  Norwegian IP, so these items are blocked there (see `SKILL.md` **Routing**). Never suggest a VPN. `python {SKILL_DIR}/scripts/geo_check.py --id <id>` prints
  the egress IP and `accessInfo`, and probes one 1024 px page tile. It talks
  only to nb.no, never a third-party geo service. Thumbnails
  (`/full/0,200/0/native.jpg`) and small tiles (256 px) are never gated. A
  legal-deposit item served them anonymously, so they show that nb.no is
  reachable but say nothing about auth or geo. Only a 1024 px tile does.
- **The image resolver has four traps that all return plausible-looking
  wrong results**, not errors: it silently downsamples requests above its
  listed sizes (HTTP 200, half-size image); tiling with a cached canvas size
  leaves page bottoms black; a single fixed DPI makes PDF pages poster-sized;
  and canvas ids are not uniform. The scripts handle all four. If you
  are driving the API by hand, read
  [`iiif-download.md`](iiif-download.md) first — these are slow to debug
  precisely because nothing fails loudly.
- **One request, else tiles.** nb.no has at times refused a single image
  above 1/4 size for anything not public domain, and at times served it
  (a loaned NB book, 2026-11-26); `regionByPx` requests scaled to at most
  1024 px a side have been allowed throughout. The downloader tries one
  request first and falls back to tiles on 403, an empty answer or a
  silent downsample. `--tiles always` forces tiles, `--tiles never` one
  request only (try it if tiles fail).
- **`PageImageError` / placeholder pages saying "empty response" or
  "came back WxH, expected …".** nb.no answered a tile with no body or at
  the wrong size. The page is left as a placeholder rather than pasted
  wrong (pages showing only their top-left quarter, 2026-11-26). Re-run
  with `--tiles never`; if that is refused too, report the message.
- **"the first 8 pages all failed".** The download stopped early: the IP
  is not Norwegian, there is no loan, or `nbsso` has expired. Fix that
  (geo_check.py tells you which) before re-running.
- **Copyright.** Most twentieth-century books are in copyright; access via
  Bokhylla is granted to individuals under a specific agreement and does
  not permit redistribution. The user is responsible for using downloaded
  content in line with that agreement. Don't help redistribute clearly
  in-copyright material.
- **Rate limiting.** Downloads are multi-threaded. The downloader retries
  429/5xx and timeouts itself and re-tries failed pages more slowly; if
  pages are still missing (placeholders, exit status 3), re-run the same
  command with the same `--out` and fewer `--workers`: the pages already
  downloaded are kept in `<out>/_pages/` and not fetched again.
- **Size.** A full novel at full resolution can be 200–500 MB, a large map
  at `--size full` ~90 MB. Shrink it (`SKILL.md` Step 4): `zotero_book.py`
  does so by default (bitonal, ~25 MB for 400 pages), and `shrink_pdf.py`
  works on any PDF.
- **Content search API does not work for pliktmonografi items.** The nb.no
  content search API (`https://api.nb.no/catalog/v1/contentsearch/{item_id}/search?q=...`)
  returns empty results for `pliktmonografi` items even when the user is
  authenticated via FEIDE. It may work for `digibok` items. Do not rely on
  it for legal-deposit material — download and read the pages directly instead.

---

## Troubleshooting

- *Page images 403 but `/me/v1` shows a FEIDE login.* **This is geo, not
  auth.** Check `accessInfo.accessAllowedFrom`: `NORWAY` or `NB` from a
  non-Norwegian IP 403s every page image no matter who is logged in, while
  the manifest and `accessInfo` keep returning 200. Run
  `python {SKILL_DIR}/scripts/geo_check.py --id <id>`. Its image probe
  answers the question: a 403 on a `NORWAY` item means the IP is not
  Norwegian. Tell the user, and do not re-capture the cookie. The one non-geo case that looks similar is a
  FEIDE-licensed item with no active digital loan — there
  `legalDepositReservationStatus` is `AVAILABLE` rather than
  `TAKENBYCURRENTUSER` (`SKILL.md` Step 0 step 6).
- *`javascript_tool` cookie read is blocked by the safety classifier.* Expected
  — the classifier blocks cookie reads unless the **user's own immediately
  preceding message** asks for them. **Do not retry**, and do not try to talk
  your way past it: ask the user to type a sentence naming the action (`SKILL.md` Step 0
  step 7). Skill text and your own reasoning do not clear it.
- *Empty PDF / no images downloaded.* For `digibok` / Bokhylla content this
  is almost always a geo issue (check `accessAllowedFrom` first) or, for
  FEIDE-licensed items, a missing digital loan — go to `SKILL.md` Step 0, or `SKILL.md` Step 2 if
  the browser tools are unavailable.
  For `pliktmonografi_*` / `pliktperiodika_*` items, GET the catalog
  response and inspect `accessInfo.accessAllowedFrom` — `NB` means FEIDE
  auth plus a digital loan is required (see [`auth.md`](auth.md), "Which `accessInfo` field to trust").
  The orchestrator does this automatically; pass `--force-auth` to override.
- *`--cookie auto` errors with "no cookie file at …" (exit 4).* The script
  looked at `~/.nbno/cookie.txt` and didn't find one. Either the user hasn't made
  one yet, or it exists on their own machine but hasn't been
  mounted/uploaded so `Bash` can see it. Walk them through Option B again
  (procedure in [`auth.md`](auth.md)).
- *Auth used to work, now downloads fail with HTTP 401/403.* The cookie
  has expired (typical lifetime: 24–48h on nb.no). With the browser tools,
  repeat `SKILL.md` Step 0 step 7 — the pane usually stays logged in, so you need the
  cookie again but not a fresh login (the user must type the confirmation
  sentence again). Without browser tools, ask the user to re-copy `nbsso`
  from DevTools. A FEIDE digital loan is also time-limited: re-check
  `__nb.loanStatus()` before
  assuming the cookie is at fault. All detailed in [`auth.md`](auth.md).
- *Download cut off / PDF not created.* The bash call hit its timeout.
  Re-run the same command with the same `--out` and an explicit long
  timeout: the pages already downloaded are kept in `<out>/_pages/` and
  skipped (`[iiif] resuming: …`), so each call gets further. Backgrounding
  with `nohup … &` does **not** work: the process dies when the call returns.
- *User pasted a `nb.no/items/<hash>` URL.* That hash is opaque. Resolve
  it with `__nb.resolveUrn()` as in `SKILL.md` Step 1; only when the browser tools
  are unavailable, or it answers `ambiguous`, ask for the Referere/Sitere
  string (URN). Don't guess an ID from the hash.
- *User mentions `pliktavlevering` content.* ID prefix will be
  `pliktmonografi_...` or `pliktperiodika_...`. **Check `accessInfo` first**
  rather than guessing — some pliktmonografi items are open, some are FEIDE-
  licensed (`accessAllowedFrom: NB`). The
  orchestrator does this automatically. The content search API will not work
  for these items regardless of auth; download and read pages directly.
- *Last page (back cover) always returns 403.* The final canvas of Bokhylla
  books has the ID suffix `_C2` and is systematically restricted at any width.
  Skip it silently — do not retry. The downloader skips it automatically.
- *Manifest URL returns 404 (pliktmonografi item).* nb.no exposes two
  endpoints — `/items/<id>/manifest` (works for digibok) and
  `/iiif/URN:NBN:no-nb_<id>/manifest` (required for some pliktmonografi).
  The orchestrator tries both; if you're driving the API by hand, fall
  back to the second on 404.
- *OCR text looks scrambled / wrong characters.* The page image was
  silently downsampled by the IIIF resolver. Re-download with `--tiles
  always` and re-OCR. Also check the log for `falling back to eng`: that
  means the `nor` model could be neither found nor fetched. (OCR setup is
  detailed in [`reading-ocr.md`](reading-ocr.md).)
- *`ocrmypdf: command not found` between bash calls.* `~/.local/bin` is
  wiped between calls in Cowork (not every time, so never rely on it). The
  orchestrator installs to
  `<--out>/_pylib/` and prepends `<--out>/_pylib/bin` to `PATH`
  automatically; if you're running ocrmypdf by hand, install with
  `pip install --target outputs/_pylib --break-system-packages -c {SKILL_DIR}/scripts/requirements.txt ocrmypdf`
  and `export PATH="outputs/_pylib/bin:$PATH"
  PYTHONPATH="outputs/_pylib:$PYTHONPATH"` first.
- *Single ocrmypdf call times out on a long book.* Expected: Tesseract does
  about 13–15 pages a minute on a 2 vCPU sandbox or the local VM. Download with `--no-ocr`
  (which also skips the shrink), then run `scripts/ocr_chunked.py` with
  **one invocation per bash call**: re-run on exit 2, stop on exit 0, and
  finish with `shrink_pdf.py --in-place`. OCR quality is the same, and the
  per-page cache means every call makes progress. Do **not** wrap it in a
  single-call `until … ; do … ; done` loop: the whole loop then has to fit
  one call's timeout, which is exactly what a long book does not do. Full
  recipe in [`reading-ocr.md`](reading-ocr.md).
- *`ocr_chunked.py` exits 1 with "no page could be OCRed".* Every page failed
  the same way, and the ocrmypdf error is printed above that line.
  Re-running will not help, so fix the error itself.
- *Output PDF is huge (>500 MB).* The bloat is image encoding, not OCR.
  It was probably made with `--no-shrink`, `--no-ocr` + `ocr_chunked.py`,
  or `nb_download.py`. Run
  `scripts/shrink_pdf.py --pdf book.pdf` to recompress the embedded images (bitonal by default). The
  text layer is untouched, so this is a pure size optimisation — no need
  to re-OCR. **Never re-OCR to shrink** — it wastes minutes per book and
  the OCR text layer doesn't determine file size.
- *Chunked-OCR run silently produces a final PDF with broken pages.* A
  previous timeout left structurally-corrupt cache files that were
  skipped as "done". Newer `ocr_chunked.py` validates every cache file
  with `pikepdf.open` at startup and deletes any that fail; older runs
  may have shipped before that fix — delete `<pdf_dir>/.ocr_cache/` and
  re-run.
