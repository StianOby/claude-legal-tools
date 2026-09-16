// Consilium Treaties Office database — in-page helper for the Claude Desktop
// built-in browser (Cowork). Paste the whole file into a tab parked on
// https://www.consilium.europa.eu/en/documents/treaties-agreements/ via
// javascript_tool once per tab.
//
// Idempotent: re-pasting is a no-op if window.__cs already exists. All
// functions are async and return plain JSON-serialisable objects. They never
// throw to the caller — errors come back as
// {error: 'challenge' | 'wrong_origin' | 'unknown_party' | 'bad_id' |
//         'not_found' | 'http_<n>' | 'fetch_failed' | 'no_results_container' |
//         'not_cached', detail}.
//
// Why a browser helper at all: www.consilium.europa.eu sits behind a
// Cloudflare "managed challenge" (HTTP 403, `cf-mitigated: challenge`) for
// every non-browser client — curl, Python, WebFetch, headless Chrome alike
// (verified 2026-09-16, see NOTES.md). Same-origin fetch() from a tab that
// has already passed the challenge is the only supported way in. The helper
// therefore does nothing to *bypass* the challenge: if a response is itself a
// challenge page it reports {error: 'challenge'} and stops.
//
// Also exported for Node (CommonJS) so the pure parsers can be unit-tested
// against saved HTML fixtures with a DOM shim — see NOTES.md §3 and tests/run.js.

(function (root) {
  if (root.window && root.window.__cs) return;

  const api = (() => {
    // javascript_tool errors hard above ~49-50K raw characters ("result
    // exceeds maximum allowed tokens") rather than truncating. 45000 leaves
    // headroom for the tool's wrapper text and JSON-escaping expansion.
    // (Measured for the lovdata-pro skill; same tool channel.)
    const PAGE_SIZE = 45000;

    const ORIGIN = 'https://www.consilium.europa.eu';
    const BASE = '/en/documents/treaties-agreements/';
    const SEARCH_URL = ORIGIN + BASE;
    const DETAIL_URL = ORIGIN + BASE + 'agreement/';
    const RATIFICATION_URL = ORIGIN + BASE + 'ratification/';

    // Injected so tests can swap in a DOM shim / canned responses.
    const deps = {
      fetch: (url, opts) => fetch(url, opts),
      parse: (html) => new DOMParser().parseFromString(html, 'text/html'),
      currentDocument: () => (typeof document !== 'undefined' ? document : null),
      location: () => (typeof location !== 'undefined' ? location : null),
    };

    const cache = {
      parties: null,      // [{code, name, names}]
      searches: {},       // key -> {meta, results}
      details: {},        // id -> detail object
      texts: {},          // key -> string (declarations, captures)
    };

    // --- small utilities --------------------------------------------------

    const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim();

    // Site dates are DD/MM/YYYY; the form's "empty" value is 01/01/0001.
    function toIso(s) {
      const m = String(s || '').match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
      if (!m) return null;
      if (m[3] === '0001') return null;
      return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
    }

    // Accepts ISO date, DD/MM/YYYY, or bare year; returns DD/MM/YYYY for the
    // form. `end` picks 31/12 for a bare year (DateTo), else 01/01.
    function toSiteDate(v, end = false) {
      if (v == null || v === '') return null;
      const s = String(v).trim();
      let m;
      if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/))) return `${m[3]}/${m[2]}/${m[1]}`;
      if ((m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/))) return `${m[1].padStart(2, '0')}/${m[2].padStart(2, '0')}/${m[3]}`;
      if ((m = s.match(/^(\d{4})$/))) return end ? `31/12/${m[1]}` : `01/01/${m[1]}`;
      return null;
    }

    const PV_RE = /proc[eè]s[\s-]*verba/i;

    function isChallengeHtml(html) {
      return /<title>\s*(Just a moment|Browser check)/i.test(html)
        || /challenge-error-text|_cf_chl_opt/.test(html);
    }

    function fitToPageSize(obj, shrink) {
      // Serialise; if too big, let `shrink(obj)` reduce it and retry.
      for (let i = 0; i < 50; i++) {
        const s = JSON.stringify(obj);
        if (s.length <= PAGE_SIZE) return obj;
        if (!shrink || !shrink(obj)) break;
      }
      return obj;
    }

    // --- network ----------------------------------------------------------

    async function fetchHtml(url) {
      let res;
      try {
        res = await deps.fetch(url, { credentials: 'include' });
      } catch (e) {
        return { error: 'fetch_failed', detail: String((e && e.message) || e), url };
      }
      const html = await res.text();
      const mitigated = res.headers && res.headers.get && res.headers.get('cf-mitigated');
      if (mitigated === 'challenge' || (res.status === 403 && isChallengeHtml(html))) {
        return {
          error: 'challenge',
          url,
          detail: 'Cloudflare challenge page returned. Wait for the tab to settle or ask the user to reload it; do not retry in a loop.',
        };
      }
      if (res.status >= 400) return { error: `http_${res.status}`, url };
      return { html, url, status: res.status };
    }

    // --- parties (the code list) -----------------------------------------

    // The search form is an alphabetical index: each party appears once per
    // name form, as `<label>text <input name="Parties" value="CODE"></label>`
    // (the label wraps the input; there is no `for`). The text is either
    // "Short - Long" (Long may be blank: "Greenland -") or "Long (Short)".
    // 412 inputs dedupe to 256 codes (Sept 2026). `name` is the short form —
    // the one the ratification tables use — `long_name` the official one.
    function splitLabel(text) {
      const t = norm(text);
      let m;
      if ((m = t.match(/^(.*?)\s+-(?:\s+(.*))?$/))) return { short: norm(m[1]), long: norm(m[2]) || null };
      if ((m = t.match(/^(.*)\s\(([^()]+)\)$/))) return { short: norm(m[2]), long: norm(m[1]) || null };
      return { short: t, long: null };
    }

    function parsePartyList(doc) {
      const inputs = Array.from(doc.querySelectorAll('input')).filter(
        (i) => String(i.getAttribute('name') || '').toLowerCase() === 'parties',
      );
      const byCode = new Map();
      for (const input of inputs) {
        const code = norm(input.getAttribute('value'));
        if (!code) continue;
        let label = '';
        const l = input.closest && input.closest('label');
        if (l) label = norm(l.textContent);
        if (!label && input.parentElement) label = norm(input.parentElement.textContent);
        if (!label && input.nextSibling) label = norm(input.nextSibling.textContent);
        const entry = byCode.get(code) || { code, name: null, long_name: null, names: [] };
        if (label) {
          const { short, long } = splitLabel(label);
          if (!entry.name || (short && short.length < entry.name.length)) entry.name = short;
          if (long && (!entry.long_name || long.length > entry.long_name.length)) entry.long_name = long;
          for (const n of [short, long, label]) if (n && !entry.names.includes(n)) entry.names.push(n);
        }
        byCode.set(code, entry);
      }
      const out = Array.from(byCode.values()).map((e) => ({ ...e, name: e.name || e.code }));
      out.sort((a, b) => a.code.localeCompare(b.code));
      return out;
    }

    // Lower-cased name → code, over every name form, for mapping the plain
    // party names in ratification tables back to codes.
    function partyIndexOf(parties) {
      const idx = new Map();
      for (const p of parties || []) for (const n of p.names) {
        const k = n.toLowerCase();
        if (!idx.has(k)) idx.set(k, p.code);
      }
      return idx;
    }

    async function loadParties({ force = false } = {}) {
      if (cache.parties && !force) return cache.parties;
      // Prefer the current document if it is the search form.
      const doc = deps.currentDocument();
      if (doc) {
        const local = parsePartyList(doc);
        if (local.length > 50) { cache.parties = local; return local; }
      }
      const r = await fetchHtml(SEARCH_URL + '?Lang=en');
      if (r.error) return r;
      const parsed = parsePartyList(deps.parse(r.html));
      if (parsed.length < 50) {
        return { error: 'no_results_container', detail: `only ${parsed.length} party inputs found on the search form`, url: r.url };
      }
      cache.parties = parsed;
      return parsed;
    }

    // Short queries (≤ 3 chars) look like codes: match the code or a whole
    // word only — "AT" must not hit "St**at**es". Longer ones are substrings.
    function partyMatches(p, q) {
      const ql = q.toLowerCase();
      if (p.code.toLowerCase() === ql) return true;
      if (ql.length <= 3) {
        const re = new RegExp(`(^|[^\\p{L}])${ql.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\p{L}])`, 'iu');
        return p.names.some((n) => re.test(n));
      }
      return p.names.some((n) => n.toLowerCase().includes(ql));
    }

    // Levenshtein for "did you mean" on short codes.
    function editDistance(a, b) {
      a = a.toUpperCase(); b = b.toUpperCase();
      const dp = Array.from({ length: a.length + 1 }, (_, i) => [i]);
      for (let j = 1; j <= b.length; j++) dp[0][j] = j;
      for (let i = 1; i <= a.length; i++) {
        for (let j = 1; j <= b.length; j++) {
          dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        }
      }
      return dp[a.length][b.length];
    }

    // Codes people type from ISO 3166 / common usage that the site does NOT
    // use for that party, mapped to what it uses instead. The site's own list
    // is authoritative; this feeds suggestions — and one hard stop: `EC` is
    // Ecuador on the site, so a bare "EC" is ambiguous and must be confirmed
    // with {literal: true} (Ecuador) or rewritten as CE (European Community).
    const ISO_TRAPS = {
      AT: 'A', BE: 'B', DE: 'D', FR: 'F', IT: 'I', IE: 'IRL', HU: 'H', PT: 'P', SE: 'S', FI: 'SF',
      EU: 'UE', EC: 'CE', EEC: 'CEE', EEA: 'EEE',
    };

    async function resolveParty(code, { literal = false } = {}) {
      const parties = await loadParties();
      if (parties.error) return parties;
      const c = norm(code);
      const exact = parties.find((p) => p.code.toUpperCase() === c.toUpperCase());
      const trap = ISO_TRAPS[c.toUpperCase()];
      if (exact && trap && !literal) {
        const t = parties.find((p) => p.code === trap);
        return {
          error: 'ambiguous_code',
          detail: `"${c.toUpperCase()}" is ${exact.name} on this site; the party usually meant by ${c.toUpperCase()} is coded ${trap}${t ? ` (${t.name})` : ''}. Pass {literal: true} for ${exact.name}, or use ${trap}.`,
          options: [{ code: exact.code, name: exact.name }, ...(t ? [{ code: t.code, name: t.name }] : [])],
        };
      }
      if (exact) return { code: exact.code, name: exact.name };
      const suggestions = [];
      if (trap) {
        const t = parties.find((p) => p.code === trap);
        if (t) suggestions.push({ code: t.code, name: t.name, why: `site uses ${t.code}, not ISO ${c.toUpperCase()}` });
      }
      for (const p of parties) {
        if (partyMatches(p, c) && !suggestions.some((s) => s.code === p.code)) suggestions.push({ code: p.code, name: p.name, why: 'name match' });
      }
      // Fuzzy codes only as a last resort, and never for 2-letter queries —
      // every code starting with the same letter is one edit away from those.
      if (suggestions.length === 0 && c.length >= 3) {
        for (const p of parties) {
          if (p.code.length <= 4 && editDistance(p.code, c) <= 1) suggestions.push({ code: p.code, name: p.name, why: 'similar code' });
        }
      }
      return {
        error: 'unknown_party',
        detail: `"${code}" is not a party code on the site. The site returns zero hits for unknown codes without any error, so this was stopped locally.`,
        suggestions: suggestions.slice(0, 8),
      };
    }

    async function parties(query = '') {
      const list = await loadParties();
      if (list.error) return list;
      const q = norm(query);
      const hits = q ? list.filter((p) => partyMatches(p, q)) : list;
      return fitToPageSize({ total: list.length, shown: hits.length, parties: hits }, (o) => {
        if (o.parties.length <= 20) return false;
        o.parties = o.parties.slice(0, Math.floor(o.parties.length / 2));
        o.shown = o.parties.length;
        o.truncated = true;
        return true;
      });
    }

    // For saving as data/parties.json — compact, one object per code.
    async function partiesDump() {
      const list = await loadParties({ force: true });
      if (list.error) return list;
      const key = 'parties.json';
      cache.texts[key] = JSON.stringify(list, null, 1);
      return { key, total: cache.texts[key].length, pages: Math.ceil(cache.texts[key].length / PAGE_SIZE), count: list.length, note: 'read with page(key, n)' };
    }

    // --- search -----------------------------------------------------------

    function buildSearchUrl({ parties: codes = [], title = '', dateType = 'signature', from = null, to = null, sort = null, lang = 'en' } = {}) {
      const q = new URLSearchParams();
      q.set('DoSearch', 'true');
      for (const c of codes) q.append('Parties', c);
      if (title) q.set('Title', title);
      const f = toSiteDate(from, false);
      const t = toSiteDate(to, true);
      if (f || t) {
        q.set('DateType', dateType);
        q.set('DateFrom', f || '01/01/0001');
        q.set('DateTo', t || '01/01/0001');
      }
      if (sort) q.set('SortOrder', sort);
      q.set('Lang', lang);
      return SEARCH_URL + '?' + q.toString();
    }

    const ID_IN_HREF = /agreement\/?\?(?:[^#]*&)?id=(\d{7})/i;

    // Find the smallest ancestor of `a` that contains no other agreement link
    // — that is the result row/card, whatever element the site uses.
    function resultItemFor(a, allAnchors) {
      const myId = (a.getAttribute('href').match(ID_IN_HREF) || [])[1];
      const idOf = (x) => (x.getAttribute('href').match(ID_IN_HREF) || [])[1];
      let node = a;
      while (node.parentElement) {
        const parent = node.parentElement;
        // Links to the same agreement (title + "details") belong to this row.
        const inside = allAnchors.filter((x) => parent.contains(x) && idOf(x) !== myId);
        if (inside.length > 0) break;
        node = parent;
      }
      return node;
    }

    // The page has a dedicated `<strong class="gsc-u-results-count">101
    // results</strong>`. The text fallback is deliberately narrow: "N
    // results" only — "agreement(s)" begins most titles, and a loose pattern
    // once returned a signature year as the count.
    function parseResultCount(doc) {
      const el = doc.querySelector('.gsc-u-results-count');
      const text = el ? norm(el.textContent) : ((doc.body && norm(doc.body.textContent)) || norm(doc.documentElement.textContent));
      const m = text.match(/(\d[\d.,\s\u00a0]*)\s*results?/i);
      if (!m) return null;
      const n = parseInt(m[1].replace(/[^\d]/g, ''), 10);
      return Number.isFinite(n) ? n : null;
    }

    // Rows carry `<p>Signature: <time datetime="3/26/2026 12:00:00 AM">
    // 26/03/2026</time></p>` — the attribute is US M/D/YYYY, the text
    // DD/MM/YYYY. Prefer the attribute, fall back to the text.
    function timeToIso(t) {
      const dt = t.getAttribute('datetime') || '';
      let m = dt.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
      if (m && m[3] !== '0001') return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
      m = dt.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (m) return `${m[1]}-${m[2]}-${m[3]}`;
      return toIso(t.textContent);
    }

    function parseRowDates(item) {
      let sig = null, eif = null;
      const times = Array.from(item.querySelectorAll('time'));
      for (const t of times) {
        const label = norm((t.parentElement || item).textContent);
        if (/entry into force/i.test(label)) eif = eif || timeToIso(t);
        else if (/signature/i.test(label)) sig = sig || timeToIso(t);
      }
      if (times.length === 0) {
        const itemText = norm(item.textContent);
        const ms = itemText.match(/Signature\D{0,20}(\d{1,2}\/\d{1,2}\/\d{4})/i);
        const me = itemText.match(/Entry into force\D{0,20}(\d{1,2}\/\d{1,2}\/\d{4})/i);
        if (ms) sig = toIso(ms[1]);
        if (me) eif = toIso(me[1]);
      }
      return { sig, eif };
    }

    function parseResults(doc) {
      // `a[href*="agreement"]` would also match the language-switcher links
      // (the path contains "treaties-agreements"); the id regex is what counts.
      const anchors = Array.from(doc.querySelectorAll('a[href*="/agreement/"]')).filter((a) => ID_IN_HREF.test(a.getAttribute('href') || ''));
      const byId = new Map();
      for (const a of anchors) {
        const id = (a.getAttribute('href').match(ID_IN_HREF) || [])[1];
        const item = resultItemFor(a, anchors);
        const title = norm(a.textContent);
        const { sig, eif } = parseRowDates(item);
        const prev = byId.get(id);
        if (!prev || title.length > prev.title.length) {
          byId.set(id, {
            id,
            title: title || (prev && prev.title) || '',
            signature: sig || (prev && prev.signature) || null,
            entry_into_force: eif || (prev && prev.entry_into_force) || null,
            is_proces_verbal: PV_RE.test(title),
          });
        }
      }
      return { results: Array.from(byId.values()), site_total: parseResultCount(doc) };
    }

    function sortResults(results, sort) {
      const key = /EIF/i.test(sort || '') ? 'entry_into_force' : 'signature';
      const desc = /^L/i.test(sort || 'LSF');
      // Missing dates (8% of NO agreements) always go last, whatever the order.
      return results.slice().sort((a, b) => {
        const x = a[key], y = b[key];
        if (!x && !y) return 0;
        if (!x) return 1;
        if (!y) return -1;
        return desc ? y.localeCompare(x) : x.localeCompare(y);
      });
    }

    function searchSummary(key) {
      const entry = cache.searches[key];
      const out = { key, ...entry.meta, total: entry.results.length, shown: 0, results: [], note: 'more with items(key, offset)' };
      const results = entry.results;
      let n = Math.min(results.length, 60);
      for (;;) {
        out.results = results.slice(0, n);
        out.shown = n;
        if (JSON.stringify(out).length <= PAGE_SIZE || n <= 5) break;
        n = Math.floor(n / 2);
      }
      if (out.shown === out.total) delete out.note;
      return out;
    }

    // opts:
    //   parties: ['NO', 'IS']  -> site semantics: OR (union). One request.
    //   all:     ['NO', 'IS']  -> AND (intersection), done locally from one
    //                             request per code. The site has no AND.
    //   title, dateType ('signature'|'eif'), from, to,
    //   sort ('LSF'|'OSF'|'LEIFF'|'OEIFF'), noPV (drop Procès-Verbaux),
    //   literal (accept a code that collides with an ISO trap, e.g. EC =
    //   Ecuador), lang.
    //
    // Dates — verified live 2026-09-16: the site honours DateFrom as a lower
    // bound and SILENTLY IGNORES DateTo (`DateFrom=01/01/2010&DateTo=
    // 31/12/2020` returned agreements signed in 2026). `to` is therefore
    // applied locally here, on the dateType field, and rows without that
    // date are dropped when a range is given (they cannot be placed).
    // DateType=ratification returns 0 rows for everything, like an invalid
    // value; it is refused.
    const DATE_FIELD = { signature: 'signature', eif: 'entry_into_force' };

    async function search(opts = {}) {
      const o = { ...opts };
      const codesOr = Array.isArray(o.parties) ? o.parties : (o.parties ? [o.parties] : []);
      const codesAnd = Array.isArray(o.all) ? o.all : (o.all ? [o.all] : []);
      const resolved = [];
      for (const c of [...codesOr, ...codesAnd]) {
        const r = await resolveParty(c, { literal: !!o.literal });
        if (r.error) return r;
        resolved.push(r.code);
      }
      const orCodes = resolved.slice(0, codesOr.length);
      const andCodes = resolved.slice(codesOr.length);

      const dateType = o.dateType || 'signature';
      if (!DATE_FIELD[dateType]) {
        return { error: 'unsupported_date_type', detail: `dateType must be "signature" or "eif"; "${dateType}" returns zero rows on the site for every query (verified 2026-09-16).` };
      }
      const fromIso = o.from ? toIso(toSiteDate(o.from, false)) : null;
      const toIsoDate = o.to ? toIso(toSiteDate(o.to, true)) : null;
      if ((o.from && !fromIso) || (o.to && !toIsoDate)) {
        return { error: 'bad_date', detail: 'from/to must be YYYY, YYYY-MM-DD or DD/MM/YYYY' };
      }
      // Only DateFrom goes to the site; `to` is enforced locally below.
      const base = { title: o.title || '', dateType, from: o.from || null, to: null, sort: o.sort || null, lang: o.lang || 'en' };
      const urls = [];
      let results, siteTotal = null, semantics;

      if (andCodes.length > 0) {
        semantics = 'AND';
        let acc = null;
        for (const code of andCodes) {
          const url = buildSearchUrl({ ...base, parties: [...orCodes, code] });
          urls.push(url);
          const r = await fetchHtml(url);
          if (r.error) return r;
          const parsed = parseResults(deps.parse(r.html));
          const ids = new Map(parsed.results.map((x) => [x.id, x]));
          acc = acc === null ? ids : new Map([...acc].filter(([id]) => ids.has(id)));
        }
        results = Array.from(acc.values());
      } else {
        semantics = orCodes.length > 1 ? 'OR' : 'single';
        const url = buildSearchUrl({ ...base, parties: orCodes });
        urls.push(url);
        const r = await fetchHtml(url);
        if (r.error) return r;
        const parsed = parseResults(deps.parse(r.html));
        results = parsed.results;
        siteTotal = parsed.site_total;
      }

      const notes = [];
      const field = DATE_FIELD[dateType];
      if (fromIso || toIsoDate) {
        const before = results.length;
        const undated = results.filter((x) => !x[field]).length;
        results = results.filter((x) => x[field] && (!fromIso || x[field] >= fromIso) && (!toIsoDate || x[field] <= toIsoDate));
        if (toIsoDate) notes.push(`"to" applied locally: the site ignores DateTo (${before} → ${results.length} rows).`);
        if (undated) notes.push(`${undated} row(s) without a ${field.replace('_', ' ')} date were excluded by the date filter.`);
      }
      if (o.noPV) {
        const before = results.length;
        results = results.filter((x) => !x.is_proces_verbal);
        if (before !== results.length) notes.push(`${before - results.length} Procès-Verbal row(s) removed locally (noPV); site_total still counts them.`);
      }
      results = sortResults(results, base.sort);

      const key = 'search:' + JSON.stringify({ orCodes, andCodes, ...base, to: toIsoDate, noPV: !!o.noPV });
      cache.searches[key] = {
        meta: {
          semantics,
          parties: orCodes,
          all: andCodes,
          title: base.title || null,
          from: fromIso, to: toIsoDate, dateType: (fromIso || toIsoDate) ? dateType : null,
          sort: base.sort, noPV: !!o.noPV,
          site_total: siteTotal,
          urls,
          notes: notes.length ? notes : undefined,
          warning: semantics === 'OR'
            ? 'Several Parties= values are OR on the site (union, not intersection). Use {all: [...]} for agreements where every listed party is a party.'
            : undefined,
        },
        results,
      };
      return searchSummary(key);
    }

    async function items(key, offset = 0, limit = 100) {
      const entry = cache.searches[key];
      if (!entry) return { error: 'not_cached', detail: 'unknown search key — run search() first' };
      offset = Math.max(0, offset | 0);
      let n = Math.max(1, Math.min(limit | 0, 200));
      let out;
      for (;;) {
        const slice = entry.results.slice(offset, offset + n);
        out = { key, offset, shown: slice.length, total: entry.results.length, next: offset + n < entry.results.length ? offset + n : null, results: slice };
        if (JSON.stringify(out).length <= PAGE_SIZE || n <= 5) break;
        n = Math.floor(n / 2);
      }
      return out;
    }

    // The whole register in one request (~2 400 rows, ~1.6 MB HTML — stays in
    // the page; only slices are returned). Cached for the tab's lifetime.
    async function list({ force = false } = {}) {
      const key = 'list';
      if (!cache.searches[key] || force) {
        const url = buildSearchUrl({});
        const r = await fetchHtml(url);
        if (r.error) return r;
        const parsed = parseResults(deps.parse(r.html));
        cache.searches[key] = { meta: { semantics: 'all', site_total: parsed.site_total, urls: [url] }, results: parsed.results };
      }
      const e = cache.searches[key];
      return { key, total: e.results.length, site_total: e.meta.site_total, note: 'query with find(); browse with items(key, offset)' };
    }

    // Local title search over the cached full list. `pattern` is a JS regex
    // source (case-insensitive) or plain text.
    async function find(pattern, { noPV = false, limit = 60, regex = false } = {}) {
      const l = await list();
      if (l.error) return l;
      let re;
      try {
        re = regex ? new RegExp(pattern, 'i') : new RegExp(String(pattern).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
      } catch (e) {
        return { error: 'bad_regex', detail: String(e.message || e) };
      }
      let hits = cache.searches.list.results.filter((x) => re.test(x.title));
      if (noPV) hits = hits.filter((x) => !x.is_proces_verbal);
      const key = 'find:' + pattern + (noPV ? ':nopv' : '');
      cache.searches[key] = { meta: { semantics: 'local-title', pattern, noPV }, results: hits };
      const out = await items(key, 0, limit);
      return { ...out, note: 'local title match over the full list; party filters need search()' };
    }

    // --- detail page --------------------------------------------------------

    const FIELD_LABELS = {
      entry_into_force: /^entry into force\s*:?$/i,
      signature: /^signature\s*:?$/i,
      oj: /^official journal reference\s*:?$/i,
      observations: /^observations\s*:?$/i,
      ratification: /^ratification details\s*:?$/i,
    };

    // Live layout (gsc-* template): `<div><h2>Label</h2><p>value</p></div>`,
    // so the value is the label's next sibling. Kept generic for other
    // shapes (dt/dd, h3 + div), but never matched inside a table — the
    // ratification table has an "Observations" header cell, and matching it
    // once leaked the table's first rows into `observations`.
    function findFieldValue(doc, re) {
      const candidates = Array.from(doc.querySelectorAll('dt, h2, h3, h4, strong, b, label, span, div, p'));
      for (const el of candidates) {
        if (el.children.length > 2) continue;
        if (el.closest && el.closest('table')) continue;
        if (!re.test(norm(el.textContent))) continue;
        let v = el.nextElementSibling;
        if (!v && el.parentElement) v = el.parentElement.nextElementSibling;
        if (!v && el.parentElement && el.parentElement.parentElement) v = el.parentElement.parentElement.nextElementSibling;
        if (v && !(v.closest && v.closest('table'))) return v;
      }
      return null;
    }

    function parseOjLinks(container) {
      if (!container) return [];
      const out = [];
      for (const a of Array.from(container.querySelectorAll('a[href]'))) {
        const href = a.getAttribute('href');
        const abs = /^https?:/i.test(href) ? href : ORIGIN + href;
        const m = href.match(/uri=OJ:([A-Z]):(\d{4}):(\d+):([A-Z]+)/i) || href.match(/uri=(CELEX:[^&]+)/i);
        const ref = { text: norm(a.textContent), url: abs };
        if (m && m[4]) {
          ref.oj = { series: m[1].toUpperCase(), year: m[2], issue: m[3], part: m[4] };
          ref.eurlex_hint = `OJ ${m[1].toUpperCase()} ${m[3]}, ${m[2]} — table of contents at ${abs}; find the agreement's CELEX there and open it with the eurlex skill`;
        } else if (m) {
          ref.celex = m[1].replace(/^CELEX:/i, '');
          ref.eurlex_hint = `CELEX ${ref.celex} — open with the eurlex skill`;
        }
        out.push(ref);
      }
      if (out.length === 0) {
        const t = norm(container.textContent);
        if (t) out.push({ text: t, url: null });
      }
      return out;
    }

    function headerIndex(headers) {
      const idx = {};
      headers.forEach((h, i) => {
        const t = h.toLowerCase();
        if (/^party/.test(t)) idx.party = i;
        else if (/^signature/.test(t)) idx.signature = i;
        else if (/^notification/.test(t)) idx.notification = i;
        else if (/entry into force/.test(t)) idx.eif = i;
        else if (/declaration|reservation/.test(t)) idx.declaration = i;
        else if (/^observation/.test(t)) idx.observations = i;
      });
      return idx;
    }

    // Date cells carry `data-sort-value="20110616000000000"` (empty string
    // when the cell is genuinely empty); prefer it over the visible text.
    function cellDate(cell) {
      if (!cell) return null;
      const sv = cell.getAttribute && cell.getAttribute('data-sort-value');
      if (sv !== null && sv !== undefined) {
        const m = String(sv).match(/^(\d{4})(\d{2})(\d{2})/);
        return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
      }
      return toIso(cell.textContent);
    }

    // The party cell is plain text (`<td><b>Belgium</b></td>`, short names).
    // The only `partyid=` link in a row is the declaration link, present
    // only for parties that filed one — so codes come from `partyIndex`
    // (name → code, built from the search form's party list), with the link
    // as a fallback.
    function parseRatificationTable(doc, agreementDates, partyIndex = null) {
      const tables = Array.from(doc.querySelectorAll('table'));
      for (const table of tables) {
        const rows = Array.from(table.querySelectorAll('tr')).filter((r) => !(r.closest && r.closest('tfoot')));
        if (rows.length < 2) continue;
        const headers = Array.from(rows[0].querySelectorAll('th, td')).map((c) => norm(c.textContent));
        const idx = headerIndex(headers);
        if (idx.party === undefined) continue;
        const parties = [];
        for (const row of rows.slice(1)) {
          const cells = Array.from(row.querySelectorAll('td, th'));
          if (cells.length < 2) continue;
          const cellText = (i) => (i === undefined || !cells[i] ? '' : norm(cells[i].textContent));
          const partyCell = cells[idx.party];
          const partyLink = partyCell && partyCell.querySelector('a[href*="partyid="]');
          const declCell = idx.declaration !== undefined ? cells[idx.declaration] : null;
          const declLink = (declCell && declCell.querySelector('a[href*="ratification"]')) || (row.querySelector && row.querySelector('a[href*="ratification"]'));
          const codeFromLink = (a) => {
            if (!a) return null;
            const m = (a.getAttribute('href') || '').match(/partyid=([^&]+)/i);
            return m ? decodeURIComponent(m[1]) : null;
          };
          const name = cellText(idx.party);
          const code = codeFromLink(partyLink) || codeFromLink(declLink) || (partyIndex && partyIndex.get(name.toLowerCase())) || null;
          const sig = idx.signature === undefined ? null : cellDate(cells[idx.signature]);
          const notif = idx.notification === undefined ? null : cellDate(cells[idx.notification]);
          const eif = idx.eif === undefined ? null : cellDate(cells[idx.eif]);
          parties.push({
            name,
            code,
            signature: sig,
            // Footnote on the site: an empty Signature / EIF cell means the
            // agreement-level date applies (except for acceding parties).
            // The flag marks the empty cell; `inherited_*` carries the
            // agreement-level value, which may itself be null (e.g. 2011036,
            // where the page has no agreement-level dates at all).
            signature_inherited: !sig,
            inherited_signature: !sig ? agreementDates.signature : undefined,
            notification: notif,
            entry_into_force: eif,
            entry_into_force_inherited: !eif,
            inherited_entry_into_force: !eif ? agreementDates.entry_into_force : undefined,
            has_declaration: !!declLink,
            declaration_url: declLink ? (/^https?:/i.test(declLink.getAttribute('href')) ? declLink.getAttribute('href') : ORIGIN + declLink.getAttribute('href')) : null,
            observations: cellText(idx.observations) || null,
          });
        }
        const foot = norm((table.parentElement || doc.body || doc.documentElement).textContent).match(/\*\s*When no dates are specified[^.]*\./i);
        return { headers, parties, footnote: foot ? foot[0] : null };
      }
      return { headers: [], parties: [], footnote: null };
    }

    function parseDetail(doc, id, partyIndex = null) {
      const h1 = doc.querySelector('h1');
      const title = norm(h1 ? h1.textContent : (doc.title || ''));
      const eifEl = findFieldValue(doc, FIELD_LABELS.entry_into_force);
      const sigEl = findFieldValue(doc, FIELD_LABELS.signature);
      const ojEl = findFieldValue(doc, FIELD_LABELS.oj);
      const obsEl = findFieldValue(doc, FIELD_LABELS.observations);
      const sigText = norm(sigEl ? sigEl.textContent : '');
      const sigDate = toIso(sigText);
      const sigPlace = sigText.replace(/\d{1,2}\/\d{1,2}\/\d{4}/, '').replace(/^[\s,;:–-]+|[\s,;:–-]+$/g, '') || null;
      const dates = { signature: sigDate, entry_into_force: toIso(eifEl ? eifEl.textContent : '') };
      const table = parseRatificationTable(doc, dates, partyIndex);
      return {
        id,
        title,
        is_proces_verbal: PV_RE.test(title),
        signature: dates.signature,
        signature_place: sigPlace,
        entry_into_force: dates.entry_into_force,
        oj_references: parseOjLinks(ojEl),
        observations: norm(obsEl ? obsEl.textContent : '') || null,
        parties: table.parties,
        party_codes: table.parties.map((p) => p.code).filter(Boolean),
        parties_without_code: table.parties.filter((p) => !p.code).map((p) => p.name),
        ratification_footnote: table.footnote,
        url: `${DETAIL_URL}?id=${id}&docLanguage=en`,
        caveats: [
          'The 7-digit ID is an opaque registration key — its year prefix is NOT the signature year (wrong in ~25% of cases).',
          'Empty Signature/EIF cells in the ratification table inherit the agreement-level dates; they do not mean "not ratified".',
          'One Consilium record can cover several instruments that national registers list separately.',
        ],
      };
    }

    async function detail(id, lang = 'en') {
      id = norm(id);
      if (!/^\d{7}$/.test(id)) return { error: 'bad_id', detail: 'agreement IDs are exactly 7 digits, e.g. 2016032' };
      const cacheKey = `${id}:${lang}`;
      if (cache.details[cacheKey]) return fitDetail(cache.details[cacheKey]);
      const url = `${DETAIL_URL}?id=${id}&docLanguage=${encodeURIComponent(lang)}`;
      const r = await fetchHtml(url);
      if (r.error) return r;
      const plist = await loadParties();
      const d = parseDetail(deps.parse(r.html), id, plist.error ? null : partyIndexOf(plist));
      d.url = url;
      if (!d.title && d.parties.length === 0) return { error: 'not_found', detail: 'no title and no ratification table on the page', url };
      cache.details[cacheKey] = d;
      return fitDetail(d);
    }

    function fitDetail(d) {
      const copy = JSON.parse(JSON.stringify(d));
      return fitToPageSize(copy, (o) => {
        if (o.observations && o.observations.length > 2000) { o.observations = o.observations.slice(0, 2000) + ' …[truncated]'; return true; }
        if (o.parties.length > 10) { o.parties_truncated_from = o.parties.length; o.parties = o.parties.slice(0, Math.floor(o.parties.length / 2)); return true; }
        return false;
      });
    }

    // Several detail pages, politely: limited concurrency, small delay.
    // Returns compact rows; full objects stay in cache.details.
    async function details(ids, lang = 'en', { concurrency = 3, delayMs = 400 } = {}) {
      const queue = ids.slice();
      const rows = [];
      let firstError = null;
      async function worker() {
        while (queue.length && !firstError) {
          const id = queue.shift();
          const d = await detail(id, lang);
          if (d.error) { if (d.error === 'challenge') firstError = d; rows.push({ id, error: d.error }); continue; }
          rows.push({ id, title: d.title, signature: d.signature, entry_into_force: d.entry_into_force, party_codes: d.party_codes, declarations: d.parties.filter((p) => p.has_declaration).map((p) => p.code || p.name) });
          await new Promise((r) => setTimeout(r, delayMs));
        }
      }
      await Promise.all(Array.from({ length: Math.max(1, concurrency) }, worker));
      if (firstError) return { ...firstError, partial: rows };
      const key = 'details:' + ids.join(',');
      cache.searches[key] = { meta: { semantics: 'details' }, results: rows };
      return items(key, 0, 100);
    }

    // --- declarations / reservations ---------------------------------------

    function mainText(doc) {
      const pick = ['main', '#main', '[role="main"]', '.main-content', 'article', 'body'];
      let el = null;
      for (const s of pick) { el = doc.querySelector(s); if (el) break; }
      if (!el) return '';
      const clone = el.cloneNode(true);
      for (const junk of Array.from(clone.querySelectorAll('script, style, nav, header, footer, noscript, svg, iframe, form'))) junk.remove();
      return clone.textContent.replace(/[ \t ]+/g, ' ').replace(/\s*\n\s*/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
    }

    async function declaration(id, party, lang = 'en') {
      id = norm(id);
      if (!/^\d{7}$/.test(id)) return { error: 'bad_id', detail: 'agreement IDs are exactly 7 digits' };
      const p = await resolveParty(party);
      if (p.error) return p;
      // Note the casing: docLanguage on the agreement page, doclanguage here.
      const url = `${RATIFICATION_URL}?id=${id}&partyid=${encodeURIComponent(p.code)}&doclanguage=${encodeURIComponent(lang)}`;
      const r = await fetchHtml(url);
      if (r.error) return r;
      const doc = deps.parse(r.html);
      const text = mainText(doc);
      const key = `declaration:${id}:${p.code}:${lang}`;
      cache.texts[key] = text;
      const h1 = doc.querySelector('h1');
      return {
        key, id, party: p.code, party_name: p.name, url,
        title: norm(h1 ? h1.textContent : doc.title),
        total: text.length,
        text: text.slice(0, PAGE_SIZE - 600),
        truncated: text.length > PAGE_SIZE - 600,
        note: text.length > PAGE_SIZE - 600 ? 'continue with page(key, 1)' : undefined,
      };
    }

    // --- paging over cached texts ---------------------------------------

    async function page(key, n = 0) {
      const text = cache.texts[key];
      if (text === undefined) return { error: 'not_cached', detail: `no text under key "${key}"`, keys: Object.keys(cache.texts) };
      const size = PAGE_SIZE - 400;
      const pages = Math.ceil(text.length / size) || 1;
      n = Math.max(0, Math.min(n | 0, pages - 1));
      return { key, page: n, pages, total: text.length, text: text.slice(n * size, (n + 1) * size) };
    }

    // --- fixture capture (maintainer use) ----------------------------------

    // Returns a trimmed copy of a page's main container as HTML, in PAGE_SIZE
    // slices, so the maintainer can save fixtures for parser tests without
    // pushing site chrome through the tool channel. `selector` overrides the
    // container guess. With no url, captures the current document.
    async function capture(url = null, { selector = null } = {}) {
      let doc, title;
      if (url) {
        const r = await fetchHtml(url);
        if (r.error) return r;
        doc = deps.parse(r.html);
        title = norm(doc.title);
      } else {
        doc = deps.currentDocument();
        url = deps.location() ? deps.location().href : null;
        title = norm(doc.title);
      }
      const guesses = selector ? [selector] : ['main', '#main', '[role="main"]', '.main-content', '#content', 'form', 'body'];
      let el = null, used = null;
      for (const s of guesses) { el = doc.querySelector(s); if (el) { used = s; break; } }
      if (!el) return { error: 'no_results_container', detail: 'no container matched', tried: guesses };
      const clone = el.cloneNode(true);
      for (const junk of Array.from(clone.querySelectorAll('script, style, svg, noscript, iframe, img, link, meta, picture, video'))) junk.remove();
      // Drop site chrome only when capturing something bigger than it.
      if (used === 'body') for (const junk of Array.from(clone.querySelectorAll('header, footer, nav'))) junk.remove();
      // Do NOT collapse whitespace between elements: it changes textContent
      // ("101 results" + "Sorted by" → "101 resultsSorted by") and made a
      // fixture behave differently from the live page. Comments only.
      let html = clone.outerHTML.replace(/<!--[\s\S]*?-->/g, '');
      html = `<!-- captured ${new Date().toISOString()} from ${url} selector=${used} title=${JSON.stringify(title)} -->\n` + html;
      const key = 'capture:' + url;
      cache.texts[key] = html;
      return { key, url, title, selector_used: used, total: html.length, pages: Math.ceil(html.length / (PAGE_SIZE - 400)), note: 'read with page(key, n) and append each page to the fixture file' };
    }

    async function ready() {
      const doc = deps.currentDocument();
      const loc = deps.location();
      if (!doc || !loc) return { error: 'wrong_origin', detail: 'no document' };
      if (!/consilium\.europa\.eu$/i.test(loc.hostname)) return { error: 'wrong_origin', detail: `tab is on ${loc.hostname}; park it on ${SEARCH_URL}` };
      if (/Just a moment|Browser check/i.test(doc.title) || doc.querySelector('#challenge-error-text')) {
        return { error: 'challenge', detail: 'The tab is showing the Cloudflare browser check. Wait a few seconds for it to pass (or ask the user to reload the tab), then call ready() again.' };
      }
      const p = await loadParties();
      if (p.error) return p;
      return { ok: true, url: loc.href, parties: p.length, page_title: norm(doc.title), searchUrl: SEARCH_URL };
    }

    return {
      PAGE_SIZE,
      cache,
      ready,
      parties,
      partiesDump,
      resolveParty,
      search,
      items,
      list,
      find,
      detail,
      details,
      declaration,
      page,
      capture,
      buildSearchUrl,
      // exposed for unit tests / debugging only:
      _deps: deps,
      _internal: { parsePartyList, splitLabel, partyIndexOf, partyMatches, parseResults, parseResultCount, parseDetail, parseRatificationTable, parseOjLinks, mainText, toIso, toSiteDate, isChallengeHtml, sortResults },
    };
  })();

  if (root.window) root.window.__cs = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
