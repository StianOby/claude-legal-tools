#!/usr/bin/env node
// Tests for scripts/browser/lovdata_pro.js (the in-page helper). No network
// and no npm dependencies: the helper runs in a vm context with a stub
// window/location/document, and documents are put straight into its cache,
// so load() (cached), toc(), page() and grep() run without a DOM. section()
// needs a real DOM Range and is only exercised in the browser.
//
// Checks that every reply stays under PAGE_SIZE once JSON-encoded, that the
// paging continues where the last reply stopped, and that search() reads
// only results rendered by its own query.
//
// Run with `node tests/lovdata-pro/test_browser.js`.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'plugins', 'lovdata-pro', 'skills', 'lovdata-pro', 'scripts', 'browser', 'lovdata_pro.js'), 'utf8');

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else { console.log(`  FAIL ${name}: got ${g.slice(0, 200)}, want ${w.slice(0, 200)}`); failures += 1; }
}

// --- a fake Pro tab ---------------------------------------------------------

function anchor(href, title) {
  return { dataset: {}, textContent: title, getAttribute: (k) => (k === 'href' ? href : null) };
}

function makeTab() {
  const tab = { anchors: [], onEnter: null };
  const location = { hash: '#myPage' };
  const input = {
    value: '',
    focus() {},
    dispatchEvent(ev) { if (ev.type === 'keyup' && tab.onEnter) tab.onEnter(this.value); },
  };
  const document = {
    title: 'Min side - Lovdata Pro',
    querySelector: (sel) => (sel === '#quickSearchField-input' ? input : null),
    querySelectorAll: () => tab.anchors.slice(),
  };
  class Event { constructor(type) { this.type = type; } }
  class KeyboardEvent extends Event {}
  const HTMLInputElement = { prototype: {} };
  const ctx = { window: {}, location, document, Event, KeyboardEvent, HTMLInputElement, setTimeout, console };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return { lp: ctx.__lp, tab, location, input };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const { lp, tab, location } = makeTab();
  const LIMIT = lp.PAGE_SIZE;

  // Text that is expensive to JSON-encode: many newlines and quotes.
  const line = 'Avsnitt «x» med "sitat" og \\ skråstrek\n';
  const big = line.repeat(4000);
  const toc = Array.from({ length: 708 }, (_, i) => ({
    i, id: `kapittel-${i}`, level: 2 + (i % 3), title: `${i}.${i % 7} Forholdet til folkeretten og urfolks rettigheter`, chars: 1000,
  }));
  lp.cache['NOU/forarbeid/nou-2022-8'] = { title: 'NOU 2022: 8', metadata: { Dato: '2022-06-01' }, toc, fullText: big };

  console.log('load() / toc()');
  const d = await lp.load('NOU/forarbeid/nou-2022-8');
  check('load reply under PAGE_SIZE', JSON.stringify(d).length <= LIMIT, true);
  check('load reports truncated toc', [d.tocTotal, d.tocNext > 0, d.toc.length === d.tocNext], [708, true, true]);
  const all = [...d.toc];
  for (let next = d.tocNext; next !== null;) {
    const t = await lp.toc('NOU/forarbeid/nou-2022-8', next);
    check(`toc(${next}) under PAGE_SIZE`, JSON.stringify(t).length <= LIMIT, true);
    all.push(...t.toc);
    next = t.next;
  }
  check('toc pages rebuild the whole toc', JSON.stringify(all) === JSON.stringify(toc), true);

  console.log('page()');
  let text = '';
  let pages = 0;
  for (let offset = 0; offset !== null; pages++) {
    const p = await lp.page('NOU/forarbeid/nou-2022-8', offset);
    if (JSON.stringify(p).length > LIMIT) check(`page(${offset}) under PAGE_SIZE`, JSON.stringify(p).length, `<= ${LIMIT}`);
    text += p.text;
    offset = p.next;
  }
  check('every page under PAGE_SIZE', failures, 0);
  check('pages rebuild the whole text', text === big, true);
  check('a raw PAGE_SIZE slice of this text would be over the limit', JSON.stringify(big.slice(0, LIMIT)).length > LIMIT, true);
  check('so page() returns shorter slices', pages > big.length / LIMIT, true);

  console.log('grep()');
  const g = await lp.grep('NOU/forarbeid/nou-2022-8', 'sitat', 600, 1000);
  check('grep reply under PAGE_SIZE', JSON.stringify(g).length <= LIMIT, true);
  check('grep counts every match', g.matches, 4000);
  check('grep flags truncation', [g.truncated, g.hits.length < 1000], [true, true]);
  check('hit offset points at the match', big.substr(g.hits[3].offset, 5), 'sitat');
  const g2 = await lp.grep('NOU/forarbeid/nou-2022-8', 'sitat', 20, 5);
  check('small grep is not truncated', [g2.matches, g2.hits.length, g2.truncated], [4000, 5, undefined]);

  console.log('search()');
  // Old results on screen; the new query changes the hash at once but
  // renders its list 600 ms later. search() must not return the old list.
  tab.anchors = [anchor('#document/OLD/avgjorelse/old-1?rowNumber=1', 'Gammelt treff')];
  location.hash = '#result&id=1&q=gammel*';
  tab.onEnter = (q) => {
    location.hash = `#result&id=2&q=${encodeURIComponent(q.toLowerCase())}*`;
    setTimeout(() => { tab.anchors = [anchor('#document/HRSIV/avgjorelse/rt-2000-1811-x?rowNumber=1', 'Rt. 2000 s. 1811')]; }, 600);
  };
  let s = await lp.search('Rt-2000-1811', 10, { timeoutMs: 3000 });
  check('search waits for the new list', s.results && s.results.map((r) => r.path), ['HRSIV/avgjorelse/rt-2000-1811-x']);

  // Same query again, re-rendered with the same hrefs and hash: new nodes count.
  tab.onEnter = () => { setTimeout(() => { tab.anchors = [anchor('#document/HRSIV/avgjorelse/rt-2000-1811-x?rowNumber=1', 'Rt. 2000 s. 1811')]; }, 300); };
  s = await lp.search('Rt-2000-1811', 10, { timeoutMs: 3000 });
  check('repeated query with re-render', [s.error, s.results && s.results.length, s.reused], [undefined, 1, undefined]);

  // Same query again and the SPA does nothing: the results on screen are
  // this query's, so they are returned with reused:true.
  tab.onEnter = () => {};
  s = await lp.search('Rt-2000-1811', 10, { timeoutMs: 1000 });
  check('repeated query without re-render', [s.error, s.results && s.results.length, s.reused], [undefined, 1, true]);

  // A different query that never renders: timeout, not the stale list.
  s = await lp.search('HR-2016-2554-P', 10, { timeoutMs: 1000 });
  check('different query without results times out', s.error, 'search_timeout');

  console.log(failures ? `${failures} failure(s)` : 'all ok');
  process.exit(failures ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
