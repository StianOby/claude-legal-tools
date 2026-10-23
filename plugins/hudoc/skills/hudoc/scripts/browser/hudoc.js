// HUDOC in-page helper — the fallback for when Cloudflare challenges
// scripts/hudoc.py. Paste the whole file into a Claude Desktop built-in
// browser tab on https://hudoc.echr.coe.int/ via javascript_tool.
//
// Idempotent: re-pasting is a no-op if the same version of window.__hd
// already exists (see HELPER_VERSION below). All functions are async, return
// plain JSON-serialisable objects no larger than PAGE_SIZE characters, and
// never throw to the caller — errors come back as
// {error: 'wrong_origin' | 'challenge' | 'http_<n>' | 'fetch_failed' |
//         'not_json' | 'no_match' | 'no_html' | 'bad_html' | 'not_loaded' |
//         'not_found', detail}.
//
// Why a browser helper: HUDOC sits behind Cloudflare, which answers a script
// with a "Just a moment…" page (HTTP 403) often enough to make the Python CLI
// unreliable — and which request it challenges changes from minute to minute
// (see scripts/hudoc.py, USER_AGENT). A tab that has loaded HUDOC passes. The
// helper does nothing to get around a challenge: it makes the same same-origin
// requests the HUDOC page itself makes, and reports {error: 'challenge'} if
// one comes back anyway.
//
// It mirrors scripts/hudoc.py: the same query endpoint and field list, the
// same resolve() scoring, and the same HTML-to-text conversion of the page
// HUDOC's reading view shows (paragraphs separated by a blank line, footnotes
// as [fn N] plus a FOOTNOTES block), so text read here and text read from
// the CLI cache match line for line.
//
// Also exported for Node (CommonJS) so the pure parts can be unit-tested —
// see the repo's tests/hudoc/test_browser.js.

// HELPER_VERSION follows the plugin version and changes whenever this file
// does (set it by hand; CI checks it). A helper of another version already in
// the tab — pasted before a skill update — is replaced, dropping its cache;
// the same version is left alone.
(function (root) {
  const HELPER_VERSION = '1.4.0';
  if (root.window && root.window.__hd && root.window.__hd.VERSION === HELPER_VERSION) return;

  const api = (() => {
    // javascript_tool errors hard above ~49-50K characters of result
    // (measured for lovdata-pro, same tool channel). 45000 leaves headroom.
    const PAGE_SIZE = 45000;
    const ORIGIN = 'https://hudoc.echr.coe.int';
    const QUERY_PATH = '/app/query/results';
    const HTML_PATH = '/app/conversion/docx/html/body';
    const WEB_URL = ORIGIN + '/eng?i=';
    // Direct link to the official PDF (see pdf_url in hudoc.py): the way to
    // hand the user a PDF copy, opened in their own browser.
    const pdfUrl = (id) => `${ORIGIN}/app/conversion/pdf/?library=ECHR&id=${encodeURIComponent(id)}&filename=${encodeURIComponent(id)}.pdf`;
    const SITE_FILTER = '(contentsitename=ECHR)';

    const DEFAULT_FIELDS = [
      'itemid', 'docname', 'appno', 'respondent', 'article', 'kpdate',
      'judgementdate', 'doctypebranch', 'doctype', 'documentcollectionid2',
      'importance', 'languageisocode', 'conclusion', 'ecli', 'scl',
      'extractedappno', 'kpthesaurus', 'originatingbody', 'issue',
      'separateopinion',
    ];
    // What search() returns unless asked for more: enough to pick a row.
    const SEARCH_FIELDS = [
      'itemid', 'docname', 'appno', 'respondent', 'kpdate', 'doctypebranch',
      'doctype', 'languageisocode', 'importance', 'conclusion',
    ];

    // Injected so tests can swap in canned responses.
    const deps = {
      fetch: (...a) => root.fetch(...a),
      location: () => root.location,
    };

    const cache = { items: {} }; // itemid -> {meta, text}

    // --- HTTP ---------------------------------------------------------------

    function isChallenge(status, text) {
      return status === 403 && /Just a moment/i.test(text || '');
    }

    function checkOrigin() {
      const loc = deps.location();
      if (!loc || loc.origin !== ORIGIN) {
        return { error: 'wrong_origin', detail: `this tab is on ${loc ? loc.origin : '?'}; open ${ORIGIN}/eng first` };
      }
      return null;
    }

    async function getJson(url) {
      let res, text;
      try {
        res = await deps.fetch(url, {
          credentials: 'include',
          headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
        });
        text = await res.text();
      } catch (e) {
        return { error: 'fetch_failed', detail: String((e && e.message) || e) };
      }
      if (isChallenge(res.status, text)) return { error: 'challenge', detail: 'Cloudflare "Just a moment…" page' };
      if (!res.ok) return { error: 'http_' + res.status, detail: url };
      try {
        return { json: JSON.parse(text) };
      } catch (e) {
        return { error: 'not_json', detail: text.slice(0, 200) };
      }
    }

    function queryUrl(lucene, { fields = DEFAULT_FIELDS, sort = '', start = 0, length = 20 } = {}) {
      const full = lucene ? `${SITE_FILTER} AND (${lucene})` : SITE_FILTER;
      const params = [
        ['query', full], ['select', fields.join(',')], ['sort', sort],
        ['start', String(start)], ['length', String(length)],
      ];
      return QUERY_PATH + '?' + params.map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
    }

    async function query(lucene, opts) {
      const r = await getJson(queryUrl(lucene, opts));
      if (r.error) return r;
      const rows = (r.json.results || []).map((x) => x.columns);
      return { resultcount: r.json.resultcount || 0, rows };
    }

    // --- output size --------------------------------------------------------

    // Drop rows from the end of `key` until the JSON fits one tool response.
    function fitRows(out, key) {
      while (out[key].length > 1 && JSON.stringify(out).length > PAGE_SIZE) {
        out[key] = out[key].slice(0, Math.max(1, Math.floor(out[key].length * 0.8)));
        out.truncated = true;
      }
      return out;
    }

    // Cut long string fields (scl, extractedappno …) of one row to fit.
    function fitRow(row) {
      const out = { ...row };
      const long = Object.keys(out).filter((k) => typeof out[k] === 'string').sort((a, b) => out[b].length - out[a].length);
      for (const k of long) {
        if (JSON.stringify(out).length <= PAGE_SIZE) break;
        const over = JSON.stringify(out).length - PAGE_SIZE + 200;
        out[k] = out[k].slice(0, Math.max(0, out[k].length - over)) + ' …[cut]';
        out.truncated = (out.truncated ? out.truncated + ',' : '') + k;
      }
      return out;
    }

    // --- resolve (ported from scripts/hudoc.py) -----------------------------

    const ITEMID_RE = /^\d{3}-\d+(?:-\d+)?$/;
    const ECLI_RE = /^ECLI:CE:ECHR:\d{4}:\d{4}[A-Z]{3}\d{9,12}$/i;
    // Application numbers, alone or listed after "no." / "nos." /
    // "Application no." / "n°" (see appnos_in in hudoc.py).
    const APPNO_PREFIX_RE = /^(?:(?:application|app\.|requête|req\.)\s*)?(?:nos?\.?|n[°º]s?\.?)?\s*/i;
    const APPNO_ANY_RE = /(?<![\d/])\d{1,6}\/\d{2}(?![\d/])/g;
    const APPNO_LIST_RE = /^\d{1,6}\/\d{2}(?:\s*(?:;|,|&|\band\b|\bet\b)\s*\d{1,6}\/\d{2})*$/i;

    function appnosIn(s) {
      const rest = String(s).trim().replace(APPNO_PREFIX_RE, '').replace(/[ .]+$/, '');
      return APPNO_LIST_RE.test(rest) ? rest.match(APPNO_ANY_RE) : [];
    }

    // Respondent states as HUDOC codes them (ISO-3); same table as
    // RESPONDENT_CODES in hudoc.py.
    const RESPONDENT_CODES = {
      ALB: ['albania', 'albanie'], AND: ['andorra', 'andorre'], ARM: ['armenia', 'arménie'],
      AUT: ['austria', 'autriche'], AZE: ['azerbaijan', 'azerbaïdjan'], BEL: ['belgium', 'belgique'],
      BIH: ['bosnia and herzegovina', 'bosnie-herzégovine'], BGR: ['bulgaria', 'bulgarie'],
      HRV: ['croatia', 'croatie'], CYP: ['cyprus', 'chypre'],
      CZE: ['czech republic', 'czechia', 'république tchèque', 'tchéquie'],
      DNK: ['denmark', 'danemark'], EST: ['estonia', 'estonie'], FIN: ['finland', 'finlande'],
      FRA: ['france'], GEO: ['georgia', 'géorgie'], DEU: ['germany', 'allemagne'],
      GRC: ['greece', 'grèce'], HUN: ['hungary', 'hongrie'], ISL: ['iceland', 'islande'],
      IRL: ['ireland', 'irlande'], ITA: ['italy', 'italie'], LVA: ['latvia', 'lettonie'],
      LIE: ['liechtenstein'], LTU: ['lithuania', 'lituanie'], LUX: ['luxembourg'],
      MLT: ['malta', 'malte'],
      MDA: ['moldova', 'republic of moldova', 'république de moldova', 'moldavie'],
      MCO: ['monaco'], MNE: ['montenegro', 'monténégro'], NLD: ['netherlands', 'pays-bas'],
      MKD: ['north macedonia', 'former yugoslav republic of macedonia', 'macedonia',
        'macédoine du nord', 'ex-république yougoslave de macédoine', 'fyrom'],
      NOR: ['norway', 'norvège'], POL: ['poland', 'pologne'], PRT: ['portugal'],
      ROU: ['romania', 'roumanie'],
      RUS: ['russia', 'russian federation', 'russie', 'fédération de russie'],
      SMR: ['san marino', 'saint-marin'], SRB: ['serbia', 'serbie'],
      SVK: ['slovakia', 'slovak republic', 'slovaquie'], SVN: ['slovenia', 'slovénie'],
      ESP: ['spain', 'espagne'], SWE: ['sweden', 'suède'], CHE: ['switzerland', 'suisse'],
      TUR: ['turkey', 'türkiye', 'turkiye', 'turquie'], UKR: ['ukraine'],
      GBR: ['united kingdom', 'uk', 'u.k.', 'royaume-uni', 'great britain'],
    };
    const RESPONDENT_BY_NAME = {};
    for (const [code, names] of Object.entries(RESPONDENT_CODES)) for (const n of names) RESPONDENT_BY_NAME[n] = code;
    const VERSUS_RE = /\s+(?:v\.?|c\.|vs\.?)\s+/i;
    const NAME_FILLER = new Set(['and', 'others', 'other', 'et', 'autres', 'the', 'of']);

    function respondentCode(state) {
      let s = String(state).split(/[[(,]/)[0];
      s = s.trim().toLowerCase().replace(/^(?:the|la|le|l')\s*/, '');
      s = s.replace(/\s+/g, ' ').replace(/^[ .]+|[ .]+$/g, '');
      return RESPONDENT_BY_NAME[s] || RESPONDENT_BY_NAME[s.replace(/\./g, '')] || null;
    }

    const BRANCH_PRIORITY = {
      GRANDCHAMBER: 0, CHAMBER: 1, COMMITTEE: 2,
      ADMISSIBILITY: 3, ADMISSIBILITYCOM: 4, MERITS: 5,
    };

    // Lower is better: real judgment > decision > advisory opinion > legal
    // summary > CM resolution > other > press release; then GC > Chamber >
    // Committee; then preferred language; then most recent.
    function scoreKey(c, langPref) {
      const doctype = c.doctype || '';
      let kind;
      if (doctype === 'HEJUD' || doctype === 'HFJUD') kind = 0;
      else if (doctype === 'HEDEC' || doctype === 'HFDEC') kind = 1;
      else if (['ADV', 'HEADV', 'HFADV'].includes(doctype)) kind = 2;
      else if (doctype === 'CLIN' || doctype === 'INFONOTE') kind = 3;
      else if (doctype.startsWith('HERES') || doctype.startsWith('HFRES')) kind = 4;
      else if (doctype === 'PR') kind = 6;
      else kind = 5;
      const branch = BRANCH_PRIORITY[c.doctypebranch || ''] ?? 9;
      let lang = langPref.indexOf(c.languageisocode || '');
      if (lang < 0) lang = langPref.length;
      const date = c.kpdate ? c.kpdate.replace(/\d/g, (d) => String(9 - Number(d))) : '9'.repeat(19);
      return [kind, branch, lang, date];
    }

    function compareKeys(a, b) {
      for (let i = 0; i < a.length; i++) {
        if (a[i] < b[i]) return -1;
        if (a[i] > b[i]) return 1;
      }
      return 0;
    }

    // {clause, length} for the query, plus `fallback` (the name without the
    // respondent filter) when a name search is narrowed by respondent state.
    function referenceClause(ref) {
      if (ITEMID_RE.test(ref)) return { clause: `itemid:"${ref}"`, length: 1 };
      const appnos = appnosIn(ref);
      if (appnos.length) return { clause: `appno:"${appnos[0]}"`, length: 50 };
      if (ECLI_RE.test(ref)) return { clause: `ecli:"${ref.toUpperCase()}"`, length: 50 };
      if (ref.includes(':') && !ref.startsWith('"')) return { clause: ref, length: 50 };
      // A citation with its application number: the number is the key.
      const found = ref.match(APPNO_ANY_RE);
      if (found) return { clause: `appno:"${found[0]}"`, length: 50 };
      // Free-text case name: AND of the tokens before " v. " / " c. ",
      // narrowed by the respondent state after it.
      const parts = ref.split(VERSUS_RE);
      const head = parts[0];
      let tokens = (head.match(/[\p{L}\p{N}_'-]+/gu) || []).filter((t) => t.length > 1);
      if (!tokens.length) tokens = ref.match(/[\p{L}\p{N}_'-]+/gu) || [];
      const clause = tokens.map((t) => 'docname:' + t).join(' AND ') || `docname:"${ref}"`;
      const code = parts.length > 1 ? respondentCode(parts.slice(1).join(' ')) : null;
      // The applicant's name for ranking: every word before "v.", one-letter
      // ones included ("A v. Norway"), never "v" or the state, and not the
      // words that differ between the English and French title.
      const name = (head.match(/[\p{L}\p{N}_'-]+/gu) || []).filter((t) => !NAME_FILLER.has(t.toLowerCase()));
      if (code) return { clause: `${clause} AND respondent:"${code}"`, length: 50, fallback: clause, name };
      return { clause, length: 50, name };
    }

    // See NAME_SEARCH_MAX_ROWS / name_matches / _rows_for in hudoc.py:
    // HUDOC's docname search matches inside words ("Kurt" finds Özkurt), so
    // a name search reads further pages and whole-word matches rank first.
    const NAME_SEARCH_MAX_ROWS = 300;

    function nameMatches(row, name) {
      const docname = String(row.docname || '').toUpperCase();
      return (name || []).every((t) => {
        const esc = t.toUpperCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return new RegExp(`(?<![\\p{L}\\p{N}_])${esc}(?![\\p{L}\\p{N}_])`, 'u').test(docname);
      });
    }

    async function rowsFor(clause, length, name, fields) {
      const r = await query(clause, { fields, length });
      if (r.error || !name || !name.length) return r;
      const rows = r.rows;
      while (rows.length && rows.length < Math.min(r.resultcount, NAME_SEARCH_MAX_ROWS)) {
        const more = await query(clause, { fields, start: rows.length, length: 100 });
        if (more.error) return more;
        if (!more.rows.length) break;
        rows.push(...more.rows);
      }
      return { resultcount: r.resultcount, rows };
    }

    async function resolveRow(reference, { doctype = null, langPref = ['ENG', 'FRE'], fields = DEFAULT_FIELDS } = {}) {
      const ref = String(reference).trim();
      const { clause, length, fallback, name } = referenceClause(ref);
      let r = await rowsFor(clause, length, name, fields);
      if (r.error) return r;
      if (!r.rows.length && fallback) {
        r = await rowsFor(fallback, length, name, fields);
        if (r.error) return r;
      }
      let rows = r.rows;
      if (!rows.length) return { error: 'no_match', detail: `no HUDOC item matched ${JSON.stringify(ref)}; try search()` };
      if (doctype) {
        const want = doctype.toUpperCase();
        const filtered = rows.filter((x) => (x.doctypebranch || '').toUpperCase() === want);
        if (!filtered.length) {
          const available = [...new Set(rows.map((x) => x.doctypebranch || '?'))].sort();
          return { error: 'no_match', detail: `no ${want} row for ${JSON.stringify(ref)}; available: ${available.join(', ')}` };
        }
        rows = filtered;
      }
      if (ITEMID_RE.test(ref)) return { row: rows[0] };
      // Whole-word name matches first (Kurt before Özkurt), then the rest.
      const key = (x) => [nameMatches(x, name) ? 0 : 1, ...scoreKey(x, langPref)];
      rows.sort((a, b) => compareKeys(key(a), key(b)));
      return { row: rows[0] };
    }

    // --- citations (ported from parse_scl) ----------------------------------

    const MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December';

    function parseScl(scl) {
      const out = [];
      for (let raw of String(scl || '').split(/;\s*/)) {
        raw = raw.trim();
        if (!raw) continue;
        const appnos = [];
        const m = raw.match(/nos?\.\s*([\d/]+(?:\s*and\s*[\d/]+)*)/i);
        if (m) {
          for (const part of m[1].split(/\s+and\s+/i)) {
            if (part.includes('/')) appnos.push(part.trim());
          }
        }
        const name = raw.split(/,\s*nos?\./i)[0].trim();
        const d = raw.match(new RegExp(`(\\d{1,2}\\s+(?:${MONTHS})\\s+\\d{4})`));
        out.push({ raw, name, appnos, date: d ? d[1] : null });
      }
      return out;
    }

    // --- HTML -> text (mirrors html_to_text in scripts/hudoc.py) ------------

    // Both sides walk the markup with the same token regex, not a DOM, so the
    // text matches character for character (and Node can test it).
    const HTML_TOKEN_RE = /<!--[\s\S]*?-->|<(\/?)([A-Za-z][\w:.-]*)([^>]*?)(\/?)>|([^<]+)/g;
    const HTML_BLOCK = new Set(['p', 'div', 'li', 'tr', 'td', 'th', 'table', 'hr', 'ol', 'ul', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']);
    const HTML_NAMED = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: String.fromCharCode(0xa0) };
    // Whitespace (non-breaking spaces included: hudoc's documented exception,
    // see _TEXT_FIXES in hudoc.py), and Word Symbol/Wingdings characters
    // (private-use code points) used for bullets and footnote marks; nothing
    // else is changed.
    // Same table as _TEXT_FIXES in hudoc.py.
    const TEXT_FIXES = new Map([
      [0xa0, ' '], [0x202f, ' '], [0x09, ' '], [0x0d, ' '],
      [0xf02a, '*'], [0xf09f, '•'], [0xf0a7, '▪'], [0xf0b7, '•'], [0xf0d8, '➢'], [0xf0fc, '✓'],
    ]);
    const ROMAN = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
      [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];

    function htmlUnescape(s) {
      return s.replace(/&(#[xX][0-9a-fA-F]+|#\d+|[A-Za-z]+);/g, (m, e) => {
        if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
        const named = HTML_NAMED[e.toLowerCase()];
        return named === undefined ? m : named;
      });
    }

    function attr(attrs, name) {
      const m = attrs.match(new RegExp('\\b' + name + '="([^"]*)"'));
      return m ? m[1] : null;
    }

    function listLabel(n, kind) {
      if (kind === 'I' || kind === 'i') {
        let out = '';
        for (const [value, numeral] of ROMAN) {
          while (n >= value) { out += numeral; n -= value; }
        }
        return kind === 'I' ? out : out.toLowerCase();
      }
      if (kind === 'A' || kind === 'a') {
        let out = '';
        while (n > 0) {
          const r = (n - 1) % 26;
          n = Math.floor((n - 1) / 26);
          out = String.fromCharCode(kind.charCodeAt(0) + r) + out;
        }
        return out;
      }
      return String(n);
    }

    // Emphasis and superscript (mirrors hudoc.py and source_text.py): classes
    // from the page's <style>, inherited and overridden element by element;
    // italic/bold text becomes *…*/**…**, raised text that is not a footnote
    // reference becomes superscript.
    const EM = String.fromCharCode(2); const EM_END = String.fromCharCode(3);
    const STRONG = String.fromCharCode(4); const STRONG_END = String.fromCharCode(5);
    const SUP = String.fromCharCode(6); const SUP_END = String.fromCharCode(7);
    const MARKERS = EM + EM_END + STRONG + STRONG_END;
    const WS = ' \t\r\f\v';
    const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
    const SUP_CHARS = new Map(Array.from('0123456789+-−=()', (c, k) => [c, '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾'[k]]));

    function cssProps(decl) {
      const out = {};
      let m = decl.match(/font-style\s*:\s*([A-Za-z]+)/);
      if (m) out.i = ['italic', 'oblique'].includes(m[1].toLowerCase());
      m = decl.match(/font-weight\s*:\s*([A-Za-z0-9]+)/);
      if (m) {
        const w = m[1].toLowerCase();
        out.b = w === 'bold' || w === 'bolder' || (/^[0-9]+$/.test(w) && Number(w) >= 600);
      }
      m = decl.match(/vertical-align\s*:\s*([A-Za-z-]+)/);
      if (m) out.sup = m[1].toLowerCase() === 'super';
      return out;
    }

    function cssClasses(html) {
      let css = '';
      for (const s of html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)) css += s[1];
      const out = new Map();
      let n = 0;
      for (const r of css.matchAll(/\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}/g)) {
        const props = cssProps(r[2]);
        if (Object.keys(props).length) out.set(r[1], [n, Object.assign({}, (out.get(r[1]) || [0, {}])[1], props)]);
        n += 1;
      }
      return out;
    }

    function elementStyle(tag, attrs, parent, classes) {
      const style = { i: parent[0], b: parent[1], sup: parent[2] };
      if (tag === 'i' || tag === 'em') style.i = true;
      else if (tag === 'b' || tag === 'strong') style.b = true;
      else if (tag === 'sup') style.sup = true;
      const rules = (attr(attrs, 'class') || '').split(' ').filter((c) => classes.has(c)).map((c) => classes.get(c));
      rules.sort((x, y) => x[0] - y[0]);
      for (const [, props] of rules) Object.assign(style, props);
      Object.assign(style, cssProps(attr(attrs, 'style') || ''));
      return [style.i, style.b, style.sup];
    }

    function styled(text, style) {
      const [i, b, sup] = style;
      if (sup) return SUP + text + SUP_END;
      return (i ? EM : '') + (b ? STRONG : '') + text + (b ? STRONG_END : '') + (i ? EM_END : '');
    }

    function superscript(text) {
      const core = text.replace(/^[ \t\r\f\v\n]+|[ \t\r\f\v\n]+$/g, '');
      if (!core) return text;
      const at = text.indexOf(core);
      const lead = text.slice(0, at); const trail = text.slice(at + core.length);
      if (Array.from(core).every((c) => SUP_CHARS.has(c))) return lead + Array.from(core, (c) => SUP_CHARS.get(c)).join('') + trail;
      return `${lead}^${core}^${trail}`;
    }

    // *italic*, **bold**, nested as Markdown nests them; spaces go outside the
    // markers and no marker spans a line (source_text.finish).
    function finish(text) {
      if (!Array.from(MARKERS).some((c) => text.includes(c))) return text;
      const out = []; const opened = []; let ws = [];
      let italic = 0; let bold = 0;
      const closeTo = (target) => {
        let keep = 0;
        while (keep < opened.length && target.has(opened[keep])) keep += 1;
        for (let k = opened.length - 1; k >= keep; k -= 1) out.push(opened[k]);
        opened.length = keep;
      };
      for (const c of text) {
        if (c === EM) { italic += 1; continue; }
        if (c === EM_END) { italic = Math.max(0, italic - 1); continue; }
        if (c === STRONG) { bold += 1; continue; }
        if (c === STRONG_END) { bold = Math.max(0, bold - 1); continue; }
        if (c === '\n') { closeTo(new Set()); out.push(...ws); ws = []; out.push(c); continue; }
        if (WS.includes(c)) { ws.push(c); continue; }
        const target = new Set();
        if (bold > 0) target.add('**');
        if (italic > 0) target.add('*');
        closeTo(target);
        out.push(...ws); ws = [];
        for (const mark of ['**', '*']) {
          if (target.has(mark) && !opened.includes(mark)) { out.push(mark); opened.push(mark); }
        }
        out.push(c);
      }
      closeTo(new Set());
      out.push(...ws);
      return out.join('');
    }

    function resolveMarks(s) {
      s = s.split(SUP_END + SUP).join('');
      s = s.replace(new RegExp(SUP + '([^' + SUP_END + ']*)' + SUP_END, 'g'), (_, t) => superscript(t));
      return finish(s);
    }

    function cleanBlock(s) {
      let fixed = '';
      for (const ch of s) {
        const r = TEXT_FIXES.get(ch.codePointAt(0));
        fixed += r === undefined ? ch : r;
      }
      return resolveMarks(fixed).split('\n').map((line) => line.replace(/ {2,}/g, ' ').replace(/^ +| +$/g, '')).filter(Boolean).join('\n');
    }

    // One block per paragraph, blocks separated by a blank line, <br> kept as
    // a single newline; <ol start="2" type="I"> numbers written out; footnote
    // references as " [fn N]" with N the label as printed, and the notes
    // under a FOOTNOTES heading.
    function htmlToText(html) {
      const blocks = [];
      const notes = new Map();
      let parts = [];
      const lists = [];
      let divs = 0; let note = null; let noteDepth = 0; let skip = 0;
      let ref = null; let refText = [];
      const printed = new Map(); // footnote id -> its printed label
      const classes = cssClasses(html);
      const stack = [['', false, false, false]]; // open elements: [tag, italic, bold, sup]
      const NUL = String.fromCharCode(0); const SOH = String.fromCharCode(1);
      const flush = () => {
        const text = cleanBlock(parts.join(''));
        parts = [];
        if (!text) return;
        if (note) {
          if (!notes.has(note)) notes.set(note, []);
          notes.get(note).push(text);
        } else blocks.push(text);
      };
      HTML_TOKEN_RE.lastIndex = 0;
      let m;
      while ((m = HTML_TOKEN_RE.exec(html))) {
        if (m[5] !== undefined) {
          if (skip) continue;
          const text = htmlUnescape(m[5].replace(/[\r\n]+/g, ' '));
          if (ref) refText.push(text);
          else parts.push(styled(text, stack[stack.length - 1].slice(1)));
          continue;
        }
        if (m[2] === undefined) continue; // comment
        const closing = m[1] === '/'; const tag = m[2].toLowerCase(); const attrs = m[3];
        if (tag === 'style' || tag === 'script') { skip += closing ? -1 : 1; continue; }
        if (closing) {
          for (let k = stack.length - 1; k > 0; k -= 1) {
            if (stack[k][0] === tag) { stack.length = k; break; }
          }
        } else if (!VOID.has(tag) && !m[4]) {
          stack.push([tag, ...elementStyle(tag, attrs, stack[stack.length - 1].slice(1), classes)]);
        }
        if (tag === 'a') {
          if (closing) {
            if (ref) {
              const label = cleanBlock(refText.join('')).replace(/^\[+|\]+$/g, '').replace(/^ +| +$/g, '');
              if (label && !printed.has(ref)) printed.set(ref, label);
            }
            ref = null;
            continue;
          }
          const href = attr(attrs, 'href') || '';
          const r = href.match(/^#_ftn(?:ref)?(\d+)$/);
          if (r) {
            ref = r[1]; refText = [];
            // Placeholder for the body marker; the label is only final once
            // every footnote has been seen.
            if (!href.startsWith('#_ftnref')) parts.push(' ' + NUL + ref + SOH);
          }
          continue;
        }
        if (tag === 'br') { parts.push('\n'); continue; }
        if (!HTML_BLOCK.has(tag)) continue;
        flush();
        if (tag === 'div') {
          if (closing) {
            divs -= 1;
            if (note && divs < noteDepth) note = null;
          } else {
            divs += 1;
            const id = (attr(attrs, 'id') || '').match(/^_ftn(\d+)$/);
            if (id) {
              note = id[1]; noteDepth = divs;
            }
          }
        } else if (tag === 'ol' || tag === 'ul') {
          if (closing) lists.pop();
          else {
            const start = attr(attrs, 'start');
            const kind = tag === 'ul' ? '•' : (attr(attrs, 'type') || '1');
            lists.push([kind, start && /^\d+$/.test(start) ? Number(start) : 1]);
          }
        } else if (tag === 'li' && !closing && lists.length) {
          const top = lists[lists.length - 1];
          parts.push(top[0] === '•' ? '• ' : listLabel(top[1], top[0]) + '. ');
          top[1] += 1;
        }
      }
      flush();
      // The printed label; Word's footnote id only if none was printed.
      const label = (id) => printed.get(id) || id;
      const out = blocks.slice();
      if (notes.size) {
        out.push('FOOTNOTES');
        for (const [id, texts] of notes) out.push(`[fn ${label(id)}] ${texts.join(' ')}`);
      }
      const text = out.join('\n\n') + '\n';
      return text.replace(new RegExp(NUL + '([0-9]+)' + SOH, 'g'), (_, id) => `[fn ${label(id)}]`);
    }

    // --- numbered paragraphs ------------------------------------------------

    // The judgment's own paragraphs start "88.  Text …". Separate opinions and
    // the operative part restart at 1, so a number can occur several times;
    // the first occurrence is the judgment's.
    function blocks(text) {
      return text.split('\n\n');
    }

    function paragraphStarts(text, n) {
      const re = new RegExp(`^${n}\\.\\s`);
      const out = [];
      blocks(text).forEach((b, i) => { if (re.test(b)) out.push(i); });
      return out;
    }

    const HEADING_RE = /^(?:[IVXLC]+\.|[A-Z]\.|\d+\.\s*[A-Z][A-Z ,'’-]{8,}$)\s|^[A-Z][A-Z .,'’()-]{10,}$/;

    // --- public API -----------------------------------------------------------

    async function ready() {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await query('itemid:"001-57619"', { fields: ['itemid', 'docname'], length: 1 });
      if (r.error) return r;
      return { ok: true, VERSION: HELPER_VERSION, probe: r.rows[0] ? r.rows[0].docname : null };
    }

    // Lucene search, as in `hudoc.py search`. `select: 'full'` returns every
    // field of DEFAULT_FIELDS; the default is a compact set.
    async function search(lucene, { length = 10, start = 0, sort = 'kpdate Descending', select = null } = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const fields = select === 'full' ? DEFAULT_FIELDS : (Array.isArray(select) ? select : SEARCH_FIELDS);
      const r = await query(lucene, { fields, sort, start, length });
      if (r.error) return r;
      return fitRows({ resultcount: r.resultcount, shown: r.rows.length, results: r.rows }, 'results');
    }

    async function resolve(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await resolveRow(ref, { ...opts, fields: SEARCH_FIELDS.concat(['ecli', 'article']) });
      if (r.error) return r;
      return { ...r.row, source_url: WEB_URL + r.row.itemid, pdf_url: pdfUrl(r.row.itemid) };
    }

    async function metadata(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await resolveRow(ref, opts);
      if (r.error) return r;
      return fitRow({ ...r.row, source_url: WEB_URL + r.row.itemid, pdf_url: pdfUrl(r.row.itemid) });
    }

    async function citations(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await resolveRow(ref, opts);
      if (r.error) return r;
      const cited = parseScl(r.row.scl);
      return fitRows({ itemid: r.row.itemid, docname: r.row.docname, cited_count: cited.length, cited }, 'cited');
    }

    // Fetch the HTML of HUDOC's reading view and convert it to text in the page. The text is
    // cached here by itemid; read it with page(), grep() and paragraph().
    async function load(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      let meta;
      const cachedId = ITEMID_RE.test(String(ref).trim()) ? String(ref).trim() : null;
      if (cachedId && cache.items[cachedId]) meta = cache.items[cachedId].meta;
      else {
        const r = await resolveRow(ref, opts);
        if (r.error) return r;
        meta = r.row;
      }
      const id = meta.itemid;
      if (!cache.items[id]) {
        const url = `${HTML_PATH}?library=ECHR&id=${encodeURIComponent(id)}`;
        let res, body;
        try {
          res = await deps.fetch(url, { credentials: 'include' });
          body = await res.text();
        } catch (e) {
          return { error: 'fetch_failed', detail: String((e && e.message) || e) };
        }
        if (isChallenge(res.status, body)) return { error: 'challenge', detail: 'Cloudflare "Just a moment…" page' };
        if (!(res.ok && /<(?:p|div|li|td)[\s>]/.test(body))) {
          return { error: 'no_html', detail: `HTTP ${res.status}, ${body.length} characters, no HTML text — HUDOC may hold this item as PDF only (${pdfUrl(id)})` };
        }
        let text;
        try {
          text = htmlToText(body);
        } catch (e) {
          return { error: 'bad_html', detail: String((e && e.message) || e) };
        }
        cache.items[id] = { meta, text };
      }
      const { text } = cache.items[id];
      const numbered = blocks(text).filter((b) => /^\d+\.\s/.test(b)).length;
      return {
        itemid: id,
        docname: meta.docname,
        appno: meta.appno,
        kpdate: meta.kpdate,
        doctypebranch: meta.doctypebranch,
        languageisocode: meta.languageisocode,
        ecli: meta.ecli,
        totalChars: text.length,
        numberedBlocks: numbered,
        pages: Math.ceil(text.length / PAGE_SIZE),
        source_url: WEB_URL + id,
        pdf_url: pdfUrl(id),
      };
    }

    function requireLoaded(itemid) {
      const e = cache.items[itemid];
      return e ? null : { error: 'not_loaded', detail: `${itemid} not loaded in this tab — call load() first` };
    }

    // A slice of the text; `next` is the offset of the following slice, or null.
    async function page(itemid, offset = 0, size = PAGE_SIZE - 500) {
      const bad = requireLoaded(itemid);
      if (bad) return bad;
      const text = cache.items[itemid].text;
      size = Math.min(Math.max(1, size | 0), PAGE_SIZE - 500);
      offset = Math.max(0, offset | 0);
      // JSON escaping (quotes, newlines) makes the response longer than the
      // slice itself; shrink until the serialised result fits.
      let out;
      for (;;) {
        const next = offset + size < text.length ? offset + size : null;
        out = { itemid, offset, next, total: text.length, text: text.slice(offset, offset + size) };
        if (JSON.stringify(out).length <= PAGE_SIZE || size <= 1000) break;
        size -= 1000;
      }
      return out;
    }

    // `term` is literal (spaces match any whitespace, a hyphen also a
    // non-breaking one) unless regex = true.
    // Each hit carries the number of the judgment paragraph it falls in.
    async function grep(itemid, term, ctx = 400, max = 15, regex = false) {
      const bad = requireLoaded(itemid);
      if (bad) return bad;
      const text = cache.items[itemid].text;
      let re;
      try {
        // The text keeps the Court's non-breaking hyphens (a typed "-"
        // matches either) and its emphasis (*…*, **…**, which may sit
        // anywhere inside a phrase: skipped between any two characters).
        const glue = '\\*{0,3}';
        const char = (c) => (c === '-' ? '[-' + String.fromCharCode(0x2011) + ']' : c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
        const source = regex ? term : String(term).replace(/\*/g, '').trim().split(/\s+/)
          .map((w) => Array.from(w, char).join(glue)).join(glue + '\\s+' + glue);
        re = new RegExp(source, 'gi');
      } catch (e) {
        return { error: 'not_found', detail: `invalid regex: ${term}` };
      }
      const hits = [];
      let total = 0;
      let m;
      while ((m = re.exec(text))) {
        total += 1;
        if (hits.length < max) {
          const before = text.slice(0, m.index);
          const pm = [...before.matchAll(/(?:^|\n\n)(\d+)\.\s/g)].pop();
          const a = Math.max(0, m.index - ctx);
          const b = Math.min(text.length, m.index + m[0].length + ctx);
          hits.push({ offset: m.index, paragraph: pm ? Number(pm[1]) : null, snippet: text.slice(a, b) });
        }
        if (m.index === re.lastIndex) re.lastIndex += 1;
      }
      return fitRows({ itemid, term, total, shown: hits.length, hits }, 'hits');
    }

    // Judgment paragraph n (and the following count-1), up to the next
    // numbered paragraph, with trailing section headings dropped.
    async function paragraph(itemid, n, count = 1) {
      const bad = requireLoaded(itemid);
      if (bad) return bad;
      const text = cache.items[itemid].text;
      const bl = blocks(text);
      const starts = paragraphStarts(text, n);
      if (!starts.length) return { error: 'not_found', detail: `no paragraph ${n}. in ${itemid}` };
      const from = starts[0];
      let to = bl.length;
      for (let i = from + 1; i < bl.length; i++) {
        if (new RegExp(`^${n + count}\\.\\s`).test(bl[i]) || /^(FOR THESE REASONS|PAR CES MOTIFS|FOOTNOTES$)/.test(bl[i])) { to = i; break; }
      }
      let chunk = bl.slice(from, to);
      while (chunk.length > 1 && HEADING_RE.test(chunk[chunk.length - 1].replace(/\*/g, ''))) chunk = chunk.slice(0, -1);
      const full = chunk.join('\n\n');
      const res = { itemid, paragraph: n, count, text: full };
      while (JSON.stringify(res).length > PAGE_SIZE - 800) {
        res.text = res.text.slice(0, res.text.length - 2000);
        res.truncated = 'use page() from offset ' + (text.indexOf(full) + res.text.length) + ' for the rest';
      }
      if (starts.length > 1) {
        res.note = `"${n}." also starts ${starts.length - 1} later block(s) — separate opinions and the operative part number from 1 again; this is the first occurrence`;
      }
      return res;
    }

    return {
      VERSION: HELPER_VERSION,
      PAGE_SIZE,
      cache,
      ready,
      search,
      resolve,
      metadata,
      citations,
      load,
      page,
      grep,
      paragraph,
      // exposed for unit tests / debugging only:
      _deps: deps,
      _internal: { referenceClause, appnosIn, respondentCode, nameMatches, scoreKey, compareKeys, parseScl, htmlToText, queryUrl, isChallenge, paragraphStarts },
    };
  })();

  if (root.window) root.window.__hd = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
