---
name: lovdata-pro
description: >
  Use for Norwegian legal sources behind the Lovdata Pro login that the free
  `lovdata-api` skill lacks: case law (Høyesterett, lagmannsrett, tingrett,
  special courts such as Trygderetten, Arbeidsretten, jordskifte), forarbeider and
  Storting documents, rundskriv, uttalelser (Lovavdelingen, Sivilombudet),
  decisions of nemnder (KOFA, Finansklagenemnda …), and the history of laws and
  regulations (earlier and original texts, repealed acts, Lovtidend, local
  forskrifter). Needs the Cowork built-in browser. Triggers: references like
  HR-YYYY-N, Rt. YYYY s. N, RG, LB-/LG-YYYY-N, TOSL-YYYY-N, TRR-, AR-, ND YYYY s.
  N, KOFA-, FinKN-, SOM-, JDLOV-, rundskriv G-2019-3, Ot.prp./Prop. N L, NOU
  YYYY:N, Innst., LOV-/FOR-; asks like "find the Holship judgment", "hent
  forarbeidene til mineralloven", "aml. § 14-9 slik den lød i 2019", "Norske Lov
  1687 as enacted". Use even if Lovdata isn't named. Do NOT use for: current
  lov/forskrift text (lovdata-api); Meld. St.; finding a lawyer; legal theory that
  needs no document text.
---

# Lovdata Pro — rettspraksis, forarbeider, rundskriv, uttalelser og nemnder

**Første steg, før alle kommandoer:** finn `{SKILL_DIR}` som beskrevet under «Skill-katalogen» nedenfor, og bruk den utskrevne stien bokstavelig. Gjett den aldri (f.eks. `/mnt/skills/...`).

Dette dokumentet er på norsk. **Svaret til brukeren skrives på brukerens
språk** (engelsk → engelsk, bokmål → bokmål, også når kilden er på nynorsk
eller dansk; blandet → norsk). Sitater beholdes på originalspråket.

**Dekning** (kategoriene i nye Lovdata Pro): rettsavgjørelser (alminnelige
domstoler, spesialdomstoler som Trygderetten, Arbeidsretten og
jordskiftedomstolene, publikasjoner som Nordiske Domme i
Sjøfartsanliggender), forarbeider og stortingsdokumenter, rundskriv og
uttalelser, nemnder og utvalg, og det historiske for lover og forskrifter:
tidligere versjoner, vedtatt tekst, opphevede lover, Lovtidend og lokale
forskrifter. Gjeldende lovtekst alene: `lovdata-api`.

**Verktøy.** Skill-en henter dokumentene i brukerens innloggede sesjon i
Claude Desktops innebygde browser, og virker ikke uten den (se Steg 0). To
hjelpescript:

- `scripts/lovdata_ref.py` (Bash, ingen nettverk): referanse → kandidatstier.
- `scripts/browser/lovdata_pro.js`: limes inn i fanen (Steg 0) og gjør
  henting, tekst, søk og sitatkontroll.

All henting skjer i browser-panelet. Bash kan ikke nå lovdata.no
(sky-sandkassen har Anthropics IP: 405; lokal shell er ikke innlogget):
ikke prøv `curl` e.l.

**Skill-katalogen (`{SKILL_DIR}`).** Kjør alltid dette én gang før første kommando, også når «Base directory for this skill:» er oppgitt: den stien virker for å lese filer, men shellet ser den ofte ikke.
Bruk den utskrevne stien bokstavelig i senere kommandoer:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/lovdata-pro}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/lovdata-pro/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```
Erstatt `{SKILL_DIR}` nedenfor med den stien.

**Referansefiler** (les dem når oppgaven trenger dem):

- `references/lover-historikk.md` — lover og forskrifter slik de lød før,
  slik de ble vedtatt, opphevede lover, Lovtidend, endringslover.
- `references/klassisk.md` — Lovdata Pro Klassisk (dokumenter nye Pro
  mangler) og lese-ruten når innlimingen avvises.
- `references/lovdata-pro-mapping.md` — samlinger, prefikser, slug-regler og
  dekningsgrenser.

**En lov eller forskrift oppgitt bare med navn** («arbeidsmiljøloven»,
«den gamle arbeidsmiljøloven fra 1977»): ta aldri dato og nummer fra
hukommelsen, heller ikke når du er sikker. Slå dem opp først (Steg 1), før
du bruker dem noe sted, også i argumentene til Skill-kallet og i `resolve`.

---

## Steg 0 — sesjon (alltid først, hver ny samtale)

1. **Browserverktøyene.** Kjør ett ToolSearch-kall med query
   `Claude_Browser` og `max_results` 64, og bruk prefikset som kommer
   tilbake (`mcp__Claude_Browser__…` lokalt, `mcp__remote-devices__Claude_Browser__…`
   i skyen); filen omtaler verktøyene med suffiks (`tabs_context`,
   `preview_start`, `navigate`, `javascript_tool`). Finnes de ikke (f.eks. i
   Claude Code CLI): stopp og si at skill-en trenger de innebygde
   browserverktøyene i Claude Desktop.
2. **Fanen.** `tabs_context`: finnes en fane på `pro2.lovdata.no`, gjenbruk
   den. Ellers `preview_start` med

   **Standard: `https://pro2.lovdata.no/`** (nye Lovdata Pro)

   Står en annen skills fane fremme (f.eks. nb.no), åpne en egen fane med
   `tabs_create` + `navigate`, ellers mister den andre skill-en hjelperen sin.
   Trenger du Lovdata Pro Klassisk, se `references/klassisk.md`.
   **Naviger aldri fanen bort, og aldri til en dokumentside**
   (`/dokument/…`): hjelperen og cachen forsvinner, og Pro skriver besøket
   inn i brukerens historikk (smulesti).
   Ber et verktøy om tilgang og `request_access` finnes:
   `request_access {url: "https://pro2.lovdata.no/", scope: "site"}`.
3. **Hjelperen.** Sjekk først om den alt er der: `javascript_tool` med
   `[window.__lp && __lp.VERSION, window.__lp && __lp.SITE]`, og
   `grep -m1 "HELPER_VERSION = " {SKILL_DIR}/scripts/browser/lovdata_pro.js`
   i Bash. Samme versjon og `SITE` = `pro2`: hopp til punkt 4.
   Ellers: kjør `python3 {SKILL_DIR}/scripts/browser/paste_site.py pro2`, les
   filen den skriver ut, og send **hele** innholdet via `javascript_tool`
   (`action: "javascript_exec"`) uten å legge til noe. Svaret skal være
   `[VERSION, SITE]` (f.eks. `["1.5.1", "pro2"]`; versjonen er hjelperens `HELPER_VERSION`). Virker ikke
   `paste_site.py`: `python3 {SKILL_DIR}/scripts/browser/paste.py
   {SKILL_DIR}/scripts/browser/lovdata_pro.js` (begge nettstedene).
   **Innlimingen er ikke valgfri** og kortes aldri ned: ikke hopp over den
   fordi den er stor, og ikke erstatt den med `get_page_text` eller egne kall
   til Pro-ets API. Avvises den av en sikkerhetssjekk: se lese-ruten i
   `references/klassisk.md`.
4. **Innlogging.** `await __lp.isLoggedIn()`.
   - Ikke innlogget → si: *"Logg inn på Lovdata Pro i browser-panelet
     (SSO/FEIDE går fint). Si fra når du er inne."* Vent, og kjør
     `isLoggedIn()` igjen. **Skriv aldri inn brukernavn/passord, og be aldri
     brukeren oppgi dem til deg.**
   - Innlogget → bruk samme fane til alt videre.
5. **Lovdatas KI-vilkår.** Første gang i en samtale: si i én setning, på
   brukerens språk, at Lovdatas brukervilkår bare tillater Pro-innhold i
   KI-verktøy som ikke bruker det til trening, så brukeren bør ha slått av
   «Help improve our AI models» (Settings → Privacy; gjelder ikke Team- og
   Enterprise-planer). Ikke be om bekreftelse og ikke stopp. Arbeider du for
   en annen agent, ta setningen med i svaret ditt.

Navigering, innliming og `isLoggedIn()` kan slås sammen i ett
`browser_batch`-kall (med `navigate`; `preview_start` kan ikke batches).

---

## Steg 1 — oppslag av referanse

```bash
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "HR-2016-2554-P"
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "Ot.prp. nr. 3 (1998-99)" --json-array
```

Svaret er `{input, parsed, candidates}` (med `--json-array` bare
kandidatlisten, klar for `__lp.load([...])`), og når de er aktuelle:

- **`pinpoint`** — presiseringen som ble skilt ut («avsnitt 77», «s. 1827»,
  «punkt 3.4», «para. 77», «at p. 1827»). Søk etter den med `grep` og ta den
  med i sitatet.
- **`pro2_ref`** — Lovdatas kortform (`avgjorelse/rt-2000-1811`) for Rt., RG,
  ND, NAD, ARD, Utv. og prefikser skriptet ikke kjenner. `load(pro2_ref)`
  finner selv dommen (Rt. 2000 s. 1811 = `HRSIV/avgjorelse/hr-2000-49-b`);
  med `/s<side>` (`avgjorelse/rt-2000-1811/s1827`) svarer `load()` med
  `part: "s1827"`.
- **`search_hint`** — ved `parsed:false`: søkestrengen i Lovdatas egen form
  (`Rt-2000-1811`) for Steg 3.
- **`forarbeider`** — for en lov: `RFA/lov/<dato>-<nr>`, Lovdatas register
  over lovens forarbeider.
- **`note`** — hva du bør vite (lover; nyere `SDOK` finnes ofte bare som PDF;
  St.prp. er ikke fulltekst i Pro: si det i stedet for å sitere fra andre
  kilder. Meld. St. dekkes ikke av skill-en: ikke søk etter dem i Lovdata;
  kanonisk kilde er regjeringen.no).

`parsed:false`: prøv `load(pro2_ref)`; ellers Steg 3 med `search_hint`, og
verifiser treffet.

**Andre referanser.** Spesialdomstoler, nemnder, uttalelser og rundskriv
siteres `PREFIKS-ÅR-NUMMER` (TRR-2026-695, KOFA-2026-1389, FinKN-2026-1252,
SOM-2025-2770, JDLOV-2024-5261, G-2019-3); id-en er referansen med små
bokstaver, også for «rundskriv G-01/2016» (`g-2016-1`). Mangler et suffiks
(ND-2025-23 er `nd-2025-23-23s`), finner `load()` det selv. Også Dokument 8,
Dokument 12, Ot.meld., Besl. O., Lovvedtak og statsrådsforedrag (PRE-…).
Lover og forskrifter (`LOV-2005-06-17-62`, «lov 17. juni 2005 nr. 62») gir
kortformen `lov/2005-06-17-62`, som går til gjeldende, opphevet eller
Lovtidend-tekst.

**En lov oppgitt bare med navn:** finn den med
`search("<navn>", 5, { bases: ["NL"] })` (`["NLO"]` for en opphevet lov,
`["SF"]`/`["SFO"]` for forskrifter) eller `lovdata-api`, og bruk `path` fra
treffet (rett i `load()`, uten `resolve`). Oppslaget kommer først, ikke som
bekreftelse etterpå.

---

## Steg 2 — hent og les dokumentet

```javascript
await __lp.load(["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"])
```

Svaret er `{path, title, metadata, totalChars, toc}` eller `{error, detail}`
(se Feilhåndtering). Dokumentet caches i fanen, så videre kall er gratis.
Bruk alltid `path` fra svaret (feil samling rettes automatisk:
`redirectedFrom`; en kortform gir `via`). `part` sier hvor en referanse
peker (`s1827`); finn stedet med `grep`.

Flagg i svaret:

- **`metadataOnly`** — ingen brødtekst i Pro (St.prp., eldre NOU under
  `PUBG`). Sitér ikke fra posten. **`originalFile`** er
  original-PDF-en (nyere `SDOK`), **`publication`** publikasjonen med
  teksten: gi brukeren lenken, hent den ikke selv. **Hent heller ikke
  teksten andre steder** (WebFetch, curl, nye faner på regjeringen.no
  e.l.): si at Lovdata ikke har teksten, gi lenken du har, og stopp der.
- **`alternatives`** — flere dokumenter deler referansen; `load()` tok det
  første. Sjekk tittelen.
- **`noHeadings`** — ingen overskrifter (vanlig for dommer): bruk `grep` og
  `page`, ikke `section`.
- **`tocNext`** — innholdsfortegnelsen var for stor til ett svar. Hent resten
  med `await __lp.toc(path, tocNext)`, videre med `next` til den er `null`.

**Lesing.**

```javascript
await __lp.grep(path, "slutning", 600, 20)   // {matches, hits: [{i, sectionTitle, offset, snippet}]}
await __lp.page(path, offset)                 // {offset, next, total, text}
await __lp.section(path, i)                   // én seksjon fra toc
await __lp.toc(path, start)                   // resten av toc
```

- `grep` er bokstavelig (`"§ 4-6 (2)"` og `"(77)"` virker som de står),
  skiller ikke store og små bokstaver, og hopper over uthevingsmerker; `true`
  som femte argument gir et regulært uttrykk. `page(path, offset - 2000)` gir
  sammenhengen rundt et treff. `truncated: true`: senk `ctx`/`max`.
- Ingen funksjon svarer med mer enn ca. 45 000 tegn: gå videre med `next`,
  ikke `offset + 45000`. Store seksjoner har `{offset, next, total}`:
  `section(path, i, next)`.
- **Les aldri `__lp.cache` direkte** (verken `fullText`, `toc` eller `body`).
  Vil du ha ett kapittel, filtrer `toc` fra `load()`- eller `toc()`-svaret.
  Ser teksten feil ut, si det til brukeren; ikke undersøk markupen.

**Dommer:** avsnitt står som `(77) Teksten …`: `grep(path, "(77)", 600, 3)`.
Domsslutningen står under «Slutning»/«Domsslutning» (`grep(path,
"slutning")`, siste treff). Partene står i `metadata.Parter`. Er dommen
under 45 000 tegn, hent den med `page(path, 0)`.

**Forarbeider** (NOU, Prop., Innst., ofte 1–3 MB): velg kapitler fra `toc`
(hent alt med `tocNext` først), finn stedet med `grep`, hent med `section`.
Hele dokumentet bare når brukeren ber om en lokal kopi: løkke over `page`
til `next` er `null`, skriv til `/mnt/user-data/outputs/<slug>.md`, og si på
forhånd omtrent hvor mange kall det tar.

**Lover og forskrifter, historikk:** les `references/lover-historikk.md`
før du svarer. Det viktigste: tidligere versjoner med
`__lp.versions("lov/<id>", { asOf: "ÅÅÅÅ-MM-DD" })`; lag aldri en
`HIST`-sti selv; loven slik den ble vedtatt siteres fra Lovtidend
(`LTI/lov/<id>`), med datoen den trådte i kraft; Norske Lov 1687 er den
eldste versjonen i `versions("lov/1687-04-15")`.

**Sitatkontroll:** kopier sitater ordrett fra et svar, og kontroller dem før
du svarer, ett kall per dokument (se «Før du svarer»):

```javascript
await __lp.checkQuotes(path, ["<sitat 1>", "<kort frase>", "<tittel>"])
// {allFound, checked, quotes: [{n, matches, inMetadata, ignoringCase}]}
```

Sjekken leter i teksten, tittelen og metadata, skiller store og små
bokstaver og tåler uthevingsmerker og linjeskift. `matches: 0` betyr et
avvik (et ord, en bokstav, et tegn, to biter satt sammen); `ignoringCase`
over 0 betyr at bare store og små bokstaver avviker. Finn stedet igjen og
rett sitatet.

---

## Steg 3 — søk

Når `resolve` ga `parsed:false` uten `pro2_ref`, når `load()` gir
`not_found`, eller når brukeren spør etter dokumenter om et tema.

```javascript
await __lp.search("tomtefeste", 10, { bases: ["HRA"] })
await __lp.search("taushetsplikt", 10, { bases: ["JDLOV"], sort: "date" })
```

Svaret er `{query, totalHits, nextOffset, results: [{path, title, date,
status}]}`.

- **Nyeste først:** `sort: "date"`, når brukeren spør etter de nyeste eller
  «fra 2020 og senere»; relevansrekkefølgen blander årene.
- **Flere treff:** `search(…, { offset: nextOffset })` (samme `sort` og
  `bases`); `nextOffset` mangler på siste side.
- Treffene er dokumentene der søkeordet står, og `totalHits` er alle. En
  datosortert liste er fullstendig for søkeordet: ikke `load()` treffene for
  å kontrollere den; søk heller på andre ord eller ordformer. Velg ut fra
  titlene hvilke treff som handler om spørsmålet, og `load()` bare dem du
  siterer fra. Er nyeste treff gammelt, er det svaret: si at det ikke finnes
  nyere dokumenter med søkeordet, i stedet for å lete gjennom nyere
  dokumenter uten det.
- Søket treffer innhold, ikke bare dokumentet du mener: et søk på
  «St.prp. nr. 100 1991-92 EØS-avtalen» gir EU-direktiver. **Verifiser
  tittelen** med `load()` før du siterer.
- `noDocument: true` er register- og listeoppføringer: ikke `load()` dem.
  Karnov-kommentarer og litteratur er tatt bort. Søket legges ikke i
  brukerens historikk. Skriv aldri egne kall til Pro-ets søke-API.

`bases` tar samlings- eller gruppekoder; treffene kan ligge i undersamlinger
(`FINKN` gir `FINKNF`, `FINKNB`, `FINKNI`):

| Kategori | Gruppekode | Eksempler på samlinger |
|---|---|---|
| Alle rettsavgjørelser | `AVG` | `HRA` (hele Høyesterett), `LRA`, `TRA`, `LBSIV`, `TRSIV` |
| Spesialdomstoler | `SD` | `TRR`, `ARD`, `JSR`, `JSO`, `UTMA` |
| Publikasjoner | `PUB` | `NDS` (ND), `NDSENG`, `NAD` |
| Forarbeider og stortingsdokumenter | `FSA` | `NOU`, `PROP`, `INNST`, `REPFOR`, `GLFOR`, `SDOK`, `LOVVED`, `OTMELD`, `PRE` |
| Rundskriv og uttalelser | `ROU` | `RUNDSKRIV`, `UTTALELSER`; `RDEP`, `JDLOV`, `SOMB`, `BFU`, `SKM` |
| Nemnder og utvalg | `NEMNDEROGUTVALG` | `KOFA`, `FINKN`, `DIN`, `PSN`, `TLN`, `HTU` |
| Lover og forskrifter | `LFA` | `NL`, `NLO`, `SF`, `SFO`, `LF`, `LFO` |
| Lovtidend | ingen | `["LTI", "LTII"]` |

`RT`, `UTV` og `FS` er ikke filtre (de gir alle avgjørelser): søk på
referansen (`Rt-1990-…`). Hele listen: `references/lovdata-pro-mapping.md`.

---

## Forarbeidene til en lov

1. **Har brukeren oppgitt lovens dato og nummer?** Hvis ikke: finn loven
   først (Steg 1, «En lov oppgitt bare med navn»), før `resolve` eller noe
   annet.
2. **Registeret:** `resolve "LOV-<dato>-<nr>"` gir `forarbeider:
   RFA/lov/<dato>-<nr>`. `load()` det og hent dokumentene listen nevner,
   typisk NOU, Prop. L / Ot.prp. og Innst.; alle hentes når brukeren ber om
   «forarbeidene».
3. **Kapitlene:** NOU-er og proposisjoner har ofte `tocNext`: hent hele
   `toc` før du lister kapitlene.

For forarbeidene til en *endring*: finn endringsloven med
`backlinks(lov, "endringslover")` og slå opp dens `RFA`.

---

## Sitatformat

- **Høyesterett**: *HR-2016-2554-P avsnitt 77*; **Rt.**: *Rt. 2000 s. 1811
  (Finanger I) på s. 1827*; **lagmannsrett**: *LG-2008-135938*
- **Forarbeider**: *Ot.prp. nr. 3 (1998-99) s. 12*, *NOU 2022: 8 punkt 3.4*
- **Spesialdomstoler, nemnder, uttalelser, rundskriv**: Lovdatas referanse
  (i `metadata.Saksnummer` eller tittelen): *KOFA-2026-1389 avsnitt 30*,
  *Rundskriv G-2019-3 punkt 2*, *ND 2025 s. 23*
- **Lover**: *arbeidsmiljøloven § 14-9* eller *LOV-2005-06-17-62 § 14-9*;
  tidligere versjoner og Lovtidend: se `references/lover-historikk.md`

Sitater står i anførselstegn («…»), gjerne med oversettelse eller
forklaring etter. Teksten har kildens kursiv og fet som `*…*` og `**…**`:
det er en del av teksten, så behold det (som kursiv/fet i svaret).
Overskrifter (`## …`) er uten uthevingsmerker; hevet skrift står som `m²`
eller `^TM^`; fotnoter som `[fn N]`.

**Aldri sitér eller parafraser fra hukommelsen:** hent dokumentet og sitér
fra det.

### Før du svarer

Gå gjennom utkastet før du sender det:

1. **Finn alle sitater.** Et sitat er all tekst fra Lovdata i anførselstegn
   («…», "…") eller i et blokksitat: også titler, korttitler, overskrifter,
   korte fraser, ord fra metadata og bokstav- og nummerpunkter. Tell dem.
2. **Send hvert av dem til `checkQuotes`**, ett kall per dokument, og rett
   det som får `matches: 0`. `checked` til sammen skal være lik antallet du
   talte.
3. **Ingen påstand om kontrollen.** Skriv ikke i svaret at sitatene er
   «kontrollert», «sjekket ordrett», «checked word for word» e.l.
4. **Språket:** svaret er på brukerens språk; bare sitatene er på
   originalspråket.
5. **Lenker** kan gis som `https://pro2.lovdata.no/dokument/<path>`, bare
   for dokumenter du har hentet med `load()`, med `path` fra det svaret.
   Åpne dem aldri selv.

---

## Feilhåndtering

Funksjonene kaster ikke: de svarer `{error, detail}`, og `detail` sier
som regel hva du skal gjøre.

- **`not_logged_in`** → be brukeren logge inn (Steg 0 punkt 4). Ikke debugg
  videre.
- **`not_found`** → sjekk referansen, prøv `pro2_ref` eller Steg 3. Sjekk
  dekningsgrensene i `references/lovdata-pro-mapping.md` (lovproposisjoner
  fra 1984/85, NOU-er fra 1994, innstillinger fra 1991/92).
- **`missing_json`**, **`static_file`** → dokumentet har ingen tekst i nye
  Pro: prøv Klassisk (`references/klassisk.md`), eller si det til brukeren.
- **`wrong_site`** → fanen står ikke på Lovdata Pro, eller kopien er for det
  andre nettstedet (`pasted`): `navigate` til standardadressen og lim inn
  `paste_site.py pro2`-kopien.
- **`cors`** → JS-en kjørte i en fane som ikke er på Lovdata Pro.
- **`before_first_version`**, **`bad_date`**, **`unsupported_kind`** →
  `references/lover-historikk.md`.
- **`pro2_only`** → kallet ble gjort i en Klassisk-fane: bruk fanen på nye
  Pro.
- **`unsupported_format`** → Lovdata har endret formatet: prøv Klassisk, og
  si at skill-en bør oppdateres.
- **Siden er ikke godkjent / brukeren avslo tilgang** → si det og stopp.
