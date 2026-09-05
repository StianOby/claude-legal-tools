---
name: lovdata-pro
description: >
  Use this skill any time the user needs Norwegian case law (rettspraksis) or
  preparatory works (forarbeider) — the Pro-only material the free `lovdata`
  skill cannot reach. Requires the Claude Desktop built-in browser (Cowork).
  Triggers include any reference like HR-YYYY-N (Holship, Finanger), Rt.
  YYYY s. N, RG YYYY s. N, LB-/LA-/LE-/LF-/LG-/LH-YYYY-N (lagmannsrett),
  TR-YYYY-N (tingrett), Ot.prp. nr. N (YYYY-YY), Prop. N L (YYYY-YY), NOU
  YYYY:N, Innst. N L (YYYY-YY), Meld. St. N (YYYY-YY); also natural-language
  asks like "find the Holship judgment", "hva sa Høyesterett i Finanger I",
  "hent forarbeidene til mineralloven". Use this skill even when the user
  doesn't name Lovdata: if the answer requires the text of a Norwegian court
  decision or preparatory work, this is the right tool. Do NOT use for:
  looking up gjeldende lov/forskrift text (that's the free `lovdata` skill);
  finding a lawyer; general questions about Norwegian legal theory that
  don't need the actual document text.
---

# Lovdata Pro — rettspraksis og forarbeider

Dette ferdighetsdokumentet er på norsk. **Svaret til brukeren skal alltid
tilpasses brukerens eget språk** (samme regel som i `lovdata`-skill-en):
spørsmål på engelsk → svar på engelsk; norsk → norsk; blandet → norsk.
Sitater fra dommer og forarbeider beholdes alltid på originalt norsk.

Denne skill-en bruker Claude Desktops innebygde browser (Cowork-verktøyene
`mcp__Claude_Browser__*`) til å hente Lovdata Pro-dokumenter direkte i
brukerens innloggede sesjon. Den kjører **ikke** i Claude Code CLI.

Du har tilgang til to hjelpescript:

- `scripts/lovdata_ref.py` — rent Python, ingen nettverkstilgang. Oversetter
  en referanse til kandidat-Pro-stier. Kjøres via bash/terminal.
- `scripts/browser/lovdata_pro.js` — limes inn i browser-fanen via
  `javascript_tool`. Gjør selve hentingen, seksjoneringen og søket.

(se `Base directory for this skill:` i starten av konteksten din for stien —
erstatt `{SKILL_DIR}` nedenfor med den.)

For komplette URL-mønstre, samlingsforkortelser og slug-regler, se
`references/lovdata-pro-mapping.md`.

---

## Forutsetninger

Denne skill-en krever at Cowork-verktøyene (`mcp__Claude_Browser__*`, f.eks.
`preview_start`, `navigate`, `javascript_tool`) er tilgjengelige i
verktøylisten din. **Hvis de ikke er det** (for eksempel når du kjører som
Claude Code CLI): stopp og si til brukeren at denne skill-en bare virker i
Claude Desktop med Cowork aktivert.

---

## Steg 0 — sesjon (alltid først, hver ny samtale)

1. `tabs_context` — se om det allerede finnes en fane på `lovdata.no/pro`.
   Gjenbruk den om den finnes (cachen i `window.__lp` dør ved navigering, så
   ikke naviger denne fanen bort fra `https://lovdata.no/pro/` for annet enn
   søk — se Steg 3). Ellers: `preview_start {url: "https://lovdata.no/pro/"}`.
2. Hvis et verktøy rapporterer at siden ikke er godkjent ennå:
   `request_access {url: "https://lovdata.no/pro/", scope: "site"}` og prøv
   igjen.
3. Lim inn hele innholdet i `{SKILL_DIR}/scripts/browser/lovdata_pro.js` via
   `javascript_tool` (`action: "javascript_exec"`). Idempotent — trygt å lime
   inn flere ganger i samme fane.
4. Kjør `await __lp.isLoggedIn()`.
   - **Ikke innlogget** → si til brukeren: *"Logg inn på Lovdata Pro i
     browser-panelet (SSO/FEIDE går fint). Si fra når du er inne."* Vent på
     bekreftelse, kjør `isLoggedIn()` på nytt. **Skriv aldri inn
     brukernavn/passord selv, og be aldri brukeren oppgi dem til deg** —
     innlogging skjer utelukkende i browser-panelet.
   - **Innlogget** → gå videre. Fane-id-en er "sesjonshåndtaket" for resten
     av samtalen; gjenbruk samme fane til alt under.

Du kan slå sammen navigering + paste + `isLoggedIn()`-sjekk i én
`browser_batch`-kall for å spare tur-reprisetid.

---

## Steg 1 — oppslag av referanse

```bash
python {SKILL_DIR}/scripts/lovdata_ref.py resolve "<referanse>"
```

Eksempler:

```bash
python {SKILL_DIR}/scripts/lovdata_ref.py resolve "HR-2016-2554-P"
python {SKILL_DIR}/scripts/lovdata_ref.py resolve "Ot.prp. nr. 3 (1998-99)"
python {SKILL_DIR}/scripts/lovdata_ref.py resolve "NOU 2022:8"
```

Returnerer `{input, parsed, candidates}`. Bruk `--json-array` for å få bare
kandidatlisten (nyttig til å lime rett inn i `__lp.load([...])`):

```bash
python {SKILL_DIR}/scripts/lovdata_ref.py resolve "HR-2016-2554-P" --json-array
# ["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"]
```

Hvis `parsed:false` (typisk pre-2008 Rt.-dommer, RG-dommer, uvanlige
referanseformer): hopp til **Steg 3 — søk**.

---

## Steg 2 — hent dokument

```javascript
await __lp.load(["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"])
```

Returnerer `{path, title, metadata, totalChars, toc}` (eller en
`{error: ...}`-payload — se **Feilhåndtering**). Dokumentet caches i fanen på
`path`, så alle videre kall (`section`, `grep`, `page`) på samme `path` er
gratis (ingen ny nettforespørsel).

Velg videre strategi ut fra dokumenttype og størrelse:

- **Dommer** (vanligvis ≤ noen hundre KB): bruk `section(path, i)` for det
  aktuelle avsnittet/kapittelet, eller `page(path, 0)` én gang hvis hele
  dokumentet er lite nok (`totalChars` under ~45 000 tegn — `PAGE_SIZE`,
  satt fra spike 1s målte grense for hvor mye ett `javascript_tool`-svar
  tåler).
- **Forarbeider** (NOU, Prop., Innst. — ofte flere MB): vis `toc` til
  brukeren eller velg selv relevante kapitler ut fra tittel/spørsmål.
  `grep(path, "søkeord")` finner riktig kapittel raskt; `section(path, i)`
  henter det ut.
- **Dump-modus** — kun når brukeren ber om en full lokal kopi eller
  uttømmende gjennomgang: løkke over `page(path, offset)` til `next` er
  `null`, og skriv hver `text` til `outputs/<slug>.md` (bash `>>` mellom
  hvert kall). Si fra til brukeren på forhånd omtrent hvor mange kall det
  tar (`Math.ceil(totalChars / 45000)`).

**Skriv alltid det du skal sitere til fil først, og siter fra filen** — ikke
fra samtalens korttidsminne av et tidligere `javascript_tool`-svar.

Eksempler på JS-kall:

```javascript
await __lp.section("HRSIV/avgjorelse/hr-2016-2554-p", 3)
await __lp.grep("NOU/forarbeid/nou-2022-8", "urfolk", 600, 20)
await __lp.page("PROP/forarbeid/otprp-3-199899", 0)
```

---

## Steg 3 — søk

Brukes når `resolve` ga `parsed:false`, eller når et direkte slug-forsøk
feiler med `not_found`.

**Søket kan ikke gjøres med ett JS-kall.** Lovdata Pro-søket er en GWT-app;
verken å sette `input.value` + dispatche syntetiske hendelser, eller å sende
Enter (syntetisk eller ekte via `key`-verktøyet), trigger søkehandleren — kun
et ekte museklikk på søkeknappen fungerer (bekreftet empirisk). Gjør derfor:

1. Sørg for at fanen viser søkefeltet (`#quickSearchField-input`) — bruk en
   **egen** fane hvis den parkerte hoved-fanens `window.__lp.cache` må
   overleve.
2. Skriv inn søketeksten med `computer {action:"type"}` (ikke ved å sette
   `.value` fra JS).
3. Finn søkeknappen (🔍-ikonet ved siden av feltet, via `find` eller
   `read_page`) og klikk den med `computer {action:"left_click"}`. **Ikke**
   trykk Enter — det gjør ingenting.
4. Vent ~2 sekunder til resultatene rendres (hash endrer seg til noe sånt
   som `#result&id=<n>&q=<query>`).
5. Lim inn `lovdata_pro.js` i denne fanen hvis den ikke allerede er der, og
   les ut treffene:

   ```javascript
   await __lp.readSearchResults(10)
   ```

`readSearchResults()` tar ingen query — den leser bare
`a[href^="#document/"]`-ankere som allerede er rendret i DOM-en, fra
søket du nettopp utførte med klikket over.

Samme advarsler som før:

- **Pro-søk returnerer innholdstreff, ikke dokumenttreff.** Et søk på
  «St.prp. nr. 100 1991-92 EØS-avtalen» kan gi EU-direktiver fra
  EØS-vedlegget fordi fulltekstsøket slår på alle treff i
  dokumentkorpuset — ikke selve dokumentet.
- **Pre-2008 Rt.-slugs har et opakt suffiks** (`rt-YYYY-PAGENUMBER-SUFFIX`)
  som ikke kan gjettes deterministisk — søk er eneste pålitelige vei.
- **Verifiser alltid** at topptreffets `path` faktisk tilsvarer den
  etterspurte referansen før du siterer fra den — sjekk tittel/metadata via
  `load()` på treffet.
- For proposisjoner og forarbeider: prøv direkte slug-mønstre (Steg 1)
  **først**; bruk søk bare som siste utvei.

---

## Sitatformat

Bruk standard norsk juridisk siteringsform i svaret til brukeren:

- **Høyesterett (moderne)**: *HR-2016-2554-P avsnitt 77*
- **Rt.**: *Rt. 2000 s. 1811 (Finanger I) på s. 1827*
- **Lagmannsrett**: *LG-2008-135938*
- **Forarbeider**: *Ot.prp. nr. 3 (1998-99) s. 12* eller *NOU 2022: 8 punkt 3.4*

Sitater beholdes på originalt norsk, i anførselstegn («…» eller "…"). Legg
gjerne til oversettelse/forklaring på brukerens språk etter sitatet.

**Aldri parafraser fra hukommelsen.** Hent dokumentet via `__lp.load`/
`section`/`page` og siter fra det. Eldre dommer endres riktignok ikke — men
forarbeidsprosessen, saksopplysninger og henvisninger varierer mellom
referanseverk og Lovdatas egen tekst, og hallusinasjon av domspremisser har
høy kostnad.

---

## Arbeidsflyt for vanlige oppgaver

### Brukeren spør om hva en dom sier

1. Steg 0 (sesjon), Steg 1 (resolve), Steg 2 (`load` → `section`/`page`).
2. Finn relevante avsnitt, siter på norsk, forklar på brukerens språk.
3. Oppgi kilde inkludert avsnittsnummer/side hvor mulig.

### Brukeren spør om forarbeidene til en lov

Forarbeidene består typisk av tre dokumenter — alle bør hentes når brukeren
ber om «forarbeidene»:

1. **NOU** (utvalgsutredning) — `NOU YYYY:N`
2. **Prop. L / Ot.prp.** (departementets proposisjon) — `Prop. N L (YYYY-YY)`
   eller `Ot.prp. nr. N (YYYY-YY)`
3. **Innst.** (komitéinnstilling) — `Innst. N L (YYYY-YY)`

Disse er ofte 1-3 MB tekst hver. Bruk `toc` + `grep` + `section` for å finne
og hente det relevante kapittelet — ikke hele dokumentet via dump-modus, med
mindre brukeren eksplisitt ber om en full lokal kopi.

### Brukeren oppgir en uvanlig referanse (Rt., RG, eldre Ot.prp.)

For pre-2008 Rt.-dommer, RG-dommer og Ot.prp. fra før ~1968 finnes ingen
deterministisk slug-regel. `lovdata_ref.py resolve` gir `parsed:false` for
disse — gå til Steg 3 (søk) og **verifiser** treffet før du siterer.

**Pro-søk returnerer innholdstreff, ikke dokumenttreff** — se advarslene i
Steg 3.

Hvis topptreffet er feil: se gjennom flere av treffene fra
`readSearchResults()`, plukk riktig `path` manuelt, og kjør `load(path)` på
den. Hvis ingen treff er
riktige, fortell brukeren at dokumentet ikke ble funnet og be om mer presis
referanse.

---

## Feilhåndtering

Alle JS-funksjoner returnerer `{error: "<kode>", detail}` i stedet for å
kaste. Kodene:

- **`not_logged_in`** → be brukeren logge inn i browser-panelet (se Steg 0
  punkt 4). Ikke debugg videre — dette er alltid årsaken til en tom/uventet
  respons når du nettopp har startet en ny fane.
- **`collection_mismatch`** → skjer normalt ikke synlig for deg: `load()`
  prøver automatisk SIV/STR-motparten selv. Hvis begge feiler, rapporteres
  det som `not_found` med begge stiene i `detail`.
- **`not_found`** → sjekk referansen for skrivefeil; prøv Steg 3 (søk). Sjekk
  også dekningsterskler i `references/lovdata-pro-mapping.md`: lovrelaterte
  proposisjoner i fulltekst fra sesjon 1984/85, NOU-er i fulltekst fra 1994
  (1985–1993 varierer), Innstillinger fra sesjon 1991/92. Eldre NOU-er kan
  dukke opp under `PUBG`-samlingen, men har ofte bare metadata.
  Ikke-lovrelaterte proposisjoner (St.prp. etc.) er aldri fulltekst-indeksert.
- **`cors`** → du kjørte JS i en fane som ikke er på `lovdata.no`. Sjekk at
  fanen faktisk viser en `lovdata.no/pro`-side (Steg 0).
- **Siden er ikke godkjent / brukeren avslo tilgangsforespørselen** → fortell
  brukeren dette og stopp; ikke prøv å omgå det.

---

## Ytelsesnotat

Hvert `javascript_tool`-svar går gjennom verktøykanalen og inn i samtalen —
returner **aldri** mer enn `PAGE_SIZE` (se toppen av `lovdata_pro.js`) fra ett
JS-kall. Bruk `section`/`grep`/`page` istedenfor å be om hele
`__lp.cache[path].fullText` direkte. Foretrekk `browser_batch` når du skal
navigere + lime inn scriptet + sjekke innlogging i samme tur.

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
