---
name: icj
description: Use whenever the user needs ICJ or PCIJ material — case law, advisory opinions, jurisdictional facts, optional-clause declarations, or treaty bases. Triggers: named cases (Nicaragua, Lotus, Chorzów, Whaling, Bosnia Genocide, Israeli Wall, Chagos, etc.); ICJ case numbers or PCIJ series codes; Article 36(2) optional clause, compulsory jurisdiction, reservations, reciprocity; jurisdictional bases; states entitled to appear; questions like "could state A bring B before the ICJ", "find the PCIJ Lotus judgment", "hva sa ICJ i Whaling-saken". Use even when the Court isn't named if the question requires ICJ/PCIJ judgment or jurisdictional text. Prefer over training-data recall — declarations change and only icj-cij.org is authoritative. Do NOT use for: ECtHR/Strasbourg (hudoc); CJEU/EU law (eurlex); Norwegian domestic law (lovdata); Council of Europe treaties (ets); UN treaty status (untc); EFTA Court. Pleadings and verbatim records are out of scope.
---

# ICJ — International Court of Justice

This skill exposes ICJ and PCIJ case law plus the Court's jurisdictional architecture (Article 36 declarations, jurisdictional treaties, organs entitled to request advisory opinions, states entitled to appear) through a small Python CLI that scrapes `icj-cij.org` and caches the slow-changing parts on disk.

The user's most common questions are of three kinds, and the skill is organised around them:

1. **Case law lookup** — "what did the Court say in X", "find me the judgment in Y", "list pending cases", "PCIJ Lotus".
2. **Jurisdictional analysis** — "could state A bring state B to the Court", "what reservations did France attach to its declaration", "which states have accepted compulsory jurisdiction", "which agencies can request advisory opinions".
3. **Declaration text** — the verbatim text of any state's optional-clause declaration, e.g. to compare two declarations and decide whether their reservations would carve out a particular dispute.

Pleadings, written observations and verbatim records of hearings are deliberately **out of scope**. A separate skill is planned for those.

## Setup

All scripts live in `scripts/`. They are plain Python 3 and depend only on `requests` and `beautifulsoup4`:

```bash
pip install requests beautifulsoup4 --break-system-packages
```

The CLI entry point is `scripts/icj.py`. Run `python scripts/icj.py --help` for the subcommand list. Cached data lives in `data/cache/` and is created on first use.

## Cache and freshness

Jurisdiction pages (the seven `/index.php/...` pages listed below) and the per-state declaration texts change over time as states deposit new declarations, terminate them, or amend reservations. The skill keeps a local cache and offers explicit freshness controls so you don't silently serve stale answers:

- `python scripts/icj.py status` — print, for every cached page, when it was last fetched, the server's `Last-Modified` header (if any), and whether a HEAD request now reports the resource as changed.
- `python scripts/icj.py refresh` — re-fetch any page that has changed (or all pages if `--all` is passed). Updates the cache and the manifest atomically.
- The default TTL for jurisdiction data is 14 days. After that, every read prints a "stale, consider refreshing" notice on stderr but still returns the cached value.

When the user asks a question that hinges on the *current* state of jurisdiction (e.g., "does Iceland still accept compulsory jurisdiction"), run `status` first; if anything is stale or changed, run `refresh` before answering. When the question is about historical facts (e.g., what the Lotus judgment said), the cache age does not matter — case-law PDFs at `icj-cij.org` are immutable.

## Subcommands

The CLI groups functionality by data type. Each subcommand prints either machine-friendly JSON (with `--json`) or a short human-readable summary. PDFs are referenced by URL — the skill does not download or parse PDFs by default; the user can fetch them directly if needed.

### `cases` — ICJ contentious + advisory cases

- `cases list [--pending] [--year YYYY] [--country XX] [--advisory] [--contentious]` — list the Court's cases. Default lists all 170+ cases. `list-of-all-cases` is the source.
- `cases show <case_id>` — show a case page: title, parties, key dates, and links to all judgments / orders / advisory opinions / summaries / press releases. **Pleadings and oral proceedings are intentionally omitted** from the output (see "Out of scope" below).
- `cases recent [--limit N]` — the latest decisions across all cases (mirrors the `/decisions` page).
- `cases search "query"` — substring search over case titles in the cache.

### `pcij` — Permanent Court of International Justice (1922-1946)

- `pcij list [--series a|b|ab]` — list PCIJ cases in Series A (Judgments 1923-1930), Series B (Advisory Opinions 1923-1930), or Series A/B (from 1931). Default: all three.
- `pcij show <code>` — show a PCIJ case (e.g. `A10` for Lotus, `B04` for Nationality Decrees in Tunis and Morocco, `A/B53` for Eastern Greenland). Lists judgment, dissenting opinions, declarations, orders, annexes — each with its PDF URL.

PCIJ Series C (pleadings/oral arguments), Series D (organisational acts), Series E (annual reports) and Series F (indexes) are listed in `references/pcij-series.md` for completeness but are not exposed as commands — the same hearing-documents-out-of-scope rule applies.

### `jurisdiction` — the seven jurisdictional pages

- `jurisdiction states [--with-declaration] [--un-member] [--non-un]` — the table of all 193 UN members plus historical entries, with admission date and (where applicable) the date their Article 36(2) declaration was deposited. Source: `/states-entitled-to-appear`.
- `jurisdiction non-un` — text of `/states-not-members` (states that became party to the Statute without being UN members).
- `jurisdiction non-parties` — text of `/states-not-parties` (states not party to the Statute to which the Court may be open under Art. 35(2) and SC Resolution 9 (1946)).
- `jurisdiction basis` — text of `/basis-of-jurisdiction` (the Court's own description of how jurisdiction can be founded: special agreement, treaty clause, optional clause, forum prorogatum, Article 35).
- `jurisdiction treaties [--year YYYY] [--search QUERY]` — the long table of treaties that confer jurisdiction on the Court.
- `jurisdiction organs` — text of `/organs-agencies-authorized` (UN organs and specialized agencies entitled to request advisory opinions, with the list of opinions each has requested).

### `declarations` — Article 36(2) optional-clause declarations

- `declarations list` — every state currently shown on `/declarations`, with ISO-2 country code and date of deposit.
- `declarations show <state>` — full text of one state's declaration. `<state>` may be the ISO-2 code (`no`, `fi`, `gb`) or a unique name prefix (`Norway`, `United Kingdom`).
- `declarations compare <state1> <state2> [<stateN> ...]` — print the texts side by side. Useful for deciding whether two states' declarations would intersect over a given subject matter (see workflow below).

## Workflow: "Could states X and Y litigate dispute Z at the ICJ?"

This is the headline use case the user described — e.g. *would Norway's and Finland's Article 36(2) declarations allow an ICJ case concerning a territorial dispute between them*. The analysis has a fixed shape:

1. **Confirm both states are parties to the Statute.** Run `jurisdiction states` and check both are listed (all UN members are; otherwise check `non-un` or `non-parties`).
2. **Confirm both have made a declaration under Article 36(2).** Run `declarations list` — if either is missing, compulsory jurisdiction under the optional clause is unavailable and you must look for a treaty basis (`jurisdiction treaties`) or special agreement (`jurisdiction basis`).
3. **Pull both texts.** `declarations compare no fi`. Read the full text — the date the declaration came into force, its duration / termination clause, and crucially the *reservations*.
4. **Apply reciprocity.** Under Article 36(2) and the Court's case law (Norwegian Loans, Interhandel), each state can invoke the other's reservations against it. So a dispute is covered by the optional clause only if it falls outside *both* states' reservations.
5. **Map reservations to the dispute.** Common reservation categories: disputes covered by another method of settlement; disputes arising before a date X; disputes with members of the Commonwealth; disputes concerning the law of the sea (e.g. Norway's UNCLOS carve-out); disputes concerning national defence or military activities; disputes that the state notifies in advance.
6. **Conclude.** Either the dispute fits within both declarations (compulsory jurisdiction available); or it does not, in which case the parties would need a special agreement or another jurisdictional treaty.

Always quote the relevant reservation language verbatim from the declaration text — paraphrasing reservations changes their legal effect.

## How to ground answers

When answering substantive questions:

- For **case law**, link to the official PDF on `icj-cij.org` (the URLs returned by `cases show` / `pcij show` are the canonical ones). If the user wants the text of a judgment, point them at the PDF — the skill does not extract PDF text by default. If they explicitly ask, you can use a separate PDF tool to read it.
- For **jurisdictional facts**, cite the page name (e.g. "States entitled to appear before the Court") and the date the cache was last refreshed. Always check `status` first if the user's question is about the current legal position.
- For **declarations**, quote the deposit date and the relevant clause exactly as it appears in the cached text. The skill stores the canonical English version published by the Court.

## Out of scope (deliberately)

This skill does not expose:

- **Pleadings, written observations, counter-memorials, or verbatim records of oral hearings.** Even when present in a case page, they are filtered out of `cases show` output. A separate skill will handle hearing documents.
- **PDF text extraction.** PDFs are referenced by URL; reading them is the user's choice using a generic PDF tool.
- **Translation.** Documents are surfaced in English by default. French URLs are noted when present but not parsed.
- **Live-scraping every request.** Jurisdiction data goes through the cache; case data is fetched on demand and cached briefly. The user-facing freshness contract is described above.

## File layout

```
icj/
├── SKILL.md
├── scripts/
│   ├── icj.py            # CLI entry point; thin dispatcher to the modules below
│   ├── _common.py        # HTTP, cache manifest, freshness, country codes
│   ├── jurisdiction.py   # the 7 /index.php/... pages
│   ├── declarations.py   # /declarations and /declarations/<cc>
│   ├── cases.py          # /list-of-all-cases, /case/<N>, /decisions
│   └── pcij.py           # /pcij-series-{a,b,ab}
├── references/
│   ├── url-patterns.md       # all URLs, PDF naming, doc-type codes
│   ├── jurisdiction-overview.md  # Statute Articles 34-36, optional clause, reciprocity
│   ├── declaration-analysis.md   # how to compare two declarations (Norway-Finland worked example)
│   ├── pcij-series.md            # Series A/B/A/B/C/D/E/F overview
│   └── data-codes.md             # ISO-2 codes, document-type codes used in PDF filenames
└── data/cache/                # populated at runtime; manifest.json + per-page payloads
```

When a question maps to one of the reference files, read the relevant file before answering — they encode case-law nuance the SKILL.md keeps short.
