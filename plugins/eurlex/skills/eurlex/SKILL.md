---
name: eurlex
description: |
  Load before calling any *__eurlex_* tool, even for one known CELEX or paragraph. Use for any EU-law question that needs the text or metadata of a CJEU/General Court judgment, order or AG opinion, or an EU regulation, directive or decision — if the user gives a CELEX (32016R0679, 62012CJ0131), ECLI (EU:C:2014:317), case number (C-131/12), case name (Google Spain, Schrems II), act name (GDPR, AI Act), or asks to quote/verify a paragraph or article, find case law interpreting an act or article, search case law full text ("cases on abuse of rights", "judgments mentioning X"), get a consolidated version, or check dates/transposition. Prefer over web search and EUR-Lex/Curia websites. Guide to the eurlex MCP server (user-installed), plus a full-text case-law search script. Do NOT use for: EFTA Court (efta-court); EEA status of EU acts, JCDs (eea-lex); ECtHR (hudoc); Council of Europe treaties (ets); Norwegian law (lovdata-api/lovdata-pro); Norway's treaty register (norges-traktater); UN treaties (untc).
---

# eurlex — using the EUR-Lex MCP well

Everything is done with the eurlex MCP server, except full-text search of case
law, which it lacks and `scripts/case_law_search.py` provides. The server
([Honeyfield-Org/eurlex-mcp-server](https://github.com/Honeyfield-Org/eurlex-mcp-server))
is installed by the user separately (the `eurlex` plugin does not bundle it).
Its tools are the ones whose names end in `__eurlex_<tool>` (pattern
`*__eurlex_*`, e.g. `mcp__eurlex__eurlex_fetch`), with `<tool>` one of the
names listed below. The prefix before `__eurlex_` varies by client
(cloud Cowork adds `mcp__remote-devices__`) and by the name the user gave the
server, so never assume one. The tools are often deferred: run one ToolSearch
with query `eurlex` and `max_results` 20 before deciding they are absent, and
use the names that come back. If no `*__eurlex_*` tools are present, stop and
tell the user the
server has to be added first — in Claude Desktop under **Settings →
Developer → Edit Config** (`claude_desktop_config.json`, under
`mcpServers`), then restart the app:

```json
"eurlex": { "command": "npx", "args": ["-y", "eurlex-mcp-server"] }
```

## Which tool when

Parameters are documented in the tools' own descriptions; read those. This
list only says which tool to pick.

- **Text of an act, treaty article or judgment:** `eurlex_fetch`. Pass
  `format: "plain"` (the default is `xhtml`).
- **Consolidated text of an act:** `eurlex_consolidated`, also with
  `format: "plain"`. Check the date it returns (see "Consolidated versions").
- **Where an article or paragraph begins:** `eurlex_structure`.
- **Dates, in-force status, legal basis:** `eurlex_metadata`. `null` means
  "not recorded". For staged application read `dates_effect`, not only
  `date_application`. It gives neither ECLI nor language of the case.
- **Case law, and the ECLI of a case:** `eurlex_case_law`, with
  `type: "JUDG"` when you want the judgment itself. Its `query` matches
  titles only; for words inside judgments see "Full-text search" below.
- **Legislation by title / by topic:** `eurlex_search` / `eurlex_by_eurovoc`.
- **What cites, amends, repeals what:** `eurlex_citations`.
- **National implementing measures:** `eurlex_transposition`.
- **Plain-language overview:** `eurlex_summary`. Never a source for a
  quotation. Given a judgment it can return the summary of an act or case
  line that mentions it (for Google Spain, one headed by C-507/17).
- **Anything else:** `eurlex_sparql`.

**Do not use web search, the EUR-Lex or Curia websites, or the browser** to find
or read EU acts and case law, unless the user asks for it. If neither the
MCP server nor the script gives the answer, say so and let the user choose.

EUR-Lex has no Norwegian texts. For Norwegian users fetch `ENG` (what
Norwegian legal writing cites) and, when wording matters, the language of the
case (see "Authentic language" below).

## Identifiers: getting to a CELEX

The MCP takes CELEX everywhere, plus ECLI in `eurlex_case_law` and ELI /
OJ references for legislation. Convert what the user gives you:

- **Case number → CELEX (sector 6):** `6` + 4-digit year + type + number
  padded to 4 digits. `C-131/12` → `62012CJ0131`. Court of Justice:
  `CJ` judgment, `CO` order, `CC` Advocate General opinion. General Court:
  `TJ` judgment, `TO` order. Joined cases use the first number. Old cases
  keep their real year: `26/62` (Van Gend en Loos) → `61962CJ0026`.
- **ECLI:** pass straight to `eurlex_case_law` (`ecli: "ECLI:EU:C:2014:317"`);
  the result gives the CELEX and title.
- **Case name only** ("Schrems II", "Bauer"): `eurlex_case_law` with `query`
  matches the *title*, so search a party name, not the nickname; narrow with
  `type: "JUDG"`, `date_from`/`date_to` or `court`. Without `type`, notices and
  résumés come too (`62012CA0131`, `62018CJ0311_RES`); a CELEX ending `_RES`
  cannot be fetched, so drop the suffix. If that fails, use `related_celex` with
  the act the case interprets, or `eurlex_sparql`.
- **Case number as a `query`:** titles write it either with an ordinary hyphen
  (`C-311/18`) or a non-breaking one (`C‑131/12`), and only the matching form
  is found. Build the CELEX instead, or search both forms.
- **Treaty article:** sector 1, e.g. `12016E267` (Article 267 TFEU),
  `12016M006` (Article 6 TEU), in `eurlex_fetch`.
- **Act name / number:** `eurlex_consolidated` with `doc_type: "reg"`,
  `year: 2016`, `number: 679` needs no CELEX at all. Otherwise
  `eurlex_search` (`resource_type: "REG"|"DIR"|"DEC"`) or ELI short form
  `reg/2016/679` in `eurlex_fetch`.

## Cases on a particular article

`related_celex` takes a whole act. Cellar also records which provision a
decision cites or interprets, and in which of its paragraphs (`N 49`). Query it
with `eurlex_sparql`, here for Article 12(5) GDPR:

```sparql
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX annot: <http://publications.europa.eu/ontology/annotation#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?case ?how ?prov ?paras WHERE {
  VALUES ?act { "32016R0679"^^xsd:string }
  VALUES (?rel ?ann ?how) {
    (cdm:work_cites_work annot:fragment_cited_target "cites")
    (cdm:case-law_interpretes_resource_legal annot:reference_to_modified_location "interprets")
  }
  ?t cdm:resource_legal_id_celex ?act .
  ?a owl:annotatedTarget ?t ; owl:annotatedProperty ?rel ; owl:annotatedSource ?w ; ?ann ?prov .
  ?w cdm:resource_legal_id_celex ?case .
  FILTER(REGEX(STR(?prov), "^A12P5([^0-9]|$)"))
  FILTER(REGEX(STR(?case), "^6....[CT]J"))
  OPTIONAL { ?a annot:fragment_citing_source ?paras }
} ORDER BY DESC(?case) LIMIT 100
```

- **Provision codes:** `A12` article, `P5` paragraph, `L1` subparagraph, `LB`
  point (b), `SNT2` sentence, `C63` recital. The pattern above includes
  everything below Article 12(5). **Single-digit articles are zero-padded:**
  Article 3(2) is `^A0?3P2([^0-9]|$)` (without the `0` the query finds next to
  nothing). Articles 3a and 3b are `A03BIS` and `A03TER`. Decisions are often
  tagged only with the article, so also try `^A12([^0-9]|$)` (the paragraphs
  then come along).
- **Case types:** `[CT]J` is judgments; use `[CT][JCO]` to add AG opinions
  and orders.
- **Treaty and Charter articles** have a CELEX of their own, one per edition,
  and cases are spread over them: put all in `VALUES ?act`, e.g.
  `"12008E267"^^xsd:string "12010E267"^^xsd:string "12012E267"^^xsd:string
  "12016E267"^^xsd:string` (TEU likewise with `M004`; Charter `12007P007`,
  `12010P007`, `12012P007`, `12016P007`). The provision code then starts at
  the paragraph: `^P3([^0-9]|$)` for Article 4(3) TEU. For a whole article, replace
  `; ?ann ?prov .` with `.` and the `?prov` filter with
  `OPTIONAL { ?a ?ann ?prov }`.
- **100 rows, or `truncated: true`** (100 is the tool's maximum) means there are more: narrow the years in
  the `?case` filter (`^6202[0-9][CT]J`) and repeat. One case can have several
  rows.
- **Older cases** may be tagged with the article's former number or the
  predecessor act; search those too when they matter.
- **Recent judgments are missing:** for several months after delivery they have
  no article tags at all, and some of the later ones never get any. So after the
  SPARQL query, unless the user only asks about older cases, run **one**
  full-text search for the article and the act, from four years before today,
  **in French**, the Court's working language (unpublished judgments are usually
  not translated into English):
  `'"article 12, paragraphe 5" "2016/679"' --language FR --type judgment --from <date> --newest --size 50`.
  Use the paragraph if the user asked for one, otherwise `"article 12"`. The
  French forms are `article 5 bis` (5a), `article 267 TFUE`, `article 47 de la
  Charte`, `article 4, paragraphe 3, TUE`. Other wordings are missed (`article 3,
  paragraphes 1 et 2`; `paragraphe 3, premier alinéa, TUE`).
  Look only at hits not already in the list. Many concern the same number in
  another act or only mention the article: drop a hit without fetching it when
  the snippet shows another act, and fetch the others before relying on them
  (`FRA` if there is no `ENG`). Say which search found a case. If there are more than 50
  hits, give the number and say that only the newest 50 were listed.
- **No full-text search for cases older than that**, nor for the provision's
  wording, unless the user asks; there the tags are good. They are still not
  complete, so do not say that the list has every case.

## Full-text search of case law

Use the script **only when the search has to look inside the texts**:

| Need | Tool |
|---|---|
| CELEX, ECLI, case number, case or party name | MCP only |
| Cases interpreting or citing a known act, no particular wording in mind | MCP only (`eurlex_case_law` with `related_celex`, `eurlex_citations`) |
| Where a phrase stands in a known judgment | MCP only: fetch the text and look |
| Cases on a doctrine, phrase or concept, where the question is not about a particular article | script |
| Cases citing or interpreting a particular article | MCP (`eurlex_sparql`), then one script search for the last four years (see "Cases on a particular article") |
| A name or nickname the title search does not find | script, after the MCP search |
| Text, quotation, metadata | always MCP, also for the script's hits (their CELEX and ECLI may be used as printed) |

An MCP timeout is no reason to run the script: retry the MCP call.

Run it in the cloud sandbox (Python standard library only), one search at a
time; never loop through pages or queries to collect material in bulk:

```bash
python3 scripts/case_law_search.py '"abuse of rights" tax' --type judgment --court C --from 2015-01-01
```

- Words must all occur; `"…"` is an exact phrase. `OR` does not keep phrases
  exact, so search alternative phrases separately. **Quote
  phrases:** `abuse of rights` unquoted finds the words anywhere (4,700 hits,
  against 382 quoted). A common phrase is best narrowed with a second term.
- `--type judgment|opinion|order`, `--court C|T|F` (Court of Justice, General
  Court, Civil Service Tribunal), `--from`/`--to`, `--newest`, `--page`,
  `--size`, `--language`. The result also says how many hits there are in all.
- Only texts in `--language` (default `EN`) are searched. Not every decision
  has been translated, so repeat the search in French (`--language FR` with the
  French term) before calling something absent.
- A hit only shows that the words occur, perhaps in a party's argument. The
  snippet is for choosing what to read: fetch the hit's CELEX with
  `eurlex_fetch` before relying on it, and quote from that, never from the
  snippet. If a hit has no CELEX, build it from the case number, and say so if it
  cannot be fetched.
- **Type codes:** `ARRET` judgment, `CONCL` AG opinion, `ORD` order; `_NP` marks
  a decision not published in the Reports. **`_DR` is only a summary notice of
  such a decision.** The search has then matched the notice, not the text. The
  full text exists under the same CELEX, usually only in French and the
  language of the case: if `ENG` is not found, fetch `FRA`, and search again
  with `--language FR`.
- A blank case name is not in the data. Take it from `eurlex_case_law`, or
  leave it out.
- **`SEARCH FAILED` (exit 1) is not a negative result.** The service is
  undocumented and may change or refuse. Retry once, then tell the user that
  full-text search is unavailable, and go on with the MCP tools.
- Tell the user that the hits come from a full-text search of InfoCuria, and
  with which query. If you add a case that the search did not return, say so
  and why, and read it like the others.

## Quoting a paragraph of a long judgment

Long judgments exceed one `eurlex_fetch` call (default 20 000 chars, max
50 000 per call). Do not page blindly from the start:

1. `eurlex_structure(celex_id, language)` — read the `offset` of
   `Paragraph N` for the first paragraph you need.
2. `eurlex_fetch(celex_id, language, format: "plain", offset: <that offset>,
   max_chars: …)` — offsets are for **plain** text in the **same language**;
   mixing `xhtml` or another language misaligns them.
3. Keep calling with `next_offset` until you have the last paragraph; stop
   when `next_offset` is `null`.
4. Quote verbatim with the paragraph number, keeping the source's characters
   (curly quotes, non-breaking hyphens). Never reconstruct a paragraph
   from memory; if the fetched text does not contain it, say so.

The same goes for describing a case: state its facts and reasoning, and cite
paragraphs, only from text you have fetched. Mark anything from memory as such,
case names included. If a document could not be fetched, say that; do not guess
why.

`eurlex_structure` caps at 300 entries and sets `truncated: true` for very
large documents; then fetch by offset ranges and read paragraph numbers from
the text itself.

**No `Paragraph N` entries.** Some judgments (Google Spain, 62012CJ0131; Van
Gend en Loos) and AG opinions generally come back without an outline, though
the tool calls such a document "short" or "PDF". A single number can also be
missing (Schmidberger, 62000CJ0112, starts at 2); it then stands just before
the next one. Without an outline, estimate: fetch a small piece near the end
to learn the last paragraph number and where the grounds end (the operative
part, "On those grounds, the Court … hereby rules", and the costs follow the
last paragraph). Start at about
`N / last_paragraph × <offset where the grounds end>`, minus 10 %, and step
forward or back by the paragraph numbers you see until you have paragraph N.
Using the total length overshoots.

Plain text of older documents can contain undecoded HTML entities (`&uuml;`,
`&hellip;`). Read them as the character they stand for; they are not a
discrepancy in a quotation.

For legislation as published in the OJ, `eurlex_structure` gives article
offsets the same way.

## Consolidated versions

- **The version returned may lie in the future.** `eurlex_consolidated` calls
  its result "currently in-force" but returns the newest consolidation, even
  one dated later than today. Compare `consolidation_date` with today every
  time. If it is later, do not quote it as the law in force: tell the user,
  and find the right version as in the next point.
- **The law on a given date.** The tool takes no date, and `eurlex_fetch`
  rejects a consolidated CELEX (`02013L0034-20260318`) and a dated ELI. List
  the versions with `eurlex_sparql` (slow, about 20–30 s; replace the CELEX):

  ```sparql
  PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
  SELECT DISTINCT ?c WHERE {
    ?w cdm:resource_legal_id_celex ?c .
    FILTER(REGEX(STR(?c), "^02013L0034-"))
  } ORDER BY DESC(?c) LIMIT 100
  ```

  The last eight digits are the date; the version that applied is the latest
  one not after the date in question. If that is the one
  `eurlex_consolidated` returns, use it. Otherwise its text is out of reach:
  give the user the link
  `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02013L0034-20260318`
  and say that you have not read it, or work from the original act and the
  amending acts and say so.
- **Offsets from `eurlex_structure` do not fit consolidated text.** They index
  the OJ version. Page through the consolidated text with `next_offset`, or
  jump by estimate and step until the article heading appears. The annexes
  and amendment list make estimates rough.
- **"No consolidated version available"** means either that there is none
  (often because the act was never amended) or that one exists but "could not
  be retrieved" (e.g. 32003L0088). The message shows which. In the second
  case do not say the act is unamended; check with `eurlex_citations`.
- Report `consolidation_date` with every quotation. Consolidated text has no
  legal effect; where exact wording is decisive, check the OJ text too.

## Authentic language

Judgments are authentic only in the language of the case (usually the
referring court's). If the user's argument turns on exact wording, fetch
that language too and quote both. The language is in a footnote at the very
end of the judgment ("Language of the case: Spanish"); no tool returns it as
a field.

## When something is missing

- **`total_chars: 0` or an error for a CELEX that should exist:** try
  `format: "plain"` vs `"xhtml"`, another language (`FRA` is the working
  language and most complete), and retry once after a short wait — Cellar
  renders some documents on demand. Confirm the CELEX with `eurlex_case_law`
  (`ecli`) or `eurlex_search` before concluding it is absent.
- **"Document not found"** can mean that EUR-Lex has the document only as PDF,
  or that the CELEX is wrong. Confirm the CELEX; if it exists, give the user
  the EUR-Lex link.
- **A timeout is not a negative result.** Any tool that queries Cellar can
  time out (after about 90 s), also on a good query; `eurlex_search` and
  `eurlex_metadata` do so most. Retry the same call. If a search times out
  again, reword it (drop a term, use the party name, add `resource_type` or
  dates). Never report a source as absent, or a row as unverifiable, on the
  strength of a timed-out call.
- **Truly absent from Cellar** (some early orders, unpublished AG opinions,
  material from before electronic publication): say so and give the
  InfoCuria search URL for the user to check manually:
  `https://curia.europa.eu/juris/liste.jsf?num=C-131%2F12&language=EN`.
  Do not guess text.

## Citing

- Case law: *Case C‑131/12 Google Spain, ECLI:EU:C:2014:317, para 80.* Give
  the ECLI (from `eurlex_case_law`, or the script's hit) and the EUR-Lex URL
  `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62012CJ0131`.
- Legislation: article + paragraph + the act's full title once, then short
  title; for consolidated text add "as consolidated on <consolidation_date>".
- Match the user's language in your reply but keep quotes in the language
  fetched, with your own translation after if the user writes Norwegian.

## Scope boundaries

EEA law as applied by the EFTA Court → `efta-court`. Whether and when an EU
act was incorporated into the EEA Agreement, EEA Joint Committee Decisions
not yet in the OJ, EFTA's consolidated EEA annexes → `eea-lex` (it gives the
CELEX of a JCD that is in the OJ; quote that here). ECHR case law → `hudoc`.
Council of Europe treaties → `ets`. Norwegian implementation of EU/EEA acts
→ `lovdata-api` / `lovdata-pro`; Norway's treaty commitments → `norges-traktater`.
