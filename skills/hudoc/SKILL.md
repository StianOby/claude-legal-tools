---
name: hudoc
description: |
  Use whenever the user wants the text, metadata, or citations of a European
  Court of Human Rights judgment, decision, advisory opinion, legal summary, or
  CM resolution from HUDOC. Trigger on: an ECtHR case named X v. Y / X c. Y
  (Soering v. UK, Big Brother Watch v. UK, Strand Lobben v. Norway); a HUDOC
  itemid (001-57619); an application number (14038/88); ECLI:CE:ECHR:…; asks
  like "what did the Grand Chamber say in …", "ECtHR case on bulk surveillance
  and Article 8", "cases cited by …", "official PDF of …", "search HUDOC for
  …", "hva sa Strasbourg-domstolen i …". Use even if HUDOC isn't named: if
  answering needs the text or metadata of an ECtHR document, this is the
  tool. Do NOT use for: Norwegian law or case law (lovdata, lovdata-pro); EU
  law / GDPR / CJEU (eurlex); UN treaties (untc); WTO/WIPO; news about
  Strasbourg; Rule-39 / how-to-apply procedural questions; the bare Convention
  text with no case lookup; or essays needing no specific judgment.
---

# HUDOC — European Court of Human Rights case law

This skill talks to `hudoc.echr.coe.int` to retrieve four things:

1. **Search results** — filtered by case name, application number, article,
   respondent state, conclusion, court instance, importance, date.
2. **Structured metadata** — itemid, ECLI, doctypebranch, conclusion,
   articles invoked, importance level, language, date, separate opinions.
3. **The full text of a judgment** — extracted from the official DOCX (or PDF
   as fallback), with paragraph breaks preserved so paragraph numbering
   ("§ 47", "paragraph 88") is searchable. Automatically retries on server
   errors (HTTP 500+).
4. **The official PDF** — for citing and archiving.
5. **Citations** — every ECtHR case the judgment relies on, parsed from the
   `scl` (Strasbourg case-law cited) metadata field.

The skill works on any HUDOC content type: Grand Chamber and Chamber
judgments (`HEJUD`/`HFJUD`), Committee judgments, admissibility decisions
(`HEDEC`/`HFDEC`), advisory opinions, communicated cases, Case-Law
Information Note legal summaries (`CLIN`), and Committee of Ministers
EXECUTION resolutions. Both English and French (the Court's two official
languages) are supported.

## How to use

The whole skill is one self-contained Python CLI: `scripts/hudoc.py`. No
third-party packages — only the standard library (`urllib`, `zipfile`,
`xml.etree`). Run it from this skill's directory; the cache lives in
`./cache/items/<itemid>/` relative to the script.

| The user wants… | Run |
|---|---|
| The text of a known case | `python3 scripts/hudoc.py fetch "Soering v. UK" --format text` |
| The text by itemid | `python3 scripts/hudoc.py fetch 001-57619 --format text` |
| The text by appno | `python3 scripts/hudoc.py fetch 14038/88 --format text` |
| The official PDF | `python3 scripts/hudoc.py fetch <ref> --format pdf -o /tmp/case.pdf` |
| Just the metadata (no full text) | `python3 scripts/hudoc.py metadata <ref>` |
| Cases cited by this judgment | `python3 scripts/hudoc.py citations <ref>` |
| Filtered search | `python3 scripts/hudoc.py search '(article:"8") AND (respondent:"NOR") AND (doctypebranch:GRANDCHAMBER)' -n 20` |
| Search by free-text case name | `python3 scripts/hudoc.py search 'docname:(big brother watch)' -n 5` |
| Resolve a name to itemid only | `python3 scripts/hudoc.py resolve "Big Brother Watch v. UK"` |
| Re-print already-fetched text | `python3 scripts/hudoc.py show 001-57619` |

`<ref>` is whatever the user gave you: a case name, an application number,
an itemid, an ECLI, or a Lucene clause. `resolve`/`metadata`/`fetch`/
`citations` all accept the same reference forms — you don't need to disambiguate
yourself; the script picks the best matching row (judgment over press release,
GC over Chamber over Committee, English over French, most recent rehearing).

## Mental model

HUDOC has no official API documentation, but two stable endpoints exist:

```
GET /app/query/results          JSON metadata + Lucene-style search.
                                Requires X-Requested-With: XMLHttpRequest
                                — the script handles this automatically.
GET /app/conversion/{docx,pdf}/?library=ECHR&id=<itemid>
                                Document download. No auth.
```

**Text extraction strategy:** When you request text, the script tries DOCX
first (better paragraph structure for legal paragraph numbering), then falls
back to PDF if DOCX fails. On HTTP 5xx errors, it retries up to 3 times with
exponential backoff (1s, 2s, 4s).

## Workflow guidance

### The user names a specific case

1. `python3 scripts/hudoc.py fetch "<reference>" --format text`. This
   resolves → fetches the DOCX (or PDF if DOCX fails) → extracts plain text
   → caches everything. Stdout shows the resolved itemid, docname, appno, date,
   court branch, and source URL. On server errors, retries automatically.
2. Read the text file (path is in the JSON output). Cite paragraph numbers
   directly — the text preserves paragraph breaks, so you can find
   "**88.   Article 3 (art. 3) makes no provision...**" by grepping for
   `^88\.` or for the `§ 88` style.
3. Quote sparingly and accurately. Append the source URL when citing.

If the user gave only a partial name and you're unsure which case they
meant, run `search` first and show 3-5 candidates before fetching.

### The user wants filtered search

Use `search` with a Lucene-style query. The most useful filters:

```
docname:(strand lobben)            free-text title match (AND of tokens)
appno:"14038/88"                   exact application number
respondent:"NOR"                   ISO-3 country code of the respondent state
article:"8"                        substantive article invoked
conclusion:"Violation of Article 8"  conclusion text contains this phrase
doctypebranch:GRANDCHAMBER         GC | CHAMBER | COMMITTEE | ADMISSIBILITY
                                   | ADMISSIBILITYCOM | COMMUNICATEDCASES
                                   | ADVISORYOPINIONS | CLIN | RESOLUTIONS
                                   | EXECUTION
importance:"1"                     1 (key cases) | 2 | 3 | 4 (least cited)
languageisocode:"ENG"              ENG | FRE
kpdate:[2020-01-01T00:00:00Z TO 2024-12-31T00:00:00Z]   date range
```

For more on the query language and the field set, see
`references/query-fields.md`.

### The user wants citation chains

`citations <ref>` parses the `scl` field, which HUDOC populates with a
semicolon-separated list of every Strasbourg case the judgment relies on,
typically with paragraph numbers and dates. The output is:

```json
{
  "itemid": "001-210077",
  "docname": "CASE OF BIG BROTHER WATCH ...",
  "cited_count": 27,
  "cited": [
    {"raw": "Roman Zakharov v. Russia [GC], no. 47143/06, ECHR 2015",
     "name": "Roman Zakharov v. Russia [GC]",
     "appnos": ["47143/06"], "date": null},
    ...
  ]
}
```

To follow a citation chain, feed any `appnos[0]` value back into
`fetch`/`metadata`. There's no in-bound "cited by" graph in the public API
— if the user wants that, you'd need to search for each appno appearing
inside other judgments' `extractedappno` field, e.g.
`search 'extractedappno:"14038/88"'` finds cases that reference Soering.

### The user mixes English and French

The script's default language preference is `ENG,FRE`. To prefer French
or another language pass `--lang-pref FRE,ENG`. The HUDOC parallel French
version (when published) has a different itemid from the English one but
the same `appno` + `judgementdate`, so for a French translation of an
English-only resolved case run:

```bash
python3 scripts/hudoc.py search '(appno:"<appno>") AND (languageisocode:"FRE")'
```

## ECtHR terminology — dispositif vs reasoning

When the user asks for "the operative paragraph", "the holding", "the
dispositif", or "what the Court actually decided", they mean the formal
list at the very end of the judgment, after the heading **FOR THESE
REASONS, THE COURT** (or *PAR CES MOTIFS, LA COUR* in French). It's a
numbered or lettered list of unanimous / N-to-M votes:

> FOR THESE REASONS, THE COURT
> 1. *Holds*, unanimously, that there has been a violation of Article 8
>    of the Convention as regards the section 8(4) regime;
> 2. *Holds*, by sixteen votes to one, that there has been a violation
>    of Article 10 of the Convention …
> 5. *Holds*, by twelve votes to five, that there has been no violation
>    of Article 8 of the Convention as regards the regime for receipt of
>    intelligence from foreign intelligence services …

That list **is** the operative part. The closing sentences of each
analytical section ("There has accordingly been a violation of Article 8")
are *the conclusion of the substantive reasoning*, not the dispositif —
even though they say the same thing. Quote both when relevant, but label
them correctly.

To find the dispositif in the extracted text, grep for `FOR THESE REASONS`
(English) or `PAR CES MOTIFS` (French). It's almost always near the very
end of the file.

## Citation format

Cite ECtHR cases the way the Court itself cites them in its judgments
(see the *Practical Guide on Admissibility Criteria*):

- **Modern judgment**:
  *Big Brother Watch and Others v. the United Kingdom* [GC],
  nos. 58170/13, 62322/14 and 24960/15, § 332, 25 May 2021
- **Older Chamber judgment**:
  *Soering v. the United Kingdom*, 7 July 1989, § 88, Series A no. 161
- **Decision**:
  *Senator Lines GmbH v. fifteen member States of the European Union* (dec.) [GC],
  no. 56672/00, ECHR 2004-IV

Always include the itemid or `https://hudoc.echr.coe.int/eng?i=<itemid>`
URL when sourcing in chat — the search-friendly format.

**Never paraphrase a holding from memory.** Pull the text via the script
and quote from it. ECtHR holdings are routinely revisited (Chamber → Grand
Chamber, GC overruling earlier line) and the *exact* Convention article
relied on, the precise paragraph number, and the conclusion wording (which
distinguishes "Violation" from "No violation" from "Preliminary objection
dismissed") all matter for legal accuracy.

## Cache layout

```
cache/items/<itemid>/
  meta.json        Parsed metadata from /app/query/results
  judgment.docx    Official DOCX from /app/conversion/docx/
  judgment.pdf     Official PDF from /app/conversion/pdf/
  judgment.txt    Plain-text extraction of the DOCX
```

`meta.json` is what `metadata` writes; it's the most useful starting point
for factual questions (parties, conclusion, articles, separate opinions,
list of cases cited). Read this first before extracting from the full text
when answering quick questions.

## Error handling and edge cases

- **Empty `scl`** — Older Commission decisions, Committee of Ministers
  resolutions, press releases, and many committee-level admissibility
  decisions have no Strasbourg case-law field. `citations` will return
  `cited_count: 0`. This is informational, not an error.
- **No match for a case name** — `resolve` builds the docname clause as an
  AND-of-tokens, stripping " v. " / " c. " / "vs.". If a name still
  doesn't resolve, fall back to `search 'docname:(token1 token2)'` and
  inspect the candidates.
- **Multiple-application cases** — A single judgment can have a dozen
  applicants joined into one case (e.g. `58170/13;62322/14;24960/15`).
  Searching by any