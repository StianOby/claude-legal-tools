# eu-agreements-treaties — maintainer notes

Implementation background for whoever (human or Claude) next touches this
skill. Not part of the skill itself — `SKILL.md` is what Claude reads,
`README.md` is the human-facing overview.

(Deliberately *not* named `CLAUDE.md`: that would be loaded as project
instructions by every Claude Code session working in this directory.)

## 1. Source material

The skill is built from a reconnaissance memo written after a Cowork session
that used the database for the project "Norges avtaler med EU"
(16 September 2026). Its findings, all verified against the live site that
day, are folded into `SKILL.md` ("Rules") and `references/party-codes.md`.
Fixed points from it, useful as regression checks:

| Query | Expected (Sept 2026) |
|---|---|
| `Parties=NO` | 101 hits |
| `Parties=IS` | 76 hits |
| `Parties=NO&Parties=IS` | 135 hits (OR: 101 + 76 − 42) |
| `all: [NO, IS]` (local AND) | 42 |
| empty search | 2 363 hits, one page, ~1.6 MB, ~2.4 s from the built-in browser (the memo's 560 ms was for `Parties=NO`) |
| `Parties=XX` | 0 hits, no error |
| party checkboxes | 412 inputs → **256** unique codes (the memo said ~206 — wrong: the form lists one entry per *name form*, and 100 parties have only one, e.g. "Greenland -") |
| `Parties=NO&DateFrom=01/01/2010&DateTo=31/12/2020` | 34 hits, top rows signed 2026 — **`DateTo` is ignored** (`DateFrom` alone also gives 34; `DateTo` alone gives 101) |
| `DateType=eif` | works (32 rows for the range above, different set) |
| `DateType=ratification` | **0 rows, no count text** — behaves like an invalid value although it is an `<option>` in the form |
| `Parties=EC` | Ecuador. The European Community is `CE` (whose short name on the site is "EC") |
| `id=2011036` | Observations "Provisional application as from 21/06/2011"; Austria (`A`) has a declaration; no signature date in the list view |
| `ratification/?id=2011036&partyid=A` | Austria's declaration text |
| `id=2016032` | OJ reference L 141 (28/05/2016) linking to EUR-Lex |
| `id=2009066` | signed 2011 although the ID prefix is 2009 |
| `id=2007059` | one record covering four instruments (Norges traktater `2007-07-25-20` … `-23`) |
| `docLanguage=fr&id=2016032` | French title |

Endpoint parameters (from the memo, corrected by the 2026-09-16 probes):
search `DoSearch=true`, `Parties` (repeatable, OR), `Title`,
`DateType=signature|eif` (`ratification` is dead), `DateFrom` as
`DD/MM/YYYY` (lower bound; `DateTo` is accepted and ignored — the helper
filters locally), `SortOrder=LSF|OSF|LEIFF|OEIFF`, `Lang`. Detail:
`agreement/?id=<7 digits>&docLanguage=<lang>`. Declaration:
`ratification/?id=<id>&partyid=<code>&doclanguage=<lang>` — note the
different casing of the language parameter on the two pages.

## 2. Why Cowork-only: the Cloudflare finding (2026-09-16)

The memo assumed a plain `requests` + BeautifulSoup script would do, and read
`robots.txt` as the constraint (blanket `Disallow: /`, with `Allow: /` for
named crawlers including `ClaudeBot`, `Claude-SearchBot`, `Claude-User`).
That analysis never gets to apply: **the whole `www.consilium.europa.eu`
zone is behind a Cloudflare managed challenge.** Verified from a residential
connection on 2026-09-16:

| Client | Result |
|---|---|
| `curl`, default UA | `403`, `cf-mitigated: challenge`, "Checking your browser before accessing a GSC Managed Website" |
| `curl` with Chrome UA | same |
| `curl` with `ClaudeBot/1.0` UA | same |
| Python `urllib`/`requests` | same (it is not UA-based) |
| `WebFetch` (Claude-User) | `403` |
| `robots.txt` itself | challenged |
| Chrome `--headless=new` via CDP, 90 s wait | stuck on "Just a moment…" |
| `data.consilium.europa.eu` | empty stub; no open-data mirror of the database found on data.europa.eu |

The Cowork session that produced the memo saw sub-second responses because
the Claude Desktop built-in browser is a real browser and passes the check.
The fixture-capture session of 2026-09-16 (≈45 tool calls, ≈30 same-origin
fetches including the 1.6 MB list) never saw a challenge response either. So
the skill follows the `lovdata-pro` pattern: a JS helper pasted into a tab,
doing same-origin `fetch()` from inside the cleared session.

Design decision, stated so it is not re-litigated: the skill does **not**
try to defeat the challenge (no cookie export, no fingerprint spoofing, no
headless browsers). If a response is a challenge page the helper returns
`{error: "challenge"}` and SKILL.md tells Claude to wait or ask the user to
reload. The site operator chose to block automated clients; a legal-research
tool should not be in the business of circumventing that.

Consequences: no Python CLI, no bundled data snapshot (the JS cannot read
local files, and pasting 300 KB into the tab is worse than one 1.6 MB
same-origin fetch), no Claude Code CLI support. `data/parties.json` is the
one data file worth shipping (stable, needed for the code-validation
guidance) — see §4.

## 3. Fixture capture checklist (run once in Cowork)

The parsers in `scripts/browser/consilium.js` were written from the memo's
description of the pages, not from the HTML. `tests/run.js` therefore has a
synthetic layer that always runs and a fixture layer that runs only when
`tests/fixtures/*.html` exist. Capture them like this, in a Cowork session
in this repository:

1. Step 0 of SKILL.md (open tab, paste helper, `await __cs.ready()`).
2. For each row below, run `capture`, then `page(key, n)` for
   `n = 0 … pages-1`, appending each `text` verbatim to the fixture file
   (create the file on `n = 0`). `capture` strips scripts, styles, images and
   site chrome so most pages fit in 1–3 slices; the empty search (1.6 MB)
   is deliberately not a fixture.

   | Fixture file | Call |
   |---|---|
   | `tests/fixtures/search-form.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/?Lang=en")` |
   | `tests/fixtures/search-NO.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/?DoSearch=true&Parties=NO&Lang=en")` |
   | `tests/fixtures/agreement-2011036.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/agreement/?id=2011036&docLanguage=en")` |
   | `tests/fixtures/search-NO-IS.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/?DoSearch=true&Parties=NO&Parties=IS&Lang=en")` |
   | `tests/fixtures/agreement-2016032.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/agreement/?id=2016032&docLanguage=en")` |
   | `tests/fixtures/agreement-2016032-fr.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/agreement/?id=2016032&docLanguage=fr")` |
   | `tests/fixtures/ratification-2011036-A.html` | `await __cs.capture("https://www.consilium.europa.eu/en/documents/treaties-agreements/ratification/?id=2011036&partyid=A&doclanguage=en")` |

   In the 2026-09-16 run every page resolved to `selector_used: "main"`
   and the largest (the form, 120 K chars) took three slices. If `capture`
   ever picks `"body"` with a huge `total`, pass `{selector: "…"}`.
3. **Verify every fixture byte-for-byte.** The tool channel strips trailing
   whitespace before a newline (`…checkbox">Andean Pact - \n` lost its
   space), which made one file 7 characters short and was otherwise
   invisible. Compute a SHA-256 in the browser over the concatenated
   `page().text` and compare with the file on disk; re-transfer any page that
   differs (encoding trailing spaces as a marker and restoring them works).
   The seven fixtures shipped here match their browser hashes; see
   `tests/fixtures/PROBES.md` for the values.
4. Note on the shipped fixtures: they were captured while `capture()` still
   collapsed whitespace between elements (`>\s+<` → `><`). That changes
   `textContent` (`"101 results" + "Sorted by"` became `"101 resultsSorted
   by"`) and broke the text-based count regex, which is why the count now
   comes from `.gsc-u-results-count`. The collapse has since been removed;
   the next capture will be faithful. Text-derived assertions against the
   current fixtures are still valid where the field lives in its own
   element (titles, cells, `<time>`).
5. Record what the parsers see live — `search({parties: ["NO"]})`,
   `search({all: ["NO", "IS"]})` (42), `detail("2011036")`,
   `detail("2009066")` — and every `null`/wrong field, in
   `tests/fixtures/PROBES.md`. The 2026-09-16 report is the model.
6. `cd tests && npm install && npm test`; fix parsers until green; pin the
   expected numbers in `run.js` to the capture date.

## 4. Generating `data/parties.json`

`data/parties.json` (256 entries, `{code, name, long_name, names}`) is the
output of `parsePartyList()` over `tests/fixtures/search-form.html`, and
`tests/run.js` asserts that equality — so regenerating is
`node -e` over the fixture, not a browser session:

```
cd tests && node -e "
const {parseHTML}=require('linkedom'), fs=require('fs'), cs=require('../scripts/browser/consilium.js');
const p=cs._internal.parsePartyList(parseHTML(fs.readFileSync('fixtures/search-form.html','utf8')).document);
fs.writeFileSync('../data/parties.json', JSON.stringify(p,null,1)+'\n');"
```

To pick up new parties, recapture `search-form.html` (§3) and rerun. The
in-browser `partiesDump()` + `page()` route still works and produced the
same code set on 2026-09-16, but the form fixture is the single source.
`name` is the short form (what ratification tables print — "Czechia",
"European Union"); `long_name` the official one, `null` for 13 codes
(`AC ASE CS DA GL HK HV MAL MS PAC SU UN UNR`).

## 5. Tool-channel limits

`javascript_tool` fails hard above ~49–50 K characters of result (measured
for `lovdata-pro`, same channel). `PAGE_SIZE = 45000` in the helper; every
function trims to it. If the ceiling changes, change that one constant.

## 6. Things not built, on purpose

- **Full detail crawl / offline party index.** 2 363 detail pages in a user
  session is a crawl the site did not invite. `details()` is capped at
  concurrency 3 with a delay and meant for a dozen IDs, not the register.
- **Title search via the site's `Title` parameter only.** `find()` does a
  local regex over the cached full list instead — it is one request and lets
  the user search in any language of the titles. It matches title words only;
  Schengen association agreements whose titles do not say "Schengen" are
  missed, and SKILL.md says so.
- **Sending `DateTo` to the site.** It is ignored there (§1), so `search()`
  keeps it local. `dateType: "ratification"` is refused for the same reason.
- **Party codes from the ratification table's own markup.** The party cell is
  plain text; the only `partyid=` link is the declaration link. Codes come
  from `data/parties.json` names instead, which is also why `detail(id,
  "fr")` leaves most rows in `parties_without_code`.
- **EUR-Lex fetching.** `detail()` emits an `eurlex_hint` from the OJ
  reference; the `eurlex` skill does the rest.
