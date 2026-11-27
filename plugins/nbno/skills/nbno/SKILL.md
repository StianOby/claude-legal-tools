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
  posters, programme reports. ALSO use for Zotero requests
  ("Zotero-ready book", "Zotero RDF for nb.no", "OCR and import this book",
  "add it to my Zotero") — PDF + OCR + Zotero RDF, or direct import via
  Zoteus.
  Uses the Cowork built-in browser for FEIDE session capture when available;
  falls back to a manual DevTools cookie.
  Do NOT use for: Lovdata legal texts (use lovdata-api / lovdata-pro), generic web
  scraping, or content the user has no right to access.
---

# nbno — download from Nasjonalbiblioteket (nb.no)

**First step, before any command:** resolve `{SKILL_DIR}` as described under "Skill directory" below and use the printed path literally. Never guess it (e.g. `/mnt/skills/...`).

This skill downloads books, newspapers, photos, journals, maps, manuscripts,
etc. from nb.no's IIIF API as page images and assembles them into a PDF.

The user's preferences for this skill:

- **Output**: PDF only (the page images are removed unless `--keep-images`).
- **Auth**: Prompt every time an item needs a credential (`NB`, FEIDE).
  Before such a run, ask the user which auth path in **Step 2** to take.
  `EVERYWHERE` and `NORWAY` items need no credential — don't ask. The default cookie location is `~/.nbno/cookie.txt`
  when the user keeps a durable one.

## Prerequisites

- **Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for
  this skill:" only to read files: the shell often cannot see that path.
  Always run this once before the first command and use the printed path
  literally in later commands:
  ```bash
  for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/nbno}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/nbno/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
  ```
- **Built-in browser (optional, Cowork only).** If the built-in browser tools
  are present, **Step 0** uses them for the session check, item
  classification and cookie capture.
  > **Browser tools.** The built-in browser's tool prefix differs by environment (`mcp__Claude_Browser__…` in local
  > Cowork, `mcp__remote-devices__Claude_Browser__…` in cloud Cowork). They are often deferred: run one ToolSearch with
  > query `Claude_Browser` and `max_results` 64, and use whatever prefix comes back. This file names them by suffix only
  > (`tabs_context`, `preview_start`, `navigate`, `javascript_tool`, `get_page_text`, `read_page`, …).
  > `request_access` does not exist in every environment; if it is missing, go straight to `preview_start`/`navigate`.

  If they genuinely are not available (Claude Code CLI, or the user's
  preferred browser is Chrome and the built-in tools are offline), **skip
  Step 0** and use the fallback ladder in [`auth.md`](auth.md) Option B —
  everything else in this file works unchanged. Say which path you took;
  never degrade silently.

## Where each step runs

| Step | Runs in |
|---|---|
| Session check, `accessInfo`, URN resolution, digital-loan dialog, cookie read (Step 0) | **browser pane** (the user's IP and logins) |
| Catalogue search (`nb_search.py`), manifests, first `geo_check.py` probe | **`Bash`** |
| Download, OCR, shrink, Zotero RDF — `EVERYWHERE` items | **`Bash`** |
| Download, OCR, shrink, Zotero RDF — `NORWAY` / `NB` items | **local shell** (`device_bash`, the local route) |

Cowork runs in the cloud: `Bash` has Anthropic's IP, not the user's; only the browser pane and the local shell
(`device_bash`) have the user's IP, and only the browser pane has the user's logins.

### Routing

nb.no serves `NORWAY` (Bokhylla) and `NB` (legal deposit) page images only to Norwegian IPs, and Anthropic's cloud is
not one. So:

| `accessAllowedFrom` | Where the download runs | Credential |
|---|---|---|
| `EVERYWHERE` | cloud sandbox (`Bash`), as always | none |
| `NORWAY` | local shell (local route) | none |
| `NB` | local shell (local route) | `nbsso` from the browser pane (Step 0.7) + an active loan (Step 0.6) |

1. **Probe in `Bash`:** `python {SKILL_DIR}/scripts/geo_check.py --id <id>`. The last line is `route: …`.
   - `route: here` → download in `Bash` (Step 3). This is every `EVERYWHERE` item.
   - `route: norwegian-ip` or `norwegian-ip+loan` → expected, not an error: use the local route
     (step 2). **First make sure it can run** (`local-route.md` §1: load the tools, find a connected folder),
     before asking the user to log in, take a loan or approve a cookie read; then, for `norwegian-ip+loan`,
     Step 0.6–0.7 (loan, cookie).
   - `route: unknown` → report the probe line and ask before downloading.
   - A `NORWAY`/`NB` item never downloads in `Bash`: if the cloud probe says `here` for one, treat it as
     `norwegian-ip`, use the local route, and tell the user the probe was wrong.
2. **Local route** — follow [`local-route.md`](local-route.md) (it decides whether `device_bash` and a connected folder
   are available and has the fixed messages if not). **Check for a connected folder first** (`ls -d "$HOME"/mnt/*/`
   in `device_bash`; if none, ask for one as `local-route.md` §1 says) — `device_bash` refuses to run without one.
   For nbno, once `READY <dir>` is printed:
   - `NB` only: put the cookie in a mode-600 file inside `<dir>`, never in the connected folder:
     `umask 077; printf 'cookie=nbsso=%s; _nblb=%s\n' '<nbsso>' '<nblb>' > <dir>/cookie.txt`
   - Get the Python once (`local-route.md` §3): `test -f <dir>/.ready || exit 4; bash <dir>/scripts/local_python.sh <dir>`
     prints `<py>`, a Python 3.13 (exit 1 → use `python3` and say newer packages may not install).
   - Probe again from the user's machine, in `device_bash`:
     `test -f <dir>/.ready || exit 4; PYTHONUTF8=1 <py> <dir>/scripts/geo_check.py --id <id>` (add
     `--cookie <dir>/cookie.txt` for `NB`). `route: here` → go on. `norwegian-ip` → the user's IP is not Norwegian; tell
     them and stop. `norwegian-ip+loan` → ask the user to log in again / retake the loan in the browser pane, re-read
     the cookie, retry **once**, then stop. For `NB`, `here` needs the cookie *and* the loan
     (`legalDepositReservationStatus: TAKENBYCURRENTUSER`); a served tile alone is not enough, as nb.no serves the
     first pages without a loan.
   - Download with the same commands as in Step 3 / [`zotero-ready.md`](zotero-ready.md), calling the scripts by
     absolute path (`<py> <dir>/scripts/nb_download.py …`, `<py> <dir>/scripts/zotero_book.py …`) with
     `--out <dir>/out` (plus `--cookie <dir>/cookie.txt` for `NB`).
   - OCR / Zotero-ready: first `command -v tesseract`. Present (tesseract 4.1.1 with `eng`/`osd` only on
     2026-09-30) → `zotero_book.py` fetches `nor` and pip-installs Pillow and `ocrmypdf` into the run directory itself.
     Missing → `--no-ocr`. Current ocrmypdf needs Python ≥ 3.11: with `<py>` that holds; if
     `local_python.sh` failed and you are on the VM's `python3` (3.10), pip installs an older ocrmypdf, so say
     so. Install no Python other than through `local_python.sh` (never system-wide, never conda). Either way, if `zotero_book.py` exits **5**, OCR failed but the PDF and RDF are complete:
     handle it as in **OCR failed (exit 5)** under Step 4.
   - If the device drops mid-run ("not connected to the bridge"), wait for it to reconnect and re-run the same
     command: `<dir>` with the downloaded pages and `ocr_chunked.py`'s page cache survives, and the run resumes (2026-11-26).
   - Copy the finished PDF (and RDF) to `<connected folder>/nbno/<id>/` and tell the user where it is. Keep
     `<dir>` for further nb.no downloads in this conversation (`local-route.md` §2.4); when you are done with
     nb.no, `rm -rf <dir>` (this also removes the cookie).

Never fall back silently to the cloud sandbox for a `NORWAY`/`NB` item, never debug headers after a geo 403, and never
suggest a VPN.

---

## Step 0 — Session (Cowork built-in browser)

Only for `NB` items (login and loan), or to resolve an `nb.no/items/<hash>`
link (Step 1); `EVERYWHERE` and `NORWAY` items need none of it, as
`geo_check.py` reads their `accessInfo`. For an `NB` item, run it only after
**Routing** has confirmed that the local route can run (tools and a
connected folder), so the user is never asked to log in or take a loan for
a download that cannot happen. Skip it if
the browser tools are absent (see Prerequisites). The full procedure, with the
reasons behind each rule, is in [`auth.md`](auth.md) ("Fallback 1 (primary) —
built-in browser"); the rules below are the ones you must not break.

**The browser pane never downloads.** It is only for the session check,
`accessInfo`, URN resolution, the digital-loan dialog and — for `NB` items
only — the cookie. Never shuttle page images through the browser.

1. **Tab.** `tabs_context` → reuse an nb.no tab, else
   `preview_start {url: "https://www.nb.no/"}`. If `request_access` exists
   and the page is not approved: `request_access {url: "https://www.nb.no/",
   scope: "site"}`. FEIDE / IdP / BankID / Vipps may each need approval.
2. **Helper.** Run `python3 {SKILL_DIR}/scripts/browser/paste.py
   {SKILL_DIR}/scripts/browser/nbno_auth.js` in Bash; it writes a stripped
   copy (~6,000 characters) and prints its path. Read that file and send all
   of it via `javascript_tool` → `window.__nb` (if `paste.py` fails, paste
   `nbno_auth.js` itself; never trim it). **Navigating the tab wipes it:
   paste it again after every `navigate`/`preview_start`** (same version =
   no-op; `__nb.VERSION` is the plugin version of the last change to the
   helper, so it can be lower than the plugin's). If the paste is refused by a safety check, do not retry it: tell
   the user in one sentence and fall back to the manual DevTools cookie
   (`auth.md`, Fallback 3); `EVERYWHERE` items need no browser at all.
3. **Session.** `await __nb.status()`. Not logged in → *"Logg inn på nb.no i
   browser-panelet (Feide/BankID/Vipps). Si fra når du er inne."* Block on
   this only for `NB` items. **Never type credentials or ask for them.**
   The login redirects through FEIDE/IdP pages, which wipes `__nb`: when the
   user says they are in, check `typeof __nb` and paste the helper again
   before `status()`.
4. **Classify.** `await __nb.access("<id>")` → classify on
   **`accessAllowedFrom` only** (`EVERYWHERE` open · `NORWAY` Bokhylla, no
   cookie · `NB` legal deposit, `nbsso` + loan).
   `viewability` and `legalDepositLoginText` flip when you log in — status,
   never classification.
5. **Geo.** `NORWAY`/`NB` → run the probe and follow **Routing** above.
6. **Loan (`NB` only).** If `legalDepositReservationStatus !=
   "TAKENBYCURRENTUSER"`, navigate the pane to the item page. **Never click
   OK yourself** — it takes one of the item's four licences in the user's
   name. Navigating to the item page wipes `__nb`: paste the helper again
   before polling. Ask the user to click it, then poll
   `await __nb.loanStatus("<id>")`.
7. **Cookie (`NB` only).** First ask the user to type a sentence naming the
   action (*"Read the nbsso and _nblb cookie values from the open nb.no tab
   and write them to a cookie file so it can download my book."*) — the
   safety classifier blocks cookie reads otherwise, and retrying does not
   help. Then `await __nb.cookies()` → `{nbsso, nblb}` only, never the whole
   jar. Do it early and once. The cookie goes straight into
   `<dir>/cookie.txt` in the local shell, mode 600 (**Routing**; format in
   `auth.md`); never a shared path like `/tmp/cookie.txt`.
8. **Expiry.** Cookies live 24–48 h; on a mid-run 401/403 repeat step 7 (and
   check the loan).

---

## Step 1 — Identify the media ID

nbno needs an ID of the form `<type>_<key>`, e.g. `digibok_2008051600041`
(keys may contain underscores: `digavis_aftenposten_morgen_1_20150107_156_7_2`).

1. **URN** `URN:NBN:no-nb_digibok_…` → the scripts strip the prefix; pass
   either form.
2. **`nb.no/items/<hash>` URL** — the hash is **not** the ID and cannot be
   converted. With the browser tools: navigate the pane to the URL, paste
   the helper again (same file), then `await __nb.resolveUrn()` → `{id, urn, via}`. On
   `{error: "ambiguous"}` (item pages embed other editions' ids) ask the user
   for the URN; do not pick a candidate. Otherwise ask the user to click
   "Referere/Sitere" and paste the URN. Check that `__nb.access(id).title`
   matches the page before downloading a whole book.
3. **Canonical ID** → use as-is.
4. **Only a reference** (author, title, year):
   `python {SKILL_DIR}/scripts/nb_search.py "Eckhoff Rettskildelære" --year 2001`.
   Use surname + one title word and narrow with `--year`. Pick the hit whose
   **year matches the reference** (other years are other editions; "Utdrag
   av …" is an excerpt). `[NEWEST of the hits shown]` marks the latest
   edition when the hits span several years; add `--max 30` if more hits
   exist than are shown. `--type tidsskrift` / `avis`, `--json`.
   **By topic or period** (no specific reference): `--year 1850-1899`
   takes a range, and `--access everywhere|norway|nb` keeps only
   digitised items readable that way (free / Bokhylla / FEIDE loan).
   A hit marked `not digitised` has nothing to download.

Types: `digibok`, `digavis`, `digifoto`, `digitidsskrift`, `digikart`,
`digimanus`, `digiprogramrapport`, `pliktmonografi`, `pliktperiodika`.
**Canvas ids are not page numbers and not uniform** (`_C1`, `_I1`, `_0001`,
`_C2` …): take them from the manifest, never construct them.

---

## Step 2 — Authentication

A cookie only ever helps **`NB` (FEIDE-licensed legal deposit)** items;
everything else is decided by `accessAllowedFrom` and the egress IP.
`zotero_book.py` checks `accessInfo` itself and refuses a no-auth download of
an `NB` item (`--force-auth` overrides).

- **Option A — no auth.** Public-domain items, and Bokhylla from a Norwegian
  IP. The default.
- **Option B — session capture** (`NB` only): Step 0. Without the built-in
  browser, `auth.md` has the fallback ladder (Claude in Chrome → manual
  DevTools cookie). Never ask the user to install browser automation.
- **Option C — a cookie file** the user already has: `--cookie <path>`.

**Geo comes before auth debugging:** a `NORWAY`/`NB` item 403s from a
non-Norwegian IP whoever is logged in. Without browser tools, ask the user to
confirm they are logged in to nb.no before any authenticated fetch. **Read
[`auth.md`](auth.md) before capturing or using any cookie.**

---

## Step 3 — Download

**Fetch only what you need** — ask which pages before downloading a whole
book. `--start`/`--stop` are 1-based **canvas** numbers, not printed pages.
Page numbers the user gives ("sidene 1–10", "pp. 45–60") are printed pages
unless they say otherwise. To find the offset, probe a few canvases with
`--keep-images` near where the wanted page should be: start at page + 4
(front matter is usually 2–10 canvases), or at canvases 1–7 for an early
page. Read the printed number on a probe page, work out canvas = page +
offset, then fetch the range. If you only see front matter, probe further
in. On the cloud route, look at the probe images. On the local route you
cannot see them, because they sit in `<dir>` and must not be copied to the
user's folder. Read the number with the local tesseract instead:
`tesseract <img> - 2>/dev/null | sed -n '1,3p;$p' | grep -oE '[0-9]+'`
prints only the numbers in the head and foot lines, not the body text. OCR
can add noise (`123)`), so match loosely. To check the final pages on the
local route, pass `--keep-images` on the final call as well and read each
page the same way. Fetch front matter before printed p. 1 only if asked,
and name both the printed pages and the canvases when you deliver.
Use **one `--out` for every call in a task**, the probes and the final
download, so Pillow and img2pdf install into `<out>/_pylib` only once.

Any item type (books, newspapers, photos, posters, maps, manuscripts, sheet
music): `nb_download.py`, which writes `AUTHOR_TITLE_(YEAR).pdf` to `--out`.
For a Zotero item, OCR or shrink in one go, use `zotero_book.py` instead
(below); both share one downloader.

Create the scratch dir once (`mktemp -d`, in its own call) and write its
printed path into every later command: a shell variable does not survive
between Bash calls.

```bash
python {SKILL_DIR}/scripts/nb_download.py --id "digibok_2008051600041" --out /tmp/tmp.Ab12Cd \
  [--start 1 --stop 7] [--cookie <file>|auto | --nbsso "nbsso=<v>"] [--size full] [--keep-images]
```

| flag | purpose |
| --- | --- |
| `--start N` / `--stop N` | canvas range (1-based manifest positions, covers included); the file gets a `_c<N>-<M>` suffix |
| `--cookie PATH` / `--cookie auto` · `--nbsso` | `NB` items only: a cookie file (`auto` = `~/.nbno/cookie.txt`) or the pair itself |
| `--size full` | the scan's own size (default half, ~145 dpi on a book page); only when the user asks for full resolution, e.g. maps |
| `--keep-images` | also keep the page JPEGs in `<out>/<basename>_images/` |
| `--shrink` | shrink the page images afterwards (Step 4) |

Pages come at half size, enough for OCR and sharp once shrunk; the script
picks one request or tiles per page itself. The resolver's traps and the
inline recipe for driving the API by hand: [`iiif-download.md`](iiif-download.md).

- **Timeouts:** request a long bash timeout (600000 ms) but plan for ~170 s
  per call. Downloads fit (424 pages ≈ 105 s); OCR of a long book does not —
  use `--no-ocr` and `ocr_chunked.py` ([`reading-ocr.md`](reading-ocr.md)).
  **Never `nohup … &`**: the process dies when the call returns.
- **Resume:** a run cut off, or ending with placeholder pages (exit 3),
  keeps its pages in `<out>/_pages/`. Re-run the same command with the same
  `--out` path, written out (not a new `mktemp -d`): only the rest is
  fetched. A 403 on every page is access, not bad luck: fix that first (Step 2).
- **`--out`** is a scratch dir; copy the PDF to the outputs folder afterwards (Step 4).

For reading pages visually, OCR and shrinking, read
[`reading-ocr.md`](reading-ocr.md) first.

---

## Step 4 — Hand the file back

- **Shrink books:** `zotero_book.py` does it by default; any other PDF over
  ~50 MB (`nb_download.py` prints its size) →
  `python {SKILL_DIR}/scripts/shrink_pdf.py --pdf <file>`, or `--shrink` on
  the download. Order is always download → OCR → shrink. The default
  (`--shrink-mode bitonal`) makes text pages sharp black and white (~25–37 MB
  for 400 pages) and keeps covers and photos as JPEG; faint pencil notes
  turn black and stamps become outlines. If the user wants grey tones kept
  (annotations, stamps, illustrations), use `--shrink-mode grey`
  (~80 MB for 400 pages). Say what size the PDF ended up.
- **Don't shrink maps, photos or posters** the user asked for at full
  resolution: bitonal would turn them black and white. Deliver them as they
  are; offer `--shrink-mode grey` only if the size is a problem.
- **OCR failed (exit 5):** the shrunk PDF and RDF are complete, and the
  unshrunk pages are kept as `<base>.original.pdf`. Tell the user OCR
  failed and why (the log quotes ocrmypdf's own error), then try to fix the
  cause — usually a missing Python module (install it into `<out>/_pylib`,
  where the scripts put their own installs) or Tesseract. If fixed, follow the retry line the log prints:
  `ocr_chunked.py` on the `.original.pdf`, `shrink_pdf.py` from it to the
  main PDF, then delete the `.original.pdf`. Do not download the book
  again. If it cannot be fixed (no Tesseract on the local route), deliver
  without a text layer and use message **C** from `local-route.md`.
- **Deliver:** copy it to the outputs directory (`/mnt/user-data/outputs` in
  cloud Cowork) and share it with `SendUserFile`, which refuses files
  over 30 MiB: then just say where the PDF is. Local-route results are
  already in `<connected folder>/nbno/<id>/`; say where (send one only if it
  is under 30 MiB, after `device_stage_files` — see `local-route.md` §3).
- **Page size:** pages are scaled to A4 height (297 mm), with the width
  following the scan's proportions — the scan does not record the book's
  real size, so do not report it as the book's format.
- **Say what it is, when you deliver it:** a canvas range is an **excerpt**
  (name the canvases and, if known, the printed pages); placeholder pages
  (exit 3) are missing pages; exit 5 means no text layer.
- Don't narrate the contents; let the user open it.

---

## Zotero-ready books

For "Zotero-ready", "RDF with the PDF attached", "OCR and import this book",
"put it in my Zotero library": read [`zotero-ready.md`](zotero-ready.md)
first. `zotero_book.py` downloads, adds a text layer (nb.no's own OCR for
public-domain books, Tesseract otherwise), shrinks and writes a `.pdf` +
`.rdf` pair; drag the `.rdf` into Zotero. With the Zoteus tools
(`zotero_*`), the item can go straight into the library instead.
`--start/--stop` make an excerpt (files get a `_c<N>-<M>` suffix). **If the
item ends up without its PDF, tell the user** (`zotero-ready.md`, "When the
PDF is not attached").

```bash
python {SKILL_DIR}/scripts/zotero_book.py --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" [--nbsso "nbsso=<v>"] [--start 1 --stop 20] [--shrink-mode grey]
```

---

## Caveats and troubleshooting

Read [`troubleshooting.md`](troubleshooting.md) when something fails or
looks wrong. The three rules that prevent most wasted time:

- **Geo first.** Page images 403 while the manifest, `accessInfo` and
  `/me/v1` look fine → it is the IP (`NORWAY`/`NB`), not auth: follow
  **Routing**. Never suggest a VPN.
- **Silent wrong results.** The image resolver downsamples, blackens page
  bottoms and mis-sizes pages without an error; use the scripts rather than
  hand-rolled requests (`iiif-download.md` if you must).
- **Copyright.** Bokhylla and FEIDE access is personal and does not permit
  redistribution; don't help redistribute in-copyright material.
