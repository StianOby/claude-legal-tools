#!/usr/bin/env node
// Copy shared/source-text/source_text.js into the browser helpers that embed
// it, replacing the block between its marker comments. A helper that has no
// block yet gets it before the line given as the anchor in HELPERS.
//
//   node .github/scripts/embed-source-text.js
//
// Run from the repo root after editing the canonical copy, then bump each
// changed helper's HELPER_VERSION and plugin version (CLAUDE.md).
// tests/source-text/test_source_text.js fails while a copy differs.

const fs = require('fs');

const CANON = fs.readFileSync('shared/source-text/source_text.js', 'utf8').replace(/\r\n/g, '\n');
const START = CANON.split('\n')[0] + '\n';
const END = '    // --- end source text ---\n';
const HELPERS = {
  'plugins/norges-traktater/skills/norges-traktater/scripts/browser/norges_traktater.js': '    // --- Body / articles',
  'plugins/lovdata-pro/skills/lovdata-pro/scripts/browser/lovdata_pro.js': '    // Renders a block element',
  'plugins/eu-agreements-treaties/skills/eu-agreements-treaties/scripts/browser/consilium.js': '    // --- declarations / reservations',
};

for (const [file, anchor] of Object.entries(HELPERS)) {
  const src = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const a = src.indexOf(START); const b = src.indexOf(END);
  let out;
  if (a >= 0 && b > a) out = src.slice(0, a) + CANON + src.slice(b + END.length);
  else {
    const at = src.indexOf(anchor);
    if (at < 0) throw new Error(`${file}: anchor not found: ${anchor}`);
    out = src.slice(0, at) + CANON + '\n' + src.slice(at);
  }
  if (out !== src) {
    fs.writeFileSync(file, out);
    console.log(`[fixed] ${file}`);
  } else console.log(`[ok   ] ${file}`);
}
