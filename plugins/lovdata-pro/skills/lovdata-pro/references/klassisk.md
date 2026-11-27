# Lovdata Pro Klassisk og lese-ruten

Les denne filen når du må bruke **Lovdata Pro Klassisk** (`lovdata.no/pro`,
tilgjengelig ut 2027), eller når innlimingen av hjelperen blir avvist.

## Når Klassisk

Standard er nye Lovdata Pro (`https://pro2.lovdata.no/`). Bruk Klassisk bare
når nye Pro ikke har dokumentet:

- **`missing_json`** eller **`static_file`** fra `load()` på nye Pro;
- nye Pro virker ikke (innlogging eller feil).

Versjoner, endringslover og kategoriene utenom alminnelige domstoler og
Prop./NOU/Innst. finnes bare i nye Pro (`pro2_only`).

## Sesjon

1. Åpne en **egen fane** (`tabs_create` + `navigate`) på
   `https://lovdata.no/pro/?forceFullVersion=true`, så hjelperen i nye
   Pro-fanen beholdes.
2. Lim inn Klassisk-kopien: `python3 {SKILL_DIR}/scripts/browser/paste_site.py
   klassisk` (ca. 29 000 tegn), resten som i SKILL.md Steg 0. Svaret er
   `["<versjon>", "klassisk"]`.
3. Kjør `await __lp.isLoggedIn()` (SKILL.md Steg 0 punkt 4). Den avgjøres
   på `#myPage` av `document.title`; står fanen på et dokument, gjør den et
   lite prøveoppslag (`source: "probe"`).

`load()`, `toc()`, `section()`, `grep()`, `page()` og `checkQuotes()` virker som
på nye Pro. Avsnittsnumre i dommer står i en egen tabellcelle (`| (77) |`);
`grep(path, "(77)")` finner dem. Rt.-dommer før 2008 har et suffiks som ikke
kan gjettes: søk på `search_hint` fra `resolve`.

## Søk i Klassisk

```javascript
await __lp.search("Rt-2000-1811", 10)
```

`search()` skriver spørringen inn i Hurtigsøk-feltet
(`#quickSearchField-input`), sender en syntetisk `keyup` med Enter (det er
den GWT-søket lytter på) og venter til trefflisten fra *dette* søket er
tegnet. Svaret er `{query, hash, submitted, results}`. Hash-navigering laster
ikke siden på nytt, så cachen overlever et søk i samme fane; dette er den
eneste navigeringen som er i orden.

- Pro skriver om spørringen (små bokstaver, `*` til slutt: `TOSL-2022` →
  `q=TOSL-2022*`); `submitted` viser hva feltet endte opp med.
- Samme søk to ganger uten ny tegning gir treffene som står der, med
  `reused: true`.
- `noHits: true` med tom `results`: trolig ingen treff.
- `singleHit: true`: søket hadde nøyaktig ett treff, og Klassisk åpnet
  dokumentet selv (hash `#document/…`); `results` har det ene treffet.
- `bases`, `sort` og `offset` virker bare på nye Pro.

**Hvis `search()` svarer `search_timeout` eller `no_search_field`:**

1. Sørg for at fanen viser søkefeltet (`#quickSearchField-input`).
2. Skriv søketeksten med `computer {action:"type"}`.
3. Finn søkeknappen med `read_page` (`button "🔍"`); skjermbilder kan feile.
4. Klikk den med `computer {action:"left_click"}` (Enter virker ikke).
5. Vent ~2 sekunder og kjør `await __lp.readSearchResults(10)`.

## Lese-ruten (begge nettstedene)

Bare når **en sikkerhetssjekk avviser innlimingen**. Ikke prøv samme kall
igjen; si det til brukeren med én setning.

1. Logg inn uten `isLoggedIn()`: spør brukeren.
2. `navigate` til `https://lovdata.no/pro/#document/<path>` eller
   `https://pro2.lovdata.no/dokument/<path>` (path fra `resolve`), vent et par
   sekunder og les med `get_page_text` (eller `read_page`).
3. Søk som i fallbacken over, med `get_page_text` i stedet for
   `readSearchResults`.

Lese-ruten har ingen `grep`/`section`/biter, og den skriver besøkene inn i
brukerens historikk. Lange dokumenter blir avkortet (nye Pro: tom tekst når
panelet er skjult, og bare ca. 10 000 tegn av lange dokumenter): si fra hvis
teksten slutter brått, og sitér bare det siden faktisk viser.
