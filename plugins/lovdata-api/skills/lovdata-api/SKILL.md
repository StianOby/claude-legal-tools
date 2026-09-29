---
name: lovdata-api
description: >
  Use this skill any time the user needs to look up, cite, or verify Norwegian law —
  even for conversational questions. Covers: what a Norwegian lov or forskrift says on
  any topic (employment, criminal, administrative, family, health, tax, etc.); exact
  text of a paragraph or provision; recent amendments; rights or duties under Norwegian
  law; explaining Norwegian legal concepts using actual statute text; working with
  Norwegian legal documents. Trigger even for natural-language questions like "kan
  arbeidsgiver nekte meg å jobbe deltid?", "what does norwegian law say about X?",
  "hva sier loven om Y?" — if answering requires current statute text, use this skill.
  Prefer this over training-data recall: legislation changes and only Lovdata guarantees
  the current wording. Do NOT use for: finding a lawyer, summarising non-legislative
  documents, or legal theory with no need for actual statute text.
---

# Lovdata — Norsk lovdatabase (API)

Dette ferdighetsdokumentet er på norsk, men **svaret til brukeren skal alltid
tilpasses brukerens eget språk** (se Språkregler nedenfor).

Du har tilgang til Lovdatas offisielle datapakker via et hjelpescript i
`scripts/lovdata.py` (se Ferdighetskatalogens base dir). Merk: legg merke til
"Base directory for this skill:" i starten av dette dokumentet — det er samme
katalog som `scripts/lovdata.py` ligger i.

---

## Innhold — hva dekkes

Frie datapakker (ingen API-nøkkel nødvendig):
- **NL** — Gjeldende norske lover (ca. 760 XML-filer, daglig oppdatert)
- **SF** — Gjeldende sentrale forskrifter (over 5000 XML-filer, daglig oppdatert)

Lokale forskrifter (LF) er ikke inkludert i de frie pakkene.

---

## Grunnprinsipp: stol aldri på hukommelsen

Norsk lovtekst endres jevnlig. **Aldri siter eller parafraserer lovtekst uten å
hente den via scriptet.** Enhver gjengivelse av lovtekst må komme fra de
nedlastede XML-filene — ikke fra treningsdata.

---

## Språkregler

1. **Svar alltid på brukerens eget språk.** Spørsmål på engelsk → svar på engelsk.
   Spørsmål på norsk → svar på norsk. Spørsmål blandet → bruk norsk.
2. **Siter alltid lovteksten på original norsk**, uansett svarspråk. Direkte sitat
   av bestemmelser skal stå på norsk med anførselstegn («...» eller "...").
3. Legg gjerne til en oversettelse eller forklaring på brukerens språk etter sitatet.

---

## Kjøring ved oppstart: oppdateringssjekk

**Alltid første steg:** kjør oppdateringssjekket for å sikre at du arbeider med
gjeldende lovtekst:

```bash
python {SKILL_DIR}/scripts/lovdata.py update
```

Scriptet sammenligner `lastModified`-tidsstemplene fra Lovdata-APIet
(`https://api.lovdata.no/v1/publicData/list`, ingen autentisering) med lokalt
lagrede pakker i `state.json`. Hvis oppdateringer finnes, lastes de ned og
ekstraheres automatisk (~6 MB lover + ~21 MB forskrifter, daglig oppdatert).
Første gang tar det lenger tid; påfølgende kjøringer er raske hvis intet er endret.

Erstatt `{SKILL_DIR}` med basiskatalogens sti fra "Base directory for this skill:". Finnes ikke den stien i bash (Cowork viser noen ganger en vertsbane sandkassen ikke ser), finn skillen med `find /sessions -path '*/skills/lovdata-api/SKILL.md' 2>/dev/null | head -1` og bruk katalogen til den filen.

---

## Slik bruker du scriptet

### Søk etter lover/forskrifter

```bash
python {SKILL_DIR}/scripts/lovdata.py search "søkeord"
```

Søker i titler, Lovdatas korttitler/forkortelser (`aml`, `fvl`, `Grl.`,
`Grunnloven`) og DokID. Returnerer liste med tittel, korttittel, DokID og
sist-endret-dato. Eksakt treff på forkortelse eller korttittel rangeres
først, og lover før forskrifter og delegeringsvedtak. Flere ord treffer når
hvert ord står i tittelen («arbeidsmiljø lov»).

**Eksempler:**
```
python .../lovdata.py search "arbeidsmiljø"
python .../lovdata.py search "aml"
python .../lovdata.py search "internkontroll"
```

### Fulltekstsøk i bestemmelsene

Når du ikke vet hvilken lov som regulerer et tema:

```bash
python {SKILL_DIR}/scripts/lovdata.py find "deltid"
python {SKILL_DIR}/scripts/lovdata.py find "rimelig tid" --phrase
python {SKILL_DIR}/scripts/lovdata.py find "oppfølgingsplan" aml        # bare i én lov
python {SKILL_DIR}/scripts/lovdata.py find "personopplysninger" --sf    # også forskriftene
```

Gir én linje per paragraf (lov, §, DokID) med et utdrag. En bestemmelse
treffer når *alle* ordene står i den, som delstrenger («deltid» treffer
også «deltidsstilling»); `--phrase` krever hele uttrykket ordrett.
Bestemmelser med hele uttrykket ordrett kommer først, deretter lover før
forskrifter og flest forekomster først. Standard er bare lovene (`--sf`
tar med forskriftene), og 20 treff (`--max N`). Si fra til brukeren når
det er flere treff enn du viste. Utdraget er bare en pekepinn: hent alltid
paragrafen med `get` før du siterer.

### Hent en spesifikk paragraf

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" "§4-6"
# eller uten §-tegn:
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" "4-6"
```

Returnerer ren tekst av paragrafen med alle ledd, inkl. endringshistorikk.
Listepunkter beholder markøren (`a.`, `b.`, `1.`), slik at «annet ledd
bokstav b» kan siteres presist.

Dokumentet kan oppgis på flere måter — `get` godtar alle disse:

| Form | Eksempel |
|------|----------|
| DokID | `NL/lov/2005-06-17-62`, `SF/forskrift/1996-12-06-1127` |
| Lovdatas referanse | `LOV-2005-06-17-62`, `FOR-1996-12-06-1127` |
| lovdata.no-URL | `https://lovdata.no/dokument/NL/lov/2005-06-17-62/§4-6` (paragrafen i URL-en brukes når du ikke oppgir en) |
| Entydig korttittel/forkortelse | `aml`, `Grl.`, `Grunnloven` |

Er en korttittel tvetydig (f.eks. `forvaltningsloven`, se DokID-listen
nedenfor), sier scriptet hvilke DokID-er den kan være.

**Grunnloven** finnes på bokmål og nynorsk med samme DokID. `get` gir
bokmål; legg til `--nn` for nynorsk. Siter den språkformen forfatteren eller
brukeren bruker.

**Ikrafttredelse.** Hodet viser `Ikrafttredelse:` når Lovdata oppgir den.
Pakken inneholder også vedtatte lover som ikke er satt i kraft ennå — står
det «Kongen bestemmer» eller en dato fram i tid, er teksten *ikke* gjeldende
rett, og du må si det.

### Hent et kapittel eller et vedlegg

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" "kap4"
```

Foretrekk kapittel fremfor hele loven når spørsmålet gjelder et tema
(f.eks. arbeidstid = aml. kapittel 10).

Navngitte seksjoner virker på samme måte. Det er nyttig for
**menneskerettsloven** (`NL/lov/1999-05-21-30`), som har seks konvensjoner
som vedlegg i fulltekst — de samme konvensjonene traktatregisteret
(`norges-traktater`) ikke har tekst for:

| Konvensjon | Norsk | Engelsk |
|------------|-------|---------|
| EMK | `emkn` | `emke` |
| SP | `spn` | `spe` |
| ØSK | `oskn` | `oske` |
| Barnekonvensjonen | `bkn` | `bke` |
| Kvinnekonvensjonen | `kdkn` | `kdke` |
| CRPD | `crpdn` | `crpde` |

Seksjonen inneholder bare selve konvensjonen. **Protokollene er egne
seksjoner**: `emkn/p1`, `emkn/p4`, `emkn/p6`, `emkn/p7`, `emkn/p13` (og
`bkn/p1`, `bkn/p2`, `kdkn/p1` …). **Én artikkel** hentes med `/a<nr>`:
`emkn/a8` er EMK art. 8, `emkn/p1/a1` er protokoll 1 art. 1. Skrivemåtene
`"emkn art 8"` og `"emkn protokoll 1 art. 1"` virker også. Hent én artikkel
fremfor hele konvensjonen når spørsmålet gjelder én bestemmelse.

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/1999-05-21-30" "emkn/a8"
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/1999-05-21-30" "emkn/p1/a1"
```

Oppgir du et ukjent seksjonsnavn, lister scriptet de gyldige.

### Hent full lovtekst

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" --out aml.txt
```

Hele lover er ofte svært lange (arbeidsmiljøloven er over 200 000 tegn).
Bruk `--out FIL` og les filen i deler i stedet for å skrive alt til
terminalen; uten `--out` skrives teksten til stdout.

### Sjekk status

```bash
python {SKILL_DIR}/scripts/lovdata.py status
```

Viser nedlastningsdatoer og filantall per pakke, samt hvilken datakatalog som
er i bruk.

---

## DokID-format

| Kilde | Format | Eksempel |
|-------|--------|---------|
| Norsk lov | `NL/lov/YYYY-MM-DD-NNN` | `NL/lov/2005-06-17-62` |
| Sentral forskrift | `SF/forskrift/YYYY-MM-DD-NNN` | `SF/forskrift/1996-12-06-1127` |

Vanlige lover og forkortelser:
- `NL/lov/2005-06-17-62` — arbeidsmiljøloven (aml.)
- `NL/lov/1967-02-10` — forvaltningsloven (fvl.). Den nye forvaltningsloven
  (`NL/lov/2025-06-20-81`) ligger også i pakken; sjekk `Ikrafttredelse:` før
  du bruker den.
- `NL/lov/2006-05-19-16` — offentleglova (offl.)
- `NL/lov/2005-05-20-28` — straffeloven (strl.)
- `NL/lov/1981-05-22-25` — straffeprosessloven (strpl.)
- `NL/lov/2005-05-20-25` — tvisteloven (tvl.)
- `NL/lov/1999-07-02-63` — pasientrettighetsloven
- `NL/lov/1999-07-02-64` — helsepersonelloven
- `NL/lov/1992-11-04-126` — arbeidstvistloven
- `NL/lov/2013-06-21-58` — likestillings- og diskrimineringsloven
- `NL/lov/2023-12-20-108` — digitalsikkerhetsloven
- `NL/lov/2024-12-13-76` — ekomloven
- `SF/forskrift/1996-12-06-1127` — internkontrollforskriften (HMS)

Kjenner du ikke DokID, bruk `search` og finn den riktige. Pakkene inneholder
bare *gjeldende* regelverk: opphevede lover (f.eks. straffeloven 1902) finnes
ikke her — bruk `lovdata-pro` for historiske versjoner.

---

## Arbeidsflyt for vanlige oppgaver

### Bruker spør om en spesifikk paragraf

1. Kjør `update` for å sikre gjeldende data.
2. Finn DokID med `search` hvis den ikke er kjent.
3. Kjør `get <dokid> <paragraf>`.
4. Presenter teksten på norsk i anførselstegn, med forklaring på brukerens språk.
5. Oppgi kilde: lovens/forskriftens navn og paragrafnummer.

### Bruker spør hva loven sier om et tema

1. Kjør `update`.
2. Kjør `search` med relevante norske søkeord for å finne loven. Vet du ikke
   hvilken lov temaet står i, bruk `find` med et faguttrykk.
3. Hent relevante kapitler (`get <dokid> kapN`) eller paragrafer med `get`;
   hent hele loven med `--out` bare når det virkelig trengs.
4. Presenter relevante bestemmelser med sitat på norsk.

### Bruker spør om nylige endringer

1. Kjør `update` — scriptet rapporterer automatisk om pakker er oppdatert.
2. Hvis du henter et dokument, viser header-informasjonen `Sist endret i kraft`.
3. Endringshistorikk er inkludert i slutten av hver paragrafstekst ("Endret ved lover...").

---

## Sitatformat

Bruk standard norsk juridisk siteringsform:
- **Lov**: *[kortform] § [paragraf]* — f.eks. *aml. § 4-6 første ledd*
- **Forskrift**: *[kortform] § [paragraf]* — f.eks. *internkontrollforskriften § 5*
- **Direkte sitat**: «Arbeidsgiver skal, så langt det er mulig, ...»

Sitat skal alltid komme fra scriptet — ikke fra hukommelse.

Fotnoter står som `[fn N]` i teksten og `[fn N] …` i fotnoteteksten under
bestemmelsen («protokoll 3[fn 5]» = protokoll 3, fotnote 5). Ta ikke med
markøren i sitater; `[fn N]` er fra scriptet, ikke fra lovteksten.

---

## Hvor lagres data og state?

Selve ferdighetskatalogen er ofte skrivebeskyttet (skill installert via
plugin), så scriptet legger `state.json` og nedlastede XML-filer i en
skrivbar brukerkatalog. Stien velges i denne rekkefølgen:

1. `$LOVDATA_DATA_DIR` — hvis miljøvariabelen er satt
2. `$XDG_CACHE_HOME/lovdata` — hvis satt
3. `%LOCALAPPDATA%\lovdata` — på Windows
4. `~/.cache/lovdata` — ellers

Kjør `python {SKILL_DIR}/scripts/lovdata.py status` for å se faktisk sti.
Hvis en eldre installasjon hadde lagt `state.json` og `data/` direkte i
ferdighetskatalogen, blir disse migrert over første gang scriptet kjører.

---

## Feilhåndtering

- **Nettverksfeil under update**: Scriptet fortsetter med de lokale dataene
  fra forrige vellykkede nedlasting og skriver en `ADVARSEL` med datoene.
  Si da fra til brukeren at teksten ikke er sjekket mot dagens versjon.
  Finnes ingen lokale data, avslutter det med feil.
- **Dokument ikke funnet**: Prøv `search` med andre søkeord; husk at lokale
  forskrifter (LF) ikke er inkludert i de frie pakkene.
- **Tom paragraf**: Paragrafen kan være opphevet — sjekk lovteksten rundt.
- **Filen finnes ikke lenger**: Indeksen er utdatert — kjør `index` (eller
  `update`) på nytt.