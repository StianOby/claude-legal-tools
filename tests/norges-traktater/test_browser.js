#!/usr/bin/env node
// Tests for scripts/browser/norges_traktater.js (the in-page helper). No
// network and no npm dependencies: fetch and location are stubbed with the
// saved lovdata.no pages in fixtures/ (routing in fixtures/routes.json).
//
// Parity: fixtures/parity_expected.json is what traktater.py returns for the
// same pages and cases (tests/test_browser_parity.py checks and regenerates
// it). Every case here must produce the identical structure from the JS
// helper.
//
// Run with `node tests/norges-traktater/test_browser.js`.

const fs = require('fs');
const path = require('path');

const nt = require(path.join(__dirname, '..', '..', 'plugins', 'norges-traktater', 'skills', 'norges-traktater', 'scripts', 'browser', 'norges_traktater.js'));
const FIX = path.join(__dirname, 'fixtures');
const ROUTES = JSON.parse(fs.readFileSync(path.join(FIX, 'routes.json'), 'utf8'));
const CASES = JSON.parse(fs.readFileSync(path.join(FIX, 'parity_cases.json'), 'utf8'));
const EXPECTED = JSON.parse(fs.readFileSync(path.join(FIX, 'parity_expected.json'), 'utf8'));

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else {
    console.log(`  FAIL ${name}`);
    if (g.length + w.length < 600) console.log(`       got  ${g}\n       want ${w}`);
    else {
      let i = 0; while (i < g.length && g[i] === w[i]) i++;
      console.log(`       first difference at char ${i}:\n       got  ...${g.slice(Math.max(0, i - 60), i + 100)}\n       want ...${w.slice(Math.max(0, i - 60), i + 100)}`);
    }
    failures += 1;
  }
}

const read = (name) => {
  const p = path.join(FIX, name);
  return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
};

// Canonical request: path plus sorted query parameters.
function canon(url) {
  const u = new URL(url, 'https://lovdata.no');
  const q = [...u.searchParams.entries()].sort((a, b) => (a[0] + '=' + a[1]).localeCompare(b[0] + '=' + b[1]));
  return u.pathname + (q.length ? '?' + new URLSearchParams(q).toString() : '');
}

// Python sorts the canonical strings by code point; do the same here.
const sortedUnique = (xs) => [...new Set(xs)].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

let requests = [];
let status = {};
function route(url) {
  const u = new URL(url, 'https://lovdata.no');
  if (u.pathname === '/register/traktater') {
    if (![...u.searchParams.keys()].length) return read('register.html');
    if (u.searchParams.get('search') === 'menneskerett') {
      return read(`search_menneskerett_${u.searchParams.get('offset') || '0'}.html`);
    }
    return read('search_wien_0.html');
  }
  const tid = u.pathname.split('/').pop();
  return read(`doc_${ROUTES.aliases[tid] || tid}.html`);
}
nt._deps.location = () => ({ origin: 'https://lovdata.no' });
nt._deps.fetch = async (url) => {
  requests.push(canon(url));
  if (status.all) return { ok: false, status: status.all, text: async () => '' };
  const body = route(url);
  if (body === null) return { ok: false, status: 404, text: async () => '' };
  return { ok: true, status: 200, text: async () => body };
};

// Collect a chunked text/article result into the Python-shaped one, checking
// the size limit on every chunk.
async function collect(fn) {
  let res = await fn(0);
  if (res.error && !res.available_articles) return res;
  if (!('next' in res)) return res; // available:false etc. carry no chunk keys
  let body = res.body; let chunks = 1;
  while (true) {
    if (JSON.stringify(res).length > nt.PAGE_SIZE) throw new Error('chunk over PAGE_SIZE');
    if (res.next === null) break;
    res = await fn(res.next);
    body += res.body; chunks += 1;
  }
  const { total, offset, next, ...rest } = res;
  return { ...rest, body, _chunks: chunks, _total: total };
}

async function runCase(c) {
  const a = c.args;
  nt.cache.clear();
  requests = [];
  let got;
  if (c.op === 'search') {
    got = await nt.search(a.query || '', { year: a.year, country: a.country, context: a.context, max: a.max, full: a.full });
  } else if (c.op === 'meta') {
    got = await nt.meta(a.id);
  } else if (c.op === 'meta_batch') {
    got = await nt.meta(a.ids);
  } else if (c.op === 'text') {
    got = await collect((offset) => nt.text(a.id, { offset, length: 20000 }));
  } else if (c.op === 'article') {
    got = await collect((offset) => nt.article(a.id, a.article, { offset, length: 20000 }));
  } else if (c.op === 'countries') {
    got = await nt.countries(a.query);
  } else if (c.op === 'status') {
    const s = await nt.status();
    got = { reachable: s.reachable, total: s.total, years: s.years, countries: s.countries };
  }
  // Errors: Python {"__error": msg}; JS {error, detail}.
  if (got && got.error && got.detail !== undefined && !got.available_articles && !Array.isArray(got)) {
    got = { __error: got.detail };
  }
  return got;
}

(async () => {
  console.log('Parity with traktater.py (same pages, same cases)');
  for (let i = 0; i < CASES.length; i++) {
    const c = CASES[i]; const want = EXPECTED[i];
    if (c.name !== want.name) { console.log('  FAIL case list and parity_expected.json differ: regenerate'); failures++; break; }
    const got = await runCase(c);
    // JS adds keys Python has no equivalent for; drop those before comparing.
    if (got && typeof got === 'object') { delete got._chunks; delete got._total; }
    const cleaned = JSON.parse(JSON.stringify(got));
    if (cleaned && cleaned.full_title_failures !== undefined) delete cleaned.full_title_failures;
    check(c.name, cleaned, want.result);
    check('  requests: ' + c.name, sortedUnique(requests), want.requests);
  }

  console.log('Chunking');
  nt.cache.clear();
  const big = await collect((offset) => nt.text('1992-05-02-1', { offset }));
  check('EEA text needs several chunks (default size)', big._chunks > 1, true);
  const first = await nt.text('1992-05-02-1');
  check('first chunk reports total and next', [first.total > first.body.length, first.next === first.body.length, first.offset], [true, true, 0]);
  check('every default-size chunk fits', JSON.stringify(first).length <= nt.PAGE_SIZE, true);
  const tail = await nt.text('1992-05-02-1', { offset: first.total - 10, length: 5000 });
  check('last chunk ends with next:null', [tail.body.length, tail.next], [10, null]);
  const short = await nt.text('1948-12-09-1');
  check('short text is one chunk', short.next, null);

  console.log('Errors are returned, not thrown');
  status = { all: 405 };
  nt.cache.clear();
  check('405 -> http_405 on search', (await nt.search('Wien')).error, 'http_405');
  check('405 -> http_405 on text', (await nt.text('1948-12-09-1')).error, 'http_405');
  check('405 -> http_405 on status', (await nt.status()).error, 'http_405');
  status = {};
  nt._deps.location = () => ({ origin: 'https://example.org' });
  check('wrong tab origin', (await nt.status()).error, 'wrong_origin');
  nt._deps.location = () => ({ origin: 'https://lovdata.no' });
  check('bad id', (await nt.text('foo')).error, 'invalid');
  check('empty batch', (await nt.meta([' ', '# nothing'])).error, 'invalid');

  console.log('Result-size guard');
  nt.cache.clear();
  const many = await nt.meta(Array.from({ length: 4 }, () => '1992-05-02-1').concat(['1951-07-28-1']));
  check('a small batch is returned whole', Array.isArray(many), true);
  const ids = ['1992-05-02-1', '1951-07-28-1', '1948-12-09-1', '1950-11-04-1'];
  const total = JSON.stringify(await Promise.all(ids.map((i) => nt.meta(i)))).length;
  console.log(`       (four metas together: ${total} chars)`);

  console.log('Idempotent guard');
  check('VERSION set', typeof nt.VERSION, 'string');
  const before = nt;
  global.window = { __nt: before };
  delete require.cache[require.resolve(path.join(__dirname, '..', '..', 'plugins', 'norges-traktater', 'skills', 'norges-traktater', 'scripts', 'browser', 'norges_traktater.js'))];
  const again = require(path.join(__dirname, '..', '..', 'plugins', 'norges-traktater', 'skills', 'norges-traktater', 'scripts', 'browser', 'norges_traktater.js'));
  check('same version already on window is left alone', global.window.__nt === before, true);
  void again;

  console.log(failures ? `${failures} failure(s)` : 'all ok');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
