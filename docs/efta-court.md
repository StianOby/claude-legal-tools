# efta-court — plan for 2.0 (probed and built 2026-10-28)

Status: 2.0.0 is built (script, SKILL.md, README, evals, tests) and
tested from a residential IP. **Not yet tested from the Cowork cloud sandbox,
and not yet run in Cowork.** What the build added beyond the plan is under
"Build (2026-10-28)" at the end.

eftacourt.int was relaunched on about 27 October 2026 (the new SPA's
`Last-Modified`). The WordPress site that efta-court 1.x scrapes is gone:
`/wp-json/wp/v2/cases`, `/cases/<slug>/` and `/download/…?wpdmdl=` now all
return the same 2.6 KB Vue shell. **1.1.10 is broken for every command.**

The new site is a thin client over an open JSON API. The skill can be rebuilt
on that API, which is smaller and simpler than 1.x and can do more.

## What the new site is

- `https://eftacourt.int/` is a Vue SPA. `/config.js` sets
  `window.EFTA_API_URL = "https://api.eftacourt.int/api"` ("overwritten at
  deploy time"; the bundle's fallback is `https://efta_back.on-forge.com`).
- On boot the SPA downloads **every collection in full**: `GET /cases`,
  `/downloads`, `/press`, `/events`, `/procedures`, `/court`, `/members`,
  `/pages`, `/slides`, `/sidebars`, `/eeftacourt`, `/taxonomies`,
  `/settings`. It then filters and sorts in the browser.
- Full-text search runs on the server: `/search/documents` and
  `/search/snippets`.
- The backend is Laravel (`No query results for model [App\Models\CourtCase]`).
  There is a generic `/{resource}` CRUD with bearer-token writes for the
  admin. We use only the public GETs.

## The API (all public and unauthenticated; honest UA works)

| Endpoint | Returns | Size / time |
|---|---|---|
| `GET /cases` | all 463 cases, one JSON array | 900 KB, 0.7 s |
| `GET /cases?page=N` | 15 per page, `meta: {total, page, per_page, last_page}` | — |
| `GET /cases/{id}` | one case (`id` = `c-wp-2123`, not the case number) | 2 KB |
| `GET /downloads` | all 2,301 documents (case documents, press, legal texts) | 610 KB, 0.7 s |
| `GET /downloads/{id}` | one document (`dc-2123-2`) | 0.3 KB |
| `GET /taxonomies` | controlled vocabularies (status, type, procedure, docType, language …) | 5 KB |
| `GET /search/documents?q=…[&lang=EN]` | IDs of matching documents (`dc-…`, `pd-…`) | — |
| `GET /search/snippets?q=…&ids=a,b,…` | `[{id, snippet}]`, about 200 characters around the hit | the SPA sends ≤ 60 IDs |

**Case record** (`/cases`): `id, ref, parties, status (Pending|Decided),
type (Advisory Opinion|Direct Action|Other), procedure, source (country),
referringCourt, language, subjectMatter[], keywords, description (HTML),
about[], diary[{date, description}], dateSubmitted, hearingDate,
judgmentDate (ISO dates), publishedIn, joinedFrom[], documents[doc ids]`.
`documentsContent` is always null.

**Document record** (`/downloads`): `id, title ("14/15 Judgment (EN)"),
category (Cases|Press|Procedure|…), docType, language (full name), date,
file (absolute PDF URL)`. docTypes: Judgment 738, Press Release 596, Report
for the Hearing 424, Notification 308, Request for an Advisory Opinion 118,
Order of the President 44, Order of the Court 36, Information Note 20, Legal
Text 14, Decision 2, Guide 1. Languages: English 1623, Norwegian 284,
German 201, Icelandic 189, Finnish 2, Swedish 2.

**Search semantics** (tested):

- Whole words, terms ANDed (`collect` 28 hits, `collective` 153).
- Prefix with `*` (`collect*` 377).
- `"quoted phrase"` works (`state aid` 238, `"state aid"` 191; the snippets
  show the phrase).
- `+`/`-` operators return 0, so they are not supported. `OR` is not an
  operator.
- Diacritics count (`Høyesterett` 192, `hoyesterett` 13).
- `lang=EN|NO|IS|DE` filters by document language.
- **Results stop at 1000** (`EEA`, `the`): the script must warn when it
  gets exactly 1000.
- The full text is indexed, not just the first page ("dockworkers" from
  late in the Holship judgment matches).

**PDF hosts.** `file` points to `https://efta_back.on-forge.com/storage/imports/<md5>.pdf`
(2,299 of 2,301). That host is behind Cloudflare and gives a **403 to
`Python-urllib/…`** but a 200 to the honest UA. The same path on
`https://api.eftacourt.int/storage/imports/…` serves the identical file from
plain nginx, with no Cloudflare in front.

**Data quirks to handle:**

- `ref` is already normalised (`E-8/26`, never `E-08/26`). The 1.x slug
  problem is gone, but users still type `E-08/26`.
- 30 refs are not a single `E-N/YY`: joined cases in four spellings
  (`Joined Cases E-31/24 and E-32/24`, `E-8/94 and E-9/94`,
  `E-5/04, E-6/04, and E-7/04`), and `COSTS`, `Costs II`, `INT` and `r`
  (`E-6/94r`) suffixes. The component cases of a joined case have their own
  records, but **without the judgment** (20 Decided cases have no
  judgment or order). Resolve a component to the joined record for the
  judgment, and show both.
- `type: "Direct Action"` covers infringement actions (166, procedure
  `Infringement Proceedings`), actions for annulment (40), failure to act,
  costs, etc. Derive AO/INF/DA from `type` + `procedure` + "EFTA
  Surveillance Authority v" in `parties`, as 1.x does. `procedure` is
  null or `""` for 107 cases.
- `source` is the country for AOs and `""` for direct actions.
- `publishedIn` says only "Report of EFTA Court" (282) or is empty, with no
  volume or page. The EFTA Ct. Rep. citation is still not available.
- No ECLI anywhere.
- Public case page: `https://eftacourt.int/cases/<id>` (`c-wp-2123`). The
  SPA also maps old slugs such as `/cases/e-14-15/` client-side (legacy
  matcher), but cite the `<id>` form.

**Not tested yet:** any of this from the Cowork cloud sandbox. Both hosts
answered from a residential IP. Step 1 below does the cloud check.

## Design for 2.0 (a rewrite, not a port)

What goes: the WP REST index, HTML case-page parsing, slug resolution,
document-label parsing, the `--pending/--decided` verification pass that
fetched every recent case page, and the "search only sees what you've
fetched" limit. The API returns all of this in two requests.

**One script, `scripts/efta_court.py`, stdlib only.** It reads the API base
from `https://eftacourt.int/config.js` (falling back to the hard-coded
`https://api.eftacourt.int/api`), so a redeploy that moves the backend does
not break the skill. It uses the UA `efta-court-skill/<version> (+…)`, and a
test checks that the UA never starts with `Mozilla/` or `Python-urllib/`.

**Metadata: live, with a short cache.** `/cases` + `/downloads` take about
1.5 MB and under 2 s. They are cached for 1 hour (not a day: there is no
crawl to save, and a new judgment should show up the same day). This is not
a snapshot, so nothing goes in `snapshots.json`. PDFs and extracted text are
cached per document ID. A document's `file` hash changes if the file is
replaced, so key the cache on it.

**Subcommands:**

| Command | Does |
|---|---|
| `case E-14/15` | Full record: parties, status, procedure code, referring court, language, subject matter, keywords, dates, diary, published-in, case page URL (the only link ever given to the user), and a numbered document list. A joined component shows the joined record too. |
| `list [--year] [--country NO\|IS\|LI] [--procedure AO\|INF\|DA] [--status pending\|decided] [--subject …] [--court …] [--limit]` | Filters over the full metadata. All filters now work for every case, ESA actions included. |
| `search "<query>" [--lang EN] [--year] [--procedure] [--country] [--meta-only]` | Two layers, as the site does: (1) local match on ref, parties, keywords, subject matter and referring court; (2) server full text via `/search/documents`, mapped to cases through `case.documents` (other hits dropped), with snippets from `/search/snippets` in batches of 60. Prints the case, the matching documents and the snippets. Passes `"phrases"` and `prefix*` through, and warns at the 1000 cap. |
| `get E-14/15 [--type judgment] [--lang EN] [--doc N]` | Downloads the PDF and writes the `.txt` next to it. No `--type` → the document list. `--type` keys come from `docType` (`judgment`, `report`, `request`, `order`, `notification`, `information-note`, `decision`; press releases excluded), and `order` matches both Order types. `--lang` takes EN/NO/IS/DE/FI/SV and falls back to EN with a stderr note, as now. |
| `status` | Cache location and age. |

`fetch` stays as an alias of `case` so the old SKILL.md muscle memory and
kildesjekk prompts still work.

**PDF download:** try the `file` URL as given. If that fails (Cloudflare
403/challenge), retry the same path on the API host. Do it the other way
round if step 1 shows the cloud sandbox gets challenged on on-forge.
Text extraction is unchanged: `pdftotext -raw` → pypdf → PDF only, with the
existing notes on 1990s letter spacing and line-end hyphens. PDF text has no
emphasis (source-text rules).

**Text from the server search?** Snippets are short and lightly processed.
Never quote from a snippet; quote only from the PDF text. SKILL.md has to
say so.

**SKILL.md:** rewritten to fit the new model. That makes it much shorter:
the mental-model, verification-pass and slug sections go, and a
"how search works" section comes in (whole words, AND, `*`, phrases,
diacritics, 1000 cap, `--lang`; grep the PDF text for anything subtler).
The citation guidance stays. The description stays ≤ 1024 characters
(current one is unchanged in scope).

**Tests (`tests/efta-court/`):** offline, against small trimmed fixtures
from `/cases`, `/downloads` and `/search/*`, with private parties
anonymised ("Person A v Company B"): ref normalisation (`E-08/26`, `e14-15`,
`14/15`), joined/COSTS/INT resolution, procedure-code derivation, `--type`
mapping, the 1000-cap warning, the UA check, the host fallback, and
`config.js` parsing.

**Evals:** eval 2 expects `eftacourt.int/cases/<slug>/` URLs; change it to
`/cases/<id>`. Add one full-text search eval ("EFTA Court cases discussing
'collective action'"), which 1.x could not answer in a fresh session.

**Other plugins:** kildesjekk step 11 only delegates to `/efta-court`, so
no change is needed unless it refers to `fetch`. eea-lex is unaffected. Old
`/download/…?wpdmdl=` links in users' notes and Zotero items are dead. The
skill can't fix that, but `case` gives the new links.

**Version:** efta-court 2.0.0. The old cache (`index.json`, `raw.html`
per case) is ignored and removed on first run. Explain that in a code
comment, not SKILL.md.

## Steps

1. **Cloud probe** (Cowork sandbox): `/cases`, `/downloads`,
   `/search/documents`, a PDF from both hosts, with the honest UA and with
   `Python-urllib`. This decides the host order for PDFs, and whether the
   browser route is needed at all (probably not).
2. Write the new script and tests. Delete the HTML parser.
3. Rewrite SKILL.md, README and evals, and check the description length.
4. Bump 2.0.0, run CI checks locally (`check-plugin-versions.sh`, plugin
   validate), and test in Cowork with the three evals plus the new search
   eval.
5. Afterwards: record the build findings here, as `docs/eea-lex.md` does.

## Risks

- **The site is a day old.** The PDF host is a Laravel Forge default
  hostname, and the API is undocumented. Mitigations: read `config.js`, fall
  back between the two PDF hosts, and fail with a clear message that names
  the endpoint. Optional: ask the Registry whether `api.eftacourt.int` is
  meant to be stable.
- **Data migrated from WordPress** may have gaps: 463 cases now vs ~457 in
  1.x; IDs keep the WP post ID (`c-wp-2123`). A spot check found every case
  has documents, but for the judgment you must look at the joined record.
- If the court later puts the API behind auth or Cloudflare, the fallback is
  the built-in browser running the same fetches from the SPA's own origin.

## Maintainer decisions (2026-10-28)

1. **Links.** Legal citations carry no URL. When the user asks for a link
   (to a case or one of its PDFs), give the **case page**
   `https://eftacourt.int/cases/<id>`, as if the user had navigated there
   themselves. Never give the raw `file` URL (on-forge or api host). The
   `file` URL is only used internally for the download.
2. **Press releases: out.** Drop `docType: "Press Release"` from case
   document lists, from `--type`, and from search results. Also drop
   everything with `category: "Press"`, including the 170 items typed
   "Judgment": they are press releases titled "Judgment in Case …" (`pd-…`),
   and none of their files is a case document.
3. **Search** reports case documents only: drop `pd-…` hits and anything not
   in some `case.documents`.

## Procedural texts (proposed 2026-10-28; maintainer wants them in, kept apart from case law)

The court's own texts, `category: "Procedure"` (14 documents, no case, in
the search index): the Statute (EN), the Rules of Procedure (EN/DE/NO/IS)
and the previous Rules (EN), Guidance for Counsel (EN/DE/IS/NO), Guidance
on Requests for Advisory Opinions, and the Court's decisions on
e-EFTACourt, on publication of written observations and on remote oral
hearings. Plus the e-EFTACourt portal user guide (`ee-doc`, category
`e-EFTACourt`). Left out: `d1003`, a German press release ("25_25_PR_DE")
wrongly filed as a case notification.

**Separation: one partition, two command groups.**

- Every document belongs to exactly one bucket, decided from `/downloads`:
  **case** = its ID is in some `case.documents`; **text** = `category` is
  `Procedure` or `e-EFTACourt`; **dropped** = everything else (press). The
  partition lives in one function, and a test checks that no ID falls in
  two buckets.
- Case-law commands (`case`, `list`, `search`, `get`) see only the case
  bucket. A new `texts` group sees only the text bucket:
  - `texts list` gives the numbered texts with their languages,
  - `texts get <N|title words> [--lang]` downloads and extracts, the same
    pipeline as `get`,
  - `texts search "<query>"` runs the same server query and keeps text hits
    only.
- So a query never mixes the two. The server returns all IDs in one
  response anyway, so the script can count the other bucket at no cost and
  print one line at the end, e.g. `(also 7 hits in procedural texts:
  texts search "…")`, and the other way round. That keeps the results clean
  without hiding that the other kind exists. A `--quiet` flag could drop
  the line, but probably isn't needed.
- Texts are picked by number or by title words (`texts get "rules of
  procedure" --lang NO`), matched against the title without its
  `(EN)`-style suffix. The IDs can't be used for this: `pr-doc-rules-of-procedure-4`
  is the decision on remote oral hearings. If the words match both the
  current and the previous Rules, the script lists both and asks Claude to
  pick, with the current one first.
- Links follow decision 1: the case-law side gives the case page. A text
  has no case page, so give the site's page that lists it,
  `https://eftacourt.int/procedure`.

**Cost:** about 60–80 lines (bucket function, three small subcommands that
reuse the download/extract/search code), one section in SKILL.md, and
"Rules of Procedure / Statute of the EFTA Court" added to the description's
triggers (check the 1024-character limit). There's no extra request: the
texts come from the `/downloads` response the skill already loads.

## Build (2026-10-28)

The maintainer asked for anything the API makes possible, not parity with
1.x. Also decided during the build:

- **Document files are always fetched from `https://api.eftacourt.int/storage/…`**,
  never from the `efta_back.on-forge.com` host the records name
  (`storage_url()`; the origin follows the API base from `config.js`). There
  is no fallback to on-forge.
- **Procedural texts** are defined by `/procedures` (each page's
  `documents`) plus the e-EFTACourt page's `document`, not by `category`.
  This brings in the *EFTA Court Texts* collection (4 languages), which the
  data files as `Press Release` (`pd-8855` …). The Surveillance and Court
  Agreement page has no PDF: its 68 KB HTML body (main part, Protocols
  2–5 and 7) is converted with `shared/source-text/` and searched locally,
  because the server index holds only files. Each text links to its own
  `https://eftacourt.int/procedure/<id>` page.

Features 1.x could not have:

- `search`: server full text plus case details, with snippets, `--type`,
  `--lang` and all list filters; semantics are as above.
- `cited-by`: phrase search for the case number (plus the `E-0N/YY` form for
  2026 citations), the cited case's own records excluded, and 1990s joined
  records deduplicated by file (`dedupe_hits`). The snippets also show the
  *EFTA Court Report* references that citing documents give, tallied
  (E-1/94: `[1994-1995] 15` ×13, `… 17` ×3). They disagree, so SKILL.md says
  to report the source and the disagreement.
- **Written observations:** the diary entries' `docs` link to the parties'
  published observations (256 PDFs, from 2021-06; labelled by party). They
  are not in `/downloads`, so they are probably not in the search index.
  `get --type observations --party …`.
- `list --observer X` (from the diary text "Written observations received
  from …", available for old cases too), `--court`, `--subject`,
  `--party`, `--language`; `subjects` (tag counts).
- `calendar`: hearings, judgment dates, deadlines (diary entries starting
  "Deadline", or with `calendar: true`), court events and the judicial
  vacations from `settings.calendar_entries`, as the site's own calendar
  builds them. The data is not always consistent: E-4/26's hearing is in its
  diary and in `/events`, but not in `hearingDate`.

Data quirks found during the build:

- 8 AOs have no `source` or `referringCourt`. The country is read from the
  description (`_COURT_KEYS`); 3 remain unknown.
- Press releases are attached to cases too (344), and dropped there.
- The 1990s joined cases (E-8/94 and E-9/94) carry the same PDF on the
  joined record and on each component.

Still to do: step 1 (cloud probe), and the Cowork run of evals 1–6
(4–6 are new: full-text search, cited-by + observations, Rules of
Procedure).

Not in scope: Zotero-ready items. 1.x had none, and `docs/zotero-ready.md`
has international cases blocked on how they are entered in Zotero. The API's
structured fields (parties, ISO dates, case page, court, language, the
judgment PDF) would make a mapping straightforward once that is decided.

## Cowork test, run 14 (2026-10-28) → 2.0.1

Cloud access works: the API and `api.eftacourt.int/storage` both answer 200
from the cloud sandbox with the honest UA, and the slowest command
(`cited-by E-1/94`) took 4.4 s. All self-checks passed. Fixed in 2.0.1 from
the issue list:

- **Language of the case:** the site defaults to English for many older AOs
  (E-1/99, E-3/06, E-4/09 say English; the judgments say Norwegian,
  Norwegian, German). `case_language()` takes the non-English version of
  the request, judgment or hearing report (81 of the 94 English AOs), and
  marks the remaining 11 (old, English documents only, no request) as
  unverified. Recent English referrals (Borgarting: E-5/26, E-11/26 have only
  an English request) are correct, as the maintainer expected.
- Referring court and country of new AOs from the keywords/description
  (E-13/26: Haugaland og Sunnhordland tingrett). `_COURT_KEYS` is only that
  country fallback, and uses generic court terms (tingrett, lagmannsrett,
  høyesterett, héraðsdómur, landsréttur …), not court names.
- `list` has a header and separate lodged/judgment columns; components of
  joined cases show the joined judgment date. `--since/--until`.
- Withdrawn/discontinued cases show `Withdrawn` (the site says Decided).
- A file carried by both a component and its joined record is listed once.
- Calendar: no truncation; deadline dates come from the entry text (diary
  entries are dated when posted).
- ESA actions' keywords (a copy of the description) are not repeated.
- `texts list` marks the previous Rules "superseded".
- The cross-kind hint is shell-quoted; `search` counts matching case
  documents, not raw server hits.
- `cited-by --judgments`; the Reports tally also reads `[1994−95]` and the
  Norwegian `Sml. 1994–1995 s. 15`, normalised to one form.
- `--observer` matches a State's Government, not "University of
  Liechtenstein".
- BrokenPipe when piped into `head`.

Left as is: document titles without "E-" (the site's own titles);
E-27/25's hearing date missing from its diary (data); observations show
language `--` (not recorded by the site).
