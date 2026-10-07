// Norges traktater in-page helper — paste into javascript_tool once per tab
// that is open on https://lovdata.no/ (e.g. https://lovdata.no/register/traktater).
//
// Why it exists: lovdata.no answers Anthropic's cloud with HTTP 405, and Cowork
// runs in the cloud. The browser pane runs on the user's own PC and can load
// the public treaty pages, so this helper does all fetching and parsing there,
// with same-origin fetch(). It is the skill's only route (the Python script it
// was ported from was dropped in 1.3.0); it works on the raw HTML string with
// regular expressions rather than on a DOM tree. The repo's
// tests/norges-traktater/test_browser.js checks it on saved pages.
//
// Idempotent: re-pasting is a no-op if the same version of window.__nt is
// already there. Everything is on window.__nt; functions are async and never
// throw to the caller: they return {error, detail} objects. The cache
// (a Map of URL -> HTML) dies on navigation, so re-paste after navigating.
//
// Also exported for Node (CommonJS) so it can be unit-tested — see
// the repo's tests/norges-traktater/test_browser.js.

// HELPER_VERSION follows the plugin version and changes whenever this file
// does (set it by hand; CI checks it). A helper of another version already in
// the tab — pasted before a skill update — is replaced, dropping its cache;
// the same version is left alone.
(function (root) {
  const HELPER_VERSION = '1.3.0';
  if (root.window && root.window.__nt && root.window.__nt.VERSION === HELPER_VERSION) return;

  const api = (() => {
    // javascript_tool errors hard above ~49-50K characters of result
    // (measured for lovdata-pro, same tool channel). 45000 leaves headroom.
    const PAGE_SIZE = 45000;
    const ORIGIN = 'https://lovdata.no';
    const REGISTER_PATH = '/register/traktater';
    const DOC_PATH = '/dokument/TRAKTAT/traktat';
    const REGISTER = ORIGIN + REGISTER_PATH;
    const DOC_BASE = ORIGIN + DOC_PATH;
    const MIN_BODY_TEXT = 50;
    const RESULTS_PER_PAGE = 20; // Lovdata's register listing
    const FULL_CONCURRENCY = 4;

    // Injected so tests can swap in canned responses.
    const deps = {
      fetch: (...a) => root.fetch(...a),
      location: () => root.location,
      decodeNamed: null, // optional (name) -> string, for entities not in NAMED
    };

    const cache = new Map(); // url -> html ('' for 404)

    class Failure extends Error {
      constructor(error, detail) { super(detail || error); this.error = error; this.detail = detail || ''; }
    }
    // Python's ValueError / FileNotFoundError / SystemExit messages become
    // {error: 'invalid', detail: <same Norwegian message>}.
    const invalid = (msg) => new Failure('invalid', msg);

    const jsonLen = (v) => JSON.stringify(v).length;

    // --- HTTP ---------------------------------------------------------------

    function checkOrigin() {
      const loc = deps.location();
      if (loc && loc.origin && loc.origin !== ORIGIN) {
        throw new Failure('wrong_origin',
          `Fanen står på ${loc.origin}; naviger den til ${REGISTER} og lim inn hjelperen på nytt.`);
      }
    }

    async function fetchHtml(url, noCache) {
      if (!noCache && cache.has(url)) return cache.get(url);
      checkOrigin();
      let r;
      try {
        r = await deps.fetch(url.replace(ORIGIN, ''), {
          credentials: 'same-origin',
          headers: { Accept: 'text/html,application/xhtml+xml' },
        });
      } catch (e) {
        throw new Failure('network', String(e && e.message || e));
      }
      if (r.status === 404) { cache.set(url, ''); return ''; }
      if (!r.ok) {
        throw new Failure('http_' + r.status,
          `lovdata.no svarte HTTP ${r.status} på ${url}`);
      }
      const html = await r.text();
      cache.set(url, html);
      return html;
    }

    // --- Python string helpers ---------------------------------------------

    const NAMED = {
      amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\xa0',
      times: '×', larr: '←', rarr: '→', ndash: '–', mdash: '—',
      laquo: '«', raquo: '»', hellip: '…', copy: '©', reg: '®',
      deg: '°', sect: '§', middot: '·', bull: '•',
      lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”',
      aelig: 'æ', AElig: 'Æ', oslash: 'ø', Oslash: 'Ø',
      aring: 'å', Aring: 'Å', eacute: 'é', Eacute: 'É',
      egrave: 'è', agrave: 'à', ouml: 'ö', Ouml: 'Ö',
      auml: 'ä', Auml: 'Ä', uuml: 'ü', Uuml: 'Ü', szlig: 'ß',
      ccedil: 'ç', shy: '­', para: '¶', plusmn: '±',
    };

    // Python's html.unescape for the cases Lovdata produces: numeric
    // references and the usual named ones. A named entity not in NAMED is
    // handed to deps.decodeNamed, or, in a real page, to the browser's own
    // decoder; otherwise it is left as it stands.
    function unescape(s) {
      return s.replace(/&(#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);/g, (whole, body) => {
        if (body[0] === '#') {
          const n = (body[1] === 'x' || body[1] === 'X') ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
          if (n === 0 || n > 0x10ffff || (n >= 0xd800 && n <= 0xdfff)) return '�';
          return String.fromCodePoint(n);
        }
        if (Object.prototype.hasOwnProperty.call(NAMED, body)) return NAMED[body];
        if (deps.decodeNamed) return deps.decodeNamed(whole);
        if (typeof root.document !== 'undefined' && root.document.createElement) {
          const t = root.document.createElement('textarea');
          t.innerHTML = whole;
          return t.value;
        }
        return whole;
      });
    }

    // str.splitlines()
    // Built from char codes, not escapes: the javascript_tool channel decodes
    // backslash-u escapes before running the code, and a decoded U+2028/U+2029
    // inside a regex literal is a line break, i.e. a SyntaxError (cloud
    // Cowork, 2026-09-30). CI rejects backslash-u escapes in browser helpers.
    const SPLITLINES_RE = new RegExp(
      String.fromCharCode(13, 10) + '|[' +
      String.fromCharCode(10, 13, 11, 12, 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029) + ']');
    const splitlines = (s) => {
      const parts = s.split(SPLITLINES_RE);
      if (parts.length && parts[parts.length - 1] === '') parts.pop();
      return parts;
    };
    const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // --- ID normalisation ---------------------------------------------------

    function normalizeId(raw) {
      const s = String(raw).trim();
      const m = /(\d{4}-\d{2}-\d{2}-\d+)/.exec(s);
      if (!m) {
        throw invalid(
          `Kjente ikke igjen traktat-ID: '${raw}'. Formatet er YYYY-MM-DD-N ` +
          '(f.eks. 1948-12-09-1), eventuelt hele DokID-en eller URL-en.');
      }
      return m[1];
    }

    // --- difflib.get_close_matches -----------------------------------------

    function ratio(a, b) {
      const b2j = new Map();
      for (let j = 0; j < b.length; j++) {
        if (!b2j.has(b[j])) b2j.set(b[j], []);
        b2j.get(b[j]).push(j);
      }
      const longest = (alo, ahi, blo, bhi) => {
        let besti = alo, bestj = blo, bestsize = 0;
        let j2len = new Map();
        for (let i = alo; i < ahi; i++) {
          const newj2len = new Map();
          for (const j of (b2j.get(a[i]) || [])) {
            if (j < blo) continue;
            if (j >= bhi) break;
            const k = (j2len.get(j - 1) || 0) + 1;
            newj2len.set(j, k);
            if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
          }
          j2len = newj2len;
        }
        return [besti, bestj, bestsize];
      };
      let matches = 0;
      const queue = [[0, a.length, 0, b.length]];
      while (queue.length) {
        const [alo, ahi, blo, bhi] = queue.pop();
        const [i, j, k] = longest(alo, ahi, blo, bhi);
        if (k) {
          matches += k;
          if (alo < i && blo < j) queue.push([alo, i, blo, j]);
          if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
        }
      }
      const total = a.length + b.length;
      return total ? 2.0 * matches / total : 1.0;
    }

    function closeMatches(word, possibilities, n = 5, cutoff = 0.6) {
      const scored = [];
      for (const x of possibilities) {
        const r = ratio([...x], [...word]);
        if (r >= cutoff) scored.push([r, x]);
      }
      scored.sort((p, q) => (q[0] - p[0]) || (p[1] < q[1] ? 1 : p[1] > q[1] ? -1 : 0));
      return scored.slice(0, n).map((p) => p[1]);
    }

    // --- Register form values (year / country dropdowns) --------------------

    async function selectOptions(name, noCache) {
      const html = await fetchHtml(REGISTER, noCache);
      const m = new RegExp(`<select[^>]*name="${name}"[^>]*>(.*?)</select>`, 's').exec(html);
      if (!m) return [];
      const out = [];
      for (const om of m[1].matchAll(/<option[^>]*>(.*?)<\/option>/gs)) {
        const val = unescape(om[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ')).trim();
        if (val && !val.toLowerCase().startsWith('alle')) out.push(val);
      }
      return out;
    }

    async function resolveOption(kind, value, noCache) {
      const options = await selectOptions(kind, noCache);
      if (!options.length) return value; // markup changed; let the server decide
      const want = value.trim().toLowerCase();
      for (const o of options) if (o.toLowerCase() === want) return o;
      const close = closeMatches(value, options, 5, 0.6);
      const hint = close.length ? 'Mente du: ' + close.join(', ') + '?'
        : (kind === 'country' ? 'Se hele listen med: await __nt.countries()'
          : `Gyldige år: ${options[options.length - 1]}-${options[0]}.`);
      throw invalid(`Ukjent ${kind}: '${value}'. Lovdata ville ha ignorert filteret og ` +
        `returnert hele registeret. ${hint}`);
    }

    // --- Registry search ----------------------------------------------------

    function hitCount(html) {
      const text = html.replace(/<[^>]+>/g, ' ');
      const m = /([\d \s]{1,12})\s*treff/.exec(text);
      if (!m) return null;
      const digits = m[1].replace(/\D/g, '');
      return digits ? parseInt(digits, 10) : null;
    }

    function cleanTitle(inner) {
      return unescape(inner.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')).trim();
    }

    async function searchRaw(query, o) {
      const scMap = { tittel: 'I tittel', tekst: 'I teksten' };
      const scValue = scMap[String(o.context || 'tittel').toLowerCase()] || 'I tittel';
      let country = o.country, year = o.year;
      if (country) country = await resolveOption('country', String(country), o.noCache);
      if (year) year = await resolveOption('year', String(year), o.noCache);
      const maxResults = o.max == null ? 20 : o.max;

      const results = [];
      const seen = new Set();
      let offset = 0, total = null;
      while (results.length < maxResults) {
        const params = new URLSearchParams();
        if (query) { params.set('search', query); params.set('searchContext', scValue); }
        if (year) params.set('year', year);
        if (country) params.set('country', country);
        if (offset) params.set('offset', String(offset));
        const qs = params.toString();
        const html = await fetchHtml(qs ? `${REGISTER}?${qs}` : REGISTER, o.noCache);
        if (!html) break;
        if (total === null) total = hitCount(html);

        let rows = [...html.matchAll(
          /<a\s+href="\/dokument\/TRAKTAT\/traktat\/(\d{4}-\d{2}-\d{2}-\d+)(?:\?[^"]*)?"[^>]*>\s*<strong>\s*(.*?)\s*<\/strong>/gs)]
          .map((m) => [m[1], m[2]]);
        if (!rows.length) {
          rows = [...html.matchAll(
            /<a\s+href="\/dokument\/TRAKTAT\/traktat\/(\d{4}-\d{2}-\d{2}-\d+)(?:\?[^"]*)?"[^>]*>(.*?)<\/a>/gs)]
            .map((m) => [m[1], m[2]]);
        }

        let newCount = 0;
        for (const [tid, inner] of rows) {
          if (seen.has(tid)) continue;
          seen.add(tid);
          results.push({ id: tid, title: cleanTitle(inner), year: tid.slice(0, 4) });
          newCount += 1;
          if (results.length >= maxResults) break;
        }
        if (newCount === 0) break;
        if (total !== null && seen.size >= total) break;
        if (!/href="\?[^"]*offset=\d+/.test(html)) break;
        offset += RESULTS_PER_PAGE;
      }
      return { total, shown: results.length, results };
    }

    // --- Document fetch / metadata ------------------------------------------

    const fetchDocHtml = (tid, noCache) => fetchHtml(`${DOC_BASE}/${tid}`, noCache);

    function tdToText(raw) {
      raw = raw.replace(/<br\s*\/?>/gi, '\n');
      raw = raw.replace(/<\/p\s*>/gi, '\n');
      raw = raw.replace(/<[^>]+>/g, ' ');
      let text = unescape(raw);
      text = splitlines(text).map((line) => line.replace(/[ \t]+/g, ' ').trim()).join('\n');
      return text.replace(/\n{2,}/g, '\n').trim();
    }

    function formatParties(value) {
      const out = [];
      for (const ln of splitlines(value)) {
        if (ln.startsWith('Part:') && out.length) out.push('');
        out.push(ln);
      }
      return out.join('\n');
    }

    function parseMetadata(html) {
      const out = {};
      let titleMatch = null;
      const metatitle = /<td class="metaTitleText">(.*?)<\/td>/s.exec(html);
      if (metatitle) {
        const h1 = /<h1[^>]*>(.*?)<\/h1>/s.exec(metatitle[1]);
        if (h1) titleMatch = h1[1];
      }
      if (!titleMatch) {
        const h1 = /<h1 class="veryLongTitle">(.*?)<\/h1>/s.exec(html);
        if (h1) titleMatch = h1[1];
      }
      if (titleMatch) {
        out.title = unescape(titleMatch.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ')).trim();
      }

      const ordered = {};
      const fields = {};
      const table = /<table class="[^"]*\bmeta\b[^"]*"[^>]*>(.*?)<\/table>/s.exec(html);
      if (table) {
        for (const rm of table[1].matchAll(/<tr[^>]*>(.*?)<\/tr>/gs)) {
          const row = rm[1];
          const th = /<th[^>]*>(.*?)<\/th>/s.exec(row);
          const td = /<td[^>]*>(.*?)<\/td>/s.exec(row);
          if (!th || !td) continue;
          const label = unescape(th[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ')).trim();
          let value = tdToText(td[1]);
          if (!label || !value) continue;
          const fid = /id="metaField_([^"]+)"/.exec(row);
          if (fid) {
            fields[fid[1]] = value;
            if (fid[1] === 'parter') value = formatParties(value);
          }
          // dict.setdefault: the first row with a label wins.
          if (!Object.prototype.hasOwnProperty.call(ordered, label)) ordered[label] = value;
        }
      }
      if (!Object.keys(ordered).length) {
        // Fallback for a markup change: read the metaField cells directly.
        for (const m of html.matchAll(/id="metaField_([^"]+)"[^>]*>(.*?)<\/td>/gs)) {
          fields[m[1]] = tdToText(m[2]);
          ordered[m[1]] = fields[m[1]];
        }
      }
      out.metadata = ordered;
      out.fields = fields;
      return out;
    }

    // --- Body / articles ----------------------------------------------------

    const cellText = (raw) => unescape(
      raw.replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')).trim();

    function listeitemSub(_m, cls, inner) {
      const lm = /leftMargin_(\d+)/.exec(cls);
      const indent = '  '.repeat(Math.max(0, (lm ? parseInt(lm[1], 10) : 1) - 1));
      const parts = [...inner.matchAll(/<t[dh][^>]*>(.*?)<\/t[dh]>/gis)]
        .map((c) => cellText(c[1])).filter((p) => p);
      return parts.length ? '\n' + indent + parts.join(' ') : '\n';
    }

    function tableSub(_m, inner) {
      const rows = [];
      for (const rm of inner.matchAll(/<tr[^>]*>(.*?)<\/tr>/gis)) {
        let cells = [...rm[1].matchAll(/<t[dh][^>]*>(.*?)<\/t[dh]>/gis)].map((c) => cellText(c[1]));
        if (!cells.some((c) => c)) cells = [];
        if (!cells.length) continue;
        rows.push(cells.length === 1 ? cells[0] : '| ' + cells.join(' | ') + ' |');
      }
      return rows.length ? '\n' + rows.join('\n') + '\n' : '\n';
    }

    function stripHtml(s) {
      s = s.replace(/<a class="share-paragraf".*?<\/a>/gs, '');
      s = s.replace(/<i [^>]+ss-icon[^>]*>.*?<\/i>/gs, '');
      s = s.replace(/<span class="share-paragraf-title">.*?<\/span>/gs, '');
      s = s.replace(/<script.*?<\/script>/gs, '');
      s = s.replace(/<table[^>]*class="([^"]*\blisteItem\b[^"]*)"[^>]*>(.*?)<\/table>/gis, listeitemSub);
      s = s.replace(/<table[^>]*>(.*?)<\/table>/gis, tableSub);
      s = s.replace(/<h(\d)[^>]*>/g, '\n\n');
      s = s.replace(/<\/h\d>/g, '\n');
      s = s.replace(/<p[^>]*>/g, '\n');
      s = s.replace(/<\/p>/g, '');
      s = s.replace(/<br\s*\/?>/gi, '\n');
      s = s.replace(/<li[^>]*>/g, '\n - ');
      s = s.replace(/<[^>]+>/g, '');
      s = unescape(s);
      s = s.replace(/\xa0/g, ' ');
      s = s.replace(/[ \t]+/g, ' ');
      s = s.replace(/\n[ \t]+/g, '\n');
      s = s.replace(/\n{3,}/g, '\n\n');
      return s.trim();
    }

    function getBodyHtml(html) {
      let m = /<div id="documentBody">(.*?)<ul class="pager"/s.exec(html);
      if (m) return m[1];
      m = /<div id="documentBody">(.*)/s.exec(html);
      return m ? m[1] : '';
    }

    const bodyHasText = (bodyHtml) => stripHtml(bodyHtml).length >= MIN_BODY_TEXT;

    function roman(n) {
      const pairs = [[50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];
      let out = '';
      for (const [v, s] of pairs) while (n >= v) { out += s; n -= v; }
      return out;
    }
    const ROMAN_VALUES = { i: 1, v: 5, x: 10, l: 50 };
    function romanToInt(s) {
      let total = 0, prev = 0;
      for (const ch of [...s.toLowerCase()].reverse()) {
        const val = ROMAN_VALUES[ch];
        total += val < prev ? -val : val;
        prev = val;
      }
      return total;
    }

    function splitSubArticle(s) {
      const m = /^(\d+|[ivxl]+)\s*(?:\(?([a-z])\)?|(bis|ter|quater))$/i.exec(s);
      if (!m || /^[ivxl]+$/i.test(s)) return [s, null];
      return [m[1], (m[2] || m[3]).toLowerCase()];
    }

    const ART_PREFIX = /^art(?:ikkel|icle|ikel|\.)?\.?\s*/i;

    function normalizeArticleKey(raw) {
      let s = raw.trim();
      s = s.replace(ART_PREFIX, '');
      s = s.trim().replace(/\.+$/, '');
      const candidates = [];
      if (!s) return candidates;
      const [base, suffix] = splitSubArticle(s);
      if (suffix) {
        candidates.push((base + suffix).toLowerCase());
        for (const key of normalizeArticleKey(base)) if (!candidates.includes(key)) candidates.push(key);
        return candidates;
      }
      if (/^\d+$/.test(s)) {
        const n = parseInt(s, 10);
        candidates.push(s);
        if (n >= 1 && n <= 50) candidates.push(roman(n).toLowerCase());
      } else {
        candidates.push(s.toLowerCase());
        if (/^[ivxl]+$/.test(s.toLowerCase())) candidates.push(String(romanToInt(s)));
      }
      return candidates;
    }

    // --- Operations ---

    async function getMeta(rawId, noCache) {
      const tid = normalizeId(rawId);
      const html = await fetchDocHtml(tid, noCache);
      if (!html) throw invalid(`Traktat ${tid} ikke funnet på ${DOC_BASE}/${tid}`);
      const meta = parseMetadata(html);
      meta.id = tid;
      meta.url = `${DOC_BASE}/${tid}`;
      meta.has_text = bodyHasText(getBodyHtml(html));
      return meta;
    }

    async function fullTitle(tid, noCache) {
      const html = await fetchDocHtml(normalizeId(tid), noCache);
      if (!html) return null;
      return parseMetadata(html).title || null;
    }

    async function mapLimit(items, limit, fn) {
      const out = new Array(items.length);
      let next = 0;
      const worker = async () => {
        while (next < items.length) { const i = next++; out[i] = await fn(items[i], i); }
      };
      await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
      return out;
    }

    // Longest slice of text from `offset` (at most `size` chars) whose JSON
    // encoding fits in `budget`.
    function fitSlice(text, offset, size, budget) {
      let end = Math.min(text.length, offset + size);
      let slice = text.slice(offset, end);
      let over;
      while ((over = jsonLen(slice) - budget) > 0) {
        end -= over;
        slice = text.slice(offset, end);
      }
      return slice;
    }

    function chunked(res, opts) {
      const body = res.body;
      const offset = Math.max(0, (opts && opts.offset) | 0);
      let size = (opts && opts.length) | 0;
      if (size <= 0) size = 40000;
      size = Math.min(size, PAGE_SIZE);
      const overhead = jsonLen(Object.assign({}, res, { body: '' })) + 120;
      const slice = fitSlice(body, offset, size, PAGE_SIZE - overhead);
      const end = offset + slice.length;
      return Object.assign({}, res, {
        body: slice, total: body.length, offset, next: end < body.length ? end : null,
      });
    }

    function tooLarge(result, what) {
      return { error: 'result_too_large', detail:
        `${what} ga ${jsonLen(result)} tegn (grensen er ${PAGE_SIZE}). Bruk færre treff/ID-er per kall; ` +
        'sidene ligger allerede i hjelperens cache, så nytt kall er raskt.' };
    }

    function fail(e) {
      if (e instanceof Failure) return { error: e.error, detail: e.detail };
      return { error: 'exception', detail: String(e && e.stack || e) };
    }

    // search(query, {year, country, context: 'tittel'|'tekst', max, full, noCache})
    // -> {total, shown, results: [{id, title, year}], full_titles?: true}
    async function search(query = '', opts = {}) {
      try {
        const o = Object.assign({}, opts);
        const payload = await searchRaw(String(query || ''), o);
        if (o.full && payload.results.length) {
          const titles = await mapLimit(payload.results, FULL_CONCURRENCY, async (r) => {
            try { return await fullTitle(r.id, o.noCache); } catch (e) { return null; }
          });
          let failed = 0;
          payload.results.forEach((r, i) => { if (titles[i]) r.title = titles[i]; else failed += 1; });
          payload.full_titles = true;
          if (failed) payload.full_title_failures = failed;
        }
        return jsonLen(payload) > PAGE_SIZE ? tooLarge(payload, 'Søket') : payload;
      } catch (e) { return fail(e); }
    }

    // meta('1948-12-09-1') -> {title, metadata, fields, id, url, has_text}
    // meta([ids...]) or meta('id1\nid2') -> array of the same; a failed id
    // becomes {id, url, error}.
    async function meta(idOrIds, opts = {}) {
      try {
        const o = opts || {};
        const batch = Array.isArray(idOrIds) || /[\r\n]/.test(String(idOrIds).trim());
        if (!batch) {
          const m = await getMeta(idOrIds, o.noCache);
          return jsonLen(m) > PAGE_SIZE ? tooLarge(m, 'Metadataene') : m;
        }
        const raw = Array.isArray(idOrIds) ? idOrIds : String(idOrIds).split(/\r?\n/);
        const ids = [];
        for (const line of raw) {
          const l = String(line).split('#', 1)[0].trim();
          if (!l) continue;
          let tid;
          try { tid = normalizeId(l); } catch (e) { continue; } // read_id_list skips unreadable lines
          if (!ids.includes(tid)) ids.push(tid);
        }
        if (!ids.length) return { error: 'invalid', detail: 'Fant ingen traktat-ID-er i listen.' };
        const metas = await mapLimit(ids, FULL_CONCURRENCY, async (tid) => {
          try { return await getMeta(tid, o.noCache); } catch (e) {
            return { id: tid, url: `${DOC_BASE}/${tid}`, error: e.detail || e.message };
          }
        });
        return jsonLen(metas) > PAGE_SIZE ? tooLarge(metas, 'Metadataene') : metas;
      } catch (e) { return fail(e); }
    }

    // text(id, {offset, length}) -> {id, url, body, available, total, offset, next}
    // body is a slice; concatenate the slices from offset 0 while next != null.
    // available:false (no free text) has body '' and no chunk keys.
    async function text(id, opts = {}) {
      try {
        const o = opts || {};
        const tid = normalizeId(id);
        const html = await fetchDocHtml(tid, o.noCache);
        if (!html) throw invalid(`Traktat ${tid} ikke funnet`);
        const bodyHtml = getBodyHtml(html);
        const url = `${DOC_BASE}/${tid}`;
        if (!bodyHasText(bodyHtml)) return { id: tid, url, body: '', available: false };
        return chunked({ id: tid, url, body: stripHtml(bodyHtml), available: true }, o);
      } catch (e) { return fail(e); }
    }

    // article(id, art, {offset, length}) -> {id, article, body, available, url,
    // note?, available_articles?, error?} (+ total/offset/next when available)
    async function article(id, art, opts = {}) {
      try {
        const o = opts || {};
        art = String(art);
        const tid = normalizeId(id);
        const html = await fetchDocHtml(tid, o.noCache);
        if (!html) throw invalid(`Traktat ${tid} ikke funnet`);
        const bodyHtml = getBodyHtml(html);
        const url = `${DOC_BASE}/${tid}`;
        if (!bodyHasText(bodyHtml)) {
          return { id: tid, article: art, body: '', available: false, url };
        }
        const keys = normalizeArticleKey(art);
        if (!keys.length) throw invalid(`Kunne ikke tolke artikkelnummer: '${art}'`);
        const bare = art.trim().replace(ART_PREFIX, '').trim().replace(/\.+$/, '');
        const suffix = splitSubArticle(bare)[1];
        for (const key of keys) {
          const sm = new RegExp(`<div[^>]+data-id="ARTIKKEL_${escapeRe(key)}"[^>]*>`, 'i').exec(bodyHtml);
          if (!sm) continue;
          const rest = bodyHtml.slice(sm.index);
          const nxt = /<a[^>]+name="(?:ARTIKKEL_[^"]+|KAPITTEL_[^"]+)"/.exec(rest.slice(1));
          const chunk = nxt ? rest.slice(0, 1 + nxt.index) : rest;
          const out = { id: tid, article: art, body: stripHtml(chunk), available: true, url };
          if (suffix && key !== keys[0]) {
            out.note = `Lovdata har ikke '${art}' som egen artikkel; dette er hele ` +
              `artikkel ${key}. Finn ledd/bokstav ${suffix.toUpperCase()} i teksten.`;
          }
          return chunked(out, o);
        }
        let found = [...new Set([...bodyHtml.matchAll(/data-id="ARTIKKEL_([a-zA-Z0-9_-]+)"/g)].map((m) => m[1]))];
        if (!found.length) found = [...new Set([...bodyHtml.matchAll(/ARTIKKEL_([a-zA-Z0-9_-]+)/g)].map((m) => m[1]))];
        return {
          id: tid, article: art, body: '', available: false, url, available_articles: found,
          error: `Artikkel '${art}' ble ikke funnet. Tilgjengelige artikler ` +
            '(i dokumentets rekkefølge; _1, _2 … er samme nummer i neste ' +
            'del, f.eks. en protokoll): ' +
            `${found.length ? found.join(', ') : '(ingen)'}.`,
        };
      } catch (e) { return fail(e); }
    }

    // countries(query?) -> {count, countries: [...]}  (valid values for {country})
    async function countries(query, opts = {}) {
      try {
        let opts_ = await selectOptions('country', (opts || {}).noCache);
        if (query) { const q = String(query).toLowerCase(); opts_ = opts_.filter((o) => o.toLowerCase().includes(q)); }
        return { count: opts_.length, countries: opts_ };
      } catch (e) { return fail(e); }
    }

    // status() -> {reachable, origin, total, years: {first, last, count},
    // countries, cached_pages, warning?}
    async function status(opts = {}) {
      try {
        const noCache = (opts || {}).noCache;
        const html = await fetchHtml(REGISTER, noCache);
        const total = hitCount(html);
        const yrs = await selectOptions('year', noCache);
        const cs = await selectOptions('country', noCache);
        const out = {
          reachable: html.includes('Norges traktater') || html.includes('register/traktater'),
          origin: (deps.location() || {}).origin || null,
          total,
          years: yrs.length ? { first: yrs[yrs.length - 1], last: yrs[0], count: yrs.length } : null,
          countries: cs.length,
          cached_pages: cache.size,
          helper_version: HELPER_VERSION,
        };
        if (total === null || !yrs.length || !cs.length) {
          out.warning = 'Klarte ikke å lese alle feltene — Lovdata kan ha endret markupen.';
        }
        return out;
      } catch (e) { return fail(e); }
    }

    return {
      VERSION: HELPER_VERSION,
      PAGE_SIZE,
      cache,
      search,
      meta,
      text,
      article,
      countries,
      status,
      // exposed for unit tests / debugging only:
      _deps: deps,
      _internal: { normalizeId, parseMetadata, stripHtml, getBodyHtml, hitCount, closeMatches, normalizeArticleKey, unescape },
    };
  })();

  if (root.window) root.window.__nt = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
