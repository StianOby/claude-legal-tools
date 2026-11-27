# Lover og forskrifter: historikk (bare nye Lovdata Pro)

Les denne filen når spørsmålet gjelder en lov eller forskrift slik den lød
før, slik den ble vedtatt, en opphevet lov, Lovtidend eller endringslovene.
Gjeldende tekst alene: `lovdata-api`.

## Samlingene

Samme id finnes i flere samlinger:

| Hva | Samlinger |
|---|---|
| Gjeldende tekst | `NL`, `SF`, `LF`; også `DEL`, `INS`, `STV` |
| Opphevet tekst (slik den sist gjaldt, med endringsfotnoter) | `NLO`, `SFO`, `LFO` … |
| Kunngjort i Lovtidend (loven eller endringsloven slik den ble kunngjort, med «Publisert i» og «Kunngjort») | `LTI` (avd. I), `LTII` (avd. II) |
| Engelsk oversettelse | `NLE`, `SFE` |
| Tidligere versjoner | `HIST` |

Kortformen `lov/<dato>-<nr>` (fra `resolve` eller et søk) finner selv riktig
samling.

## Kallene

```javascript
await __lp.versions("lov/2005-06-17-62")                          // alle versjoner, eldste først, gjeldende sist
await __lp.versions("lov/2005-06-17-62", { asOf: "2019-03-15" })  // versjonen som gjaldt den datoen
await __lp.versions("lov/2005-06-17-62", { part: "§14-9" })       // bare versjonene der § 14-9 endret seg
await __lp.backlinks("lov/2005-06-17-62", "endringslover")         // endringslovene (LTI), også ikrafttredelsesvedtak
await __lp.backlinks("lov/2005-06-17-62", "lovspeil")              // forgjenger- og etterfølgerlover
```

`backlinks` tar bare `historisk`, `endringslover` og `lovspeil`.

## Versjonene

- En versjon er `HIST/<type>/<id>-<ÅÅÅÅMMDD>`, datoen versjonen gjelder fra
  i Lovdatas historikk, normalt ikrafttredelsen; `load()` den som et vanlig
  dokument. Den **første** versjonen kan ha en dato før loven trådte i kraft
  (arbeidsmiljøloven: `-20050701`, i kraft 1. januar 2006): for datoer nær
  lovens start, sjekk ikrafttredelsesbestemmelsen.
- **Lag aldri en HIST-sti selv**, heller ikke ut fra en dato du kjenner: Pro
  sender en ukjent dato stille til *gjeldende* tekst (`redirectedFrom` i
  svaret). Bruk `versions(…, { asOf })`, som velger den siste versjonen som
  trådte i kraft på eller før datoen, eller en sti fra `versions()`-listen.
- `checkCurrent` i svaret: datoen ligger etter siste historiske versjon, og
  Pro oppgir ikke når gjeldende tekst begynte å gjelde. Sammenlign med
  gjeldende tekst (endringsfotnotene der viser datoene) før du sier hva som
  gjaldt.
- Versjonene går ulikt langt tilbake: arbeidsmiljøloven 2005 til
  originalteksten, straffeloven 1902 glissent før 1980-årene, Grunnloven fra
  1814; opphevede forskrifter har ofte ingen. `before_first_version` betyr at
  Pro ikke har teksten fra så tidlig: si det, og bruk eventuelt Lovtidend
  (`LTI/lov/<id>`) for loven slik den ble vedtatt.
- Opphevede lover (`NLO`) har ofte ingen `HIST`-versjoner: `count: 0` med
  `part` betyr da ikke at paragrafen aldri ble endret. Se endringsfotnotene i
  teksten.
- `maybeCapped`: listen har nøyaktig 50 versjoner, som kan være en grense hos
  Pro. Er eldste versjon mye senere enn loven, kan versjoner mangle; for én
  paragraf gir `part` en egen liste.
- `part` tar §-id-en slik den står i dokumentet (`§14-9`, uten mellomrom).
- `asOf` er `ÅÅÅÅ-MM-DD` (ellers `bad_date`).

## Loven slik den ble vedtatt

Lovtidend-teksten `LTI/lov/<id>` er loven som kunngjort. Den første
`HIST`-versjonen er Lovdatas konsoliderte tekst fra den datoen; den er som
regel lik, men det er Lovtidend som er den vedtatte teksten. Sitér fra `LTI`
og oppgi «Norsk Lovtidend» (med «Publisert i»). Mangler `LTI` (eldre lover),
bruk den første versjonen og si at det er Lovdatas tekst.

Oppgi også **når loven trådte i kraft**: `metadata["I kraft fra"]` i
`LTI`-posten, ellers ikrafttredelsesvedtaket (`backlinks(lov,
"endringslover")`). «Kongen bestemmer» er ikke en dato.

## Endringslover og søk

- `backlinks(lov, "endringslover")` lister endringslovene (`LTI/lov/…`) og
  ikrafttredelsesvedtakene (`LTI/forskrift/…`). For forarbeidene til en
  endring: slå opp endringslovens `RFA/lov/<id>`.
- Søk i Lovtidend med `bases: ["LTI", "LTII"]` (`LFA` tar den ikke med, og
  `LT` gir null treff). `HIST` er ikke søkbar: finn loven og bruk
  `versions()`.

## De eldste tekstene

- **Christian Vs Norske Lov:** `lov/1687-04-15` er bare bestemmelsene som
  fortsatt gjelder. Hele originalteksten er den eldste versjonen
  (`versions("lov/1687-04-15")`, første oppføring; dansk, ca. 650 000 tegn,
  etter en utgave fra 1982).
- **Landslova** (1274) finnes som `NLO/lov/1274-06-24-nb`, `-nn` og `-non`
  (norrønt).

## Sitering

Sitér med versjonen: *arbeidsmiljøloven § 14-9 (versjon i kraft fra
1. januar 2019)*, og si at teksten er Lovdatas konsoliderte tekst. For
Lovtidend: *Norsk Lovtidend avd. I 2005 s. 1112*.
