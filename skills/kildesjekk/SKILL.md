---
name: kildesjekk
description: Run a kildesjekk — verify every reference and quotation in an academic legal text against the original sources, using Zotero, Lovdata, EUR-Lex, HUDOC, EFTA Court, UNTC, ETS, Norges traktater, and Nasjonalbiblioteket. Produces an .xlsx worklist with per-reference status, severity-coded discrepancies, and a metadata sheet. Trigger on "kildesjekk", "source check", "check references", "verify citations", "check footnotes" for an academic article, manuscript, or thesis. Norwegian or English text.
---

You are the user's research assistant. Your task is to assist with a source check of a draft of an academic text. The instructions for the source check are set out below.

You will look up each and every reference in the text, check/assess it, and document the result in an .xlsx file.

# Overview of the workflow
1) Startup: verify tools, ask for the text, extract references.
2) Worklist and output initialization: create .xlsx file with extracted references that will serve as both the output and your worklist, add columns and read the description of the purpose of each column.
3) How to check the references (read these overarching instructions on how to check references).
4) Check sources found in the Zotero library
5) Check EU legal sources
6) Check Norwegian statutes and regulations
7) Check Norwegian preparatory works
8) Check Norwegian case law
9) Check treaties
10) Check ICJ case law
11) Check decisions from the EFTA Court
12) Check ECtHR case law
13) Check Norwegian books
14) Sources not found with the tools
15) Final verification

The work may be extensive and may run over several sessions. Use the .xlsx file as a worklist along the way, by using the "checked" column to keep track of status. Remember to update the "checked" column after each session, so that the next round can pick up the thread without starting over. Save the .xlsx file after every 10 newly-checked references and at the end of each step.

Each step of the workflow is explained in detail below.

# 1) Startup
Verify that you have access to all the relevant tools:
	- MCP servers:
		- zoteus MCP (Zotero; tools named `zotero_*`). Call `zotero_whoami` and confirm it reports the Zotero desktop app as reachable — reading PDFs depends on it.
		- eurlex MCP
	- Claude Desktop's built-in browser (Cowork — `mcp__Claude_Browser__*` tools).
	- Skills:
		- efta-court
		- ets
		- eurlex
		- hudoc
		- icj
		- lovdata-api
		- lovdata-pro
		- norges-traktater
		- nbno
		- untc
	
If there is a tool you do not have access to, stop and explain which one and why. Feel free to suggest a solution. All skills mentioned are available in this GitHub repo: https://github.com/StianOby/claude-legal-tools. The MCP servers can be found here: zoteus MCP: https://github.com/oscardvs/zoteus — eurlex MCP: https://github.com/Honeyfield-Org/eurlex-mcp-server

Ask for the text document in PDF or DOCX format if not already provided.

If a worklist file (Kildesjekk_<documentname>.xlsx) already exists in the working directory, open the existing file and resume from it; do not overwrite. Before resuming, report current status counts (yes / no / source unavailable) and the next step that has un-checked rows, and confirm with the user before continuing. Derive <documentname> from the filename of the document you have just been given (without the extension) before checking for an existing worklist.

Open the PDF or DOCX document and extract all references from the text. Most references are in footnotes, but some references may appear in the main text. There will likely be references to not only literature, but also to legal sources such as cases, legislation, preparatory works, treaties, and so on.

Some references are accompanied by quotations. There will often be many quotations, and they may be found either in the main text or in the footnotes. Quotations may be as short as one or two words, but they may also consist of full sentences.

For the purposes of this source check, a "reference" is any pointer in the text to an external source (a published work, court decision, statute, regulation, treaty, preparatory work, or similar) that can in principle be looked up. A "reference" may also be a cross-reference to another part of the same manuscript (e.g. "see footnote 3 above", "see chapter 2", "see section 4.3"). A pointer to an external source without any pinpoint (e.g. "see also Smith (1962)" with no page) is still a reference and should be extracted.

Short forms are often used in the notes, particularly for literature references. They may e.g. look like this: Smith (1962). For such short references, cross-check against the bibliography at the end of the text to find the full bibliographic information for all literature references. If the short form is ambiguous against the bibliography, set discrepancy = yes, use the label "Ambiguous reference" in the type-of-discrepancy column, and explain in the description column rather than guessing.

For chain references (ibid./op.cit./same work p. X), follow the chain back to the full reference in order to identify the source you are to look up. Write both what is actually stated in the reference (e.g. ibid.) and the full reference (e.g. Smith 1962 p. 149) in the "reference" column, separated by |. If the chain cannot be resolved unambiguously (e.g. multiple preceding references could be the antecedent of ibid.), record both candidates in the reference column separated by |, set discrepancy = yes, use the "Ambiguous reference" label, and flag this in the description column.

# 2) Worklist and output initialization
Create an .xlsx file, and save it in the working directory. File name: Kildesjekk_<documentname>.xlsx The <documentname> placeholder in the file name must match the Document name value in the Metadata sheet.

This .xlsx file will serve as both your final output and your worklist. Include the following columns in the .xlsx file:

| Column | Purpose |
|---|---|
| footnote no./location in text | Where in the manuscript the reference appears (e.g. `12`, `21b`, `text p. 14`) |
| checked | One of `yes`, `no`, `source unavailable` |
| reference | The reference as it appears in the text |
| quoted text | Verbatim quotation from the text, with the original quotation marks (`""` / `«»`) |
| discrepancy | `yes` or `no` |
| type of discrepancy | Short label (see "The 'type of discrepancy' column" below) |
| severity | `high`, `medium`, or `low` |
| description | 1–3 sentence explanation; for quotation discrepancies include the correct text from the source |
| link/reference to the source you have consulted | Identifier or URL of the source consulted (URL, Zotero reference/URL, CELEX number, etc. — depending on where the source was retrieved from) |

The .xlsx file should contain one row for each reference. Ignore footnotes that contain no references or quotations (these do not need their own rows in the .xlsx file).

Row colours (to be set after checking a reference):
	- No discrepancy (discrepancy = no): green background (C6EFCE).
	- Low severity: light yellow background (FFEB9C).
	- Medium severity: orange background (FCD5B4).
	- High severity: red background (FFC7CE).
	- Source unavailable: grey background (E5E5E5).

When checked = source unavailable, leave the "discrepancy", "type of discrepancy", and "severity" columns blank. The grey row colour alone signals the status.

The following sections contain comments on some of the columns.

In addition to the main worksheet, create a second worksheet named "Metadata" in the same .xlsx file. The Metadata sheet shall contain the following key–value rows in column A and column B:

- `Document name` | the file name of the text being checked
- `Date of source check` | the date the worklist was created (ISO format, YYYY-MM-DD)
- `Total references identified` | the total number of references extracted from the text (footnote + main-text references)
- `Footnote references` | the count of references found in footnotes
- `Main-text references` | the count of references found in the main text

Fill in the Metadata sheet immediately after extracting all references from the text, before you start populating rows in the main worksheet. Confirm the totals in your reply to the user before proceeding with the source check (steps 3 onwards).

## The "footnote no./location in text" column
List all footnotes containing references in numerical order (1, 2, 3 …). If a footnote contains several references, you shall add a letter in alphabetical order (21a, 21b, 21c …) so that each individual reference gets its own row.

If the manuscript uses chapter-restarted footnote numbering, prefix the footnote number with the chapter number separated by a dot (e.g. 2.21b for chapter 2, footnote 21, second reference). Use a single sequence (no chapter prefix) only if the manuscript itself does so.

After all references found in footnotes, you shall list references found in the main text (e.g. as "text p. 14") in ascending order by page number.

## The "checked" column
This column functions as a status overview (worklist) for you. It also lets the user verify that you have checked all sources.

Do not fill in "checked = yes" if you have not actually had access to the original source. Shortcuts of the type "as cited 
in" and other "hearsay" *must be avoided*. You must *never* check a source or verify a quotation from a different source. For sources you cannot access directly you *must always* fill in "source unavailable" in the "checked" column.

## The "reference" column
Here you include the reference itself, as it is formulated in the text.

## The "quoted text" column
Shall only be filled in for direct quotations. Fill in the entire quotation from the text verbatim, including the quotation marks (""/«»). Preserve any italicisation, emphasis, or original punctuation in the source comparison too — these matter for verbatim checks.

You must check that all direct quotations are reproduced verbatim from the cited source. Check every single quote with a reference, regardless of length. Do *not* limit yourself to checking only substantive quotes. Quotes as short as a single word must be checked against the source referenced.

## The "type of discrepancy" column
Use one of the following short labels where possible. If none fit, write your own short label (1–4 words) and explain in the "description" column.

Suggested labels:
- Quotation not verbatim
- Wrong page/section/paragraph
- Claim not supported
- Weak support
- Assessment uncertain
- Outdated/superseded source
- Ambiguous reference (e.g. unresolved short form or chain reference)
- Wrong source (the reference points to the wrong work entirely)
- Citation format error (e.g. wrong year, wrong volume, wrong case number)

Leave this column blank if discrepancy = no or if checked = source unavailable.

## The "description" column
Should contain a very short explanation (preferably 1–3 sentences) of what is wrong/inaccurate. Feel free to suggest how the discrepancy might be corrected.

Here are examples of such short descriptions of discrepancies (with contextual additional information given in parentheses for clarity):
	- the quotation is not verbatim (explain the discrepancy between the quotation and the source text)
	- the reference is to the wrong page/section/paragraph (feel free to suggest which page/section/paragraph in the source that you presume the author meant to refer to)
	- the source does not appear to support the point made in the text (feel free to explain why you consider that the source does not sufficiently support the point)
	- the reference is correct, but the source is outdated/superseded, e.g. by new statutes/regulations, new editions of books, etc. (feel free to include a reference/link to the updated source, and, if you have access to it, please check whether the updated source still contains the verbatim quotation or still supports the claim made in the text).
	- if a source is unavailable, set out under "description" which tools you used to search for the source.

If you use page numbers when referring to the source, use the printed pagination (which generally does not correspond to the pagination in the PDF).

# 3) How to check the references

## Where to look
For each reference, you must look up the source and read the text referred to (if reference is made to a specific page, section, or specific paragraph in the source, you must look up that).

**Always** look up the original source document. If you cannot find it, write "source unavailable" in the "checked" column. *Never* check against a different version or edition of a source than the one referred to in the text (e.g. never substitute a book with the PhD thesis upon which the book is based, if only the PhD thesis is available). Use the printed pagination (which generally does not correspond to the pagination in e.g. the PDF).

## Correspondence rules
Check that what is stated in the source corresponds with what is stated in the text. Where there is a direct quotation (either in the footnote or in the main text), check that the quotation is reproduced verbatim from the source.

For references with a pinpoint (page, section, or paragraph), it is important that you check that:
	- any quotation appears on exactly the page/paragraph/etc referenced.
	- the claim in the text that the reference is supposed to support is in fact supported by the particular page/paragraph/etc of the source to which reference is made.

Where there is a direct quotation, you must:
	- Check that the quotation is a *verbatim* restatement of what is stated in the source, on the exact page/paragraph/etc that is referred to. If there is a discrepancy, that is normally of "high severity". If the discrepancy consists only of different quotation marks being used for a quote-within-a-quote (e.g. "" instead of ''), it shall be classified as "low severity".
		- Bracketed insertions ([…]) and ellipses (… or […]) are scholarly conventions for clarifying or shortening a quotation and do not, in themselves, constitute a discrepancy. Verify that:
			- the unbracketed text matches the source exactly,
			- bracketed insertions accurately reflect what they replace or clarify (or are a faithful [sic]),
			- the omission marked by the ellipsis does not change the sense of the passage.
	- If relevant, you must also check whether the quotation supports the claim made in the text.

For all references without a direct quote, you must:
	- Check whether the source supports the claim made in the text. In making this assessment you may use, for example, the following characterisations:
		- "Obvious discrepancy": The source says something different, or contradicts the claim. -> Usually high severity.
		- "Weak support": The source is only indirectly relevant, or the point in the text is sharpened well beyond what the source can bear. -> Usually medium severity.
		- "Uncertain": The source is difficult to interpret, or requires academic judgement. -> Usually medium severity. If you are in doubt about severity in cases of "uncertain", write "assessment uncertain" explicitly in the "description" column.

For references without a pinpoint (page, section, or paragraph), you must:
	- Check that the cited work exists, is correctly identified (author, title, year, edition), and is broadly relevant to the surrounding claim.
	- If the surrounding claim is sharp enough that pinpoint support would normally be expected, set discrepancy = yes with type "Weak support" or "Wrong source" depending on the case, and explain in the description.

For internal cross-references, you must:
	- look up the relevant footnote/page/section
	- assess whether the cross-reference seems useful or reasonable.
	- mark checked = yes (or yes with a discrepancy and description as appropriate).

Internal cross-references are checked at this point — by reading the manuscript itself. No per-tool step in §§4–13 handles them. Carry out the internal-cross-reference check at the start of the per-tool steps, before §4.

## Flagging
Identify all errors or inaccuracies. Feel free to mark uncertain assessments explicitly, so that the user can see the difference between, for example, "this is an obvious discrepancy" and "I think the support is weak here, but you should read it yourself".

What is most important is that discrepancies (errors and inaccuracies) are flagged. It is not decisive whether you manage to work out how the reference or the text ought to have looked, nor the severity level.

If a single reference contains more than one independent discrepancy, pick the most severe one for the type of discrepancy and severity columns and describe all of them in description.

## How to run §§4–14
When looking up sources, proceed in the order set out in §§4–14 of the workflow.

Stop and ask the user whether to proceed to the next step when each of the steps below has been completed – unless explicit authorisation to continue without interruption has been given.

Use only the tools specified below, and only in the manner specified. If you do not have access to a specified tool, stop immediately and explain what you do not have access to – and why.

At each of the following steps, look only at references whose checked value is still "no" and which fall within the source category that step covers. Skip references that belong to a different category — they will be handled in the step appropriate to their type.

# 4) Check sources found in the Zotero library (with the zoteus MCP, the preferred tool)
The Zotero library (zoteus MCP) may contain all types of sources, such as judgments of domestic and international courts, treaties, statutes, preparatory works, legislation, and literature. Use the Zotero library for all sources you find there, except:
- Norwegian statutes and regulations
- EU legislation (regulations and directives)

All tools are called against the personal library; do not pass `library_type` or `library_id`.

## Finding the item
Search with `zotero_search_items`. Put the most distinctive part of the reference in `q` (author surname plus a title word, a case number, a citation number). Every space-separated word in `q` must match. The default `qmode` matches title, creators and year; when that finds nothing, Zoteus automatically retries in `everything` mode (all fields, notes and PDF text) and marks the response `broadened: true`. Narrow with `itemType` when the category is known (e.g. `case`, `book`, `journalArticle`, `bookSection`) and use `response_format: "detailed"` when you need to disambiguate between similar hits.

Two things to know about the `itemType` filter:
- Matches inside the PDF text are returned as the *attachment* item, not its parent. An `itemType` filter therefore hides them. When you need a hit from inside the text, search without `itemType`, then call `zotero_get_item` on the attachment key and follow its `parentItem` to the record.
- Matches in metadata fields (e.g. "Docket number", "History") are returned as the parent item and survive the filter.

Searching inside PDF text is reliable only for distinctive strings. Short tokens ("Rt.") and common words ("side") get lost, and hyphenated identifiers behave inconsistently: in testing "HR-2016-2554-P" missed the judgment while "HR 2016 2554 P" found it, whereas "LF-1998-997" worked as written. When a text search fails, retry with spaces in place of hyphens, then with a distinctive phrase of 5–8 consecutive words. Metadata searches on `caseName`, `docketNumber` and the like are not affected.

For case law, the default quick search matches the "Case name" field. The case number (e.g. C-123/17, HR-2026-123-A) is in "Docket number" and is reached by the broadened search.

Item types used in the library: judgments are `case`; Norwegian preparatory works are `bill` (preferred) or `report` depending on how they were entered (see §7); treaties are `statute` with "type: treaty" in the Extra field; literature is `book`, `bookSection`, `journalArticle` or `thesis`. `statute` items keep their name in `nameOfAct`, so search results list them as "(untitled)" — recognise them by `shortTitle` (e.g. "UNCLOS", "ECHR") and confirm with `zotero_get_item`. Treaty numbers sit in `publicLawNumber` ("ETS No. 5") or `code`/`codeNumber` ("UNTS" 1833) and are reached by the broadened search.

Confirm every hit with `zotero_get_item` (`item_key`, `include_children: true`). This returns the full record (all bibliographic fields) plus the child attachments and notes. Check author, title, year and edition against the reference before reading, and note the attachment keys.

## Reading the source
Read the text with `zotero_get_fulltext`. Passing the parent `item_key` resolves the item's best PDF (or EPUB) automatically. Useful parameters:
- `query` — returns the passages most relevant to a phrase, each with an approximate page. This is the fastest way to locate a quotation: pass a distinctive phrase of 5–8 consecutive words from it.
- `page_range` (e.g. `"41-43"`, 1-based PDF pages) — reads a span in full. Use it to verify a quotation verbatim in context and to read the running header.
- `max_chars` — the default cap is 12 000 characters (maximum 100 000). Raise it when you need to read a quotation in context.
- `outline: true` returns the PDF's table of contents only when Zoteus has its optional PDF parser installed. If it errors, skip it.

Page numbers: unless that optional parser is installed, every page number Zoteus reports is an estimate (`pageApprox`, `pageSource: "approximate"`) derived from character counts, and the estimate drifts through a document — in testing the gap between PDF page and printed page was 5 at PDF page 30 and 3 at page 60 of the same book. Therefore:
- Never convert an estimated page to a printed page with a fixed offset for the whole item.
- To reach a printed pinpoint, read a small `page_range` near the expected position, find the running header or printed page number in the text, and step forward or back until the header shows the cited page. Use the printed pagination in the worklist.
- To verify a quotation: `query` with a distinctive phrase, note `pageApprox`, read a `page_range` around it, confirm the text verbatim, and take the printed page number from the header.

PDFs larger than about 20 MB are served from Zotero's stored index rather than re-extracted; the response says so in `notice`. `page_range` and `query` still work.

Note that a single Zotero item may contain multiple attachments (e.g. PDFs). `zotero_get_fulltext` selects one attachment automatically; if it does not contain what you are looking for, take the other attachment keys from the `zotero_get_item` children list and call `zotero_get_fulltext` with that attachment key as `item_key`.

If you don't find any fulltext (e.g. only metadata and no attachments, or `zotero_get_fulltext` returns nothing even with `fallback: true`) when you look up an item in Zotero, leave the reference as "checked" = "no" (if the source can be found with other tools, it will then be picked up in a later step).

Certain Zotero items, notably some monographs, will only have a single PDF attachment with a Table of Contents or a short excerpt, and not the full text. These can be marked as "checked" = "no" (so that they may be picked up in a later step).

## Semantic search (secondary)
`zotero_semantic_search` searches by meaning and, if the user has built a full-text index, also inside PDF bodies. It always searches the personal library and cannot be pointed at a group library. Not every user has built this index, so:
- Always call it with `auto_build: false`. If it reports an empty or missing index, skip it — do not start an index build.
- Use it only after the metadata search in "Finding the item" has been tried: to find a quotation whose reference appears to be wrong (candidate for "Wrong source" or "Wrong page/section/paragraph"), or when a work you would expect to be in the library did not surface by title/creator.
- Hits are often listed as "(untitled)" with only a key, snippet and score. Identify each hit with `zotero_get_item` before doing anything else with it.
- A semantic hit is a lead, never a verification. Always open the record with `zotero_get_item` and read the passage with `zotero_get_fulltext` before filling in the worklist.

# 5) Check EU legal sources
Use the /eurlex skill for EU sources (case law, directives, regulations) that are not in Zotero — it is a guide to the eurlex MCP tools (case number/ECLI to CELEX, paging long judgments by paragraph offset, consolidated versions).

If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 6) Check Norwegian statutes and regulations
*Always* and *only* use the /lovdata-api skill to find Norwegian statutes and regulations. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 7) Check Norwegian preparatory works
Norwegian preparatory works (Ot.prp., Prop. L/S, St.prp., St.meld., NOU, Innst.) are stored in Zotero without the citation number in the title field — the title is the document's own title (e.g. "Om lov om styrking av menneskerettighetenes stilling i norsk rett (menneskerettsloven)"). Two storage models occur, and a library may contain both:
- **`bill` items** (the preferred model): series in `code` ("Ot.prp. nr.", "Prop.", "NOU", "Innst."; spelling varies), number in `billNumber` ("3", "71 L", "521 L"), session in `codeVolume` ("1998-99", "2024-2025"; empty for NOUs), the document date in `date`, and the ministry, committee or *utvalg* as sponsor.
- **`report` items** (older entries): series in `seriesTitle` ("Ot.prp.", "Norges Offentlige Utredninger"), document number in `reportNumber` ("3", "18"), kind in `reportType` ("Proposisjon", "NOU"), session in `date` ("1998-99"), and the ministry, committee or *utvalg* as creator.

Lookup recipe:
1. `zotero_search_items` with `itemType: "bill || report"` and `q` set to the session exactly as cited ("1998-99"). The default search finds nothing in the title, broadens automatically, and matches the session in `codeVolume` or `date`. If that returns nothing, search the year instead — for a session, one call per year — since `bill` items carry the document date rather than the session in `date`. Add a distinctive word from the document title to `q` when the reference gives one.
2. Call `zotero_get_item` on each candidate: the search result lists only key, type, title, creators and date, even with `response_format: "detailed"`, so the series, number and session fields are visible nowhere else. Confirm that they reproduce the cited number in whichever model applies. Match loosely: series spellings differ ("Ot.prp. nr." and "Ot.prop. nr." both occur), numbers may carry an "L"/"S" suffix, and sessions may be written "1998-99" or "1998-1999".
3. Verify by reading the first page (`zotero_get_fulltext` with `page_range: "1-1"`) that the document carries the cited number before treating the source as found in Zotero. The typeset cover often drops the punctuation ("Ot prp nr 3 (1998-99)"), so compare the numbers, not the exact string.

Worked examples for both models, covering Ot.prp./Prop./St.prp., NOU and Innst., plus the fallback when the year search returns too many hits, are in `references/zoteus-prepworks.md`. Read that file before searching.

**For Norwegian preparatory works *not* found in Zotero**, use the /lovdata-pro skill. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 8) Check Norwegian case law
Norwegian court judgments are stored in Zotero as item type `case` with this pattern:
- **`caseName`** (shown as the title) holds the identifier and, in parentheses, the popular name or the parties: "HR-2016-2554-P (Holship Norge mot Norges Transportarbeiderforbund)", "Rt. 2000 s. 1811 (Finanger I)", "RG 1966 s. 1", "LG-2008-135938 (Tomt i LNF-område)". Some items, especially unpublished lower-court decisions, carry only the party names.
- **`docketNumber`** holds the case number: modern cases as `HR-YYYY-NNNN-X` or `LG-YYYY-NNNNNN`; older Supreme Court cases as the court's own number ("Sak nr. 55/1999"). May be empty.
- **`reporter`**, **`reporterVolume`** and **`firstPage`** hold the print citation for Rt. and RG cases ("Rt.", "2000", "1811").
- **`court`** holds the court, **`dateDecided`** the date, **`shortTitle`** the popular name ("Finanger I", "Holship"), and **`history`** may hold the HR number of an Rt. case and the lower-court case numbers.

Search `caseName` first: `zotero_search_items` with `itemType: "case"` and `q` set to the identifier as written in the reference or to the popular name. If the title does not match, the search broadens automatically to `docketNumber`, `history` and the other fields. To search inside the judgment text (for a case cited only in the body, or for a quotation), repeat the search *without* `itemType` — text hits are returned as attachment items — and follow `parentItem` from `zotero_get_item`. Do not rely on the author/creator field: it is usually the court, but some items name the judges instead. Confirm with `zotero_get_item` that identifier, court and date match, and read the first page of the judgment to make sure it is the right case.

Example calls for modern HR cases, older Rt. cases and RG cases, plus the non-breaking-hyphen pitfall, are in `references/zoteus-caselaw.md`. Read that file before searching.

**For Norwegian case law *not* found in Zotero**, use the /lovdata-pro skill. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 9) Check treaties
For treaties, use the following tools *in the listed order*:
	- /untc for treaties in United Nations treaty database (UNTC/UNTS)
	- /ets for treaties in the CoE treaty office database (CETS/ETS)
	- /norges-traktater for treaties in the Norges Traktater database (should contain all treaties to which Norway is a party)

# 10) Check ICJ case law
For ICJ (International Court of Justice) or PCIJ (Permanent Court of International Justice) case law, use the /icj skill. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 11) Check decisions from the EFTA Court
For EFTA Court case law not found in Zotero, use the /efta-court skill. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 12) Check ECtHR case law
For ECtHR case law not found in Zotero, use the /hudoc skill. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 13) Check Norwegian books
For Norwegian books not found in Zotero, use the /nbno skill to look for them at Nasjonalbiblioteket. If there is something you cannot find, write "source unavailable" in the "checked" column. Do not search the web.

# 14) Sources not found with the tools
If you are unable to find a source after having gone through all the steps above (and used all the tools), enter "source unavailable" in the "checked" column. This applies in particular to non-Norwegian books, journal articles, working papers, and other literature where Zotero is the only available tool: if the item is not in Zotero, mark it "source unavailable". **Do not be afraid to do this – it is *very important* that you only check against *original sources* using *only* the tools defined above.**

# 15) Final verification
Verify that no row has checked = "no". For any that remain, attempt one final lookup using the appropriate tool from §§4–13. If the source still cannot be retrieved, set checked = "source unavailable" and explain in description which tools were tried.

At the very end, you must also check:
	- That all "discrepancy = yes" have a description filled in.
	- That every row with type of discrepancy = "Quotation not verbatim" has a non-blank quoted text column, and that every non-blank quoted text was compared verbatim against the source.
	- That row colours are consistent with row state: green for discrepancy = no; light yellow / orange / red for low / medium / high severity; grey for checked = source unavailable. Severity must match the colour, and grey rows must have blank discrepancy, type of discrepancy, and severity columns.
	- That the "checked" column contains only the three permitted values (yes/no/source unavailable).
	- That the number of rows in the main worksheet matches the value of `Total references identified` in the Metadata sheet. If the numbers diverge, identify the missing or extra rows, correct the discrepancy, and report what was changed in the chat.

Correct any errors and shortcomings found by the checks above. Report in the chat what was corrected, and provide the following statistics both in the chat and as new rows in the Metadata sheet:
	- total references
	- number of checked = yes and number of checked = source unavailable (the no count must be 0)
	- total discrepancies, broken down by severity (high / medium / low)
	- total discrepancies, broken down by type (using the labels in §2)
