---
name: efta-court
description: |
  Use this skill any time the user needs case law or procedural texts from the
  EFTA Court — the court that interprets the EEA Agreement for Norway, Iceland
  and Liechtenstein. Triggers: case numbers like E-1/94, E-08/26, names like
  "Holship", "Finanger", "Restamark", advisory opinions, ESA infringement
  actions v an EFTA State, actions against ESA; "find EFTA Court cases on Y",
  "which judgments cite E-9/97", "what did Norway argue in E-25/24" (written
  observations), "pending EFTA Court cases", "next hearings", "hva sa
  EFTA-domstolen om Z"; the Court's Rules of Procedure, Statute, Guidance for
  Counsel, or the Surveillance and Court Agreement (SCA). Full-text search of
  all case documents. Use even when
  eftacourt.int isn't named, and prefer it over training-data recall: only
  eftacourt.int has current text. Do NOT use for: CJEU case law (eurlex);
  whether an EU act is part of the EEA Agreement, or EEA JCDs (eea-lex);
  Norwegian Høyesterett (lovdata-pro); Norwegian statutes (lovdata-api); ECHR
  (hudoc).
---

# EFTA Court — case law and procedural texts

**First step, before any command:** resolve `{SKILL_DIR}` as described under "Skill directory" below and use the printed path literally. Never guess it (e.g. `/mnt/skills/...`).

One CLI, `scripts/efta_court.py` (stdlib only), over the open JSON API
behind eftacourt.int. It loads every case and document record in about two
seconds and caches them for an hour, so filters see every case. Full-text
search runs on the Court's server and covers the text of all published
judgments, hearing reports, requests and orders.

**Skill directory (`{SKILL_DIR}`).** Always run this once before the first command, even when "Base directory for this skill:" is given: that path works for reading files, but the shell often cannot see it.
Use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/efta-court}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/efta-court/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

Run everything as `python3 {SKILL_DIR}/scripts/efta_court.py <command>` in
`Bash` (the cloud sandbox). If the API answers 403/405 from `Bash`, tell the
user "This source is blocked from Anthropic's cloud" rather than retrying.

## The Court's business

| Code | Type | Started by | Example |
|---|---|---|---|
| AO | Advisory opinion | a national court of NO/IS/LI | E-14/15 *Holship* |
| INF | Infringement action | ESA v an EFTA State | E-3/26 ESA v Norway |
| DA | Direct action | a party v ESA (annulment, failure to act) | E-4/26 Fitness Group Nordic v ESA |

Judgments and orders are in English, often with a version in the language of
the case. Requests for an advisory opinion come in the referring court's
language. The original is authoritative; the English version is a translation.

## Recipes

| User asks | Run |
|---|---|
| "Holship judgment" / "E-14/15" | `case E-14/15`, then `get E-14/15 --type judgment` |
| "Norwegian version of the request in E-8/26" | `get E-8/26 --type request --lang NO` |
| "What did Norway argue in E-25/24?" | `get E-25/24 --type observations --party Norway` |
| "Cases on collective action" | `search '"collective action"'` |
| "State aid judgments since 2020 from Iceland" | `search "state aid" --type judgment --country IS` and filter by year |
| "Which judgments cite Restamark / E-1/94?" | `cited-by E-1/94 --judgments` |
| "Advisory opinions since 2022" | `list --procedure AO --since 2022` |
| "Pending cases" / "ESA v Norway cases" | `list --pending`, `list --procedure INF --country NO` |
| "Cases where Liechtenstein submitted observations" | `list --observer Liechtenstein` |
| "Referrals from Høyesterett" | `list --court Høyesterett` |
| "What subject areas?" | `subjects` (takes the same filters) |
| "Next hearings / judgment dates" | `calendar` (`--days 180`, `--past 30`) |
| "Rules of Procedure, Art. 97" | `texts get "rules of procedure"`, then grep the `.txt` |
| "What do the procedural texts say about remote hearings?" | `texts search "remote"` |

## Commands

- **`case <case>`** (alias `fetch`): parties, status, AO/INF/DA, country,
  referring court, language of the case, subject matter, keywords, dates,
  the full diary (lodging, observations received, deadlines, hearing), the
  case page, and a numbered document list. `--json` for machine use.
  **Language of the case:** the site's field says English for many older
  advisory opinions referred in Norwegian, Icelandic or German. The CLI
  takes the language from the case's non-English document versions when
  there are any, and says so. If it prints "unverified", read the
  "Language of the request" line at the top of the judgment before stating
  it. Recent cases referred in English (e.g. by Borgarting lagmannsrett)
  really are English. A component of joined cases shows the judgment date
  "on Joined Cases …". **Status `Withdrawn`** means the case ended
  without a judgment (the site says Decided). `case` accepts any form of a case number (`E-14/15`, `e14-15`, `14/15`,
  `E-08/26`), or an exact ref for a side record (`"E-9/04 COSTS"`,
  `"E-2/12 INT"`).
- **`get <case> [--type T] [--lang L] [--doc N] [--party P]`**: downloads
  the PDF and writes a `.txt` next to it. With no `--type`/`--doc` it
  prints the document list. Types: `judgment` (advisory opinions too),
  `report` (Report for the Hearing), `request`, `notification`, `order`
  (both kinds; or `order-court`, `order-president`), `information-note`,
  `decision`, `observations`. `--lang` defaults to EN. If that language is
  missing, the CLI falls back to EN and says so on stderr: tell the user
  which language you quote. When two documents share a type and language,
  the CLI notes it; pick with `--doc N`.
- **Written observations** (`--type observations`): the observations of
  the parties, the EFTA States, ESA and the Commission, published for cases
  from about 2021 on. Pick one with `--party Norway` /
  `--party Commission` / `--doc N`. The diary in `case` shows who submitted
  observations, for older cases too, even where the text is not published.
  Observations are in the submitter's language; the list shows `--` for
  their language because the site does not record it.
- **`search "<query>"`**: matches the case details (ref, parties,
  keywords, subject matter, referring court) and the full text of every
  case document (server). It prints matching cases, newest first, with the
  document types hit and a snippet. Filters: everything `list` takes, plus
  `--type` (hits in that document type only) and `--lang EN|NO|IS|DE`;
  `--meta-only` skips the full text; `--oldest`, `--limit`, `--json`.
- **`cited-by <case>`**: later cases whose judgments, orders or decisions
  mention the case number. `--judgments` restricts it to judgments (use it
  for "which judgments cite …"); `--all` includes any document, e.g.
  hearing reports. Each comes with a snippet. It also tallies the *EFTA Court Report* references
  that the citing documents give for the cited case (see Citing).
- **`list`**: every case, filtered, one line each under a header (case,
  lodged, judgment, status, procedure, State, parties, subject matter).
  Takes `--year`, `--since`/`--until` (year of the case number),
  `--country NO|IS|LI` (for ESA actions, the State sued),
  `--procedure AO|INF|DA`, `--pending`/`--decided`/`--status withdrawn`,
  `--subject`, `--court`, `--party`, `--language`, `--limit`, `--json`.
  `--observer Liechtenstein` matches the Government of Liechtenstein, not
  the University of Liechtenstein. Give a body by its name
  (`--observer "European Commission"`).
- **`calendar`**: hearings, judgment deliveries and deadlines for written
  observations, in the next 90 days (`--days`, `--past`; `--all` adds
  conferences and talks).
- **`texts list | get <N|title words> [--lang] | search "<query>"`**: the
  Court's procedural texts. These are the Statute, the Rules of Procedure
  (EN/DE/NO/IS, plus the previous Rules), Guidance for Counsel, Guidance on
  Requests for Advisory Opinions, the Court's decisions on procedural issues,
  the collected *EFTA Court Texts*, the e-EFTACourt user guide, and the
  Surveillance and Court Agreement (SCA) with Protocols 2–5 and 7. The SCA
  is the Court's web-page copy, not an official consolidation: say so when
  you quote it.
- **`update`** re-fetches the data now; **`status`** shows the cache.

Case law and procedural texts are kept apart: `search` never lists
procedural texts, and `texts search` never lists case documents. Each ends
with one line counting the other kind's hits, e.g. `(also 4 hit(s) in
procedural texts: texts search "…")`. Mention it only if it matters to the
user's question.

## How search works

The server's rules, which the local case-details match also follows:

- Whole words, and every word must match: `collect` does not find
  "collective", and `"trade union"` misses "trade unions". For topic
  searches use a prefix: `"trade union*"` or `union*`.
- `"a phrase"` matches the words in sequence, also across a line break in
  the PDF. `+`, `-` and `OR` are not operators. Run two searches instead.
- Diacritics count: `Høyesterett`, not `Hoyesterett`.
- Case numbers work as search terms (`"E-9/97"`), and the order of the parts
  matters.
- **The server returns at most 1000 documents.** The CLI warns when it hits
  the cap. Narrow the query then (a phrase, more words, `--lang EN`).
- The snippets are for orientation only. **Never quote from a snippet.**
  `get` the document and quote from its `.txt`.

The `.txt` keeps the PDF's lines as printed, hyphens at line ends included
("non-\nprofit"). A plain `grep` for a phrase misses one that is split
across lines. Grep for one distinctive word, or use
`grep -iPzo 'state\s+aid'`.

## Presenting a case

1. Give the **case number** and the **parties** (the case title).
2. Quote from the `.txt` only, never from memory or a snippet, and keep the
   paragraph numbers (*Holship*, para 90). Text from 1990s PDFs can split
   words at odd letter spacing ("statut ory", "intr a-EEA"): join such
   fragments when quoting, and check the PDF if a word is unclear. When
   quoting across a line break, join the lines. Keep a line-end hyphen
   where the word has one ("non-profit"), and drop it where it only splits
   the word ("recognition"). PDF text has no italics.
3. **Citing:** *Case E-14/15 Holship Norge AS v Norsk
   Transportarbeiderforbund, judgment of 19 April 2016, para X*; in
   Norwegian *Sak E-14/15 Holship, avsnitt X*. Legal citations carry no URL.
   The data has no *EFTA Court Report* volume or page. `cited-by` shows the
   references later documents give, and they sometimes disagree (e.g.
   `[1994-1995] EFTA Ct. Rep. 15` ×13 vs `… 17` ×3 for E-1/94). Add a
   Reports reference only if the user wants one. Give the majority form,
   say it comes from later citing documents, and mention any disagreement.
4. **Links:** when the user wants a link to a case or to any of its
   documents, give the **case page** (`Case page:` in the output,
   `https://eftacourt.int/cases/<id>`), where the user finds the documents
   themselves. For a procedural text, give its `Page:`. Never give the
   PDF's storage URL.
5. A **pending** case has no judgment yet. Say so, and say what the diary
   shows (observations, hearing date).
6. Match the user's language. If the user writes Norwegian and the judgment
   is English, quote the English and add your own translation.

## Pitfalls

- **Joined cases:** the judgment is on the joined record ("Joined Cases E-31/24
  and E-32/24"), not on the component cases. `case`/`get` with either
  component number include the joined record's documents, marked
  `[Joined Cases …]`.
- **Side records:** costs orders, interpretation and revision cases have their
  own refs (`E-9/04 COSTS`, `E-2/12 INT`, `E-6/94r`). `case` lists them as
  "Related record"; pass the full ref to open one.
- **Not case law?** The EEA status of an EU act, or Joint Committee Decisions
  → `eea-lex`.
- **Text not extracted** (no `pdftotext`/`pypdf`, or a scanned PDF): give the
  case page, say the text could not be read, and don't paraphrase from memory.
- **Cache:** `status` shows where it is (`$EFTA_COURT_CACHE_DIR`, else the
  user cache dir). The data refreshes itself hourly. If the API cannot be
  reached, the CLI uses the cached data and says how old it is: pass that on.
