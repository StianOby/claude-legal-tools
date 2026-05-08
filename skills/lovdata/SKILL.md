---
name: lovdata
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

# Lovdata — Norsk lovdatabase

Dette ferdighetsdokumentet er på norsk, men **svaret til brukeren skal alltid
tilpasses brukerens eget språk** (se Språkregler nedenfor).

Du har tilgang til Lovdatas offisielle datapakker via et hjelpescript i
`scripts/lovdata.py` (se Ferdighetskatalogens base dir). Merk: legg merke til
"Base directory for this skill:" i starten av dette dokumentet — det er samme
katalog som `scripts/lovdata.py` ligger i.

---

## Innhold — hva dekkes

Frie datapakker (ingen API-nøkkel nødvendig):
- **NL** — Gjeldende norske lover (782 XML-filer, daglig oppdatert)
- **SF** — Gjeldende sentrale forskrifter (3733 XML-filer, daglig oppdatert)

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

Erstatt `{SKILL_DIR}` med basiskatalogens sti fra "Base directory for this skill:".

---

## Slik bruker du scriptet

### Søk etter lover/forskrifter

```bash
python {SKILL_DIR}/scripts/lovdata.py search "søkeord"
```

Søker i titler og DokID. Returner liste med tittel, DokID og sist-endret-dato.

**Eksempler:**
```
python .../lovdata.py search "arbeidsmiljø"
python .../lovdata.py search "forvaltning"
python .../lovdata.py search "internkontroll"
```

### Hent full lovtekst

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62"
```

### Hent en spesifikk paragraf

```bash
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" "§4-6"
# eller uten §-tegn:
python {SKILL_DIR}/scripts/lovdata.py get "NL/lov/2005-06-17-62" "4-6"
```

Returner ren tekst av paragrafen med alle ledd, inkl. endringshistorikk.

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
- `NL/lov/1967-02-10` — forvaltningsloven (fvl.)
- `NL/lov/2006-05-19-16` — offentleglova (offl.)
- `NL/lov/2005-05-20-28` — straffeloven (strl.)
- `NL/lov/1902-05-22-10` — straffeloven 1902 (opphevet)
- `NL/lov/1981-05-22-25` — straffeprosessloven (strpl.)
- `NL/lov/2005-05-20-25` — tvisteloven (tvl.)
- `NL/lov/1999-07-02-63` — pasientrettighetsloven
- `NL/lov/1999-07-02-64` — helsepersonelloven
- `NL/lov/1992-11-04-126` — arbeidstvistloven
- `NL/lov/2013-06-21-58` — likestillings- og diskrimineringsloven
- `SF/forskrift/1996-12-06-1127` — internkontrollforskriften (HMS)

Kjenner du ikke DokID, bruk `search` og finn den riktige.

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
2. Kjør `search` med relevante norske søkeord.
3. Hent relevante dokumenter/paragrafer med `get`.
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

## Med API-nøkkel

Hvis `api_key` i `state.json` er satt, får scriptet tilgang til ytterligere
Lovdata-endepunkter (live oppslag, søk, historikk). Nøklene er foreløpig ikke
generelt tilgjengelige. De frie datapakkene gir tilgang til gjeldende
lovtekst for alle praktiske formål.

---

## Feilhåndtering

- **Nettverksfeil under update**: Informer brukeren; bruk evt. eksisterende
  lokale data hvis de finnes (sjekk status med `status`-kommandoen).
- **Dokument ikke funnet**: Prøv `search` med andre søkeord; husk at lokale
  forskrifter (LF) ikke er inkludert i de frie pakkene.
- **Tom paragraf**: Paragrafen kan være opphevet — sjekk lovteksten rundt.