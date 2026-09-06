---
name: nbno
description: >
  Use any time the user wants to download or work with material from
  Nasjonalbiblioteket (Norwegian National Library, nb.no). Triggers: links to
  nb.no or urn.nb.no; mentions of "Nasjonalbiblioteket", "Bokhylla", "FEIDE
  login to nb.no", "digibok", "digavis", "digifoto", "digitidsskrift",
  "digikart", "digimanus", "digiprogramrapport"; URN ids like
  "URN:NBN:no-nb_digibok_..."; requests like "last ned boka fra nb.no", "log
  in to nb.no with FEIDE and download X".
  Covers books, newspapers, photos, journals, maps, manuscripts, sheet music,
  posters, programme reports. ALSO use for "Zotero-ready" requests
  ("Zotero-ready book", "Zotero RDF for nb.no", "OCR and import this book")
  — triggers the PDF + OCR + Zotero RDF workflow.
  Uses the Cowork built-in browser for FEIDE session capture when available;
  falls back to a manual DevTools cookie.
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
- **Auth**: Prompt every time. Before each run, ask the user which auth path
  in **Step 2** to take. The default cookie location is `~/.nbno/cookie.txt`
  when the user keeps a durable one.

## Prerequisites

- **`{SKILL_DIR}`** — replace this placeholder with the path printed in
  "Base directory for this skill:" at the top of your context.
- **`nbno` CLI** — the wrapper installs it automatically on first run via
  `pip install --break-system-packages nbno`. If auto-install fails, run
  that command manually before proceeding.
- **Built-in browser (optional, Cowork only).** If the `mcp__Claude_Browser__*`
  tools are present, **Step 0** uses them for the session check, item
  classification and cookie capture. They may be *deferred* — load them with
  one `ToolSearch` call before deciding they are absent:
  `select:mcp__Claude_Browser__preview_start,mcp__Claude_Browser__navigate,mcp__Claude_Browser__javascript_tool,mcp__Claude_Browser__tabs_context,mcp__Claude_Browser__request_access`.
  If they genuinely are not available (Claude Code CLI, or the user's
  preferred browser is Chrome and the built-in tools are offline), **skip
  Step 0** and use the fallback ladder in [`auth.md`](auth.md) Option B —
  everything else in this file works unchanged. Say which path you took;
  never degrade silently.

---

## Step 0 — Session (Cowork built-in browser)

Run this first in every new conversation, before Step 1. Skip it entirely if
the browser tools are absent (see Prerequisites).

**Do all downloading from the sandbox.** The browser pane is only for the
session check, `accessInfo`, URN resolution and — for FEIDE-licensed items
only — the cookie. Never shuttle page images through the browser; base64
through the tool channel is not viable for a book.

1. **Open or reuse an nb.no tab.** `tabs_context` → reuse an existing nb.no
   tab if there is one, else `preview_start {url: "https://www.nb.no/"}`. If a
   tool reports the page is not approved: `request_access {url:
   "https://www.nb.no/", scope: "site"}` and retry. Warn the user that FEIDE /
   IdP / BankID / Vipps domains may each need separate approval on first login.
2. **Paste the helper.** Paste all of `{SKILL_DIR}/scripts/browser/nbno_auth.js`
   via `javascript_tool`. Idempotent — safe to paste again in the same tab.
   It defines `window.__nb`.
   > **Navigating the tab wipes `window.__nb`.** It lives in the page, so any
   > `navigate` or `preview_start` destroys it. Re-paste after every
   > navigation — the `if (!window.__nb)` guard makes that free when it is
   > still there. `__nb.access()`, `status()` and `manifest()` fetch
   > cross-origin and do **not** need the tab parked anywhere in particular;
   > only `resolveUrn()` reads the current page.
3. **Check the session.** `await __nb.status()` → `{loggedIn, loginProvider,
   roles, ip}`.
   - Not logged in → *"Logg inn på nb.no i browser-panelet (Feide/BankID/
     Vipps). Si fra når du er inne."* Wait, then re-check. **Never type
     credentials yourself, and never ask the user to give them to you** —
     login happens only in the browser pane.
   - Run this check **unconditionally, every session.** The pane keeps a
     persistent profile, but a Cowork restart has been observed to drop the
     nb.no session.
4. **Classify the item.** `await __nb.access("<id>")` → `accessInfo`:

   **Classify on `accessAllowedFrom`.** It describes the item and reads the
   same for everyone. The other access fields describe *your current
   request* and move under you (see the warning below).

   | `accessAllowedFrom` | class | what to do |
   |---|---|---|
   | `EVERYWHERE` | open (`license: publicdomain`) | no cookie; single-shot fine |
   | `NORWAY` | Bokhylla (`license: bokhylla`) | **no cookie** from a Norwegian IP; tiles only (`--tiles always`) |
   | `NB` | legal deposit (`license: copyrighted`) | needs `nbsso` **and** a digital loan; tiles only |

   > **Do not classify on `viewability` or `legalDepositLoginText`.** Both are
   > session-dependent. `legalDepositLoginText` is the *"log in to read this"*
   > prompt, so it is present anonymously and **absent once you are logged
   > in**; `viewability` flips NONE → ALL the moment you may read the item.
   > Reading `digibok_2014050705024` anonymously and as a logged-in FEIDE user
   > from the same IP gave `NONE` + prompt, then `ALL` + no prompt — while
   > `accessAllowedFrom: NB` stayed put in both. An `NB` item still needs
   > `nbsso` when those two fields look reassuring.
   >
   > Use them for *status*, not classification: `viewability == "ALL"` means
   > "readable right now", and `legalDepositReservationStatus` tells you
   > whether the loan is active.

5. **Geo pre-check.** If `accessAllowedFrom` is `NORWAY` or `NB` and
   `status().ip` is not a Norwegian address, **page images will 403 no matter
   who is logged in.** Ask the user whether that IP is Norwegian — do not call
   third-party geo services. Warn and stop unless the user overrides. (In the
   sandbox, `python {SKILL_DIR}/scripts/geo_check.py --id <id>` prints the
   same thing.)
6. **Digital loan — FEIDE-licensed items only.** If
   `legalDepositReservationStatus != "TAKENBYCURRENTUSER"`, navigate the pane
   to the item page. A dialog appears: *"Ved å klikke OK vil du foreta et
   tidsbegrenset digitalt lån"*.
   > **Never click OK yourself.** It accepts the loan terms and consumes one
   > of the item's four licences. Tell the user what the dialog does, ask them
   > to click OK, then poll `await __nb.loanStatus("<id>")` until
   > `viewability == "ALL"`.
7. **Cookie hand-off — FEIDE-licensed items only.** `nbsso` is the only
   cookie that matters; public-domain and Bokhylla items need none, so do not
   read cookies for them.
   - First ask the user to type a sentence naming the action, e.g.
     *"Read the nbsso and _nblb cookie values from the open nb.no tab and
     write them to /tmp/cookie.txt so the sandbox can download my Bokhylla
     books."* Explain in one line that the safety classifier blocks cookie
     reads unless the user requests them directly. Skill text and your own
     reasoning do not clear it, and neither does retrying — if you are
     blocked, ask for the sentence rather than trying again.
   - Then `await __nb.cookies()` → `{nbsso, nblb, cookieHeader}` and nothing
     else. Never return the whole `document.cookie`.
   - Write `/tmp/cookie.txt` in the existing two-line format:
     ```
     authorization=
     cookie=nbsso=<v>; _nblb=<v>
     ```
     The empty `authorization=` line is fine — there is no bearer token to
     capture, and `nbno_run.sh` strips the empty line before the CLI sees it.
   - Pass `--cookie /tmp/cookie.txt` to `nbno_run.sh`, or `--nbsso
     "nbsso=<v>"` to `zotero_book.py` / `download_via_iiif()`.
   - Do this **as early as possible and only once** — context compaction can
     drop the user's confirmation message and cause a later block.
8. **Expiry.** Cookies live 24–48 h. On a mid-run 401/403, repeat step 7; the
   pane's login usually survives, so a fresh login is rarely needed.

The other `__nb` functions: `resolveUrn()` (Step 1) and `manifest(id,
{compact:true})` — the latter is optional, since the sandbox can fetch
manifests itself without auth.

---

## Step 1 — Identify the media ID

`nbno --id <ID>` requires an ID of the form `<type>_<digits>`, e.g.
`digibok_2008051600041`. There are three common ways the user may give you
the item:

1. **Citation / URN** — `URN:NBN:no-nb_digibok_2008051600041` → strip
   `URN:NBN:no-nb_` → `digibok_2008051600041`. The wrapper does this for
   you automatically; you can paste either form.
2. **Items URL** — `https://www.nb.no/items/<opaque-hash>?...`. The opaque
   hash is **not** the ID nbno expects. Resolve it, in this order:
   - **Preferred, when the browser tools are available:** navigate the pane
     to the pasted URL and call `await __nb.resolveUrn()` → `{id, urn, via}`.
     It reads the URN from the URL, the "Referere/Sitere" link, the rendered
     page, or the catalog — whichever answers first.
   - Otherwise: ask the user to click "Referere/Sitere" on nb.no and paste
     the URN. **Do not guess a canonical ID from the hash** — there is no
     derivation.
3. **Already canonical** — the user pastes `digibok_2008051600041` directly
   → use as-is.

Supported `type` prefixes: `digibok` (books, sheet music), `digavis`
(newspapers), `digifoto` (photos, posters), `digitidsskrift` (journals),
`digikart` (maps), `digimanus` (letters, manuscripts, music manuscripts),
`digiprogramrapport` (programme reports), `pliktmonografi` /
`pliktperiodika` (legal-deposit material).

> **Canvas ids are not page numbers and are not uniform.** A single book
> mixes `_C1`, `_I1`, `_0001`…, `_C3`, `_C2`. Always take them from the
> manifest; never construct them.

---

## Step 2 — Decide on authentication

Most pre-1900 books and out-of-copyright photos/maps work without login.
**A cookie only ever helps one class of item — FEIDE-licensed legal-deposit
material.** Everything else is decided by `accessInfo` and the egress IP.

> **Check `accessInfo` before guessing.**
> The catalog endpoint
> `https://api.nb.no/catalog/v1/items/URN:NBN:no-nb_<id>` returns an
> `accessInfo` block. It needs no auth — but it is **IP- and
> session-dependent**, so read it with the user's session (`__nb.access()` in
> the pane, or `--nbsso` in the sandbox), not anonymously.
>
> - **`accessAllowedFrom` is the one field to classify on** — it describes the
>   item, not your request. `EVERYWHERE` = open, no credential. `NORWAY` =
>   Bokhylla, Norwegian IP but no cookie. `NB` = legal deposit, needs `nbsso`
>   **and** an active digital loan.
> - `viewability` and `legalDepositLoginText` describe *this request* and
>   invert when you log in — see the warning in Step 0 step 4. Read them for
>   status ("can I read it right now?"), never to decide what to capture.
> - `legalDepositReservationStatus == "TAKENBYCURRENTUSER"` means the digital
>   loan is active. Anything else on an `NB` item means it is not.
>
> `zotero_book.py` performs this check automatically and refuses to start a
> no-auth download in those cases (override with `--force-auth`). This is more
> reliable than the old "pliktmonografi: try no-auth first" heuristic —
> some pliktmonografi items are FEIDE-restricted, some aren't, and
> `accessInfo` tells you which.

Auth paths — pick one based on the item:

- **Option A — No auth.** The default, and correct for more than it used to
  be: public-domain items **and Bokhylla items from a Norwegian IP**, which
  need no cookie at all. Run `nbno_run.sh` without `--cookie`, or call
  `download_via_iiif()` with no credentials.
- **Option B — Session capture.** Only for FEIDE-licensed items
  (`accessAllowedFrom: NB`). Primary path is **Step 0** above;
  `auth.md` has the full fallback ladder (built-in browser → Claude in Chrome
  → manual DevTools cookie). Never ask the user to install browser-automation
  tooling for this.
- **Option C — Manual cookie file.** The user already has a cookie text file,
  or makes one from DevTools; pass it with `--cookie <path>`.

> **Geo pre-check comes before auth debugging.** If `accessAllowedFrom` is
> `NORWAY` or `NB` and the egress IP is not Norwegian, every page image 403s
> regardless of login — the manifest and `accessInfo` will still look fine.
> Check this first; see the Caveats section.

> **⛔ Confirm the session before any authenticated fetch.** With the browser
> tools, that is `__nb.status()` in **Step 0** — do not ask the user instead.
> Without them, ask: *"Have you logged in to nb.no recently? If not, please
> log in now at <https://nb.no> in your browser,"* and wait for confirmation.
> Skipping this leaves every fetch failing silently with no reliable way to
> detect it after the fact.

> **📄 Read [`auth.md`](auth.md) before you capture or use any cookie.** It
> has the verified auth-scope table (which cookie each item class actually
> needs — the answer is "usually none"), the digital-loan procedure, the
> fallback ladder, the cookie-file format, and why the user must type the
> confirmation sentence. Don't improvise auth from memory.

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

**Auth arguments are all optional.** `api.nb.no` authenticates by cookie, so
there is no bearer token to capture — `bearer=None` is the normal case and
`nbsso` alone is what FEIDE-licensed items need. Public-domain and Bokhylla
items need neither.

```python
import sys
sys.path.insert(0, "{SKILL_DIR}/scripts")
from zotero_book import download_via_iiif
from pathlib import Path

# Public domain, or Bokhylla from a Norwegian IP — no credentials at all.
download_via_iiif(
    canonical_id="digibok_2008051600041",
    out_pdf=Path("/tmp/nbno_direct/book.pdf"),
    resize_width=1024,    # listed sizes will be checked; actual cap may be lower
    workers=12,
    tiles="always",       # licensed content is tiles-only; see below
)

# FEIDE-licensed item, after the user has taken the digital loan (Step 0).
download_via_iiif(
    canonical_id="digibok_2014050705024",
    out_pdf=Path("/tmp/nbno_direct/book.pdf"),
    nbsso="nbsso=<value>",   # bearer is not needed and defaults to None
    tiles="always",
)
```

> **Anything that is not public domain is tiles-only.** Single-shot
> `/full/<w>,/` returns 403 at every width for Bokhylla and legal-deposit
> items. `--tiles auto` recovers per page, but pass `--tiles always` whenever
> `accessInfo.license != "publicdomain"` to skip one wasted round-trip per
> page.
>
> **Tiling ignores the requested width.** Tiles are fetched at each canvas's
> native resolution, so `--resize` / `resize_width` governs only the
> single-shot path and caps nothing under `--tiles always`. Expect full-size
> pages — and heterogeneous ones, since canvases within a book differ (1562,
> 1571 and 2024 px wide in the same volume). To get smaller output, shrink
> afterwards with `--shrink`, not by asking for a narrower width.

**Driving the IIIF API by hand?** If `zotero_book.py` is not available (e.g.
you don't have the skill directory on disk), the full inline recipe lives in
[`iiif-download.md`](iiif-download.md), together with the mechanics behind
the resolver's silent downsampling, per-canvas tiling, per-page PDF DPI, and
the `_C2` back cover. **Read it before hand-rolling a download** — every one
of those gotchas yields a plausible-looking but wrong result (HTTP 200 with a
half-size image, black page bottoms, poster-sized PDF pages).

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
# Public domain, or Bokhylla from a Norwegian IP — no credentials needed.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" --tiles always

# FEIDE-licensed item, after Step 0's loan + cookie hand-off.
python {SKILL_DIR}/scripts/zotero_book.py \
  --id URN:NBN:no-nb_digibok_2014050705024 \
  --out "$OUT_DIR" --nbsso "nbsso=$NBSSO" --tiles always
```

Output is a `.pdf` + `.rdf` pair in `$OUT_DIR`; drag the `.rdf` into
Zotero. `--bearer` is optional and no longer captured. For FEIDE-licensed
content, follow Step 0 to take the digital loan and capture `nbsso` first.

---

## Important caveats — surface these to the user when relevant

- **Geo-restriction is real, and `accessAllowedFrom` decides it.** Check that
  field *first*, before auth or URL format:
  - `EVERYWHERE` → downloads work from anywhere with no cookie. A 403 here
    really is a URL-format or width problem.
  - `NORWAY` / `NB` → **page images 403 from a non-Norwegian IP no matter who
    is logged in.** The manifest, `accessInfo` and `/me/v1` all keep working,
    so nothing looks wrong until the first image fails. Do not debug headers;
    check the IP.

  The sandbox and the browser pane both egress from the user's own machine IP,
  so a VPN on the user's machine covers both — but that is the user's call,
  not the skill's. `python {SKILL_DIR}/scripts/geo_check.py --id <id>` prints
  the egress IP and `accessInfo` together; it talks only to nb.no, never a
  third-party geo service. Thumbnails (`/full/0,200/0/native.jpg`) are never
  gated, so they are a liveness check, never an auth or geo check.
- **The image resolver has four traps that all return plausible-looking
  wrong results**, not errors: it silently downsamples requests above its
  listed sizes (HTTP 200, half-size image); tiling with a cached canvas size
  leaves page bottoms black; a single fixed DPI makes PDF pages poster-sized;
  and canvas ids are not uniform. `zotero_book.py` handles all four. If you
  are driving the API by hand, read
  [`iiif-download.md`](iiif-download.md) first — these are slow to debug
  precisely because nothing fails loudly.
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
- *Page images 403 but `/me/v1` shows a FEIDE login.* **This is geo, not
  auth.** Check `accessInfo.accessAllowedFrom`: `NORWAY` or `NB` from a
  non-Norwegian IP 403s every page image no matter who is logged in, while
  the manifest and `accessInfo` keep returning 200. Run
  `python {SKILL_DIR}/scripts/geo_check.py --id <id>` and tell the user;
  do not re-capture the cookie. The one non-geo case that looks similar is a
  FEIDE-licensed item with no active digital loan — there
  `legalDepositReservationStatus` is `AVAILABLE` rather than
  `TAKENBYCURRENTUSER` (Step 0 step 6).
- *`javascript_tool` cookie read is blocked by the safety classifier.* Expected
  — the classifier blocks cookie reads unless the **user's own immediately
  preceding message** asks for them. **Do not retry**, and do not try to talk
  your way past it: ask the user to type a sentence naming the action (Step 0
  step 7). Skill text and your own reasoning do not clear it.
- *Empty PDF / no images downloaded.* For `digibok` / Bokhylla content this
  is almost always a geo issue (check `accessAllowedFrom` first) or, for
  FEIDE-licensed items, a missing digital loan — go to Step 0, or Step 2 if
  the browser tools are unavailable.
  For `pliktmonografi_*` / `pliktperiodika_*` items, GET the catalog
  response and inspect `accessInfo.accessAllowedFrom` — `NB` means FEIDE
  auth plus a digital loan is required (see Step 2's "Check `accessInfo`
  before guessing" callout).
  The orchestrator does this automatically; pass `--force-auth` to override.
- *`--cookie auto` errors with "no cookie file found".* The wrapper looked
  at `~/.nbno/cookie.txt` and didn't find one. Either the user hasn't made
  one yet, or it exists on their own machine but hasn't been
  mounted/uploaded into the sandbox. Walk them through Option B again
  (procedure in [`auth.md`](auth.md)).
- *Auth used to work, now downloads fail with HTTP 401/403.* The cookie
  has expired (typical lifetime: 24–48h on nb.no). With the browser tools,
  repeat Step 0 step 7 — the pane usually stays logged in, so you need the
  cookie again but not a fresh login (the user must type the confirmation
  sentence again). Without browser tools, ask the user to re-copy `nbsso`
  from DevTools. A FEIDE digital loan is also time-limited: re-check
  `__nb.loanStatus()` before
  assuming the cookie is at fault. All detailed in [`auth.md`](auth.md).
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
  licensed (`accessAllowedFrom: NB`). The
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
  