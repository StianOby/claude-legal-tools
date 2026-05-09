---
name: efta-court
description: |
  Use this skill any time the user needs case law from the EFTA Court — the court
  that interprets the EEA Agreement for Norway, Iceland and Liechtenstein. Triggers
  include any reference like E-1/94, E-08/26, "Holship", "Finanger", an Advisory
  Opinion to the EFTA Court, an infringement action by the EFTA Surveillance
  Authority (ESA) v an EFTA State; also natural-language asks like "find the EFTA
  Court case where Y", "list pending EFTA Court cases", "hva sa EFTA-domstolen om
  Z". Use even when the user doesn't name eftacourt.int: if the answer needs the
  text of an EFTA Court judgment, advisory opinion or order, or the parties /
  status / documents of a specific case, this is the right tool. Prefer this over
  training-data recall — the EFTA Court regularly delivers new judgments and only
  eftacourt.int guarantees current text. Do NOT use for: CJEU case law (eurlex);
  Norwegian Høyesterett (lovdata-pro); Norwegian statutes (lovdata); ECHR.
---

# EFTA Court — Case Law Lookup

This skill talks to `eftacourt.int` to find and download case law from the
EFTA Court — the court that interprets the EEA Agreement for the three EFTA
states inside the EEA (Iceland, Liechtenstein, Norway).

You have a single self-contained CLI at `scripts/efta_court.py`. Run it with
`python3` from this skill's directory. It caches everything locally so a
second lookup of the same case is instant.

---

## What the EFTA Court does (so you trigger correctly)

The EFTA Court has three main types of business; if any of them shows up in
the user's question, you should use this skill.

| Type | Code | Started by | Typical citation form |
|---|---|---|---|
| Advisory opinion | AO | Reference from a national court of NO/IS/LI | `E-1/95` |
| Infringement action | INF | EFTA Surveillance Authority (ESA) v EFTA State | `E-2/12` |
| Direct action against ESA | DA | Private party v ESA | `E-15/10` |

Common case naming you'll see: `E-1/94` (the very first case), `E-2/11`
("STX"), `E-14/15` ("Holship"), `E-1/99` ("Finanger I"). Joined cases use
"Joined Cases E-X/YY and E-Z/YY".

Languages: judgments and orders are issued in English; advisory opinion
requests come in the language of the referring court (Norwegian, Icelandic,
or German). Documents on the case page are tagged with a language suffix
(EN/NO/IS/DE).

---

## Mental model of the data

The CLI works in two layers and always lays down a local cache so repeated
queries are cheap.

**Layer 1 — Index of all cases.** The site exposes
`/wp-json/wp/v2/cases?per_page=100` paginated. ~457 cases total as of
mid-2026 across 5 pages. Each entry has the slug, the date the page was
created, and taxonomy chips (`sources-*`, `procedure_an_result-*`) that say
which national court referred the case and what kind of procedure it is.
This is enough to answer "list cases by year", "show recent advisory
opinions", "find ESA v Iceland cases".

**Layer 2 — Per-case detail page.** The REST API does not expose case
content (the title field is just the case number). To get parties, status,
dates, and the document PDFs you must fetch and parse the HTML at
`/cases/<slug>/`. The CLI does this and parses it into JSON. PDFs are
linked from that page at `/download/<name>/?wpdmdl=<id>`.

**The slug isn't deterministic.** `E-8/25` lives at `/cases/e-8-25/`
but `E-08/26` lives at `/cases/e-08-26/`. Always resolve a case number
through the local index — never hand-build a URL.

---

## Use it like this

Always start with the script's `--help`, then use these recipes:

| User says | Run |
|---|---|
| "List recent EFTA Court judgments" | `python3 scripts/efta_court.py list --decided --limit 10` |
| "What are the pending cases?" | `python3 scripts/efta_court.py list --pending --limit 20` |
| "Cases from Norway in 2024" | `python3 scripts/efta_court.py list --year 2024 --country NO` |
| "Advisory opinions in 2025" | `python3 scripts/efta_court.py list --year 2025 --procedure AO` |
| "Fetch case E-14/15" / "Holship judgment" | `python3 scripts/efta_court.py fetch E-14/15` |
| "ESA v Norway cases" | `python3 scripts/efta_court.py search "Norway" --party-only` |
| "Find the case about state aid in 2024" | `python3 scripts/efta_court.py search "state aid" --year 2024` |
| "Get the judgment text in E-14/15" | `python3 scripts/efta_court.py get E-14/15 --type judgment` |
| "Norwegian version of the request in E-8/26" | `python3 scripts/efta_court.py get E-8/26 --type request --lang NO` |

### Subcommands

- **`update`** — refresh the local case index from the WP REST API. The
  index is small (~150 KB) so refreshing is cheap. Run when the user asks
  about something recent, or when a `fetch` returns "case not found".
- **`list`** — query the local index. Filters: `--year`, `--country`
  (NO/IS/LI), `--procedure` (AO/INF/DA), `--pending`, `--decided`,
  `--limit`. Returns a JSON-and-text table of case numbers. The first
  time you pass `--pending` or `--decided`, the CLI verifies the status
  of all recent cases (last 3 years by default; tune with
  `--verify-years N`) by fetching their detail pages — this is necessary
  because the public pending listing on eftacourt.int is JS-paginated
  and unreliable. The verified statuses are cached in the index, so
  later calls are fast.
- **`fetch <case>`** — resolve the case via the index, download the
  detail page, parse it, and write `meta.json` + a human-readable
  `summary.txt`. Also lists the available documents and their PDF URLs.
  Pass a case number in any reasonable form: `E-14/15`, `E-14-15`,
  `e14/15`.
- **`get <case> [--type T] [--lang L]`** — download a specific PDF
  (judgment, order, request, notification, opinion-of-aag, …) and
  also write a plain-text extraction next to it. `--lang` defaults to
  EN; pass NO / IS / DE / FR for other language versions when the
  case has them. Without `--type`, the CLI lists what's available.
- **`search <query> [--party-only] [--year YYYY] [--country C]`** —
  search local case data. By default searches case parties and titles
  in the local cache; pass `--full-text` to include text extracted
  from cached judgment PDFs (slower; only works on cases you've
  already `fetch`-ed or `get`-ed).
- **`status`** — print where the cache lives and how fresh it is.

### Case-number normalisation

The user will write case numbers in any form. The CLI accepts all of
these and resolves them to the same case:

```
E-14/15    e-14/15    E14-15    e 14/15    E-14-15    14/15
E-8/25     E-08/25    e-8-25    E0825
```

If the user writes only a year-and-number like `8/25`, the CLI assumes
prefix `E-`. If you're not sure which case the user means, run `search`
on a name fragment first.

---

## Output format and how to present results

`fetch` writes two files into the cache and prints both paths:

```
cache/cases/E-14-15/meta.json          # parsed metadata
cache/cases/E-14-15/summary.txt        # human-readable summary
cache/cases/E-14-15/raw.html           # source HTML (for re-parsing if needed)
```

`meta.json` is the source of truth for factual questions:

```json
{
  "case_number": "E-14/15",
  "title": "Holship Norge AS v Norsk Transportarbeiderforbund",
  "url": "https://eftacourt.int/cases/e-14-15/",
  "status": "Decided",
  "type": "AO",
  "language_of_request": "Norwegian",
  "date_submitted": "12/06/2015",
  "hearing_date": "16/05/2016",
  "judgment_date": "19/04/2017",
  "procedure": "Request for an advisory opinion",
  "source_court": "Norges Høyesterett",
  "about": "Request for an Advisory Opinion ...",
  "documents": [
    {
      "title": "14/15 Judgment",
      "lang": "EN",
      "date": "19/04/2017",
      "url": "https://eftacourt.int/download/14-15-judgment/?wpdmdl=4912"
    }
  ]
}
```

`get` writes the requested PDF and a `.txt` extraction:

```
cache/cases/E-14-15/judgment-EN.pdf
cache/cases/E-14-15/judgment-EN.txt
```

### When you present an EFTA Court case to the user

1. Always give the **case number** and the **case title** (parties).
2. Quote judgment paragraphs from the cached `.txt`, never from memory.
   EFTA Court judgments are paragraph-numbered — keep the numbering when
   quoting (e.g. *Holship*, para 90).
3. Cite using the form: *Case E-14/15 Holship Norge AS v Norsk
   Transportarbeiderforbund [2017] EFTA Ct. Rep. 1, para X*. If the
   user is writing in Norwegian, the conventional citation is *Sak
   E-14/15 Holship*.
4. Link to the case page (`meta.json` → `url`) and to the specific PDF
   you quoted from (`documents[i].url`).
5. If the case is still pending (`status: Pending`), say so plainly —
   there is no judgment yet, only the request and procedural documents.

### Language of your reply

Match the user's language. Quote the judgment in the language the
document was issued in (English for judgments and orders; original
language for advisory-opinion requests). If the user writes in Norwegian
and the judgment is in English, give the English quote followed by your
own translation/paraphrase.

---

## Where the cache lives

The skill folder is often read-only (installed via plugin), so the
script writes its cache to a writable user directory in this order:

1. `$EFTA_COURT_CACHE_DIR` — if set
2. `$XDG_CACHE_HOME/efta-court`
3. `%LOCALAPPDATA%\efta-court` on Windows
4. `~/.cache/efta-court` otherwise

Run `python3 scripts/efta_court.py status` to see the actual path.

---

## Common pitfalls

- **"Case not found"** after `fetch`. Run `update` and try again — your
  index might be stale (the case was published after your last update).
- **Joined cases** (e.g. *Joined Cases E-31/24 and E-32/24*) live at
  their own slug. The CLI resolves either component case to the joined
  page automatically; pass either case number.
- **Old cases (1994–2003)** sometimes have only a judgment PDF and no
  document index in the structured format. The CLI still extracts text
  from the PDF; just don't expect a fully populated `meta.json`.
- **Norwegian / Icelandic versions** of advisory-opinion requests are
  the original; the EN version posted later is a translation. For
  the legal question being referred, the original-language version is
  authoritative.
- **PDF parsing fails on a scanned old judgment**: fall back to citing
  the PDF URL directly and tell the user to read it. Don't paraphrase
  from memo