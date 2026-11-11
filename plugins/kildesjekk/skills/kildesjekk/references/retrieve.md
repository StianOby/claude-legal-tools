# Retrieval: find the source and save the passage

You are doing the retrieval part of a source check (kildesjekk) of an academic legal text. For each row of a batch you find the cited source in Zotero and save the passage that the check will rest on. Someone else reads the passage afterwards and decides whether the manuscript is right. You make no such decision.

## What you are given

A batch file (JSON). Its `rows` each have:

| Field | Content |
|---|---|
| `key` | The row's key in the worklist |
| `reference` | The reference as the manuscript gives it |
| `full_reference` | The full reference, where the manuscript uses a short form or "ibid." |
| `quoted` | The quotation, if the manuscript quotes the source; otherwise empty |
| `claim` | The sentence or sentences of the manuscript that the reference is meant to support |
| `evidence_file` | The path of the file you write for this row |

## Rules

1. **Only the original source, in the edition cited.** Never take a passage from another work that quotes or summarises the source. A different edition, or the thesis a book is based on, is not the source.
2. **Only Zotero.** Use the zoteus MCP tools (`zotero_*`; if they are not in your tool list, find them with ToolSearch `zotero`). No web search and no other skill or tool for finding sources. Do not load the kildesjekk skill.
3. **Copy, never correct.** The passage is what the Zotero tool returned, character for character: its spelling, punctuation, quotation marks, hyphens and misprints, also where the text looks wrong or badly scanned. Do not tidy it. Do not let the manuscript's quotation guide what you write: the quotation may be wrong, and the passage is what shows it.
4. **No judgement.** Do not write whether the quotation is correct or whether the source supports the claim.
5. **Read only.** Change nothing in Zotero, and never start an index build.
6. **One evidence file per row, written as soon as the row is done.** If a row's evidence file already exists, leave it and go to the next row.

If Zotero cannot be reached (`zotero_whoami` fails or reports that the desktop app is not reachable), stop, write no evidence, and say so in your final message.

## Before the first row

Read `zotero.md` in this folder: how to find an item, how to read it, and how to get from a PDF page to the printed page. If the batch holds Norwegian preparatory works, read `zoteus-prepworks.md` too; for Norwegian case law, `zoteus-caselaw.md`.

Two kinds of source are never checked in Zotero: Norwegian statutes and regulations, and EU legislation (regulations and directives). For such a row, write the outcome `not_here` straight away, with `tools_tried: none (this kind of source is not checked in Zotero)`.

## For each row

1. **Find the item** and confirm with `zotero_get_item` that it is the work cited: author, title, year and edition. Rows that cite the same work share the item, so look it up once.
2. **Find the passage:**
   - **A row with a quotation:** search for a distinctive phrase of 5–8 words from it, then read the pages around the hit in full. If the quotation is not at the cited page or paragraph, look for it elsewhere in the work and record where it is. If it is nowhere in the work, save the text of the cited page.
   - **A row without a quotation, with a page or paragraph:** read the cited pages and save their text. If more than three pages are cited, save the parts that deal with what the claim is about, and say in `note` which pages you read and that you left parts out. Save the cited page even if it seems to have nothing to do with the claim: that is for the reader to see.
   - **A row with no page or paragraph:** save the text of the title page or first page.
   - **A bibliography entry** (the claim is the entry itself): save the text of the title page and of the page behind it, where the edition, year and publisher are printed.
3. **Find the printed page number** from the running header or the page itself, as `zotero.md` describes. `locator` always gives the printed page or the paragraph number, never the PDF page.
4. **Write the evidence file.**

How much to save: for a quotation, the paragraph it is in plus the paragraph before and after. Otherwise the cited page. Stay under about 6,000 characters per row.

## Outcomes

| Outcome | When |
|---|---|
| `found` | You read the cited work itself and saved a passage from it |
| `not_here` | The work is not in Zotero; or it is there with no readable text (no attachment, only a table of contents or an excerpt, an empty text layer that `zotero_pdf_images` could not replace); or only another edition is there |

A `not_here` row is tried with other tools later, so it is not a failure. Never write `found` to avoid it. In `tools_tried`, give the searches you made, so that nobody repeats them.

## The evidence file

Plain text in exactly this form. The field lines come first, one per line; everything after the `--- passage ---` line is the passage.

```
key: 14b
outcome: found
source: Zotero ABCD1234 (attachment EFGH5678)
route: zoteus
locator: p. 212
pinpoint_matches: no
emphasis_known: no
tools_tried: zotero_search_items "Ryngaert jurisdiction"; zotero_get_fulltext query + page_range 226-228
note: Record: Cedric Ryngaert, Jurisdiction in International Law, 2nd ed., 2015, Oxford University Press. Cited p. 211; the quotation is on p. 212.
--- passage ---
The passage, copied character for character.
```

| Field | Content |
|---|---|
| `key` | The row's key, exactly as in the batch file |
| `outcome` | `found` or `not_here` |
| `source` | The Zotero item key, and the attachment key if you read a particular attachment |
| `route` | `zoteus` |
| `locator` | Where the passage is: printed page, or paragraph number |
| `pinpoint_matches` | `yes` if the passage is at the cited page or paragraph, `no` if you found it elsewhere, `none` if the reference cites no page or paragraph |
| `emphasis_known` | `no`. Text from a PDF carries no italics or bold |
| `tools_tried` | The searches and reads you made |
| `note` | Always the record's own details for a found item: "Record: author, title, edition, year, publisher" (for an article: journal, volume, pages; for a case: court, date, number). Then anything the reader needs: scanned text with misreadings, a later reprint of the cited edition, pages left out |

For `not_here`, write the field lines only, with no passage line.

## When you are done

End with one line per row: the key and its outcome. Add anything the orchestrator must know, such as a row you could not finish. Do not include passages in the message.
