// Parser tests for scripts/browser/consilium.js.
//
//   cd tests && npm install && npm test
//
// Two layers:
//   1. Synthetic checks that always run. Their markup is copied from the
//      live site (captured 2026-09-16, see fixtures/PROBES.md "dom"), not
//      invented — an earlier version used a `<label for>` shape the site
//      never emits and stayed green over a real bug.
//   2. Fixture checks against tests/fixtures/*.html, captured with
//      __cs.capture() in Cowork (NOTES.md §3). Expected values are pinned
//      to the capture date and will drift; update them with the fixture.
//
// Uses linkedom as the DOM shim; the helper's fetch/document deps are
// swapped out so no network is touched.

'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { parseHTML } = require('linkedom');

const cs = require('../scripts/browser/consilium.js');
const I = cs._internal;

cs._deps.parse = (html) => parseHTML(html).document;
cs._deps.currentDocument = () => null;
cs._deps.location = () => null;

const FIX = path.join(__dirname, 'fixtures');
const fixture = (name) => {
  const p = path.join(FIX, name);
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
};
const doc = (html) => parseHTML(html).document;

// Shipped party list → name index, as detail() builds it at runtime.
const PARTIES = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'parties.json'), 'utf8'));
const INDEX = I.partyIndexOf(PARTIES);

let passed = 0, skipped = 0;
function test(name, fn) {
  try { fn(); passed++; console.log('  ok   ', name); }
  catch (e) { console.log('  FAIL ', name); console.log(String(e.stack || e).split('\n').slice(0, 6).join('\n')); process.exitCode = 1; }
}
function skip(name, why) { skipped++; console.log('  skip ', name, '—', why); }

// ---------------------------------------------------------------------------
console.log('synthetic (markup copied from the live site)');

test('toIso handles site dates and the 0001 empty value', () => {
  assert.strictEqual(I.toIso('21/06/2011'), '2011-06-21');
  assert.strictEqual(I.toIso('1/6/2011'), '2011-06-01');
  assert.strictEqual(I.toIso('01/01/0001'), null);
  assert.strictEqual(I.toIso(''), null);
});

test('toSiteDate accepts ISO, DD/MM/YYYY and bare years', () => {
  assert.strictEqual(I.toSiteDate('2016-05-28'), '28/05/2016');
  assert.strictEqual(I.toSiteDate('2000'), '01/01/2000');
  assert.strictEqual(I.toSiteDate('2000', true), '31/12/2000');
  assert.strictEqual(I.toSiteDate('x'), null);
});

test('buildSearchUrl repeats Parties and only sets dates when given', () => {
  const u = cs.buildSearchUrl({ parties: ['NO', 'IS'] });
  assert.ok(u.includes('DoSearch=true'));
  assert.ok(u.includes('Parties=NO&Parties=IS'));
  assert.ok(!u.includes('DateType'));
  const v = cs.buildSearchUrl({ from: '2000' });
  assert.ok(v.includes('DateType=signature') && v.includes('DateTo=01%2F01%2F0001'));
});

test('splitLabel handles "Short - Long", "Short -" and "Long (Short)"', () => {
  assert.deepStrictEqual(I.splitLabel('Norway - Kingdom of Norway'), { short: 'Norway', long: 'Kingdom of Norway' });
  assert.deepStrictEqual(I.splitLabel('Kingdom of Norway (Norway)'), { short: 'Norway', long: 'Kingdom of Norway' });
  assert.deepStrictEqual(I.splitLabel('Greenland -'), { short: 'Greenland', long: null });
  assert.deepStrictEqual(I.splitLabel('EC - European Community'), { short: 'EC', long: 'European Community' });
  // dash form wins over a parenthesis inside the name
  assert.deepStrictEqual(I.splitLabel('Kosovo (under UNSC Resolution 1244/99) - Kosovo (under UNSC Resolution 1244/99)'),
    { short: 'Kosovo (under UNSC Resolution 1244/99)', long: 'Kosovo (under UNSC Resolution 1244/99)' });
});

test('parsePartyList: wrapping label without `for`, one entry per name form, short name wins', () => {
  // Exactly the site's markup: label wraps the input, id is the party name.
  const d = doc(`<ul>
    <li><label class="gsc-form__label gsc-form__label--checkbox">Austria - Republic of Austria
 <input name="Parties" id="Austria" type="checkbox" class="gsc-form__input" value="A"></label></li>
    <li><label class="gsc-form__label gsc-form__label--checkbox">Greenland -
 <input name="Parties" id="Greenland" type="checkbox" class="gsc-form__input" value="GL"></label></li>
    <li><label class="gsc-form__label gsc-form__label--checkbox">Republic of Austria (Austria)
 <input name="Parties" id="Republic of Austria" type="checkbox" class="gsc-form__input" value="A"></label></li>
    <li><label class="gsc-form__label"><input name="Other" value="ZZ"> not a party</label></li>
  </ul>`);
  const p = I.parsePartyList(d);
  assert.deepStrictEqual(p.map((x) => x.code), ['A', 'GL']);
  assert.strictEqual(p[0].name, 'Austria');
  assert.strictEqual(p[0].long_name, 'Republic of Austria');
  assert.deepStrictEqual(p[0].names, ['Austria', 'Republic of Austria', 'Austria - Republic of Austria', 'Republic of Austria (Austria)']);
  assert.strictEqual(p[1].name, 'Greenland');
  assert.strictEqual(p[1].long_name, null);
});

test('partyMatches: short queries match codes or whole words only', () => {
  const acp = { code: 'ACP', names: ['ACP', 'African, Caribbean and Pacific States'] };
  assert.strictEqual(I.partyMatches(acp, 'AT'), false);      // "St-at-es" must not match
  assert.strictEqual(I.partyMatches(acp, 'acp'), true);
  const at = { code: 'A', names: ['Austria', 'Republic of Austria'] };
  assert.strictEqual(I.partyMatches(at, 'austr'), true);
  assert.strictEqual(I.partyMatches({ code: 'CE', names: ['EC', 'European Community'] }, 'EC'), true);
});

test('parseResults: gsc rows with <time datetime> (US order), dedicated count element, PV flag', () => {
  const d = doc(`<main><p class="gsc-u-search-info">current search <strong class="gsc-u-results-count">101 results</strong></p><ol>
    <li data-block-flow-sm=""><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2026005" class="gsc-link">Agreement between the European Union and the Kingdom of Norway on GOVSATCOM</a><p>Signature: <time datetime="3/26/2026 12:00:00 AM">26/03/2026</time></p></li><hr>
    <li data-block-flow-sm=""><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2023045" class="gsc-link">Agreement amending the VAT cooperation agreement</a><p>Signature: <time datetime="10/2/2024 12:00:00 AM">02/10/2024</time></p><p>Entry into force: <time datetime="8/1/2025 12:00:00 AM">01/08/2025</time></p></li><hr>
    <li data-block-flow-sm=""><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2017039" class="gsc-link">Procès-Verbal of Rectification to the Agreement …</a><p>Signature: <time datetime="6/15/2017 12:00:00 AM">15/06/2017</time></p></li><hr>
    <li data-block-flow-sm=""><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2006052" class="gsc-link">Multilateral Agreement on a European Common Aviation Area</a></li>
  </ol><ul class="gsc-lang"><li><a href="/bg/documents/treaties-agreements/?DoSearch=true">български</a></li></ul></main>`);
  const r = I.parseResults(d);
  assert.strictEqual(r.site_total, 101);
  assert.strictEqual(r.results.length, 4);
  const a = r.results.find((q) => q.id === '2026005');
  assert.strictEqual(a.signature, '2026-03-26');               // from datetime, M/D/YYYY
  assert.strictEqual(a.entry_into_force, null);
  const b = r.results.find((q) => q.id === '2023045');
  assert.strictEqual(b.signature, '2024-10-02');
  assert.strictEqual(b.entry_into_force, '2025-08-01');
  assert.strictEqual(r.results.find((q) => q.id === '2017039').is_proces_verbal, true);
  const e = r.results.find((q) => q.id === '2006052');
  assert.strictEqual(e.signature, null);
  assert.strictEqual(e.entry_into_force, null);
});

test('parseResultCount: no count element → narrow text fallback, never a year from a date', () => {
  assert.strictEqual(I.parseResultCount(doc('<main><p>current search101 resultsSorted by</p></main>')), 101);
  assert.strictEqual(I.parseResultCount(doc('<main><li><a>Agreement X</a><p>Signature: 26/03/2026</p></li><li><a>Agreement Y</a></li></main>')), null);
});

test('sortResults puts undated rows last in both directions', () => {
  const rows = [{ signature: null }, { signature: '2011-01-01' }, { signature: '2009-01-01' }];
  assert.deepStrictEqual(I.sortResults(rows, 'LSF').map((r) => r.signature), ['2011-01-01', '2009-01-01', null]);
  assert.deepStrictEqual(I.sortResults(rows, 'OSF').map((r) => r.signature), ['2009-01-01', '2011-01-01', null]);
});

const DETAIL_HTML = `<main><h1 class="gsc-title">Agreement on aviation</h1>
  <div class="gsc-grid gsc-accords-details">
    <div data-block-flow=""><h2 class="gsc-title gsc-title--underlined gsc-title--lp-section">Entry into force</h2><p><strong>01/06/2017</strong></p></div>
    <div data-block-flow=""><h2 class="gsc-title gsc-title--underlined gsc-title--lp-section">Signature</h2><p><strong>16/06/2011, Luxembourg</strong></p></div>
    <div data-block-flow=""><h2 class="gsc-title gsc-title--underlined gsc-title--lp-section">Official Journal reference</h2><ul class="gsc-link-list"><li><a href="https://eur-lex.europa.eu/legal-content/en/TXT/?uri=OJ:L:2016:141:TOC" class="gsc-link"> L 141 (28/05/2016); </a></li></ul></div>
  </div>
  <div class="gsc-accords-details"><div data-block-flow=""><h2 class="gsc-title gsc-title--underlined gsc-title--lp-section">Observations</h2><p>Provisional application as from 21/06/2011 (except Austria, see Declaration)</p></div></div>
  <h3 class="gsc-title gsc-heading--sm">Ratification Details</h3>
  <table><thead><tr><th data-sort="string">Party</th><th data-sort="string">Signature (*)</th><th data-sort="string">Notification</th><th data-sort="string">Entry into force (*)</th><th data-sort="string" title="Declarations and reservations made by Parties/Countries to an agreement">Declaration / reservation</th><th data-sort="string">Observations</th></tr></thead>
  <tbody>
    <tr><td><b>Austria</b></td><td data-sort-value="">  </td><td data-sort-value="20140320000000000">20/03/2014</td><td data-sort-value=""></td><td><a href="/en/documents/treaties-agreements/ratification/?id=2011036&amp;partyid=A&amp;doclanguage=en" class="gsc-link">Declaration</a></td><td></td></tr>
    <tr><td><b>Czechia</b></td><td data-sort-value="20110616000000000">16/06/2011</td><td data-sort-value="20111205000000000">05/12/2011</td><td data-sort-value="20170601000000000">01/06/2017</td><td></td><td>acceding</td></tr>
    <tr><td><b>Not A Party Name</b></td><td data-sort-value=""></td><td data-sort-value=""></td><td data-sort-value=""></td><td></td><td></td></tr>
  </tbody>
  <tfoot><tr><td colspan="6">* When no dates are specified, the dates shown in "Entry into Force" (above left) and "Signature" (above right) apply, except in the case of acceding Parties.</td></tr></tfoot></table></main>`;

test('parseDetail: h2/p fields, OJ link, table dates from data-sort-value, codes via party index, inheritance flags', () => {
  const r = I.parseDetail(doc(DETAIL_HTML), '2011036', INDEX);
  assert.strictEqual(r.title, 'Agreement on aviation');
  assert.strictEqual(r.entry_into_force, '2017-06-01');
  assert.strictEqual(r.signature, '2011-06-16');
  assert.strictEqual(r.signature_place, 'Luxembourg');
  assert.ok(/Provisional application/.test(r.observations));
  assert.strictEqual(r.oj_references.length, 1);
  assert.deepStrictEqual(r.oj_references[0].oj, { series: 'L', year: '2016', issue: '141', part: 'TOC' });
  assert.strictEqual(r.parties.length, 3, 'tfoot row must not become a party');
  const at = r.parties[0];
  assert.strictEqual(at.code, 'A');                            // from the declaration link
  assert.strictEqual(at.has_declaration, true);
  assert.strictEqual(at.signature, null);
  assert.strictEqual(at.signature_inherited, true);
  assert.strictEqual(at.inherited_signature, '2011-06-16');
  assert.strictEqual(at.notification, '2014-03-20');
  const cz = r.parties[1];
  assert.strictEqual(cz.code, 'CZ');                           // plain-text name → code via parties.json
  assert.strictEqual(cz.signature_inherited, false);
  assert.strictEqual(cz.inherited_signature, undefined);
  assert.strictEqual(cz.observations, 'acceding');
  assert.strictEqual(r.parties[2].code, null);
  assert.deepStrictEqual(r.parties_without_code, ['Not A Party Name']);
  assert.deepStrictEqual(r.party_codes, ['A', 'CZ']);
  assert.ok(r.ratification_footnote && /When no dates are specified/.test(r.ratification_footnote));
});

test('parseDetail: page without an Observations section must not leak the table header (2009066 bug)', () => {
  const html = DETAIL_HTML.replace(/<div class="gsc-accords-details"><div data-block-flow=""><h2[^>]*>Observations<\/h2><p>[^<]*<\/p><\/div><\/div>/, '');
  assert.ok(!/Provisional application/.test(html), 'test setup: observations section removed');
  const r = I.parseDetail(doc(html), '2009066', INDEX);
  assert.strictEqual(r.observations, null);
});

test('parseDetail: empty agreement-level dates (2011036 shape) still flag inheritance, with null inherited value', () => {
  const html = DETAIL_HTML
    .replace('<p><strong>01/06/2017</strong></p>', '<p><strong></strong></p>')
    .replace('<p><strong>16/06/2011, Luxembourg</strong></p>', '<p><strong>Luxembourg &amp; Oslo</strong></p>');
  const r = I.parseDetail(doc(html), '2011036', INDEX);
  assert.strictEqual(r.signature, null);
  assert.strictEqual(r.entry_into_force, null);
  assert.strictEqual(r.signature_place, 'Luxembourg & Oslo');
  const at = r.parties[0];
  assert.strictEqual(at.signature_inherited, true);
  assert.strictEqual(at.inherited_signature, null);
});

test('isChallengeHtml recognises the Cloudflare page', () => {
  assert.strictEqual(I.isChallengeHtml('<title>Just a moment...</title>'), true);
  assert.strictEqual(I.isChallengeHtml('<html><span id="challenge-error-text">x</span>'), true);
  assert.strictEqual(I.isChallengeHtml('<title>Treaties and agreements</title>'), false);
});

// async: runs last in the synthetic layer, then hands over to the fixtures.
(async () => {
  // Canned response: two rows, one inside 2010–2020, one signed 2026.
  const html = `<main><strong class="gsc-u-results-count">2 results</strong><ol>
    <li><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2026005">A</a><p>Signature: <time datetime="3/26/2026 12:00:00 AM">26/03/2026</time></p></li>
    <li><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2015001">B</a><p>Signature: <time datetime="5/3/2015 12:00:00 AM">03/05/2015</time></p></li>
    <li><a href="/en/documents/treaties-agreements/agreement/?docLanguage=en&amp;id=2006052">C undated</a></li>
  </ol></main>`;
  const calls = [];
  cs._deps.fetch = async (url) => { calls.push(url); return { status: 200, headers: { get: () => null }, text: async () => html }; };
  cs.cache.parties = PARTIES;
  return (async () => {
    const r = await cs.search({ parties: ['NO'], from: '2010', to: '2020' });
    assert.deepStrictEqual(r.results.map((x) => x.id), ['2015001']);
    assert.ok(!calls[0].includes('DateTo=31'), 'DateTo must not be sent to the site');
    assert.ok(calls[0].includes('DateFrom=01%2F01%2F2010'));
    assert.ok(r.notes.some((n) => /ignores DateTo/.test(n)));
    assert.ok(r.notes.some((n) => /without a signature date/.test(n)));
    const bad = await cs.search({ parties: ['NO'], dateType: 'ratification', from: '2010' });
    assert.strictEqual(bad.error, 'unsupported_date_type');
    const ec = await cs.search({ parties: ['EC'] });
    assert.strictEqual(ec.error, 'ambiguous_code');
    const ecLiteral = await cs.search({ parties: ['EC'], literal: true });
    assert.strictEqual(ecLiteral.parties[0], 'EC');
    const at = await cs.resolveParty('AT');
    assert.strictEqual(at.error, 'unknown_party');
    assert.strictEqual(at.suggestions[0].code, 'A');
    assert.ok(at.suggestions.length <= 3, `noisy suggestions: ${JSON.stringify(at.suggestions)}`);
  })().then(() => { passed++; console.log('  ok    (async) search(): dates, ambiguous EC, AT suggestions'); },
    (e) => { console.log('  FAIL  (async) search(): dates, ambiguous EC, AT suggestions'); console.log(String(e.stack || e).split('\n').slice(0, 6).join('\n')); process.exitCode = 1; })
    .finally(runFixtures);
})();

// ---------------------------------------------------------------------------
function runFixtures() {
  console.log('fixtures (captured 2026-09-16; see NOTES.md §3 and fixtures/PROBES.md)');

  const form = fixture('search-form.html');
  if (form) {
    test('search form: 412 inputs → 256 codes, short names, the ten non-ISO EC codes present', () => {
      const p = I.parsePartyList(doc(form));
      assert.strictEqual(p.length, 256);
      for (const c of ['A', 'B', 'D', 'F', 'I', 'IRL', 'H', 'P', 'S', 'SF', 'NO', 'UE', 'CE', 'CEE', 'EEE', 'EC']) assert.ok(p.some((x) => x.code === c), `missing ${c}`);
      const by = Object.fromEntries(p.map((x) => [x.code, x]));
      assert.strictEqual(by.NO.name, 'Norway');
      assert.strictEqual(by.NO.long_name, 'Kingdom of Norway');
      assert.strictEqual(by.EC.name, 'Ecuador');
      assert.strictEqual(by.CE.long_name, 'European Community');
      assert.strictEqual(p.filter((x) => !x.long_name).length, 13);
      // shipped data/parties.json is this parse of this fixture
      assert.deepStrictEqual(PARTIES, p);
    });
  } else skip('search form', 'tests/fixtures/search-form.html missing');

  const no = fixture('search-NO.html');
  if (no) {
    test('Parties=NO: 101 rows = site count, 8 undated, 3 Procès-Verbaux, dates from <time>', () => {
      const r = I.parseResults(doc(no));
      assert.strictEqual(r.site_total, 101);
      assert.strictEqual(r.results.length, 101);
      assert.ok(r.results.every((x) => /^\d{7}$/.test(x.id) && x.title.length > 5));
      assert.strictEqual(r.results.filter((x) => !x.signature).length, 8);
      assert.deepStrictEqual(r.results.filter((x) => x.is_proces_verbal).map((x) => x.id), ['2017039', '2014064', '2012060']);
      const top = r.results.find((x) => x.id === '2026005');
      assert.strictEqual(top.signature, '2026-03-26');
      assert.ok(r.results.some((x) => x.id === '2011036' && x.signature === null), 'aviation agreement should be undated in the list');
      assert.strictEqual(r.results.find((x) => x.id === '2023045').entry_into_force, '2025-08-01');
    });
  } else skip('Parties=NO results', 'tests/fixtures/search-NO.html missing');

  const nois = fixture('search-NO-IS.html');
  if (nois && no) {
    test('Parties=NO&Parties=IS: 135 rows (OR), superset of NO, 2025008 flagged PV', () => {
      const r = I.parseResults(doc(nois));
      assert.strictEqual(r.site_total, 135);
      assert.strictEqual(r.results.length, 135);
      const noIds = new Set(I.parseResults(doc(no)).results.map((x) => x.id));
      const ids = new Set(r.results.map((x) => x.id));
      for (const id of noIds) assert.ok(ids.has(id), `NO row ${id} missing from OR result`);
      assert.strictEqual(ids.size - noIds.size, 34, 'IS-only rows: 135 − 101');
      assert.ok(r.results.find((x) => x.id === '2025008').is_proces_verbal);
    });
  } else skip('Parties=NO&Parties=IS', 'fixture missing');

  const d2011036 = fixture('agreement-2011036.html');
  if (d2011036) {
    test('agreement 2011036: provisional application, 31 parties all coded, Austria declaration, no agreement-level dates', () => {
      const r = I.parseDetail(doc(d2011036), '2011036', INDEX);
      assert.ok(r.title.length > 10);
      assert.strictEqual(r.observations, 'Provisional application as from 21/06/2011 (except Austria, see Declaration)');
      assert.strictEqual(r.signature, null);
      assert.strictEqual(r.signature_place, 'Luxembourg & Oslo');
      assert.strictEqual(r.entry_into_force, null);
      assert.strictEqual(r.parties.length, 31);
      assert.deepStrictEqual(r.parties_without_code, []);
      assert.strictEqual(r.party_codes.length, 31);
      for (const c of ['B', 'CZ', 'D', 'IRL', 'GR', 'A', 'SF', 'S', 'GB', 'UE', 'IS', 'NO', 'US']) assert.ok(r.party_codes.includes(c), `code ${c}`);
      const at = r.parties.find((p) => p.code === 'A');
      assert.strictEqual(at.has_declaration, true);
      assert.ok(/partyid=A/.test(at.declaration_url));
      assert.strictEqual(at.signature, '2011-06-16');
      assert.strictEqual(at.notification, '2020-07-02');
      assert.strictEqual(at.entry_into_force_inherited, true);
      assert.strictEqual(at.inherited_entry_into_force, null);
      assert.strictEqual(r.parties.filter((p) => p.has_declaration).length, 1);
      assert.ok(/\(above left\)/.test(r.ratification_footnote));
      assert.strictEqual(r.oj_references.length, 2);
      assert.ok(r.oj_references.some((o) => o.oj && o.oj.issue === '283' && o.oj.year === '2011'));
    });
  } else skip('agreement 2011036', 'tests/fixtures/agreement-2011036.html missing');

  const d2016032 = fixture('agreement-2016032.html');
  if (d2016032) {
    test('agreement 2016032: OJ L 141 (2016), Brussels 2016-05-03, EIF 2017-09-01, four coded parties', () => {
      const r = I.parseDetail(doc(d2016032), '2016032', INDEX);
      const oj = r.oj_references.find((x) => x.oj && x.oj.series === 'L' && x.oj.issue === '141' && x.oj.year === '2016');
      assert.ok(oj, JSON.stringify(r.oj_references));
      assert.ok(/eur-lex\.europa\.eu/.test(oj.url));
      assert.strictEqual(r.signature, '2016-05-03');
      assert.strictEqual(r.signature_place, 'Brussels');
      assert.strictEqual(r.entry_into_force, '2017-09-01');
      assert.deepStrictEqual(r.party_codes, ['UE', 'IS', 'LI', 'NO']);
    });
  } else skip('agreement 2016032', 'tests/fixtures/agreement-2016032.html missing');

  const dfr = fixture('agreement-2016032-fr.html');
  if (dfr) {
    test('agreement 2016032 (fr): French title and OJ link, table names not coded except code-like ones', () => {
      const r = I.parseDetail(doc(dfr), '2016032', INDEX);
      assert.ok(/^Accord entre l'Union européenne/.test(r.title), r.title);
      assert.ok(/\/legal-content\/fr\//.test(r.oj_references[0].url));
      assert.strictEqual(r.signature_place, 'Bruxelles');
      assert.strictEqual(r.parties.length, 4);
      assert.ok(r.parties_without_code.length >= 3, 'French party names are not in the English index — detail(id, "en") for codes');
    });
  } else skip('agreement 2016032 (fr)', 'tests/fixtures/agreement-2016032-fr.html missing');

  const decl = fixture('ratification-2011036-A.html');
  if (decl) {
    test('ratification 2011036/A (old Bootstrap template): declaration text present', () => {
      const t = I.mainText(doc(decl));
      assert.ok(t.length > 200, `text too short: ${t.length}`);
      assert.ok(/austria/i.test(t));
    });
  } else skip('ratification 2011036/A', 'tests/fixtures/ratification-2011036-A.html missing');

  console.log(`\n${passed} passed, ${skipped} skipped${process.exitCode ? ', FAILURES above' : ''}`);
}
