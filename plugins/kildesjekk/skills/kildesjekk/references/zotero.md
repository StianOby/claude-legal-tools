# Zotero: finding an item and reading it

How to look a source up in the user's Zotero library with the zoteus MCP (tools named `zotero_*`; if they are not in your tool list, find them with ToolSearch `zotero`). Read this before the first Zotero call.

Where this file says to leave a row at checked = "no", a retrieval worker writes the outcome `not_here` instead (see `retrieve.md`).

All tools are called against the personal library; do not pass `library_type` or `library_id`.

## Finding the item
Search with `zotero_search_items`. Put the most distinctive part of the reference in `q` (author surname plus a title word, a case number, a citation number). Every space-separated word in `q` must match. The default `qmode` matches title, creators and year; when that finds nothing, Zoteus automatically retries in `everything` mode (all fields, notes and PDF text) and marks the response `broadened: true`. Narrow with `itemType` when the category is known (e.g. `case`, `book`, `journalArticle`, `bookSection`) and use `response_format: "detailed"` when you need to disambiguate between similar hits.

Two things to know about the `itemType` filter:
- Matches inside the PDF text are returned as the *attachment* item, not its parent. An `itemType` filter therefore hides them. When you need a hit from inside the text, search without `itemType`, then call `zotero_get_item` on the attachment key and follow its `parentItem` to the record.
- Matches in metadata fields (e.g. "Docket number", "History") are returned as the parent item and survive the filter.

Searching inside PDF text is reliable only for distinctive strings. Short tokens ("Rt.") and common words ("side") get lost, and hyphenated identifiers behave inconsistently: in testing "HR-2016-2554-P" missed the judgment while "HR 2016 2554 P" found it, whereas "LF-1998-997" worked as written. When a text search fails, retry with spaces in place of hyphens, then with a distinctive phrase of 5–8 consecutive words. Metadata searches on `caseName`, `docketNumber` and the like are not affected.

For case law, the default quick search matches the "Case name" field. The case number (e.g. C-123/17, HR-2026-123-A) is in "Docket number" and is reached by the broadened search.

Item types used in the library: judgments are `case`; Norwegian preparatory works are `bill` (preferred) or `report` depending on how they were entered (see `zoteus-prepworks.md`); treaties are `statute` with "type: treaty" in the Extra field; literature is `book`, `bookSection`, `journalArticle` or `thesis`. `statute` items keep their name in `nameOfAct`, so search results list them as "(untitled)" — recognise them by `shortTitle` (e.g. "UNCLOS", "ECHR") and confirm with `zotero_get_item`. Treaty numbers sit in `publicLawNumber` ("ETS No. 5"), in `code`/`codeNumber` ("UNTS" 1833) or, for agreements published in the Official Journal, in `code`/`codeNumber`/`pages` ("OJ 2001 L" 93 "40-47") and are reached by the broadened search.

Confirm every hit with `zotero_get_item` (`item_key`, `include_children: true`). This returns the full record (all bibliographic fields) plus the child attachments and notes. Check author, title, year and edition against the reference before reading, and note the attachment keys.

## Reading the source
Read the text with `zotero_get_fulltext`. Passing the parent `item_key` resolves the item's best PDF (or EPUB) automatically. Useful parameters:
- `query` — returns the passages most relevant to a phrase, each with an approximate page. This is the fastest way to locate a quotation: pass a distinctive phrase of 5–8 consecutive words from it.
- `page_range` (e.g. `"41-43"`, 1-based PDF pages) — reads a span in full. Use it to verify a quotation verbatim in context and to read the running header.
- `max_chars` — the default cap is 12 000 characters (maximum 100 000). Raise it when you need to read a quotation in context.
- `precise_pages: true` — with `query`, re-extracts the PDF so each passage carries an exact `page` instead of `pageApprox`. Try it first; the response's `pageSource` says whether you got `"exact"` pages or an estimate.
- `outline: true` returns the PDF's table of contents only when Zoteus has its optional PDF parser installed. If it errors, skip it.
- `zotero_pdf_images` (same `item_key`, a page span) renders pages as images. Use it for a scanned PDF whose text layer is missing or garbled — old Norwegian books typically — so the quotation can still be read off the page instead of the row being marked unavailable. It refuses PDFs over about 20 MB (see below).

Page numbers: unless that optional parser is installed (or `precise_pages`/`page_range` re-extracted the file — `pageSource: "exact"`), every page number Zoteus reports is an estimate (`pageApprox`) derived from character counts, and the estimate drifts through a document — in testing the gap between PDF page and printed page was 5 at PDF page 30 and 3 at page 60 of the same book. Therefore:
- Never convert an estimated page to a printed page with a fixed offset for the whole item.
- To reach a printed pinpoint, read a small `page_range` near the expected position, find the running header or printed page number in the text, and step forward or back until the header shows the cited page. Use the printed pagination in the worklist.
- To verify a quotation: `query` with a distinctive phrase, note `pageApprox`, read a `page_range` around it, confirm the text verbatim, and take the printed page number from the header.

PDFs larger than about 20 MB are served from Zotero's stored index rather than re-extracted; the response says so in `notice`. `page_range` and `query` still work, but `precise_pages` is skipped and `zotero_pdf_images` refuses the file, so there is no page image to look at. Scanned books are often this large. For them:
- Settle the printed page from the running headers of the neighbouring pages (e.g. headers 21, 22, ?, 24 around the quotation put it on 23). A page number in the OCR text can itself be misread.
- A difference the OCR cannot show, such as en dash against em dash or a lost diacritic, is not a "Quotation not verbatim" finding. Say in the description that it could not be checked.
- If the page image matters and the book is on nb.no, fetch that one page through §15 of SKILL.md. Otherwise ask the user to look at the page in Zotero. (A retrieval worker does neither: it says in the evidence file's `note` that the page image could not be read.)

Note that a single Zotero item may contain multiple attachments (e.g. PDFs). `zotero_get_fulltext` selects one attachment automatically; if it does not contain what you are looking for, take the other attachment keys from the `zotero_get_item` children list and call `zotero_get_fulltext` with that attachment key as `item_key`.

If you don't find any fulltext (e.g. only metadata and no attachments, or `zotero_get_fulltext` returns nothing even with `fallback: true`) when you look up an item in Zotero, leave the reference as "checked" = "no" (if the source can be found with other tools, it will then be picked up in a later step).

Certain Zotero items, notably some monographs, will only have a single PDF attachment with a Table of Contents or a short excerpt, and not the full text. These can be marked as "checked" = "no" (so that they may be picked up in a later step).

## Semantic search (secondary)
`zotero_semantic_search` searches by meaning and, if the user has built a full-text index, also inside PDF bodies. It always searches the personal library and cannot be pointed at a group library. Not every user has built this index, so:
- Always call it with `auto_build: false`. If it reports an empty or missing index, skip it — do not start an index build.
- Use it only after the metadata search in "Finding the item" has been tried: to find a quotation whose reference appears to be wrong (candidate for "Wrong source" or "Wrong page/section/paragraph"), or when a work you would expect to be in the library did not surface by title/creator.
- Hits are often listed as "(untitled)" with only a key, snippet and score. Identify each hit with `zotero_get_item` before doing anything else with it.
- A semantic hit is a lead, never a verification. Always open the record with `zotero_get_item` and read the passage with `zotero_get_fulltext` before filling in the worklist.
