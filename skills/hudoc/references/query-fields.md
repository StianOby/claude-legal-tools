# HUDOC query field reference

The `/app/query/results` endpoint speaks a Lucene-flavoured query language.
This file documents every field worth indexing on, plus the document type
codes you'll see in results.

## Query syntax cheatsheet

```
field:value                    fielded match (case-insensitive)
field:"phrase match"           exact phrase, single-token boundary
field:(tokA tokB)              AND-of-tokens within field
NOT field:value                exclusion
clause1 AND clause2            boolean AND
clause1 OR clause2             boolean OR
field:[A TO B]                 range (dates, numeric)
field:*                        any value present
```

The script always wraps your clause in `(contentsitename=ECHR) AND (...)`
to limit results to the public Court collection. Pass a raw clause to
`search`, `resolve`, `fetch`, or `metadata`.

## Identification fields

| Field | Description | Example |
|---|---|---|
| `itemid` | HUDOC's stable internal id. NNN-NNNNNN(-NNNNNN). | `001-57619` (Soering) |
| `appno` | Application number (one or several). | `14038/88`, `58170/13;62322/14;24960/15` |
| `extractedappno` | All appnos referenced anywhere in the document, including in citations. | (used to find "cited by") |
| `docname` | Indexed case title. The full form is "CASE OF X v. Y" / "AFFAIRE X c. Y". | |
| `ecli` | European Case Law Identifier. | `ECLI:CE:ECHR:2018:0904JUD000622114` |

## Filter fields

| Field | Description | Common values |
|---|---|---|
| `respondent` | ISO-3 country code of the respondent state. | `NOR`, `GBR`, `FRA`, `RUS`, `TUR`, `POL`, `DEU`, `ITA`, `ESP` … |
| `article` | Convention article(s) invoked. Includes sub-paragraphs. | `8`, `8-1`, `8-2`, `P1-1` (Protocol 1, art 1) |
| `conclusion` | Free-text conclusion. Useful for filtering on outcome. | `"Violation of Article 8"`, `"No violation"`, `"Inadmissible"`, `"Strike out"`. |
| `kpdate` | Decision/publication date in ISO. | `[2020-01-01T00:00:00Z TO 2024-12-31T00:00:00Z]` |
| `judgementdate` | Same as kpdate for judgments. | `04/09/2018 00:00:00` form on output |
| `importance` | 1 (key cases, mandatory reading), 2, 3, 4 (least cited). | `1`, `2`, `3`, `4` |
| `languageisocode` | Language version. | `ENG`, `FRE` (and a few translations: `BUL`, `RUS`, `TUR`, `UKR` …) |
| `originatingbody` | Internal id of the chamber/court. Number, not name — see HUDOC user manual. | `7` (4th Section), `8` (Grand Chamber), … |
| `kpthesaurus` | Indexed thesaurus tags (numeric). | Filter is rarely useful; results show what tags apply. |

## Document type fields

`doctypebranch` is the most useful filter. Combined values give you the
"is this a judgment?" question in one filter.

| `doctypebranch` | Meaning |
|---|---|
| `GRANDCHAMBER` | Grand Chamber judgment (17 judges) |
| `CHAMBER` | Chamber judgment (7 judges) |
| `COMMITTEE` | Committee judgment / decision (3 judges) |
| `ADMISSIBILITY` | Court admissibility decision |
| `ADMISSIBILITYCOM` | Old Commission admissibility decision (pre-1998) |
| `MERITS` | Old Commission merits report (pre-1998) |
| `COMMUNICATEDCASES` | Case communicated to the respondent state |
| `ADVISORYOPINIONS` | Article 47 / Protocol No. 16 advisory opinion |
| `CLIN` | Case-Law Information Note legal summary |
| `EXECUTION` | Committee of Ministers EXECUTION resolution |
| `RESOLUTIONS` | Committee of Ministers final resolution |

`doctype` is the underlying file kind. Useful when you need to *exclude*
press releases or news.

| `doctype` | Meaning |
|---|---|
| `HEJUD` | English-language judgment |
| `HFJUD` | French-language judgment |
| `HEDEC` | English decision |
| `HFDEC` | French decision |
| `HEADV` / `HFADV` | Advisory opinion (EN / FR) |
| `CLIN` | Case-Law Information Note |
| `INFONOTE` | Information Note (older format) |
| `HERES54` / `HFRES54` | EXECUTION resolutions |
| `PR` | Press release |

## Citation field

| Field | Description |
|---|---|
| `scl` | "Strasbourg case-law" — semicolon-separated list of cited ECtHR cases, with paragraph numbers and dates. **The most useful single field for citation analysis.** |
| `extractedappno` | Every application number that appears in the document (the case's own appno first, then the appnos of every cited Strasbourg case). |
| `kpresources` | Cited international and domestic instruments — UN treaties, EU law, domestic statutes. Sparse but rich when populated. |

## Other useful fields

| Field | Description |
|---|---|
| `separateopinion` | `TRUE` if there are concurring or dissenting opinions. |
| `representedby` | Counsel / agent who represented the applicant. |
| `issue` | Domestic legal instrument the case turns on, when noted. |
| `documentcollectionid2` | Hierarchy tag, e.g. `CASELAW;JUDGMENTS;GRANDCHAMBER;ENG`. |

## Recipes

### "Latest 10 GC judgments finding a violation of Article 10"

```
(article:"10") AND (conclusion:"Violation of Article 10") AND
(doctypebranch:GRANDCHAMBER) AND (languageisocode:"ENG")
```
Sort: `kpdate Descending`.

### "Strand Lobben line of cases against Norway, child welfare"

```
(respondent:"NOR") AND (article:"8") AND (importance:"1" OR importance:"2")
```

### "All Article 6 admissibility decisions from 2023"

```
(article:"6") AND (doctypebranch:ADMISSIBILITY) AND
(kpdate:[2023-01-01T00:00:00Z TO 2023-12-31T00:00:00Z])
```

### "Every case that cites Soering"

```
(extractedappno:"14038/88") AND NOT (itemid:"001-57619")
```

### "French-language version of a known case"

```
(appno:"15379/16") AND (languageisocode:"FRE")
```

## What's *not* available via the public API

- The "Cited by" reverse-citation graph rendered in the HUDOC web UI is
  not a single API call. Approximate it by searching `extractedappno`.
- Translations into Russian, Turkish, Ukrainian etc. exist on HUDOC but
  the metadata is sparse; use `languageisocode` to filter and accept
  that some fields will be empty.
- Pinpoint paragraph anchors inside the rendered HTML view are not in
  the JSON API. Use the extracted DOCX text and grep for `^N\.` to find
  paragraph N.
