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
  YYYY:N, Innst., Meld. St., LOV-/FOR-; asks like "find the Holship judgment",
  "hent forarbeidene til mineralloven", "aml. § 14-9 slik den lød i 2019", "Norske
  Lov 1687 as enacted". Use even if Lovdata isn't named. Do NOT use for: current
  lov/forskrift text (lovdata-api); finding a lawyer; legal theory that needs no
  document text.
---

# Lovdata Pro — rettspraksis, forarbeider, rundskriv, uttalelser og nemnder

**Første steg, før alle kommandoer:** finn `{SKILL_DIR}` som beskrevet under «Skill-katalogen» nedenfor, og bruk den utskrevne stien bokstavelig. Gjett den aldri (f.eks. `/mnt/skills/...`).

Dette ferdighetsdokumentet er på norsk. **Svaret til brukeren skal alltid
tilpasses brukerens eget språk** (samme regel som i `lovdata-api`-skill-en):
spørsmål på engelsk → svar på engelsk; norsk → norsk; blandet → norsk.
Sitater fra dommer og forarbeider beholdes alltid på originalt norsk.

Dekningen følger kategoriene i nye Lovdata Pro: rettsavgjørelser (alminnelige
domstoler, spesialdomstoler som Trygderetten, Arbeidsretten og
jordskiftedomstolene, og publikasjoner som Nordiske Domme i
Sjøfartsanliggender), forarbeider og stortingsdokumenter, rundskriv og
uttalelser, nemnder og utvalg, og lover og forskrifter for det historiske:
tidligere versjoner, opphevede lover og forskrifter, Lovtidend og lokale
forskrifter (gjeldende tekst alene: `lovdata-api`). Alt utenom alminnelige
domstoler og Prop./NOU/Innst. er kartlagt og testet bare i **nye Lovdata
Pro**; bruk den for disse.

Denne skill-en bruker Claude Desktops innebygde browserverktøy til å hente
Lovdata Pro-dokumenter direkte i brukerens innloggede sesjon. Den virker
**ikke** uten disse verktøyene (se Forutsetninger).

Du har tilgang til to hjelpescript:

- `scripts/lovdata_ref.py` — rent Python, ingen nettverkstilgang. Oversetter
  en referanse til kandidat-Pro-stier. Kjøres via bash/terminal.
- `scripts/browser/lovdata_pro.js` — limes inn i browser-fanen via
  `javascript_tool`. Gjør selve hentingen, seksjoneringen og søket.
  `scripts/browser/paste_site.py` lager kopien for nettstedet fanen står på
  (Steg 0).

**Skill-katalogen (`{SKILL_DIR}`).** Kjør alltid dette én gang før første kommando, også når «Base directory for this skill:» er oppgitt: den stien virker for å lese filer, men shellet ser den ofte ikke.
Bruk den utskrevne stien bokstavelig i senere kommandoer:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/lovdata-pro}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/lovdata-pro/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```
Erstatt `{SKILL_DIR}` nedenfor med den stien.

For komplette URL-mønstre, samlingsforkortelser og slug-regler, se
`references/lovdata-pro-mapping.md`.

---

## Forutsetninger

Denne skill-en krever at de innebygde browserverktøyene (f.eks.
`preview_start`, `navigate`, `javascript_tool`) er tilgjengelige. Finn dem med
ToolSearch som beskrevet under. **Hvis de ikke finnes** (for eksempel i Claude
Code CLI): stopp og si til brukeren at denne skill-en trenger de innebygde
browserverktøyene i Claude Desktop (Cowork, eller Code-fanen der de er
tilgjengelige).

**Browserverktøy.** Prefikset til den innebygde browserens verktøy varierer (`mcp__Claude_Browser__…` i lokal Cowork,
`mcp__remote-devices__Claude_Browser__…` i sky-Cowork). De er ofte utsatt (deferred): kjør ett ToolSearch-kall med
query `Claude_Browser` og `max_results` 64, og bruk prefikset som kommer tilbake. Denne filen omtaler verktøyene bare
med suffiks (`tabs_context`, `preview_start`, `navigate`, `javascript_tool`, …). `request_access` finnes ikke i alle
miljøer; mangler det, gå rett til `preview_start`/`navigate`.

## Hvor hvert steg kjøres

| Steg | Hvor |
|---|---|
| Innlogging, navigering, henting, seksjonering og søk (`lovdata_pro.js`) | **Browser-panelet** (brukerens IP og innlogging) |
| Oppslag av referanse (`lovdata_ref.py`, ingen nettverkstilgang) | **Bash** (sky-sandkasse eller lokal) |

All henting skjer i browser-panelet. Ingen av shellene kan kalle lovdata.no
direkte (sky-sandkassen: 405; lokal shell: ikke innlogget) — ikke prøv `curl`
e.l. mot lovdata.no fra `Bash`.

Cowork kjører i skyen: `Bash` har Anthropics IP, ikke brukerens; bare browser-panelet har med sikkerhet brukerens IP og innlogginger.

---

## Steg 0 — sesjon (alltid først, hver ny samtale)

1. `tabs_context` — se om det allerede finnes en fane på `lovdata.no/pro`
   eller `pro2.lovdata.no`. Gjenbruk den om den finnes (cachen i
   `window.__lp` dør ved navigering, så ikke naviger fanen bort for annet
   enn søk i Klassisk — se Steg 3). **Naviger aldri til en dokumentside**
   (`pro2.lovdata.no/dokument/…`, `#document/…`) for å lese den: hjelperen
   og cachen forsvinner, og Pro-appen skriver besøket inn i brukerens
   historikk (smulesti). Er det ingen faner: `preview_start` med
   **standardadressen**:

   **Standard: `https://lovdata.no/pro/?forceFullVersion=true`** (Lovdata Pro Klassisk)

   Hjelperen virker på begge Lovdata Pro-utgavene, med samme funksjoner:
   **nye Lovdata Pro** (`pro2.lovdata.no`; innlogging fører dit fra
   26.11.2026) og **Lovdata Pro Klassisk** (`lovdata.no/pro`, tilgjengelig
   ut 2027). `isLoggedIn()` og `load()` svarer med `site: "pro2"` på nye
   Pro. Står fanen et annet sted, svarer kallene `wrong_site`. Fungerer ikke
   den ene utgaven (innlogging, feil eller manglende dokument), prøv den
   andre: `https://pro2.lovdata.no/` eller
   `https://lovdata.no/pro/?forceFullVersion=true`.
   Står en annen skills fane åpen (f.eks. nb.no), åpne en egen fane med
   `tabs_create` og `navigate` — `preview_start` gjenbruker fanen som er
   fremme, og den andre skillen mister da hjelperen sin.
2. Hvis `request_access` finnes og et verktøy rapporterer at siden ikke er
   godkjent ennå: `request_access {url: "https://lovdata.no/pro/", scope: "site"}`
   (på nye Pro: `https://pro2.lovdata.no/`) og prøv igjen.
3. Last inn hjelperen.
   **Sjekk først om den alt er der:** `javascript_tool` med
   `[window.__lp && __lp.VERSION, window.__lp && __lp.SITE]`, og
   `grep -m1 "HELPER_VERSION = " {SKILL_DIR}/scripts/browser/lovdata_pro.js`
   i Bash. Er versjonen den samme og `SITE` er nettstedet fanen står på
   (`pro2` eller `klassisk`), er hjelperen klar: hopp til punkt 4.
   **Ellers:** kjør `python3 {SKILL_DIR}/scripts/browser/paste_site.py pro2`
   i Bash når fanen står på nye Pro (`pro2.lovdata.no`), `… paste_site.py
   klassisk` på `lovdata.no/pro`. Den skriver en kopi med bare koden for det
   nettstedet, uten kommentarer og innrykk (ca. 36 000 tegn for nye Pro,
   29 000 for Klassisk), og skriver ut stien. Les den filen og send **hele**
   innholdet via `javascript_tool` (`action: "javascript_exec"`), uten å
   legge til noe: kopiens siste linje gjør at svaret er `[VERSION, SITE]`
   (f.eks. `["1.4.4", "pro2"]`), og det bekrefter at innlimingen virket.
   Virker ikke `paste_site.py`, bruk `python3 {SKILL_DIR}/scripts/browser/paste.py
   {SKILL_DIR}/scripts/browser/lovdata_pro.js` (begge nettstedene, ca.
   44 000 tegn). Kort aldri ned hjelperen.
   **Innlimingen er ikke valgfri.** Den koster én lang melding, men alt
   annet i skill-en bygger på den: ikke hopp over den fordi den er stor, og
   ikke erstatt den med `get_page_text` eller egne kall til Pro-ets API.
   Idempotent — trygt å lime inn flere ganger i samme fane. En annen versjon
   (fra før en skill-oppdatering) eller kopien for det andre nettstedet
   byttes ut (cachen tømmes).
   **Avvises innlimingen av en sikkerhetssjekk**, ikke prøv samme kall igjen.
   Si det til brukeren med én setning og bruk lese-ruten: logg inn (punkt 4 uten
   `isLoggedIn()` — spør brukeren), `navigate` til
   `https://lovdata.no/pro/#document/<path>` (path fra Steg 1, f.eks.
   `HRSIV/avgjorelse/hr-2016-2554-p`), vent et par sekunder og les med
   `get_page_text` (eller `read_page`). Åpnes dokumentet i nye Lovdata Pro
   (`pro2.lovdata.no/dokument/…`), les det der på samme måte; på nye Pro
   kan du også `navigate` direkte til `https://pro2.lovdata.no/dokument/<path>`.
   Søk skjer som i fallbacken i Steg 3, med `get_page_text` i stedet for
   `readSearchResults`. Lese-ruten har ingen
   `grep`/`section`/biter: lange dokumenter kan bli avkortet, så si fra hvis
   teksten slutter brått, og sitér bare det siden faktisk viser. På nye Pro
   er den særlig upålitelig: `get_page_text` gir tom tekst når panelet er
   skjult, og lange dokumenter tegnes bare delvis (målt: ca. 10 000 tegn).
   Lese-ruten skriver også besøkene inn i brukerens historikk.
4. Kjør `await __lp.isLoggedIn()`. På nye Pro spør den Pro-ets API
   (`source: "api"`). I Klassisk avgjøres svaret på `#myPage` av
   `document.title`; står fanen på et dokument, gjør funksjonen i stedet et
   lite prøveoppslag mot Pro (`source: "probe"`).
   - **Ikke innlogget** → si til brukeren: *"Logg inn på Lovdata Pro i
     browser-panelet (SSO/FEIDE går fint). Si fra når du er inne."* Vent på
     bekreftelse, kjør `isLoggedIn()` på nytt. **Skriv aldri inn
     brukernavn/passord selv, og be aldri brukeren oppgi dem til deg** —
     innlogging skjer utelukkende i browser-panelet.
   - **Innlogget** → gå videre. Fane-id-en er "sesjonshåndtaket" for resten
     av samtalen; gjenbruk samme fane til alt under.

Du kan slå sammen navigering + paste + `isLoggedIn()`-sjekk i ett
`browser_batch`-kall for å spare turer — men bare med `navigate`;
`preview_start` kan ikke batches (en batch som starter med `navigate` åpner
panelet selv).

**Lovdatas KI-vilkår.** Første gang skill-en brukes i en samtale: si i én
setning, på brukerens språk, at Lovdatas brukervilkår bare tillater
Pro-innhold i KI-verktøy som ikke bruker det til trening, så brukeren bør
ha slått av «Help improve our AI models» (Settings → Privacy; gjelder ikke Team-
og Enterprise-planer). Du kan ikke se innstillingen selv: ikke be om
bekreftelse og ikke stopp arbeidet. Arbeider du for en annen agent (uten
egen kontakt med brukeren), ta setningen med i svaret ditt.

---

## Steg 1 — oppslag av referanse

```bash
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "<referanse>"
```

Eksempler:

```bash
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "HR-2016-2554-P"
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "Ot.prp. nr. 3 (1998-99)"
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "NOU 2022:8"
```

Returnerer `{input, parsed, candidates}` pluss disse feltene når de er
aktuelle:

- **`pinpoint`** — presisering som ble skilt ut av referansen («avsnitt 77»,
  «s. 1827», «punkt 3.4», og engelske former som «para. 77», «paras 77–80»,
  «at p. 1827», «section 3.4»). Bruk den som søkeord i `grep`/`section`
  etter at dokumentet er lastet, og ta den med i sitatet.
- **`search_hint`** — når `parsed:false`: søkestrengen som fungerer best i
  Pro, i Lovdatas egen referanseform (`Rt-2000-1811`, `RG-2010-100`), ikke
  prosasiteringen.
- **`pro2_ref`** — for Rt. og RG: Lovdatas kortform (`avgjorelse/rt-2000-1811`).
  På nye Pro tar `load()` den direkte og finner den underliggende dommen
  (Rt. 2000 s. 1811 = `HRSIV/avgjorelse/hr-2000-49-b`); legg til `/s<side>`
  for en side (`avgjorelse/rt-2000-1811/s1827`), så svarer `load()` med
  `part: "s1827"`. I Klassisk: søk på `search_hint`. Det samme gjelder
  andre samlinger sitert med år og side (ND 1990 s. 140, NAD, ARD, Utv.) og
  Lovdata-referanser med et prefiks skriptet ikke kjenner (eldre navn som
  BKN-, LKN-, ENV-): `pro2_ref` er da `avgjorelse/<referansen med små
  bokstaver>`, og nye Pro finner samlingen selv.
- **`note`** også på løste referanser når det er noe å vite: lover og
  forskrifter, og `SDOK` (nyere stortingsdokumenter finnes ofte bare som PDF).
- **`forarbeider`** — for en lov: `RFA/lov/<dato>-<nr>`, Lovdatas register
  over lovens forarbeider (se Arbeidsflyt).
- **`note`** — hvorfor referansen ikke kunne løses, og hvor dokumentet
  faktisk ligger. Disse tilfellene er verdt å kjenne:
  - **Rt./RG** — slug-suffikset er Lovdata-tildelt. Nye Pro: `load(pro2_ref)`.
    Klassisk: søk på `search_hint`.
  - **Meld. St. / St.meld.** — finnes bare i Klassisk, i `STS/forarbeid/stsg-<sesjon>-<løpenummer>`
    (Meld. St. 17 (2020-2021) = `STS/forarbeid/stsg-202021-355`). Løpenummeret
    kan ikke utledes av referansen; søk med referansen i anførselstegn
    (`"Meld. St. 17 (2020-2021)"` — uten dem kommer bare Prop./NOU-treff) og
    verifiser tittelen på treffet.
    Nye Pro har ikke stortingsmeldinger.
  - **St.prp.** — ikke-lovproposisjoner er ikke fulltekstindeksert i Pro
    (og finnes ikke i nye Pro). Si det til brukeren i stedet for å sitere
    fra andre kilder.

**Referanser utenom de alminnelige domstolene.** Spesialdomstoler, nemnder,
uttalelser og rundskriv siteres med Lovdatas egen referanse
`PREFIKS-ÅR-NUMMER` (TRR-2026-695, AR-2026-38, KOFA-2026-1389,
FinKN-2026-1252, SOM-2025-2770, JDLOV-2024-5261, BFU-2026-5, RA-2026-819,
G-2019-3, IS-2026-9003, RUDI-2026-6); dokument-id-en er referansen med små
bokstaver. `resolve` slår opp samlingen i en prefikstabell
(`references/lovdata-pro-mapping.md`), også for departementenes egen form
(«rundskriv G-01/2016» = `g-2016-1`). Mangler et suffiks som id-en har
(ND-2025-23 er `nd-2025-23-23s`), finner `load()` det likevel på nye Pro.
Forarbeider og stortingsdokumenter utover Prop./NOU/Innst.: Dokument 8 /
Representantforslag, Dokument 12 / Grunnlovsforslag, andre Dokument-serier,
Ot.meld., Besl. O., Lovvedtak og statsrådsforedrag (PRE-2026-11-20-2434).
Lover og forskrifter: `LOV-2005-06-17-62`, `FOR-2011-12-06-1360`, «lov 17.
juni 2005 nr. 62»; kandidaten er kortformen `lov/2005-06-17-62`, som nye Pro
løser til gjeldende tekst (`NL`, `SF`, `LF`), opphevet tekst (`NLO`, `SFO`,
`LFO`) eller, for en endringslov uten konsolidert tekst, Lovtidend (`LTI`).
Se Steg 2b for tidligere versjoner.

**En lov eller forskrift oppgitt bare med navn** («arbeidsmiljøloven»,
«den gamle arbeidsmiljøloven fra 1977»): slå opp dato og nummer **før du
bruker dem noe sted**, også før `resolve` og i argumentene til Skill-kallet,
med `search("<navn>", 5, { bases: ["NL"] })` (`["NLO"]` for en
opphevet lov, `["SF"]`/`["SFO"]` for forskrifter) eller `lovdata-api`, og
bruk `path` fra treffet (det kan gå rett i `load()`, uten `resolve`). Ta
aldri dato og nummer fra hukommelsen, heller ikke når du er sikker, og
heller ikke for å «bekrefte» dem etterpå: oppslaget kommer først.

Bruk `--json-array` for å få bare kandidatlisten (nyttig til å lime rett inn
i `__lp.load([...])`):

```bash
python3 {SKILL_DIR}/scripts/lovdata_ref.py resolve "HR-2016-2554-P" --json-array
# ["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"]
```

Hvis `parsed:false` (typisk pre-2008 Rt.-dommer, RG-dommer, uvanlige
referanseformer): på nye Pro, prøv `load(pro2_ref)` hvis feltet finnes;
ellers hopp til **Steg 3 — søk**, og søk på `search_hint`.

---

## Steg 2 — hent dokument

```javascript
await __lp.load(["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"])
```

Returnerer `{path, title, metadata, totalChars, toc}` (eller en
`{error: ...}`-payload — se **Feilhåndtering**). Dokumentet caches i fanen på
`path`, så alle videre kall (`section`, `grep`, `page`) på samme `path` er
gratis (ingen ny nettforespørsel). Bruk alltid `path` fra svaret i videre
kall: på nye Pro kan den avvike fra kandidaten (feil samling rettes
automatisk, `redirectedFrom`; en kortform gir `via`). `part` (nye Pro)
sier hvor i dokumentet en referanse peker (`s1827`, `k4-1-4`); finn stedet
med `grep`.

To flagg i svaret styrer hva du kan gjøre videre:

- **`metadataOnly: true`** (og `totalChars: 0`) — dokumentet finnes som
  metadatapost, men uten brødtekst i Pro. Typisk St.prp., eldre NOU under
  `PUBG`, og enkelte meldinger. **Ikke siter noe fra en slik post** — si til
  brukeren at fulltekst ikke finnes i Lovdata Pro. To unntak på nye Pro:
  **`originalFile`** er en lenke til original-PDF-en (nyere
  stortingsdokumenter, `SDOK`), og **`publication`** er publikasjonen som
  har teksten (Kommissariske Høyesterett 1941–45: Retstidende). Gi brukeren
  lenken; den åpnes i den innloggede browseren. Ikke hent PDF-en selv (den
  kan være over 30 MB).
- **`alternatives`** (nye Pro) — flere dokumenter deler referansen (samme
  Rt.-side, FKR-2022-4, OB-2024-4). `load()` tok det første; sjekk tittelen
  og velg et annet om det er feil.
- **`noHeadings: true`** (`toc` er tom) — dokumentet har ingen `h1`–`h6`.
  Dette er vanlig for dommer: både HR-2016-2554-P og LG-2008-135938 har null
  overskrifter. Da er `section()` ubrukelig; bruk `grep()` og `page()`.
- **`tocNext`** (med `tocTotal`) — innholdsfortegnelsen var for stor til ett
  svar, og `toc` inneholder bare de første oppføringene. Hent resten med
  `await __lp.toc(path, tocNext)`, som svarer `{start, next, total, toc}`;
  fortsett med `next` til den er `null`.

Velg videre strategi ut fra dokumenttype og størrelse:

- **Dommer** (vanligvis ≤ noen hundre KB): som regel ingen overskrifter, så
  bruk `grep(path, "<stikkord eller avsnittsnummer>")` for å finne stedet og
  `page(path, offset)` for å lese rundt det. Er hele dommen liten nok
  (`totalChars` under ~45 000 tegn — `PAGE_SIZE`, satt fra den målte grensen
  for hvor mye ett `javascript_tool`-svar tåler), hent den med `page(path, 0)`.
  Partene og prosessfullmektigene står ikke i brødteksten — de ligger i
  `metadata.Parter` (én linje per part).
  **Avsnittsnumre** står som `(77)`, ikke som «avsnitt 77»: på nye Pro
  først på avsnittets linje (`(77) Teksten …`), i Klassisk i en egen
  tabellcelle (`| (77) |`). Finn avsnitt 77 med
  `grep(path, "(77)", 600, 3)` — `term` er bokstavelig, så parentesene
  trenger ingen escaping — og les videre med `page(path, offset)`.
  **Domsslutningen** står under «Slutning», «SLUTNING» eller «Domsslutning»
  (tingrett ofte med store bokstaver): `grep(path, "slutning")` finner alle
  tre (`grep` skiller ikke mellom store og små bokstaver); ta det siste treffet.
- **Forarbeider** (NOU, Prop., Innst. — ofte flere MB): disse har `toc`
  (NOU 2022:8 har flere hundre; `toc` kommer da i flere
  omganger, se `tocNext`). Vis `toc` til brukeren eller velg selv
  relevante kapitler ut fra tittel/spørsmål. `grep(path, "søkeord")` finner
  riktig kapittel raskt; `section(path, i)` henter det ut.
  Lovdata bruker ikke `<ul>/<li>`: litra- og nummerpunkter kommer som
  én-rads tabeller, og `toText()` gjengir dem som innrykkede linjer
  («a. konsultere vedkommende folk …»), ikke som rørtabellrader.
- **Dump-modus** — kun når brukeren ber om en full lokal kopi eller
  uttømmende gjennomgang: løkke over `page(path, offset)` til `next` er
  `null`, og skriv hver `text` til `/mnt/user-data/outputs/<slug>.md` (bash `>>` mellom
  hvert kall). Si fra til brukeren på forhånd omtrent hvor mange kall det
  tar (`Math.ceil(totalChars / 45000)`).

**Kontroller alle sitater før du svarer**, i ett kall per dokument:

```javascript
await __lp.checkQuotes(path, ["<sitat 1>", "<sitat 2>", "<kort frase>"])
```

Det gjelder **alt** du setter i anførselstegn fra dokumentet, også korte
fraser, overskrifter, titler og sitater fra metadata (sjekken leter også
i `title` og `metadata`; `inMetadata` sier hvor mange treff som var der).
Kopier sitatene ordrett fra et `page`/`section`/`grep`/`load`-svar; sett
ikke sammen to biter med et tegn som ikke står i kilden. Svaret er
`{allFound, checked, quotes: [{n, matches, inMetadata, ignoringCase}]}`;
sjekken skiller mellom
store og små bokstaver og tåler uthevingsmerker og linjeskift. Er
`matches` 0 for et sitat, har det et avvik (et ord, en stor bokstav, et
tegn, en sammenstykket bit; `ignoringCase` over 0 betyr at bare store og
små bokstaver avviker): finn stedet igjen og rett det. Sitér aldri fra
hukommelsen av et tidligere svar. Hvordan du teller og oppgir sitatene,
står i «Før du svarer» nedenfor.

Eksempler på JS-kall:

```javascript
await __lp.section("HRSIV/avgjorelse/hr-2016-2554-p", 3)
await __lp.grep("NOU/forarbeid/nou-2022-8", "urfolk", 600, 20)
await __lp.page("PROP/forarbeid/otprp-3-199899", 0)
```

`grep(path, term, ctx, max, regex)` tolker `term` **bokstavelig** (og lar
mellomrom matche linjeskift), så «§ 4-6 (2)» og «art. 8(1)» virker som de
står, og den hopper over uthevingsmerkene (`*`, `**`) inne i en frase. Send
`true` som femte argument for et ekte regulært uttrykk (det ser merkene). Svaret er
`{matches, hits}`: `matches` er antall treff i hele dokumentet, `hits` de
første `max` av dem med `{i, sectionTitle, offset, snippet}`. `offset` er
der treffet står i teksten `page()` leser, så `page(path, offset - 2000)`
gir sammenhengen rundt. Får du `truncated: true`, fikk ikke alle `max` treff
plass i ett svar — senk `ctx`/`max` eller snevre inn søket.

Ingen funksjon svarer med mer enn `PAGE_SIZE` tegn, regnet som JSON (der
linjeskift og anførselstegn teller dobbelt). `page()` gir derfor ofte litt
under 45 000 tegn tekst; gå videre med `next`, ikke `offset + 45000`.
`section()` gjør det samme for store seksjoner: svaret har da `{offset, next,
total}`, og resten hentes med `section(path, i, next)`.

---

## Steg 2b — lover og forskrifter: historikk (bare nye Pro)

Tekstene ligger i flere samlinger med samme id: gjeldende (`NL`, `SF`, `LF`;
også `DEL`, `INS`, `STV`), opphevet (`NLO`, `SFO`, `LFO` …, teksten slik den
sist gjaldt, med endringsfotnoter), kunngjort i Lovtidend (`LTI` avd. I,
`LTII` avd. II: loven eller endringsloven slik den ble kunngjort, med
«Publisert i» og «Kunngjort»), engelsk oversettelse (`NLE`, `SFE`) og
**tidligere versjoner** i `HIST`.

```javascript
await __lp.versions("lov/2005-06-17-62")                          // alle versjoner, eldste først, gjeldende sist
await __lp.versions("lov/2005-06-17-62", { asOf: "2019-03-15" })  // versjonen som gjaldt den datoen
await __lp.versions("lov/2005-06-17-62", { part: "§14-9" })       // bare versjonene der § 14-9 endret seg
await __lp.backlinks("lov/2005-06-17-62", "endringslover")         // endringslovene (LTI), også ikrafttredelsesvedtak
await __lp.backlinks("lov/2005-06-17-62", "lovspeil")              // forgjenger- og etterfølgerlover
```

- En versjon er `HIST/<type>/<id>-<ÅÅÅÅMMDD>`, datoen versjonen gjelder fra
  i Lovdatas historikk, normalt ikrafttredelsen; `load()` den som et vanlig
  dokument. Den **første** versjonen kan ha en dato før loven trådte i kraft
  (arbeidsmiljøloven: `-20050701`, i kraft 1. januar 2006): for datoer nær
  lovens start, sjekk ikrafttredelsesbestemmelsen. **Lag aldri en HIST-sti med en
  annen dato selv:** Pro sender da stille til *gjeldende* tekst
  (`redirectedFrom` i svaret). Bruk `versions(…, { asOf })`, som velger den
  siste versjonen som trådte i kraft på eller før datoen.
- `checkCurrent` i svaret: datoen ligger etter siste historiske versjon, og
  Pro oppgir ikke når gjeldende tekst begynte å gjelde. Sammenlign med
  gjeldende tekst (endringsfotnotene der viser datoene) før du sier hva som
  gjaldt.
- Versjonene går ulikt langt tilbake: arbeidsmiljøloven 2005 til
  originalteksten, straffeloven 1902 glissent før 1980-årene, Grunnloven fra
  1814; opphevede forskrifter har ofte ingen. `before_first_version` betyr at
  Pro ikke har teksten fra så tidlig: si det, og bruk eventuelt
  Lovtidend-teksten (`LTI/lov/<id>`) for loven slik den ble vedtatt.
  Opphevede lover (`NLO`) har ofte ingen `HIST`-versjoner: `count: 0` med
  `part` betyr da ikke at paragrafen aldri ble endret. Se endringsfotnotene i
  teksten.
- `maybeCapped` i svaret: listen har nøyaktig 50 versjoner, som kan være en
  grense hos Pro. Er eldste versjon mye senere enn loven, kan versjoner
  mangle; for én paragraf gir `part` en egen liste.
- `part` tar §-id-en slik den står i dokumentet (`§14-9`, uten mellomrom).
- **Loven slik den ble vedtatt:** Lovtidend-teksten `LTI/lov/<id>` er
  loven som kunngjort. Den første `HIST`-versjonen er Lovdatas konsoliderte
  tekst fra den datoen; den er som regel lik, men det er Lovtidend som er
  den vedtatte teksten. Sitér fra `LTI` og oppgi «Norsk Lovtidend»; mangler
  `LTI` (eldre lover), bruk den første versjonen og si at det er Lovdatas
  tekst. Oppgi også **når loven trådte i kraft**: `metadata["I kraft fra"]`
  i `LTI`-posten, ellers ikrafttredelsesvedtaket
  (`backlinks(lov, "endringslover")`). «Kongen bestemmer» er ikke en dato.
- Christian Vs Norske Lov: `lov/1687-04-15` er bare bestemmelsene som
  fortsatt gjelder; hele originalteksten er den eldste versjonen
  (`versions("lov/1687-04-15")`, første oppføring; dansk, ca. 650 000 tegn). Landslova
  (1274) finnes som `NLO/lov/1274-06-24-nb`, `-nn` og `-non` (norrønt).
- Sitér med versjonen: *arbeidsmiljøloven § 14-9 (versjon i kraft fra
  1. januar 2019)*, og si at teksten er Lovdatas konsoliderte tekst.

---

## Steg 3 — søk

Brukes når `resolve` ga `parsed:false`, eller når et direkte slug-forsøk
feiler med `not_found`.

**Vanlig vei — ett JS-kall:**

```javascript
await __lp.search("Rt-2000-1811", 10)
await __lp.search("tomtefeste", 10, { bases: ["HRA"] })   // bare nye Pro
```

**På nye Pro** er `search()` ett API-kall, sortert etter relevans; svaret er
`{query, site: "pro2", filterBases, sort, offset, totalHits, nextOffset,
results: [{path, title, date}]}`.

- **Nyeste først:** `{ sort: "date" }`. Bruk det når brukeren spør etter de
  nyeste, «fra 2020 og senere» e.l.: relevansrekkefølgen blander årene, og
  de øverste treffene sier ingenting om hva som er nyest.
- **Flere treff:** ett kall gir én side; `search(…, { offset: nextOffset })`
  henter neste (samme `sort` og `bases`). `nextOffset` mangler på siste side.
- Skriv aldri egne kall til Pro-ets søke-API: `search()` dekker det.
- Treffene er dokumentene der søkeordet står i teksten, og `totalHits` er
  alle sammen. En datosortert liste er derfor fullstendig for det søkeordet:
  ikke `load()` treffene for å kontrollere den. Vil du dekke andre ord
  eller ordformer, søk på dem også i stedet for å lese dokumentene.

`bases` avgrenser til Lovdatas samlings- eller gruppekoder. Treffene kan
ligge i undersamlinger av koden du ga (`FINKN` gir `FINKNF`, `FINKNB`,
`FINKNI`):

| Kategori | Gruppekode | Eksempler på samlinger |
|---|---|---|
| Alle rettsavgjørelser | `AVG` | `HRA` (hele Høyesterett), `LRA`, `TRA`, `LBSIV`, `TRSIV` |
| Spesialdomstoler | `SD` | `TRR`, `ARD`, `JSR`, `JSO`, `UTMA` |
| Publikasjoner | `PUB` | `NDS` (ND), `NDSENG`, `NAD` |
| Forarbeider og stortingsdokumenter | `FSA` | `NOU`, `PROP`, `INNST`, `REPFOR`, `GLFOR`, `SDOK`, `LOVVED`, `OTMELD`, `PRE` |
| Rundskriv og uttalelser | `ROU` | `RUNDSKRIV`, `OPPHEVDERUNDSKRIV`, `UTTALELSER`; `RDEP`, `JDLOV`, `SOMB`, `BFU`, `SKM` |
| Nemnder og utvalg | `NEMNDEROGUTVALG` | `KOFA`, `FINKN` (alle Finansklagenemnda), `DIN`, `PSN`, `TLN`, `HTU` |
| Lover og forskrifter | `LFA` (`LOVER`, `SFA`, `SFOA`, `LOK`) | `NL`, `NLO`, `SF`, `SFO`, `LF`, `LFO` |
| Lovtidend | ingen: list samlingene | `["LTI", "LTII"]` |

`LFA` tar ikke med Lovtidend, og `LT` gir null treff: søk i Lovtidend med
`bases: ["LTI", "LTII"]`. Tidligere versjoner (`HIST`) er ikke søkbare;
finn loven og bruk `versions()`. Treffene har `status` når Pro oppgir den
(`REPEALED`, `ORIGINALLY_PROMULGATED`, `NOT_IN_FORCE`).

Hele listen står i `references/lovdata-pro-mapping.md`. `RT`, `UTV` og `FS`
(Retstidende, Utvalgte skattedommer, Rettens Gang) er ikke filtre: de gir
like mange treff som `AVG`. Søk heller på referansen (`Rt-1990-…`).
Treff med `noDocument: true` er register- eller listeoppføringer (f.eks.
`PUBG`) som ikke kan åpnes; ikke kall `load()` på dem.
Karnov-kommentarer og litteratur tas bort fra treffene (de er
ikke dokumenter fra offentlige organer). Det trengs ingen fallback, og
`readSearchResults()` brukes ikke. Søket legges ikke i brukerens
søkehistorikk (smulesti).

**I Klassisk** skriver `search()` spørringen inn i `#quickSearchField-input` og sender en
syntetisk `keyup` med Enter, som er hendelsen GWT-søket faktisk lytter på
(målt: `input` alene, syntetisk `keydown`, syntetisk `keypress` og et *ekte*
Enter-tastetrykk gjør ingenting — `keyup` submitter). Deretter venter den på
at hash-en blir `#result…` og at trefflisten fra *dette* søket er tegnet opp
(treff som sto på skjermen fra før, telles ikke), og returnerer `{query,
hash, submitted, results}`. Kjører du samme søk to ganger og Pro ikke tegner
listen på nytt, får du treffene som står der, med `reused: true`. Viser
resultatsiden for søket ingen dokumentlenker, svarer den `noHits: true` med
tom `results`: trolig ingen treff (sjekk med `get_page_text` om det betyr noe).
Hash-navigering laster ikke siden på nytt, så `window.__lp.cache` overlever
et søk i samme fane.

Merk at Pro skriver om spørringen: den settes til små bokstaver og får et
trunkeringsjokertegn (`TOSL-2022` → `q=TOSL-2022*`). `submitted` viser hva
feltet endte opp med. Ikke sammenlign `hash` med spørringen din.

**Fallback (Klassisk) — hvis `search()` svarer `search_timeout`:**

1. Sørg for at fanen viser søkefeltet (`#quickSearchField-input`).
2. Skriv inn søketeksten med `computer {action:"type"}`.
3. Finn søkeknappen (🔍-ikonet ved siden av feltet) med `read_page` — den
   dukker opp som `button "🔍"`. `computer {action:"screenshot"}` kan feile,
   så ikke regn med skjermbilder her.
4. Klikk knappen med `computer {action:"left_click"}`. Enter-tasten gjør
   fortsatt ingenting.
5. Vent ~2 sekunder og les ut treffene:

   ```javascript
   await __lp.readSearchResults(10)
   ```

Samme advarsler som før:

- **Pro-søk returnerer innholdstreff, ikke dokumenttreff.** Et søk på
  «St.prp. nr. 100 1991-92 EØS-avtalen» kan gi EU-direktiver fra
  EØS-vedlegget fordi fulltekstsøket slår på alle treff i
  dokumentkorpuset — ikke selve dokumentet.
- **Pre-2008 Rt.-slugs har et opakt suffiks** (`rt-YYYY-PAGENUMBER-SUFFIX`)
  som ikke kan gjettes deterministisk — i Klassisk er søk eneste pålitelige
  vei; på nye Pro løser `load(pro2_ref)` det (Steg 1).
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
- **Spesialdomstoler, nemnder, uttalelser, rundskriv**: Lovdatas referanse
  (står i `metadata.Saksnummer` eller tittelen), f.eks. *TRR-2026-695*,
  *KOFA-2026-1389 avsnitt 30*, *Rundskriv G-2019-3 punkt 2*; *ND 2025 s. 23*
- **Lover og forskrifter**: *LOV-2005-06-17-62 § 14-9* eller
  *arbeidsmiljøloven § 14-9*; for en tidligere versjon med datoen den gjaldt
  fra, for Lovtidend med «Publisert i» (*Norsk Lovtidend avd. I 2005 s. 1112*)

Sitater beholdes på originalt norsk, i anførselstegn («…» eller "…"). Legg
gjerne til oversettelse/forklaring på brukerens språk etter sitatet.
**Resten av svaret skrives på brukerens språk** (bokmål til en som skriver
bokmål, også når kilden er på nynorsk eller dansk; engelsk til en som skriver
engelsk).

Teksten har kildens kursiv og fet som `*…*` og `**…**` (sakstitler, latinske
uttrykk, rettens egne uthevinger i sitater). Uthevingen er en del av teksten:
et sitat som mister eller legger til kursiv er ikke eksakt, så behold den
(som kursiv/fet i svaret). Overskrifter (`## …`) er uten uthevingsmerker.
Hevet skrift står som Unicode der det finnes («20 m²»), ellers `^TM^`;
fotnoter som `[fn N]` i teksten og ved fotnoten.

**Aldri parafraser fra hukommelsen.** Hent dokumentet via `__lp.load`/
`section`/`page` og siter fra det. Eldre dommer endres riktignok ikke — men
forarbeidsprosessen, saksopplysninger og henvisninger varierer mellom
referanseverk og Lovdatas egen tekst, og hallusinasjon av domspremisser har
høy kostnad.

### Før du svarer

Gå gjennom utkastet til svar før du sender det:

1. **Finn alle sitater i utkastet.** Et sitat er all tekst fra Lovdata i
   anførselstegn («…», "…") eller i et blokksitat: også titler,
   korttitler, overskrifter, korte fraser, ord fra metadata og bokstav- og
   nummerpunkter. Tell dem.
2. **Send hvert av dem til `checkQuotes`**, ett kall per dokument, og rett
   det som får `matches: 0`. `checked` til sammen skal være lik antallet du
   talte i punkt 1.
3. **Skriv antallet i svaret:** «N av N sitater kontrollert mot Lovdatas
   tekst». Er noe ikke kontrollert, skriv «N av M» og si hvilke.
4. **Språket:** svaret er på brukerens språk (bokmål til bokmål, engelsk til
   engelsk); bare sitatene er på originalspråket.
5. **Lenker** til et dokument kan gis som
   `https://pro2.lovdata.no/dokument/<path>` (med `path` fra et svar). Åpne
   dem aldri selv.

---

## Arbeidsflyt for vanlige oppgaver

### Brukeren spør om hva en dom sier

1. Steg 0 (sesjon), Steg 1 (resolve), Steg 2 (`load` → `section`/`page`).
2. Finn relevante avsnitt, siter på norsk, forklar på brukerens språk.
3. Oppgi kilde inkludert avsnittsnummer/side hvor mulig.

### Brukeren spør om forarbeidene til en lov

1. **Har brukeren oppgitt lovens dato og nummer?** Hvis ikke: finn loven
   først, som i Steg 1 («En lov eller forskrift oppgitt bare med navn»),
   før `resolve` eller noe annet.
2. **Registeret (nye Pro):** `resolve "LOV-<dato>-<nr>"` gir i feltet
   `forarbeider` stien `RFA/lov/<dato>-<nr>`, Lovdatas liste over lovens
   forarbeider (også for endringslover). `load()` den og hent dokumentene
   listen nevner.

For forarbeidene til en *endring*: finn endringsloven med
`backlinks(lov, "endringslover")` og slå opp dens `RFA`.

Forarbeidene består typisk av tre dokumenter — alle bør hentes når brukeren
ber om «forarbeidene»:

1. **NOU** (utvalgsutredning) — `NOU YYYY:N`
2. **Prop. L / Ot.prp.** (departementets proposisjon) — `Prop. N L (YYYY-YY)`
   eller `Ot.prp. nr. N (YYYY-YY)`
3. **Innst.** (komitéinnstilling) — `Innst. N L (YYYY-YY)`

Disse er ofte 1-3 MB tekst hver. Bruk `toc` + `grep` + `section` for å finne
og hente det relevante kapittelet — ikke hele dokumentet via dump-modus, med
mindre brukeren eksplisitt ber om en full lokal kopi. **NOU-er og
proposisjoner har ofte `tocNext`** i `load()`-svaret: hent resten med
`toc(path, tocNext)` (og videre med `next`) før du lister kapitlene, ellers
mangler resten av dokumentet.

### Brukeren oppgir en uvanlig referanse (Rt., RG, eldre Ot.prp.)

For pre-2008 Rt.-dommer, RG-dommer, stortingsmeldinger (Meld. St./St.meld.)
og Ot.prp. fra før ~1968 finnes ingen deterministisk slug-regel.
`lovdata_ref.py resolve` gir `parsed:false` for disse, med `search_hint` og en
`note` om hvor dokumenttypen ligger — gå til Steg 3 (søk) og **verifiser**
treffet før du siterer.

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
- **`no_headings`** (fra `section()`) → dokumentet har ingen overskrifter.
  Bruk `grep()` og `page()`.
- **`no_search_field`** / **`search_timeout`** (fra `search()`) → fanen viser
  ikke Hurtigsøk-feltet, eller søket kom ikke gjennom. Bruk fallback-flyten i
  Steg 3.
- **`cors`** → du kjørte JS i en fane som ikke er på Lovdata Pro. Sjekk at
  fanen faktisk viser en Lovdata Pro-side (Steg 0).
- **`wrong_site`** → fanen står verken på nye Lovdata Pro eller Klassisk:
  `navigate` til standardadressen i Steg 0, lim inn hjelperen igjen og prøv
  på nytt. Har svaret `pasted`, er kopien laget for det andre nettstedet:
  kjør `paste_site.py <site>` (Steg 0 punkt 3) og lim inn den.
- **`bad_sort`** (fra `search()`) → `sort` er `"relevance"` eller `"date"`.
- **`missing_json`** (nye Pro) → dokumentet finnes, men uten tekstversjon i
  nye Pro. Åpne Klassisk (`https://lovdata.no/pro/?forceFullVersion=true`) i
  en egen fane, lim inn hjelperen der og `load()` på nytt.
- **`static_file`** (nye Pro) → dokumentet er bare en fil (PDF/HTML) i Pro,
  ikke tekst hjelperen kan lese. Si det til brukeren; prøv gjerne Klassisk.
- **`pro2_only`** (fra `versions()`/`backlinks()`) → åpne nye Pro
  (`https://pro2.lovdata.no/`) i en egen fane og lim inn hjelperen der.
- **`before_first_version`**, **`bad_date`**, **`unsupported_kind`** → se
  Steg 2b (`asOf` er `ÅÅÅÅ-MM-DD`; `backlinks` tar `historisk`,
  `endringslover` og `lovspeil`).
- **`unsupported_format`** (nye Pro) → Lovdata har endret dokumentformatet.
  Bruk Klassisk, og si til brukeren at skill-en bør oppdateres.
- **Siden er ikke godkjent / brukeren avslo tilgangsforespørselen** → fortell
  brukeren dette og stopp; ikke prøv å omgå det.

---

## Ytelsesnotat

Hvert `javascript_tool`-svar går gjennom verktøykanalen og inn i samtalen —
returner **aldri** mer enn `PAGE_SIZE` (se toppen av `lovdata_pro.js`) fra ett
JS-kall. **Les aldri `__lp.cache` direkte**, verken `fullText` eller
`toc`: bruk `page`/`section`/`grep`, og `toc(path, start)` for
innholdsfortegnelsen. De holder svarene under grensen. Vil du ha ett
kapittel, filtrer `toc` fra `load()`- eller `toc()`-svaret. Ser teksten feil
ut (et manglende tegn, en rar liste), si det til brukeren; ikke undersøk
markupen gjennom cachen. Foretrekk `browser_batch` når du skal
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
