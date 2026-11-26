// Preload (`node -r`) that makes every read of lovdata_pro.js return the copy
// scripts/browser/paste_site.py makes for the site in LP_SITE (pro2 or
// klassisk), so a suite runs against the copy that gets pasted on that site.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SITE = process.env.LP_SITE;
const BROWSER = path.join(__dirname, '..', '..', 'plugins', 'lovdata-pro', 'skills', 'lovdata-pro', 'scripts', 'browser');
const HELPER = path.join(BROWSER, 'lovdata_pro.js');
const PY = process.platform === 'win32' ? 'python' : 'python3';

const real = fs.readFileSync;
let text = null;

fs.readFileSync = function (file, options) {
  const p = typeof file === 'string' ? path.resolve(file) : null;
  if (p !== HELPER) return real.apply(fs, arguments);
  if (text === null) {
    const line = execFileSync(PY, [path.join(BROWSER, 'paste_site.py'), SITE], { encoding: 'utf8' });
    text = real.call(fs, line.slice(0, line.indexOf('  (')), 'utf8');
  }
  const enc = typeof options === 'string' ? options : options && options.encoding;
  return enc ? text : Buffer.from(text, 'utf8');
};

process.on('exit', () => {
  console.log(text === null ? 'site_preload: NO helper was read' : `site_preload: ran against the ${SITE} copy`);
});
