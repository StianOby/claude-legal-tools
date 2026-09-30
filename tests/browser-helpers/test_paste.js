#!/usr/bin/env node
// shared/browser-paste/paste.py: the stripped copy of every browser helper
// must parse, be smaller, keep HELPER_VERSION and its window.__x global, carry
// no backslash-u escapes (javascript_tool decodes them), and pass the helper's
// own test suite. The suites are rerun with stripped_preload.js, which hands
// them the stripped text wherever they read the helper file.
// Run with `node tests/browser-helpers/test_paste.js` (needs python3).

const fs = require('fs');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..', '..');
const PASTE = path.join(ROOT, 'shared', 'browser-paste', 'paste.py');
const PRELOAD = path.join(__dirname, 'stripped_preload.js');
const PY = process.platform === 'win32' ? 'python' : 'python3';
const BS = String.fromCharCode(92);

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ': ' + detail}`);
  if (!ok) failures++;
};

const helpers = [];
for (const plugin of fs.readdirSync(path.join(ROOT, 'plugins'))) {
  const dir = path.join(ROOT, 'plugins', plugin, 'skills', plugin, 'scripts', 'browser');
  if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir)) if (f.endsWith('.js')) helpers.push({ plugin, file: path.join(dir, f) });
}
check('found the browser helpers', helpers.length >= 5, `${helpers.length} found`);

for (const { plugin, file } of helpers) {
  const name = path.basename(file);
  const src = fs.readFileSync(file, 'utf8');
  const line = execFileSync(PY, [PASTE, file], { encoding: 'utf8' });
  const out = fs.readFileSync(line.slice(0, line.indexOf('  (')), 'utf8');
  let err = null;
  try { new Function(out); } catch (e) { err = e.message; }
  check(`${name}: parses`, err === null, err);
  check(`${name}: smaller`, out.length < src.length * 0.8, `${out.length} of ${src.length}`);
  const ver = src.match(/const HELPER_VERSION = '[^']+'/);
  check(`${name}: keeps HELPER_VERSION`, ver && out.includes(ver[0]), 'missing');
  const g = src.match(/window\.__[a-z]+ = /);
  check(`${name}: keeps its global`, g && out.includes(g[0]), 'missing');
  check(`${name}: no backslash-u`, !out.includes(BS + 'u'), 'found one');
  check(`${name}: plugin carries paste.py`,
    fs.existsSync(path.join(path.dirname(file), 'paste.py')), 'scripts/browser/paste.py missing');

  const suite = path.join(ROOT, 'tests', plugin, 'test_browser.js');
  if (!fs.existsSync(suite)) continue;
  const r = spawnSync(process.execPath, ['-r', PRELOAD, suite], { encoding: 'utf8', cwd: path.dirname(suite) });
  const ran = /stripped_preload: ran against stripped/.test(r.stdout);
  check(`${name}: own suite passes on the stripped copy`, r.status === 0 && ran,
    (r.stdout + r.stderr).split('\n').filter((l) => /FAIL|Error|NO helper/.test(l)).slice(0, 5).join(' | ') || `exit ${r.status}`);
}
// tests/eu-agreements-treaties/run.js needs linkedom; CI runs it with the
// preload in its own step, after `npm ci`.

console.log(failures ? `${failures} failure(s)` : 'all ok');
process.exit(failures ? 1 : 0);
