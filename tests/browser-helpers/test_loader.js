#!/usr/bin/env node
// shared/browser-loader/load.sh: the printed one-liner must load every real
// helper from the repo, be a no-op the second time, refuse a file whose hash
// differs, report a failed fetch, and contain no backslash (javascript_tool
// decodes escapes). A local HTTP server stands in for raw.githubusercontent.com.
// Run with `node tests/browser-helpers/test_loader.js` (needs bash, sha256sum).

const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..', '..');
const LOAD = path.join(ROOT, 'shared', 'browser-loader', 'load.sh');

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ': ' + detail}`);
  if (!ok) failures++;
};

// A path bash understands (Git Bash on Windows wants /c/...).
const posix = (p) => {
  if (process.platform !== 'win32') return p;
  try { return execFileSync('cygpath', ['-u', p], { encoding: 'utf8' }).trim(); } catch { return p.split(path.sep).join('/'); }
};

const printLoader = (helper, base) => execFileSync('bash', [posix(LOAD), posix(helper)], {
  encoding: 'utf8', env: { ...process.env, CLT_RAW_BASE: base },
}).trim();

// Run the printed line the way javascript_tool does: as an awaited expression.
const run = (line) => (0, eval)('(async () => ' + line + ')()');

let tamper = null; // path served with altered bytes
const server = http.createServer((req, res) => {
  const file = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
  if (!file.startsWith(ROOT) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  let body = fs.readFileSync(file);
  if (tamper && file === tamper) body = Buffer.concat([body, Buffer.from('\n// changed\n')]);
  res.writeHead(200, { 'content-type': 'text/plain' });
  res.end(body);
});

(async () => {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  globalThis.window = globalThis;

  const helpers = [];
  for (const plugin of fs.readdirSync(path.join(ROOT, 'plugins'))) {
    const dir = path.join(ROOT, 'plugins', plugin, 'skills', plugin, 'scripts', 'browser');
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) if (f.endsWith('.js')) helpers.push(path.join(dir, f));
  }
  check('found the browser helpers', helpers.length >= 5, `${helpers.length} found`);

  for (const helper of helpers) {
    const name = path.basename(helper);
    const line = printLoader(helper, base);
    check(`${name}: one line`, !line.includes('\n'), 'multi-line output');
    check(`${name}: no backslash`, !line.includes(String.fromCharCode(92)), 'backslash in loader');
    const first = await run(line);
    check(`${name}: LOADED`, /^LOADED __[a-z]+ \S+$/.test(first), first);
    const second = await run(line);
    check(`${name}: ALREADY on re-run`, second.startsWith('ALREADY '), second);
  }

  // A different file on GitHub than in the session: refuse, don't run it.
  const nt = helpers.find((h) => h.endsWith('norges_traktater.js'));
  delete globalThis.__nt;
  tamper = nt;
  const mm = await run(printLoader(nt, base));
  check('changed file: MISMATCH', mm.startsWith('MISMATCH '), mm);
  check('changed file: not run', globalThis.__nt === undefined, 'helper was installed');
  tamper = null;

  // Cowork syncs updates into <plugin>~gN folders; the URL must not pick that up.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'loader-'));
  const synced = path.join(tmp, 'norges-traktater~g2', 'skills', 'norges-traktater', 'scripts', 'browser');
  fs.mkdirSync(synced, { recursive: true });
  fs.copyFileSync(nt, path.join(synced, 'norges_traktater.js'));
  const g2 = await run(printLoader(path.join(synced, 'norges_traktater.js'), base));
  check('~gN folder: LOADED', g2.startsWith('LOADED __nt '), g2);
  fs.rmSync(tmp, { recursive: true, force: true });

  // Nothing at the URL: the caller falls back to pasting the file.
  delete globalThis.__nt;
  const nf = await run(printLoader(nt, base + '/missing'));
  check('404: FETCH_FAILED', nf === 'FETCH_FAILED HTTP 404', nf);

  server.close();
  console.log(failures ? `${failures} failure(s)` : 'all ok');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
