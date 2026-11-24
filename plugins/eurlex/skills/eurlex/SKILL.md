---
name: eurlex
description: |
  Use for any EU-law source question that needs the actual text or metadata of a CJEU/General Court judgment, order or AG opinion, or an EU regulation, directive or decision — whenever the user gives a CELEX (32016R0679, 62012CJ0131), ECLI (ECLI:EU:C:2014:317), case number (C-131/12, T-612/17), case name (Google Spain, Bauer, Schrems II), act name (GDPR, AI Act, Working Time Directive), or asks to quote/verify a paragraph or article, find case law interpreting an act, get a consolidated version, or check dates/transposition. No scripts: a usage guide for the eurlex MCP server (*__eurlex_* tools; the user installs it separately) — case number to CELEX, paging long judgments by eurlex_structure offsets, citing. Do NOT use for: EFTA Court (efta-court); EEA status of EU acts, EEA JCDs (eea-lex); ECtHR (hudoc); Council of Europe treaties (ets); Norwegian law (lovdata-api/lovdata-pro); Norway's treaty register (norges-traktater); UN treaties (untc).
---

# eurlex — using the EUR-Lex MCP well

This skill contains no code. Everything is done with the eurlex MCP server
([Honeyfield-Org/eurlex-mcp-server](https://github.com/Honeyfield-Org/eurlex-mcp-server)),
which the user installs separately (the `eurlex` plugin does not bundle it).
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
  `type: "JUDG"` when you want the judgment itself.
- **Legislation by title / by topic:** `eurlex_search` / `eurlex_by_eurovoc`.
- **What cites, amends, repeals what:** `eurlex_citations`.
- **National implementing measures:** `eurlex_transposition`.
- **Plain-language overview:** `eurlex_summary`. Never a source for a
  quotation. Given a judgment it can return the summary of an act or case
  line that mentions it (for Google Spain, one headed by C-507/17).
- **Anything else:** `eurlex_sparql`.

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
4. Quote verbatim with the paragraph number. Never reconstruct a paragraph
   from memory; if the fetched text does not contain it, say so.

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
  the ECLI (from `eurlex_case_law`) and the EUR-Lex URL
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
