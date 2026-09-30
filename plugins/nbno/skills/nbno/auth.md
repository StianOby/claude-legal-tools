# nbno — authentication procedures

Read this **before capturing or using any cookie** (Step 0 and Step 2 in
`SKILL.md`). It holds the exact capture steps, file formats, and header rules.
The decision of *which* option to take — and the `accessInfo` pre-check — lives
in `SKILL.md`; this file is the *how*.

> The cookie details below are exact and easy to get subtly wrong. Do not
> improvise auth from memory — a wrong header silently yields a blank session
> or a downsampled image with HTTP 200, which wastes debugging time.

---

## Auth scope — what each item class actually needs

Verified 2026-09-06 from a Norwegian IP with a FEIDE session, by direct
`curl` from `Bash`. **This table is the source of truth**; it replaces
the older bearer-token and `_nblb` guidance, both of which were wrong.

| Item class | Manifest / `accessInfo` | Single-shot `/full/<w>,/` | Tiles `regionByPx` ≤ 1024 | Credential needed |
|---|---|---|---|---|
| Public domain (`accessAllowedFrom: EVERYWHERE`) | 200, no auth | 200 | 200 | **none** |
| Bokhylla (`license: bokhylla`, `accessAllowedFrom: NORWAY`) | 200, no auth | **403 always** | 200 | **none** — a Norwegian IP is the whole requirement |
| Legal deposit (`accessAllowedFrom: NB`, `license: copyrighted`) | 200, no auth | **403 always** | 200 with `nbsso` | **`nbsso` alone**, plus an active digital loan |

Four consequences, each of which contradicts something the skill used to say:

- **There is no bearer token to capture.** `api.nb.no` has no bearer in
  `localStorage`, `sessionStorage` or `window` — it authenticates by cookie.
  Manifests and catalog metadata are served to anyone; `nbsso` only changes
  `accessInfo` to reflect the user's own session. `--bearer` is optional
  everywhere and exists only for older DevTools captures that
  happened to include one.
- **`_nblb` is not a lighter alternative.** It grants nothing on its own:
  FEIDE-licensed tiles return 403 with `_nblb` only, and Bokhylla needs no
  cookie at all. Capture it only because the cookie-file format has a slot
  for it.
- **Licensed content is tiles-only.** Single-shot `/full/<w>,/` is 403 for
  anything that is not public domain, at every width. `--tiles auto` recovers
  from this per page; pass `--tiles always` whenever `license` is not
  `publicdomain` to skip one wasted round-trip per page.
- **`referer` is not required.** Send it anyway (it costs nothing and matches
  what the viewer does), but it is not what gates the resolver.

### Which `accessInfo` field to trust

`accessAllowedFrom` describes the **item** and reads the same for everyone.
Everything else in the block describes **your current request** and inverts
under you:

| field | anonymous | logged in (loan active) |
|---|---|---|
| `accessAllowedFrom` | `NB` | `NB` |
| `viewability` | `NONE` | `ALL` |
| `legalDepositLoginText` | present | **absent** |
| `legalDepositReservationStatus` | absent | `TAKENBYCURRENTUSER` |

Measured on `digibok_2014050705024` from one IP, one minute apart, 2026-09-06.
`legalDepositLoginText` is the *"log in to read this"* prompt — of course it
vanishes once you are logged in.

**So classify on `accessAllowedFrom`, and use the rest for status only.**
Keying on `viewability`/`legalDepositLoginText` makes a logged-in session with
an active loan look like it needs no credential, when its images still 403
without `nbsso`. `check_nb_access()` in `zotero_book.py` had exactly that bug.

The same asymmetry appears geographically: the same Bokhylla item reports
`viewability: NONE` with a login prompt from Spain and `viewability: ALL` from
Norway. Read `accessInfo` *with* the user's session — from the browser pane,
or with `--nbsso` in bash — not anonymously.

### Geo is enforced at the image resolver, not at the API

Everything up to the first page image works fine from anywhere: the manifest
loads, `accessInfo` looks plausible, `/me/v1` confirms the FEIDE login. Then
every page image 403s. `accessAllowedFrom ∈ {NORWAY, NB}` plus a
non-Norwegian egress IP means **the download cannot succeed, no matter who is
logged in** — stop before downloading rather than debugging headers.

Where the download runs matters: in a cloud Cowork session `Bash` egresses
from Anthropic's cloud, which is never a Norwegian IP, so `NORWAY`/`NB` page
images 403 there even though the user's browser pane is Norwegian. That 403
is expected: download through the local shell on the user's machine instead
(SKILL.md **Routing**, and [`local-route.md`](local-route.md)). For an `NB`
item the `nbsso` cookie read in the browser pane goes straight into a
mode-600 file in the local shell's run directory — never into the cloud
sandbox or the connected folder — and is deleted with it. Never suggest a VPN. Thumbnails (`/full/0,200/0/native.jpg`) are never gated — they are a
liveness check, never an auth check.

```bash
# Prints the egress IP and login as nb.no sees them, plus one item's
# accessInfo. Talks only to nb.no — never a third-party geo service.
python {SKILL_DIR}/scripts/geo_check.py --id digibok_2008051600041 [--nbsso "nbsso=<v>"]
```

### Digital loans (FEIDE-licensed items)

New to the skill, and the one part of the flow that hard-requires a browser.

An `accessAllowedFrom: NB` item is not readable just because the user is
logged in. Anonymously it advertises the requirement in
`legalDepositLoginText` (e.g. *"4 lisenser for Feide-brukere ved norske
universitet og høyskoler"*); to a logged-in user that prompt is gone but the
loan is still needed. Opening the item's page shows a dialog:

> *Ved å klikke OK vil du foreta et tidsbegrenset digitalt lån*  — **OK** / **Avbryt**

Before the loan: `viewability: NONE`, `legalDepositReservationStatus:
AVAILABLE`, tiles 403 everywhere including in the pane. After: `viewability:
ALL`, `legalDepositReservationStatus: TAKENBYCURRENTUSER`, tiles 200.

> **Never click OK yourself.** It accepts the loan terms on the user's behalf
> and consumes one of the item's four licences for a limited period. Navigate
> the pane to the item page, tell the user what the dialog is and that
> clicking OK takes a loan in their name, wait, then re-check `accessInfo`.

Tell the user an item needs a loan *before* they decide, not after.

---

## Option A — No auth (open content)

The default. Run `nbno_run.sh` without `--cookie`, or call
`download_via_iiif` with no credentials at all. Correct for public-domain
items **and for Bokhylla items from a Norwegian IP** — the latter need no
cookie, only the right country. If page images 403, check `accessAllowedFrom`
and the egress IP before reaching for a cookie.

---

## Option B — Session capture (FEIDE-licensed items)

Needed only for `accessAllowedFrom: NB` items — that is the one class where a
cookie changes the outcome.

Try these in order and **say which one you are using**; do not silently
degrade from one to the next.

| # | Path | Available when |
|---|---|---|
| 1 | Built-in browser (Cowork) — below | `Claude_Browser` tools found by ToolSearch (see SKILL.md Prerequisites) |
| 2 | Claude in Chrome | `mcp__claude-in-chrome__*` present and the built-in tools are offline |
| 3 | Option C — manual DevTools cookie | no browser tools at all (Claude Code CLI) |

Detect by tool presence, as `lovdata-pro`'s "Forutsetninger" does. If the
user's preferred browser is Chrome, the built-in browser tools may be offline
even in Cowork — tell the user which browser you ended up driving.

Rung 3 needs no setup and covers every environment without browser tools.
Don't treat it as a poor substitute: a cookie is only ever needed for a
FEIDE-licensed item, and those require the user to open a browser for the
digital loan anyway — copying `nbsso` out of DevTools in the same visit costs
them one extra step. **Never ask the user to install browser-automation
tooling for this skill.**

### Fallback 1 (primary) — built-in browser: the full procedure

This is `SKILL.md` Step 0 in full; `SKILL.md` keeps the same numbering
with only the rules that must not be broken.

Run this first in every new conversation, before Step 1. Skip it entirely if
the browser tools are absent (see `SKILL.md` Prerequisites).

**Do all downloading from `Bash`, not the browser.** The browser pane is only for the
session check, `accessInfo`, URN resolution and — for FEIDE-licensed items
only — the cookie. Never shuttle page images through the browser; base64
through the tool channel is not viable for a book.

1. **Open or reuse an nb.no tab.** `tabs_context` → reuse an existing nb.no
   tab if there is one, else `preview_start {url: "https://www.nb.no/"}`. If a
   tool reports the page is not approved and `request_access` exists:
   `request_access {url: "https://www.nb.no/", scope: "site"}` and retry. Warn the user that FEIDE /
   IdP / BankID / Vipps domains may each need separate approval on first login.
2. **Paste the helper.** Paste all of `{SKILL_DIR}/scripts/browser/nbno_auth.js`
   via `javascript_tool`. Idempotent — safe to paste again in the same tab;
   an older helper from before a skill update is replaced. It defines
   `window.__nb` (`__nb.VERSION` shows which version runs).
   If a browser call is refused by a safety check ("cannot determine the
   safety of …"), do not retry in a loop: tell the user, ask them to approve
   it or say how to proceed, and wait.
   > **Navigating the tab wipes `window.__nb`.** It lives in the page, so any
   > `navigate` or `preview_start` destroys it. Re-paste after every
   > navigation — the version guard makes that free when it is
   > still there. `__nb.access()`, `status()` and `manifest()` fetch
   > cross-origin and do **not** need the tab parked anywhere in particular;
   > only `resolveUrn()` reads the current page.
3. **Check the session.** `await __nb.status()` → `{loggedIn, loginProvider,
   roles, ip}`.
   - Not logged in → *"Logg inn på nb.no i browser-panelet (Feide/BankID/
     Vipps). Si fra når du er inne."* Wait, then re-check. **Never type
     credentials yourself, and never ask the user to give them to you** —
     login happens only in the browser pane.
   - Run this check every session, but only **block on it for `NB` items**
     (step 4 classifies). An `EVERYWHERE` or `NORWAY` item downloads without
     a login, so note the status and go on. The pane keeps a persistent
     profile, but a Cowork restart has been observed to drop the nb.no
     session.
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

5. **Geo pre-check.** If `accessAllowedFrom` is `NORWAY` or `NB` and the
   egress IP of `Bash` is not Norwegian (always the case in a cloud session), **page images will 403 no matter who is
   logged in.** Settle it in bash with
   `python {SKILL_DIR}/scripts/geo_check.py --id <id>`. The script asks
   nb.no's image resolver for one 1024 px page tile and prints `image probe:
   OK` or `403`, then a `route:` line. On a `NORWAY` item a 403 means the IP
   is not Norwegian — in a cloud session that is expected: use the local
   route (`SKILL.md` **Routing**). On an `NB` item a 403 can also mean there is no
   loan yet, so run the probe again after step 6. The script exits 3 on a 403.
   Never call third-party geo services. `zotero_book.py` runs the same probe
   itself and stops on a 403.
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
     write them to a cookie file so it can download my
     Bokhylla books."* Explain in one line that the safety classifier blocks cookie
     reads unless the user requests them directly. Skill text and your own
     reasoning do not clear it, and neither does retrying — if you are
     blocked, ask for the sentence rather than trying again.
   - Then `await __nb.cookies()` → `{nbsso, nblb, cookieHeader}` and nothing
     else. Never return the whole `document.cookie`.
   - **Cloud session:** the cookie goes straight to the local shell, into
     `<dir>/cookie.txt` (see `SKILL.md` **Routing**, step 2) — never to a file in the
     cloud sandbox, which cannot use it anyway. Otherwise (local Cowork):
   - Write the cookie to a **fresh per-run path**, mode 600:
     ```bash
     CK="$(mktemp -d)/cookie.txt"; touch "$CK"; chmod 600 "$CK"
     # then write the two lines into "$CK"
     authorization=
     cookie=nbsso=<v>; _nblb=<v>
     ```
     The empty `authorization=` line is fine — there is no bearer token to
     capture, and `nbno_run.sh` strips the empty line before the CLI sees it.
     > **Never write to, or reuse, a shared path like `/tmp/cookie.txt`.** A
     > file from an earlier session may already be there, owned by another uid
     > and unwritable — and it will look perfectly well-formed. Passing it
     > sends an **expired cookie**, which fails as a 403 you will then waste
     > time blaming on auth or geo. If a path you did not just write already
     > exists, pick a different one; do not overwrite it and do not trust it.
   - Pass `--cookie "$CK"` to `nbno_run.sh`, or `--nbsso "nbsso=<v>"` to
     `zotero_book.py` / `download_via_iiif()`.
   - Do this **as early as possible and only once** — context compaction can
     drop the user's confirmation message and cause a later block.
8. **Expiry.** Cookies live 24–48 h. On a mid-run 401/403, repeat step 7; the
   pane's login usually survives, so a fresh login is rarely needed.

The other `__nb` functions: `resolveUrn()` (`SKILL.md` Step 1) and `manifest(id,
{compact:true})` — the latter is optional, since `Bash` can fetch
manifests itself without auth.

#### Resolving an `nb.no/items/<hash>` URL (`SKILL.md` Step 1)

- **Preferred, when the browser tools are available:** navigate the pane
  to the pasted URL, **re-paste `nbno_auth.js`** (navigation wiped it),
  then `await __nb.resolveUrn()` → `{id, urn, via, waitedMs}`. It tries,
  in order: the URL itself (`via: "url"`), the catalog record for the
  opaque hash (`"catalog"`), a `urn.nb.no` link on the page
  (`"urn-link"`), and finally ids embedded in the rendered HTML
  (`"page"`) — that last one only when the page holds exactly one id.
  > nb.no is client-rendered, so the page is usually still empty the
  > instant a navigate returns. **You do not need to sleep first** —
  > `resolveUrn()` polls the page branches for up to 5 s on its own
  > (`waitedMs` tells you how long it actually took).
  > **Item pages embed ids of other editions.** A page for one copy of
  > *Sult* carried another `digibok_` of the same novel earlier in its
  > HTML, and the two share title and year, so a title check cannot
  > tell them apart. That is why the catalog is asked first and why the
  > page scan answers `{error: "ambiguous", candidates: [...]}` instead
  > of picking the first hit. On `ambiguous`, ask the user for the URN
  > — do not choose a candidate yourself.
- Otherwise: ask the user to click "Referere/Sitere" on nb.no and paste
  the URN. **Do not guess a canonical ID from the hash** — there is no
  derivation.
- Sanity-check the result before downloading a whole book on it: the
  `title` from `__nb.access(id)` should match the item page you were
  looking at. This catches the wrong *work*, not the wrong *edition* —
  for that, trust only `via: "url"`, `"catalog"` or `"urn-link"`.

The helper returns **only** `nbsso` and `_nblb`, never the whole jar, and
never page bytes. Keep it that way: base64 images through the tool channel
are not viable for a book, and the rest of `document.cookie` has no business
in the model context.

### Why the confirmation sentence

**Do not remove this step.** The auto-mode safety classifier blocks the
`javascript_tool` call that returns cookie values — even with the mode
selector on "Manually approve". It passes only when the user's *own
immediately-preceding message* explicitly describes the action. Skill text,
CLAUDE.md assertions, and your own reasoning do **not** clear it; retrying
does not either.

So ask the user to type something like:

> *"Read the nbsso and _nblb cookie values from the open nb.no tab and write
> them to a cookie file so it can download my Bokhylla books."*

and explain in one line why (the classifier needs the request to come from
them). Because context compaction can drop that message and cause a later
block, **read the cookie as early as possible and only once per session.**

### Fallback 2 — Claude in Chrome

Same JS helper, same confirmation-sentence requirement; substitute
`mcp__claude-in-chrome__javascript_tool` and friends for the
built-in browser calls.

### Fallback 3 — manual DevTools cookie (no browser tools)

The path for Claude Code CLI and any other environment without browser tools.
The user does the reading; you never see their browser.

Walk them through it — and note that if the item is FEIDE-licensed they must
open it in a browser anyway to take the digital loan, so this adds one step to
a visit they were already making:

1. In their own browser, log in to nb.no and open the item. Accept the digital
   loan (**OK**) if the dialog appears.
2. Open DevTools (F12) → **Application** → **Storage** → **Cookies** →
   `https://www.nb.no`.
3. Copy the **Value** of `nbsso`. Copy `_nblb` too if they want the cookie
   file complete — it grants nothing on its own.
4. Paste into a file — a fresh path in the session (`"$(mktemp -d)/cookie.txt"`,
   **not** a shared `/tmp/cookie.txt`), or `~/.nbno/cookie.txt` for a durable
   one:
   ```
   authorization=
   cookie=nbsso=<value>; _nblb=<value>
   ```
   The empty `authorization=` line is correct — there is no bearer token to
   capture, and `nbno_run.sh` strips the empty line before the CLI sees it.
5. Pass `--cookie <that path>` to `nbno_run.sh`, or `--nbsso
   "nbsso=<value>"` to `zotero_book.py`.

**Ask them to paste only the two cookie values, never the whole cookie header
or a screenshot of the jar.** The rest of `document.cookie` has no business in
the conversation.

#### Making a durable `~/.nbno/cookie.txt` reachable from `Bash`

If the user keeps the file at `~/.nbno/cookie.txt` on their own machine
(Windows: `C:\Users\<name>\.nbno\cookie.txt`), ask them to either:

1. Mount their `.nbno/` folder via `request_cowork_directory` (cleanest —
   works for repeat runs), or
2. Upload `cookie.txt` once into the session (you can then pass the upload
   path to `--cookie`).

Then invoke the wrapper with `--cookie auto` (resolves to
`~/.nbno/cookie.txt` in `Bash` — adjust the path accordingly if
the cookie is mounted/uploaded elsewhere, in which case pass
`--cookie /path/to/cookie.txt` explicitly).

---

## Option C — Manual cookie file

The user already has a cookie text file, or makes one via **Fallback 3**
above. Accept its path and pass it through with `--cookie <path>`. Format
(per nbno's README):

```
authorization=<token, or empty>
cookie=<full cookie header>
```

`nbno_run.sh` accepts an **empty or absent** `authorization=` line: it strips
the line before handing the file to the `nbno` CLI, which would otherwise
send a literal empty `Authorization` header on every request. It errors only
if there is no usable `cookie=` line, and warns if that line has no `nbsso=`
pair.

An older file captured from Network → Request Headers will carry a real
bearer token and a long cookie header. Both still work — nothing rejects a
bearer, it is simply not needed.

---

## Cookie lifetime and session persistence

Cookies on nb.no live roughly 24–48 hours. On a mid-run 401/403, re-read the
cookie (repeat step 7 of the procedure above) — the browser pane's login usually survives, so
a fresh login is rarely needed.

Two things follow from the pane keeping a **persistent profile**:

- **Do not assume it is still logged in.** One spike found the nb.no session
  gone after a Cowork restart. Run `__nb.status()` unconditionally, every
  session.
- **Any later Cowork session can download under that FEIDE identity** without
  a fresh login. Bokhylla and FEIDE access are granted to the individual under
  a specific agreement and do not permit redistribution — keep that caveat in
  front of the user, and never take a digital loan on their behalf.
