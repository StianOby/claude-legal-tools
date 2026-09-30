#!/usr/bin/env node
// Every browser helper must survive being pasted through javascript_tool.
// That channel decodes backslash-u escapes in the code text before running it
// (cloud Cowork, 2026-09-30): a decoded U+2028/U+2029 inside a regex literal
// became a line break and norges_traktater.js failed with "Invalid regular
// expression: missing /". So: no backslash-u escapes at all, and the file must
// still parse after the channel's decoding.
// Run with `node tests/browser-helpers/test_paste_safe.js`.

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const BS = String.fromCharCode(92);           // no literal backslash-u in this file either
const ESCAPE = new RegExp(BS + BS + 'u(?:[0-9a-fA-F]{4}|' + BS + '{)', 'g');
const DECODE = new RegExp(BS + BS + 'u([0-9a-fA-F]{4})', 'g');

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ': ' + detail}`);
  if (!ok) failures++;
};

const helpers = [];
for (const plugin of fs.readdirSync(path.join(ROOT, 'plugins'))) {
  const dir = path.join(ROOT, 'plugins', plugin, 'skills', plugin, 'scripts', 'browser');
  if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir)) if (f.endsWith('.js')) helpers.push(path.join(dir, f));
}
check('found the browser helpers', helpers.length >= 5, `${helpers.length} found`);

for (const file of helpers) {
  const name = path.relative(ROOT, file).split(path.sep).join('/');
  const src = fs.readFileSync(file, 'utf8');
  const hits = [];
  src.split('\n').forEach((line, i) => { if (line.match(ESCAPE)) hits.push(i + 1); });
  check(`${name}: no backslash-u escapes`, hits.length === 0, `line(s) ${hits.join(', ')}`);
  const decoded = src.replace(DECODE, (m, h) => String.fromCharCode(parseInt(h, 16)));
  let err = null;
  try { new Function(decoded); } catch (e) { err = e.message; }
  check(`${name}: parses after the channel's decoding`, err === null, err);
}

console.log(failures ? `${failures} failure(s)` : 'all ok');
process.exit(failures ? 1 : 0);
