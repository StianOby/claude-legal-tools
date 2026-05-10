# URL patterns on icj-cij.org

The skill targets stable, documented URL shapes. This file is the cheat
sheet — read it when you need to construct or recognise an ICJ URL by hand.

## Top-level pages

```
https://www.icj-cij.org/index.php/<slug>
```

The `index.php/` prefix is optional but the canonical form on most pages.
Both work; the cache stores whichever was actually fetched.

| Slug | What it lists |
|------|---------------|
| `home` | Landing page |
| `decisions` | Most recent ~80 decisions across all cases |
| `pending-cases` | Pending cases |
| `list-of-all-cases` | All cases (170+), grouped by year |
| `cases-by-country` | Cases organised by State |
| `contentious-cases` | Contentious cases only |
| `advisory-proceedings` | Advisory proceedings only |
| `states-entitled-to-appear` | All UN-member parties to the Statute |
| `states-not-members` | Non-UN states that have been parties to the Statute |
| `states-not-parties` | States not party to the Statute that may access the Court |
| `basis-of-jurisdiction` | The Court's own description of jurisdiction (Art. 36 etc.) |
| `declarations` | Index of Article 36(2) declarations |
| `treaties` | Treaties conferring jurisdiction |
| `organs-agencies-authorized` | UN organs and specialized agencies authorised to request advisory opinions |

## Per-case pages

```
https://www.icj-cij.org/case/<N>
```

`<N>` is the case ID (1..199 as of 2026). The page lists every document
in the case grouped under H4 headings: *Institution of proceedings,
Written proceedings, Oral proceedings, Other documents, Orders,
Judgments, Summaries of Judgments and Orders, Press releases*.

The skill exposes only the decision-adjacent buckets. Pleadings (Written
proceedings) and verbatim records (Oral proceedings) are filtered out.

## Per-state declarations

```
https://www.icj-cij.org/declarations/<cc>
```

`<cc>` is a lowercase ISO 3166-1 alpha-2 country code, except a handful
of historical exceptions:

- `cg` is used for the Democratic Republic of the Congo (despite ISO using `cg` for Republic of the Congo and `cd` for DRC).
- `gb` for United Kingdom (UK).
- The site uses the lowercase code; passing uppercase still resolves due to URL canonicalisation.

## PCIJ pages

```
https://www.icj-cij.org/pcij                # landing
https://www.icj-cij.org/pcij-series-a       # Judgments 1923-1930
https://www.icj-cij.org/pcij-series-b       # Advisory opinions 1923-1930
https://www.icj-cij.org/pcij-series-ab      # Judgments, Orders, Advisory opinions 1931-1940
https://www.icj-cij.org/pcij-series-c       # Pleadings, Oral arguments, Documents (out of scope)
https://www.icj-cij.org/pcij-series-d       # Acts and documents on the organization (out of scope)
https://www.icj-cij.org/pcij-series-e       # Annual reports (out of scope)
https://www.icj-cij.org/pcij-series-f       # General indexes (out of scope)
```

## PDF naming

Modern ICJ documents:

```
/sites/default/files/case-related/<case_id>/<case_id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf
```

Field meanings:

- `<case_id>` echoed twice for path uniqueness.
- `YYYYMMDD` document date.
- `<type>` short tag for document type (see `data-codes.md`).
- `NN-NN` two two-digit serials. The first usually distinguishes a series of
  same-type documents on the same date (e.g., judgment + dissenting opinions);
  the second is sometimes a sub-document.
- `<lang>` language code: `en` (English), `fr` (French), `frc` (French
  consolidated), `bil` (bilingual), `ar`, `es`, `ru`, `zh` for translations
  in landmark cases.

PCIJ documents have a different scheme (per series and per case):

```
/sites/default/files/permanent-court-of-international-justice/serie_<X>/<X>_<NN>/<file>.pdf
```

where `<X>` is `A`, `B`, or `AB`, `<NN>` is the two-digit case number, and
`<file>` is a French-language descriptor — e.g.
`30_Lotus_Arret.pdf` (Judgment in the Lotus case).

## Notes on the site itself

- Drupal 10. URLs are case-sensitive on the path component.
- The same content is reachable with or without `/index.php/`. Pick one and
  stick with it; the cache is keyed by the exact URL fetched.
- The site does NOT consistently send `Last-Modified` or `ETag` headers, so
  freshness checks fall back to a TTL when those headers are absent.
- A `?page=N` query string is accepted on listing pages, but the listings
  used by this skill (`/decisions`, `/list-of-all-cases`) currently render
  all entries on one page.
