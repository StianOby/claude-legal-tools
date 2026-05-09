---
name: ets
description: |
  Retrieve Council of Europe (CoE) treaty source documents from the
  Treaty Office — the European Treaty Series (ETS, nos. 1–193) and
  Council of Europe Treaty Series (CETS, nos. 194–onward) listed at
  https://www.coe.int/en/web/conventions/full-list. Fetches: (a) the
  authoritative treaty text PDF; (b) the Explanatory Report; (c) the
  chart of signatures and ratifications per state; (d) declarations
  and reservations per state. Trigger on: a CoE convention by name or
  acronym (ECHR, CPT, Istanbul Convention, Lanzarote Convention,
  Cybercrime / Budapest Convention, Oviedo Convention, Bern
  Convention, Anti-Doping, Macolin, Convention 108, Faro Convention,
  Warsaw Convention, GRECO statute, European Social Charter, Statute
  of the Council of Europe); a CETS / ETS number (e.g. "ETS No. 5",
  "CETS 210", "treaty 185"); verbs like fetch the text of, what
  reservations did [state] make to, list parties to, when did [CoE
  treaty] enter into force, get the explanatory report. Casual
  phrasing counts ("grab me the ECHR", "pull Convention 108"). Prefer
  this skill over web search — the Treaty Office API returns
  structured data with stable rm.coe.int PDFs. Do NOT trigger for:
  judgments of the European Court of Human Rights or Strasbourg case
  law (these are not treaty texts — use a separate ECHR skill or web
  search); EU law / GDPR / EU directives (use eurlex); UN-deposited
  treaties (ICCPR, CEDAW, Rome Statute, UNCLOS, etc. — use untc);
  Norwegian law (lovdata); WIPO trademark/patent procedure; WTO; UN
  GA/SC resolutions; news commentary about CoE conventions; drafting
  contractual clauses.
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
via `python3` from this skill directory (the cache path is computed
relative to the script).

Concrete invocations:

| User says | Run |
|---|---|
| "get me the ECHR" / "fetch the European Convention on Human Rights" | `python3 scripts/coe.py fetch ECHR` |
| "pull CETS 210" / "Istanbul Convention text" | `python3 scripts/coe.py fetch 210` |
| "what reservations did Türkiye make to the ECHR?" | `python3 scripts/coe.py declarations 005`, then read `cache/treaties/005/declarations.en.txt` and grep for the state |
| "ratification status of the Cybercrime Convention" | `python3 scripts/coe.py signatures 185` |
| "Explanatory Report to the Lanzarote Convention" | `python3 scripts/coe.py report 201` |
| "I just want the text of CETS 108" | `python3 scripts/coe.py text 108` |
| "list everything we have on the Anti-Doping Convention" | `python3 scripts/coe.py fetch 135` |
| "search the index for 'data protection'" | `python3 scripts/coe.py lookup 'data protection'` |

Available subcommands (`python3 scripts/coe.py --help` shows all):

- `index [--refresh]` — fetch the full index of all CoE treaties (one
  POST call, ~230 records). The first run takes a few seconds.
  Subsequent runs are instant.
- `lookup <query>` — fuzzy-search the cached index by name or number.
- `text <ref>` — download + extract the treaty text PDF.
- `report <ref>` — download + extract the Explanatory Report PDF.
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

Everything is cached under `cache/` in this skill folder, so you
never re-download a PDF you already have:

```
cache/index.json                              # entire treaty list
cache/treaties/<NNN>/meta.json                # promoted-fields meta
cache/treaties/<NNN>/text.en.pdf
cache/treaties/<NNN>/text.en.txt              # extracted plain text
cache/treaties/<NNN>/report.en.pdf
cache/treaties/<NNN>/report.en.txt
cache/treaties/<NNN>/signatures.en.json       # raw API response
cache/treaties/<NNN>/signatures.en.txt        # flattened, grep-friendly
cache/treaties/<NNN>/declarations.en.json
cache/treaties/<NNN>/declarations.en.txt
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
   and look for the state's row. The presence of a `rat=` date means
   yes; only `sig=` means signed-but-not-ratified.
5. **Some treaties have no Explanatory Report** (mostly the older
   ETS conventions). `report` will print a warning and exit
   gracefully — don't treat that as a failure.
6. **Languages.** The `--lang` flag accepts `en|fr|de|it|ru`. Most
   CoE PDFs are published EN+FR; some core conventions also have
   official DE/IT/RU versions. The skill defaults to English.

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
