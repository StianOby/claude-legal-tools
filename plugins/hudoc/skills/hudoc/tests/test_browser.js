#!/usr/bin/env node
// Tests for scripts/browser/hudoc.js (the in-page fallback helper). No
// network and no npm dependencies: fetch and location are stubbed, and the
// DOCX fixtures are tiny synthetic files (one deflated, one stored) with the
// constructs the converter has to handle — tabs, entities, footnote
// references, a text box, separator pseudo-footnotes.
//
// The conversion must match docx_to_text() in scripts/hudoc.py character for
// character; tests/test_docx.py checks the same fixtures on the Python side.
//
// Run with `node plugins/hudoc/skills/hudoc/tests/test_browser.js`.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'scripts', 'browser', 'hudoc.js');
const hd = require(SRC);
const FIX = path.join(__dirname, 'fixtures');

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else { console.log(`  FAIL ${name}: got ${g}, want ${w}`); failures += 1; }
}

const MINI_TEXT =
  'CASE OF TEST v. NORWAY\n\n' +
  '1. The applicant & his wife complained [fn 1].\n\n' +
  '(a) a sub-paragraph that belongs to paragraph 1\n\n' +
  'II.  ALLEGED VIOLATION OF ARTICLE 8\n\n' +
  '2. The Court reiterates “margin of appreciation” [fn 2].\n\n' +
  'A text box: inside\n\n' +
  'FOR THESE REASONS, THE COURT\n\n' +
  '1. Holds, unanimously, that there has been a violation of Article 8;\n\n' +
  'FOOTNOTES\n\n' +
  '[fn 1] See Smith v. Norway, no. 1/01. Second paragraph of the note.\n\n' +
  '[fn 2] Case-law cited.\n';

const ROWS = [
  { itemid: '003-1', docname: 'Press release', doctype: 'PR', doctypebranch: 'GRANDCHAMBER', languageisocode: 'ENG', kpdate: '2021-05-25T00:00:00' },
  { itemid: '001-2', docname: 'CASE OF X v. Y', doctype: 'HEJUD', doctypebranch: 'CHAMBER', languageisocode: 'ENG', kpdate: '2018-09-13T00:00:00' },
  { itemid: '001-3', docname: 'AFFAIRE X c. Y', doctype: 'HFJUD', doctypebranch: 'GRANDCHAMBER', languageisocode: 'FRE', kpdate: '2021-05-25T00:00:00' },
  { itemid: '001-4', docname: 'CASE OF X v. Y', doctype: 'HEJUD', doctypebranch: 'GRANDCHAMBER', languageisocode: 'ENG', kpdate: '2021-05-25T00:00:00',
    scl: 'Klass and Others v. Germany, 6 September 1978, Series A no. 28; Roman Zakharov v. Russia [GC], no. 47143/06, § 232, ECHR 2015' },
  { itemid: '001-5', docname: 'CASE OF X v. Y (dec.)', doctype: 'HEDEC', doctypebranch: 'ADMISSIBILITY', languageisocode: 'ENG', kpdate: '2015-01-01T00:00:00' },
];

function buf(file) {
  const b = fs.readFileSync(path.join(FIX, file));
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
}

// Stub the page: query answers with ROWS, the DOCX endpoint with `docx`.
function stub({ docx = buf('mini.docx'), queryStatus = 200, queryBody = null, docxStatus = 200 } = {}) {
  const seen = [];
  hd._deps.location = () => ({ origin: 'https://hudoc.echr.coe.int' });
  hd._deps.fetch = async (url) => {
    seen.push(url);
    if (url.startsWith('/app/query/results')) {
      const body = queryBody || JSON.stringify({ resultcount: ROWS.length, results: ROWS.map((c) => ({ columns: c })) });
      return { ok: queryStatus === 200, status: queryStatus, text: async () => body };
    }
    const b = docxStatus === 200 ? docx : new TextEncoder().encode('<html><title>Just a moment...</title></html>').buffer;
    return { ok: docxStatus === 200, status: docxStatus, arrayBuffer: async () => b };
  };
  for (const k of Object.keys(hd.cache.items)) delete hd.cache.items[k];
  return seen;
}

(async () => {
  console.log('DOCX conversion (must match hudoc.py docx_to_text)');
  check('deflated zip', await hd._internal.docxToText(buf('mini.docx')), MINI_TEXT);
  check('stored zip', await hd._internal.docxToText(buf('mini-stored.docx')), MINI_TEXT);

  console.log('Reference forms');
  const rc = hd._internal.referenceClause;
  check('itemid', rc('001-57619'), { clause: 'itemid:"001-57619"', length: 1 });
  check('appno (first of several)', rc('58170/13;62322/14').clause, 'appno:"58170/13"');
  check('ECLI upper-cased', rc('ecli:ce:echr:1989:0707jud001403888').clause, 'ecli:"ECLI:CE:ECHR:1989:0707JUD001403888"');
  check('Lucene passes through', rc('docname:(big brother)').clause, 'docname:(big brother)');
  // Same table as tests/test_references.py runs through hudoc.py.
  const REFS = JSON.parse(fs.readFileSync(path.join(FIX, 'references.json'), 'utf8'));
  for (const [ref, clause, fallback] of REFS) {
    const got = rc(ref);
    check(ref, [got.clause, got.fallback ?? null], [clause, fallback]);
  }
  check('query URL has the site filter and brackets',
    decodeURIComponent(hd._internal.queryUrl('itemid:"1"', { fields: ['itemid'], length: 1 })),
    '/app/query/results?query=(contentsitename=ECHR) AND (itemid:"1")&select=itemid&sort=&start=0&length=1');

  console.log('resolve() picks the best row, as hudoc.py does');
  stub();
  check('English GC judgment beats press release, French and Chamber', (await hd.resolve('X v. Y')).itemid, '001-4');
  check('language preference', (await hd.resolve('X v. Y', { langPref: ['FRE', 'ENG'] })).itemid, '001-3');
  check('doctype filter', (await hd.resolve('X v. Y', { doctype: 'ADMISSIBILITY' })).itemid, '001-5');
  check('doctype filter with no row', (await hd.resolve('X v. Y', { doctype: 'COMMITTEE' })).error, 'no_match');
  // A respondent-narrowed query that finds nothing is retried without it.
  const urls = stub();
  const empty = JSON.stringify({ resultcount: 0, results: [] });
  const full = JSON.stringify({ resultcount: ROWS.length, results: ROWS.map((c) => ({ columns: c })) });
  const plainFetch = hd._deps.fetch;
  hd._deps.fetch = async (url) => {
    const r = await plainFetch(url);
    if (!url.startsWith('/app/query/results')) return r;
    const body = decodeURIComponent(url).includes('respondent:"TUR"') ? empty : full;
    return { ok: true, status: 200, text: async () => body };
  };
  check('respondent fallback', (await hd.resolve('X v. Turkey')).itemid, '001-4');
  check('narrowed query tried first', urls.map((u) => decodeURIComponent(u).includes('respondent:"TUR"')), [true, false]);
  // "Kurt v. Turkey": 213 hits because docname:Kurt matches inside Özkurt,
  // Bozkurt …; the judgment is on page 2 and older than the Özkurt one.
  const kurt = [{ itemid: '001-145119', docname: 'CASE OF BELEK AND ÖZKURT v. TURKEY (No. 7)', doctype: 'HEJUD', doctypebranch: 'COMMITTEE', languageisocode: 'ENG', kpdate: '2014-07-01T00:00:00' }];
  for (let i = 0; i < 150; i++) kurt.push({ itemid: `001-9${i}`, docname: `CASE OF BOZKURT ${i} v. TURKEY`, doctype: 'HEJUD', doctypebranch: 'CHAMBER', languageisocode: 'ENG', kpdate: '2010-01-01T00:00:00' });
  kurt.push({ itemid: '001-58198', docname: 'CASE OF KURT v. TURKEY', doctype: 'HEJUD', doctypebranch: 'CHAMBER', languageisocode: 'ENG', kpdate: '1998-05-25T00:00:00' });
  for (let i = 0; i < 61; i++) kurt.push({ itemid: `001-8${i}`, docname: `CASE OF KIZILKURT ${i} v. TURKEY`, doctype: 'HEJUD', doctypebranch: 'CHAMBER', languageisocode: 'ENG', kpdate: '2012-01-01T00:00:00' });
  const kurtUrls = stub();
  hd._deps.fetch = async (url) => {
    kurtUrls.push(url);
    const q = new URLSearchParams(url.split('?')[1]);
    const start = Number(q.get('start')); const length = Number(q.get('length'));
    const body = JSON.stringify({ resultcount: kurt.length, results: kurt.slice(start, start + length).map((c) => ({ columns: c })) });
    return { ok: true, status: 200, text: async () => body };
  };
  check('Kurt v. Turkey finds the whole-word match past page 1', (await hd.resolve('Kurt v. Turkey')).itemid, '001-58198');
  check('pages read up to the hit count', kurtUrls.map((u) => new URLSearchParams(u.split('?')[1]).get('start')), ['0', '50', '150']);
  stub();
  const cit = await hd.citations('X v. Y');
  check('citations parsed from scl', cit.cited.map((c) => [c.name, c.appnos]),
    [['Klass and Others v. Germany, 6 September 1978, Series A no. 28', []], ['Roman Zakharov v. Russia [GC]', ['47143/06']]]);

  console.log('load(), paragraph(), grep(), page()');
  const seen = stub();
  const info = await hd.load('X v. Y');
  check('load summary', [info.itemid, info.totalChars, info.numberedBlocks], ['001-4', MINI_TEXT.length, 3]);
  check('DOCX URL carries filename=', seen.some((u) => u === '/app/conversion/docx/?library=ECHR&id=001-4&filename=001-4.docx'), true);
  const p1 = await hd.paragraph('001-4', 1);
  check('paragraph 1 with its sub-paragraph, heading dropped',
    p1.text, '1. The applicant & his wife complained [fn 1].\n\n(a) a sub-paragraph that belongs to paragraph 1');
  check('restarted numbering is flagged', /also starts 1 later block/.test(p1.note), true);
  check('paragraph 2 stops at FOR THESE REASONS',
    (await hd.paragraph('001-4', 2)).text,
    '2. The Court reiterates “margin of appreciation” [fn 2].\n\nA text box: inside');
  check('missing paragraph', (await hd.paragraph('001-4', 9)).error, 'not_found');
  const g = await hd.grep('001-4', 'margin of  appreciation', 10);
  check('grep: literal, whitespace-tolerant, with paragraph number', [g.total, g.hits[0].paragraph], [1, 2]);
  check('grep: regex metacharacters are literal', (await hd.grep('001-4', '(a)')).total, 1);
  check('not loaded', (await hd.page('001-999')).error, 'not_loaded');

  // A long text full of quotes and newlines: JSON escaping must not push a
  // page over the tool limit.
  hd.cache.items['001-big'] = { meta: {}, text: ('"quoted"\n\n'.repeat(12000)) };
  let off = 0; let pages = 0; let maxLen = 0;
  for (;;) {
    const pg = await hd.page('001-big', off);
    maxLen = Math.max(maxLen, JSON.stringify(pg).length);
    pages += 1;
    if (pg.next === null) break;
    off = pg.next;
  }
  check('every page fits PAGE_SIZE once serialised', maxLen <= hd.PAGE_SIZE, true);
  check('pages cover the whole text', off + (await hd.page('001-big', off)).text.length, 12000 * 10);

  console.log('Errors');
  stub({ docxStatus: 403 });
  check('challenge on the DOCX', (await hd.load('X v. Y')).error, 'challenge');
  stub({ queryStatus: 403, queryBody: '<title>Just a moment...</title>' });
  check('challenge on the query', (await hd.search('article:"8"')).error, 'challenge');
  hd._deps.location = () => ({ origin: 'https://www.example.org' });
  check('wrong origin', (await hd.ready()).error, 'wrong_origin');

  console.log('Paste guard');
  const src = fs.readFileSync(SRC, 'utf8');
  const ctx = { location: { origin: 'https://hudoc.echr.coe.int' } };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  const first = ctx.__hd;
  vm.runInContext(src, ctx);
  check('same version is a no-op', ctx.__hd === first, true);
  ctx.__hd = { VERSION: '0.0.0-old' };
  vm.runInContext(src, ctx);
  check('older version is replaced', ctx.__hd.VERSION, first.VERSION);

  if (failures) { console.log(`\n${failures} failure(s)`); process.exit(1); }
  console.log('\nall passed');
})();
