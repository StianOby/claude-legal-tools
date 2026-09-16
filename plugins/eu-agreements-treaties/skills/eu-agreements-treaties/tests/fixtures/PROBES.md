# Consilium fixture capture and parser probes

**Date: 2026-09-16** — all of it captured live from `www.consilium.europa.eu`
through the Claude Desktop built-in browser, with
`scripts/browser/consilium.js` pasted into the tab. No other route to the site
was attempted.

Written to an outputs mirror of `$SKILL/` (then named `consilium-treaties`, since renamed `eu-agreements-treaties`), not into the repository (the repo was
mounted read-only by agreement with the maintainer). Copy the tree in after
review; nothing here has been committed.

---

## ready()

Tab parked on `https://www.consilium.europa.eu/en/documents/treaties-agreements/`,
helper pasted, no Cloudflare challenge on first load.

```json
{
  "ok": true,
  "page_title": "Search the Treaties and Agreements database - Consilium",
  "parties": 256,
  "searchUrl": "https://www.consilium.europa.eu/en/documents/treaties-agreements/",
  "url": "https://www.consilium.europa.eu/en/documents/treaties-agreements/"
}
```

**Deviation from NOTES.md §1.** The notes expect ~206 unique party codes (412
checkboxes, "each party listed twice"). There are 412 `input[name="Parties"]`,
but they dedupe to **256**, not 206.

The form is an alphabetical index listing each party once per *name form*, and
the number of name forms is not uniformly two. 100 codes carry one name form
(their long name is blank — `ASEAN - `, `Greenland - `, `Malgache - `, …) and
156 carry two, which is exactly 412 inputs → 256 codes.

`parsePartyList` is behaving correctly here; the "~206" figure in NOTES.md §1
and memo §3.1 is wrong and should be restated as **256**. The `tests/run.js`
bound (`p.length > 150 && p.length < 300`) still passes, so nothing fails — but
the test's *name* ("~206 unique party codes") should be corrected too.

---

## captures

All seven captured at `selector_used: "main"` — `capture()`'s first guess, and
never `"body"`, so no `{selector: …}` override was needed anywhere. None
exceeded the 200 000-char threshold in the task.

| Fixture | selector_used | total (chars) | pages |
|---|---|---|---|
| `search-form.html` | `main` | 120 627 | 3 |
| `search-NO.html` | `main` | 73 630 | 2 |
| `search-NO-IS.html` | `main` | 89 654 | 3 |
| `agreement-2011036.html` | `main` | 8 621 | 1 |
| `agreement-2016032.html` | `main` | 3 128 | 1 |
| `agreement-2016032-fr.html` | `main` | 3 172 | 1 |
| `ratification-2011036-A.html` | `main` | 1 243 | 1 |

### Fidelity

Every file was verified by comparing a SHA-256 computed in the browser over the
concatenated `page(key, n).text` against one computed over the bytes on disk.
**All seven match exactly:**

| Fixture | chars | SHA-256 |
|---|---|---|
| `search-form.html` | 120 627 | `9d39f6e8a6e5fc18a9f9ae429bfecc6cc2c75c23d3b0a52d9a7a457e29c19878` |
| `search-NO.html` | 73 630 | `699ba2e5d59a65a6652b4fc60d82c4743beb0f1bb5b608f8ad13b1233236b132` |
| `search-NO-IS.html` | 89 654 | `b58365e14a1f06d01bb04198924002361062d381a5d98823f19e70428eaf730b` |
| `agreement-2011036.html` | 8 621 | `1a63a707b36d5cb621a7cca83741ccea16d3c5c950303c0e9e3d16bdd1f9717e` |
| `agreement-2016032.html` | 3 128 | `381c75cf2fa7bd08e32b4c0dc2c9f1a858127f2c1804fdcb991f9e19b675933b` |
| `agreement-2016032-fr.html` | 3 172 | `c6c982737ed66aa5b52dd27289bb325164a9605c8a4b217c7868165f044873d8` |
| `ratification-2011036-A.html` | 1 243 | `b1beb7a77ac60fe9471c6fe84f95c8fec4622879985a1efd3fa0ef075f8388b2` |

Leftover zero-length `*.part*` scratch files sit in this directory; this session
had no delete permission, so please remove them when copying the tree in.

**Transfer hazard.** The first write came out 7 characters short: the text
contains lines ending in a space (`…checkbox">Andean Pact - \n`) and trailing
whitespace before a newline is stripped in transit. Later pages were transferred
with each trailing space encoded as `§` and converted back on disk. Per-page
SHA-256 comparison should become a required step in NOTES.md §3 — it caught this
in two tool calls, and the corruption was otherwise invisible.

---

## probes

`search({parties: ["NO"]})` — **matches expectation.** `total` 101,
`site_total` 101, `semantics` "single", dates populated
(`2026-03-26`, `2025-10-14`, …). 562 ms.

`search({parties: ["NO", "IS"]})` — **matches.** `total` 135, `site_total` 135,
`semantics` "OR", and the OR warning is emitted. 355 ms.

`search({all: ["NO", "IS"]})` — **matches.** `total` 42, `semantics` "AND", two
URLs fetched, `site_total` null (correct: there is no site count for a local
intersection).

`search({parties: ["XX"]})` — **matches.** `{error: "unknown_party"}` with one
suggestion (`MX`, "similar code"). Stopped locally, as intended.

`search({parties: ["AT"]})` — **matches, but the suggestions are noisy.**
`unknown_party` with `A` (Austria) first and the right reason
("site uses A, not ISO AT"). It is then followed by **seven junk suggestions** —
`ACP`, `AE`, `ASC`, `ASG`, `BO`, `BR`, `CCS` — all tagged "name match", because
`partyMatches` does a substring test and "at" occurs inside "St**at**es",
"Navig**at**ion" and so on. A two-letter query should not substring-match names.

`search({parties: ["NO"], from: "2010", to: "2020", sort: "LSF"})` —
**WRONG, and the site is at fault.** Returns 34 rows whose top entries are
signed **2026-03-26, 2025-10-14, 2024-11-14** — outside the requested range. See
"Date filtering" below; this is the most consequential finding of the session.

`search({parties: ["NO"], noPV: true})` — **matches.** `total` 98 (101 − 3
Procès-Verbaux), `site_total` still 101. PV detection works on the real titles
("Procès-Verbal of Rectification to …"). Minor: the summary shows `total: 98`
beside `site_total: 101` with no note that the difference is the local PV filter.

`list()` — **matches.** `total` 2363, `site_total` 2363, one request,
**2 378 ms** (the memo's ~560 ms no longer holds; still one fetch, ~1.6 MB).

`find("schengen")` — 8 hits, 1 ms, local over the cached list. Correct as
designed, but note it only matches the word in the *title*, so the Schengen
association agreements that don't carry the word are missed; that is a
documented limitation of `find()`, not a bug.

`detail("2011036")` — **mostly matches.** Observations exactly
`"Provisional application as from 21/06/2011 (except Austria, see Declaration)"`;
Austria resolves to code `A`, `has_declaration: true`, correct `declaration_url`;
footnote captured. 31 parties, no truncation. But:
- `signature: null` and `entry_into_force: null`. **These are correct** — the
  page's Signature field holds only `Luxembourg & Oslo` and the EIF field is
  empty `<strong></strong>`; per-party dates live in the table. `signature_place`
  is right.
- `code: null` for all 30 parties except Austria — see below.
- `signature_inherited` is `false` on every row, because the flag is computed
  from `agreementDates.signature`, which is null here. The inheritance logic
  silently disables itself on exactly the pages where the footnote matters most.

`detail("2016032")` — **matches.** OJ `L 141 (28/05/2016)` → `{series: "L",
year: "2016", issue: "141", part: "TOC"}` linking to EUR-Lex; signature
`2016-05-03`, place `Brussels`, EIF `2017-09-01`. `party_codes` empty (4 parties,
none with declarations).

`detail("2009066")` — **signature correct, observations WRONG.** `signature`
`2011-09-22` against ID prefix 2009, confirming the ID≠year trap. But
`observations` came back as
`"European Union 13/03/2012 01/05/2012 Iceland 24/03/2014 …"` — that is the
**ratification table's first rows**, not observations. See the `findFieldValue`
bug below.

`detail("2007059")` — **matches.** One record covering four instruments; title
begins "Agreement on the participation of the Republic of Bulgaria and Romania in
the European Economic Area (including the Agreement in the form of an Exchange
of Letters … / the Additional Protocol … / …)". Signature `2007-07-25`, EIF
`2011-11-09`, three OJ references.

`detail("2016032", "fr")` — **matches.** French title ("Accord entre l'Union
européenne, l'Islande, …"), French observations, `Bruxelles`, and the EUR-Lex
link switches to `/legal-content/fr/`. Note the table headers stay English.

`declaration("2011036", "A")` — **matches.** 570 chars, Austria's text present
and complete.

`parties("german")` — **matches.** `D` (+ `RDA`, GDR — reasonable).
`parties("economic community")` — **matches.** `CEE` (+ `CED`, ECOWAS —
reasonable).

### Fields that came back null, empty or wrong

| Field | Where | Verdict |
|---|---|---|
| `party.code` | every party without a declaration, on every detail page | **bug** |
| `party.signature_inherited` | all rows of 2011036 | **bug** (cascades from a null agreement-level signature) |
| `observations` | 2009066 | **bug** — ratification table text leaked in |
| `site_total` | fixture layer only | **bug** — see the `npm test` section |
| `signature` / `entry_into_force` | 2011036 | correct (the page really is empty) |
| `party_codes` | 2016032, 2009066, 2007059 | empty, consequence of the `party.code` bug |

---

## dom

**(a) party checkbox markup**

```html
<li><label class="gsc-form__label gsc-form__label--checkbox">Kingdom of Norway (Norway)
 <input name="Parties" id="Norway" type="checkbox" class="gsc-form__input" value="NO"></label></li>
```

- The `<label>` **wraps** the input and has **no `for`**. Verified with
  linkedom over the captured fixture: `label[for]` matches **0** elements on the
  whole page. `parsePartyList`'s first strategy is dead code against the live
  site; every label is found by the `closest('label')` fallback.
- The input's `id` is the party *name* (`id="Norway"`, `id="Côte d'Ivoire"`,
  `id="Kosovo*"`, `id="Kosovo (under UNSC Resolution 1244/99)"`) — quotes,
  spaces, parentheses and asterisks. If a `for` attribute ever appeared, the
  selector built from it would break.
- Label text is the whole `short - long` or `long (short)` string, so `name`
  comes out as `"Kingdom of Norway (Norway)"` for NO and
  `"Austria - Republic of Austria"` for A — never the short form the field is
  meant to hold.

**(b) result-row structure** — from the `Parties=NO` results page:

```html
<li data-block-flow-sm="">
  <a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2026005" class="gsc-link">…title…</a>
  <p>Signature: <time datetime="3/26/2026 12:00:00 AM">26/03/2026</time></p>
</li>
```

Ancestors of the anchor: `A.gsc-link` → `LI` → `OL` → `SECTION.gsc-main-section
gsc-container` → `MAIN`. `resultItemFor` therefore lands on the `LI`, which is
right. Rows are separated by bare `<hr>` siblings.

Three things the parser should use and currently doesn't:

- `<time datetime="3/26/2026 12:00:00 AM">` — a machine-readable date on every
  row. Far more robust than regexing `26/03/2026` out of the row text. (Note the
  attribute is US `M/D/YYYY` while the visible text is `DD/MM/YYYY`.)
- `<strong class="gsc-u-results-count">101 results</strong>` — a dedicated hook
  for the count, instead of a regex over the whole body.
- `id` is **not** the first query parameter: `?docLanguage=en&id=2026005`.
  `ID_IN_HREF` handles this correctly, but note that
  `querySelectorAll('a[href*="agreement"]')` also matches the 59
  language-switcher links (`/bg/documents/treaties-agreements/?…`), because the
  path itself contains "agreements". They are filtered out by the id regex, so
  the result is correct — but the selector is doing no useful narrowing.

**(c) detail-page label/value markup and ratification table**

```html
<div class="gsc-grid gsc-accords-details">
  <div data-block-flow=""><h2 class="gsc-title gsc-title--underlined gsc-title--lp-section">Entry into force</h2><p><strong></strong></p></div>
  <div data-block-flow=""><h2 class="…">Signature</h2><p><strong>Luxembourg &amp; Oslo</strong></p></div>
  <div data-block-flow=""><h2 class="…">Official Journal reference</h2><ul class="gsc-link-list …"><li><a href="https://eur-lex.europa.eu/legal-content/en/TXT/?uri=OJ:L:2011:283:TOC" class="gsc-link"> L 283 (29/10/2011); </a></li>…</ul></div>
</div>
<div class="gsc-accords-details">
  <div data-block-flow=""><h2 class="…">Observations</h2><p>Provisional application as from 21/06/2011 (except Austria, see Declaration)</p></div>
</div>
<h3 class="gsc-title gsc-heading--sm">Ratification Details</h3>
```

So each field is `<h2>label</h2>` followed by a sibling `<p>` **inside the same
`div`** — which is exactly what `findFieldValue`'s `el.nextElementSibling` picks
up. That part is sound.

Table header and first row:

```html
<tr><th data-sort="string">Party</th><th data-sort="string">Signature (*)</th><th data-sort="string">Notification</th><th data-sort="string">Entry into force (*)</th><th data-sort="string" title="Declarations and reservations made by Parties/Countries to an agreement">Declaration / reservation</th><th data-sort="string">Observations</th></tr>
<tr> <td><b>Belgium</b></td> <td data-sort-value="20110616000000000">16/06/2011</td> <td data-sort-value="20160826000000000">26/08/2016</td> <td data-sort-value=""></td> <td> </td> <td></td> </tr>
```

Two consequences:

- **The party cell is `<td><b>Belgium</b></td>` — plain text, no link.** The only
  `partyid=` link in a row is in the *Declaration / reservation* cell, and only
  when that party filed one. `codeFromLink` therefore yields a code for
  declaring parties only, and `party_codes` is not the party list — it is the
  list of parties with declarations. Any mapping from `name` to code has to go
  through `data/parties.json`, and the names here ("Czechia", "European Union")
  are the *short* forms.
- `data-sort-value="20110616000000000"` gives a sortable ISO-ish date per cell,
  and `""` for genuinely empty ones — again more robust than parsing the text,
  and it distinguishes "empty" from "unparseable".

The footnote sits in a `<tfoot>` inside the table, so
`table.parentElement.textContent` still finds it. Live wording is slightly
different from the synthetic test's: it includes "(above left)" and
"(above right)".

Also worth noting: the **ratification page uses a completely different, older
template** (`container-council`, `col-md-9`, `page-header`, `well` — Bootstrap)
from the agreement page's `gsc-*` design system. Two layouts to keep working.

---

## Date filtering — the most serious finding

`search({from, to})` promises a range and does not deliver one. Probing the
endpoint directly with `Parties=NO`:

| Query | Count |
|---|---|
| no dates | 101 |
| `DateFrom=01/01/2010&DateTo=31/12/2020` | 34 |
| `DateFrom=01/01/2010` alone | **34** |
| `DateTo=31/12/2020` alone | **101** |
| `DateFrom=01/01/2015&DateTo=31/12/2016` | 22 |
| `DateFrom=01/01/1990&DateTo=31/12/1991` | 79 |

**`DateTo` is silently ignored.** `DateFrom` works as a lower bound and nothing
else, which is why a 2010–2020 search returns agreements signed in 2026 at the
top and why the counts fall monotonically as `DateFrom` rises (1990 → 79,
2010 → 34, 2015 → 22). The site's own "34 results" agrees, so this is the
site's behaviour, not a parsing error.

`DateType` behaves oddly too:

| `DateType` | Result |
|---|---|
| omitted | 34 (same as `signature`) |
| `signature` | 34 |
| `eif` | 32, different rows — genuinely switches the field |
| `ratification` | **0 results, no count text** |
| `zzz` (invalid) | **0 results, no count text** |

All three of `signature`, `ratification`, `eif` are real `<option>` values in the
form's `<select name="DateType">`, but `ratification` behaves exactly like an
invalid value. `signature` is a no-op because it is already the default.

For a treaty-status tool this is a silent-wrong-answer class of bug: "Norway's
agreements signed in the 1990s" quietly returns everything from 1990 to today.
The skill should either drop `to`, or apply it locally after fetching, and
SKILL.md should say plainly that the site has no upper date bound.

---

## parties

`partiesDump()` → 256 codes, 39 386 chars, 1 page. `data/parties.json` was
rebuilt from the dump and verified byte-identical to the browser's
`JSON.stringify(list, null, 1)`:
`0dc49eccc9ef8a59cfabb58286677a950acb64c499299127da2215e5c0071942`. It parses as
JSON; all 256 codes are unique.

**Odd entries.** No empty names and no duplicate codes. Thirteen codes have a
blank long name, so their `name` ends in a bare dash: `AC` (Andean Pact),
`ASE` (ASEAN), `CS` (Czechoslovakia), `DA` (Dahomey), `GL` (Greenland),
`HK` (Hong Kong), `HV` (Upper-Volta), `MAL` (Malgache), `MS` (Mercosur),
`PAC` (Central Africa Party), `SU` (USSR), `UN` (United Nations),
`UNR` (UNRWA). No label maps to more than one code.

**The six codes asked for:**

| State | Site code | ISO 3166 |
|---|---|---|
| Greece | `GR` | GR ✔ |
| United Kingdom | `GB` | GB ✔ |
| Liechtenstein | `LI` | LI ✔ |
| Switzerland | `CH` | CH ✔ |
| Russia | `RU` | RU ✔ |
| Türkiye | `TR` | TR ✔ (label carries `ü` — `Republic of Türkiye (Türkiye)`) |

All six match ISO. The non-ISO trap is confined to the ten old EC member-state
codes, which are all confirmed present: `A`, `B`, `D`, `F`, `I`, `IRL`, `H`,
`P`, `S`, `SF`.

**`EC` is Ecuador.** The site uses `CE` for the European Community and `EC` for
**Ecuador**. `ISO_TRAPS` maps `EC → CE`, but `resolveParty` finds the exact
match on `EC` first and returns Ecuador without ever consulting the trap table.
A user asking for "EC" meaning the European Community gets Ecuador's agreements
and no warning. Same shape of trap, unexercised: `EEA→EEE`, `EEC→CEE`,
`EU→UE`. Other near-collisions worth a line in `references/party-codes.md`:
`CG` Congo vs `CGP` P.R. Congo, `CS` Czechoslovakia vs `CZ` Czechia,
`KV` vs `KVO` (two Kosovo entries), `SZ` Swaziland vs `SWZ` Eswatini,
`MK` North Macedonia vs `AYM` FYROM.

---

## channel

- **Capture sizes / paging.** Largest was the search form at 120 627 chars →
  3 slices of 44 600 (`PAGE_SIZE - 400`). No `page()` call errored for size; the
  45 000 ceiling is comfortable for every page here.
- **Challenge responses.** **None, at any point.** `ready()` passed on the first
  call and every fetch returned 200 across roughly 45 `javascript_tool` calls and
  ~30 same-origin fetches (including the 1.6 MB `list()`). No `{error:
  "challenge"}` was seen. Response times 355–560 ms for searches, 382 ms for the
  form capture.
- **`list()` timing.** 2 378 ms for the full 2 363-row register in one request.
  The memo's ~560 ms no longer holds; still a single fetch.
- **Tool-channel outage (not the site).** For roughly 20 minutes mid-session
  every `javascript_tool` call — including a bare `1+1` — was refused with
  "claude-sonnet-5[1m] is temporarily unavailable (timed out), so auto mode
  cannot determine the safety of mcp__Claude_Browser__javascript_tool". This is
  the tool-approval classifier, not the site, the tab or the helper. Read-only
  tools kept working. It cleared on its own; the tab kept `window.__cs` loaded
  throughout, so work resumed without repasting.

---

## npm test

Run against a scratch copy of `scripts/` + `tests/` with the seven captured
fixtures dropped in. The repository was mounted read-only, so nothing was
installed or written inside it.

```
synthetic
  ok    toIso handles site dates and the 0001 empty value
  ok    toSiteDate accepts ISO, DD/MM/YYYY and bare years
  ok    buildSearchUrl repeats Parties and only sets dates when given
  ok    parsePartyList dedupes on value and keeps both names
  ok    parseResults finds rows, ids, dates, PV flag and dedupes duplicate links
  ok    sortResults puts undated rows last in both directions
  ok    parseDetail reads fields, OJ links and the ratification table with inheritance
  ok    isChallengeHtml recognises the Cloudflare page
fixtures (captured from the live site; see NOTES.md §3)
  ok    search form: ~206 unique party codes incl. the non-ISO EC codes
  FAIL  Parties=NO: ~101 rows, every id 7 digits, some undated, PVs flagged
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:

2026 !== 101

    at /tmp/cs-test/tests/run.js:172:39
    at test (/tmp/cs-test/tests/run.js:38:9)
  ok    agreement 2011036: provisional application in observations, Austrian declaration
  ok    agreement 2016032: OJ L 141 (2016) reference to EUR-Lex
  ok    ratification 2011036/A: declaration text present

12 passed, 0 skipped, FAILURES above
```

### The one failure is a `capture()` bug, not a `parseResultCount` bug — and both need fixing

`site_total` comes back as **2026** (the first result's signature *year*) instead
of 101. Traced end to end:

- **Live page:** body text reads `… current search 101 results Sorted by: …`.
  The regex matches `"101 results"` at index 2786. Correct — which is why the
  live `search({parties:["NO"]})` probe reported `site_total: 101`.
- **Fixture:** the same text reads `… current search101 resultsSorted by:…`.
  `capture()` does `.replace(/>\s+</g, '><')`, which deletes the whitespace
  *between elements*. `results` is now immediately followed by `S`, so the
  trailing `\b` in `/(…)(results?|…)\b/` fails, the match is skipped, and the
  regex falls through to the first thing that does match: `"2026Agreement"` —
  the year `2026` from `26/03/2026` running straight into the next row's title
  beginning "Agreement".

So there are two distinct defects:

1. **`capture()` is lossy in a way that changes parser behaviour.** Collapsing
   inter-element whitespace alters `textContent`, so a fixture is *not* a
   faithful input for any text-based parser. Every `textContent` assertion tested
   against a fixture is testing a different string from the live one. Either drop
   the `>\s+<` collapse from `capture()` (it saves little, these pages are mostly
   markup) or stop testing text-derived fields against fixtures.
2. **`parseResultCount` is fragile independently.** `agreements?` matches the
   ordinary word "Agreement" that begins most titles, and `[\d.,\s]*` will happily
   consume a preceding date's digits. On the live page the correct match happens
   to be leftmost, so it wins — but any page where the count string is absent,
   reworded or differently spaced will silently return a year. Use the dedicated
   `strong.gsc-u-results-count` element instead, and fall back to the regex.

### Other notes on the test suite

- The synthetic `parsePartyList` test passes **because its markup is not the
  site's**: it feeds `<input><label for="p1">Austria</label>` and asserts
  `p[0].name === 'Austria'`. That exercises the `label[for]` branch the live page
  never hits, and asserts a short display name the live parser never produces. It
  will stay green over the `name` bug. Rewrite it to the real
  `<label>text<input></label>` shape.
- The fixture test names should be updated: "~206 unique party codes" → ~256.
- `search-NO-IS.html` and `agreement-2016032-fr.html` were captured as asked but
  `run.js` has no cases for them yet — good targets for an OR-semantics test
  (135 rows, `2025008` flagged as a Procès-Verbal) and a language test (French
  title and `/legal-content/fr/` OJ link).
