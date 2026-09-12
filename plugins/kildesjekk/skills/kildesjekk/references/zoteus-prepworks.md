# Zoteus lookups — Norwegian preparatory works

Preparatory works are stored without the citation number in the title; the title holds the document's own title only. Two storage models occur, and a library may contain both. Always search both item types and let the field check decide.

## Model A — `bill` items (preferred)

| Cited as | `code` | `billNumber` | `codeVolume` | `date` | sponsor (creator) | `legislativeBody` |
|---|---|---|---|---|---|---|
| Ot.prp. nr. 3 (1998-99) | Ot.prop. nr. *(sic)* | 3 | 1998-99 | 1998-10-09 | Justis- og politidepartementet | *(empty)* |
| Ot.prp. nr. 23 (1961-62) | Ot.prp. nr. | 23 | 1961-62 | 1962-01-05 | Justis- og politidepartementet | *(empty)* |
| Prop. 71 L (2024-2025) | Prop. | 71 L | 2024-2025 | 2025-03-28 | Nærings- og fiskeridepartementet | Stortinget |
| Innst. 521 L (2024-2025) | Innst. | 521 L | 2024-2025 | 2025-06-03 | Næringskomiteen | Stortinget |
| NOU 2022: 8 | NOU | 8 | *(empty)* | 2022-07-01 | Minerallovutvalget | *(empty)* |

The session sits in `codeVolume`; `date` is the document date, so a year search for the second year of a session ("1999" for 1998-99) finds nothing.

## Model B — `report` items (older entries)

| Cited as | `seriesTitle` | `reportNumber` | `reportType` | `date` | creator |
|---|---|---|---|---|---|
| Ot.prp. nr. 3 (1998-99) | Ot.prp. | 3 | Proposisjon | 1998-99 | Justis- og politidepartementet |
| NOU 1993: 18 | Norges Offentlige Utredninger | 18 | NOU | 1993 | *(utvalg)* |

The session or year sits in `date`.

Note the variation in both models: series spelling differs between items, the number may carry the "L"/"S" suffix, and the session may be written "1998-99" or "2024-2025". Match these fields loosely and let the combination decide.

## How the search behaves

- Every space-separated word in `q` must match, in any one field.
- The default search covers title, creators and year. When it finds nothing, Zoteus retries automatically across all fields and marks the response `broadened: true`. That retry is what reaches `codeVolume` and `date`.
- Search results list only key, item type, title, creators and date — even with `response_format: "detailed"`. The series, number and session fields are visible only through `zotero_get_item`.

## Recipe

1. **Search the session** as cited, with `itemType: "bill || report"`. The broadened search matches it in `codeVolume` (model A) or `date` (model B). If the reference gives the title, add one distinctive word from it to `q`.
2. **No hit?** Search the year(s) instead — one call per year of the session. NOUs are cited by year, so start here for them.
3. **Confirm** each candidate with `zotero_get_item`. Model A: `code`, `billNumber`, `codeVolume`; for NOUs `codeVolume` is empty, so use `code` = "NOU", `billNumber` and the year of `date`. Model B: `seriesTitle` or `reportType` gives the series, `reportNumber` the number, `date` the session.
4. **Read the first page** with `zotero_get_fulltext` and `page_range: "1-1"`: the citation number is printed there, often without punctuation ("Ot prp nr 3 (1998-99)"), so compare the numbers rather than the exact string. Do not treat the source as found in Zotero until it matches. If the item has no attachment, leave the reference as checked = no. Very large PDFs (over about 20 MB) are served from Zotero's stored index; the first page still comes back.

### Ot.prp. / Prop. / St.prp. (ministry-authored), e.g. Ot.prp. nr. 3 (1998-99)

```json
{"tool": "zotero_search_items", "q": "1998-99", "itemType": "bill || report", "limit": 100}
```

Fallback by year, and with a title word (the menneskerettsloven bill):

```json
{"tool": "zotero_search_items", "q": "1998", "itemType": "bill || report", "limit": 100}
{"tool": "zotero_search_items", "q": "1998 menneskerettsloven", "itemType": "bill || report", "limit": 25}
```

Then `zotero_get_item` on the candidates whose creator is a ministry (*…departementet*). Model A: `code` starts with "Ot.prp"/"Ot.prop", `billNumber` = "3", `codeVolume` = "1998-99". Model B: `seriesTitle` starts with "Ot.prp", `reportNumber` = "3", `date` = "1998-99".

### NOU (committee-authored), e.g. NOU 2022: 8

```json
{"tool": "zotero_search_items", "q": "2022", "itemType": "bill || report", "limit": 100}
```

Model A: `code` = "NOU", `billNumber` = "8". Model B: `reportType` = "NOU" (or `seriesTitle` = "Norges Offentlige Utredninger"), `reportNumber` = "8". The creator is the *utvalg*, never a ministry, so do not filter on "departement".

### Prop. and Innst. of the same session, e.g. Prop. 71 L (2024-2025) and Innst. 521 L (2024-2025)

```json
{"tool": "zotero_search_items", "q": "2024-2025", "itemType": "bill || report", "limit": 100}
{"tool": "zotero_search_items", "q": "2025 mineralloven", "itemType": "bill || report", "limit": 25}
```

Both documents come back together; `zotero_get_item` separates them. Model A: `code` = "Prop." with `billNumber` = "71 L", and `code` = "Innst." with `billNumber` = "521 L", both `codeVolume` = "2024-2025". The Innst. creator is a Storting committee (*…komiteen*).

## Fallback when the session search is too broad

Search for the citation string as printed on the document's first page, **without** an `itemType` filter. The search covers all fields and the PDF text; hits from inside a PDF are returned as the attachment item, so call `zotero_get_item` on each hit and follow `parentItem` to the record. This route is noisy — any document whose text merely cites the one you want will also match — so step 4 (first-page check) is mandatory after it.

```json
{"tool": "zotero_search_items", "q": "Ot.prp. nr. 3 (1998-99)", "qmode": "everything", "limit": 25}
{"tool": "zotero_search_items", "q": "NOU 2022: 8", "qmode": "everything", "limit": 25}
```
