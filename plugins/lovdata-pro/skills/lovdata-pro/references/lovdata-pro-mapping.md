# Lovdata Pro — URL & DOM mapping

This file captures what we observed exploring `lovdata.no/pro` (originally with
Playwright; the skill now drives Claude Desktop's built-in browser instead —
see `SKILL.md`). It's the source of truth for the URL and selector logic in
`scripts/browser/lovdata_pro.js`. When Lovdata changes their site, update this
file alongside the script.

---

## The one URL pattern that matters

Every Pro document is server-rendered as a single HTML page at:

```
https://lovdata.no/pro/document/<COLLECTION>/<TYPE>/<SLUG>/*
```

The trailing `/*` is the critical bit — it triggers the in-iframe
"Hele dokumentet" link (`<a id="allParts" class="partNavigation allParts">`)
behaviour. Without it, the URL returns only a small TOC stub for forarbeider.
The trailing `?showmarkings=true` is harmless but unnecessary for our purposes.

**Confirmed working examples (full HTML body returned):**

| Reference                        | Path                                                |    Bytes |
| -------------------------------- | --------------------------------------------------- | -------: |
| Ot.prp. nr. 3 (1998-99)          | `PROP/forarbeid/otprp-3-199899/*`                   |     1.3M |
| HR-2016-2554-P (Holship)         | `HRSIV/avgjorelse/hr-2016-2554-p/*`                 |     248K |
| NOU 2022:8 (Ny minerallov)       | `NOU/forarbeid/nou-2022-8/*`                        |     2.8M |
| Prop. 71 L (2024-2025)           | `PROP/forarbeid/prop-71-l-202425/*`                 |     2.4M |
| Innst. 521 L (2024-2025)         | `INNST/forarbeid/inns-521-l-202425/*`               |        ? |
| LG-2008-135938                   | `LGSIV/avgjorelse/lg-2008-135938/*`                 |      42K |

Without the `/*`, forarbeider return ~7 KB of just the table-of-contents — the
SPA lazy-loads chapters when you click them. Case-law decisions appear to
return the full document either way (Holship returns 248 KB at both URLs).

---

## Collection prefixes

Observed during exploration. **Rettspraksis** (`avgjorelse`) first:

| Citation form              | Collection | Type slug   | Notes |
| -------------------------- | ---------- | ----------- | ----- |
| `HR-YYYY-N-A/B/P/F/...`    | `HRSIV` (sivil) / `HRSTR` (straff) | `avgjorelse` | Modern Supreme Court |
| `Rt. YYYY s. N`            | `HRSIV` / `HRSTR` | `avgjorelse` | Pre-2008 Supreme Court. Slug pattern: `rt-YYYY-PAGENUMBER-SUFFIX` where SUFFIX is a Lovdata-assigned sequential number (e.g. `rt-2000-1811-hrsiv`). **The suffix cannot be guessed deterministically — use Pro UI search.** Some page numbers have two separate documents (e.g. `rt-1938-584-166` is a short tvistemål stub; `rt-1938-584-176` is the substantive case). When a short result appears for an old case, try the next sequential suffix before treating it as a dead end. |
| `LG-YYYY-N`                | `LGSIV` (Gulating sivil) | `avgjorelse` | Lagmannsrett: prefix encodes court (LB Borgarting, LA Agder, LF Frostating, LH Hålogaland, LE Eidsivating) and division (SIV / STR) |
| `LB-YYYY-N`                | `LBSIV` / `LBSTR` | `avgjorelse` | Borgarting lagmannsrett |
| `RG YYYY s. N`             | varies — older RG cases sit under whichever lagmannsrett actually decided them. Pro renders them via Tingrett (`TRSIV`) when search is the only path | `avgjorelse` | Slugs are irregular; runtime search needed. Search for Lovdata's own reference form (`RG-2010-100`), not the prose citation — `lovdata_ref.py` returns that as `search_hint` |

**Complete lagmannsrett collection table:**

| Court code | Court name         | Civil   | Criminal |
| ---------- | ------------------ | ------- | -------- |
| LB         | Borgarting         | `LBSIV` | `LBSTR`  |
| LA         | Agder              | `LASIV` | `LASTR`  |
| LE         | Eidsivating        | `LESIV` | `LESTR`  |
| LF         | Frostating         | `LFSIV` | `LFSTR`  |
| LG         | Gulating           | `LGSIV` | `LGSTR`  |
| LH         | Hålogaland         | `LHSIV` | `LHSTR`  |

**Tingrett references carry a court prefix, not a bare `TR-`.** Lovdata
cites district courts as `TOSLO-2019-12345` (Oslo tingrett, pre-2021
court reform), `TOSL-2022-123456` (post-reform), `TBERG-`, `TSTAV-`,
`THOD-`, and so on — the letters after `T` abbreviate the court. The
collection is `TRSIV`/`TRSTR` for all of them. `lovdata_ref.py` accepts
any `T<letters>-YYYY-N` form and lower-cases the reference into the slug,
trailing `-1`/`-2` included. `TRR-` (Trygderetten), `TLN-`, `TGLA-`,
`TUSAK-` and `TUDEP-` are not tingretter: the prefix table in the next
section is checked first.
**Confirmed live (September 2026):** `TOSLO-2019-108726-2` →
`TRSIV/avgjorelse/toslo-2019-108726-2`, `TOSL-2022-105703` →
`TRSTR/avgjorelse/tosl-2022-105703`. As with the other court collections the
SIV/STR split is by subject matter, and `tryPaths()` swaps automatically.

**Forarbeider** (`forarbeid`):

| Citation form              | Collection | Type slug   | Notes |
| -------------------------- | ---------- | ----------- | ----- |
| `Ot.prp. nr. N (YYYY-YY)`  | **`PROP`** for ≥1968-ish, older may be `OTPRP` (not yet confirmed in Pro) | `forarbeid` | Slug: `otprp-N-YYYYYY` (year encoded as 6 digits, no separators) |
| `Prop. N L/S/Stortingsm.`  | `PROP` | `forarbeid` | Slug: `prop-N-l-YYYYYY` (lowercase L, year as 6 digits) |
| `NOU YYYY: N`              | `NOU` | `forarbeid` | Slug: `nou-YYYY-N` (a/b suffix when split into parts: `nou-2001-32a`, `-32b`) |
| `Innst. N L (YYYY-YY)`     | **`INNST`** | `forarbeid` | Slug uses `inns-` (not `innst-`): `inns-521-l-202425` — note the collection/slug mismatch |
| `Innst. O./S. nr. N (YYYY-YY)` | `INNST` | `forarbeid` | Pre-2009 committee recommendations. Same `inns-` rule with the chamber letter: `inns-o-45-200405`, `inns-s-12-200405`. Confirmed live |
| `Meld. St. N (YYYY-YY)` / `St.meld. nr. N` | **`STS`** | `forarbeid` | **Not covered by the skill** (since 1.5.2): not in the new Pro, and mostly register-only in Klassisk. For the record: slug `stsg-<sesjon>-<løpenummer>`: Meld. St. 17 (2020-2021) → `STS/forarbeid/stsg-202021-355`, St.meld. nr. 12 (2006-2007) → `STS/forarbeid/stsg-200607-255`. **The løpenummer is Lovdata-assigned and not derivable from the citation** — same class of problem as pre-2008 Rt. suffixes, so `lovdata_ref.py` returns `parsed:false` and a search hint. There is no `MELD` collection |
| `St.prp. nr. N (YYYY-YY)`  | — | — | Non-law propositions are not full-text indexed. Four Hurtigsøk queries for St.prp. nr. 100 (1991-92) surfaced only EEA-annex directives, never the proposition. Treat as "not in Pro" |
| `Dok. 8:N`                 | `REPFOR` | `forarbeid` | `dok8-12-199900`. Confirmed live |
| `Representantforslag N S (YYYY-YY)` / `Dokument 8:N S` | `REPFOR` | `forarbeid` | From 2009 the id is `representantforslag-N-YYYYYY` (no letter); `dok8-N-s-YYYYYY` resolves to it through `references` |
| `Dokument 12:N` / `Grunnlovsforslag N` | `GLFOR` | `forarbeid` | `dok12-N-YYYYYY` |
| `Dokument N (YYYY-YY)` (other series) | `SDOK` | `forarbeid` | `dokN-YYYYYY` (`dok5-202526`, `dok7-197273`). Recent ones are PDF only in pro2 (`originalFile`). `dokN-M-YYYYYY` for a sub-numbered series is assumed, not seen |
| `Ot.meld. nr. N` | `OTMELD` | `forarbeid` | `otmeld-N-YYYYYY`, 1927–2006/07 |
| `Besl. O. nr. N` / `Lovvedtak N` | `LOVVED` | `forarbeid` | `besl-o-N-YYYYYY` / `lovvedtak-N-YYYYYY` |
| `PRE-YYYY-MM-DD-N` (statsrådsforedrag) | `PRE` | `forarbeid` | `pre-YYYY-MM-DD-N`; a foredrag for two forskrifter resolves by either number |
| Forarbeider to a law | `RFA` | **`lov`** | `RFA/lov/YYYY-MM-DD-N`: Lovdata's register of the law's forarbeider (~400 chars). `references/lov/<id>` gives the law itself (`NL`/`NLO`/`LTI`), so use the full path; `resolve` returns it as `forarbeider` |
| `NOU YYYY:N` (pre-~1975)   | `PUBG` | `pubg-YYYYYY-nou-N` | Historical publications. E.g. NOU 1972:16 → `PUBG/pubg-197273-nou-16`. **Returns metadata only (~468 chars), not full text.** Year range encoded as 6 digits same as forarbeider. In the new Pro PUBG records have type `null` and cannot be opened (search marks them `noDocument`); Klassisk only. |

### Year encoding rule (forarbeider)

Slug encoding: full first year (4 digits) followed by the last two of the
second year. `(2024-2025)` becomes `202425`, `(1998-99)` becomes `199899`,
`(1961-62)` becomes `196162`. Six digits, no separator. We confirmed this
matches Pro's actual slugs for the documents in our test set.

### Coverage cutoff (forarbeider)

Official Lovdata Pro coverage by document type:

**Propositions (Ot.prp. / Prop. L):**
- Full text from session **1984/85** onwards for all law-related propositions.
- Selected older Ot.prp. also have full text.
- Non-law propositions (St.prp., etc.): header + PDF link only — not indexed
  as full-text forarbeider regardless of age.
- Page numbers appear **only in PDF** from 2024 onwards (all propositions
  from session 2025/26).

**NOU:**
- Full text from **1994** onwards (all NOUs); PDF also from 2003.
- **1985–1993**: many have only summary or TOC; but many pre-1985 NOUs for
  central legal areas are available in full text.
- Pre-1985 NOUs may appear under the `PUBG` collection (often metadata-only).

**Other reports:**
- NUT series ("Innstillinger og Betenkninger", predecessor to NOU) available,
  including all Rådsegn from Sivillovbokutvalget.

**Innstillinger:**
- Law-related from session **1991/92** onwards; some older ones also available.
- Other Innstillinger + budget from session **1992/93** onwards.

When a slug 404s and search returns no plausible match, surface a "likely not
in Lovdata Pro as full text" message rather than a generic "document not
found".

### Division (SIV vs STR)

Court collections come in pairs: civil (`...SIV`) and criminal (`...STR`).
`lovdata_pro.js` must try both when the citation doesn't disclose which.

**The split is by subject matter, not era.** HRSTR is not only for old Rt.
cases — recent Høyesterett decisions in criminal matters also live in HRSTR.
Heuristic: if the case involves straffeloven, straffeprosess, or EMK artikkel
6 (fair trial / uskyldspresumsjonen), try HRSTR first. Example: HR-2025-813-A
(TikTok) is HRSTR despite its modern identifier.

**Redirect URL reveals the correct collection.** If you navigate to a
wrong-collection URL in the SPA (e.g., `#document/HRSIV/avgjorelse/hr-2025-813-a`),
Lovdata Pro silently updates the hash to the correct collection
(`#document/HRSTR/avgjorelse/hr-2025-813-a`). Use this as a manual
collection-discovery technique when debugging: navigate, read the redirected
hash, then use that collection in subsequent fetch calls.

`lovdata_pro.js`'s `tryPaths()` function automatically tries the SIV/STR
counterpart whenever a collection-mismatch response is detected, so callers
(i.e. `load()`) need not enumerate both variants explicitly.

---

## New Lovdata Pro: categories beyond the ordinary courts (2026-11-26)

Mapped from the new Pro's `GET /api/document-lookup-data/base-tree` and one
probe per base. Bases are tested on the new Pro only (`docs/lovdata-pro2.md`).
Counts are `term:"*"` hits on 2026-11-26; "from" is the earliest date seen.
**The id is the lower-cased Lovdata reference** unless noted, so
`resolve` builds `<BASE>/<type>/<prefix-year-number>` from the prefix table
in `scripts/lovdata_ref.py`. When the id has a suffix the citation leaves
out, the full path misses and `load()` resolves the short form
`<type>/<id>` through `references`, which finds the suffixed id (and the
base). That also covers old prefixes not in the table; `explain()` returns
them as `pro2_ref`.

`references/<type>/<id>` fails where the printed reference pads the number
(`G-1958-0005` is `g-1958-5`: `resolve` strips the zeros) or the id keeps a
letter the reader might drop (`adn-2026-d24673`, `kt-2026-3v`). Several short
forms have more than one hit (`fkr-2022-4`, `ob-2024-4`, `bdn-1973-52`, an
Rt. page): `load()` takes the first and lists `alternatives`.

Group codes for `search(..., {bases})`: `SD` and `PUB` (both under `AVG`),
`FSA` (with `REGISTEROPPLYSNINGER`), `ROU` (with `RUNDSKRIV`,
`OPPHEVDERUNDSKRIV`, `UTTALELSER`), `NEMNDEROGUTVALG` (with `FINKN`). `RT`,
`UTV` and `FS` are publication nodes without children: as filters they
return about as much as `AVG`, so they are not filters.

### Spesialdomstoler (`SD`, type `avgjorelse`)

| Base | Court | Prefix | Count | From | Notes |
|---|---|---|---|---|---|
| `ARD` | Arbeidsretten | `AR-`, `ARD-` | 2 872 | 1916 | Old ids `ard-1916-1-16001`; `ard-1916-1` and `ARD 1916 s. 1` resolve |
| `TRR` | Trygderetten | `TRR-` | 69 814 | 1971 | |
| `JSR` | Jordskifterettene | `J<court>-` (`JMOR-`) | 2 527 | 1996 | |
| `JSO` | Jordskifteoverrettene | `JO<court>-` (`JOAG-`) | 530 | 1991 | |
| `UTMA` | Utmarksdomstolen for Finnmark | `UTMA-` | 31 | 2014 | Header has Dokumenttype for Instans |
| `FKR` | Finnmarkskommisjonen | `FKR-` | 10 | 2012 | `fkr-2022-4` has three parts (-1, -2, -3) |
| `UNT` | Utmarkskommisjonen for Nordland og Troms | `UNT-` | 36 | 1990 | |
| `HFK` | Høyfjellskommisjonen | `HFK-` | 78 | 1910–1953 | |
| `HKOM` | Kommissariske Høyesterett 1941–1944 | `Rt-1944-…` | 85 | 1941–1944 | Header only; text in Retstidende (`publication`) |

There is no Riksrett base.

### Publikasjoner (`PUB`, type `avgjorelse`)

| Base | Publication | Prefix | Count | From | Notes |
|---|---|---|---|---|---|
| `NDS` | Nordiske Domme i Sjøfartsanliggender | `ND-`, `ND YYYY s. N` | 3 311 | 1925 | Id has a suffix (`nd-2025-23-23s`). Full report, can be in Swedish or Danish |
| `NDSENG` | ND in English | | 7 | 1961 | `nd-2016-219-eng`; the short form without `-eng` gives the Norwegian original |
| `NAD` | Norsk arbeidsrettslig domssamling | `NAD-`, `NAD YYYY s. N` | 1 126 | 1981–1988 | `nad-1988-1369-ag` |
| `LODA` | Avgjørelser publisert i Lov&Data | `LOD-` | 819 | 2011–2016 | Header only; Lovdata's own journal. Not in the prefix table |

Retstidende, Rettens Gang and Utvalgte skattedommer are cited by year and
page and resolve to the underlying judgment (`pro2_ref`, e.g.
`avgjorelse/utv-2017-1057`).

### Rundskriv og uttalelser (`ROU`)

Type `rundskriv` unless noted. Each rundskriv base has a twin for repealed
ones (`…O`); `resolve` gives both.

| Base (repealed) | Issuer | Prefix | Count | From |
|---|---|---|---|---|
| `RDEP` (`RDEPO`) | Departementene | series letter: `G-`, `GI-`, `R-`, `H-`, `I-` … | 1 191 (1 195) | 1958 |
| `ROO` (`ROOO`) | Andre offentlige organer | `IS-` (Helsedirektoratet) | 155 (51) | 1997 |
| `NAV` (`NAVO`) | Arbeids- og velferdsetaten | irregular (`r25-13-for-1944`, `v8-15-00`) | 517 (241) | 1953 |
| `RFT` (`RFTO`) | Finanstilsynet | `RFT-` | 97 (161) | 2007 |
| `RPOD` (`RPODO`) | Politidirektoratet | `RPOD-` | 83 (100) | 2002 |
| `RUDI` (`RUDIO`) | Utlendingsdirektoratet | `RUDI-` | 302 (530) | 1993 |
| `RUNE` (`RUNEO`) | Utlendingsnemnda | `UNEPN-` | 31 (3) | 2005 |
| `RA` (`RAO`) | Riksadvokaten | `RA-` — **type `avgjorelse`** | 362 (37) | 1928 |
| `SKM` | Skattedirektoratets meldinger | `SKM-` — type `avgjorelse` | 572 | 1954 |
| `SPHPM` | SPH – personalmeldinger | `PM-` — type `null`, cannot be opened | 302 | 2013 |

Departmental circulars are also cited as `G-01/2016`; `resolve` turns that
into `g-2016-1` (assumed from the id rule, not yet seen).

Uttalelser (`UTTALELSER`, all type `avgjorelse`):

| Base | Body | Prefix | Count | From |
|---|---|---|---|---|
| `JDLOV` | Lovavdelingen | `JDLOV-` | 2 289 | 1975 |
| `SOMB` | Sivilombudet | `SOM-`, `SOMB-` | 5 572 | 1963 |
| `SOMFOR` | Sivilombudets forebyggingsenhet | `SOMFOR-` | 108 | 2014 |
| `BFU` | Skattedirektoratets bindende forhåndsuttalelser | `BFU-` | 947 | 2001 |
| `USKD` | Skattedirektoratets uttalelser | `USKD-` | 961 | 2000 |
| `UFIN` | Finansdepartementets uttalelser | `UFIN-` (also `Utv. YYYY s. N`) | 662 | 1984 |
| `TUDEP` | Tolkningsuttalelser fra departementene | `TUDEP-` (id ends in a literal `-*`) | 787 | 1986 |
| `UMD` | Miljøverndepartementet | `UMD-` | 173 | 2001–2012 |
| `BFJR` | Byggebransjens Faglig Juridiske Råd | `BFJR-` | 660 | 1977 |

### Nemnder og utvalg (`NEMNDEROGUTVALG`, type `avgjorelse`)

The prefix is the base, lower-cased, except where noted. Header field
`Dokumenttype` takes the place of Instans and `Nemndsmedlemmer` that of
Rettsmedlemmer.

| Base | Body | Count | From | Notes |
|---|---|---|---|---|
| `ADN` | Advokatnemnda | 7 267 | 1910 | Number can carry a letter (`adn-2026-d24673`) |
| `ADT` | Advokattilsynet | 122 | 2019 | |
| `AN` | Ankenemnda for sykepenger i arbeidsgiverperioden | 3 385 | 1979 | |
| `APN` | Apotekklagenemnda | 16 | 2002 | |
| `BVHN` | Barneverns- og helsenemnda | 4 878 | 2002 | County suffix (`bvhn-2026-199-bro`) |
| `DIN` | Diskrimineringsnemnda | 3 468 | 1980 | |
| `DOK` | Domeneklagenemnda | 812 | 2004 | |
| `ELKN` | Elklagenemnda | 1 673 | 2012 | |
| `ENK` | Energiklagenemnda | 140 | 2020 | |
| `FINKNB`, `FINKNF`, `FINKNI` | Finansklagenemnda – bank, forsikring, inkasso (group `FINKN`) | 28 130 | 1988 | All `FinKN-`; `resolve` tries the three |
| `FTK` | Finanstilsynsklagenemnda | 303 | 1989 | |
| `FKU` | Forbrukerklageutvalget | 25 712 | | `FKU/null/list-…` entries are lists, not documents |
| `FOV` | Forbrukertilsynets vedtak | 130 | 2009 | |
| `FREN` | Frivillighetsregisternemnda | 118 | 2017 | |
| `GK` | Gjenopptakelseskommisjonen | 2 581 | 2005 | |
| `HPN` | Helsepersonellnemnda | 2 178 | 2001 | |
| `HTU` | Husleietvistutvalget | 5 150 | 2010 | |
| `INTOPS` | Klagenemnda … internasjonale operasjoner | 115 | 2020 | |
| `KDF` | Klagenemnda for disiplinærsaker i Forsvaret | 695 | 1989 | |
| `KEOS` | Klagenemnda for EØS-saker | 75 | 2020 | |
| `KFIR` | Klagenemnda for industrielle rettigheter | 1 697 | 2013 | |
| `KMI` | Klagenemnda for miljøinformasjon | 210 | 2004 | |
| `KMVA` | Klagenemnda for merverdiavgift | 5 364 | 1995–2016 | |
| `KOFA` | Klagenemnda for offentlige anskaffelser | 2 937 | 2003 | |
| `KT` | Konkurransetilsynet | 797 | 1998 | Letter suffix (`kt-2026-3v`) |
| `KTKD` | Konkurransetilsynet – vedtak i klagesaker til dep. | 137 | 2005–2018 | |
| `KTKN` | Konkurranseklagenemnda | 43 | 2018 | |
| `KTN` | Kabeltvistnemnda | 18 | 1991 | |
| `LOTN` | Lotterinemnda | 1 168 | 2010 | |
| `MKN` | Medieklagenemnda | 257 | 2010 | |
| `MR` | Markedsrådet | 628 | 1973 | |
| `NKU` | Næringslivets konkurranseutvalg | 757 | 1964 | |
| `NSK` | Klagenemnda for naturskadesaker | 1 827 | 2009 | |
| `OB` | Oslo Børs | 979 | 1998 | `ob-2024-4` and `ob-2024-4-1` both exist |
| `PARKN` | Parkeringsklagenemnda | 248 | 2023 | |
| `PGD` | Preimplantasjonsdiagnostikknemnda | 357 | 2004–2020 | |
| `PLN` | Partilovnemnda | 477 | 2006 | |
| `PRKN` | Pakkereiseklagenemnda | 3 316 | 2010 | |
| `PS` | Patentstyret 2. avdeling | 759 | 1966–2013 | `ps-2013-8147-8147-p` |
| `PSA` | Patentstyret | 1 851 | 2008 | |
| `PSK` | Klagenemnda for petroleumsskatt | 405 | 1977 | |
| `PSN` | Pasientskadenemnda | 24 735 | 2003 | |
| `PVN` | Personvernnemnda | 433 | 2001 | |
| `RAV` | Vedtak fra Riksadvokaten | 19 | 2020 | |
| `REHJ` | SRF – fri rettshjelp og salær | 1 523 | 2006 | |
| `RFE` | Reklamasjonsnemnda for eiendomsmeglingstjenester | 3 078 | 2005 | |
| `SINN` | Skjønnsnemnda etter inndelingslova | 6 | 1972 | |
| `SJTKN`, `FLYKN`, `KOLLKN` | Transportklagenemnda – sjø, fly, kollektivreiser | 13 674 | 2009 | |
| `SKN` | Skatteklagenemnda | 1 184 | 2016 | Avdeling in the prefix: `SKNA2-`, `SKNS1-` |
| `SKNS` | Skatteklagenemnda for storbedrifter | 317 | 1999–2016 | Prefix `SKN-` (older); `resolve` tries `SKNS` then `SKN` |
| `SKU` | Skatteklagenemnda for utenlandssaker | 211 | 2011–2016 | |
| `ESTR` | SRF – erstatning for strafforfølgning | 6 184 | 2005 | |
| `STKN` | Stiftelsesklagenemnda | 183 | 2015 | |
| `TGLA` | Tinglysingsavgjørelser | 1 402 | 1900–1989 | |
| `TLN` | Tvisteløsningsnemnda etter arbeidsmiljøloven | 2 925 | 1993 | |
| `TUSAK` (`TUSAKENG`) | Tilsynsutvalget for dommere (English) | 826 (149) | 2003 | English ids end in `-eng` |
| `UKN` | Klagenemnda for behandling i utlandet | 335 | 1999 | |
| `UNESV` | Utlendingsnemnda stornemnd | 37 | 2006 | |
| `VEM` | Voldserstatningsmyndigheten | 9 785 | 2003 | Old `env-` ids also resolve under a legacy base `ENV` |
| `VMM` | SRF – vergemål | 845 | 2013 | |
| `VPOD` | Vedtak fra Politidirektoratet | 550 | 2003 | |
| `VSPES` | Spesialenheten for politisaker | 15 | 2023 | |
| `VVN` | Vederlagsnemnda – åndsverk | 11 | 1992–2007 | |

Old prefixes (`BKN-`, `INKN-`, `LKN-`, `OBKN-`, `NSN-`, `KUD-`, `TOGKN-`,
`BDN-`, `FNV-`, `OLN-`, `ABN-`, `ADA-`) live in the successor's base; they
are not in the table and go through `pro2_ref`.

### Lover og forskrifter (`LFA`)

Types `lov` and `forskrift`; id `YYYY-MM-DD-N` (just the date for laws
without a number, 1687 and 1814; `-nb`/`-nn`/`-non` language variants).
`resolve` gives the short form `lov|forskrift/<id>`: `references` returns the
consolidated text when there is one (current or repealed base), otherwise
the Lovtidend item. `checkDocument/NL/lov/<id>` of an amending act redirects
to `LTI`. `checkDocument` ignores parts (`…/§9999` is Success).
`references/lov/<id>/§3` resolves a §; chapter parts are unreliable
(`KAPITTEL_2` and `k2` land on the English `NLE`), so find chapters with
`grep`.

| Group | Base (repealed) | Content | Count | From |
|---|---|---|---|---|
| `LOVER` | `NL` (`NLO`) | Lover | 753 (2 666) | 1687 (1274) |
| | `NLE` (`NLEO`) | Lover, English | 83 (9) | 1814 |
| | `ISL` | Ikke-sanksjonerte lover (type `isl`; `references` does not find it) | 1 | |
| `SFA` (`SFOA`) | `SF` (`SFO`) | Sentrale forskrifter | 3 460 (13 213) | 1896 (1817) |
| | `DEL` (`DELO`), `INS` (`INSO`), `STV` (`STVO`) | Delegeringer, instrukser, stortingsvedtak | 1 431, 186, 84 | 1905 |
| | `SFE` (`SFEO`) | Sentrale forskrifter, English | 86 (23) | 1971 |
| `LOK` | `LF` (`LFO`), `LFE` | Lokale forskrifter | 12 124 (14 895) | 1894 (1855) |
| — | `LTI`, `LTII` | Norsk Lovtidend avd. I (laws, central forskrifter) and II (local) as promulgated | 58 886, 29 533 | 1909, 1894 |
| — | `HIST` | Historical versions, `HIST/<type>/<id>-<YYYYMMDD>` | not searchable | |

`LFA` as a search filter leaves out `LTI`/`LTII` (`LT` gives 0); name them.
Repealed texts are complete as last in force, with amendment footnotes; the
header's "Sist endret ved" names the repealing act. Lovtidend items carry
"Publisert i" (e.g. "I 2005 hefte 8 s 1112"), "Kunngjort" and
"Journalnummer"; 2026 items also link the signed PDF
(`externalVersions` `LT_PDF`).

**Historical versions.** `GET backLinks/historisk/<doc>` lists them (HIST
entries with `historicDateString`, the current text last);
`GET paragraphHistory?dokID=<doc>&partID=§N` lists the versions of one §.
A HIST path with a date that is not a version date redirects to the
**current** text, so the helper's `versions(path, {asOf})` picks the last
version on or before the date. `documentSummary` dates in the list are
unreliable; `historicDateString` is the version date. Depth varies:
arbeidsmiljøloven 2005: 49 versions back to the original; folketrygdloven:
167; straffeloven 1902: 71, sparse before the 1980s; Grunnloven: 32 from
1814; Norske Lov 1687: 3, the first (`HIST/lov/1687-04-15-16870415`) the
full Danish original (~656 000 chars) while `NL/lov/1687-04-15` holds only
what is still in force. Repealed regulations checked had none.

Other lists per act: `backLinks/endringslover/<doc>` (amending acts and
commencement resolutions, `LTI`; aml 2005: 127) and
`backLinks/lovspeil/<doc>` (predecessor/successor acts). The helper's
`backlinks()` reads only `historisk`, `endringslover` and `lovspeil`.

## Authentication

- Login is via SSO/FEIDE/email-password depending on the user. The skill never
  stores or sees credentials — it asks the user to log in interactively inside
  Claude Desktop's built-in browser pane (Cowork).
- The built-in browser has a persistent profile on the user's own machine, so
  cookies (including the HttpOnly session cookie) persist across turns and
  conversations without the skill saving or reading them itself — unlike the
  Playwright-era script, there is no `storage_state.json` and nothing for the
  skill to manage on disk.
- Logged-in landing page: `https://lovdata.no/pro/#myPage` — title becomes
  `Min side - Lovdata Pro`. `__lp.isLoggedIn()` uses this as a "still logged
  in" probe before every fetch.
- **Spike 2 findings** (confirmed 2026-09-05): `location.hash` is **not** a
  usable discriminator — it stays `#myPage` in both the logged-in and
  logged-out states (Lovdata swaps the rendered content client-side without
  touching the hash). Only `document.title` distinguishes them:
  - Logged in: `"Min side - Lovdata Pro"`
  - Logged out: bare `"Lovdata"` (body text includes "Logg inn i Lovdata
    Pro")

  `isLoggedIn()` therefore checks `document.title` only.

---

## Search

Two layers:

1. **Free public `/sok` endpoint** (`https://lovdata.no/sok?q=...`) returns
   only documents available on the free site. **Forarbeider, older Rt./RG,
   and many other Pro-only documents are not surfaced here.** Useful only as
   a first-pass fallback for case law that's also on the free site.

2. **Pro search inside the SPA** is GWT-RPC over `LovdataPro/GWT.rpc?fulltextSearchService`.
   **Confirmed by spike 3 (2026-09-05):** the request/response is a
   comma-separated stream of numbers, type-tag characters, and string-table
   references (e.g. `//OK["o","Bx",0,0,425,0,5,0,0,0.0,0.0,...`) — GWT's
   positional serialization with an obfuscated string table, not JSON. No
   separate JSON/REST search endpoint exists to call directly; hand-parsing
   or replicating this format is impractical.
   - **The query is submitted by a `keyup` event (re-measured 2026-09-09).**
     Event-by-event isolation in a live session: an `input` event alone does
     **not** submit; a synthetic `keydown` does **not**; a synthetic
     `keypress` does **not**; a synthetic **`keyup`** with key Enter **does**
     (the hash went to `#result&id=2378&q=TOSL-2023*`). A *real* Enter
     keypress from the `computer` tool, with focus verified in the field,
     does **not** submit. A real click on the 🔍 button does.
     This corrects the earlier spike-4 conclusion ("only a real click
     works"), which had tested `input`/`keydown` but not `keyup`.
   - `__lp.search(query, n)` therefore does the whole thing in one JS call:
     set the value through the native setter, dispatch
     `keydown`/`keypress`/`keyup`, wait for the hash to become `#result…`,
     then read the anchors. Hash routing does not reload the page, so
     `window.__lp.cache` survives a search in the same tab.
   - `__lp.readSearchResults(n)` remains available for the fallback flow
     (`computer.type` + `computer.left_click` on the 🔍 button, located with
     `read_page` — `computer.screenshot` has been seen to fail with
     `UnknownVizError`). It reads `a[href^="#document/"]` anchors already in
     the DOM and takes no query.
   - **Pro rewrites the query**: it lower-cases the input and appends a
     truncation wildcard, so `TOSL-2022` is submitted as `tosl-2022*` and the
     hash reads `q=TOSL-2022*`. Never assert that the hash matches the query.
   - Each href has the form `#document/<COLLECTION>/<TYPE>/<SLUG>?searchResultContext=...&rowNumber=...&totalHits=...`
   - The first match is usually correct for direct-citation queries; for
     ambiguous queries `__lp.readSearchResults()` returns the top N and lets
     the caller pick.

Free-text search does NOT find the cited document by reference — it finds
documents that *cite* it, or documents whose full text happens to contain
the query terms. Example: searching «St.prp. nr. 100 1991-92 EØS-avtalen»
returns EU directives from the EEA annex (because the EEA Agreement
references those terms pervasively), not the proposition itself.

For exact-reference resolution, prefer direct slug patterns first and use
search only as a fallback. Pro's advanced search (`#search`) has a
`dokumentnr` field, but it's only visible after selecting a "Rettskilde"
first. Practical strategy: start with the Hurtigsøk; if the top result's
slug doesn't match the requested ref, fall back to the user.

---

## DOM — extracting the document body

The fully-rendered page at `/*` has this structure (from
`Ot.prp.nr.3 (1998-99)/*`):

```html
<div id="maincolOneColumn">
  <div id="lovdataDocument" class="commentWidget desktop">
    <div id="documentBody">
      <a class="namedAnchor" name="kap1"></a>
      <div class="documentButtonsBar part smallIcons …" id="documentButtons_kap1">…</div>
      <div data-level="1" data-id="KAPITTEL_1" class="morTag_b kapittel" id="KAPITTEL_1">
        <h2>1 Proposisjonens hovedinnhold</h2>
        <p class="morTag_am no-text-indent avsnitt">…body text…</p>
        …
      </div>
      …more KAPITTEL_N divs…
    </div>
  </div>
</div>
```

For text extraction, `lovdata_pro.js`'s `toText()` targets `#documentBody`
(not `#lovdataDocument` — that also wraps the separate `#documentMeta`
sidebar, which would leak metadata-table noise into every section/page and
break `sectionRange()`'s heading-to-heading walk) and:

- Strips `.documentButtonsBar` toolbars (per-chapter share/note icons) before
  extraction, via `stripNoise()`.
- Maps `<h1>`–`<h6>` to markdown-style `#`/`##`/… heading lines.
- Maps `<p>` to plain lines. **Lovdata emits no `<ul>`/`<ol>`/`<li>` at all**
  (NOU 2022:8 contains zero): litra and numbered points are one-row
  `<table class="listeItem">` elements whose depth is carried by a
  `leftMargin_N` class. `toText()` detects those and renders them as
  indented `a. text` lines rather than pipe rows, so a litra can be quoted
  and located. The `<li>` branch is kept for other markup but is currently
  dead on Pro documents.
- Preserves `<table>` as pipe rows (Pro uses real HTML tables for metadata
  blocks, and occasionally in body text).
- Within headings/`<p>`/`<li>`/table cells, `inlineText()` (not raw
  `textContent`) renders `<strong>`/`<b>` as `**bold**`, `<em>`/`<i>` as
  `*italic*`, and `<sup>` as `^superscript^`, so e.g. bold §-titles in
  statute text quoted inside forarbeider survive extraction instead of
  merging invisibly into the surrounding paragraph. Confirmed by a live
  check against `HRSIV/avgjorelse/hr-2016-2554-p` that Høyesterett's
  "(77)"-style avsnitt numbers are real DOM text, not CSS-generated
  content — see `NOTES.md` for that check and how to re-run it.
- Footnote/reference anchors (`<a class="namedAnchor">`) are left as-is;
  `inlineText()`/`toText()` just read text content so empty anchors
  contribute nothing.

Metadata block (title, dato, utgiver, henvisninger, etc.) sits in a `<table>`
under `#documentMeta` (falling back to `#documentBody` if that ID isn't
present for a given document type). `extractMetadata()` in `lovdata_pro.js`
picks the one table among possibly several whose rows look like genuine
key/value pairs (≥3 rows, keys ≤40 chars) and extracts it into a JSON payload
kept separate from the body text. It reads the cells with `inlineText()`, not
`textContent`, because the `Parter` row separates each party and its counsel
with `<br>` — the parties are **not** in the body text of a judgment, so this
table is the only place they appear.

---

## Failure modes seen during exploration

- **Status 200 with ~145 bytes, body contains "Javascript aktivert"** — this
  is a **collection mismatch signal**, not a session problem. It means you've
  hit the wrong SIV/STR collection. The fix is always to try the counterpart
  (`HRSIV` → `HRSTR` or vice versa). Diagnostic rule: `if len(result) < 500
  and "Javascript aktivert" in result`, retry with the other collection before
  assuming failure. `isCollectionMismatch()` in `lovdata_pro.js` detects this
  automatically and `tryPaths()` swaps the collection.
- **Status 200 with 4,765 bytes and title `LovdataPro`** — this is a
  client-side redirect stub. The URL is valid syntactically but the slug
  doesn't resolve to a Pro document. Treat this byte-count as a sentinel for
  "not found" alongside the 404/803-byte feilmelding page.
- **Status 200 with ~7,000-7,500 bytes and the document title set** — for
  forarbeider, this is the TOC-only stub returned without `/*`. Refetch with
  `/*` appended.
- **Status 404 + `Lovdata - feilmelding`** — straightforward: the slug is
  wrong. Fall back to Pro search.
- **A real page with a title and metadata but no body text** — header-only
  records (St.prp. and other non-law propositions, pre-1985 NOUs under
  `PUBG`, some meldinger). `load()` succeeds; the giveaway is
  `totalChars: 0`, which it now reports as `metadataOnly: true` with a
  warning. Nothing can be quoted from these.
- **A judgment with no headings at all** — HR-2016-2554-P and LG-2008-135938
  have zero `h1`–`h6`, so `toc` is empty and `section()` returns
  `no_headings`. Use `grep()`/`page()`. Some tingrett decisions do have
  headings, so this varies by document.
