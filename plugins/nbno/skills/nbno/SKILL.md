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
  Do NOT use for: Lovdata legal texts (use lovdata-api / lovdata-pro), generic web
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
- **Auth**: Prompt every time an item needs a credential (`NB`, FEIDE).
  Before such a run, ask the user which auth path in **Step 2** to take.
  `EVERYWHERE` and `NORWAY` items need no credential — don't ask. The default cookie location is `~/.nbno/cookie.txt`
  when the user keeps a durable one.

## Prerequisites

- **Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for
  this skill:" if it exists in bash. Otherwise resolve it once and use the
  printed path literally in later commands:
  ```bash
  for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/nbno}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/nbno/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
  ```
- **`nbno` CLI** — the wrapper installs it automatically on first run via
  `pip install --break-system-packages nbno`. If auto-install fails, run
  that command manually before proceeding.
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
     (step 2). For `norwegian-ip+loan` do Step 0.6–0.7 first (loan, cookie).
   - `route: unknown` → report the probe line and ask before downloading.
2. **Local route** — follow [`local-route.md`](local-route.md) (it decides whether `device_bash` and a connected folder
   are available and has the fixed messages if not). **Check for a connected folder first** (`ls -d "$HOME"/mnt/*/`
   in `device_bash`; if none, ask for one as `local-route.md` §1 says) — `device_bash` refuses to run without one.
   For nbno, once `READY <dir>` is printed:
   - Probe again from the user's machine, in `device_bash`:
     `test -f <dir>/.ready || exit 4; PYTHONUTF8=1 python3 <dir>/scripts/geo_check.py --id <id>` (add
     `--nbsso "nbsso=<v>"` for `NB`). `route: here` → go on. `norwegian-ip` → the user's IP is not Norwegian; tell
     them and stop. `norwegian-ip+loan` → ask the user to log in again / retake the loan in the browser pane, re-read
     the cookie, retry **once**, then stop.
   - `NB` only: put the cookie in a mode-600 file inside `<dir>`, never in the connected folder:
     `umask 077; printf 'authorization=\ncookie=nbsso=%s; _nblb=%s\n' '<nbsso>' '<nblb>' > <dir>/cookie.txt`
   - Download with the same commands as in Step 3 / [`zotero-ready.md`](zotero-ready.md), calling the scripts by
     absolute path (`bash <dir>/scripts/nbno_run.sh …`, `python3 <dir>/scripts/zotero_book.py …`) with
     `--out <dir>/out` (plus `--cookie <dir>/cookie.txt` for `nbno_run.sh`, or `--nbsso "nbsso=<v>"` for
     `zotero_book.py`). A 3-page range took 5–13 s on 2026-09-30; keep ranges modest until longer runs are tried.
     `nbno_run.sh` makes a short-lived copy of the cookie in `$TMPDIR` and deletes it on exit.
   - OCR / Zotero-ready: first `command -v tesseract`. Present (tesseract 4.1.1 with `eng`/`osd` only on
     2026-09-30) → `zotero_book.py` fetches `nor` and pip-installs `ocrmypdf` into the run directory itself.
     Missing → `--no-ocr`. Either way, if `zotero_book.py` exits **5**, OCR failed but the PDF and RDF are complete:
     deliver them and use message **C** from `local-route.md`. Do not re-run just to retry OCR.
   - Copy the finished PDF (and RDF) to `<connected folder>/nbno/<id>/`, tell the user where it is, then
     `rm -rf <dir>` (this also removes the cookie).

Never fall back silently to the cloud sandbox for a `NORWAY`/`NB` item, never debug headers after a geo 403, and never
suggest a VPN.

---

## Step 0 — Session (Cowork built-in browser)

Run this first in every new conversation, before Step 1. Skip it if the
browser tools are absent (see Prerequisites). The full procedure, with the
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
4. **Classify.** `await __nb.access("<id>")` → classify on
   **`accessAllowedFrom` only** (`EVERYWHERE` open · `NORWAY` Bokhylla, no
   cookie, tiles only · `NB` legal deposit, `nbsso` + loan, tiles only).
   `viewability` and `legalDepositLoginText` flip when you log in — status,
   never classification.
5. **Geo.** `NORWAY`/`NB` → run the probe and follow **Routing** above.
6. **Loan (`NB` only).** If `legalDepositReservationStatus !=
   "TAKENBYCURRENTUSER"`, navigate the pane to the item page. **Never click
   OK yourself** — it takes one of the item's four licences in the user's
   name. Ask the user to click it, then poll `await __nb.loanStatus("<id>")`.
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
   converted. With the browser tools: navigate the pane to the URL, paste the helper again (same file)
   the helper, `await __nb.resolveUrn()` → `{id, urn, via}`. On
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
book. `--start`/`--stop` are 1-based **canvas** numbers, not printed pages:
download canvases 1–7 first to find the offset.

- **Short ranges, non-book material:** the `nbno_run.sh` wrapper (below).
- **Whole books:** `zotero_book.py` (with `--no-ocr --no-shrink` if the user
  only wants the images), or its in-process downloader `download_via_iiif()`
  — about 20× faster than the wrapper. Usage, the resolver's traps and the
  inline recipe: [`iiif-download.md`](iiif-download.md). Anything not public
  domain is tiles-only: pass `--tiles always`.

```bash
OUT=$(mktemp -d)
bash {SKILL_DIR}/scripts/nbno_run.sh --id "digibok_2008051600041" --out "$OUT" \
  [--start 1 --stop 7] [--cookie <file>] [--resize 75] [--title]
```

| flag | purpose |
| --- | --- |
| `--start N` / `--stop N` | canvas range (1-based, inclusive) |
| `--cookie PATH` / `--cookie auto` | cookie file (`auto` = `~/.nbno/cookie.txt`); `NB` items only |
| `--resize N` | percent of original size — prefer `shrink_pdf.py` afterwards (Step 4) |
| `--title` · `--cover` · `--keep-images` | title as folder name · cover separately · keep page images in `<out>/<ID>_images/` |

The wrapper builds one PDF in `--out` (never pass `--pdf` yourself) and
rescales nbno's poster-size pages to book size.

- **Timeouts:** request a long bash timeout (600000 ms) but plan for ~170 s
  per call. Downloads fit (424 pages ≈ 105 s); OCR of a long book does not —
  use `--no-ocr` and `ocr_chunked.py` ([`reading-ocr.md`](reading-ocr.md)).
  **Never `nohup … &`**: the process dies when the call returns.
- **Scratch, then copy, in one call:** `--out` must be a scratch dir
  (`mktemp -d`), not a mounted folder (`mv: unable to remove target`).
  Shell variables and scratch may not survive to the next call, so create
  `$OUT`, run and copy the result in the same call.

For reading pages visually, OCR and shrinking, read
[`reading-ocr.md`](reading-ocr.md) first.

---

## Step 4 — Hand the file back

- **Shrink books:** `zotero_book.py` does it by default; any other PDF over
  ~50 MB (`nbno_run.sh` prints a `[hint]`) →
  `python {SKILL_DIR}/scripts/shrink_pdf.py --pdf <file>`. Order is always
  full resolution → OCR → shrink; never `--resize` to save space. Say what
  size the PDF ended up.
- **Deliver:** copy it to the outputs directory (`/mnt/user-data/outputs` in
  cloud Cowork) and share it with `SendUserFile`, which refuses files
  over 30 MiB: then just say where the PDF is. Local-route results are
  already in `<connected folder>/nbno/<id>/`; say where (send one only if it
  is under 30 MiB, after `device_stage_files` — see `local-route.md` §3).
- **Say what it is, when you deliver it:** a canvas range is an **excerpt**
  (name the canvases and, if known, the printed pages); placeholder pages
  (exit 3) are missing pages; exit 5 means no text layer.
- Don't narrate the contents; let the user open it.

---

## Zotero-ready books

For "Zotero-ready", "RDF with the PDF attached", "OCR and import this book":
read [`zotero-ready.md`](zotero-ready.md) first. `zotero_book.py` downloads,
adds a text layer (nb.no's own OCR for public-domain books, Tesseract
otherwise), shrinks and writes a `.pdf` + `.rdf` pair; drag the `.rdf` into
Zotero. `--start/--stop` make an excerpt (files get a `_c<N>-<M>` suffix).

```bash
python {SKILL_DIR}/scripts/zotero_book.py --id URN:NBN:no-nb_digibok_2008051600041 \
  --out "$OUT_DIR" --tiles always [--nbsso "nbsso=<v>"] [--start 1 --stop 20]
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
