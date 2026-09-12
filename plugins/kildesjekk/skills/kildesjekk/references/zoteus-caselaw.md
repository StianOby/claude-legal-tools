# Zoteus lookups — Norwegian case law

Norwegian judgments are `case` items. How the identifiers are stored (Zotero field → example values):

| Field | Modern HR case | Older Rt. case | RG case | Lower court |
|---|---|---|---|---|
| `caseName` (title) | HR-2016-2554-P (Holship Norge mot Norges Transportarbeiderforbund) | Rt. 2000 s. 1811 (Finanger I) | RG 1966 s. 1 | LG-2008-135938 (Tomt i LNF-område) |
| `docketNumber` | HR-2016-2554-P | Sak nr. 55/1999 | *(empty)* | LG-2008-135938 |
| `reporter` / `reporterVolume` / `firstPage` | *(empty)* | Rt. / 2000 / 1811 | RG / 1966 / 1 | *(empty)* |
| `court` | Norges Høyesterett | Norges Høyesterett | Mandal byrett | Gulating lagmannsrett |
| `shortTitle` | Holship | Finanger I | *(empty)* | Tomt i LNF-område |
| `history` | *(empty)* | … Høyesterett HR-2000-49-B, nr. 55/1999. | *(empty)* | Bergen tingrett TBERG-2007-170926 - … |

Some items, typically unpublished lower-court decisions, have only party names in `caseName` (e.g. "Dennis mot Stiftelsen Flyktningehjelpen") and an empty `docketNumber`. Search those by party name. Lower-court items may carry an HTML snapshot rather than a PDF; `zotero_get_fulltext` reads those too.

## How the search behaves

- Every space-separated word in `q` must match, in any one field. "Holship Transportarbeiderforbund" finds Holship; "Holship Finanger" finds nothing.
- The default search covers `caseName`, creators and year. When it finds nothing, Zoteus retries automatically across all fields (`docketNumber`, `history`, …) and the PDF text, and marks the response `broadened: true`.
- With `itemType: "case"` only parent items come back. Hits from inside a PDF are returned as the *attachment* item, so the filter hides them. To search inside judgment texts, drop `itemType`, then call `zotero_get_item` on the attachment key and follow `parentItem`.

## Recipe

1. **Search `caseName`** with `itemType: "case"` and the identifier as written in the reference. The automatic broadening also covers `docketNumber` and `history`.
2. **No hit?** Try the popular name. Then, if the case may be filed under another identifier, search without `itemType` so PDF text counts, and resolve attachments to their parent — see the pitfalls below.
3. **Confirm** the candidate with `zotero_get_item` (`include_children: true`): identifier, `court` and `dateDecided` must match the reference.
4. **Read the first page** with `zotero_get_fulltext` and `page_range: "1-1"` to rule out a false positive before filling in the worklist. The header of a Supreme Court PDF carries the HR number and, for older cases, the Rt. citation as well ("HR-2000-49-B - Rt-2000-1811").

### Modern HR case (e.g. HR-2016-2554-P Holship)

```json
{"tool": "zotero_search_items", "q": "HR-2016-2554", "itemType": "case", "limit": 10}
```

Fallback by popular name:

```json
{"tool": "zotero_search_items", "q": "Holship", "itemType": "case", "limit": 10}
```

### Older Rt. case in Lovdata print format (e.g. Rt. 2000 s. 1811 Finanger I)

```json
{"tool": "zotero_search_items", "q": "Rt. 2000 s. 1811", "itemType": "case", "limit": 10}
```

Fallbacks: the popular name (`"q": "Finanger"`), or the HR number if the reference gives one — `history` often holds it, and the broadened search reaches it:

```json
{"tool": "zotero_search_items", "q": "HR-2000-49-B", "itemType": "case", "limit": 10}
```

When confirming with `zotero_get_item`, check `reporter` = "Rt.", `reporterVolume` = "2000" and `firstPage` = "1811".

### RG case (e.g. RG 1966 s. 1)

```json
{"tool": "zotero_search_items", "q": "RG 1966 s. 1", "itemType": "case", "limit": 10}
```

Confirm `reporter` = "RG", `reporterVolume` = "1966", `firstPage` = "1". Because `q` matches on substrings, "RG 1966 s. 1" also hits "RG 1966 s. 12"; the `firstPage` check is what settles it.

### Lower-court case (e.g. LG-2008-135938)

```json
{"tool": "zotero_search_items", "q": "LG-2008-135938", "itemType": "case", "limit": 10}
```

### Case cited only inside another judgment's text

```json
{"tool": "zotero_search_items", "q": "HR 2016 2554 P", "qmode": "everything", "limit": 25}
```

No `itemType`: hits are attachment items. Resolve each with `zotero_get_item` and read `parentItem`. Note the spaces instead of hyphens — see below.

## Pitfalls when searching inside PDF text

Tested against a personal library with indexed PDFs:

| Query | Result |
|---|---|
| `HR-2016-2554-P` (as written) | 42 attachments, the Holship judgment **not** among them |
| `HR 2016 2554 P` (spaces) | 12 hits, Holship included |
| `LF-1998-997` (as written) | 2 hits, the right one |
| `LF 1998 997` (spaces) | 21 hits, the right one plus noise |
| `Rt. 1997 side 337` | the judgment that contains it verbatim was **not** returned — "Rt" is too short, "side" too common |
| `å tvinge Holship til å inngå tariffavtale` | the right attachment returned |

So, when you must search inside texts: try the identifier as written, then with spaces in place of hyphens, then a popular name or a distinctive phrase of 5–8 consecutive words. Rt. citations are effectively unsearchable in text; use the case name. Whether U+2011 non-breaking hyphens in court PDFs add to the problem has not been isolated. Metadata searches with `itemType: "case"` on `caseName` and `docketNumber` are not affected and work reliably with the identifier as written.
