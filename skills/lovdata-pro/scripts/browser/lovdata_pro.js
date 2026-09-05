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
    function isLoggedIn() {
      const hash = location.hash;
      const title = document.title;
      const loggedIn = /Min side/i.test(title);
      return { loggedIn, hash, title };
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
    // italic renders as ***text***).
    function inlineText(node) {
      const parts = [];
      const visit = (n) => {
        if (n.nodeType === 3) { parts.push(n.textContent); return; }
        if (n.nodeType !== 1) return;
        const tag = n.tagName.toLowerCase();
        if (tag === 'script' || tag === 'style') return;
        if (tag === 'strong' || tag === 'b') { parts.push('**' + inlineText(n) + '**'); return; }
        if (tag === 'em' || tag === 'i') { parts.push('*' + inlineText(n) + '*'); return; }
        if (tag === 'sup') { parts.push('^' + inlineText(n) + '^'); return; }
        for (const child of n.childNodes) visit(child);
      };
      for (const child of node.childNodes) visit(child);
      return parts.join('').replace(/\s+/g, ' ').trim();
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
          for (const tr of node.querySelectorAll('tr')) {
            const cells = Array.from(tr.querySelectorAll('th, td')).map(inlineText);
            if (cells.some(c => c)) lines.push('| ' + cells.join(' | ') + ' |');
          }
          return;
        }
        if (tag === 'li') {
          lines.push('- ' + inlineText(node));
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
          const key = cells[0].textContent.replace(/\s+/g, ' ').trim();
          const val = cells[1].textContent.replace(/\s+/g, ' ').trim();
          if (key && val) rows.push([key, val]);
        }
        if (rows.length >= 3 && rows.every(([k]) => k.length <= 40)) {
          for (const [k, v] of rows) meta[k] = v;
          return meta;
        }
      }
      return meta;
    }

    function buildToc(body) {
      const headings = Array.from(body.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      const toc = [];
      headings.forEach((h, i) => {
        const level = Number(h.tagName[1]);
        toc.push({
          i,
          id: h.closest('[id]') ? h.closest('[id]').id : (h.id || null),
          level,
          title: h.textContent.replace(/\s+/g, ' ').trim(),
          _el: h,
        });
      });
      // Compute chars per section: from this heading up to the next
      // heading of same-or-higher level (lower or equal `level` number).
      const allNodes = Array.from(body.querySelectorAll('*'));
      toc.forEach((entry, idx) => {
        const startIdx = allNodes.indexOf(entry._el);
        let endIdx = allNodes.length;
        for (let j = idx + 1; j < toc.length; j++) {
          if (toc[j].level <= entry.level) {
            endIdx = allNodes.indexOf(toc[j]._el);
            break;
          }
        }
        let chars = 0;
        for (let k = startIdx; k < endIdx && k < allNodes.length; k++) {
          chars += (allNodes[k].textContent || '').length;
        }
        entry.chars = chars;
      });
      return toc.map(({ i, id, level, title, chars }) => ({ i, id, level, title, chars }));
    }

    function sectionRange(body, toc, index) {
      // A heading's section runs from itself to the next heading of
      // same-or-higher level, wherever that falls in the DOM — headings
      // are not reliably direct children of `body` (a subsection's <h3>
      // often sits inside the same wrapper div as its parent <h2>, not as
      // a sibling top-level div). Range boundary points can straddle any
      // depth, so use the native Range API instead of walking siblings.
      const headings = Array.from(body.querySelectorAll('h1, h2, h3, h4, h5, h6'));
      const heading = headings[index];
      if (!heading) return null;
      const entry = toc[index];
      const nextEntry = toc.slice(index + 1).find(e => e.level <= entry.level);
      const nextHeading = nextEntry ? headings[nextEntry.i] : null;

      const range = body.ownerDocument.createRange();
      range.setStartBefore(heading);
      if (nextHeading) {
        range.setEndBefore(nextHeading);
      } else {
        range.setEnd(body, body.childNodes.length);
      }
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
        if (cache[c]) {
          const entry = cache[c];
          return { path: c, title: entry.title, metadata: entry.metadata, totalChars: entry.fullText.length, toc: entry.toc };
        }
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
      return { path, title, metadata, totalChars: fullText.length, toc };
    }

    function requireCached(path) {
      const entry = cache[path];
      if (!entry) return null;
      return entry;
    }

    async function section(path, iOrId) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
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

    async function grep(path, term, ctx = 600, max = 20) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      let re;
      try {
        re = new RegExp(term, 'gi');
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

    async function page(path, offset, size = PAGE_SIZE) {
      const entry = requireCached(path);
      if (!entry) return { error: 'not_found', detail: `${path} not loaded — call load() first` };
      const text = entry.fullText;
      const slice = text.slice(offset, offset + size);
      const next = offset + size < text.length ? offset + size : null;
      return { offset, next, total: text.length, text: slice };
    }

    // There is no JSON/REST search endpoint (spike 3): Pro search is
    // GWT-RPC with positional/binary-ish serialization, impractical to call
    // directly. Submitting the query itself also can't be done from inside
    // this module (spike 4): neither JS-dispatched input/keydown events nor
    // a real Enter keypress reach Lovdata's GWT search handler — only an
    // actual click on the search button works. So the SKILL.md workflow
    // drives the search at the tool-call level (computer.type into the
    // field, computer.left_click the button) and calls this function only
    // afterwards, to read the rendered result anchors back out of the DOM.
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
      readSearchResults,
      docUrl,
      // exposed for unit testing / debugging only:
      _internal: { toText, inlineText, extractMetadata, buildToc, looksLikeRealDoc, isCollectionMismatch, swapSivStr, isLoginPage },
    };
  })();
}
