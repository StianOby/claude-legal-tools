# lovdata-pro and the new Lovdata Pro (pro2)

Lovdata launched a new Lovdata Pro on 2026-11-26
(<https://hjelp.lovdata.no/article/380-kom-i-gang-med-nye-lovdata-pro>).
A login lands there from that date; the old site lives on as **Lovdata Pro
Klassisk** at `https://lovdata.no/pro/?forceFullVersion=true`, and Lovdata
says it stays available through 2027.

**Decision (maintainer, 2026-11-11):** the helper keeps both backends at
least until the end of 2027. Which one SKILL.md opens by default is chosen
by a measured comparison (speed, tokens, coverage — see "Default site"
below), to be rerun in mid/late 2027.

Everything below was measured on 2026-11-11 from the public JS bundle and,
logged in, from Claude Desktop (probes and a free exploration; no document
text was recorded).

## Site and API

- The app is an Elm single-page app at `https://pro2.lovdata.no/`, path
  routed (`/dokument/<base>/<type>/<id>[/<part>]`, `/sok?q=…`,
  `/referanser/<short form>`). `/document/…` redirects to `/dokument/…`.
- The JSON API is at `<origin>/api`. The bundle also names
  `https://lovdata.no/pro/api` (and stage hosts), so after the switch the
  new app may be served from `lovdata.no/pro` too. The helper tells it from
  Klassisk by the Vite bundle (`<script src=".../assets/index-…">`); check
  this after 2026-11-26.
- Calls the helper uses (all with the session cookie):

  | Call | Returns |
  |---|---|
  | `GET auth/user` | user record; the helper returns only yes/no |
  | `GET checkDocument/<base>/<type>/<id>` | `{type}`: `Success`, `RedirectTo` (+`documentURI`; also for the wrong SIV/STR collection and for `AVG/avgjorelse/rt-…`), `DocumentNotFound`, `MissingJSON` (+`proURL`), `StaticFile` (+`url`, `fileType`). Without a base: HTTP 400 |
  | `GET references/<type>/<id>[/<part>]` | array of `{title, base, documentURI, …}`; `[]` when unknown. Resolves Lovdata's short forms: `avgjorelse/rt-2000-1811` → `HRSIV/avgjorelse/hr-2000-49-b`, `avgjorelse/rg-2009-1` → `LHSIV/…/lh-2008-37682`, parts remapped (`nou-1984-18/kap3.4` → part `k4-1-4`) |
  | `GET documentContent/<path>` | `{version: 2, header, toc, mainTags}`, JSON-ML (below). The whole document (NOU 2022:8: 1.47 M chars) — no lazy loading |
  | `GET documentMeta/<path>` | `title`, `shortTitle`, `documentURI`, dates, `sammendrag`, backlinks … |
  | `GET partContent/<path>/<partId>` | `{documentURI, content}` for one part (not used: documentContent is complete) |
  | `POST search?minimal=true` | `{request, results[], totalHits, facets}`; each result has `documentURI` (object), `base`, `documentTitles.title`, `isoDate` |

- **Search ranks by relevance only with `sortField: "relevance"` and
  `sortOrder: "desc"`.** Without them an exact reference comes behind Karnov
  comments. With them HR-2016-2554-P, Rt. 2000 s. 1811 and NOU 2022:8 are
  #1. `filterBases` takes collection or group codes (`HRA` all
  Høyesterett, `AVG` all court decisions, `LBSIV`, `NOU` …).
- **Never called:** `breadcrumbs` (the UI posts one per document view and
  search; it writes the user's Smulesti), and the KI services (`ai-search`,
  `ai-chat`, `v2/ai-chat`, `ai-search-migrate`, `reference-preview`), whose
  rules forbid automated queries (`docs/lovdata-pro-terms.md`).
  `tests/lovdata-pro/pro2.js` checks both.

## documentContent format

An element is `[tag, {attrs}, [children]]`; a child is a string or an
element. `header` and `toc` are single elements, `mainTags` a list. The
helper rebuilds it as DOM nodes in an inert `DOMParser` document and reads
it with the same `toText()` as Klassisk. The vocabulary is Lovdata's
Klassisk one (`footnotereference`, `footnoteLabel`, `data-name`, h2–h6),
plus:

| Markup | Drawn as | Text |
|---|---|---|
| `article.verdictNumberedP[data-part-id=aN]` > `span.verdictNumberedPId` "(N)", " ", `article.defaultP` | one row: "(N)" then the paragraph | `(N) text` on one line |
| `li[data-name]` > `span.data-originalId` | the label, = `data-name`; `value`/`type` not used | `data-name` + text; the span skipped |
| `li[data-list-id-style=i]` | italic label | `*b.* text` |
| `sup.footnotereference` / `article.footnote` > `span.footnoteLabel` | marker / note in `footer.footnotes` | `[fn N]` |
| `aside.pagenumber` "Side N" | inline, floated right | own line `Side N`; taken out of heading text |
| `span.legalArticleValue` ". " `span.legalArticleTitle` | §-header, title italic (CSS) | `§ 1-1. *Formål*` |
| `figcaption` | italic (CSS) | `*…*` |
| `i` / `strong` | italic / weight 500 | `*…*` / `**…**` |
| `span.underline` | underlined | not marked (repo rule) |
| `blockquote`, `a[data-link-type=external]` | CSS glyphs “ and ↗ | not text |
| header `dl.data-document-key-info` `dt.<class>`/`dd` | labels Instans, Avsagt, Parter, … | `metadata` keyed by the shown label |

Drawn text equals the JSON for LG-2008-135938 (22 534 = 22 534 chars).
NOU 2022:8 drew 184 chars more than its JSON; not traced.

## Coverage differences

- **Not in pro2:** stortingsmeldinger (Meld. St./St.meld.; no STS base in
  the facets) and St.prp. Klassisk has the STS records.
- **Karnov comments** (`COMMENT`) have no documentContent (404); the helper
  drops them from search results anyway (literature is out of scope).
- Oslo tingrett is `tosl-` from 2021 (`toslo-` before); Innst. ids vary by
  era (`inns-409-l-202021`, `inns-s-264-200809`, `inns-o-ix-196061`).
- RG has no base of its own: it resolves to the LB/LH/… judgment, the RG
  reference only in the title.
- Old Klassisk links (`lovdata.no/pro/#document/…`) still opened Klassisk on
  2026-11-11.

## Default site

SKILL.md Step 0 names one default URL (Klassisk until decided). It is
chosen by the comparison test in `docs/lovdata-pro-default-test.md`
(correctness gate, then tokens, then speed), rerun in mid/late 2027 before
Klassisk goes away.

## Later (2027)

- **Advanced search.** Lovdata's *Avansert søk* exists only in Klassisk so
  far ("Avansert søk: ikke ennå", help article 380). When pro2 gets it,
  explore whether its API (the `facet*`/`custom*` fields of `POST search`,
  `search-facet-values`, `search-counts`) can serve fielded search from the
  helper — court, date range, legal area — and add a task for it to the
  default-site test.
- Before Klassisk is retired: remove the Klassisk backend, its tests and
  the Hurtigsøk fallback in SKILL.md, and re-measure `PAGE_SIZE` and the
  paste size.
