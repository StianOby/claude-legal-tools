# nbno — authentication procedures

Read this **before capturing or using any cookie** (Step 2 Option B or C in
`SKILL.md`). It holds the exact capture steps, file formats, and header rules.
The decision of *which* option to take — and the `accessInfo` pre-check — lives
in `SKILL.md`; this file is the *how*.

> The header and cookie details below are exact and easy to get subtly wrong.
> Do not improvise auth from memory — a wrong header silently yields a blank
> session or a downsampled image with HTTP 200, which wastes debugging time.

---

## Option A — No auth (open content)

The default. Run `nbno_run.sh` without `--cookie`. Best when the user pasted
a URN for an old book, sheet music, public-domain photo, or any
`pliktmonografi_*` / `pliktperiodika_*` item. If the download fails with HTTP
401/403, fall back to Option B.

---

## Option B — Cookie capture (recommended for FEIDE / Bokhylla)

Use this when the item is in-copyright (Bokhylla) or the user mentions
FEIDE, BankID, Vipps, or "logged in."

> **⛔ STOP — MANDATORY BEFORE ANY FETCH IN COWORK MODE**
>
> Before running any fetch or navigation command, you **must** confirm the
> user has an active Nasjonalbiblioteket session. Do this first, every time:
>
> 1. Ask the user: *"Have you logged in to nb.no recently? If not,
>    please log in now at <https://nb.no> in your browser."*
> 2. Wait for confirmation before proceeding.
>
> **If you skip this step and the user is not logged in, every fetch will
> silently fail** (returning a JS-required page or a blank session error)
> and the resulting debugging will waste significant time. There is no
> reliable way to detect a missing session after the fact.

### Primary method for Cowork sessions — playwright MCP

In a Cowork session the most practical approach is to capture the cookie
directly via the `mcp__playwright__*` tools.

> **Before proceeding: check that Playwright MCP is installed.**
> Look for `mcp__playwright__*` tools in your available tool set. If they
> are absent, stop and tell the user:
>
> > "This method requires the **Playwright MCP** server — a browser
> > automation layer that lets Claude drive a real Chromium window and
> > inspect its network traffic. Without it I cannot capture the nb.no
> > authentication cookie automatically.
> >
> > Install it from the official repository:
> > [github.com/microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
> >
> > Once installed and connected to your Claude session (you may need to
> > restart the session), come back and I will continue from here."
>
> Do not proceed with steps 1–6 until `mcp__playwright__*` tools are
> confirmed available. Fall back to `capture_cookie.py` (below) or
> Option C (manual cookie file) if the user cannot install the MCP.

1. Navigate to nb.no and let the user complete login in the visible window.
2. Ask the user to open the book page in the viewer.
3. Call `mcp__playwright__browser_network_requests` filtered on `api.nb.no`
   to list recent requests.
4. Find the `manifest?fields=...` entry; call
   `mcp__playwright__browser_network_request` with `part: "request-headers"`
   on that entry to retrieve the `authorization` token.
5. Retrieve the cookie string separately with
   `mcp__playwright__browser_evaluate` using `() => document.cookie`.
6. Write both values to a two-line file (e.g. `/tmp/cookie.txt`):
   ```
   authorization=<token>
   cookie=<full cookie string>
   ```
   Pass this path as `--cookie /tmp/cookie.txt` to the wrapper.

> **Auth scope:** The `authorization` bearer token captured above is valid
> only for `api.nb.no` (the manifest API). The IIIF image resolver at
> `www.nb.no/services/image/resolver/` ignores the bearer token entirely —
> it authenticates via the `nbsso` session cookie plus a correct `referer`
> header. Both values are needed: bearer for the manifest, nbsso for images.
>
> **Lighter cookie often suffices for tiles.** In practice the `_nblb`
> session cookie alone has returned `200` on every IIIF tile request, without
> the full FEIDE bearer + `nbsso` combination. Try the lighter auth path
> first (just the session cookie + `referer`) and only escalate to capturing
> the full bearer token if tiles start returning `403`.

Cookies on nb.no live roughly 24–48 hours. When downloads start failing
with auth errors, repeat steps 3–6 to refresh the token.

### Alternative for repeated or automated use — `capture_cookie.py`

The skill ships a script at `scripts/capture_cookie.py` that opens a real
Chromium window, lets the user complete FEIDE/BankID/Vipps login
interactively, and writes the captured `authorization` + `cookie` headers
to `~/.nbno/cookie.txt`. This approach is better when you expect to run
multiple sessions and want a durable cookie file.

The script must run on the user's own machine (it needs a visible browser —
the sandbox has no display). On first run:

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

---

## Option C — Manual cookie file (legacy)

If the user already has a cookie text file from DevTools, accept its path
and pass it through with `--cookie <path>`. Format (per nbno's README):

```
authorization=<token>
cookie=<full cookie header>
```

The user obtains it from DevTools → Network → `manifest?fields=...` →
Request Headers, while logged in.
