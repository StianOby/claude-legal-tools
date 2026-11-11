#!/usr/bin/env node
// Tests for the new-Lovdata-Pro (pro2) backend of scripts/browser/lovdata_pro.js:
// login check, finding a document (checkDocument, RedirectTo, references),
// JSON-ML -> text, metadata, search, and the calls the helper must never
// make (breadcrumbs, Lovdata's KI services). fetch is a stub; the fixtures
// copy pro2's structure (tags, classes, attributes as measured 2026-11-11,
// docs/lovdata-pro2.md) with made-up text — nothing from Lovdata.
//
// Needs linkedom, installed for the eu-agreements-treaties tests (CI runs
// this in that step); skipped without it.
//
// Run with `node tests/lovdata-pro/pro2.js` after `npm ci` in
// tests/eu-agreements-treaties.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let parseHTML; let DOMParser;
try {
  ({ parseHTML, DOMParser } = require(path.join(__dirname, '..', 'eu-agreements-treaties', 'node_modules', 'linkedom')));
} catch (e) {
  console.log('skip (linkedom not installed: npm ci in tests/eu-agreements-treaties)');
  process.exit(0);
}

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'plugins', 'lovdata-pro', 'skills', 'lovdata-pro', 'scripts', 'browser', 'lovdata_pro.js'), 'utf8');

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else { console.log(`  FAIL ${name}: got ${g && g.slice(0, 400)}, want ${w && w.slice(0, 400)}`); failures += 1; }
}

// --- fixtures (pro2 structure, made-up text) ---------------------------------

const el = (tag, attrs = {}, kids = []) => [tag, attrs, kids];
const numbered = (n, text) => el('article', { class: 'verdictNumberedP', 'data-part-id': `a${n}`, 'data-offset': n }, [
  el('span', { class: 'verdictNumberedPId' }, [`(${n})`]), ' ',
  el('article', { class: 'defaultP' }, text),
]);

const JUDGMENT = {
  version: 2,
  header: el('header', { class: 'documentHeader', id: 'hode' }, [
    el('dl', { class: 'data-document-key-info' }, [
      el('dt', { class: 'court' }, ['Instans']), el('dd', { class: 'court' }, ['Høyesterett – dom.']),
      el('dt', { class: 'parties' }, []), el('dd', { class: 'parties' }, ['Part A (advokat X)', el('br'), 'mot', el('br'), 'Part B']),
      el('dt', { class: 'caseNumber' }, ['Saksnummer']), el('dd', { class: 'caseNumber' }, ['2016/1']),
    ]),
  ]),
  toc: el('ul', { class: 'tocTopUl' }, []),
  mainTags: [
    el('article', { class: 'defaultP' }, ['Innledende tekst.']),
    numbered(1, ['Første avsnitt med ', el('i', {}, ['kursiv']), ' og ', el('strong', {}, ['fet']), ' skrift.']),
    numbered(2, ['Andre avsnitt, jf. ', el('a', { href: 'lov/1999-05-21-30/§2' }, ['§ 2']), '.']),
    el('ol', { class: 'defaultList', type: 'a' }, [
      el('li', { value: '1', 'data-name': 'a.' }, [el('span', { class: 'data-originalId' }, ['a.']), el('article', { class: 'listArticle' }, ['første punkt'])]),
      el('li', { value: '2', 'data-name': 'b.', 'data-list-id-style': 'i' }, [el('span', { class: 'data-originalId', 'data-list-id-style': 'i' }, ['b.']), el('article', { class: 'listArticle' }, ['andre punkt'])]),
    ]),
  ],
};

const NOU = {
  version: 2,
  header: el('header', { class: 'documentHeader', id: 'hode' }, [el('dl', { class: 'data-document-key-info' }, [
    el('dt', { class: 'caseID' }, ['Dokumentnummer']), el('dd', { class: 'caseID' }, ['NOU 2000: 1']),
  ])]),
  toc: el('ul', { class: 'tocTopUl' }, []),
  mainTags: [
    el('section', { class: 'section', id: 'kapittel-1', 'data-part-id': 'k1', 'data-name': 'kap1' }, [
      el('h2', { 'data-text-align': 'center' }, ['Innledning', el('aside', { class: 'pagenumber', 'aria-label': 'side 11', 'data-pagenumbervalue': '11' }, ['Side 11'])]),
      el('article', { class: 'defaultP' }, ['Tekst i kapittel 1', el('sup', { class: 'footnotereference', 'data-footnotereferencevalue': '1' }, ['1']), '.']),
      el('section', { class: 'section', id: 'kapittel-1-kapittel-1', 'data-part-id': 'k1-1' }, [
        el('h3', {}, ['Bakgrunn']),
        el('article', { class: 'defaultP' }, ['m', el('sup', {}, ['2']), ' og tabell:']),
        el('table', {}, [el('tbody', {}, [el('tr', {}, [el('td', {}, ['A']), el('td', {}, ['B'])])])]),
      ]),
    ]),
    el('section', { class: 'section', id: 'kapittel-2', 'data-part-id': 'k2' }, [
      el('h2', {}, ['Lovforslag']),
      el('article', { class: 'futureLegalArticle', 'data-name': '§1-1', 'data-part-id': '§1-1' }, [
        el('span', { class: 'futureLegalArticleHeader' }, [el('span', { class: 'legalArticleValue' }, ['§ 1-1']), '. ', el('span', { class: 'legalArticleTitle' }, ['Formål'])]),
        el('article', { class: 'legalP' }, ['Loven skal fremme noe.']),
      ]),
      el('footer', { class: 'footnotes' }, [
        el('article', { class: 'footnote', 'data-name': '1' }, [el('span', { class: 'footnoteLabel' }, ['1']), ' Fotnotetekst.']),
      ]),
    ]),
  ],
};

// --- a fake pro2 tab ----------------------------------------------------------

function makeTab({ loggedIn = true } = {}) {
  const calls = [];
  const json = (status, body) => ({ status, text: async () => JSON.stringify(body) });
  const routes = {
    'auth/user': () => (loggedIn ? json(200, { userID: 7, name: 'Navn Navnesen', email: 'x@example.org' }) : json(401, {})),
    'checkDocument/HRSIV/avgjorelse/hr-2016-1-a': () => json(200, { type: 'Success' }),
    'checkDocument/HRSTR/avgjorelse/hr-2016-1-a': () => json(200, { type: 'RedirectTo', documentURI: { base: 'HRSIV', type: 'avgjorelse', id: 'hr-2016-1-a', part: null } }),
    'checkDocument/HRSIV/avgjorelse/rt-2000-1': () => json(200, { type: 'RedirectTo', documentURI: { base: 'HRSIV', type: 'avgjorelse', id: 'hr-2000-1-b', part: null } }),
    'checkDocument/NOU/forarbeid/nou-2000-1': () => json(200, { type: 'Success' }),
    'checkDocument/PROP/forarbeid/stprp-1-200001': () => json(200, { type: 'DocumentNotFound' }),
    'checkDocument/PUBG/forarbeid/nou-1980-1': () => json(200, { type: 'MissingJSON', proURL: '/pro/#document/PUBG/forarbeid/nou-1980-1' }),
    'references/avgjorelse/rt-2000-1': () => json(200, [{ title: 'HR-2000-1-B - Rt-2000-1', base: 'HRSIV', documentURI: { base: 'HRSIV', type: 'avgjorelse', id: 'hr-2000-1-b', part: null } }]),
    'references/avgjorelse/rt-2000-1/s5': () => json(200, [{ title: 'HR-2000-1-B - Rt-2000-1', base: 'HRSIV', documentURI: { base: 'HRSIV', type: 'avgjorelse', id: 'hr-2000-1-b', part: 's5' } }]),
    'references/forarbeid/stprp-1-200001': () => json(200, []),
    'documentContent/HRSIV/avgjorelse/hr-2016-1-a': () => json(200, JUDGMENT),
    'documentMeta/HRSIV/avgjorelse/hr-2016-1-a': () => json(200, { title: 'HR-2016-1-A', shortTitle: 'HR-2016-1-A' }),
    'documentContent/HRSIV/avgjorelse/hr-2000-1-b': () => json(200, JUDGMENT),
    'documentMeta/HRSIV/avgjorelse/hr-2000-1-b': () => json(200, { title: 'HR-2000-1-B - Rt-2000-1' }),
    'documentContent/NOU/forarbeid/nou-2000-1': () => json(200, NOU),
    'documentMeta/NOU/forarbeid/nou-2000-1': () => json(200, { title: 'NOU 2000: 1 Et utvalg' }),
    'search?minimal=true': (init) => {
      const body = JSON.parse(init.body);
      calls[calls.length - 1].body = body;
      return json(200, { totalHits: 3, results: [
        { documentURI: { base: 'COMMENT', type: 'karnov', id: 'x' }, documentTitles: { title: 'Kommentar' } },
        { documentURI: { base: 'HRSIV', type: 'avgjorelse', id: 'hr-2016-1-a' }, documentTitles: { title: 'HR-2016-1-A' }, isoDate: '2016-01-01' },
        { documentURI: { base: 'NOU', type: 'forarbeid', id: 'nou-2000-1' }, documentTitles: { title: 'NOU 2000: 1' } },
      ] });
    },
  };
  const API = 'https://pro2.lovdata.no/api/';
  const fetch = async (url, init = {}) => {
    calls.push({ url, method: init.method || 'GET' });
    if (!url.startsWith(API)) throw new TypeError('Failed to fetch');
    const key = decodeURIComponent(url.slice(API.length)).replace(/\?frontendVersion=.*$/, '');
    const route = routes[key];
    return route ? route(init) : json(404, {});
  };
  const { document } = parseHTML('<html><head><script type="module" src="/assets/index-X.js"></script></head><body></body></html>');
  const location = { hostname: 'pro2.lovdata.no', origin: 'https://pro2.lovdata.no', hash: '', pathname: '/' };
  const ctx = { location, document, DOMParser, fetch, setTimeout, console };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return { lp: ctx.__lp, calls, location, document };
}

async function main() {
  const { lp, calls } = makeTab();

  check('backend on pro2', lp._internal.backend().kind, 'pro2');
  check('logged in, no personal data returned', await lp.isLoggedIn(), { loggedIn: true, source: 'api', site: 'pro2' });
  check('logged out', (await makeTab({ loggedIn: false }).lp.isLoggedIn()).loggedIn, false);

  // Judgment by full path; then the STR candidate redirects to SIV.
  let r = await lp.load(['HRSIV/avgjorelse/hr-2016-1-a', 'HRSTR/avgjorelse/hr-2016-1-a']);
  check('load judgment', [r.path, r.title, r.site, r.toc.length === 0, r.metadata.Instans, r.metadata.Parter, r.metadata.Saksnummer],
    ['HRSIV/avgjorelse/hr-2016-1-a', 'HR-2016-1-A', 'pro2', true, 'Høyesterett – dom.', 'Part A (advokat X)\nmot\nPart B', '2016/1']);
  const t = (await lp.page(r.path, 0)).text;
  check('judgment text', t, [
    'Innledende tekst.',
    '(1) Første avsnitt med *kursiv* og **fet** skrift.',
    '(2) Andre avsnitt, jf. § 2.',
    'a. første punkt',
    '*b.* andre punkt',
  ].join('\n'));
  check('grep "(2)" finds the paragraph', (await lp.grep(r.path, '(2)', 20, 5)).matches, 1);

  const { lp: lp2 } = makeTab();
  r = await lp2.load(['HRSTR/avgjorelse/hr-2016-1-a']);
  check('RedirectTo followed', [r.path, r.redirectedFrom], ['HRSIV/avgjorelse/hr-2016-1-a', 'HRSTR/avgjorelse/hr-2016-1-a']);

  // Rt. by short form through references, with a page pinpoint.
  r = await lp.load('avgjorelse/rt-2000-1/s5');
  check('Rt short form via references', [r.path, r.part, r.via, r.title], ['HRSIV/avgjorelse/hr-2000-1-b', 's5', 'references avgjorelse/rt-2000-1/s5', 'HR-2000-1-B - Rt-2000-1']);

  // Not found anywhere; MissingJSON points to Klassisk.
  r = await lp.load(['PROP/forarbeid/stprp-1-200001']);
  check('not found after checkDocument + references', [r.error, /references forarbeid\/stprp-1-200001/.test(r.detail)], ['not_found', true]);
  r = await lp.load(['PUBG/forarbeid/nou-1980-1']);
  check('MissingJSON', [r.error, /forceFullVersion/.test(r.detail)], ['missing_json', true]);

  // NOU: headings, page markers, footnotes, superscript, table, §-title.
  r = await lp.load(['NOU/forarbeid/nou-2000-1']);
  check('NOU toc', r.toc.map(e => [e.level, e.title]), [[2, 'Innledning'], [3, 'Bakgrunn'], [2, 'Lovforslag']]);
  check('NOU metadata', r.metadata, { Dokumentnummer: 'NOU 2000: 1' });
  check('NOU text', (await lp.page(r.path, 0)).text, [
    '## Innledning',
    'Side 11',
    'Tekst i kapittel 1[fn 1].',
    '### Bakgrunn',
    'm² og tabell:',
    '| A | B |',
    '## Lovforslag',
    '§ 1-1. *Formål*',
    'Loven skal fremme noe.',
    '[fn 1] Fotnotetekst.',
  ].join('\n'));

  // Search: relevance order requested, Karnov comments dropped, bases passed.
  const s = await lp.search('HR-2016-1-A', 10, { bases: ['HRA'] });
  const sc = calls.find(c => /search\?minimal=true$/.test(c.url));
  check('search request', [sc.method, sc.body.sortField, sc.body.sortOrder, sc.body.filterBases, sc.body.term], ['POST', 'relevance', 'desc', ['HRA'], 'HR-2016-1-A']);
  check('search results', s.results.map(x => x.path), ['HRSIV/avgjorelse/hr-2016-1-a', 'NOU/forarbeid/nou-2000-1']);
  check('readSearchResults not needed', (await lp.readSearchResults()).error, 'not_needed');

  // Never: breadcrumbs (writes the user's history) or KI services.
  const forbidden = calls.filter(c => /\/(breadcrumbs|ai-search|ai-chat|v2\/ai-chat|reference-preview|ai-search-migrate)\b/.test(c.url));
  check('no breadcrumbs or KI calls', forbidden, []);
  check('only GET or search POST', calls.filter(c => c.method !== 'GET' && !/search\?minimal=true$/.test(c.url)), []);

  // The meter counts calls, returned characters and fetches; reset zeroes it.
  const st = await lp.stats({ reset: true });
  check('stats', [st.site, st.calls.load.n >= 5, st.calls.search.n, st.returnedChars > 1000, st.fetches === calls.length, st.fetchBytes > 0],
    ['pro2', true, 1, true, true, true]);
  const st2 = lp.stats();
  check('stats reset', [st2.returnedChars, st2.fetches, Object.keys(st2.calls).length], [0, 0, 0]);

  // lovdata.no: Klassisk unless the page is the new app's Vite bundle.
  const k = makeTab();
  k.location.hostname = 'lovdata.no'; k.location.origin = 'https://lovdata.no';
  check('lovdata.no with Vite bundle is pro2 at /pro/api', k.lp._internal.backend(), { kind: 'pro2', api: 'https://lovdata.no/pro/api' });
  k.document.querySelector('script').remove();
  check('lovdata.no without it is Klassisk', k.lp._internal.backend(), { kind: 'klassisk' });
  k.location.hostname = 'example.org';
  check('other host is wrong_site', (await k.lp.isLoggedIn()).error, 'wrong_site');

  console.log(failures ? `${failures} failure(s)` : 'all ok');
  process.exit(failures ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
