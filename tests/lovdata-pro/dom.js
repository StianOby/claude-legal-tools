#!/usr/bin/env node
// DOM tests for toText() in scripts/browser/lovdata_pro.js: emphasis,
// superscripts, footnote markers, list labels, headings and inline content
// directly in a <div>, on Lovdata-style markup. Needs linkedom, installed
// for the eu-agreements-treaties tests (CI runs this in that step); skipped
// without it.
//
// Run with `node tests/lovdata-pro/dom.js` after
// `npm ci` in tests/eu-agreements-treaties.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let parseHTML;
try {
  ({ parseHTML } = require(path.join(__dirname, '..', 'eu-agreements-treaties', 'node_modules', 'linkedom')));
} catch (e) {
  console.log('skip (linkedom not installed: npm ci in tests/eu-agreements-treaties)');
  process.exit(0);
}

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'plugins', 'lovdata-pro', 'skills', 'lovdata-pro', 'scripts', 'browser', 'lovdata_pro.js'), 'utf8');
const ctx = { location: { hash: '' }, document: parseHTML('<html><body></body></html>').document, setTimeout, console };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(SRC, ctx);
const { toText } = ctx.__lp._internal;

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else { console.log(`  FAIL ${name}: got ${g}, want ${w}`); failures += 1; }
}
const text = (html) => toText(parseHTML(`<html><body><div id="d">${html}</div></body></html>`).document.getElementById('d'));

check('emphasis in a paragraph',
  text('<p>jf. <i>Rt.&nbsp;2015 s.&nbsp;93</i> avsnitt 40, se <b>særlig</b><i> </i>der</p>'),
  'jf. *Rt. 2015 s. 93* avsnitt 40, se **særlig** der');
check('nested', text('<p><i>se <b>Holship</b>, avsnitt 90</i></p>'), '*se **Holship**, avsnitt 90*');
check('headings plain', text('<h2><strong>§ 3</strong> Formål</h2><p>x</p>'), '## § 3 Formål\nx');
check('inline content in a div is one line',
  text('Saken gjelder <i>Holship</i>-dommen\n og <a href="#">HR-2016-2554-P</a>.'),
  'Saken gjelder *Holship*-dommen og HR-2016-2554-P.');
check('superscript and footnotes',
  text('<p>20 m<sup>2</sup>, protokoll 3<sup class="footnotereference">5</sup>, merke<sup>TM</sup></p>' +
       '<p><span class="footnoteLabel">5</span> Gjelder handel.</p>'),
  '20 m², protokoll 3[fn 5], merke^TM^\n[fn 5] Gjelder handel.');
check('list labels: data-name, <ol>, <ul>',
  text('<ol><li data-name="a.">første</li><li data-name="b.">andre</li></ol>' +
       '<ol type="i" start="2"><li>to</li><li>tre</li></ol><ul><li>punkt</li></ul>'),
  'a. første\nb. andre\nii. to\niii. tre\n- punkt');
check('<br> in a party list', text('<p>A (advokat X)<br>mot<br>B</p>'), 'A (advokat X)\nmot\nB');

console.log(failures ? `${failures} failure(s)` : 'all ok');
process.exit(failures ? 1 : 0);
