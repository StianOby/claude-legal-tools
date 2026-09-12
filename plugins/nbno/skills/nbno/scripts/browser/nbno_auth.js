// nb.no in-page helper — paste into javascript_tool once per tab.
//
// Idempotent: re-pasting is a no-op if window.__nb already exists. All
// functions are async and return plain JSON-serialisable objects (that is
// what javascript_tool hands back to the caller — no DOM nodes, no
// functions, no page bytes).
//
// Scope, deliberately narrow: session check, access/loan status, URN
// resolution and — only when the item needs it — the two readable nb.no
// cookies. Page images are NEVER fetched here; base64 through the tool
// channel is not viable for a book. The sandbox does all downloading.
//
// Error convention: functions never throw to the caller. They return
// {error: 'http_<n>' | 'cors' | 'bad_id' | 'not_found' | 'ambiguous', detail}.

if (!window.__nb) {
  window.__nb = (() => {
    // javascript_tool errors above ~49-50K raw characters ("result exceeds
    // maximum allowed tokens") rather than truncating silently. 45000 leaves
    // headroom for the tool's own wrapper text and for JSON-escaping.
    const MAX_CHARS = 45000;

    const API = 'https://api.nb.no/catalog/v1';
    const ME = 'https://api.nb.no/me/v1';

    const TYPES = [
      'digibok', 'digavis', 'digifoto', 'digitidsskrift', 'digikart',
      'digimanus', 'digiprogramrapport', 'pliktmonografi', 'pliktperiodika',
    ];
    // e.g. digibok_2008051600041 — the type prefix keeps a stray opaque
    // items-hash from matching.
    const ID_RE = new RegExp('(?:' + TYPES.join('|') + ')_[0-9A-Za-z_]+');

    // --- id handling -------------------------------------------------------

    // Accepts a canonical id, a URN in any casing, an https://urn.nb.no/...
    // link, or an https://www.nb.no/items/URN:NBN:no-nb_... URL. Returns the
    // canonical `<type>_<key>` form (the key may contain underscores:
    // digavis_aftenposten_morgen_1_20150107_156_7_2), or null.
    function normId(raw) {
      if (!raw) return null;
      const m = String(raw).match(ID_RE);
      return m ? m[0] : null;
    }

    function urnForm(id) {
      return 'URN:NBN:no-nb_' + id;
    }

    // Every distinct item id in a blob of text, in order of first
    // appearance. Cover-page ids (`<id>_C1`, `_C2`, `_C3`) are folded into
    // their item: they sit next to the base id in the catalog JSON and in
    // page markup and are not a second item.
    const ID_RE_G = new RegExp(ID_RE.source, 'g');
    function distinctIds(text) {
      const all = (String(text || '').match(ID_RE_G) || [])
        .map((id) => id.replace(/_C\d+$/, ''));
      return Array.from(new Set(all));
    }

    // --- fetch -------------------------------------------------------------

    // No explicit Accept header: /me/v1 serves only application/hal+json and
    // answers 406 to `Accept: application/json`. The browser's default
    // (…, */*;q=0.8) matches everything nb.no offers, so leave it alone.
    async function getJson(url) {
      try {
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) return { error: 'http_' + res.status, detail: url };
        return { json: await res.json() };
      } catch (e) {
        // Cross-origin failures surface here as an opaque TypeError.
        return { error: 'cors', detail: String((e && e.message) || e) };
      }
    }

    // --- public API --------------------------------------------------------

    // Who is nb.no serving this browser as? Anonymous responses carry only
    // {ip}; a logged-in one adds loginProvider/roles/displayName. `ip` is the
    // egress IP the image resolver geo-checks — the sandbox shares it.
    async function status() {
      const r = await getJson(ME);
      if (r.error) return r;
      const j = r.json || {};
      return {
        loggedIn: !!j.loginProvider,
        loginProvider: j.loginProvider || null,
        roles: j.roles || null,
        ip: j.ip || null,
        displayName: j.displayName || null,
      };
    }

    // accessInfo is both IP- and session-dependent: the same item reports
    // viewability NONE from abroad and ALL from Norway. Always read it here
    // (in the logged-in tab), not anonymously from the sandbox.
    async function access(idOrUrl) {
      const id = normId(idOrUrl);
      if (!id) return { error: 'bad_id', detail: String(idOrUrl) };
      const r = await getJson(API + '/items/' + urnForm(id));
      if (r.error) return r;
      const j = r.json || {};
      const md = j.metadata || {};
      return {
        id: id,
        urn: urnForm(id),
        title: md.title || null,
        accessInfo: j.accessInfo || null,
      };
    }

    // Polled after the user clicks OK in the digital-loan dialog. Never take
    // the loan on their behalf — it accepts terms and consumes one of the
    // item's licences.
    async function loanStatus(idOrUrl) {
      const a = await access(idOrUrl);
      if (a.error) return a;
      const ai = a.accessInfo || {};
      return {
        id: a.id,
        viewability: ai.viewability || null,
        legalDepositReservationStatus: ai.legalDepositReservationStatus || null,
        accessAllowedFrom: ai.accessAllowedFrom || null,
        isPublicDomain: !!ai.isPublicDomain,
      };
    }

    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    // Turn the opaque https://www.nb.no/items/<hash> URL the user pasted into
    // a canonical id. Run this with the tab parked on that page.
    //
    // Order matters. The catalog is asked about the opaque hash BEFORE the
    // rendered page is scanned: an item page routinely embeds ids of other
    // editions (an opaque-hash page for Hamsun's Sult carried another
    // digibok_ of the same novel first in its HTML, 2026-09-12), and the
    // title check downstream cannot tell two copies of the same book apart.
    // The page scan is kept as a fallback but refuses to guess when it sees
    // more than one distinct id.
    //
    // nb.no is client-rendered, so calling this straight after a navigate
    // races the render. Rather than making every caller sleep first, the DOM
    // branches are polled until something answers or waitMs (default 5000)
    // runs out. Pass {waitMs: 0} to check once and return.
    async function resolveUrn(opts) {
      const o = opts || {};
      const waitMs = o.waitMs === undefined ? 5000 : Math.max(0, Number(o.waitMs) || 0);
      const started = Date.now();
      const deadline = started + waitMs;
      const waited = () => Date.now() - started;

      // 1. The URL itself may already carry the URN.
      const fromUrl = normId(location.href);
      if (fromUrl) {
        return { id: fromUrl, urn: urnForm(fromUrl), via: 'url', waitedMs: waited() };
      }

      // 2. Ask the catalog about the opaque path segment. One request, and
      //    the answer is the record for exactly this item.
      const seg = location.pathname.split('/').filter(Boolean).pop();
      if (seg && seg !== 'items') {
        const r = await getJson(API + '/items/' + encodeURIComponent(seg));
        if (!r.error) {
          const j = r.json || {};
          const ids = (j.metadata && j.metadata.identifiers) || {};
          const id = normId(ids.urn) || normId(j.id);
          if (id) return { id: id, urn: urnForm(id), via: 'catalog', waitedMs: waited() };
        }
      }

      let ambiguous = null;
      for (;;) {
        // 3. A urn.nb.no anchor (the "Referere/Sitere" block). Page-dependent:
        //    present on some fully rendered item pages, absent on others.
        const links = document.querySelectorAll('a[href*="urn.nb.no"]');
        for (let i = 0; i < links.length; i++) {
          const id = normId(links[i].getAttribute('href'));
          if (id) return { id: id, urn: urnForm(id), via: 'urn-link', waitedMs: waited() };
        }

        // 4. Ids embedded in the rendered HTML. Trusted only when the page
        //    contains exactly one; several means related items are on the
        //    page and the first hit is no better than a coin toss.
        const seen = distinctIds(document.documentElement.innerHTML);
        if (seen.length === 1) {
          return { id: seen[0], urn: urnForm(seen[0]), via: 'page', waitedMs: waited() };
        }
        if (seen.length > 1) ambiguous = seen;

        if (Date.now() >= deadline) break;
        await sleep(300);
      }

      if (ambiguous) {
        return {
          error: 'ambiguous',
          candidates: ambiguous.slice(0, 10),
          detail: 'page holds ' + ambiguous.length + ' distinct ids and the catalog ' +
                  'did not answer for ' + location.href +
                  '; ask the user for the URN (Referere/Sitere) or try __nb.access() on ' +
                  'each candidate and compare the full record, not just the title',
        };
      }
      return {
        error: 'not_found',
        detail: 'no URN on ' + location.href + ' after ' + waited() + 'ms',
      };
    }

    // The two nb.no cookies that are readable from document.cookie (neither
    // is HttpOnly). Returns NOTHING else — never hand the whole jar to the
    // model context.
    //
    // Only `nbsso` grants anything: it is what the IIIF resolver checks for
    // FEIDE-licensed items. `_nblb` is returned solely so the cookie file
    // matches the format the nbno CLI and DevTools captures use; on its own
    // it authenticates nothing.
    //
    // document.cookie can list `nbsso` twice (same value, two cookie
    // domains) — take the last occurrence.
    function cookies() {
      const jar = {};
      const parts = String(document.cookie || '').split(';');
      for (let i = 0; i < parts.length; i++) {
        const eq = parts[i].indexOf('=');
        if (eq < 0) continue;
        const k = parts[i].slice(0, eq).trim();
        if (k !== 'nbsso' && k !== '_nblb') continue;
        jar[k] = parts[i].slice(eq + 1).trim();   // last wins
      }
      return {
        nbsso: jar.nbsso || null,
        nblb: jar._nblb || null,
        // Ready to paste into the sandbox cookie file's `cookie=` line.
        cookieHeader: [
          jar.nbsso ? 'nbsso=' + jar.nbsso : null,
          jar._nblb ? '_nblb=' + jar._nblb : null,
        ].filter(Boolean).join('; ') || null,
      };
    }

    // Compact IIIF manifest: canvas name + image service id only. Optional —
    // the sandbox can fetch the manifest itself without any auth. Use this
    // only if that ever fails.
    //
    // opts: {offset, limit} to page through a long book. `compact: true` is
    // accepted for call-signature compatibility but is always on — a full
    // manifest would not survive the tool channel, so there is no non-compact
    // mode to turn off.
    //
    // Canvas ids are heterogeneous (_C1, _I1, _0001…, _C2). Always read them
    // from here; never construct them.
    async function manifest(idOrUrl, opts) {
      const o = opts || {};
      const id = normId(idOrUrl);
      if (!id) return { error: 'bad_id', detail: String(idOrUrl) };

      let r = await getJson(API + '/items/' + id + '/manifest');
      if (r.error === 'http_404') {
        // Required for some pliktmonografi items.
        r = await getJson(API + '/iiif/' + urnForm(id) + '/manifest');
      }
      if (r.error) return r;

      let canvases;
      try {
        canvases = r.json.sequences[0].canvases;
      } catch (e) {
        return { error: 'not_found', detail: 'no sequences[0].canvases' };
      }

      const all = canvases.map((c) => ({
        name: String(c['@id']).split('/').pop(),
        serviceId: c.images[0].resource.service['@id'],
      }));

      const offset = Number(o.offset) || 0;
      const limit = Number(o.limit) || all.length;
      let items = all.slice(offset, offset + limit);
      // Trim until the serialised payload fits one javascript_tool response.
      while (items.length > 1 && JSON.stringify(items).length > MAX_CHARS) {
        items = items.slice(0, Math.floor(items.length * 0.8));
      }
      const next = offset + items.length < all.length
        ? offset + items.length
        : null;
      return { id: id, count: all.length, offset: offset, next: next, canvases: items };
    }

    return {
      status: status,
      access: access,
      loanStatus: loanStatus,
      resolveUrn: resolveUrn,
      cookies: cookies,
      manifest: manifest,
      // exposed for debugging only:
      _internal: { normId: normId, urnForm: urnForm, distinctIds: distinctIds, MAX_CHARS: MAX_CHARS },
    };
  })();
}
