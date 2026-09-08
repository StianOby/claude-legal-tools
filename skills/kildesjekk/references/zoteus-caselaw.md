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

Some items, typically unpublished lower-court decisions, have only party names in `caseName` (e.g. "Dennis mot Stiftelsen Flyktningehjelpen") and an empty `docketNumber`. Search those by party name.

## Recipe

1. **Search `caseName`** with the identifier as written in the reference. The default `qmode` matches title (= `caseName`), creators and year, and each space-separated word in `q` must match somewhere.
2. **No hit?** Retry with `qmode: "everything"`, which adds `docketNumber`, `history`, notes and the PDF text. Then try the popular name.
3. **Confirm** the candidate with `zotero_get_item` (`include_children: true`): identifier, `court` and `dateDecided` must match the reference.
4. **Read the first page** with `zotero_get_fulltext` and `page_range: "1-1"` to rule out a false positive before filling in the worklist.

### Modern HR case (e.g. HR-2016-2554-P Holship)

```json
{"tool": "zotero_search_items", "q": "HR-2016-2554", "itemType": "case", "limit": 10}
```

Fallback if nothing is found — covers `docketNumber` and the judgment text:

```json
{"tool": "zotero_search_items", "q": "HR-2016-2554", "qmode": "everything", "itemType": "case", "limit": 10}
{"tool": "zotero_search_items", "q": "Holship", "itemType": "case", "limit": 10}
```

### Older Rt. case in Lovdata print format (e.g. Rt. 2000 s. 1811 Finanger I)

```json
{"tool": "zotero_search_items", "q": "Rt. 2000 s. 1811", "itemType": "case", "limit": 10}
```

Fallbacks: the popular name (`"q": "Finanger"`), or the HR number if the reference gives one — `history` often holds it, so use `qmode: "everything"`:

```json
{"tool": "zotero_search_items", "q": "HR-2000-49-B", "qmode": "everything", "itemType": "case", "limit": 10}
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

## Pitfall: non-breaking hyphens

Court PDFs and Lovdata print format often render the hyphens in case numbers as U+2011 NON-BREAKING HYPHEN rather than ASCII U+002D, to keep the number from breaking across lines. `caseName` and `docketNumber` are typed by the user and normally use ASCII hyphens, so the default search is unaffected. In `qmode: "everything"` the PDF text is searched too, and a search on the full identifier can silently miss such files. If that happens, retry with the parts separated by spaces (`"q": "HR 2018 456"`) — every word must match, in any field or in the text — or with the popular name. Always read the first page of the hit to rule out false positives.
