---
name: nbno-skill
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

- **Output**: PDF only. Always run with `--pdf`, then delete the page-image
  folder after the PDF is built.
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

### Option A — No auth (open content)

The default. Run `nbno_run.sh` without `--cookie`. Best when the user pasted
a URN for an old book, sheet music, public-domain photo, etc. If the
download fails with HTTP 401/403, fall back to Option B.

### Option B — Auto-capture via Playwright (recommended for FEIDE / Bokhylla)

Use this when the item is in-copyright (Bokhylla) or the user mentions
FEIDE, BankID, Vipps, or "logged in." The skill ships a Playwright-based
capture script at `scripts/capture_cookie.py`. It opens a real Chromium
window at nb.no, lets the user complete login interactively (FEIDE 2FA,
BankID, etc.), listens for the IIIF `manifest?fields=...` request the page
fires when a book viewer loads, and writes the captured `authorization` +
`cookie` headers to `~/.nbno/cookie.txt` in the format `nbno` expects.

The script has to run on the user's own machine (it needs a visible
browser — the sandbox has no display). On first run:

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

Cookies on nb.no live roughly 24–48 hours. When downloads start failing
with auth errors, ask the user to re-run `capture_cookie.py`.

> Quick alternative without the script: in a Cowork session you can drive
> `mcp__playwright__*` tools yourself — navigate to nb.no, ask the user to
> complete login in the visible window, then call
> `mcp__playwright__browser_network_requests` after they open a book and
> pull the `authorization` + `cookie` headers from the manifest entry.
> Same end result; less reproducible than the script.

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

## Step 3 — Run the wrapper

> **Fetch only what you need.**
> Use `--start <int>` and `--stop <int>` to limit the download to a page
> range. Downloading a full book when you only need a few pages is slow,
> expensive, and stresses nb.no's servers. Always ask the user which pages
> they need before running without these flags.
>
> Examples:
> - Single page: `--start 42 --stop 42`
> - A chapter: `--start 10 --stop 35`
> - Full book: omit both flags

```bash
bash {SKILL_DIR}/scripts/nbno_run.sh \
  --id "digibok_2008051600041" \
  --out "/sessions/<your-session>/mnt/outputs/nbno" \
  [--cookie auto | --cookie /path/to/cookie.txt] \
  [--start 1 --stop 50] \
  [--resize 75] \
  [--title]
```

Useful nbno flags the wrapper passes through:

| flag | purpose |
| --- | --- |
| `--title` | fetch the item's real title and use it as the folder name |
| `--start N`      | first page to download (1-based)                      |
| `--stop N`       | last page to download (inclusive)                     |
| `--resize N`     | percentage of original size — use 50–75 for big books |
| `--title`        | fetch the item's real title and use it as folder name |
| `--cover`        | also download the cover separately                    |
| `--keep-images`  | skip deletion of the per-page image folder            |
| `--cookie auto`  | use saved auth at `~/.nbno/cookie.txt` (Bokhylla)     |
| `--cookie PATH`  | use saved auth at an explicit path                    |

After the wrapper completes you'll have a single `.pdf` in the chosen
output folder. The wrapper has already removed the per-page image folder
unless the user passed `--keep-images`.

---

## Step 4 — Hand the file back

Save the PDF inside the user's outputs directory and share it with a
`computer://` link, e.g.:

```
[View your PDF](computer:///.../outputs/nbno/<digibok_xxx>.pdf)
```

Do not narrate the contents of the PDF beyond what's needed; let the user
open it.

---

## Important caveats — surface these to the user when relevant

- **Geo-restriction.** A large share of nb.no's collection (especially
  Bokhylla / in-copyright material) is only accessible from Norwegian IP
  addresses. The sandbox running this script is **not** in Norway. Items
  outside the open collection will fail without a Norwegian session cookie
  or a VPN-routed cookie. Tell the user this if a download returns access
  errors.
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

---

## Troubleshooting

- *Command not found `nbno`.* See **Prerequisites** above.
- *Empty PDF / no images downloaded.* Almost always an auth or geo issue
  — go to Step 2 and either ask the user to run `capture_cookie.py`
  (Option B) or supply an existing cookie file (Option C).
- *`--cookie auto` errors with "no cookie file found".* The wrapper looked
  at `~/.nbno/cookie.txt` and didn't find one. Either the user hasn't run
  `capture_cookie.py` yet, or they ran it on their own machine but
  haven't mounted/uploaded the file into the sandbox. Walk them through
  Step 2 Option B again.
- *Auth used to work, now downloads fail with HTTP 401/403.* The cookie
  has expired (typical lifetime: 24–48h on nb.no). Re-run
  `capture_cookie.py`.
- *User pasted a `nb.no/items/<hash>` URL.* That hash is opaque; ask for
  the Referere/Sitere string (URN) instead. Don't guess.
- *User mentions `pliktavlevering` content.* Same flow — ID prefix will
  be `pliktmonografi_...` or `pliktperiodika_...`.
