# eurlex: what the skill adds to the MCP server

Last reviewed against: eurlex-mcp-server **2.4.5** (2026-11-24).

The skill covers only what the eurlex MCP server's own tool descriptions do
not. Parameters are left
to the server, so they cannot go stale here.

Why a skill is still needed: the server sends no `instructions`, and its
guide is an MCP *prompt* (`eurlex_guide`), which clients normally leave to
the user to pick. Claude normally sees only the tool descriptions. The skill
adds triggering, installation help, case number to CELEX, quoting by
paragraph, citation, authentic language, routing to the other skills, and the
traps below.

## Traps, as tested on 2.4.5

| Trap | Evidence | Upstream |
|---|---|---|
| `eurlex_consolidated` returns future versions | 32013L0034 and 32009L0138 → 2027-01-30 | [#85](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/85) |
| No way to read a dated consolidation, or to outline one | `celex_id` pattern rejects the hyphen; dated ELI not resolved; GDPR Art. 2 offset 155643 is Art. 65 territory in the consolidated text | [#86](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/86) |
| Case number in `query` depends on the hyphen used in the title | C-131/12 only with U+2011; C-311/18 and C-252/21 only with U+002D | [#87](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/87) |
| Guide is only a prompt | `src/server.ts` | [#88](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/88) |
| `eurlex_metadata` times out (about 92 s) | 3 of 9 calls | – |
| No paragraph outline | 62012CJ0131, 61962CJ0026; opinions 62012CC0131, 62021CC0252, 62024CC0312; 62000CJ0112 lacks paragraph 1 | – |
| Undecoded HTML entities in plain text | 62000CJ0112, 62024CC0312 | – |
| `eurlex_summary` on a judgment gives another case's summary | 62012CJ0131 → headed C-507/17 | – |
| Consolidated version exists but is not retrievable | 32003L0088 | – |

## Full-text search of case law (1.3.0, 2026-11-24)

**Why:** the server works on Cellar, whose SPARQL endpoint holds metadata; the
texts are separate files. `eurlex_search` and `eurlex_case_law` match titles.
The server's other possible source, the EUR-Lex SOAP web service, has full-text
search but needs registration and has a daily limit; the EUR-Lex site's search
page answered an empty 202 to the honest UA.

**What:** `scripts/case_law_search.py` sends one POST to InfoCuria's backend,
`https://infocuriaws.curia.europa.eu/elastic-connector/search`. It is found in
the site's `assets/config/config.prod.json`, undocumented, and needs no login
or cookie. The honest UA got 200 from a residential IP and from the cloud
sandbox.

**Maintainer's decision (2026-11-24):** rely on it, as long as it is used only
when full-text search is needed. Hence the "Need / Tool" table in SKILL.md, and
the rule against web search and the websites (Claude Desktop had been
improvising with both). Terms: the copyright page
(`https://curia.europa.eu/site/jcms/d2_5167/en/copyright`) permits reproduction
of case law with the source acknowledged; no clause on automated access was
found, but the terms were seen only as search excerpts (WebFetch got 403 from
curia.europa.eu). `robots.txt` on infocuria.curia.europa.eu: `Allow: /`.

Behaviour, as probed:

| Point | Evidence |
|---|---|
| Quoted = exact phrase; unquoted = the words | 382 / 4,707 |
| Terms are ANDed; `OR` breaks quoted phrases | `A` 62 hits, `A OR A` 389 |
| `isSearchExact` had no effect on an unquoted query | 4,707 either way |
| Filters go in `filtersValue`, as `{field, values}`; dates as two values | `docTypeCode`, `affairJurisdictionCode`, `docDate` |
| An unknown filter field gives 0 hits, no error | hence the control searches on every 0 |
| `advancedFiltersValue` with `docTypeCode` replaced the query | 68,750 hits; not used |
| `pageNumber` is zero-based | page 2 differs from page 1 |
| A joined-case document comes once per case | same ECLI; deduplicated |
| `_DR` = summary notice (site label "Judgment (Information)"); full text is an `_NP` document under the same CELEX | T-196/19: notice in 23 languages, judgment in DE and FR; Cellar serves the FR text (`text/html`), 404 for EN |
| Index name ends in a date (30-06-2026) that is not its cut-off | newest hit 2026-11-19 |
| About 320 KB for 20 hits | the script prints a few lines per hit |

Not used: the `citationsMotif`, `citationsDispositif` and `citationsConclusion`
facets (acts and provisions cited, e.g. `12008M004-P3`). Cellar has the same
data with citing paragraphs, so cases on an article go through
`eurlex_sparql`. Both lack some tags (C-307/22 for Article 12(5) GDPR).

Judgments (Court of Justice and General Court) with no article tag on any
`cdm:work_cites_work` relation, by date of judgment, measured 2026-11-24:
2018-21 22/3813, 2022 41/934, 2023 32/953, 2024 69/1021, 2025 111/927, 2026
498/814. By month in 2026: January 5/71, April 11/74, July 83/83, September
131/131, November 94/94 (the others not sampled). In 172 preliminary rulings
(case years 2005-2024), the article named in the operative part was tagged in
all judgments that had tags but one (62010CJ0256, Article 16); exact paragraphs
in about 82 % (untagged judgments included), so search the whole article too.

The maintainer therefore decided (2026-11-24) on one full-text search, limited
to the last four years, after the SPARQL query, and none for older cases. Measure
again before changing this.

Why four years (14 provisions, French search, measured 2026-11-24): judgments
naming the article in the operative part that SPARQL does not return, by window:
2 to 3 years 7, 3 to 4 years 3, 4 to 5 years 0; all ten lack article tags. Three
of them (Charter 47 twice, 108(3) TFEU) lie beyond the 50 listed hits. For the 11
narrower provisions the average is 14 / 22 / 30 / 36 hits for 2 / 3 / 4 / 5 years;
of the 80 hits in years 2-5 that SPARQL lacks, 8 are such judgments.

That search runs in French. Compared on 2026-11-24 (last two years): the same 3,
19 and 16 hits as in English for Articles 12(5) and 15 GDPR and 3 InfoSoc; 47
against 34 for Article 108(3) TFEU, all the extra ones but one `_NP`; 305 against
229 for Article 47 of the Charter. French misses `paragraphes 1 et 2` (C-579/24,
Article 3(1) InfoSoc) and a subparagraph inside a Treaty reference (`article 4,
paragraphe 3, premier alinéa, TUE`; 8 of 50 English hits missed, the cause seen
in 3 of the 4 checked). `OR` is no remedy:
the backend does not keep quoted phrases exact around it (`A` 62 hits, `A OR A`
389), so SKILL.md says to search alternatives separately.

If it breaks, look at the request the site itself sends and compare.

## Reviewing a new release

1. Compare the source with the last reviewed version (`git diff v2.4.5..` in
   a clone of the server's repository). If nothing under `src/` changed, go
   to step 5.
2. List the tools of the new version and compare their names and descriptions
   with "Which tool when" in SKILL.md, and check whether the server now sends
   `instructions`.
3. Rerun the calls in the table above and check the linked issues. Remove a
   trap from SKILL.md and the table once its fix is released; add new ones.
4. If SKILL.md changed, bump the plugin. If kildesjekk's EU section (§9)
   relies on what changed, update it too.
5. Update "Last reviewed against" at the top.
6. If the server gains full-text search, consider dropping the script.
