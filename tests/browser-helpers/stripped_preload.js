// Preload (`node -r`) that makes every read of a browser helper
// (plugins/*/skills/*/scripts/browser/*.js) return what
// shared/browser-paste/paste.py makes of it, so a helper's own test suite runs
// against the copy that actually gets pasted. require() reads through
// fs.readFileSync too, so this covers both ways the suites load a helper.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..', '..');
const PASTE = path.join(ROOT, 'shared', 'browser-paste', 'paste.py');
const HELPER = /[\\/]plugins[\\/][^\\/]+[\\/]skills[\\/][^\\/]+[\\/]scripts[\\/]browser[\\/][^\\/]+\.js$/;
const PY = process.platform === 'win32' ? 'python' : 'python3';

const real = fs.readFileSync;
const cache = new Map();

fs.readFileSync = function (file, options) {
  const p = typeof file === 'string' ? path.resolve(file) : null;
  if (!p || !HELPER.test(p)) return real.apply(fs, arguments);
  if (!cache.has(p)) {
    const line = execFileSync(PY, [PASTE, p], { encoding: 'utf8' });
    const out = line.slice(0, line.indexOf('  ('));
    cache.set(p, real.call(fs, out, 'utf8'));
    process.env.CLT_STRIPPED_SEEN = (process.env.CLT_STRIPPED_SEEN || '') + path.basename(p) + ' ';
  }
  const text = cache.get(p);
  const enc = typeof options === 'string' ? options : options && options.encoding;
  return enc ? text : Buffer.from(text, 'utf8');
};

process.on('exit', () => {
  if (!process.env.CLT_STRIPPED_SEEN) console.log('stripped_preload: NO helper was read through the preload');
  else console.log('stripped_preload: ran against stripped ' + process.env.CLT_STRIPPED_SEEN.trim());
});
