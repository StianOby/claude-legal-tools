---
name: lovdata-pro
description: >
  Use this skill any time the user needs Norwegian case law (rettspraksis) or
  preparatory works (forarbeider) — the Pro-only material the free `lovdata`
  skill cannot reach. Triggers include any reference like HR-YYYY-N (Holship,
  Finanger), Rt. YYYY s. N, RG YYYY s. N, LB-/LA-/LE-/LF-/LG-/LH-YYYY-N
  (lagmannsrett), TR-YYYY-N (tingrett), Ot.prp. nr. N (YYYY-YY), Prop. N L
  (YYYY-YY), NOU YYYY:N, Innst. N L (YYYY-YY), Meld. St. N (YYYY-YY); also
  natural-language asks like "find the Holship judgment", "hva sa Høyesterett
  i Finanger I", "hent forarbeidene til mineralloven", "what does NOU 2022:8
  say", "show me the committee report for the new mineral act". Use this
  skill even when the user doesn't name Lovdata: if the answer requires the
  text of a Norwegian court decision or preparatory work, this is the right
  tool. Do NOT use for: looking up gjeldende lov/forskrift text (that's the
  free `lovdata` skill); finding a lawyer; general questions about Norwegian
  legal theory that don't need the actual document text.
---

# Lovdata Pro — rettspraksis og forarbeider

Dette ferdighetsdokumentet er på norsk. **Svaret til brukeren skal alltid
tilpasses brukerens eget språk** (samme regel som i `lovdata`-skill-en):
spørsmål på engelsk → svar på engelsk; norsk → norsk; blandet → norsk.
Sitater fra dommer og forarbeider beholdes alltid på originalt norsk.

Du har tilgang til Lovdata Pro via et hjelpescript i `scripts/lovdata_pro.py`
(se `Base directory for this skill:` i starten av dette dokumentet — det er
samme katalog som scriptet ligger i. Erstatt `{SKILL_DIR}` nedenfor med den
banen).

For komplette URL-mønstre, samlingsforkortelser og slug-regler, se
`references/lovdata-pro-mapping.md`.

---

## Forutsetninger (sjekk én gang)

1. **Python-pakker**: `playwright`, `beautifulsoup4`, `html2text`. Hvis
   scriptet feiler med `missing python package`, kjør:

   ```bash
   pip install playwright beautifulsoup4 html2text
   python -m playwright install chromium
   ```

2. **Playwright MCP** må være installert i Claude. Det brukes når du må
   utforske ukjente dokumenttyper interaktivt (se «Når slug ikke virker»
   nederst). Hvis MCP-en ikke er tilgjengelig, **stopp og be brukeren
   installere den** før du fortsetter:
   <https://github.com/microsoft/playwright-mcp>

3. **Innlogging**: scriptet logger seg ikke inn med passord. Første gang må
   brukeren logge inn manuelt i et ekte browser-vindu (SSO/FEIDE støttes
   automatisk). Kjør:

   ```bash
   python {SKILL_DIR}/scripts/lovdata_pro.py login
   ```

   Et browser-vindu åpnes på `https://lovdata.no/pro/`. Brukeren fullfører
   innlogging; scriptet venter, oppdager `#myPage`/«Min side»-tilstanden, og
   lagrer `storage_state.json` til en skrivbar brukerkatalog. Sjekk status
   med `python {SKILL_DIR}/scripts/lovdata_pro.py status`.

   Brukeren trenger bare logge inn på nytt når sesjonen utløper (typisk hver
   par uker — Lovdata Pro har ganske lange sesjoner).

---

## Slik bruker du scriptet

### Hent et dokument (vanligste tilfelle)

```bash
python {SKILL_DIR}/scripts/lovdata_pro.py get "HR-2016-2554-P"
python {SKILL_DIR}/scripts/lovdata_pro.py get "Ot.prp. nr. 3 (1998-99)"
python {SKILL_DIR}/scripts/lovdata_pro.py get "NOU 2022:8"
python {SKILL_DIR}/scripts/lovdata_pro.py get "Innst. 521 L (2024-2025)"
```

Standard utdata er **markdown** til stdout — tett opp til Lovdatas egen
HTML-struktur, men uten verktøylinjer og delings-ikoner. Andre formater:

```bash
python {SKILL_DIR}/scripts/lovdata_pro.py get "HR-2016-2554-P" --format json
python {SKILL_DIR}/scripts/lovdata_pro.py get "HR-2016-2554-P" --format html
python {SKILL_DIR}/scripts/lovdata_pro.py get "HR-2016-2554-P" --format pdf -o holship.pdf
```

`--format json` returnerer `{title, metadata, markdown}` — nyttig når du
trenger metadata (Dato, Utgiver, Stikkord, Henvisninger) som strukturerte
felter.

For store dokumenter (NOU, Prop. — typisk flere MB markdown), **bruk
`-o fil.md`** og les filen tilbake i biter. Ikke skriv hele NOU-en til
stdout og les den inn som én streng.

### Slå opp en referanse uten å hente (debug)

```bash
python {SKILL_DIR}/scripts/lovdata_pro.py resolve "HR-2016-2554-P"
# → kandidater: HRSIV/avgjorelse/hr-2016-2554-p (alt: HRSTR/...)

python {SKILL_DIR}/scripts/lovdata_pro.py resolve "Rt. 2000 s. 1811"
# → ingen direkte slug; kjører søk og returnerer topp-treff
```

### Søk fritekst i Pro

```bash
python {SKILL_DIR}/scripts/lovdata_pro.py search "Holship boikott EØS"
python {SKILL_DIR}/scripts/lovdata_pro.py search "presumsjonsprinsippet" -n 20
```

Returnerer JSON-liste med `path` (`<COL>/<TYPE>/<SLUG>`) og `rowNumber`. Mat
en path videre inn i `get`:

```bash
python {SKILL_DIR}/scripts/lovdata_pro.py get "HRSIV/avgjorelse/hr-2016-2554-p"
```

---

## Sitatformat

Bruk standard norsk juridisk siteringsform i svaret til brukeren:

- **Høyesterett (moderne)**: *HR-2016-2554-P avsnitt 77*
- **Rt.**: *Rt. 2000 s. 1811 (Finanger I) på s. 1827*
- **Lagmannsrett**: *LG-2008-135938*
- **Forarbeider**: *Ot.prp. nr. 3 (1998-99) s. 12* eller *NOU 2022: 8 punkt 3.4*

Sitater beholdes på originalt norsk, i anførselstegn («…» eller "…"). Legg
gjerne til oversettelse/forklaring på brukerens språk etter sitatet.

**Aldri parafraser fra hukommelsen.** Hent dokumentet via scriptet og siter
fra det. Eldre dommer endres riktignok ikke — men forarbeidsprosessen,
saksopplysninger og henvisninger varierer mellom referanseverk og Lovdatas
egen tekst, og hallusinasjon av domspremisser har høy kostnad.

---

## Arbeidsflyt for vanlige oppgaver

### Brukeren spør om hva en dom sier

1. Sjekk at sesjonen er gyldig: `... status` (om du nettopp har kjørt en
   annen Lovdata Pro-kommando, hopp over).
2. `... get "<referanse>" -o /tmp/dom.md` (eller `--format json` hvis du
   trenger Stikkord/Henvisninger).
3. Les filen, finn relevante avsnitt, siter på norsk, forklar på brukerens
   språk.
4. Oppgi kilde inkludert avsnittsnummer/side hvor mulig.

### Brukeren spør om forarbeidene til en lov

Forarbeidene består typisk av tre dokumenter — alle bør hentes når brukeren
ber om «forarbeidene»:

1. **NOU** (utvalgsutredning) — `NOU YYYY:N`
2. **Prop. L / Ot.prp.** (departementets proposisjon) — `Prop. N L (YYYY-YY)`
   eller `Ot.prp. nr. N (YYYY-YY)`
3. **Innst.** (komitéinnstilling) — `Innst. N L (YYYY-YY)`

Disse er ofte 1-3 MB markdown hver. Hent én om gangen til fil, og les inn
det relevante kapittelet — ikke hele dokumentet, hvis brukeren har avgrenset
spørsmålet til ett tema.

### Brukeren oppgir en uvanlig referanse (Rt., RG, eldre Ot.prp.)

For pre-2008 Rt.-dommer, RG-dommer og Ot.prp. fra før ~1968 har ikke
scriptet en deterministisk slug-regel. Det faller automatisk tilbake til
Pro-søk og bruker første treff. **Verifiser** at treffets path passer
referansen før du siterer — et fritekst-søk på «Rt. 2000 s. 1811» finner
ofte saker som *siterer* dommen, ikke selve Finanger I.

Hvis topp-treffet er feil:

1. Kjør `... search "<referansen>"` og se gjennom topp-N.
2. Plukk riktig path manuelt og kjør `... get "<COL>/<TYPE>/<SLUG>"`.
3. Hvis ingen av treffene er riktig, hopp til neste seksjon.

### Når slug ikke virker

For ukjente dokumenttyper eller når både direkte slug og Pro-søk feiler,
bruk Playwright MCP-en til å utforske manuelt:

1. `mcp__playwright__browser_navigate` → `https://lovdata.no/pro/#search`
2. Skriv referansen i Hurtigsøk (`#quickSearchField-input`) og trykk Enter.
3. Les `a[href^="#document/"]`-anker fra resultatlisten — det første matchende
   gir kanonisk `<COLLECTION>/<TYPE>/<SLUG>`.
4. Hent dokumentet med `... get "<COL>/<TYPE>/<SLUG>"`.
5. Hvis du fant et nytt mønster (ny samlingsforkortelse, ny slug-regel),
   oppdater `references/lovdata-pro-mapping.md` slik at neste gang går
   automatisk.

Browseren krever innlogging — bruk samme `storage_state.json` som scriptet
ved å sette `LOVDATA_PRO_DATA_DIR` eller passe på at MCP-instansen kjører
mot samme bruker-context.

---

## Hvor lagres state?

Scriptets sesjonsfil ligger i en skrivbar brukerkatalog, valgt i denne
rekkefølgen:

1. `$LOVDATA_PRO_DATA_DIR` — hvis miljøvariabelen er satt
2. `$XDG_CACHE_HOME/lovdata-pro` — hvis satt
3. `%LOCALAPPDATA%\lovdata-pro` — på Windows
4. `~/.cache/lovdata-pro` — ellers

Kjør `... status` for faktisk sti.

**Innloggingsinformasjon (e-post/passord) lagres aldri.** Bare
session-cookies fra browseren — som er HttpOnly og kun gyldige mot Lovdata.
Hvis brukeren vil rive ned sesjonen, slett `storage_state.json`.

---

## Feilhåndtering

- **`error: not logged in`** → kjør `... login`.
- **`error: saved session expired`** → kjør `... login` på nytt.
- **`error: no document found`** → sjekk referansen for skrivefeil; prøv
  `... search "..."` for å finne riktig path.
- **`missing python package`** → installer pakkene som beskrevet i
  Forutsetninger.
- **Tom eller suspekt kort markdown** (under ~2 KB) → URL-en er gyldig
  syntaktisk men slug-en peker ikke til et reelt dokument. Scriptet skal
  fange dette via størrelse-sentinell, men hvis du ser det i utdataen,
  faller du tilbake til søk.

---

## Norsk-terminologiske notater

- *Rettspraksis* / *rettsavgjørelse* / *dom* — court decisions
- *Forarbeider* — preparatory works (collective term)
- *NOU* (Norges offentlige utredninger) — committee report
- *Ot.prp.* (Odelstingsproposisjon, brukt før 2009) — government bill
- *Prop. L* (Lovproposisjon, fra 2009) — government bill
- *Innst.* (Innstilling) — parliamentary committee recommendation
- *Stikkord* — keywords/index terms (Lovdata-metadata)
- *Henvisninger* — cross-references
- *Avsnitt* — paragraph (when citing modern Supreme Court, "avsnitt N" is
  the canonical paragraph reference)
