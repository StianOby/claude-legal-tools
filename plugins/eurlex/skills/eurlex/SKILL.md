---
name: eurlex
description: |
  Use for any EU-law source question that needs the actual text or metadata of a CJEU/General Court judgment, order or AG opinion, or an EU regulation, directive or decision — whenever the user gives a CELEX (32016R0679, 62014CJ0131), ECLI (ECLI:EU:C:2014:317), case number (C-131/14, T-612/17), case name (Google Spain, Bauer, Schrems II), act name (GDPR, AI Act, Working Time Directive), or asks to quote/verify a paragraph or article, find case law interpreting an act, get a consolidated version, or check dates/transposition. This skill has no scripts: it is a usage guide for the eurlex MCP server (mcp__eurlex__* or mcp__plugin_eurlex_eurlex__* tools), which must be installed. It tells you how to convert case numbers to CELEX, page long judgments with eurlex_structure offsets, pick plain vs xhtml, and cite correctly. Do NOT use for: EFTA Court (efta-court); ECtHR (hudoc); Council of Europe treaties (ets); Norwegian law (lovdata-api/lovdata-pro); Norway's treaty register (norges-traktater); UN treaties (untc).
---

# eurlex — using the EUR-Lex MCP well

This skill contains no code. Everything is done with the eurlex MCP server
([Honeyfield-Org/eurlex-mcp-server](https://github.com/Honeyfield-Org/eurlex-mcp-server)),
whose tools appear as `mcp__eurlex__eurlex_*` (server configured by the
user) or `mcp__plugin_eurlex_eurlex__eurlex_*` (server bundled with the eurlex
plugin). If neither set of tools is present, stop and tell the user the server
has to be added first — either install the `eurlex` plugin from the
`claude-legal-tools` marketplace, or add it manually:

```json
"eurlex": { "command": "npx", "args": ["-y", "eurlex-mcp-server"] }
```

## Tool map

| Need | Tool | Notes |
|---|---|---|
| Text of an act or judgment | `eurlex_fetch` | `celex_id`, `eli` or `oj_ref`; `format: "plain"` or `"xhtml"`; paginated |
| In-force version of an act | `eurlex_consolidated` | `celex_id` **or** `doc_type`+`year`+`number`; returns `consolidation_date` |
| Outline with character offsets | `eurlex_structure` | Lists articles; for case law lists `Paragraph N` with offset |
| Dates, in-force status, authors, legal basis | `eurlex_metadata` | `null` dates mean "not recorded" |
| Find case law | `eurlex_case_law` | by `ecli`, `celex_id`, party `query`, or `related_celex` (cases interpreting an act) |
| Find legislation | `eurlex_search`, `eurlex_by_eurovoc` | title substring / EuroVoc concept |
| What cites / amends / repeals what | `eurlex_citations` | `direction: cites | cited_by | both` |
| National implementing measures | `eurlex_transposition` | directive CELEX + optional country |
| Plain-language summary (LEGISSUM) | `eurlex_summary` | may return `total_summaries: 0` |
| Anything else | `eurlex_sparql` | read-only SELECT/ASK against Cellar |

Language is a 3-letter Cellar code (`ENG`, `FRA`, `DEU`, `DAN`, `SWE`, …).
Norwegian is not an EU language and EUR-Lex has no Norwegian texts; for
Norwegian users fetch `ENG` (what Norwegian legal writing cites) and, when
wording matters, the language of the case (see "Authentic language" below).

## Identifiers: getting to a CELEX

The MCP takes CELEX everywhere, plus ECLI in `eurlex_case_law` and ELI /
OJ references for legislation. Convert what the user gives you:

- **Case number → CELEX (sector 6):** `6` + 4-digit year + type + number
  padded to 4 digits. `C-131/14` → `62014CJ0131`. Court of Justice:
  `CJ` judgment, `CO` order, `CC` Advocate General opinion. General Court:
  `TJ` judgment, `TO` order. Joined cases use the first number. Old cases
  keep their real year: `26/62` (Van Gend en Loos) → `61962CJ0026`.
- **ECLI:** pass straight to `eurlex_case_law` (`ecli: "ECLI:EU:C:2014:317"`);
  the result gives the CELEX and title.
- **Case name only** ("Schrems II", "Bauer"): `eurlex_case_law` with `query`
  matches the *title*, which starts "Judgment of the Court … " and contains
  the party names, so search the party name, not the nickname; narrow with
  `date_from`/`date_to` or `court`. If that fails, use `related_celex` with
  the act the case interprets, or `eurlex_sparql`.
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

For legislation, `eurlex_structure` gives article offsets the same way;
prefer `eurlex_consolidated` when the user wants what is in force, and
report the `consolidation_date` alongside the quote.

## Authentic language

Judgments are authentic only in the language of the case (usually the
referring court's). If the user's argument turns on exact wording, fetch
that language too (`eurlex_metadata` and the ECLI page show it; the case
language is also printed at the end of the judgment) and quote both.

## When something is missing

- **`total_chars: 0` or an error for a CELEX that should exist:** try
  `format: "plain"` vs `"xhtml"`, another language (`FRA` is the working
  language and most complete), and retry once after a short wait — Cellar
  renders some documents on demand. Confirm the CELEX with `eurlex_case_law`
  (`ecli`) or `eurlex_search` before concluding it is absent.
- **`eurlex_consolidated` says no consolidated version:** the act was never
  amended (fetch the original) or is a decision/judgment (not consolidated).
- **Truly absent from Cellar** (some early orders, unpublished AG opinions,
  material from before electronic publication): say so and give the
  InfoCuria search URL for the user to check manually:
  `https://curia.europa.eu/juris/liste.jsf?num=C-131%2F14&language=EN`.
  Do not guess text.

## Citing

- Case law: *Case C‑131/14 Google Spain, ECLI:EU:C:2014:317, para 80.* Give
  the ECLI (from `eurlex_case_law`/`eurlex_metadata`) and the EUR-Lex URL
  `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62014CJ0131`.
- Legislation: article + paragraph + the act's full title once, then short
  title; for consolidated text add "as consolidated on <consolidation_date>".
- Match the user's language in your reply but keep quotes in the language
  fetched, with your own translation after if the user writes Norwegian.

## Scope boundaries

EEA law as applied by the EFTA Court → `efta-court`. ECHR case law → `hudoc`.
Council of Europe treaties → `ets`. Norwegian implementation of EU/EEA acts
→ `lovdata-api` / `lovdata-pro`; Norway's treaty commitments → `norges-traktater`.
