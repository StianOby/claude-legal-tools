---
name: ets
description: |
  Retrieve Council of Europe (CoE) treaty documents from the Treaty
  Office — ETS (nos. 1–193) and CETS (nos. 194+). Fetches: (a)
  treaty text PDF; (b) Explanatory Report; (c) signatures/
  ratifications per state; (d) declarations and reservations per
  state. Trigger on: CoE convention name or acronym (ECHR, CPT,
  Istanbul Convention, Lanzarote Convention, Cybercrime/Budapest
  Convention, Oviedo Convention, Bern Convention, Anti-Doping,
  Macolin, Convention 108, Faro Convention, Warsaw Convention, GRECO
  statute, European Social Charter); CETS/ETS number ("ETS No. 5",
  "CETS 210", "treaty 185"); verbs like fetch/pull the text, what
  reservations did [state] make to, list parties to, when did
  [treaty] enter into force, get the explanatory report. Do NOT
  trigger for: ECtHR judgments or Strasbourg case law; EU law/GDPR/
  directives (use eurlex); UN-deposited treaties (ICCPR, CEDAW, Rome
  Statute, UNCLOS — use untc); Norwegian law (lovdata); WIPO/WTO; UN
  GA/SC resolutions; drafting contractual clauses.
---

# Council of Europe Treaty Office (ETS / CETS) skill

This skill talks to the Treaty Office's React-portlet backend at
`conventions-ws.coe.int` — the same JSON API the public site
[`coe.int/en/web/conventions/full-list`](https://www.coe.int/en/web/conventions/full-list)
uses behind the scenes. Per treaty it can pull:

1. **Treaty text** — the authoritative PDF on `rm.coe.int`.
2. **Explanatory Report** — the rapporteur's report; cited as
   quasi-travaux préparatoires for CoE conventions.
3. **Chart of signatures and ratifications** — JSON table with date
   of signature, ratification/accession, entry-into-force, denunciation
   and suspension per state, per organisation.
4. **Declarations and reservations** — full text of each declaration,
   reservation, derogation, denunciation, withdrawal, and territorial
   application, organised by state.

## When to use

Trigger this skill whenever the user wants any of:

- The text of an ETS/CETS convention or one of its protocols
- The list of states parties / signatories to a CoE treaty
- A specific state's reservations or declarations under a CoE treaty
- Dates of signature, ratification, accession, entry into force,
  denunciation
- The Explanatory Report for a CoE convention
- The CETS number when given a name (or vice versa)

A name (ECHR, Istanbul Convention, CPT, Cybercrime/Budapest), a
number (ETS 5, CETS 210), or any verb like *fetch / pull / give me
the text of / what reservations did $STATE make to / what's the
status of / who's signed* is a trigger.

## Mental model

Every CoE treaty has a 3-digit CETS number (`001`–`???`). The Treaty
Office exposes a stable JSON API; the public site is a thin React
portlet on top. The backend lives at:

```
https://conventions-ws.coe.int/WS_LFRConventions/
```

A static API token (harvested from the public page source) is
required as the `token:` HTTP header. The CLI handles that for you.

The four artefacts the skill caches:

```
text          POST api/traites/search       (entire index — gives PDF URLs)
              + GET rm.coe.int/<hash>       (treaty text PDF)
report        + GET rm.coe.int/<hash>       (Explanatory Report PDF)
signatures    GET  api/signatures?NumSte=NNN
declarations  GET  api/conventions/getDeclarations?numSte=NNN&codeNature=0
```

The PDF URLs come straight out of the master `search` response, so
once `index.json` is cached every download is one HTTP hop on
`rm.coe.int`.

## How to use

The skill is a single self-contained CLI: `scripts/coe.py`. Run it
via `python3` from this skill directory. Every command prints the
absolute paths of the files it wrote — read those rather than
guessing the cache location.

Concrete invocations:

| User says | Run |
|---|---|
| "get me the ECHR" / "fetch the European Convention on Human Rights" | `python3 scripts/coe.py fetch ECHR` |
| "pull CETS 210" / "Istanbul Convention text" | `python3 scripts/coe.py fetch 210` |
| "what reservations did Türkiye make to the ECHR?" | `python3 scripts/coe.py declarations 005`, then read the `txt` path it prints (`<cache>/treaties/005/declarations.en.txt`) and grep for the state |
| "ratification status of the Cybercrime Convention" | `python3 scripts/coe.py signatures 185` |
| "Explanatory Report to the Lanzarote Convention" | `python3 scripts/coe.py report 201` |
| "I just want the text of CETS 108" | `python3 scripts/coe.py text 108` |
| "list everything we have on the Anti-Doping Convention" | `python3 scripts/coe.py fetch 135` |
| "search the index for 'data protection'" | `python3 scripts/coe.py lookup 'data protection'` |

Available subcommands (`python3 scripts/coe.py --help` shows all):

- `index [--refresh]` — the full index of all CoE treaties (~230
  records). A snapshot ships with the skill in `data/index.json` and
  is copied into the cache on first use, so no network call is needed
  to start. `--refresh` re-downloads it (one POST). Any command that
  is asked for a number missing from the cached index refreshes
  automatically once before giving up, so new CETS numbers work
  without manual intervention.
- `lookup <query>` — fuzzy-search the cached index by name or number.
- `text <ref>` — download + extract the treaty text (PDF, or HTML
  for the few translations that rm.coe.int publishes as web pages).
- `report <ref>` — download + extract the Explanatory Report.
- `signatures <ref>` — fetch + flatten the signature/ratification
  table to plain text.
- `declarations <ref>` — fetch + flatten the declarations and
  reservations to plain text.
- `fetch <ref-or-name>` — combo: resolve a name to a number, then
  download all four artefacts. Use this whenever the user gives just
  a name or a single number.
- `show <ref> --kind text|report|signatures|declarations|meta` —
  cat a previously cached extracted-text file.

`<ref>` accepts: a 1–3 digit CETS number (`5`, `005`, `210`), a
prefixed form (`ETS 5`, `CETS 210`, `treaty 185`), an alias
(`ECHR`, `Istanbul`, `Cybercrime`, `Convention 108`, …), or any
free-text title (fuzzy-matched against the cached index).

## Cache layout

The skill folder is usually read-only (installed as a plugin), so
nothing is written there. The cache lives in a user directory:
`$ETS_CACHE_DIR` if set, otherwise `~/.cache/ets`. Every command
prints the absolute paths of the files it wrote; `show` prints a
cached text file to stdout so you never need the path at all. Files
are UTF-8 and written atomically, so an interrupted download never
leaves a truncated file behind that later looks cached.

```
<cache>/index.json                              # entire treaty list (seeded from data/index.json)
<cache>/treaties/<NNN>/meta.json                # promoted-fields meta
<cache>/treaties/<NNN>/text.en.pdf              # or text.<lang>.html when only a web page exists
<cache>/treaties/<NNN>/text.en.txt              # extracted plain text
<cache>/treaties/<NNN>/report.en.pdf
<cache>/treaties/<NNN>/report.en.txt
<cache>/treaties/<NNN>/signatures.en.json       # raw API response
<cache>/treaties/<NNN>/signatures.en.txt        # flattened, grep-friendly
<cache>/treaties/<NNN>/declarations.en.json
<cache>/treaties/<NNN>/declarations.en.txt
```

`signatures.en.txt` is a plain table. Each row carries the dates
plus a small flag tag — `R` (state has filed reservations), `D`
(declarations), `O` (objections to other states' reservations),
`T` (territorial application), `C` (communications):

```
=== Member states ===
  Albania                                  [D ] sig=1995-07-13 rat/acc=1996-10-02 eif=1996-10-02
  Austria                                  [RD] sig=1957-12-13 rat/acc=1958-09-03 eif=1958-09-03
  …
```

`rat/acc` is "ratification or accession" — the Treaty Office stores
both as `DateConsentement`.

`declarations.en.txt` groups every declaration / reservation /
derogation / withdrawal under its state, with article number and
effective date:

```
=== Albania ===
  [Declaration] art. Ex-25  effect=1996-10-02  withdrawn=1998-10-31
      The Republic of Albania declares that it recognizes the competence …
```

`meta.json` holds the promoted-fields summary (`Numero_traite`,
`Libelle_titre_ENG`, `Date_ste`, `Date_vigueur_ste`, the four PDF
URLs, the `coe.int` source URL). Read this first when answering
quick factual questions to avoid re-parsing the index.

## Workflow guidance

1. **Always start with `fetch` or `lookup`** when the user gives a
   name. If a CETS number is already given, `text` / `signatures` /
   `declarations` resolve it directly — no `lookup` needed.
2. **Prefer reading `meta.json`** for entry-into-force date, place
   of signature, treaty parent, UN registration number — they're
   already parsed.
3. **For "what reservations did $STATE make to $TREATY"** open
   `declarations.en.txt` and search for the state name. Every entry
   under each state heading is one declaration with the article it
   relates to and its effective dates.
4. **For "is $STATE a party to $TREATY"** open `signatures.en.txt`
   and look for the state's row. The presence of a `rat/acc=` date
   means yes; only `sig=` means signed-but-not-ratified. A
   `denounced=` date means the state has left the treaty.
5. **Some treaties have no Explanatory Report** (mostly the older
   ETS conventions). `report` will print a warning and exit
   gracefully — don't treat that as a failure.
6. **Languages.** The `--lang` flag accepts `en|fr|de|it|ru`. Most
   CoE PDFs are published EN+FR; some conventions also have DE/IT/RU
   versions, which are usually *non-official* translations and are
   sometimes served as HTML pages rather than PDFs (the CLI handles
   both and reports `"format": "pdf"` or `"html"`). If the requested
   language does not exist the CLI says so on stderr, falls back to
   English and names the files `*.en.*` — so a `text.de.txt` never
   silently contains English. Only EN and FR are authentic texts;
   quote those for anything that turns on wording.

## Citation

Always cite the Treaty Office source URL. The CLI writes
`source_url` into every JSON output. Format:

> *Council of Europe Treaty Office, [Title], CETS No. [number]*
> *Treaty status as of [today]: [signatures-source-url]*
> *Reservations and Declarations: [declarations-source-url]*

Per-document URL templates (the CLI fills these in):

```
Detail page:   https://www.coe.int/en/web/conventions/full-list?module=treaty-detail&treatynum=NNN
Signatures:    https://www.coe.int/en/web/conventions/full-list?module=signatures-by-treaty&treatynum=NNN
Declarations:  https://www.coe.int/en/web/conventions/full-list?module=declarations-by-treaty&numSte=NNN
Treaty PDF:    https://rm.coe.int/<hash>     (recorded in meta.json as Lien_pdf_traite_ENG)
```

## Extending later

The skill is intentionally modular so future capabilities slot in as
new subcommands without touching what works:

- `parties <ref> [--state X]` — structured parties query against the
  cached signatures JSON
- `compare <ref> <state-a> <state-b>` — side-by-side reservation
  comparison (CoE has a "compare declarations" page)
- `partial-agreement <num>` — partial-agreements (EUR-OPA, GRECO
  statute) at `api/AccordPartiel/GetAP`
- `recent --since YYYY-MM-DD` — newly registered acts via
  `api/actestraites/getRecent`

Add these by extending `scripts/coe.py`.
