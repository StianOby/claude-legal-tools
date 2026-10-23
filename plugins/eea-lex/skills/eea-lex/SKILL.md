---
name: eea-lex
description: |
  Use when the user needs the EEA side of an EU act or the EEA Agreement itself, from EFTA (efta.int): whether and when an EU regulation, directive or decision was incorporated into the EEA Agreement, its EEA-Lex status, its annex or protocol, EEA Joint Committee Decisions (JCDs) incl. those not yet in the OJ, the current annexes, protocols and main text with the EFTA adaptations, the Norwegian/Icelandic text of EU acts, and JCDs awaiting constitutional requirements (Art. 103). Triggers: EEA-Lex, EØS-komiteens beslutning, JCD 154/2018, "er forordningen tatt inn i EØS-avtalen?", "is the AI Act EEA-relevant?", "when did the GDPR enter into force in the EEA?", vedlegg XI til EØS-avtalen, Protocol 31, "which JCDs await Norway's constitutional requirements?". Do NOT use for: the text of EU acts or CJEU case law (eurlex); EFTA Court cases (efta-court); Norwegian implementing law (lovdata-api); Norway's treaty register (norges-traktater); EU-side treaty status (eu-agreements-treaties).
---

# EEA-Lex — EEA status of EU acts, Joint Committee Decisions, EEA Agreement texts

**First step, before any command:** resolve `{SKILL_DIR}` as described under "Skill directory" below and use the printed path literally. Never guess it (e.g. `/mnt/skills/...`).

EU acts apply in Iceland, Liechtenstein and Norway only once the EEA Joint
Committee has incorporated them into an annex or protocol of the EEA Agreement
by a Joint Committee Decision (JCD). EFTA publishes the facts about that
process at `www.efta.int`; this skill reads them. EUR-Lex has the EU text and,
months later, the JCD in the Official Journal; everything before that is only
at EFTA:

| What | Source | Command |
|---|---|---|
| EEA status of an EU act: stage, legal status, annex/area, JCD, in force in the EEA, dated history (EU adoption, draft JCD, JCD adoption, Art. 103 fulfilment per state, entry into force, EEA compliance date), JCD and act PDFs in EN/DE/IS/NO | EEA-Lex factsheet | `factsheet` |
| Acts by status, annex, protocol, type, year or keyword (proposals too) | EEA-Lex search | `search` |
| A JCD: adoption, confirmed entry into force, OJ and EEA Supplement refs, annex, acts; whether it is in the OJ yet (Cellar); its text | EFTA's yearly JCD lists, JCD PDFs, Cellar | `jcd` |
| The current main text, annexes and protocols (EFTA's consolidated versions), an act's annex entry with its adaptations and the footnote naming the JCD | EFTA's agreement PDFs | `agreement` |
| The Norwegian or Icelandic text of an EU act (EEA Supplement translation, or EFTA's consolidated translation), an article or a phrase in it | the translation PDF linked from the factsheet | `translation` |
| JCDs whose entry into force waits for a state's constitutional requirements (Art. 103), per state | EFTA report 5.2.2 (regenerated daily) | `pending103` |

One CLI, standard library only: `scripts/eea_lex.py` (`python3`, ≥ 3.9).
PDF text needs `pdftotext` (poppler) or `pypdf`; both work.

**Skill directory (`{SKILL_DIR}`).** Always run this once before the first command, even when "Base directory for this skill:" is given: that path works for reading files, but the shell often cannot see it.
Use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/eea-lex}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/eea-lex/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

## Where each step runs

| Step | Runs in |
|---|---|
| Everything (`scripts/eea_lex.py`: efta.int, Cellar) | cloud sandbox (`Bash`) |
| Fallback when efta.int challenges the script (exit code 3) | browser pane, read-only |

Cowork runs in the cloud: `Bash` has Anthropic's IP, not the user's.
`www.efta.int` puts a Cloudflare challenge on every client whose User-Agent
starts with `Mozilla/`, and lets the script's own honest UA through (cloud and
residential IP, 2026-10-23). Never change the UA or retry with a browser UA.

## Which skill

| The user needs | Use |
|---|---|
| EEA status, JCDs, EEA annex/protocol text, Art. 103 | **this skill** |
| The text of the EU act, CJEU case law, a JCD already in the OJ (authentic text) | `eurlex` (CELEX from `jcd`) |
| EFTA Court judgments and advisory opinions | `efta-court` |
| How Norway implemented the act (lov/forskrift) | `lovdata-api` |
| The EEA Agreement in Norway's treaty register, Stortinget's consent | `norges-traktater` |
| EU-side status of an international agreement (signature, ratification) | `eu-agreements-treaties` |

## Recipes

Run from `{SKILL_DIR}`; every command takes `--json`, and `--refresh` to ignore the cache.

| User asks | Run |
|---|---|
| "Is the GDPR part of the EEA Agreement? Since when?" | `python3 scripts/eea_lex.py factsheet "Regulation 2016/679"` |
| Any act by CELEX | `python3 scripts/eea_lex.py factsheet 32019L1152` |
| "Is the AI Act being taken into the EEA?" / an act not yet adopted in the EU | `python3 scripts/eea_lex.py search -k "artificial intelligence" --limit 12` |
| "Which acts in Annex XI are awaiting entry into force?" | `python3 scripts/eea_lex.py search --annex XI --status pending --details` |
| "Data-protection acts incorporated" | `python3 scripts/eea_lex.py search --annex XI.III --status in-force --limit 60` |
| "What did JCD 154/2018 do? Is it in the OJ?" | `python3 scripts/eea_lex.py jcd 154/2018` |
| "Give me the text of JCD 287/2026" / in Norwegian | `python3 scripts/eea_lex.py jcd 287/2026 --text` / `--text --lang NO` |
| "How is the GDPR adapted for the EFTA States?" | `python3 scripts/eea_lex.py agreement annex XI --find 32016R0679` |
| "What does Protocol 31 say about X?" | `python3 scripts/eea_lex.py agreement protocol 31 --find "X"` |
| Article of the main part | `python3 scripts/eea_lex.py agreement main --find "Article 102"` |
| "Which JCDs await Norway's constitutional requirements?" | `python3 scripts/eea_lex.py pending103 --state NO` |
| "Hvordan lyder personvernforordningen artikkel 6 på norsk?" | `python3 scripts/eea_lex.py translation 32016R0679 --article 6` |
| Check a Norwegian quotation from an EU act | `python3 scripts/eea_lex.py translation 32019L1152 --find "tydelige og forutsigbare arbeidsvilkår"` |

### `factsheet <act>`

Accepts a CELEX number, "Regulation 2016/679", "Directive 95/46/EC",
"Regulation (EC) No 1907/2006", or an EEA-Lex URL. The CELEX is built from
the citation (regulations and decisions are number/year before 2015 when
written with "No"); if that page does not exist, the keyword search is tried,
and when it finds no single act it prints the hits — pick one and run
`factsheet <CELEX>`. Proposals (items with a numeric id and a COM/C/D number)
have **no factsheet**: their page redirects to itself. The script treats that
as "not found"; `search` shows their listing card (number and title).

Output: EEA-Lex stage, legal status, area(s), JCD number, "In force in the
EEA", the history with dates (newest first) and the document links (JCD in
EN/DE/IS/NO with OJ and EEA Supplement refs; the act on EUR-Lex; the
Icelandic and Norwegian translations of the act). The factsheet has no
free-text EEA EFTA positions; the adaptations are in the JCD and the annex.

### `search`

`--keyword/-k` (free text, CELEX, COM/C/D numbers), `--status` (proposed,
scrutiny, draft, pending, in-force, no-longer), `--annex` (XI, 11, XI.III),
`--protocol` (31), `--type` (Regulation, Directive, Decision, Recommendation,
Other), `--year` (EU adoption), `--sort` (relevance, jcd, adopted, proposal,
entry, each with `-asc`), `--limit` (6–60), `--page` (zero-based). Filter ids
are read live from the site; `facets` lists them with counts. Cards show
only the number and title; `--details` fetches each hit's factsheet (status,
JCD) at one request per second, so keep `--limit` small with it. The total
("178 items / 30 pages") is EEA-Lex's own; say so when you report a count.

### `jcd <NNN/YYYY> [--text] [--lang EN|DE|IS|NO]`

Reads the row from EFTA's yearly list of adopted JCDs (adoption date,
confirmed entry into force, OJ and EEA Supplement refs, annex/protocol, each
act with CELEX and EU compliance date), then asks Cellar whether the JCD is
in the OJ:

- **"In the OJ (Cellar): CELEX 2YYYYD####"** → the authentic text is on
  EUR-Lex; use `eurlex` with that CELEX to quote it.
- **"Cellar: no record yet"** → not yet published in the OJ. EFTA's PDF is
  the text to use (`--text` downloads it and prints the `.txt` path; read
  that file). The OJ lag is months: JCD 1/2026 was adopted on 6.2.2026 and
  published on 21.5.2026.

A JCD newer than the list (the list is regenerated irregularly; in October
2026 the 2025 list was still the one of 5.12.2025) is taken from its PDF:
title and adoption date only, with a note. An empty OJ column therefore
means "not in EFTA's list", not "unpublished"; Cellar decides. For 1994–2005
the lists have a layout the script does not read; dates and title then come
from the JCD itself, and Cellar gives the CELEX.

"Entry into force (confirmed): -" for a recent JCD usually means it waits for
constitutional requirements; check `pending103 --jcd NNN/YYYY`.

### `agreement main | annex <N> | protocol <N> [--find <CELEX | phrase>]`

Downloads EFTA's current consolidated PDF (cached for a day) and prints its
**version date** (from the page header, e.g. Annex XI "25.9.2026", which
includes the JCDs of that meeting) and the path to the extracted text.
Annexes II, XIII and XXI come in parts (`annex 13` gets all three, `annex 13b`
one). `--find 32016R0679` prints the act's whole annex entry, with its
"as amended by" indents and the EEA adaptations, plus the footnotes it cites
(which say which JCD inserted or amended it, with OJ ref and e.i.f. date).
`--find "phrase"` prints a few lines around each hit with the page number.
For anything longer, read the `.txt` file.

### `translation <act> [--lang NO|IS] [--article N | --find "phrase"]`

Downloads the translation the factsheet links ("Legal act in Norwegian: EEA
Suppl. No 21, 1.4.2026, p. 917-933") and extracts it. `--article 6` prints
that article (to the next article or chapter heading); `--find` prints the
lines around each hit. The output says which **kind** of copy EFTA serves:

- **the EEA Supplement as printed**: page headers carry the Supplement page
  ("Nr. 21/917"), and the output gives "Supplement No 21, p. 917" for each
  hit. This is the published Norwegian/Icelandic text.
- **EFTA's consolidated text** ("Konsolidert tekst – bare for
  informasjonsformål", with its date; the Norwegian GDPR, as of 3.3.2022): it
  includes later corrections and amendments, carries markers such as `►B`,
  `►C1` and `◄`, and has no Supplement page numbers. Ignore the markers when
  comparing a quotation; a difference may come from a correction made after
  the text the author quotes, so say so rather than calling it an error.

No translation linked → the factsheet says nothing about one; the script
stops and says so. The text is UTF-8 with the PDF's line breaks.

### `pending103 [--state IS|LI|NO] [--jcd NNN/YYYY]`

EFTA report 5.2.2: every JCD whose entry into force waits for at least one
EEA EFTA State's constitutional requirements, with the adoption date, the end
of the six-month period of Art. 103(2), the waiting states, the list's "Date
of delay" per state, the annex and the acts. The report is regenerated daily;
give its date. Use the column name "date of delay" as printed; do not
interpret it.

## Presenting results

1. **EEA-Lex and EFTA's consolidated texts are information, not authentic
   law.** The OJ (EEA section) and the EEA Supplement are authentic. Say this
   once when you rely on a factsheet or an EFTA annex for a legal conclusion,
   and give the OJ reference when there is one.
2. **Cite a JCD** as *Decision of the EEA Joint Committee No 154/2018 of 6
   July 2018 amending Annex XI (Electronic communication, audiovisual services
   and information society) and Protocol 37 (containing the list provided for
   in Article 101) to the EEA Agreement [2018/1022], OJ L 183, 19.7.2018,
   p. 23*; in Norwegian *EØS-komiteens beslutning nr. 154/2018 av 6. juli
   2018*. Not yet in the OJ: *Decision of the EEA Joint Committee No
   287/2026 of 25 September 2026 …, not yet published in the OJ (text:
   EFTA, <PDF URL>)*. Take the title from `jcd` (Cellar or PDF), never from
   memory.
3. Give dates as the source gives them, and name the source of each:
   factsheet history, JCD list (with its report date), Cellar, annex version
   date. Entry into force in the EEA and the EEA compliance date can differ
   from the EU dates; give both when the user asks "since when".
4. Quote annex and JCD text from the extracted `.txt`, never from memory.
   Lines keep the PDF's breaks; join them when quoting.
5. Link the factsheet, the JCD PDF or the annex PDF you used.
6. **Answer in the user's language.** For Norwegian users, the factsheet has
   the Norwegian title of the act, `translation` the Norwegian text, and
   `jcd --text --lang NO` the Norwegian JCD.

## Checking a claim or quotation

Which source counts, when the task is to verify what someone wrote (a source
check, a citation):

- **Incorporation and stage**: the factsheet. EUR-Lex's "Text with EEA
  relevance" says nothing about incorporation.
- **EEA dates**: the factsheet history and `jcd`. A JCD in the OJ gives only
  a conditional date ("provided that all the notifications under Article
  103(1) … have been made"); the confirmed date is EFTA's. EU and EEA dates
  differ: an EEA claim that matches only the EU date is wrong.
- **A JCD's text and citation**: in the OJ (Cellar has it) → EUR-Lex under
  the CELEX `jcd` gives, which is the authentic text; not yet → EFTA's PDF,
  and an OJ reference cited for it is wrong.
- **An annex or protocol point**: `agreement … --find`, which shows today's
  point. A point since renumbered or deleted was right at its date; it is
  only wrong if presented as current. Quote an adaptation from the JCD that
  introduced it (named in the footnote), not from the consolidated annex.
- **Pending constitutional requirements**: `pending103`, plus the factsheet
  history for those already fulfilled.
- **Norwegian or Icelandic wording of an EU act**: `translation`, never the
  English text. In a consolidated copy, a difference that a correction listed
  at its top explains is not a misquotation; say which correction. Supplement
  page pinpoints can be checked only in a Supplement copy.
- **EEA Supplement references**: the JCD's from `jcd`, the act
  translation's from the factsheet's document links.

## When efta.int blocks the script

Exit code 3 with `BLOCKED: … Cloudflare challenge` means the site now
challenges the script too. Do not retry from `Bash`. Tell the user in one
sentence and use the built-in browser, read-only: run one ToolSearch with
query `Claude_Browser` and `max_results` 64 (the prefix differs between
local and cloud Cowork), `navigate` to the factsheet
`https://www.efta.int/eea-lex/<celex lowercase>` or a search
`https://www.efta.int/eea-lex?keyword=<words>`, and read it with
`get_page_text` (or `read_page`). There is no helper and no parsing: quote
only what the page shows. PDFs (JCDs, annexes, lists) cannot be read that
way; give the user their URLs (the patterns are in `scripts/eea_lex.py`). If
the browser tools are missing, say that the source is unreachable from here.

Other errors: exit code 1 is "not found" (with a reason), exit code 2 a
network error. A Cellar failure is a note, not an error: then say that the
OJ status was not checked.

## Cache

`$EEA_LEX_CACHE_DIR`, else `$XDG_CACHE_HOME/eea-lex`, `%LOCALAPPDATA%\eea-lex`
or `~/.cache/eea-lex` (`status` prints it). Factsheets and searches are
always live; facets, list indexes and agreement texts are kept for a day, the
current year's JCD list for a day, older lists for 30 days, translations
for 7 days, JCD PDFs indefinitely, the Art. 103 report for six hours.
