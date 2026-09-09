# Lovdata Pro — URL & DOM mapping

This file captures what we observed exploring `lovdata.no/pro` (originally with
Playwright; the skill now drives Claude Desktop's built-in browser instead —
see `SKILL.md`). It's the source of truth for the URL and selector logic in
`scripts/browser/lovdata_pro.js`. When Lovdata changes their site, update this
file alongside the script.

---

## The one URL pattern that matters

Every Pro document is server-rendered as a single HTML page at:

```
https://lovdata.no/pro/document/<COLLECTION>/<TYPE>/<SLUG>/*
```

The trailing `/*` is the critical bit — it triggers the in-iframe
"Hele dokumentet" link (`<a id="allParts" class="partNavigation allParts">`)
behaviour. Without it, the URL returns only a small TOC stub for forarbeider.
The trailing `?showmarkings=true` is harmless but unnecessary for our purposes.

**Confirmed working examples (full HTML body returned):**

| Reference                        | Path                                                |    Bytes |
| -------------------------------- | --------------------------------------------------- | -------: |
| Ot.prp. nr. 3 (1998-99)          | `PROP/forarbeid/otprp-3-199899/*`                   |     1.3M |
| HR-2016-2554-P (Holship)         | `HRSIV/avgjorelse/hr-2016-2554-p/*`                 |     248K |
| NOU 2022:8 (Ny minerallov)       | `NOU/forarbeid/nou-2022-8/*`                        |     2.8M |
| Prop. 71 L (2024-2025)           | `PROP/forarbeid/prop-71-l-202425/*`                 |     2.4M |
| Innst. 521 L (2024-2025)         | `INNST/forarbeid/inns-521-l-202425/*`               |        ? |
| LG-2008-135938                   | `LGSIV/avgjorelse/lg-2008-135938/*`                 |      42K |

Without the `/*`, forarbeider return ~7 KB of just the table-of-contents — the
SPA lazy-loads chapters when you click them. Case-law decisions appear to
return the full document either way (Holship returns 248 KB at both URLs).

---

## Collection prefixes

Observed during exploration. **Rettspraksis** (`avgjorelse`) first:

| Citation form              | Collection | Type slug   | Notes |
| -------------------------- | ---------- | ----------- | ----- |
| `HR-YYYY-N-A/B/P/F/...`    | `HRSIV` (sivil) / `HRSTR` (straff) | `avgjorelse` | Modern Supreme Court |
| `Rt. YYYY s. N`            | `HRSIV` / `HRSTR` | `avgjorelse` | Pre-2008 Supreme Court. Slug pattern: `rt-YYYY-PAGENUMBER-SUFFIX` where SUFFIX is a Lovdata-assigned sequential number (e.g. `rt-2000-1811-hrsiv`). **The suffix cannot be guessed deterministically — use Pro UI search.** Some page numbers have two separate documents (e.g. `rt-1938-584-166` is a short tvistemål stub; `rt-1938-584-176` is the substantive case). When a short result appears for an old case, try the next sequential suffix before treating it as a dead end. |
| `LG-YYYY-N`                | `LGSIV` (Gulating sivil) | `avgjorelse` | Lagmannsrett: prefix encodes court (LB Borgarting, LA Agder, LF Frostating, LH Hålogaland, LE Eidsivating) and division (SIV / STR) |
| `LB-YYYY-N`                | `LBSIV` / `LBSTR` | `avgjorelse` | Borgarting lagmannsrett |
| `RG YYYY s. N`             | varies — older RG cases sit under whichever lagmannsrett actually decided them. Pro renders them via Tingrett (`TRSIV`) when search is the only path | `avgjorelse` | Slugs are irregular; runtime search needed. Search for Lovdata's own reference form (`RG-2010-100`), not the prose citation — `lovdata_ref.py` returns that as `search_hint` |

**Complete lagmannsrett collection table:**

| Court code | Court name         | Civil   | Criminal |
| ---------- | ------------------ | ------- | -------- |
| LB         | Borgarting         | `LBSIV` | `LBSTR`  |
| LA         | Agder              | `LASIV` | `LASTR`  |
| LE         | Eidsivating        | `LESIV` | `LESTR`  |
| LF         | Frostating         | `LFSIV` | `LFSTR`  |
| LG         | Gulating           | `LGSIV` | `LGSTR`  |
| LH         | Hålogaland         | `LHSIV` | `LHSTR`  |

**Tingrett references carry a court prefix, not a bare `TR-`.** Lovdata
cites district courts as `TOSLO-2019-12345` (Oslo tingrett, pre-2021
court reform), `TOSL-2022-123456` (post-reform), `TBERG-`, `TSTAV-`,
`THOD-`, and so on — the letters after `T` abbreviate the court. The
collection is `TRSIV`/`TRSTR` for all of them. `lovdata_ref.py` accepts
any `T<letters>-YYYY-N` form and lower-cases the reference into the slug,
trailing `-1`/`-2` included.
**Confirmed live (September 2026):** `TOSLO-2019-108726-2` →
`TRSIV/avgjorelse/toslo-2019-108726-2`, `TOSL-2022-105703` →
`TRSTR/avgjorelse/tosl-2022-105703`. As with the other court collections the
SIV/STR split is by subject matter, and `tryPaths()` swaps automatically.

**Forarbeider** (`forarbeid`):

| Citation form              | Collection | Type slug   | Notes |
| -------------------------- | ---------- | ----------- | ----- |
| `Ot.prp. nr. N (YYYY-YY)`  | **`PROP`** for ≥1968-ish, older may be `OTPRP` (not yet confirmed in Pro) | `forarbeid` | Slug: `otprp-N-YYYYYY` (year encoded as 6 digits, no separators) |
| `Prop. N L/S/Stortingsm.`  | `PROP` | `forarbeid` | Slug: `prop-N-l-YYYYYY` (lowercase L, year as 6 digits) |
| `NOU YYYY: N`              | `NOU` | `forarbeid` | Slug: `nou-YYYY-N` (a/b suffix when split into parts: `nou-2001-32a`, `-32b`) |
| `Innst. N L (YYYY-YY)`     | **`INNST`** | `forarbeid` | Slug uses `inns-` (not `innst-`): `inns-521-l-202425` — note the collection/slug mismatch |
| `Innst. O./S. nr. N (YYYY-YY)` | `INNST` | `forarbeid` | Pre-2009 committee recommendations. Same `inns-` rule with the chamber letter: `inns-o-45-200405`, `inns-s-12-200405`. Confirmed live |
| `Meld. St. N (YYYY-YY)` / `St.meld. nr. N` | **`STS`** | `forarbeid` | Slug `stsg-<sesjon>-<løpenummer>`: Meld. St. 17 (2020-2021) → `STS/forarbeid/stsg-202021-352`, St.meld. nr. 12 (2006-2007) → `STS/forarbeid/stsg-200607-255`. **The løpenummer is Lovdata-assigned and not derivable from the citation** — same class of problem as pre-2008 Rt. suffixes, so `lovdata_ref.py` returns `parsed:false` and a search hint. There is no `MELD` collection |
| `St.prp. nr. N (YYYY-YY)`  | — | — | Non-law propositions are not full-text indexed. Four Hurtigsøk queries for St.prp. nr. 100 (1991-92) surfaced only EEA-annex directives, never the proposition. Treat as "not in Pro" |
| `Dok. 8:N`                 | `REPFOR` | `forarbeid` | `dok8-12-199900`. Confirmed live |
| `NOU YYYY:N` (pre-~1975)   | `PUBG` | `pubg-YYYYYY-nou-N` | Historical publications. E.g. NOU 1972:16 → `PUBG/pubg-197273-nou-16`. **Returns metadata only (~468 chars), not full text.** Year range encoded as 6 digits same as forarbeider. |

### Year encoding rule (forarbeider)

Slug encoding: full first year (4 digits) followed by the last two of the
second year. `(2024-2025)` becomes `202425`, `(1998-99)` becomes `199899`,
`(1961-62)` becomes `196162`. Six digits, no separator. We confirmed this
matches Pro's actual slugs for the documents in our test set.

### Coverage cutoff (forarbeider)

Official Lovdata Pro coverage by document type:

**Propositions (Ot.prp. / Prop. L):**
- Full text from session **1984/85** onwards for all law-related propositions.
- Selected older Ot.prp. also have full text.
- Non-law propositions (St.prp., etc.): header + PDF link only — not indexed
  as full-text forarbeider regardless of age.
- Page numbers appear **only in PDF** from 2024 onwards (all propositions
  from session 2025/26).

**NOU:**
- Full text from **1994** onwards (all NOUs); PDF also from 2003.
- **1985–1993**: many have only summary or TOC; but many pre-1985 NOUs for
  central legal areas are available in full text.
- Pre-1985 NOUs may appear under the `PUBG` collection (often metadata-only).

**Other reports:**
- NUT series ("Innstillinger og Betenkninger", predecessor to NOU) available,
  including all Rådsegn from Sivillovbokutvalget.

**Innstillinger:**
- Law-related from session **1991/92** onwards; some older ones also available.
- Other Innstillinger + budget from session **1992/93** onwards.

When a slug 404s and search returns no plausible match, surface a "likely not
in Lovdata Pro as full text" message rather than a generic "document not
found".

### Division (SIV vs STR)

Court collections come in pairs: civil (`...SIV`) and criminal (`...STR`).
`lovdata_pro.js` must try both when the citation doesn't disclose which.

**The split is by subject matter, not era.** HRSTR is not only for old Rt.
cases — recent Høyesterett decisions in criminal matters also live in HRSTR.
Heuristic: if the case involves straffeloven, straffeprosess, or EMK artikkel
6 (fair trial / uskyldspresumsjonen), try HRSTR first. Example: HR-2025-813-A
(TikTok) is HRSTR despite its modern identifier.

**Redirect URL reveals the correct collection.** If you navigate to a
wrong-collection URL in the SPA (e.g., `#document/HRSIV/avgjorelse/hr-2025-813-a`),
Lovdata Pro silently updates the hash to the correct collection
(`#document/HRSTR/avgjorelse/hr-2025-813-a`). Use this as a manual
collection-discovery technique when debugging: navigate, read the redirected
hash, then use that collection in subsequent fetch calls.

`lovdata_pro.js`'s `tryPaths()` function automatically tries the SIV/STR
counterpart whenever a collection-mismatch response is detected, so callers
(i.e. `load()`) need not enumerate both variants explicitly.

---

## Authentication

- Login is via SSO/FEIDE/email-password depending on the user. The skill never
  stores or sees credentials — it asks the user to log in interactively inside
  Claude Desktop's built-in browser pane (Cowork).
- The built-in browser has a persistent profile on the user's own machine, so
  cookies (including the HttpOnly session cookie) persist across turns and
  conversations without the skill saving or reading them itself — unlike the
  Playwright-era script, there is no `storage_state.json` and nothing for the
  skill to manage on disk.
- Logged-in landing page: `https://lovdata.no/pro/#myPage` — title becomes
  `Min side - Lovdata Pro`. `__lp.isLoggedIn()` uses this as a "still logged
  in" probe before every fetch.
- **Spike 2 findings** (confirmed 2026-09-05): `location.hash` is **not** a
  usable discriminator — it stays `#myPage` in both the logged-in and
  logged-out states (Lovdata swaps the rendered content client-side without
  touching the hash). Only `document.title` distinguishes them:
  - Logged in: `"Min side - Lovdata Pro"`
  - Logged out: bare `"Lovdata"` (body text includes "Logg inn i Lovdata
    Pro")

  `isLoggedIn()` therefore checks `document.title` only.

---

## Search

Two layers:

1. **Free public `/sok` endpoint** (`https://lovdata.no/sok?q=...`) returns
   only documents available on the free site. **Forarbeider, older Rt./RG,
   and many other Pro-only documents are not surfaced here.** Useful only as
   a first-pass fallback for case law that's also on the free site.

2. **Pro search inside the SPA** is GWT-RPC over `LovdataPro/GWT.rpc?fulltextSearchService`.
   **Confirmed by spike 3 (2026-09-05):** the request/response is a
   comma-separated stream of numbers, type-tag characters, and string-table
   references (e.g. `//OK["o","Bx",0,0,425,0,5,0,0,0.0,0.0,...`) — GWT's
   positional serialization with an obfuscated string table, not JSON. No
   separate JSON/REST search endpoint exists to call directly; hand-parsing
   or replicating this format is impractical.
   - **The query is submitted by a `keyup` event (re-measured 2026-09-09).**
     Event-by-event isolation in a live session: an `input` event alone does
     **not** submit; a synthetic `keydown` does **not**; a synthetic
     `keypress` does **not**; a synthetic **`keyup`** with key Enter **does**
     (the hash went to `#result&id=2378&q=TOSL-2023*`). A *real* Enter
     keypress from the `computer` tool, with focus verified in the field,
     does **not** submit. A real click on the 🔍 button does.
     This corrects the earlier spike-4 conclusion ("only a real click
     works"), which had tested `input`/`keydown` but not `keyup`.
   - `__lp.search(query, n)` therefore does the whole thing in one JS call:
     set the value through the native setter, dispatch
     `keydown`/`keypress`/`keyup`, wait for the hash to become `#result…`,
     then read the anchors. Hash routing does not reload the page, so
     `window.__lp.cache` survives a search in the same tab.
   - `__lp.readSearchResults(n)` remains available for the fallback flow
     (`computer.type` + `computer.left_click` on the 🔍 button, located with
     `read_page` — `computer.screenshot` has been seen to fail with
     `UnknownVizError`). It reads `a[href^="#document/"]` anchors already in
     the DOM and takes no query.
   - **Pro rewrites the query**: it lower-cases the input and appends a
     truncation wildcard, so `TOSL-2022` is submitted as `tosl-2022*` and the
     hash reads `q=TOSL-2022*`. Never assert that the hash matches the query.
   - Each href has the form `#document/<COLLECTION>/<TYPE>/<SLUG>?searchResultContext=...&rowNumber=...&totalHits=...`
   - The first match is usually correct for direct-citation queries; for
     ambiguous queries `__lp.readSearchResults()` returns the top N and lets
     the caller pick.

Free-text search does NOT find the cited document by reference — it finds
documents that *cite* it, or documents whose full text happens to contain
the query terms. Example: searching «St.prp. nr. 100 1991-92 EØS-avtalen»
returns EU directives from the EEA annex (because the EEA Agreement
references those terms pervasively), not the proposition itself.

For exact-reference resolution, prefer direct slug patterns first and use
search only as a fallback. Pro's advanced search (`#search`) has a
`dokumentnr` field, but it's only visible after selecting a "Rettskilde"
first. Practical strategy: start with the Hurtigsøk; if the top result's
slug doesn't match the requested ref, fall back to the user.

---

## DOM — extracting the document body

The fully-rendered page at `/*` has this structure (from
`Ot.prp.nr.3 (1998-99)/*`):

```html
<div id="maincolOneColumn">
  <div id="lovdataDocument" class="commentWidget desktop">
    <div id="documentBody">
      <a class="namedAnchor" name="kap1"></a>
      <div class="documentButtonsBar part smallIcons …" id="documentButtons_kap1">…</div>
      <div data-level="1" data-id="KAPITTEL_1" class="morTag_b kapittel" id="KAPITTEL_1">
        <h2>1 Proposisjonens hovedinnhold</h2>
        <p class="morTag_am no-text-indent avsnitt">…body text…</p>
        …
      </div>
      …more KAPITTEL_N divs…
    </div>
  </div>
</div>
```

For text extraction, `lovdata_pro.js`'s `toText()` targets `#documentBody`
(not `#lovdataDocument` — that also wraps the separate `#documentMeta`
sidebar, which would leak metadata-table noise into every section/page and
break `sectionRange()`'s heading-to-heading walk) and:

- Strips `.documentButtonsBar` toolbars (per-chapter share/note icons) before
  extraction, via `stripNoise()`.
- Maps `<h1>`–`<h6>` to markdown-style `#`/`##`/… heading lines.
- Maps `<p>` to plain lines. **Lovdata emits no `<ul>`/`<ol>`/`<li>` at all**
  (NOU 2022:8 contains zero): litra and numbered points are one-row
  `<table class="listeItem">` elements whose depth is carried by a
  `leftMargin_N` class. `toText()` detects those and renders them as
  indented `a. text` lines rather than pipe rows, so a litra can be quoted
  and located. The `<li>` branch is kept for other markup but is currently
  dead on Pro documents.
- Preserves `<table>` as pipe rows (Pro uses real HTML tables for metadata
  blocks, and occasionally in body text).
- Within headings/`<p>`/`<li>`/table cells, `inlineText()` (not raw
  `textContent`) renders `<strong>`/`<b>` as `**bold**`, `<em>`/`<i>` as
  `*italic*`, and `<sup>` as `^superscript^`, so e.g. bold §-titles in
  statute text quoted inside forarbeider survive extraction instead of
  merging invisibly into the surrounding paragraph. Confirmed by a live
  check against `HRSIV/avgjorelse/hr-2016-2554-p` that Høyesterett's
  "(77)"-style avsnitt numbers are real DOM text, not CSS-generated
  content — see `NOTES.md` for that check and how to re-run it.
- Footnote/reference anchors (`<a class="namedAnchor">`) are left as-is;
  `inlineText()`/`toText()` just read text content so empty anchors
  contribute nothing.

Metadata block (title, dato, utgiver, henvisninger, etc.) sits in a `<table>`
under `#documentMeta` (falling back to `#documentBody` if that ID isn't
present for a given document type). `extractMetadata()` in `lovdata_pro.js`
picks the one table among possibly several whose rows look like genuine
key/value pairs (≥3 rows, keys ≤40 chars) and extracts it into a JSON payload
kept separate from the body text. It reads the cells with `inlineText()`, not
`textContent`, because the `Parter` row separates each party and its counsel
with `<br>` — the parties are **not** in the body text of a judgment, so this
table is the only place they appear.

---

## Failure modes seen during exploration

- **Status 200 with ~145 bytes, body contains "Javascript aktivert"** — this
  is a **collection mismatch signal**, not a session problem. It means you've
  hit the wrong SIV/STR collection. The fix is always to try the counterpart
  (`HRSIV` → `HRSTR` or vice versa). Diagnostic rule: `if len(result) < 500
  and "Javascript aktivert" in result`, retry with the other collection before
  assuming failure. `isCollectionMismatch()` in `lovdata_pro.js` detects this
  automatically and `tryPaths()` swaps the collection.
- **Status 200 with 4,765 bytes and title `LovdataPro`** — this is a
  client-side redirect stub. The URL is valid syntactically but the slug
  doesn't resolve to a Pro document. Treat this byte-count as a sentinel for
  "not found" alongside the 404/803-byte feilmelding page.
- **Status 200 with ~7,000-7,500 bytes and the document title set** — for
  forarbeider, this is the TOC-only stub returned without `/*`. Refetch with
  `/*` appended.
- **Status 404 + `Lovdata - feilmelding`** — straightforward: the slug is
  wrong. Fall back to Pro search.
- **A real page with a title and metadata but no body text** — header-only
  records (St.prp. and other non-law propositions, pre-1985 NOUs under
  `PUBG`, some meldinger). `load()` succeeds; the giveaway is
  `totalChars: 0`, which it now reports as `metadataOnly: true` with a
  warning. Nothing can be quoted from these.
- **A judgment with no headings at all** — HR-2016-2554-P and LG-2008-135938
  have zero `h1`–`h6`, so `toc` is empty and `section()` returns
  `no_headings`. Use `grep()`/`page()`. Some tingrett decisions do have
  headings, so this varies by document.
