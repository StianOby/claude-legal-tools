#!/usr/bin/env node
// Tests for shared/source-text/source_text.js: every browser helper that
// embeds it carries an identical copy, and it gives the same results as
// source_text.py (the cases mirror tests/source-text/test_source_text.py).
//
// Run with `node tests/source-text/test_source_text.js`.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
const CANON = fs.readFileSync(path.join(ROOT, 'shared', 'source-text', 'source_text.js'), 'utf8');
const HELPERS = [
  'plugins/norges-traktater/skills/norges-traktater/scripts/browser/norges_traktater.js',
  'plugins/lovdata-pro/skills/lovdata-pro/scripts/browser/lovdata_pro.js',
  'plugins/eu-agreements-treaties/skills/eu-agreements-treaties/scripts/browser/consilium.js',
];
const START = '    // --- source text (canonical copy: shared/source-text/source_text.js) ---\n';
const END = '    // --- end source text ---\n';

let failures = 0;
function check(name, got, want) {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g === w) console.log('  ok   ' + name);
  else { console.log(`  FAIL ${name}: got ${g}, want ${w}`); failures += 1; }
}

console.log('copies in the helpers');
for (const h of HELPERS) {
  const src = fs.readFileSync(path.join(ROOT, h), 'utf8').replace(/\r\n/g, '\n');
  const a = src.indexOf(START); const b = src.indexOf(END);
  const copy = a >= 0 && b > a ? src.slice(a, b + END.length) : null;
  check(path.basename(h), copy === null ? 'missing' : (copy === CANON.replace(/\r\n/g, '\n') ? 'same' : 'differs'), 'same');
}

const st = vm.runInNewContext(`${CANON}; ({ stMarkEmphasis, stFinish, stPlain, stSuperscript, stListLabel, stOlKind, stMarkLists, stFold, ST_SPACES })`);
const html = (s) => st.stFinish(st.stMarkEmphasis(s));

console.log('emphasis');
check('italic', html('endossere vekslen <i>in blanco</i> eller'), 'endossere vekslen *in blanco* eller');
check('bold', html('<strong>§ 1.</strong> Formål'), '**§ 1.** Formål');
check('both', html('<b><i>Holship</i></b>'), '***Holship***');
check('nested part', html('<i>see <b>Holship</b>, para 90</i>'), '*see **Holship**, para 90*');
check('inner ends first', html('<b><i>a</i> b</b>'), '***a* b**');
check('spaced runs merge', html('<i>a</i> <i>b</i>'), '*a b*');
check('spaces go outside', html('a<i> b </i>c'), 'a *b* c');
check('empty emphasis dropped', html('a<i> </i>b<b></b>c'), 'a bc');
check('adjacent runs merge', html('<i>Grendse</i><i>-Tractat</i>'), '*Grendse-Tractat*');
check('word with a suffix', html('<i>Holship</i>-saken'), '*Holship*-saken');
check('never spans a line', html('<i>first\nsecond</i>'), '*first*\n*second*');
check('attributes', html('<em class="x">y</em>'), '*y*');
check('unbalanced close ignored', html('a</i> b'), 'a b');
check('tag inside a malformed one', st.stMarkEmphasis('Fr.<STRONG]</STRONG>'), 'Fr.<STRONG]</STRONG>');
check('plain() drops markers', st.stPlain(st.stMarkEmphasis('<b>Title</b>')), 'Title');
check('no markers: unchanged', st.stFinish('a * b'), 'a * b');

console.log('superscript');
check('digit', st.stSuperscript('2'), '²');
check('signs', st.stSuperscript('-1'), '⁻¹');
check('letters', st.stSuperscript('er'), '^er^');
check('spaces kept outside', st.stSuperscript('st '), '^st^ ');

console.log('lists');
check('alpha', st.stListLabel(28, 'a'), 'ab');
check('roman', st.stListLabel(14, 'I'), 'XIV');
check('css', st.stOlKind(' style="list-style-type: upper-alpha"'), 'A');
check('markers', st.stMarkLists('<ol type="a" start="2"><li>x</li><li value="5">y</li></ol><ul><li>z</li></ul>'),
  '<ol type="a" start="2"><li>\nb. x</li><li value="5">\ne. y</li></ol><ul><li>\n- z</li></ul>');

console.log('spaces, fold');
check('nbsp', ('Art.' + String.fromCharCode(0xa0) + '20').replace(st.ST_SPACES, ' '), 'Art. 20');
check('fold', st.stFold('*in blanco* helse' + String.fromCharCode(0xad) + 'undersøkelse'), 'in blanco helseundersøkelse');

console.log(failures ? `${failures} failure(s)` : 'all ok');
process.exit(failures ? 1 : 0);
