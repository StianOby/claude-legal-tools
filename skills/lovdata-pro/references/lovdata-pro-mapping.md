# Lovdata Pro — URL & DOM mapping

This file captures what we observed exploring `lovdata.no/pro` with Playwright.
It's the source of truth for the script's URL and selector logic. When Lovdata
changes their site, update this file alongside the script.

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

Observed during exploration:

| Citation form              | Collection | Type slug   | Notes |
| -------------------------- | ---------- | ----------- | ----- |
| `HR-YYYY-N-A/B/P/F/...`    | `HRSIV` (sivil) / `HRSTR` (straff) | `avgjorelse` | Modern Supreme Court |
| `Rt. YYYY s. N`            | `HRSIV` / `HRSTR` | `avgjorelse` | Pre-2008 Supreme Court. Slug pattern: `rt-YYYY-PAGENUMBER-SUFFIX` where SUFFIX is a Lovdata-assigned sequential number (e.g. `rt-2000-1811-hrsiv`). **The suffix cannot be guessed deterministically — use Pro UI search.** |
| `LG-YYYY-N`                | `LGSIV` (Gulating sivil) | `avgjorelse` | Lagmannsrett: prefix encodes court (LB Borgarting, LA Agder, LF Frostating, LH Hålogaland, LE Eidsivating) and division (SIV / STR) |
| `LB-YYYY-N`                | `LBSIV` / `LBSTR` | `avgjorelse` | Borgarting |
| `RG YYYY s. N`             | varies — older RG cases sit under whichever lagmannsrett actually decided them. Pro renders them via Tingrett (`TRSIV`) when search is the only path | `avgjorelse` | Slugs are irregular; runtime search needed |
| `Ot.prp. nr. N (YYYY-YY)`  | **`PROP`** for ≥1968-ish, older may be `OTPRP` (not yet confirmed in Pro) | `forarbeid` | Slug: `otprp-N-YYYYYY` (year encoded as 6 digits, no separators). **Watch out:** the `resolve` command sometimes emits `FORARBEID/forarbeid/otprp-...`, which 404s. Always use `PROP`. If a direct get returns 404 or near-empty content for an Ot.prp./Prop. L, retry with `PROP` in place of `FORARBEID`. |
| `Prop. N L/S/Stortingsm.`  | `PROP` | `forarbeid` | Slug: `prop-N-l-YYYYYY` (lowercase L, year as 6 digits) |
| `NOU YYYY: N`              | `NOU` | `forarbeid` | Slug: `nou-YYYY-N` (a/b suffix when split into parts: `nou-2001-32a`, `-32b`) |
| `Innst. N L (YYYY-YY)`     | **`INNST`** | `forarbeid` | Slug uses `inns-` (not `innst-`): `inns-521-l-202425` — note the collection/slug mismatch |
| `Meld. St. N`              | likely `MELD` | `forarbeid` | Not directly verified |
| `Dok. 8:N`                 | `REPFOR` | `forarbeid` | e.g. `dok8-12-199900` |
| `NOU YYYY:N` (pre-~1975)   | `PUBG` | `pubg-YYYYYY-nou-N` | Historical publications. E.g. NOU 1972:16 → `PUBG/pubg-197273-nou-16`. **Returns metadata only (~468 chars), not full text.** Year range encoded as 6 digits same as forarbeider. |

### Year encoding rule (forarbeider)

Slug encoding: full first year (4 digits) followed by the last two of the
second year. `(2024-2025)` becomes `202425`, `(1998-99)` becomes `199899`,
`(1961-62)` becomes `196162`. Six digits, no separator. We confirmed this
matches Pro's actual slugs for the documents in our test set.

### Coverage cutoff (forarbeider)

Lovdata Pro doesn't index very old preparatory works. Confirmed absent:

- `Ot.prp. nr. 23 (1961-62)` — nothing at `PROP/forarbeid/otprp-23-196162`,
  `OTPRP/forarbeid/otprp-23-196162`, or in Pro search.
- `Innst. O. nr. 49 (1961-62)` — likewise absent.
- `St.prp. nr. 100 (1991-92)` (EEA ratification) — absent despite being a
  major document. Even some 1990s propositions are missing.

The practical floor for most forarbeider is around the **late 1960s**. A few
older NOUs may appear in the `PUBG` collection (metadata-only). When a slug
404s and search returns no plausible match, surface a clear "likely not in
Lovdata Pro" message rather than a generic "document not found".

### Division (SIV vs STR)

Court collections come in pairs: civil (`...SIV`) and criminal (`...STR`).
The script must try both when the citation doesn't disclose which.

---

## Authentication

- Login is via SSO/FEIDE/email-password depending on the user. The skill never
  stores or sees credentials — it launches a headed Playwright browser and
  asks the user to complete login interactively.
- Once logged in, Playwright captures `storage_state.json` (cookies + local
  storage). All subsequent requests reuse it in headless mode.
- The session cookie is HttpOnly, so it doesn't appear in `document.cookie`.
  Playwright's `context.cookies()` and `storage_state.json` capture it correctly.
- Logged-in landing page: `https://lovdata.no/pro/#myPage` — title becomes
  `Min side - Lovdata Pro`. We use that as a "still logged in" probe before
  every fetch session.

---

## Search

Two layers:

1. **Free public `/sok` endpoint** (`https://lovdata.no/sok?q=...`) returns
   only documents available on the free site. **Forarbeider, older Rt./RG,
   and many other Pro-only documents are not surfaced here.** Useful only as
   a first-pass fallback for case law that's also on the free site.

2. **Pro search inside the SPA** is GWT-RPC over `LovdataPro/GWT.rpc?fulltextSearchService`.
   The wire format is positional Java-typed serialization — too brittle to
   replicate from scratch. Drive it via Playwright instead:
   - Navigate to `https://lovdata.no/pro/#result&q=<encodeURIComponent(query)>`
   - Wait ~2 s for the SPA to render results (no good DOM signal — poll until
     `a[href^="#document/"]` appears, or sleep)
   - Extract result hrefs: `Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href')).filter(h => h && h.startsWith('#document/'))`
   - Each href has the form `#document/<COLLECTION>/<TYPE>/<SLUG>?searchResultContext=...&rowNumber=...&totalHits=...`
   - The first match is usually correct for direct-citation queries; for
     ambiguous queries the script can return the top N and let the caller pick.

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

For markdown extraction, the script targets `#documentBody` and:

- Strips `.documentButtonsBar` toolbars (per-chapter share/note icons).
- Maps `<h1>`/`<h2>`/`<h3>` to markdown headings.
- Maps `<p class="avsnitt">` to plain paragraphs.
- Preserves `<table>` (Pro uses real HTML tables for metadata blocks).
- Resolves footnote/reference anchors (`<a class="namedAnchor">`) — usually
  fine to drop the empty anchors and keep the destination text inline.

Metadata block (title, dato, utgiver, henvisninger, etc.) sits in a `<table>`
near the top of `#documentBody`. The script extracts it into a JSON
metadata payload alongside the markdown body.

---

## Failure modes seen during exploration

- **Status 200 with 4,765 bytes and title `LovdataPro`** — this is a
  client-side redirect stub. The URL is valid syntactically but the slug
  doesn't resolve to a Pro document. Treat this byte-count as a sentinel for
  "not found" alongside the 404/803-byte feilmelding page.
- **Status 200 with ~7,000-7,500 bytes and the document title set** — for
  forarbeider, this is the TOC-only stub returned without `/*`. Refetch with
  `/*` appended.
- **Status 404 + `Lovdata - feilmelding`** — straightforward: the slug is
  wrong. Fall back to Pro search.
