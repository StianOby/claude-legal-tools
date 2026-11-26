#!/usr/bin/env node
// scripts/browser/paste_site.py: the per-site copies of lovdata_pro.js. Each
// must parse, keep HELPER_VERSION, name its site, carry no backslash-u, leave
// out the other site's code, refuse the other site's tab, and pass the
// suites for its site (pro2.js and dom.js need linkedom and skip without
// it; CI also runs this file in the linkedom step).
// Run with `node tests/lovdata-pro/test_sites.js` (needs python3).

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync, spawnSync } = require('child_process');

const BROWSER = path.join(__dirname, '..', '..', 'plugins', 'lovdata-pro', 'skills', 'lovdata-pro', 'scripts', 'browser');
const SRC = fs.readFileSync(path.join(BROWSER, 'lovdata_pro.js'), 'utf8');
const PY = process.platform === 'win32' ? 'python' : 'python3';
const BS = String.fromCharCode(92);

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ': ' + detail}`);
  if (!ok) failures++;
};

const copy = (site) => {
  const line = execFileSync(PY, [path.join(BROWSER, 'paste_site.py'), site], { encoding: 'utf8' });
  return fs.readFileSync(line.slice(0, line.indexOf('  (')), 'utf8');
};

const run = (text, host) => {
  const ctx = { location: { hostname: host, origin: `https://${host}`, hash: '', pathname: '/' }, document: { title: '', querySelector: () => null }, fetch: async () => { throw new Error('no network'); }, setTimeout, console };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(text, ctx);
  return ctx.__lp;
};

const OWN = { pro2: ['pro2Load', 'pro2Search', 'paragraphHistory'], klassisk: ['tryPaths', 'collectResults', 'quickSearchField'] };

async function main() {
  const ver = SRC.match(/const HELPER_VERSION = '[^']+'/)[0];
  const full = execFileSync(PY, [path.join(BROWSER, 'paste.py'), path.join(BROWSER, 'lovdata_pro.js')], { encoding: 'utf8' });
  const fullLen = fs.readFileSync(full.slice(0, full.indexOf('  (')), 'utf8').length;
  for (const site of ['pro2', 'klassisk']) {
    const other = site === 'pro2' ? 'klassisk' : 'pro2';
    const text = copy(site);
    let err = null;
    try { new Function(text); } catch (e) { err = e.message; }
    check(`${site}: parses`, err === null, err);
    check(`${site}: keeps HELPER_VERSION`, text.includes(ver), 'missing');
    check(`${site}: HELPER_SITE set`, text.includes(`const HELPER_SITE = '${site}';`), 'missing');
    check(`${site}: no backslash-u`, !text.includes(BS + 'u'), 'found one');
    check(`${site}: smaller than the full copy`, text.length < fullLen * 0.9, `${text.length} of ${fullLen}`);
    check(`${site}: none of ${other}'s code`, OWN[other].every((w) => !text.includes(w)), OWN[other].filter((w) => text.includes(w)).join(', '));
    check(`${site}: all of its own code`, OWN[site].every((w) => text.includes(w)), OWN[site].filter((w) => !text.includes(w)).join(', '));
    const lp = run(text, site === 'pro2' ? 'lovdata.no' : 'pro2.lovdata.no');
    check(`${site}: SITE`, lp.SITE === site, lp.SITE);
    const r = await lp.isLoggedIn();
    check(`${site}: refuses a ${other} tab`, r.error === 'wrong_site' && r.pasted === site && r.site === other, JSON.stringify(r));
    check(`${site}: load refuses it too`, (await lp.load('HRSIV/avgjorelse/hr-2020-1')).error === 'wrong_site', 'no');
  }
  const k = run(copy('klassisk'), 'lovdata.no');
  check('klassisk: versions() is pro2_only', (await k.versions('lov/2005-06-17-62')).error === 'pro2_only', 'no');
  check('klassisk: backlinks() is pro2_only', (await k.backlinks('lov/2005-06-17-62', 'lovspeil')).error === 'pro2_only', 'no');

  const suites = { klassisk: ['test_browser.js', 'dom.js'], pro2: ['pro2.js', 'dom.js'] };
  for (const [site, files] of Object.entries(suites)) {
    for (const f of files) {
      const r = spawnSync(process.execPath, ['-r', path.join(__dirname, 'site_preload.js'), path.join(__dirname, f)],
        { encoding: 'utf8', env: { ...process.env, LP_SITE: site } });
      const skipped = /^skip/m.test(r.stdout);
      const ran = skipped || r.stdout.includes(`ran against the ${site} copy`);
      check(`${site}: ${f} passes on its copy${skipped ? ' (skipped: no linkedom)' : ''}`, r.status === 0 && ran,
        (r.stdout + r.stderr).split('\n').filter((l) => /FAIL|Error|NO helper/.test(l)).slice(0, 5).join(' | ') || `exit ${r.status}`);
    }
  }
  console.log(failures ? `${failures} failure(s)` : 'all ok');
  process.exit(failures ? 1 : 0);
}

main();
