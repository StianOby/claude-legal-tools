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
inneholdt **3 457 avtaler** da dette ble skrevet (september 2026), med årganger
fra **1661** til i dag. Kjør `status` for dagens tall — scriptet leser dem fra
registeret. Registeret er **fritt tilgjengelig** for søk og metadata; selve
traktatteksten er publisert offentlig for mange konvensjoner, men en god del
har bare metadata på den åpne siden.

Skillet dekker derfor to nivåer:

1. **Metadata + søk** — virker for alle traktater, ingen innlogging.
2. **Full traktattekst på norsk** — virker for de traktatene Lovdata har
   publisert offentlig. Er teksten tom, se «Når kroppen er tom» nedenfor;
   for de sentrale menneskerettskonvensjonene ligger teksten fritt et annet
   sted på lovdata.no, ikke bak Pro.

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

Søker i traktattitler. Returnerer en liste med traktat-ID og tittel, og til
slutt hvor mange treff søket ga totalt («Viser 20 av 269 treff»). **Si alltid
fra til brukeren når det er flere treff enn du viste** — ellers ser en liste
på 20 ut som om den er uttømmende.

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
  `Storbritannia`, `Sverige`, `Den europeiske union`). Les advarselen
  nedenfor om hva som *ikke* finnes i listen.
- `--context tittel|tekst` — søk i tittel (standard) eller fulltekst.
  Fulltekstsøk gir mange flere treff («menneskerett» gir 26 i tittel, 321 i
  tekst), men treffene er sortert **nyest først, ikke etter relevans**, så
  toppen av listen er ferske avtaler som tilfeldigvis nevner ordet. Bruk
  tittelsøk når du leter etter en bestemt traktat.
- `--max N` — antall treff (standard 20, henter flere sider automatisk)
- `--full` — bytt registerets forkortede titler mot dokumentenes egne.
  Lovdata kutter titler rundt 200 tegn i trefflisten, så dette koster ett
  dokumentoppslag per treff (cachet, og scriptet sier fra på stderr før det
  begynner). Bruk det når du bygger en liste; dropp det når du bare skal
  finne fram til én traktat.
- `--json` — maskinlesbart utdata, `{"total", "shown", "results": [{"id",
  "title", "year"}]}`. Da slipper du å parse tekstformatet.

`--country` og `--year` valideres mot registerets egne nedtrekkslister før
søket sendes. Det er med vilje: skriver du et land Lovdata ikke kjenner,
ignorerer nettstedet filteret og returnerer **hele registeret** — som ville
se ut som et ekte resultat. Scriptet stopper i stedet og foreslår nærmeste
treff. `python {SKILL_DIR}/scripts/traktater.py countries [søk]` lister de
216 gyldige landnavnene.

#### `--country` er en innsnevring, ikke en fullstendighetsgaranti

Nedtrekkslisten dekker ikke alle motparter som faktisk opptrer i registeret.
Kjør alltid `countries` før du stoler på et partsfilter:

```bash
python {SKILL_DIR}/scripts/traktater.py countries europ
# Den europeiske union
# Det europeiske økonomiske fellesskap
```

Det er alt EU-siden har. **«Det europeiske fellesskap» — motparten i praktisk
talt hele perioden 1993–2009 — har ingen egen post**, og det samme gjelder
Europol, Eurojust, Frontex og Euratom, som alle opptrer som motpart.

Konsekvensen er en felle: de to åpenbare EU-filtrene gir til sammen 98 treff
som *ser* uttømmende ut, men mangler blant annet EØS-avtalen selv
(`1992-05-02-1`), Dublin-avtalen (`2001-01-19-1`) og Eurojust-avtalen
(`2005-04-28-16`). En tidligere bruker av dette skillet bygde en masterliste
på den antakelsen og fikk 31 rader stående uten Lovdata-referanse.

Skal svaret være uttømmende, suppler derfor **alltid** partsfilteret med
tittelsøk på motpartens navn og på saksområdet — og si fra til brukeren at
partsfilteret alene ikke er uttømmende.

#### Søkestrategi: bruk norske juridiske termer

Søket matcher Lovdatas **norske tittelfelter** — både `Tittel (norsk)` og
`Korttittel (norsk)`. Engelske ord gir aldri treff. En forkortelse virker
nøyaktig når Lovdata har lagt den inn i ett av de to feltene, og ikke
ellers — og det går ikke an å gjette: `ECMWF` treffer fordi `1973-10-11-21`
har `Korttittel (norsk): ECMWF`, mens `COTIF` ikke treffer noe.

Praktisk rekkefølge: prøv forkortelsen først (ett kall), og gå over til det
norske faguttrykket hvis den gir null treff.

| Vil finne | Fungerer IKKE | Bruk i stedet |
|-----------|--------------|---------------|
| Haag-konvensjonen om foreldremyndighet (1996) | `"Haag 1996 barn"` | `"foreldremyndighet"` |
| ILO-konvensjoner generelt | `"ILO"` alene | `"ILO nr. 87"` e.l., eller faglig term |
| Overenskomsten om int. jernbanetransporter (COTIF) | `"COTIF"` | `"jernbanetransporter"` |
| EMK | `"ECHR"`, `"human rights"` | `"menneskerettighetskonvensjonen"` |
| Flyktningkonvensjonen | `"refugee"`, `"1951 Refugee"` | `"flyktning"` |
| Pan-Euro-Med-konvensjonen om opprinnelsesregler | `"Pan-Euro-Med"` | `"preferanseopprinnelsesregler"` |
| Energichartertraktaten | `"energichartertraktaten"` | `"energichartertraktat"` |
| Den internasjonale kornavtalen | `"kornhandel"` | `"kornavtalen"` |

Merk raden for energichartertraktaten: søket er ikke lemmatisert, så bestemt
form gir null treff når tittelen står i ubestemt form. Søk på den korteste
entydige ordstammen ved tvil.

Forkortelser som *virker*, fordi de står i tittel eller korttittel: `Frontex`,
`Europol`, `Schengen`, `ECMWF`. `COMETT` gir null treff fordi avtalen ikke
finnes i registeret i det hele tatt — se «Traktaten finnes ikke i registeret»
under Feilhåndtering.

**For ILO-konvensjoner** er det mest pålitelige å søke på konvensjonsnummeret
slik det står i den norske tittelen:

```bash
python {SKILL_DIR}/scripts/traktater.py search "ILO nr. 87"
python {SKILL_DIR}/scripts/traktater.py search "ILO nr. 98"
```

Søk på faglig innhold hvis nummeret er ukjent:

```bash
python {SKILL_DIR}/scripts/traktater.py search "tvangsarbeid"       # ILO 29/105
python {SKILL_DIR}/scripts/traktater.py search "kollektive forhandlinger"  # ILO 98/154
python {SKILL_DIR}/scripts/traktater.py search "diskriminering sysselsetting"  # ILO 111
python {SKILL_DIR}/scripts/traktater.py search "barnearbeid"         # ILO 182
```

Kjenner du Lovdata-ID-en fra tabellen nedenfor, hopp over søket og gå rett
til `meta` eller `text`.

### Hent metadata for én traktat

```bash
python {SKILL_DIR}/scripts/traktater.py meta "1948-12-09-1"
python {SKILL_DIR}/scripts/traktater.py meta "TRAKTAT/traktat/1948-12-09-1"
```

Returnerer alle metadatafelter Lovdata har for dokumentet: tittel (norsk +
originalspråk), undertegningsdato/-sted, ikrafttredelse, Norges undertegning
og ratifikasjon, depositar, Stortingets behandling (St.prp., Innst.S.,
vedtak), publisering, FN-registrering og eventuelle merknader.

Flagg:
- `--json` — hele metadatasettet som JSON: `{"id", "url", "title",
  "has_text", "metadata": {<norsk ledetekst>: <verdi>}, "fields":
  {<Lovdatas feltnavn>: <verdi>}}`. Bruk `fields` når du skal slå opp et
  bestemt felt programmatisk; `metadata` har ledetekstene slik Lovdata viser
  dem, i Lovdatas rekkefølge.
- `--batch FIL` — les IDer fra en fil, én per linje (`#` innleder kommentar,
  duplikater droppes, `-` leser fra stdin; URL-er og fulle DokID-er går
  også). Med `--json` kommer resultatet som én liste. Et oppslag som feiler
  stopper ikke resten: raden får en `error`-nøkkel i JSON, og feilen skrives
  til stderr.

```bash
python {SKILL_DIR}/scripts/traktater.py meta --batch ids.txt --json
```

Skal du bygge et register over mange traktater, er `search … --full --json`
pluss `meta --batch … --json` hele verktøykassen — ikke skriv en egen løkke
over `meta`.

Tre ting varierer fra traktat til traktat:

- **Partslisten.** For noen traktater (EØS-avtalen, nordiske avtaler) lister
  Lovdata alle parter med datoer. For mange multilaterale konvensjoner står
  bare Norge, med en merknad om at oppdatert partsforhold ligger hos
  depositaren — Folkemordkonvensjonen er et slikt tilfelle. Trenger brukeren
  den fulle partslisten for en FN-deponert traktat, bruk `untc`.
- **Feltutvalget.** Ulike dokumenttyper har ulike felter; scriptet leser
  ledeteksten fra Lovdatas egen tabell, så nye felter dukker opp automatisk
  med riktig norsk navn.
- **Bilateral/multilateral er ikke eget felt.** Det står sist i
  `Ident`-linjen (`Ident: 14-10-2003 nr 121 Bilateral`) og må plukkes ut
  derfra.

Har traktaten ingen fri tekst, sier `meta` fra om det på linjen «Tekst: ikke
publisert fritt på lovdata.no».

#### Ikrafttredelsesfeltene er fritekst, ikke datoer

Dette er den vanligste kilden til feil i maskinell bruk av registeret. Det
finnes to felter, og de opptrer i alle kombinasjoner — begge, bare det ene,
eller ingen:

| Felt | Betyr |
|------|-------|
| `Avtalens ikrafttredelsesdato` | når traktaten trådte i kraft mellom partene |
| `Ikrafttredelsesdato Norge` | når den trådte i kraft **for Norge** |

Verdiene er norsk fritekst, med datoer på formen `DD-MM-ÅÅÅÅ` der det faktisk
er en dato. Alle disse er påtruffet:

| Verdi | Traktat |
|-------|---------|
| `01-01-2011 midlertidig anvendelse, i kraft 01-05-2011` | `2010-07-28-40` |
| `Midlertidig anvendt fra 01-05-2004` | `2003-10-14-121` |
| `06-12-2005, Midlertidig anvendt fra 01-05-2004` | `2003-10-14-187` |
| `01-09-1995, med virkning fra 01-07-1995` | `1995-07-25-1` |
| `01-01-2010 mellom EU og Norge` | `2007-10-30-27` |
| `01-09-2007 (midlertidig), endelig i kraft 09-11-2011` | `2007-07-25-21` |

`Avtalens undertegningsdato` kan også ha flere verdier: Prüm-avtalen
(`2009-11-26-89`) har `26-11-2009, 30-11-2009`, fordi den ble undertegnet i
Stockholm og Brussel på ulike dager.

Og noen traktater har **ingen** ikrafttredelsesfelter i det hele tatt, men
har `Dato for dep av rat.dok el.likn` — typisk der Norge har tiltrådt en
avtale som allerede var i kraft:

```bash
python {SKILL_DIR}/scripts/traktater.py meta 2003-01-29-212   # ECURIE: deponert 09-04-2015, ingen ikrafttredelsesfelt
```

**Ikke reduser disse verdiene til «i kraft / ikke i kraft».** Gjengi feltet
slik det står, med forbeholdet det inneholder. Forskjellen mellom midlertidig
anvendelse og endelig ikrafttredelse er rettslig reell, og en avtale kan være
midlertidig anvendt i årevis før den trer i kraft (`2007-07-25-21`: fire år).
Er ikrafttredelse selve spørsmålet, sitér feltet ordrett og forklar det.

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
og bokstavpunkter. Bokstav- og nummerpunkter kommer på egne linjer med
markøren bevart («a. å drepe medlemmer av gruppen;»), slik at «artikkel II
bokstav a» kan siteres presist.

### Sjekk hva scriptet kan finne

```bash
python {SKILL_DIR}/scripts/traktater.py status
```

Viser nettverksstatus mot Lovdata, hvor cache-filene ligger, hvor mange
traktater registeret inneholder nå, hvilke årganger som finnes, og hvor mange
land nedtrekkslisten har. Klarer scriptet ikke å lese disse tallene, sier det
fra om at Lovdata kan ha endret markupen — da er det sannsynligvis
parse-reglene i `scripts/traktater.py` som må oppdateres.

---

## Traktat-ID-format

Lovdata gir hver traktat en stabil ID på formen `YYYY-MM-DD-N`, der
`YYYY-MM-DD` er undertegningsdatoen. Den fulle DokID-en er
`TRAKTAT/traktat/YYYY-MM-DD-N`. Scriptet aksepterer begge formene — du kan
også lime inn hele URL-en
(`https://lovdata.no/dokument/TRAKTAT/traktat/1948-12-09-1`).

### Hva `N` teller har endret seg underveis

| Periode | Hva `N` er |
|---------|------------|
| t.o.m. 1998 | løpenummer **innenfor datoen** — starter på 1 for hver ny undertegningsdato |
| 1999–2002 | blandet: de fleste er datobaserte, men årsbaserte numre begynner å dukke opp |
| f.o.m. 2003 | løpenummer **innenfor året** — uten sammenheng med datoen |

Fire traktater deler datoen 14. oktober 2003, og numrene deres er 70, 121,
124 og 187 — ikke 1–4:

```bash
python {SKILL_DIR}/scripts/traktater.py meta 2003-10-14-70    # Tilleggsprotokoll, EU-utvidelsen 2004
python {SKILL_DIR}/scripts/traktater.py meta 2003-10-14-121   # Norsk finansieringsordning 2004–2009
python {SKILL_DIR}/scripts/traktater.py meta 2003-10-14-124   # Visse landbruksvarer
python {SKILL_DIR}/scripts/traktater.py meta 2003-10-14-187   # EØS-utvidelsen, ti nye stater
```

Og `N` er **ikke unikt innenfor året heller**: både `2004-04-29-119` og
`2004-06-04-119` finnes. Bare hele ID-en identifiserer en traktat.

### Sitér alltid hele ID-en

**Forkort aldri til «ÅÅÅÅ nr N»** («2003 nr 121»). Den formen er tvetydig
for hele registeret, og for traktater f.o.m. 2003 kan datoen ikke engang
utledes av nummeret. En tidligere bruker av dette skillet forkortet slik i
den tro at nummeret var datobasert og at en datokolonne ved siden av gjorde
referansen entydig — og endte med seks ulike avtaler oppført under samme
referanse.

Lovdatas egen `Ident`-linje bruker formen `14-10-2003 nr 121`. Den er grei,
fordi den beholder hele datoen; det er året *uten* dato som ødelegger.

Et knippe vanlige traktater Norge er part i:

Alle ID-ene under er kontrollert mot lovdata.no (september 2026).
Kolonnen «Tekst» sier om den norske teksten ligger fritt på traktatsiden;
`meta` virker uansett.

**Sentrale menneskerettighets- og humanitærrettslige konvensjoner**

| ID | Navn (kortform) | Tekst |
|----|-----------------|-------|
| `1945-06-26-1` | FN-pakten | ja |
| `1948-12-09-1` | Folkemordkonvensjonen | ja |
| `1949-08-12-1` …`-4` | Genève-konvensjonene I–IV | ja |
| `1950-11-04-1` | Den europeiske menneskerettighetskonvensjonen (EMK) | nei → menneskerettsloven |
| `1951-07-28-1` | Flyktningkonvensjonen | ja |
| `1961-04-18-1` | Wien-konvensjonen om diplomatisk samkvem | ja |
| `1963-04-24-1` | Wien-konvensjonen om konsulært samkvem | ja |
| `1966-12-16-1` | SP — FNs konvensjon om sivile og politiske rettigheter | nei → menneskerettsloven |
| `1966-12-16-3` | ØSK — FNs konvensjon om økonomiske, sosiale og kulturelle rettigheter | nei → menneskerettsloven |
| `1979-12-18-1` | CEDAW — Kvinnediskrimineringskonvensjonen | nei → menneskerettsloven |
| `1989-11-20-1` | Barnekonvensjonen (CRC) | nei → menneskerettsloven |
| `1992-05-02-1` | EØS-avtalen | ja |
| `1996-10-19-26` | Haag-konvensjonen om foreldremyndighet og beskyttelse av barn (1996) | ja |
| `2006-12-13-34` | CRPD — Konvensjonen om rettighetene til mennesker med nedsatt funksjonsevne | ja (også i menneskerettsloven) |
| `2015-12-12-32` | Parisavtalen om klima | ja |

**ILO-kjernekonvensjoner** (søk: `"ILO nr. [X]"` eller faglig term)

| ID | ILO-nr. | Navn (kortform) | Norsk søketerm |
|----|---------|-----------------|----------------|
| `1930-06-28-1` | 29 | Tvangsarbeid | `tvangsarbeid` |
| `1948-07-09-1` | 87 | Foreningsfrihet og organisasjonsrett | `"foreningsfrihet"` |
| `1949-07-01-5` | 98 | Organisasjonsrett og kollektive forhandlinger | `"kollektive forhandlinger"` |
| `1951-06-29-1` | 100 | Lik lønn | `"lik lønn"` |
| `1957-06-25-1` | 105 | Avskaffelse av tvangsarbeid | `tvangsarbeid` |
| `1958-06-25-1` | 111 | Diskriminering i sysselsetting og yrke | `"diskriminering sysselsetting"` |
| `1973-06-26-1` | 138 | Minstealder for sysselsetting | `minstealder` |
| `1999-06-17-1` | 182 | Verste former for barnearbeid | `barnearbeid` |

**Internasjonal transportrett**

| ID | Navn (kortform) | Søketerm hvis ukjent | Tekst |
|----|-----------------|----------------------|-------|
| `1980-05-09-1` | COTIF — Overenskomst om de internasjonale jernbanetransporter | `jernbanetransporter` | nei |
| `1999-06-03-1` | Protokoll 1999 til COTIF (Vilnius-protokollen) | `jernbanetransporter` | nei |

**Merk:** Norge er **ikke** part i Wien-konvensjonen om traktatretten (1969) — den finnes
ikke i Lovdatas traktatregister. Bruk `untc`-skill-et for å hente VCLT-teksten direkte
fra UN Treaty Series, og påpek for brukeren at Norge ikke er bundet av VCLT som
traktat (selv om mange av reglene gjelder som folkerettslig sedvanerett).

Kjenner du ikke ID-en, bruk `search`. Husk: hvis brukeren spør om en lov, **ikke
denne ferdigheten** — bruk `lovdata` i stedet.

---

## Når kroppen er tom

En del traktater har bare metadata på den åpne traktatsiden. Det betyr
**ikke** at teksten er utilgjengelig — for de viktigste konvensjonene ligger
den fritt et annet sted. Gå fram i denne rekkefølgen:

### 1. Er traktaten inkorporert i menneskerettsloven?

Menneskerettsloven (`NL/lov/1999-05-21-30`) har den fulle teksten til seks
konvensjoner som vedlegg, på **både norsk og engelsk**, fritt tilgjengelig
via `lovdata-api`-skill-en. Dette gjelder nettopp de konvensjonene
traktatregisteret ikke har tekst for:

| Konvensjon | Norsk tekst | Engelsk tekst |
|------------|-------------|---------------|
| EMK med protokoller | `emkn` | `emke` |
| SP (sivile og politiske rettigheter) | `spn` | `spe` |
| ØSK (økonomiske, sosiale og kulturelle) | `oskn` | `oske` |
| Barnekonvensjonen (CRC) | `bkn` | `bke` |
| Kvinnekonvensjonen (CEDAW) | `kdkn` | `kdke` |
| CRPD | `crpdn` | `crpde` |

```bash
python {LOVDATA_API_SKILL_DIR}/scripts/lovdata.py get "NL/lov/1999-05-21-30" "emkn"
```

Scriptet sier fra om dette selv: når `text` feiler, skriver det ut de
lovdata.no-lenkene Lovdata oppgir i metadataene (for EMK peker feltet
«Original tekst» rett på menneskerettsloven) med ferdig `lovdata-api`-kommando.

**Merk om siteringen:** menneskerettsloven gjengir konvensjonsteksten slik
den er inkorporert i norsk rett. Det er riktig kilde for norsk rettsanvendelse,
men oppgi at teksten er hentet derfra, ikke fra traktatregisteret.

### 2. FN-deponerte traktater → `untc`

Gir originalteksten (engelsk/fransk) og den offisielle partslisten med
reservasjoner og innsigelser fra alle stater.

### 3. EØS/EU-rettsakter → `eurlex`

### 4. Lovdata Pro → `lovdata-pro`

Krever abonnement og Claude Desktop med Cowork. Dokumentet hentes med
`__lp.load("TRAKTAT/traktat/YYYY-MM-DD-N")`. Dette er siste utvei, ikke
første — punkt 1 dekker de mest etterspurte konvensjonene uten abonnement.

Uansett hvilken vei du går: presenter alltid Lovdatas metadata, fordi det er
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

1. `countries X` først — er motparten i det hele tatt i nedtrekkslisten?
2. `search "" --country X --max 50` (norsk landnavn). Legg til `--full` hvis
   listen skal presenteres med titler.
3. Suppler med tittelsøk på motpartens navn og eventuelle organer den
   opptrer gjennom (for EU: `"Det europeiske fellesskap"`, `Europol`,
   `Eurojust`, `Frontex`, `Euratom`) — se «`--country` er en innsnevring».
4. Presenter en sortert liste med hele ID-en, dato og tittel, og si fra om
   hvilke deler av svaret som kommer fra partsfilteret og hvilke fra
   tittelsøk.
5. Tilby `meta --batch` for de mest relevante.

### Bruker spør om Norges reservasjoner

1. `meta` — feltet `Merknad` og partslisten viser reservasjoner og
   erklæringer Norge har avgitt. Vær oppmerksom på at partslisten for mange
   multilaterale konvensjoner bare inneholder Norge.
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
  og at det faktisk er en traktat (ikke en lov/forskrift). Er formatet
  riktig, se neste punkt.
- **Traktaten finnes ikke i registeret**: Registeret inneholder det Norge er
  folkerettslig bundet av. Instrumenter Norge aldri ratifiserte
  (tiltredelsestraktaten av 1972, etter folkeavstemningen), og avtaler der
  Norge deltar via EØS/EFTA-siden uten å være selvstendig part, kan mangle
  helt selv om de ligger i EUs traktatdatabase. **Null treff er ikke
  nødvendigvis en oppslagsfeil**, men det er heller ikke bevis for at Norge
  ikke er bundet: si det som det er, og kryssjekk mot depositaren, `untc`
  eller `eurlex` før du konkluderer.
- **Tom kropp på `text`/`article`**: Se «Når kroppen er tom» — sjekk først om
  konvensjonen ligger i menneskerettsloven.
- **Ukjent land i `--country`**: Scriptet stopper med forslag til nærmeste
  navn. Bruk `countries` for hele listen. (Lovdata selv ville ha returnert
  hele registeret uten å si fra.)
- **Ukjent traktat-ID**: Scriptet skriver én linje til stderr og avslutter med
  status 1.
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
