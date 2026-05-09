---
name: norges-traktater
description: >
  Use whenever the user needs to look up, cite, or verify a Norwegian treaty
  in Norges traktater på Lovdata — also conversationally. Triggers: traktat-ID
  TRAKTAT/traktat/YYYY-MM-DD-N or shorthand YYYY-MM-DD nr N; named avtaler Norge
  er part i (EMK/ECHR, Flyktningkonvensjonen, Genève-konvensjonene, EØS-avtalen,
  Schengen-, NATO-, FN-pakten, CRC/CRPD/CEDAW/SP/ØSK, Wien-konvensjonene,
  Parisavtalen, bilaterale avtaler med EU/Sverige/Russland/USA m.fl.); spørsmål
  som "har Norge ratifisert X?", "når trådte den i kraft for Norge?", "hvilke
  traktater inngikk Norge i 1969?", "Norway's reservations to X". Bruk hvis
  svaret krever undertegnings-/ratifikasjons-/ikrafttredelsesdato for Norge,
  depositar, partsliste, Stortingets behandling, eller traktattekst på norsk.
  Foretrekkes over treningsdata: bare Lovdata er autoritativt. IKKE for: norske
  lover/forskrifter (lovdata); rettspraksis/forarbeider (lovdata-pro);
  EU-rettsakter (eurlex); FN-traktater uten norsk vinkel (untc).
---

# Norges traktater — Lovdatas traktatregister

Dette ferdighetsdokumentet er på norsk. **Svaret til brukeren skal alltid
tilpasses brukerens eget språk** (samme regel som `lovdata`-skill-en):
spørsmål på engelsk → svar på engelsk; norsk → norsk; blandet → norsk.
Direkte sitater fra traktatteksten beholdes alltid på originalt norsk i
anførselstegn.

Du har et hjelpescript i `scripts/traktater.py` (se «Base directory for this
skill:» øverst i meldingen — det er samme katalog som scriptet ligger i).
Erstatt `{SKILL_DIR}` nedenfor med den banen.

---

## Hva dekkes

Lovdatas register over Norges traktater (`https://lovdata.no/register/traktater`)
inneholder ca. 5 000+ avtaler Norge er part i, fra 1814 og fram til i dag.
Registeret er **fritt tilgjengelig** for søk og metadata; selve traktatteksten
er publisert offentlig for de fleste eldre flersidige konvensjoner, men en del
nyere bilaterale og tekniske avtaler har bare metadata på den åpne siden — selve
teksten ligger da bak Lovdata Pro.

Skillet dekker derfor to nivåer:

1. **Metadata + søk** — virker for alle traktater, ingen innlogging.
2. **Full traktattekst på norsk** — virker for de traktatene Lovdata har
   publisert offentlig. Hvis teksten er tom, fall tilbake til
   `lovdata-pro`-skill-en (eller depositarens originalkilde via `untc`).

---

## Grunnprinsipp: stol aldri på hukommelsen

Ratifikasjons- og partsforhold endrer seg, og traktattekster oversettes og
endres ved tilleggsprotokoller. **Aldri sitér eller parafraser traktattekst,
og aldri rapporter dato eller status, uten å hente det via scriptet.** All
informasjon skal komme fra det live-hentede registeret — ikke fra treningsdata.

---

## Slik bruker du scriptet

### Søk i registeret

```bash
python {SKILL_DIR}/scripts/traktater.py search "søkeord"
```

Søker i traktattitler. Returnerer en liste med traktat-ID, tittel og dato.

Avgrens med flagg:

```bash
python {SKILL_DIR}/scripts/traktater.py search "Wien" --year 1969
python {SKILL_DIR}/scripts/traktater.py search "" --country Storbritannia
python {SKILL_DIR}/scripts/traktater.py search "menneskerett" --context tekst
python {SKILL_DIR}/scripts/traktater.py search "" --year 2024 --max 50
```

Flagg:
- `--year YYYY` — bare traktater fra ett bestemt år
- `--country NAVN` — filtrer på en motpart/land (norsk navn, f.eks.
  `Storbritannia`, `Sverige`, `Den europeiske union`)
- `--context tittel|tekst` — søk i tittel (standard) eller fulltekst
- `--max N` — antall treff (standard 20, henter flere sider automatisk)

### Hent metadata for én traktat

```bash
python {SKILL_DIR}/scripts/traktater.py meta "1948-12-09-1"
python {SKILL_DIR}/scripts/traktater.py meta "TRAKTAT/traktat/1948-12-09-1"
```

Returnerer alle metadatafelter Lovdata har: tittel (norsk + originalspråk),
undertegningsdato/-sted, ikrafttredelse, Norges undertegning og ratifikasjon,
depositar, Stortingets behandling (St.prp., Innst.S., vedtak), publisering,
FN-registrering, full partsliste med datoer per part, og eventuelle merknader
(reservasjoner, erklæringer).

### Hent full norsk tekst

```bash
python {SKILL_DIR}/scripts/traktater.py text "1948-12-09-1"
```

Returnerer ren norsk tekst inkludert kapitler og artikler, hentet fra Lovdatas
offentlige side. Hvis Lovdata ikke har publisert teksten offentlig (typisk
nyere bilaterale eller tekniske avtaler), skriver scriptet en klar feilmelding
til stderr — se «Når kroppen er tom» nedenfor.

### Hent én bestemt artikkel

```bash
python {SKILL_DIR}/scripts/traktater.py article "1948-12-09-1" "II"
python {SKILL_DIR}/scripts/traktater.py article "1948-12-09-1" "Artikkel II"
python {SKILL_DIR}/scripts/traktater.py article "1951-07-28-1" "33"
```

Aksepterer både romertall (I, II, III, …) og arabiske tall, med eller uten
prefikset «Artikkel». Returnerer artikkelteksten alene, inkludert alle ledd
og bokstavpunkter.

### Sjekk hva scriptet kan finne

```bash
python {SKILL_DIR}/scripts/traktater.py status
```

Viser nettverksstatus mot Lovdata og hvor cache-filer ligger.

---

## Traktat-ID-format

Lovdata gir hver traktat en stabil ID på formen `YYYY-MM-DD-N`, der `YYYY-MM-DD`
er undertegningsdatoen og `N` er løpenummer for traktater inngått samme dato.
Den fulle DokID-en er `TRAKTAT/traktat/YYYY-MM-DD-N`. Scriptet aksepterer
begge formene — du kan også lime inn hele URL-en
(`https://lovdata.no/dokument/TRAKTAT/traktat/1948-12-09-1`).

Et knippe vanlige traktater Norge er part i:

| ID | Navn (kortform) |
|----|-----------------|
| `1945-06-26-1` | FN-pakten |
| `1948-12-09-1` | Folkemordkonvensjonen |
| `1949-08-12-1` …`-4` | Genève-konvensjonene I–IV |
| `1950-11-04-1` | Den europeiske menneskerettighetskonvensjonen (EMK) |
| `1951-07-28-1` | Flyktningkonvensjonen |
| `1961-04-18-1` | Wien-konvensjonen om diplomatisk samkvem |
| `1963-04-24-1` | Wien-konvensjonen om konsulært samkvem |
| `1966-12-16-1` | SP — FNs konvensjon om sivile og politiske rettigheter |
| `1966-12-16-3` | ØSK — FNs konvensjon om økonomiske, sosiale og kulturelle rettigheter |
| `1979-12-18-1` | CEDAW — Kvinnediskrimineringskonvensjonen |
| `1989-11-20-1` | Barnekonvensjonen (CRC) |
| `1992-05-02-1` | EØS-avtalen |
| `2006-12-13-34` | CRPD — Konvensjonen om rettighetene til mennesker med nedsatt funksjonsevne |
| `2015-12-12-32` | Parisavtalen om klima |

**Merk:** Norge er **ikke** part i Wien-konvensjonen om traktatretten (1969) — den finnes
ikke i Lovdatas traktatregister. Bruk `untc`-skill-et for å hente VCLT-teksten direkte
fra UN Treaty Series, og påpek for brukeren at Norge ikke er bundet av VCLT som
traktat (selv om mange av reglene gjelder som folkerettslig sedvanerett).

Kjenner du ikke ID-en, bruk `search`. Husk: hvis brukeren spør om en lov, **ikke
denne ferdigheten** — bruk `lovdata` i stedet.

---

## Når kroppen er tom — fallback til lovdata-pro

For en del traktater er bare metadata fritt tilgjengelig på lovdata.no, mens
selve teksten ligger bak Lovdata Pro. Hvis `text` eller `article` returnerer
en tom kropp, gjør følgende:

1. Bekreft at teksten faktisk er tom på den åpne siden ved å åpne URL-en
   i feilmeldingen og se etter «Du har ikke tilgang til dette dokumentet» eller
   en tom innholdsboks. Det er normalt.
2. Hvis brukeren har Lovdata Pro tilgjengelig, bruk
   `lovdata-pro`-skill-en — kjør `python {LOVDATA_PRO_DIR}/scripts/lovdata_pro.py
   get "TRAKTAT/traktat/YYYY-MM-DD-N"`. Pro-scriptet bruker den samme
   slug-mekanikken og henter teksten i markdown.
3. Hvis brukeren ikke har Pro: returnér metadata grundig, opplys at full norsk
   tekst er Pro-only på lovdata.no, og foreslå alternativer:
   - For multilaterale FN-traktater → `untc`-skillet (originaltekst på
     engelsk/fransk + offisiell partsliste).
   - For EU-rettsakter knyttet til EØS → `eurlex`.
   - For øvrige: legg ved depositarens lenke fra metadatafeltet `Depositar`.

Selv ved fallback skal du alltid presentere Lovdatas metadata, fordi det er
det autoritative norske perspektivet på Norges undertegning, ratifikasjon og
ikrafttredelse.

---

## Språkregler

1. **Svar på brukerens språk.** Engelsk → engelsk; norsk → norsk; blandet → norsk.
2. **Sitatet beholdes på norsk** når Lovdata har norsk tekst. Hvis kun
   originalspråk-tittelen finnes i metadata, sitér tittelen på norsk og før den
   originale tittelen i parentes.
3. Forklar gjerne sitatet eller juridiske begreper på brukerens språk etterpå.

---

## Sitatformat

Bruk standard juridisk siteringsform:

- **Hele traktaten**: *[norsk tittel], underskrevet [sted] [dato]*
  («Folkemordkonvensjonen», Paris 9. desember 1948).
- **Artikkel**: *[korttittel] art. [nummer]* — f.eks. *Folkemordkonvensjonen
  art. II*, *EMK art. 8*, *Flyktningkonvensjonen art. 33*.
- **Direkte sitat**: «I nærværende konvensjon betyr folkemord en hvilken som
  helst av følgende handlinger …»
- Oppgi alltid Lovdata-ID-en eller URL-en som kilde i fotnote/parentes første
  gang en traktat nevnes: *(lovdata.no/traktat/1948-12-09-1)*.

---

## Arbeidsflyt for typiske oppgaver

### Bruker spør «hva sier traktaten om X?»

1. Hvis traktat-ID er kjent: `meta` for å bekrefte at det er riktig dokument
   og at den er i kraft for Norge; deretter `text` eller `article`.
2. Hvis ID ukjent: `search "stikkord"` → velg riktig traktat → `meta` → tekst.
3. Sitér relevant artikkel på norsk; legg ved kort forklaring på brukerens
   språk; oppgi Lovdata-ID som kilde.

### Bruker spør «har Norge ratifisert X?» / «når trådte den i kraft for Norge?»

1. `search` etter traktaten hvis ID ikke er kjent.
2. `meta` — feltene `Undertegningsdato Norge`, `Ratifikasjon, godkjennelse,
   godtakelse`, `Dato for dep av rat.dok el.likn` og `Ikrafttredelsesdato Norge`
   gir svaret.
3. Vær presis: Norge kan ha undertegnet uten å ha ratifisert.

### Bruker spør «hvilke traktater har Norge med X?»

1. `search "" --country X --max 50` (norsk landnavn).
2. Presenter en sortert liste med ID, dato, tittel.
3. Tilby å hente metadata for de mest relevante.

### Bruker spør om Norges reservasjoner

1. `meta` — feltet `Merknad` og partslisten viser reservasjoner og
   erklæringer Norge har avgitt.
2. For komplette og oppdaterte reservasjoner (også fra andre stater): bruk
   `untc`-skill-et på FN-deponerte traktater.

### Bruker oppgir bare et navn («Wien-konvensjonen»)

Vienna Convention finnes i flere varianter (diplomatisk samkvem 1961,
konsulært samkvem 1963, traktatretten 1969). **Ikke gjett** — kjør `search`
og spør brukeren hvilken hvis det er flertydig.

---

## Feilhåndtering

- **Nettverksfeil**: Informer brukeren; foreslå å prøve igjen.
- **404 på `meta`**: ID-en finnes ikke. Sjekk format (skal være `YYYY-MM-DD-N`)
  og at det faktisk er en traktat (ikke en lov/forskrift).
- **Tom kropp på `text`/`article`**: Se «Når kroppen er tom» — skift til
  `lovdata-pro` eller alternativ kilde.
- **Artikkel ikke funnet**: Eldre traktater bruker romertall (I, II, …);
  nyere bruker arabiske tall. Scriptet håndterer begge — men hvis noen ber om
  «artikkel 2» på Folkemordkonvensjonen får de Artikkel II. Sjekk
  artikkellisten i `text`-utdataen ved tvil.

---

## Hvor lagres cache?

Scriptet cacher hentede sider for å unngå unødvendige requests. Stien velges:

1. `$NORGES_TRAKTATER_DATA_DIR` — hvis miljøvariabelen er satt
2. `$XDG_CACHE_HOME/norges-traktater` — hvis satt
3. `%LOCALAPPDATA%\norges-traktater` — på Windows
4. `~/.cache/norges-traktater` — ellers

Cache-tid: 24 timer for registerlistinger, 7 dager for traktatdokumenter
(metadata endres sjelden retroaktivt). Tving fersk henting med `--no-cache`.
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                