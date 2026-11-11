// Lovdata Pro in-page helper — paste into javascript_tool once per tab.
//
// Idempotent: re-pasting is a no-op if the same version of window.__lp
// already exists (see HELPER_VERSION below). All
// functions are async and return plain JSON-serialisable objects (this is
// what javascript_tool returns to the caller — no DOM nodes, no functions).
//
// Keep this tab parked on Lovdata Pro Klassisk (https://lovdata.no/pro/,
// opened as https://lovdata.no/pro/?forceFullVersion=true) and never navigate it
// away — window.__lp.cache dies on navigation, and every load()/section()/
// grep() after the first for a given path reuses the cached parsed
// Document instead of re-fetching.
//
// Error convention: functions never throw to the caller. They return
// {error: 'not_logged_in' | 'not_found' | 'collection_mismatch' | 'cors' | 'wrong_site' | 'http_<n>', detail}.

// HELPER_VERSION follows the plugin version and changes whenever this file
// does (bump it by hand; CI checks it). A helper of another
// version already in the tab — pasted before a skill update — is replaced,
// dropping its cache; the same version is left alone.
(() => {
  const HELPER_VERSION = '1.3.1';
  if (window.__lp && window.__lp.VERSION === HELPER_VERSION) return;
  window.__lp = (() => {
    // javascript_tool errors above ~49-50K raw characters ("result exceeds
    // maximum allowed tokens") rather than truncating silently — measured
    // empirically (spikes/README.md #1). 45000 leaves headroom for the
    // tool's own wrapper text and for JSON-escaping expansion of special
    // characters (Norwegian letters, embedded quotes).
    const PAGE_SIZE = 45000;

    // Every function below keeps its whole JSON result under PAGE_SIZE, not
    // just its main text field: newlines and quotes double in size when
    // JSON-escaped, and a big toc or many grep hits add up the same way.
    const jsonLen = (v) => JSON.stringify(v).length;

    // --- meter -----------------------------------------------------------------
    // Counts, per public function, the calls and the characters returned to
    // the conversation (JSON, as javascript_tool sends it), plus every
    // network fetch's time and size. The same meter on both backends, for
    // the default-site comparison (docs/lovdata-pro-default-test.md).
    // __lp.stats() reads it; __lp.stats({ reset: true }) reads and zeroes it.
    const meter = { since: Date.now(), calls: {}, returnedChars: 0, fetches: 0, fetchMs: 0, fetchBytes: 0 };

    function metered(name, fn) {
      return async (...args) => {
        const t0 = Date.now();
        const out = await fn(...args);
        const m = meter.calls[name] || (meter.calls[name] = { n: 0, chars: 0, ms: 0 });
        let len = 0;
        try { len = jsonLen(out === undefined ? null : out); } catch (e) { /* not serialisable */ }
        m.n += 1; m.chars += len; m.ms += Date.now() - t0;
        meter.returnedChars += len;
        return out;
      };
    }

    async function meteredFetch(url, init) {
      const t0 = Date.now();
      const res = await fetch(url, init);
      const text = await res.text();
      meter.fetches += 1; meter.fetchMs += Date.now() - t0; meter.fetchBytes += text.length;
      return { status: res.status, text };
    }

    function stats({ reset = false } = {}) {
      const out = { ...meter, calls: JSON.parse(JSON.stringify(meter.calls)), site: (backend() || {}).kind || null, ms: Date.now() - meter.since };
      if (reset) Object.assign(meter, { since: Date.now(), calls: {}, returnedChars: 0, fetches: 0, fetchMs: 0, fetchBytes: 0 });
      return out;
    }

    // Longest slice of text from `offset` (at most `size` chars) whose JSON
    // encoding fits in `budget`. An escaped char costs at least 2, so cutting
    // the overshoot converges in a few rounds.
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

    // As many toc entries from `start` as fit in `budget`; next is null when
    // the rest of the toc fitted.
    function fitToc(toc, start, budget) {
      const items = [];
      let used = 2;
      for (let k = start; k < toc.length; k++) {
        const len = jsonLen(toc[k]) + 1;
        if (used + len > budget) return { items, next: k };
        items.push(toc[k]);
        used += len;
      }
      return { items, next: null };
    }

    // --- login detection --------------------------------------------------
    // #myPage is present in location.hash in BOTH the logged-in and
    // logged-out states (Lovdata swaps rendered content client-side without
    // changing the hash) — confirmed empirically, spikes/README.md #2. Only
    // document.title distinguishes them: "Min side - Lovdata Pro" vs bare
    // "Lovdata".
    //
    // The title check is only meaningful while the tab shows #myPage. On a
    // reused tab that is parked on a document view, document.title is the
    // document's title, so we fall back to a probe: fetch a small known
    // document and classify the response (real document = logged in, login
    // redirect = logged out). One 42 KB request; result is not cached
    // because the session can expire between turns.
    const PROBE_PATH = 'LGSIV/avgjorelse/lg-2008-135938';

    // --- which Lovdata Pro this tab is on ----------------------------------
    // Two backends behind the same functions:
    // - 'klassisk': the GWT app at lovdata.no/pro ("Lovdata Pro Klassisk"
    //   from 2026-11-26), HTML documents and the Hurtigsøk field.
    // - 'pro2': the new Lovdata Pro, an Elm app over a JSON API, at
    //   pro2.lovdata.no (docs/lovdata-pro2.md). Its bundle also names
    //   https://lovdata.no/pro/api as an API base, so after the switch the
    //   new app may be served from lovdata.no/pro as well; it is told from
    //   Klassisk there by its Vite bundle (<script src=".../assets/index-…">).
    const KLASSISK_URL = 'https://lovdata.no/pro/?forceFullVersion=true';
    const PRO2_URL = 'https://pro2.lovdata.no/';

    function backend() {
      const host = location.hostname;
      if (!host) return { kind: 'klassisk' }; // unit-test stubs
      if (host === 'pro2.lovdata.no') return { kind: 'pro2', api: `${location.origin}/api` };
      if (host === 'lovdata.no') {
        const vite = document.querySelector && document.querySelector('script[src*="/assets/index-"]');
        return vite ? { kind: 'pro2', api: 'https://lovdata.no/pro/api' } : { kind: 'klassisk' };
      }
      return null;
    }

    function wrongSite() {
      if (backend()) return null;
      return { error: 'wrong_site', host: location.hostname,
               detail: `this helper works on Lovdata Pro (${PRO2_URL}) or Lovdata Pro Klassisk (${KLASSISK_URL}); navigate the tab there and paste the helper again` };
    }

    const isPro2 = () => { const b = backend(); return !!b && b.kind === 'pro2'; };

    // --- pro2: JSON API -----------------------------------------------------
    // Read-only calls only: auth/user, checkDocument, references,
    // documentContent, documentMeta and search. Never breadcrumbs (that
    // writes the user's Smulesti) and never Lovdata's KI services
    // (ai-search, ai-chat, reference-preview): their rules forbid automated
    // queries (docs/lovdata-pro-terms.md).
    async function api(path, init) {
      try {
        const res = await meteredFetch(`${backend().api}/${path}`, { credentials: 'include', ...init });
        const { text } = res;
        let json = null;
        try { json = JSON.parse(text); } catch (e) { /* not JSON */ }
        return { status: res.status, json };
      } catch (e) {
        return { status: 0, json: null, fetchError: String(e && e.message || e) };
      }
    }

    const encPath = (p) => p.split('/').map(encodeURIComponent).join('/');
    const uriPath = (u) => [u.base, u.type, u.id].join('/');
    const isBase = (s) => /^[A-Z0-9]+$/.test(s);
    const denied = (status) => status === 401 || status === 403;

    async function pro2IsLoggedIn() {
      const r = await api('auth/user?frontendVersion=lovdata-pro-skill');
      if (r.fetchError) return { loggedIn: false, source: 'api', site: 'pro2', error: 'cors', detail: r.fetchError };
      // Only the yes/no leaves the tab: the reply also carries the user's
      // name and e-mail.
      if (r.status === 200 && r.json && r.json.userID != null) return { loggedIn: true, source: 'api', site: 'pro2' };
      return { loggedIn: false, source: 'api', site: 'pro2', detail: `auth/user returned ${r.status}` };
    }

    // Finds the document for a list of candidates. A full path
    // (BASE/type/id) goes to checkDocument, which also answers RedirectTo
    // for the wrong collection (HRSTR for an HRSIV case). A short form
    // without the collection (avgjorelse/rt-2000-1811, the form Lovdata's
    // own links use) goes to references, which resolves Rt./RG citations
    // to the underlying judgment; a full path that checkDocument does not
    // know is retried there too.
    async function pro2Locate(candidates) {
      const tried = [];
      const shorts = [];
      for (const c of candidates) {
        const parts = String(c).split('/').filter(Boolean);
        if (parts.length >= 3 && isBase(parts[0])) {
          const path = parts.slice(0, 3).join('/');
          tried.push(`checkDocument ${path}`);
          const r = await api('checkDocument/' + encPath(path));
          if (r.fetchError) return { error: 'cors', detail: r.fetchError };
          if (denied(r.status)) return { error: 'not_logged_in' };
          const t = r.json && r.json.type;
          if (t === 'Success') return { path, part: parts.slice(3).join('/') || null };
          if (t === 'RedirectTo' && r.json.documentURI) return { path: uriPath(r.json.documentURI), part: r.json.documentURI.part || null, redirectedFrom: path };
          if (t === 'StaticFile') return { error: 'static_file', detail: `${path} is a static file in Lovdata Pro, not a text document`, file: r.json.url || null, fileType: r.json.fileType || null };
          if (t === 'MissingJSON') return { error: 'missing_json', detail: `${path} has no text version in the new Lovdata Pro; try Lovdata Pro Klassisk (${KLASSISK_URL})`, proURL: r.json.proURL || null };
          shorts.push(parts.slice(1).join('/'));
        } else if (parts.length >= 2) {
          shorts.push(parts.join('/'));
        }
      }
      for (const s of [...new Set(shorts)]) {
        tried.push(`references ${s}`);
        const r = await api('references/' + encPath(s));
        if (r.fetchError) return { error: 'cors', detail: r.fetchError };
        if (denied(r.status)) return { error: 'not_logged_in' };
        const hits = Array.isArray(r.json) ? r.json.filter(h => h && h.documentURI) : [];
        if (hits.length) {
          const u = hits[0].documentURI;
          const out = { path: uriPath(u), part: u.part || null, via: `references ${s}` };
          if (hits.length > 1) out.alternatives = hits.slice(1, 6).map(h => uriPath(h.documentURI));
          return out;
        }
      }
      return { error: 'not_found', detail: `tried: ${tried.join('; ')}` };
    }

    // documentContent is JSON-ML: an element is [tag, {attrs}, [children]],
    // a child a string or an element. It is rebuilt as DOM nodes in an inert
    // document (nothing loads, no scripts run), so toText(), buildToc() and
    // section() read it exactly as they read a Klassisk page.
    const isEl = (n) => Array.isArray(n) && n.length === 3 && typeof n[0] === 'string'
      && !!n[1] && typeof n[1] === 'object' && !Array.isArray(n[1]) && Array.isArray(n[2]);

    function jsonmlToDom(doc, node) {
      if (typeof node === 'string') return doc.createTextNode(node);
      if (!isEl(node)) return null;
      const [tag, attrs, kids] = node;
      let el;
      try { el = doc.createElement(tag); } catch (e) { el = doc.createElement('span'); }
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || typeof v === 'object') continue;
        try { el.setAttribute(k, String(v)); } catch (e) { /* attribute name the DOM refuses */ }
      }
      for (const c of kids) {
        const n = jsonmlToDom(doc, c);
        if (n) el.appendChild(n);
      }
      return el;
    }

    // Header field labels as the page shows them, for a <dt> that comes
    // without text (the JSON's own <dt> text wins when there is some).
    const PRO2_META_LABELS = {
      court: 'Instans', dateVerdictPublished: 'Avsagt', publishedLovdata: 'Publisert (Lovdata)', caseNumber: 'Saksnummer',
      keywords: 'Stikkord', summary: 'Sammendrag', proceedings: 'Saksgang', parties: 'Parter', membersOfTheCourt: 'Rettsmedlemmer',
      dateLastUpdated: 'Sist oppdatert', quotedlegislation: 'Sitert regelverk', caseID: 'Dokumentnummer', title: 'Tittel',
      advised: 'Tilrådet', ministry: 'Departement', numberOfPages: 'Antall sider', note: 'Merknad', titleShort: 'Korttittel',
      changestodocuments: 'Foreslåtte endringer',
    };

    function pro2Metadata(header) {
      const meta = {};
      if (!header) return meta;
      for (const dt of header.querySelectorAll('dt')) {
        const dd = dt.nextElementSibling;
        if (!dd || dd.tagName.toLowerCase() !== 'dd') continue;
        const cls = String(dt.getAttribute('class') || '').split(/\s+/)[0];
        const key = inlineText(dt).replace(/\s+/g, ' ').replace(/:$/, '').trim() || PRO2_META_LABELS[cls] || cls;
        const val = inlineText(dd);
        if (key && val) meta[key] = val;
      }
      return meta;
    }

    async function pro2Load(candidates) {
      const loc = await pro2Locate(candidates);
      if (loc.error) return loc;
      const { path } = loc;
      if (cache[path]) return describe(path, cache[path], loc);
      const [content, metaRes] = await Promise.all([
        api('documentContent/' + encPath(path)),
        api('documentMeta/' + encPath(path)),
      ]);
      if (content.fetchError) return { error: 'cors', detail: content.fetchError };
      if (denied(content.status)) return { error: 'not_logged_in' };
      if (content.status === 404) return { error: 'not_found', detail: `${path}: no document content (Karnov comments and other non-document records have none)` };
      if (content.status !== 200 || !content.json) return { error: `http_${content.status}`, detail: `documentContent ${path}` };
      const c = content.json;
      if (c.version !== 1 && c.version !== 2) return { error: 'unsupported_format', detail: `documentContent version ${c.version} for ${path}; the helper knows versions 1 and 2` };
      const doc = new DOMParser().parseFromString('<!doctype html><html><body></body></html>', 'text/html');
      const body = doc.createElement('div');
      body.id = 'documentBody';
      const main = isEl(c.mainTags) ? [c.mainTags] : (Array.isArray(c.mainTags) ? c.mainTags : []);
      for (const n of main) { const el = jsonmlToDom(doc, n); if (el) body.appendChild(el); }
      doc.body.appendChild(body);
      const header = jsonmlToDom(doc, c.header);
      const m = metaRes.status === 200 && metaRes.json ? metaRes.json : {};
      const title = m.title || m.shortTitle || path;
      const metadata = pro2Metadata(header);
      const toc = buildToc(body);
      const fullText = toText(body);
      cache[path] = { doc, body, title, metadata, toc, fullText, site: 'pro2' };
      return describe(path, cache[path], loc);
    }

    // POST /api/search ranks by relevance only when asked to: without
    // sortField/sortOrder an exact reference comes behind Karnov comments.
    // filterBases takes Lovdata's collection or group codes (HRA = all
    // Høyesterett, AVG = all court decisions, LBSIV, NOU, PROP, INNST …).
    // Karnov comments (base COMMENT) and literature are dropped: they are
    // not documents by public bodies, the skill's scope under the terms.
    async function pro2Search(query, n, bases) {
      const body = { offset: 0, term: query, sortField: 'relevance', sortOrder: 'desc', filterBases: bases || [] };
      const r = await api('search?minimal=true', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      if (r.fetchError) return { error: 'cors', detail: r.fetchError };
      if (denied(r.status)) return { error: 'not_logged_in' };
      if (r.status !== 200 || !r.json) return { error: `http_${r.status}`, detail: 'search' };
      const results = [];
      for (const h of r.json.results || []) {
        const u = h.documentURI;
        if (!u || u.base === 'COMMENT' || /^(karnov|litteratur)$/.test(u.type)) continue;
        results.push({ path: uriPath(u), title: (h.documentTitles && h.documentTitles.title) || undefined, date: h.isoDate || undefined });
        if (results.length >= n) break;
      }
      return { query, site: 'pro2', filterBases: body.filterBases, totalHits: r.json.totalHits, results };
    }

    async function isLoggedIn({ probe = true } = {}) {
      const wrong = wrongSite();
      if (wrong) return { loggedIn: false, ...wrong };
      if (isPro2()) return pro2IsLoggedIn();
      const hash = location.hash;
      const title = document.title;
      if (/Min side/i.test(title)) return { loggedIn: true, source: 'title', hash, title };
      if (/^\s*Lovdata\s*$/i.test(title) && /#myPage/.test(hash)) {
        return { loggedIn: false, source: 'title', hash, title };
      }
      if (!probe) return { loggedIn: false, source: 'title', hash, title, detail: 'not on #myPage; pass {probe:true} or navigate to https://lovdata.no/pro/#myPage' };
      const { status, html, fetchError } = await fetchHtml(docUrl(PROBE_PATH));
      if (fetchError) return { loggedIn: false, source: 'probe', hash, title, error: 'cors', detail: fetchError };
      if (status === 200 && looksLikeRealDoc(html)) return { loggedIn: true, source: 'probe', hash, title };
      if (status === 200 && isLoginPage(html)) return { loggedIn: false, source: 'probe', hash, title };
      return { loggedIn: false, source: 'probe', hash, title, detail: `probe returned status ${status}, ${html.length} bytes` };
    }

    // --- fetch + path helpers ----------------------------------------------

    function docUrl(path) {
      return `https://lovdata.no/pro/document/${path}/*`;
    }

    async function fetchHtml(url) {
      try {
        const res = await meteredFetch(url, { credentials: 'include' });
        return { status: res.status, html: res.text };
      } catch (e) {
        return { status: 0, html: '', fetchError: String(e && e.message || e) };
      }
    }

    const NOT_FOUND_TITLE = /feilmelding/i;
    const REDIRECT_STUB_TITLE = /^\s*LovdataPro\s*$/i;
    const JS_REQUIRED_FRAGMENT = 'Javascript aktivert';

    function looksLikeRealDoc(html) {
      if (html.length < 5000) return false;
      const m = html.match(/<title>([^<]+)<\/title>/);
      const title = (m ? m[1] : '').trim();
      if (NOT_FOUND_TITLE.test(title)) return false;
      if (REDIRECT_STUB_TITLE.test(title)) return false;
      // Every rendered Pro document carries one of these containers (see
      // references/lovdata-pro-mapping.md). A small page without either is
      // some shell/landing page, not a document.
      const hasDocContainer = /id="(documentBody|lovdataDocument)"/.test(html);
      if (!hasDocContainer && html.length < 20000) return false;
      return true;
    }

    function isCollectionMismatch(html) {
      return html.includes(JS_REQUIRED_FRAGMENT) && html.length < 500;
    }

    function isLoginPage(html) {
      // A logged-out session gets redirected to a login/SSO page rather
      // than the document. Distinct from collection-mismatch and
      // not-found: neither of those mention innlogging.
      return /logg inn|innlogging|feide|sign in/i.test(html) && html.length < 20000
        && !looksLikeRealDoc(html);
    }

    function swapSivStr(path) {
      const parts = path.split('/');
      if (parts.length < 2) return null;
      const collection = parts[0];
      if (collection.endsWith('SIV')) return collection.slice(0, -3) + 'STR/' + parts.slice(1).join('/');
      if (collection.endsWith('STR')) return collection.slice(0, -3) + 'SIV/' + parts.slice(1).join('/');
      return null;
    }

    async function tryPaths(paths) {
      const wrong = wrongSite();
      if (wrong) return wrong;
      const queue = [...paths];
      const seen = new Set(paths);
      for (let i = 0; i < queue.length; i++) {
        const path = queue[i];
        const { status, html, fetchError } = await fetchHtml(docUrl(path));
        if (fetchError) return { error: 'cors', detail: fetchError };
        if (status === 200 && isLoginPage(html)) return { error: 'not_logged_in' };
        if (status === 200 && looksLikeRealDoc(html)) return { path, html };
        if (isCollectionMismatch(html)) {
          const alt = swapSivStr(path);
          if (alt && !seen.has(alt)) { seen.add(alt); queue.push(alt); }
        }
      }
      return { error: 'not_found', detail: `tried: ${queue.join(', ')}` };
    }

    // --- HTML -> text --------------------------------------------------------

    const NOISE_SELECTORS = '.documentButtonsBar, #textNotes, .commentBubble, .shareLinkButton, .writeNoteButton, script, style';

    function stripNoise(root) {
      root.querySelectorAll(NOISE_SELECTORS).forEach(el => el.remove());
    }

    function documentBody(doc) {
      // #documentBody is the content-only container (see references/lovdata-
      // pro-mapping.md — "DOM — extracting the document body"). This must
      // NOT resolve to #lovdataDocument, which also wraps the separate
      // #documentMeta sidebar/table — including it would leak metadata rows
      // into every section()/page()/grep() call on the body text.
      return doc.querySelector('#documentBody') || doc.querySelector('#lovdataDocument') || doc.body;
    }

    // --- source text (canonical copy: shared/source-text/source_text.js) ---
    // The JavaScript side of shared/source-text/source_text.py, embedded as is
    // in the browser helpers (tests/source-text/test_source_text.js checks the
    // copies and that both give the same results). Emphasis placeholders
    // around <i>/<em> and <b>/<strong> text become *italic* and **bold** in
    // stFinish(); stSuperscript() writes m², 10⁻¹ or ^text^; stMarkLists()
    // writes the numbers the browser draws for an <ol>; ST_SPACES are the
    // non-breaking spaces that become plain spaces; stFold() is the text as
    // search matches it.
    const ST_EM = String.fromCharCode(2); const ST_EM_END = String.fromCharCode(3);
    const ST_STRONG = String.fromCharCode(4); const ST_STRONG_END = String.fromCharCode(5);
    const ST_MARKERS = ST_EM + ST_EM_END + ST_STRONG + ST_STRONG_END;
    const ST_WS = ' \t\r\f\v';
    const ST_SPACES = new RegExp('[' + String.fromCharCode(0xa0, 0x202f) + ']', 'g');
    const ST_SUP = new Map(Array.from('0123456789+-−=()', (c, k) => [c, '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾'[k]]));
    const ST_EMPHASIS = { i: [ST_EM, ST_EM_END], em: [ST_EM, ST_EM_END], b: [ST_STRONG, ST_STRONG_END], strong: [ST_STRONG, ST_STRONG_END] };

    function stMarkEmphasis(html) {
      return html.replace(/<[^>]*>/g, (tag) => {
        const e = /^<(\/?)(i|em|b|strong)(?:\s[^>]*)?>$/i.exec(tag);
        return e ? ST_EMPHASIS[e[2].toLowerCase()][e[1] ? 1 : 0] : tag;
      });
    }

    function stFinish(text) {
      if (!Array.from(ST_MARKERS).some((c) => text.includes(c))) return text;
      const out = []; const opened = []; let ws = [];
      let italic = 0; let bold = 0;
      const closeTo = (target) => {
        let keep = 0;
        while (keep < opened.length && target.has(opened[keep])) keep += 1;
        for (let k = opened.length - 1; k >= keep; k -= 1) out.push(opened[k]);
        opened.length = keep;
      };
      for (const c of text) {
        if (c === ST_EM) { italic += 1; continue; }
        if (c === ST_EM_END) { italic = Math.max(0, italic - 1); continue; }
        if (c === ST_STRONG) { bold += 1; continue; }
        if (c === ST_STRONG_END) { bold = Math.max(0, bold - 1); continue; }
        if (c === '\n') { closeTo(new Set()); out.push(...ws); ws = []; out.push(c); continue; }
        if (ST_WS.includes(c)) { ws.push(c); continue; }
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

    function stPlain(text) {
      return Array.from(text).filter((c) => !ST_MARKERS.includes(c)).join('');
    }

    function stSuperscript(text) {
      const core = text.replace(/^[ \t\r\f\v\n]+|[ \t\r\f\v\n]+$/g, '');
      if (!core) return text;
      const at = text.indexOf(core);
      const lead = text.slice(0, at); const trail = text.slice(at + core.length);
      if (Array.from(core).every((c) => ST_SUP.has(c))) return lead + Array.from(core, (c) => ST_SUP.get(c)).join('') + trail;
      return `${lead}^${core}^${trail}`;
    }

    const ST_ROMAN = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
      [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];
    const ST_STYLE_KIND = { 'lower-alpha': 'a', 'lower-latin': 'a', 'upper-alpha': 'A', 'upper-latin': 'A', 'lower-roman': 'i', 'upper-roman': 'I', decimal: '1' };

    function stListLabel(n, kind) {
      if (kind === 'I' || kind === 'i') {
        let out = '';
        for (const [value, numeral] of ST_ROMAN) {
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

    function stOlKind(attrs) {
      let m = /list-style-type\s*:\s*([a-z-]+)/i.exec(attrs);
      if (m && ST_STYLE_KIND[m[1].toLowerCase()]) return ST_STYLE_KIND[m[1].toLowerCase()];
      m = /\btype\s*=\s*"?([aAiI1])\b/.exec(attrs);
      return m ? m[1] : '1';
    }

    function stMarkLists(html, bullet = '- ') {
      const stack = [];
      return html.replace(/<(\/?)(ol|ul|li)\b([^>]*)>/gi, (tag, closing, name, attrs) => {
        name = name.toLowerCase();
        if (name === 'ol' || name === 'ul') {
          if (closing) stack.pop();
          else if (name === 'ul') stack.push(null);
          else {
            const start = /\bstart\s*=\s*"?(-?\d+)/.exec(attrs);
            stack.push([stOlKind(attrs), start ? Number(start[1]) : 1]);
          }
          return tag;
        }
        if (closing) return tag;
        const top = stack.length ? stack[stack.length - 1] : null;
        if (!top) return tag + '\n' + bullet;
        const value = /\bvalue\s*=\s*"?(-?\d+)/.exec(attrs);
        if (value) top[1] = Number(value[1]);
        const label = stListLabel(top[1], top[0]);
        top[1] += 1;
        return `${tag}\n${label}. `;
      });
    }

    function stFold(text) {
      return text.replace(/\*/g, '').split(String.fromCharCode(0xad)).join('');
    }
    // --- end source text ---

    // Lovdata's footnote markers: <sup class="footnotereference">5</sup> in
    // the text, <span class="footnoteLabel">5</span> on the note. Both are
    // written "[fn 5]" (as in lovdata-api), so a reference pairs with its note.
    function footnoteLabel(n) {
      const cls = String(n.className || '');
      return /\bfootnote(?:reference|Label)\b/.test(cls) ? n.textContent.replace(/\s+/g, ' ').trim() : null;
    }

    // Renders a block element's inline content as the page shows it:
    // *italic* and **bold** kept (part of the text: case names, the Court's
    // emphasis in quotations, bold §-titles in statute text quoted inside
    // forarbeider), nested as Markdown nests them (stFinish); superscript as
    // m² or ^text^; footnote markers as [fn N]. A newline in the markup is a
    // space; <br> becomes a line break (party lists in judgments:
    // "A (advokat X)<br>mot<br>B"). Nested lists are skipped when skipLists
    // is set so toText() can render them as their own lines. emphasis:false
    // gives plain text (headings, which toText() already marks).
    function inlineText(node, opts = {}) {
      return inlineNodes(node.childNodes, opts);
    }

    const hasClass = (n, c) => !!n.getAttribute && new RegExp(`(^|\\s)${c}(\\s|$)`).test(n.getAttribute('class') || '');

    // New Lovdata Pro (pro2) markup, drawn by its CSS rather than tags:
    // span.data-originalId is a list item's drawn label (also in the li's
    // data-name, which listMarker() writes, so the span itself is skipped);
    // a §-title (span.legalArticleTitle) and a figure caption are set in
    // italic, which is part of the text.
    const isListLabel = (n) => hasClass(n, 'data-originalId');
    const cssItalic = (n, tag) => tag === 'figcaption' || hasClass(n, 'legalArticleTitle');
    const isPageNumber = (n) => n.nodeType === 1 && n.tagName.toLowerCase() === 'aside' && hasClass(n, 'pagenumber');

    // A heading's text without the "Side N" page markers set inside it
    // (pro2 floats them to the right); those become their own lines.
    function headingParts(h) {
      const clone = h.cloneNode(true);
      const pages = [];
      for (const a of Array.from(clone.querySelectorAll('aside'))) {
        if (isPageNumber(a)) { pages.push(a.textContent.replace(/\s+/g, ' ').trim()); a.remove(); }
      }
      return { clone, pages: pages.filter(Boolean) };
    }

    function inlineNodes(nodes, { skipLists = false, emphasis = true } = {}) {
      const parts = [];
      const visit = (n) => {
        if (n.nodeType === 3) { parts.push(n.textContent.replace(/[\r\n\t]+/g, ' ').replace(ST_SPACES, ' ')); return; }
        if (n.nodeType !== 1) return;
        const tag = n.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return;
        if (tag === 'br') { parts.push('\n'); return; }
        if (skipLists && (tag === 'ul' || tag === 'ol')) return;
        if (isListLabel(n)) return;
        // A page marker inside inline content (a list item's paragraph) is
        // its own line, as toText() gives it everywhere else.
        if (isPageNumber(n)) { parts.push('\n' + n.textContent.replace(/\s+/g, ' ').trim() + '\n'); return; }
        const fn = footnoteLabel(n);
        if (fn !== null) { parts.push(`[fn ${fn}]`); return; }
        if (tag === 'sup') { parts.push(stSuperscript(inlineText(n, { skipLists, emphasis: false }))); return; }
        const mark = emphasis ? (ST_EMPHASIS[tag] || (cssItalic(n, tag) ? ST_EMPHASIS.i : null)) : null;
        if (mark) parts.push(mark[0]);
        for (const child of n.childNodes) visit(child);
        if (mark) parts.push(mark[1]);
      };
      for (const child of nodes) visit(child);
      return stFinish(parts.join(''))
        .split('\n')
        .map(s => s.replace(/[ \t\r\f\v]+/g, ' ').trim())
        .filter(Boolean)
        .join('\n');
    }

    const BLOCK_TAGS = new Set(['address', 'article', 'aside', 'blockquote', 'dd', 'div', 'dl', 'dt', 'figure', 'footer', 'form',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'ul',
      'script', 'style']);

    // The marker the page draws before a list item: Lovdata's own label
    // (data-name="a."), else the number of an <ol> item, else "- ".
    function listMarker(li) {
      const name = li.getAttribute && li.getAttribute('data-name');
      // pro2 sets some labels in italic (data-list-id-style="i").
      if (name) return li.getAttribute('data-list-id-style') === 'i' ? `*${name}* ` : name + ' ';
      const list = li.parentElement;
      if (!list || list.tagName.toLowerCase() !== 'ol') return '- ';
      let n = Number(list.getAttribute('start') || 1);
      for (const sib of list.children) {
        if (sib.tagName.toLowerCase() !== 'li') continue;
        const v = sib.getAttribute('value');
        if (v !== null) n = Number(v);
        if (sib === li) break;
        n += 1;
      }
      const kind = stOlKind(` type="${list.getAttribute('type') || ''}" style="${list.getAttribute('style') || ''}"`);
      return stListLabel(n, kind) + '. ';
    }

    function toText(el) {
      if (!el) return '';
      const lines = [];
      const walk = (node) => {
        if (node.nodeType === 3) { // text node
          const t = node.textContent.replace(ST_SPACES, ' ').replace(/[ \t\r\n\f\v]+/g, ' ').trim();
          if (t) lines.push(t);
          return;
        }
        if (node.nodeType !== 1) return;
        const tag = node.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return;
        if (/^h[1-6]$/.test(tag)) {
          const level = Number(tag[1]);
          const { clone, pages } = headingParts(node);
          lines.push('#'.repeat(level) + ' ' + inlineText(clone, { emphasis: false }).replace(/\n/g, ' '));
          lines.push(...pages);
          return;
        }
        // pro2 judgments: a numbered paragraph is drawn as one row, the
        // "(77)" label (span.verdictNumberedPId) and then the paragraph.
        // Written "(77) text" on one line; Klassisk's table layout gave
        // "| (77) |" instead, and grep "(77)" finds both.
        if (hasClass(node, 'verdictNumberedP')) {
          const clone = node.cloneNode(true);
          const label = Array.from(clone.children).find(ch => hasClass(ch, 'verdictNumberedPId'));
          const num = label ? label.textContent.replace(/\s+/g, ' ').trim() : '';
          if (label) label.remove();
          clone.removeAttribute('class');
          const rest = toText(clone);
          lines.push(num && rest ? `${num} ${rest}` : (num || rest));
          return;
        }
        if (tag === 'table') {
          // Lovdata does not use <ul>/<li> for legal sub-lists. Litra and
          // numbered points are one-row tables, class "listeItem", with a
          // leftMargin_N class carrying the depth (confirmed live 2026-09).
          // Render those as indented "a. text" lines rather than pipe rows,
          // so "annet ledd bokstav b" stays quotable and locatable.
          const cls = String(node.className || '');
          const isListItem = /\blisteItem\b/.test(cls) || !!node.querySelector('tr.listeItem, td.listeItem');
          if (isListItem) {
            const depthEl = /leftMargin_\d/.test(cls) ? node : node.querySelector('[class*="leftMargin_"]');
            const dm = String((depthEl && depthEl.className) || '').match(/leftMargin_(\d+)/);
            const indent = '  '.repeat(Math.max(0, (dm ? Number(dm[1]) : 1) - 1));
            for (const tr of node.querySelectorAll('tr')) {
              const cells = Array.from(tr.querySelectorAll('th, td')).map(inlineText).filter(Boolean);
              if (cells.length) lines.push(indent + cells.join(' '));
            }
            return;
          }
          for (const tr of node.querySelectorAll('tr')) {
            const cells = Array.from(tr.querySelectorAll('th, td')).map(inlineText);
            if (cells.some(c => c)) lines.push('| ' + cells.join(' | ') + ' |');
          }
          return;
        }
        if (tag === 'li') {
          const own = inlineText(node, { skipLists: true });
          if (own) lines.push(listMarker(node) + own);
          // Nested lists become their own indented lines.
          for (const sub of node.querySelectorAll(':scope > ul, :scope > ol')) {
            for (const li of sub.querySelectorAll(':scope > li')) {
              const sublines = toText(li);
              if (sublines) lines.push(sublines.split('\n').map(l => '  ' + l).join('\n'));
            }
          }
          return;
        }
        if (tag === 'p') {
          const t = inlineText(node);
          if (t) lines.push(t);
          return;
        }
        // Inline content directly in a block (text, <i>, <a> … in a <div>)
        // is one line, rendered like a paragraph; block children are walked.
        const run = [];
        const flushRun = () => {
          const t = run.length ? inlineNodes(run) : '';
          if (t) lines.push(t);
          run.length = 0;
        };
        for (const child of node.childNodes) {
          if (child.nodeType === 1 && BLOCK_TAGS.has(child.tagName.toLowerCase())) { flushRun(); walk(child); }
          else run.push(child);
        }
        flushRun();
      };
      walk(el);
      return lines.filter(Boolean).join('\n');
    }

    function extractMetadata(doc) {
      const meta = {};
      const metaRoot = doc.querySelector('#documentMeta') || doc.querySelector('#documentBody') || doc;
      for (const table of metaRoot.querySelectorAll('table')) {
        const rows = [];
        for (const tr of table.querySelectorAll('tr')) {
          const cells = Array.from(tr.querySelectorAll('th, td'));
          if (cells.length < 2) continue;
          // inlineText, not textContent: the Parter row separates each party
          // and its counsel with <br>, which textContent would run together
          // ("(partshjelper).Møter etter tvl. § 30-13").
          const key = inlineText(cells[0]).replace(/\s+/g, ' ').trim();
          const val = inlineText(cells[1]);
          if (key && val) rows.push([key, val]);
        }
        if (rows.length >= 3 && rows.every(([k]) => k.length <= 40)) {
          for (const [k, v] of rows) meta[k] = v;
          return meta;
        }
      }
      return meta;
    }

    // A heading's section runs from itself to the next heading of
    // same-or-higher level, wherever that falls in the DOM — headings are
    // not reliably direct children of `body` (a subsection's <h3> often
    // sits inside the same wrapper div as its parent <h2>, not as a
    // sibling top-level div). Range boundary points can straddle any
    // depth, so use the native Range API instead of walking siblings.
    function headingRange(body, headings, toc, index) {
      const heading = headings[index];
      if (!heading) return null;
      const entry = toc[index];
      let nextHeading = null;
      for (let j = index + 1; j < toc.length; j++) {
        if (toc[j].level <= entry.level) { nextHeading = headings[j]; break; }
      }
      const range = body.ownerDocument.createRange();
      range.setStartBefore(heading);
      if (nextHeading) {
        range.setEndBefore(nextHeading);
      } else {
        range.setEnd(body, body.childNodes.length);
      }
      return range;
    }

    function buildToc(body) {
      const headings = Array.from(body.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      const toc = headings.map((h, i) => ({
        i,
        id: h.closest('[id]') ? h.closest('[id]').id : (h.id || null),
        level: Number(h.tagName[1]),
        title: headingParts(h).clone.textContent.replace(/\s+/g, ' ').trim(),
      }));
      // Chars per section via Range.toString(): one linear pass per
      // section. (The earlier version summed textContent over every node
      // in the section, which is quadratic and took tens of seconds on a
      // multi-MB NOU.)
      // A DOM without full Range support (the test DOM) gets chars: null
      // rather than no ToC.
      toc.forEach((entry, idx) => {
        try {
          const range = headingRange(body, headings, toc, idx);
          entry.chars = range ? range.toString().length : 0;
        } catch (e) {
          entry.chars = null;
        }
      });
      return toc;
    }

    function sectionRange(body, toc, index) {
      const headings = Array.from(body.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      const range = headingRange(body, headings, toc, index);
      if (!range) return null;
      const container = document.createElement('div');
      container.appendChild(range.cloneContents());
      return container;
    }

    // --- cache ---------------------------------------------------------------

    const cache = {}; // path -> { doc, body, title, metadata, toc, fullText }

    function parseDoc(html) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      stripNoise(doc);
      return doc;
    }

    function titleOf(html, doc) {
      const m = html.match(/<title>([^<]+)<\/title>/);
      return m ? m[1].trim() : (doc.title || null);
    }

    // --- public API ------------------------------------------------------------

    async function load(pathOrCandidates) {
      const candidates = Array.isArray(pathOrCandidates) ? pathOrCandidates : [pathOrCandidates];
      for (const c of candidates) {
        if (cache[c]) return describe(c, cache[c]);
      }
      const wrong = wrongSite();
      if (wrong) return wrong;
      if (isPro2()) return pro2Load(candidates);
      const result = await tryPaths(candidates);
      if (result.error) return result;

      const { path, html } = result;
      const doc = parseDoc(html);
      const body = documentBody(doc);
      const title = titleOf(html, doc);
      const metadata = extractMetadata(doc);
      const toc = buildToc(body);
      const fullText = toText(body);

      cache[path] = { doc, body, title, metadata, toc, fullText };
      return describe(path, cache[path]);
    }

    function describe(path, entry, loc = null) {
      const out = {
        path,
        title: entry.title,
        metadata: entry.metadata,
        totalChars: entry.fullText.length,
      };
      if (entry.site) out.site = entry.site;
      // pro2 resolves a reference with a pinpoint (rt-2000-1811/s1820, a NOU
      // chapter) to a part id; it says where in the text, not what to load.
      if (loc && loc.part) out.part = loc.part;
      if (loc && loc.redirectedFrom) out.redirectedFrom = loc.redirectedFrom;
      if (loc && loc.via) out.via = loc.via;
      if (loc && loc.alternatives) out.alternatives = loc.alternatives;
      // Some Pro records are header-only (St.prp. and other non-law
      // propositions, pre-1985 NOUs under PUBG, Meld. St. shells): the page
      // loads, the title and metadata are real, but there is no body text.
      // Without this flag the caller sees a successful load and has nothing
      // to quote.
      if (out.totalChars < 200) {
        out.metadataOnly = true;
        out.warning = 'no body text in Pro — this is a header/metadata-only record '
          + '(typically a non-law proposition or an older document available as PDF only). '
          + 'Do not quote from it; tell the user the full text is not in Lovdata Pro.';
      }
      // Judgments frequently have no <h1>-<h6> at all (HR-2016-2554-P and
      // LG-2008-135938 have zero), so section() cannot be used on them.
      if (!entry.toc.length && out.totalChars >= 200) {
        out.noHeadings = true;
        out.hint = 'this document has no headings — section() will not work; use grep() and page().';
      }
      // A big forarbeid has hundreds of sections (NOU 2022:8 has 708), which
      // alone can pass PAGE_SIZE. Return what fits; toc() pages the rest.
      const { items, next } = fitToc(entry.toc, 0, PAGE_SIZE - 500 - jsonLen(out));
      out.toc = items;
      if (next !== null) {
        out.tocTotal = entry.toc.length;
        out.tocNext = next;
        out.tocHint = `toc truncated at ${next} of ${entry.toc.length} entries — call toc(path, ${next}) for the rest`;
      }
      return out;
    }

    async function toc(path, start = 0) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      start = Math.max(0, start | 0);
      const { items, next } = fitToc(entry.toc, start, PAGE_SIZE - 500);
      return { path, start, next, total: entry.toc.length, toc: items };
    }

    function requireCached(path) {
      const entry = cache[path];
      if (!entry) return null;
      return entry;
    }

    // A section can be bigger than PAGE_SIZE (a whole NOU chapter, or a
    // top-level heading that spans the document). Then the result carries
    // {offset, next, total}: call section(path, i, next) for the rest.
    async function section(path, iOrId, offset = 0) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      if (!entry.toc.length) {
        return { error: 'no_headings', detail: `${path} has no h1-h6 headings (common for judgments) — use grep() and page() instead` };
      }
      const idx = typeof iOrId === 'number'
        ? iOrId
        : entry.toc.findIndex(t => t.id === iOrId);
      if (idx < 0 || idx >= entry.toc.length) return { error: 'not_found', detail: `no section ${iOrId}` };
      const title = entry.toc[idx].title;
      const text = toText(sectionRange(entry.body, entry.toc, idx));
      offset = Math.max(0, offset | 0);
      const slice = fitSlice(text, offset, PAGE_SIZE, PAGE_SIZE - 500 - jsonLen(title));
      const out = { i: idx, title, text: slice };
      const end = offset + slice.length;
      if (offset > 0 || end < text.length) {
        Object.assign(out, { offset, next: end < text.length ? end : null, total: text.length });
      }
      return out;
    }

    // Heading lines in toText()'s output ("## Title") appear in the same
    // document order as entry.toc, so zipping the two gives each heading's
    // character offset in entry.fullText without re-walking the DOM.
    function headingOffsets(fullText) {
      const re = /^#{1,6} .+$/gm;
      const offsets = [];
      let m;
      while ((m = re.exec(fullText))) offsets.push(m.index);
      return offsets;
    }

    // `term` is matched literally (case-insensitive) unless regex=true —
    // legal search terms are full of regex metacharacters ("§ 4-6 (2)",
    // "art. 8(1)").
    //
    // Returns {matches, hits}: matches counts every occurrence in the
    // document, hits holds the first `max` of them as far as they fit in
    // PAGE_SIZE (truncated:true when they did not). Each hit's `offset` is
    // where the match starts in the text page() reads.
    async function grep(path, term, ctx = 600, max = 20, regex = false) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      ctx = Math.min(Math.max(0, ctx | 0), 5000);
      let re;
      try {
        // The text keeps the source's emphasis (*…*, **…**), which can sit
        // anywhere inside a phrase: skipped between any two characters.
        const glue = '\\*{0,3}';
        const source = regex ? term : String(term).replace(/\*/g, '').trim().split(/\s+/)
          .map((w) => Array.from(w, (c) => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join(glue)).join(glue + '\\s+' + glue);
        re = new RegExp(source, 'gi');
      } catch (e) {
        return { error: 'not_found', detail: `invalid regex: ${term}` };
      }
      const text = entry.fullText;
      const offsets = headingOffsets(text);
      const sectionAt = (pos) => {
        let idx = -1;
        for (let k = 0; k < offsets.length; k++) {
          if (offsets[k] <= pos) idx = k; else break;
        }
        return idx;
      };
      const hits = [];
      const budget = PAGE_SIZE - 500;
      let used = 2, matches = 0, full = false;
      let m;
      while ((m = re.exec(text))) {
        matches++;
        if (hits.length < max && !full) {
          const start = Math.max(0, m.index - ctx);
          const end = Math.min(text.length, m.index + m[0].length + ctx);
          const idx = sectionAt(m.index);
          const hit = {
            i: idx >= 0 ? idx : null,
            sectionTitle: idx >= 0 ? entry.toc[idx].title : null,
            offset: m.index,
            snippet: text.slice(start, end),
          };
          const len = jsonLen(hit) + 1;
          if (used + len > budget) full = true;
          else { hits.push(hit); used += len; }
        }
        if (m.index === re.lastIndex) re.lastIndex += 1; // avoid infinite loop on zero-length match
      }
      const out = { matches, hits };
      if (full) {
        out.truncated = true;
        out.detail = `only ${hits.length} hits fit in one reply — lower ctx or max, or narrow the term`;
      }
      return out;
    }

    async function page(path, offset = 0, size = PAGE_SIZE) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      // Never exceed PAGE_SIZE: javascript_tool fails hard above ~49K chars.
      size = Math.min(Math.max(1, size | 0), PAGE_SIZE);
      offset = Math.max(0, offset | 0);
      const text = entry.fullText;
      const slice = fitSlice(text, offset, size, PAGE_SIZE - 200);
      const end = offset + slice.length;
      const next = end < text.length ? end : null;
      return { offset, next, total: text.length, text: slice };
    }

    // There is no JSON/REST search endpoint: Pro search is GWT-RPC with
    // positional/obfuscated serialization, impractical to call directly.
    // The query must therefore go through the rendered SPA — but it CAN be
    // submitted from here: Lovdata's GWT handler listens for `keyup`.
    // Measured live (2026-09): an `input` event alone does not submit, nor
    // does a synthetic `keydown` or `keypress`, nor a real Enter keypress
    // from the computer tool; a synthetic `keyup` with key Enter does.
    // A real click on the 🔍 button also works and remains the fallback.
    const SEARCH_INPUT = '#quickSearchField-input';

    function setInputValue(input, value) {
      // Assign through the native setter so frameworks that shadow `value`
      // still see the change.
      const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
      if (desc && desc.set) desc.set.call(input, value); else input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // On pro2 search is one API call; `bases` (pro2 only) limits it to
    // Lovdata collection or group codes, e.g. ['HRA'] or ['NOU'].
    async function search(query, n = 10, { timeoutMs = 8000, bases = null } = {}) {
      const wrong = wrongSite();
      if (wrong) return wrong;
      if (isPro2()) return pro2Search(query, n, bases);
      const input = document.querySelector(SEARCH_INPUT);
      if (!input) {
        return { error: 'no_search_field',
                 detail: `no ${SEARCH_INPUT} in this tab — the Hurtigsøk field is on https://lovdata.no/pro/ (hash routing keeps window.__lp alive, a full navigation does not)` };
      }
      // Waiting for the hash to change is not enough: the hash can change
      // before the new list renders (the old hits are still in the DOM), and
      // it may not change at all when the same query is run twice. So stamp
      // every result link now and accept only links that are new or whose
      // href changed — those come from this search.
      const RESULT_LINKS = "a[href^='#document/']";
      for (const a of document.querySelectorAll(RESULT_LINKS)) a.dataset.lpHref = a.getAttribute('href');
      const isFresh = (a) => a.dataset.lpHref !== a.getAttribute('href');
      const before = location.hash;
      input.focus();
      setInputValue(input, query);
      for (const type of ['keydown', 'keypress', 'keyup']) {
        input.dispatchEvent(new KeyboardEvent(type, {
          key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true,
        }));
      }
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 250));
        if (!/^#result/.test(location.hash)) continue;
        if (Array.from(document.querySelectorAll(RESULT_LINKS)).some(isFresh)) {
          await new Promise(r => setTimeout(r, 400)); // let the rest of the list render
          const results = collectResults(n, isFresh);
          if (results.length) {
            // Pro rewrites what you typed: it lower-cases and appends a
            // truncation wildcard, so hash `q=` never equals `query`.
            return { query, hash: location.hash, submitted: input.value, results };
          }
        }
      }
      // Nothing re-rendered. If the tab was already showing the results of
      // this very query (same hash, and its q= is the query as Pro rewrites
      // it), the hits on screen are the right ones.
      const q = (location.hash.match(/[&?]q=([^&]*)/) || [])[1];
      let shown = null;
      try { shown = q == null ? null : decodeURIComponent(q.replace(/\+/g, ' ')); } catch (e) { shown = q; }
      const norm = (s) => String(s).toLowerCase().replace(/\*+$/, '').replace(/\s+/g, ' ').trim();
      if (location.hash === before && shown != null && norm(shown) === norm(query)) {
        const results = collectResults(n);
        if (results.length) {
          return { query, hash: location.hash, submitted: input.value, results, reused: true };
        }
      }
      return {
        error: 'search_timeout', query, hash: location.hash,
        detail: `no new results within ${timeoutMs} ms — fall back to the computer.type + click flow in SKILL.md Steg 3`,
      };
    }

    // Reads the result anchors already rendered in the DOM. search() calls
    // it; call it directly after submitting a query by hand (type + click).
    async function readSearchResults(n = 10) {
      if (isPro2()) return { error: 'not_needed', detail: 'on the new Lovdata Pro, search() returns the results itself' };
      return collectResults(n);
    }

    function collectResults(n, keep = () => true) {
      const anchors = Array.from(document.querySelectorAll("a[href^='#document/']")).filter(keep);
      const seen = new Set();
      const out = [];
      for (const a of anchors) {
        const href = a.getAttribute('href');
        const m = href.match(/^#document\/([^/]+)\/([^/?#]+)\/([^/?#]+)/);
        if (!m) continue;
        const path = `${m[1]}/${m[2]}/${m[3]}`;
        if (seen.has(path)) continue;
        seen.add(path);
        const rn = href.match(/rowNumber=(\d+)/);
        out.push({ path, rowNumber: rn ? Number(rn[1]) : null, title: a.textContent.trim() || undefined });
        if (out.length >= n) break;
      }
      return out;
    }

    return {
      VERSION: HELPER_VERSION,
      cache,
      isLoggedIn: metered('isLoggedIn', isLoggedIn),
      load: metered('load', load),
      toc: metered('toc', toc),
      section: metered('section', section),
      grep: metered('grep', grep),
      page: metered('page', page),
      search: metered('search', search),
      readSearchResults: metered('readSearchResults', readSearchResults),
      stats,
      docUrl,
      PAGE_SIZE,
      // exposed for unit testing / debugging only:
      _internal: { fitSlice, fitToc, toText, inlineText, extractMetadata, buildToc, headingRange, looksLikeRealDoc, isCollectionMismatch, swapSivStr, isLoginPage, backend, isEl, jsonmlToDom, pro2Metadata },
    };
  })();
})();
