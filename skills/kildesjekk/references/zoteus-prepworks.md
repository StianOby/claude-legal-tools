# Zoteus lookups — Norwegian preparatory works

Preparatory works are `bill` items. The citation number is spread over several fields; the title holds the document's own title only. Examples from the library (Zotero field → value):

| Cited as | `code` | `billNumber` | `codeVolume` | `date` | sponsor (creator) | `legislativeBody` |
|---|---|---|---|---|---|---|
| Ot.prp. nr. 3 (1998-99) | Ot.prop. nr. *(sic)* | 3 | 1998-99 | 1998-10-09 | Justis- og politidepartementet | *(empty)* |
| Ot.prp. nr. 23 (1961-62) | Ot.prp. nr. | 23 | 1961-62 | 1962-01-05 | Justis- og politidepartementet | *(empty)* |
| Prop. 71 L (2024-2025) | Prop. | 71 L | 2024-2025 | 2025-03-28 | Nærings- og fiskeridepartementet | Stortinget |
| Innst. 521 L (2024-2025) | Innst. | 521 L | 2024-2025 | 2025-06-03 | Næringskomiteen | Stortinget |
| NOU 2022: 8 | NOU | 8 | *(empty)* | 2022-07-01 | Minerallovutvalget | *(empty)* |

Note the variation: `code` spelling differs between items, `billNumber` may carry the "L"/"S" suffix, and `codeVolume` may be written "1998-99" or "2024-2025". Match these fields loosely and let the combination decide.

## Recipe

1. **Search by year** with `itemType: "bill"` and the default `qmode` (title, creators, year). Run one call per year of the session — a document from session 1998-99 may be dated in either year. If the reference gives the title, add one distinctive word from it to `q` to narrow the list.
2. **Confirm** each candidate with `zotero_get_item`: `code`, `billNumber` and `codeVolume` together must reproduce the cited number. For NOUs, `codeVolume` is empty — use `code` = "NOU", `billNumber` and the year of `date`.
3. **Read the first page** with `zotero_get_fulltext` and `page_range: "1-1"`: the citation number is printed there. Do not treat the source as found in Zotero until it matches.

### Ot.prp. / Prop. / St.prp. (ministry-authored), e.g. Ot.prp. nr. 3 (1998-99)

```json
{"tool": "zotero_search_items", "q": "1998", "itemType": "bill", "limit": 100, "response_format": "detailed"}
{"tool": "zotero_search_items", "q": "1999", "itemType": "bill", "limit": 100, "response_format": "detailed"}
```

Then `zotero_get_item` on the candidates whose sponsor is a ministry (*…departementet*); confirm `code` starts with "Ot.prp"/"Ot.prop", `billNumber` = "3", `codeVolume` = "1998-99".

With a title word (the menneskerettsloven bill):

```json
{"tool": "zotero_search_items", "q": "1998 menneskerettsloven", "itemType": "bill", "limit": 25}
```

### NOU (committee-authored), e.g. NOU 2022: 8

```json
{"tool": "zotero_search_items", "q": "2022", "itemType": "bill", "limit": 100, "response_format": "detailed"}
```

Confirm `code` = "NOU" and `billNumber` = "8". The sponsor is the *utvalg*, never a ministry, so do not filter on "departement".

### Innst. (committee recommendation), e.g. Innst. 521 L (2024-2025)

```json
{"tool": "zotero_search_items", "q": "2025", "itemType": "bill", "limit": 100, "response_format": "detailed"}
```

Confirm `code` = "Innst.", `billNumber` = "521 L", `codeVolume` = "2024-2025". The sponsor is a Storting committee (*…komiteen*).

## Fallback when the year search is too broad

Use `qmode: "everything"` with the citation string as printed on the document's first page. This searches all fields (including `code`, `billNumber` and `codeVolume`) and the PDF text, so it is noisier — any bill whose text merely cites the document will also match. Step 3 (first-page check) is mandatory after this route.

```json
{"tool": "zotero_search_items", "q": "Ot.prp. nr. 3 (1998-99)", "qmode": "everything", "itemType": "bill", "limit": 25}
{"tool": "zotero_search_items", "q": "NOU 2022: 8", "qmode": "everything", "itemType": "bill", "limit": 25}
```
