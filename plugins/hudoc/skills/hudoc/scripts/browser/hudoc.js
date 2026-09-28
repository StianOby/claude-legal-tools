// HUDOC in-page helper — the fallback for when Cloudflare challenges
// scripts/hudoc.py. Paste the whole file into a Claude Desktop built-in
// browser tab on https://hudoc.echr.coe.int/ via javascript_tool.
//
// Idempotent: re-pasting is a no-op if the same version of window.__hd
// already exists (see HELPER_VERSION below). All functions are async, return
// plain JSON-serialisable objects no larger than PAGE_SIZE characters, and
// never throw to the caller — errors come back as
// {error: 'wrong_origin' | 'challenge' | 'http_<n>' | 'fetch_failed' |
//         'not_json' | 'no_match' | 'no_docx' | 'bad_docx' | 'not_loaded' |
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
// same resolve() scoring, and the same DOCX-to-text conversion (paragraphs
// separated by a blank line, footnotes as [fn N] plus a FOOTNOTES block), so
// text read here and text read from the CLI cache match line for line.
//
// Also exported for Node (CommonJS) so the pure parts can be unit-tested —
// see tests/test_browser.js.

// HELPER_VERSION follows the plugin version and changes whenever this file
// does (set it by hand; CI checks it). A helper of another version already in
// the tab — pasted before a skill update — is replaced, dropping its cache;
// the same version is left alone.
(function (root) {
  const HELPER_VERSION = '1.1.0';
  if (root.window && root.window.__hd && root.window.__hd.VERSION === HELPER_VERSION) return;

  const api = (() => {
    // javascript_tool errors hard above ~49-50K characters of result
    // (measured for lovdata-pro, same tool channel). 45000 leaves headroom.
    const PAGE_SIZE = 45000;
    const ORIGIN = 'https://hudoc.echr.coe.int';
    const QUERY_PATH = '/app/query/results';
    const DOCX_PATH = '/app/conversion/docx/';
    const WEB_URL = ORIGIN + '/eng?i=';
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
    const APPNO_RE = /^\d{1,6}\/\d{2}(?:;\d{1,6}\/\d{2})*$/;
    const ECLI_RE = /^ECLI:CE:ECHR:\d{4}:\d{4}[A-Z]{3}\d{9,12}$/i;

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

    function referenceClause(ref) {
      if (ITEMID_RE.test(ref)) return { clause: `itemid:"${ref}"`, length: 1 };
      if (APPNO_RE.test(ref)) return { clause: `appno:"${ref.split(';')[0]}"`, length: 50 };
      if (ECLI_RE.test(ref)) return { clause: `ecli:"${ref.toUpperCase()}"`, length: 50 };
      if (ref.includes(':') && !ref.startsWith('"')) return { clause: ref, length: 50 };
      // Free-text case name: AND of the tokens before " v. " / " c. ".
      const head = ref.split(/\s+(?:v\.|c\.|vs\.?)\s+/)[0];
      let tokens = (head.match(/[\p{L}\p{N}_'-]+/gu) || []).filter((t) => t.length > 1);
      if (!tokens.length) tokens = ref.match(/[\p{L}\p{N}_'-]+/gu) || [];
      const clause = tokens.map((t) => 'docname:' + t).join(' AND ') || `docname:"${ref}"`;
      return { clause, length: 50 };
    }

    async function resolveRow(reference, { doctype = null, langPref = ['ENG', 'FRE'], fields = DEFAULT_FIELDS } = {}) {
      const ref = String(reference).trim();
      const { clause, length } = referenceClause(ref);
      const r = await query(clause, { fields, length });
      if (r.error) return r;
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
      rows.sort((a, b) => compareKeys(scoreKey(a, langPref), scoreKey(b, langPref)));
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

    // --- DOCX -> text (mirrors docx_to_text in scripts/hudoc.py) -------------

    // Minimal ZIP reader: the central directory gives each entry's method and
    // sizes (the local headers of streamed zips may carry zeros), the local
    // header gives where the data starts. Deflate goes through the browser's
    // own DecompressionStream.
    async function unzipEntries(buf, wanted) {
      const bytes = new Uint8Array(buf);
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      let eocd = -1;
      for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
        if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
      }
      if (eocd < 0) throw new Error('no end-of-central-directory record');
      const count = dv.getUint16(eocd + 10, true);
      let p = dv.getUint32(eocd + 16, true);
      const out = {};
      const dec = new TextDecoder('utf-8');
      for (let n = 0; n < count; n++) {
        if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('bad central directory entry');
        const method = dv.getUint16(p + 10, true);
        const csize = dv.getUint32(p + 20, true);
        const nameLen = dv.getUint16(p + 28, true);
        const extraLen = dv.getUint16(p + 30, true);
        const commentLen = dv.getUint16(p + 32, true);
        const local = dv.getUint32(p + 42, true);
        const name = dec.decode(bytes.subarray(p + 46, p + 46 + nameLen));
        p += 46 + nameLen + extraLen + commentLen;
        if (!wanted.includes(name)) continue;
        const start = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true);
        const data = bytes.subarray(start, start + csize);
        if (method === 0) out[name] = dec.decode(data);
        else if (method === 8) {
          const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
          out[name] = dec.decode(await new Response(stream).arrayBuffer());
        } else throw new Error(`unsupported compression method ${method} for ${name}`);
      }
      return out;
    }

    function xmlUnescape(s) {
      return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
        if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
        return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }[e.toLowerCase()];
      });
    }

    // Walks WordprocessingML as a token stream. Text comes only from <w:t>;
    // <w:tab/> is a space; a footnote reference with id > 0 becomes " [fn N]";
    // a paragraph nested inside another (text box) joins the outer one, as
    // ElementTree's iter() does in the Python version. Returns
    // [{text, footnote}] per top-level paragraph, `footnote` being the id of
    // the enclosing <w:footnote> (null in the document body).
    function wordParagraphs(xml) {
      const re = /<(\/?)([A-Za-z][\w:.-]*)([^>]*?)(\/?)>|([^<]+)/g;
      const paras = [];
      let depth = 0; let inT = false; let parts = []; let footnote = null;
      let m;
      while ((m = re.exec(xml))) {
        if (m[5] !== undefined) {
          if (inT && depth > 0) parts.push(xmlUnescape(m[5]));
          continue;
        }
        const closing = m[1] === '/'; const tag = m[2]; const attrs = m[3]; const selfClosing = m[4] === '/';
        if (tag === 'w:p') {
          if (closing) {
            depth -= 1;
            if (depth === 0) { paras.push({ text: parts.join('').trim(), footnote }); parts = []; }
          } else if (!selfClosing) depth += 1;
        } else if (tag === 'w:t') {
          inT = !closing && !selfClosing;
        } else if (tag === 'w:tab' && depth > 0 && !closing) {
          parts.push(' ');
        } else if (tag === 'w:footnoteReference' && depth > 0) {
          const id = (attrs.match(/w:id="(-?\d+)"/) || [])[1];
          if (id && Number(id) > 0) parts.push(` [fn ${id}]`);
        } else if (tag === 'w:footnote') {
          if (closing) footnote = null;
          else footnote = Number((attrs.match(/w:id="(-?\d+)"/) || [])[1]);
        }
      }
      return paras;
    }

    function docxXmlToText(documentXml, footnotesXml) {
      const out = wordParagraphs(documentXml).map((p) => p.text).filter(Boolean);
      const notes = [];
      if (footnotesXml) {
        const byId = new Map();
        for (const p of wordParagraphs(footnotesXml)) {
          if (!(p.footnote > 0)) continue; // separator / continuation pseudo-notes
          if (!byId.has(p.footnote)) byId.set(p.footnote, []);
          if (p.text) byId.get(p.footnote).push(p.text);
        }
        for (const [id, texts] of byId) {
          if (texts.length) notes.push(`[fn ${id}] ${texts.join(' ')}`);
        }
      }
      if (notes.length) out.push('FOOTNOTES', ...notes);
      return out.join('\n\n') + '\n';
    }

    async function docxToText(buf) {
      const e = await unzipEntries(buf, ['word/document.xml', 'word/footnotes.xml']);
      if (!e['word/document.xml']) throw new Error('no word/document.xml in the DOCX');
      return docxXmlToText(e['word/document.xml'], e['word/footnotes.xml']);
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
      return { ...r.row, source_url: WEB_URL + r.row.itemid };
    }

    async function metadata(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await resolveRow(ref, opts);
      if (r.error) return r;
      return fitRow({ ...r.row, source_url: WEB_URL + r.row.itemid });
    }

    async function citations(ref, opts = {}) {
      const bad = checkOrigin();
      if (bad) return bad;
      const r = await resolveRow(ref, opts);
      if (r.error) return r;
      const cited = parseScl(r.row.scl);
      return fitRows({ itemid: r.row.itemid, docname: r.row.docname, cited_count: cited.length, cited }, 'cited');
    }

    // Fetch the official DOCX and convert it to text in the page. The text is
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
        const url = `${DOCX_PATH}?library=ECHR&id=${encodeURIComponent(id)}&filename=${encodeURIComponent(id)}.docx`;
        let res, buf;
        try {
          res = await deps.fetch(url, { credentials: 'include' });
          buf = await res.arrayBuffer();
        } catch (e) {
          return { error: 'fetch_failed', detail: String((e && e.message) || e) };
        }
        const head = new Uint8Array(buf.slice(0, 2));
        if (!(res.ok && head[0] === 0x50 && head[1] === 0x4b)) {
          const text = new TextDecoder().decode(new Uint8Array(buf.slice(0, 4000)));
          if (isChallenge(res.status, text)) return { error: 'challenge', detail: 'Cloudflare "Just a moment…" page' };
          return { error: 'no_docx', detail: `HTTP ${res.status}, ${buf.byteLength} bytes, not a DOCX — HUDOC may hold this item as PDF only (${WEB_URL + id})` };
        }
        let text;
        try {
          text = await docxToText(buf);
        } catch (e) {
          return { error: 'bad_docx', detail: String((e && e.message) || e) };
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

    // `term` is literal (spaces match any whitespace) unless regex = true.
    // Each hit carries the number of the judgment paragraph it falls in.
    async function grep(itemid, term, ctx = 400, max = 15, regex = false) {
      const bad = requireLoaded(itemid);
      if (bad) return bad;
      const text = cache.items[itemid].text;
      let re;
      try {
        const source = regex ? term : String(term).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
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
      while (chunk.length > 1 && HEADING_RE.test(chunk[chunk.length - 1])) chunk = chunk.slice(0, -1);
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
      _internal: { referenceClause, scoreKey, compareKeys, parseScl, unzipEntries, wordParagraphs, docxXmlToText, docxToText, queryUrl, isChallenge, paragraphStarts },
    };
  })();

  if (root.window) root.window.__hd = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
