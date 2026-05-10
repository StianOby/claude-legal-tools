# Document-type and language codes used in PDF filenames

ICJ PDF URLs encode the document type and language as short tags:

```
/sites/default/files/case-related/<id>/<id>-YYYYMMDD-<type>-NN-NN-<lang>.pdf
```

This file documents the tags. The mapping is also encoded in
`scripts/cases.py` and used to filter pleadings out of `cases show`.

## Document-type tags

| Tag | Meaning | Surfaced by `cases show`? |
|------|---------|---------------------------|
| `jud` | Judgment | yes |
| `adv` | Advisory opinion | yes |
| `ord` | Order | yes |
| `app` | Application instituting proceedings | yes |
| `req` | Request for advisory opinion | yes |
| `sum` | Summary of judgment / order | yes |
| `pre` | Press release | yes |
| `mem` | Memorial | no — pleading |
| `cmem` | Counter-Memorial | no — pleading |
| `rep` | Reply | no — pleading |
| `rej` | Rejoinder | no — pleading |
| `obs` | Written observations | no — pleading |
| `wri`, `wso` | Written statement / observations | no — pleading |
| `cr` | Verbatim record (compte rendu) | no — verbatim record |

When a tag is unrecognised the document is placed in `other_pdfs` so
nothing is silently lost — surface it to the user when relevant.

## Language tags

| Tag | Language |
|------|----------|
| `en` | English |
| `fr` | French |
| `frc` | French consolidated (e.g., consolidated annexes) |
| `bil` | Bilingual EN/FR |
| `ar` | Arabic (translations of landmark opinions) |
| `es` | Spanish (idem) |
| `ru` | Russian |
| `zh` | Chinese |

The Court's two official languages are English and French. Other
languages appear only for select landmark opinions (e.g., the *Israeli
Wall* advisory opinion has translations into all six UN languages).

## ISO-2 country codes used in `/declarations/<cc>`

The skill includes an explicit name → code mapping in
`scripts/_common.py`. A handful of codes deviate from ISO 3166-1
alpha-2:

- `cg` is the URL slug used by the Court for the **Democratic Republic of
  the Congo** (ISO would assign `cd`).
- `gb` for the United Kingdom (matches ISO).
- `is` for Iceland — note this is a Python keyword in some contexts; the
  CLI handles it without quoting.

When in doubt, run `declarations list` and read the slug off the URL of
the entry you care about.
