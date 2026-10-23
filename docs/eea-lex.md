# eea-lex — plan (approved in outline 2026-10-23, not yet built)

A skill over EFTA's EEA-Lex (`https://www.efta.int/eea-lex`) and the EEA legal
texts EFTA publishes. eurlex already covers EU texts, so this skill covers what
only EFTA has: an act's EEA status, Joint Committee Decisions (JCDs) before they
reach the OJ, the current annexes and protocols, and the Art. 103 list.

Deferred to separate work: kildesjekk integration, Zotero-ready JCDs,
EØS-notatbasen (regjeringen.no; Norway-only, open over plain HTTP, rich notes).

## Why the skill is worth having (verified 2026-10-23)

| | EUR-Lex / OJ | EFTA |
|---|---|---|
| Consolidated EEA Agreement | newest `01994A0103(01)-20251206` | annex PDFs dated to the last JCD meeting (Annex XI: 25.9.2026, includes JCD 277/2026) |
| JCDs | highest in Cellar: No 187/2026 (5.6.2026) | list and English PDFs up to No 287/2026 (25.9.2026) |
| OJ lag | JCD 1/2026: adopted 6.2.2026, published in the OJ 21.5.2026 | – |

## Access: honest User-Agent, no browser

`www.efta.int` is behind a Cloudflare managed challenge that is applied only
to clients whose User-Agent starts with `Mozilla/`. A plain tool UA
(`eea-lex-skill/<version>`, curl's default, `Python-urllib/3.x`) gets real HTML
and PDFs, both from the Cowork cloud sandbox and from a residential IP. Any
`Mozilla/…` UA, browser-like or not, gets a 403 with `cf-mitigated: challenge`,
on every path including PDFs and `robots.txt`. (Probes from the cloud sandbox
and the maintainer's PC, 2026-10-23.)

The same trick does **not** work for Consilium, ICJ PDFs or HUDOC. Those
challenge both kinds of UA.

Rules for the script:

- Fixed UA `eea-lex-skill/<version>`; it must never start with `Mozilla`
  (a test enforces this).
- No more than 3 redirects. Proposal factsheets (`/eea-lex/<node id>`)
  redirect to themselves (`/node/<id>` gives a 404): treat a self-redirect as
  "not found", never loop (an earlier loop ended in a 429).
- About one request per second.
- Challenge detection (403 + `cf-mitigated`, or "Just a moment" in the body):
  exit with a clear message. SKILL.md then falls back to a read-only browser
  route (`navigate` + `get_page_text`, no JS helper).

## Site facts

- Factsheet: `/eea-lex/<celex lowercase>`, e.g. `/eea-lex/32016r0679`.
  Fields: legal status, area and sub-area (e.g. `XI.III Data Protection`),
  JCD number, "In force in the EEA", documents (JCD in EN/DE/IS/NO with OJ and
  EEA Supplement references; act in EU languages; Icelandic and Norwegian
  titles and translation PDFs) and a history timeline (EU proposal, EU
  adoption, EU compliance date, draft JCD sent to the Commission, JCD adoption,
  Art. 103 fulfilment per state, confirmed entry into force, EEA compliance
  date). No free-text EEA EFTA positions; adaptations are only in the JCD.
- Listing `/eea-lex`, a Drupal Search API view (`views-exposed-form-lex-search-page`):
  - `keyword` ("free text, CELEX or other document numbers"; works)
  - `items_per_page` 6/12/24/36/48/60
  - `sort_bef_combine`: `decision_DESC|ASC`, `adoption_DESC|ASC`,
    `proposal_DESC|ASC`, `entry_DESC|ASC`, `rel_DESC`
  - `page` zero-based
  - facets `f[0]=<facet>:<id>`: `case_status`, `area_agreement`, `protocol`,
    `celex_type`, `adoption_date_eu`. Status ids seen: 3 proposed, 5 under
    scrutiny, 9 draft JCD, 11 JCD entry into force pending, 14 incorporated
    and in force, 12 no longer in force. Read the ids live, don't hard-code.
- Proposals have no working factsheet; the listing card gives the COM/C/D
  number and the title.
- JCD PDFs: `/sites/default/files/documents/legal-texts/eea/other-legal-documents/adopted-joint-committee-decisions/<YYYY> - <English|German|Icelandic|Norwegian>/<NNN>-<YYYY>[|g|i|n].pdf`
  (about 190 KB, 2 pages).
- Yearly JCD lists (text layer; JCD → dates, OJ/Supplement refs, annex, CELEX):
  `/sites/default/files/documents/legal-texts/eea/other-legal-documents/List-Adopted-Joint-Committee-Decisions/<YYYY> List of Adopted Joint Committee Decisions.pdf`
  (1994: lowercase "adopted").
- Agreement texts: the main text PDF, and annexes linked from
  `/about-efta/legal-documents/eea-legal-texts/annexes-agreement` (paths vary:
  Annex IX lacks `media/`, so scrape them live). Protocols are linked from
  `/about-efta/legal-documents/adopted-joint-committee-decisions/105046`.
  The version date is printed in the PDF page header.
- Art. 103 constitutional-requirements and awaited-notifications lists are
  linked from `/legal-texts/eea`. The URL is still to be found.

## Plan

1. `plugins/eea-lex/` (0.1.0, marketplace entry), CLI
   `skills/eea-lex/scripts/eea_lex.py` (stdlib; `pdftotext`, else `pypdf`, as in
   efta-court):
   - `factsheet <CELEX | "Regulation 2016/679">` (resolved through `keyword`)
   - `search --keyword --status --annex --protocol --type --year --sort --page`
   - `jcd <NNN/YYYY> [--lang] [--text]`: the list gives the acts and dates;
     Cellar decides "in the OJ (CELEX 2YYYYD####, hand off to eurlex)" or
     "not yet in the OJ (EFTA PDF text)"
   - `agreement main | annex <N> | protocol <N> [--find <CELEX|phrase>]`, with
     the version date
   - `pending103`
2. SKILL.md: routing (eurlex, efta-court, lovdata-*, norges-traktater,
   eu-agreements-treaties); how to cite a JCD not yet in the OJ; caveat that
   EEA-Lex and EFTA's annexes are information, not authentic text (OJ/EEA
   Supplement are); answer in the user's language.
3. `tests/eea-lex/`: fixtures saved from the site (check for personal data),
   UA test.
4. Cross-references, each with a version bump: eurlex (section, scope line,
   description ≤ 1024 characters), efta-court, eu-agreements-treaties,
   norges-traktater (one routing line each); marketplace description.
5. Run `snapshots.py check` first; `plugin validate` at the end.
