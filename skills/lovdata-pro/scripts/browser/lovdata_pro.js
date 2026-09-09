// Lovdata Pro in-page helper — paste into javascript_tool once per tab.
//
// Idempotent: re-pasting is a no-op if window.__lp already exists. All
// functions are async and return plain JSON-serialisable objects (this is
// what javascript_tool returns to the caller — no DOM nodes, no functions).
//
// Keep this tab parked on https://lovdata.no/pro/ and never navigate it
// away — window.__lp.cache dies on navigation, and every load()/section()/
// grep() after the first for a given path reuses the cached parsed
// Document instead of re-fetching.
//
// Error convention: functions never throw to the caller. They return
// {error: 'not_logged_in' | 'not_found' | 'collection_mismatch' | 'cors' | 'http_<n>', detail}.

if (!window.__lp) {
  window.__lp = (() => {
    // javascript_tool errors above ~49-50K raw characters ("result exceeds
    // maximum allowed tokens") rather than truncating silently — measured
    // empirically (spikes/README.md #1). 45000 leaves headroom for the
    // tool's own wrapper text and for JSON-escaping expansion of special
    // characters (Norwegian letters, embedded quotes).
    const PAGE_SIZE = 45000;

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

    async function isLoggedIn({ probe = true } = {}) {
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
        const res = await fetch(url, { credentials: 'include' });
        const html = await res.text();
        return { status: res.status, html };
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

    // Renders a block element's inline content to a single line, preserving
    // emphasis (**bold**, *italic*, ^superscript^) instead of flattening it
    // like plain textContent would — matters for e.g. bold §-titles in
    // statute text quoted inside forarbeider. Nested tags compose (bold
    // italic renders as ***text***). <br> becomes a line break (party
    // lists in judgments: "A (advokat X)<br>mot<br>B"); nested lists are
    // skipped when skipLists is set so toText() can render them as their
    // own "- " lines.
    function inlineText(node, { skipLists = false } = {}) {
      const parts = [];
      const visit = (n) => {
        if (n.nodeType === 3) { parts.push(n.textContent); return; }
        if (n.nodeType !== 1) return;
        const tag = n.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return;
        if (tag === 'br') { parts.push('\n'); return; }
        if (skipLists && (tag === 'ul' || tag === 'ol')) return;
        if (tag === 'strong' || tag === 'b') { parts.push('**' + inlineText(n, { skipLists }) + '**'); return; }
        if (tag === 'em' || tag === 'i') { parts.push('*' + inlineText(n, { skipLists }) + '*'); return; }
        if (tag === 'sup') { parts.push('^' + inlineText(n, { skipLists }) + '^'); return; }
        for (const child of n.childNodes) visit(child);
      };
      for (const child of node.childNodes) visit(child);
      return parts.join('')
        .split('\n')
        .map(s => s.replace(/\s+/g, ' ').trim())
        .filter(Boolean)
        .join('\n');
    }

    function toText(el) {
      if (!el) return '';
      const lines = [];
      const walk = (node) => {
        if (node.nodeType === 3) { // text node
          const t = node.textContent.replace(/\s+/g, ' ').trim();
          if (t) lines.push(t);
          return;
        }
        if (node.nodeType !== 1) return;
        const tag = node.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return;
        if (/^h[1-6]$/.test(tag)) {
          const level = Number(tag[1]);
          lines.push('#'.repeat(level) + ' ' + inlineText(node));
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
          if (own) lines.push('- ' + own);
          // Nested lists become their own indented "- " lines.
          for (const sub of node.querySelectorAll(':scope > ul, :scope > ol')) {
            for (const li of sub.querySelectorAll(':scope > li')) {
              const sublines = toText(li);
              if (sublines) lines.push(sublines.split('\n').map(l => '  ' + (l.startsWith('- ') ? l : '- ' + l)).join('\n'));
            }
          }
          return;
        }
        if (tag === 'p') {
          const t = inlineText(node);
          if (t) lines.push(t);
          return;
        }
        for (const child of node.childNodes) walk(child);
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
        title: h.textContent.replace(/\s+/g, ' ').trim(),
      }));
      // Chars per section via Range.toString(): one linear pass per
      // section. (The earlier version summed textContent over every node
      // in the section, which is quadratic and took tens of seconds on a
      // multi-MB NOU.)
      toc.forEach((entry, idx) => {
        const range = headingRange(body, headings, toc, idx);
        entry.chars = range ? range.toString().length : 0;
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

    function describe(path, entry) {
      const out = {
        path,
        title: entry.title,
        metadata: entry.metadata,
        totalChars: entry.fullText.length,
        toc: entry.toc,
      };
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
      return out;
    }

    function requireCached(path) {
      const entry = cache[path];
      if (!entry) return null;
      return entry;
    }

    async function section(path, iOrId) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      if (!entry.toc.length) {
        return { error: 'no_headings', detail: `${path} has no h1-h6 headings (common for judgments) — use grep() and page() instead` };
      }
      const idx = typeof iOrId === 'number'
        ? iOrId
        : entry.toc.findIndex(t => t.id === iOrId);
      if (idx < 0 || idx >= entry.toc.length) return { error: 'not_found', detail: `no section ${iOrId}` };
      const range = sectionRange(entry.body, entry.toc, idx);
      return { title: entry.toc[idx].title, text: toText(range) };
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
    async function grep(path, term, ctx = 600, max = 20, regex = false) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      let re;
      try {
        const source = regex ? term : String(term).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
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
      let m;
      while ((m = re.exec(text)) && hits.length < max) {
        const start = Math.max(0, m.index - ctx);
        const end = Math.min(text.length, m.index + m[0].length + ctx);
        const idx = sectionAt(m.index);
        hits.push({
          i: idx >= 0 ? idx : null,
          sectionTitle: idx >= 0 ? entry.toc[idx].title : null,
          snippet: text.slice(start, end),
        });
        if (m.index === re.lastIndex) re.lastIndex += 1; // avoid infinite loop on zero-length match
      }
      return hits;
    }

    async function page(path, offset = 0, size = PAGE_SIZE) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      // Never exceed PAGE_SIZE: javascript_tool fails hard above ~49K chars.
      size = Math.min(Math.max(1, size | 0), PAGE_SIZE);
      offset = Math.max(0, offset | 0);
      const text = entry.fullText;
      const slice = text.slice(offset, offset + size);
      const next = offset + size < text.length ? offset + size : null;
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

    async function search(query, n = 10, { timeoutMs = 8000 } = {}) {
      const input = document.querySelector(SEARCH_INPUT);
      if (!input) {
        return { error: 'no_search_field',
                 detail: `no ${SEARCH_INPUT} in this tab — the Hurtigsøk field is on https://lovdata.no/pro/ (hash routing keeps window.__lp alive, a full navigation does not)` };
      }
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
        if (location.hash !== before && /^#result/.test(location.hash)) {
          await new Promise(r => setTimeout(r, 400)); // let the list render
          const results = await readSearchResults(n);
          if (results.length) {
            // Pro rewrites what you typed: it lower-cases and appends a
            // truncation wildcard, so hash `q=` never equals `query`.
            return { query, hash: location.hash, submitted: input.value, results };
          }
        }
      }
      return {
        error: 'search_timeout', query, hash: location.hash,
        detail: `no results within ${timeoutMs} ms — fall back to the computer.type + click flow in SKILL.md Steg 3`,
      };
    }

    // Reads the result anchors already rendered in the DOM. search() calls
    // it; call it directly after submitting a query by hand (type + click).
    async function readSearchResults(n = 10) {
      const anchors = Array.from(document.querySelectorAll("a[href^='#document/']"));
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
      cache,
      isLoggedIn,
      load,
      section,
      grep,
      page,
      search,
      readSearchResults,
      docUrl,
      PAGE_SIZE,
      // exposed for unit testing / debugging only:
      _internal: { toText, inlineText, extractMetadata, buildToc, headingRange, looksLikeRealDoc, isCollectionMismatch, swapSivStr, isLoginPage },
    };
  })();
}
