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
// {error: 'http_<n>' | 'cors' | 'bad_id' | 'not_found', detail}.

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
    // canonical `<type>_<digits>` form, or null.
    function normId(raw) {
      if (!raw) return null;
      const m = String(raw).match(ID_RE);
      return m ? m[0] : null;
    }

    function urnForm(id) {
      return 'URN:NBN:no-nb_' + id;
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
    // nb.no is client-rendered, so calling this straight after a navigate
    // races the render: the DOM branches miss and it falls through to the
    // catalog branch or not_found. Rather than making every caller sleep
    // first, the page branches are polled until the URN appears or waitMs
    // (default 5000) runs out. Pass {waitMs: 0} to check once and return.
    async function resolveUrn(opts) {
      const o = opts || {};
      const waitMs = o.waitMs === undefined ? 5000 : Math.max(0, Number(o.waitMs) || 0);
      const started = Date.now();
      const deadline = started + waitMs;
      const waited = () => Date.now() - started;

      for (;;) {
        // 1. The URL itself may already carry the URN.
        const fromUrl = normId(location.href);
        if (fromUrl) {
          return { id: fromUrl, urn: urnForm(fromUrl), via: 'url', waitedMs: waited() };
        }

        // 2. The "Referere/Sitere" block links to urn.nb.no.
        //    Observed 2026-09-06 to match nothing on a fully rendered item
        //    page — the cite link is not a plain urn.nb.no anchor. Kept
        //    because it is free and exact when it does fire, but branch 3 is
        //    what actually carries this in practice: don't weaken it on the
        //    assumption that this one backs it up.
        const links = document.querySelectorAll('a[href*="urn.nb.no"]');
        for (let i = 0; i < links.length; i++) {
          const id = normId(links[i].getAttribute('href'));
          if (id) return { id: id, urn: urnForm(id), via: 'urn-link', waitedMs: waited() };
        }

        // 3. The rendered page embeds the URN in metadata / JSON payloads.
        const inPage = normId(document.documentElement.innerHTML);
        if (inPage) {
          return { id: inPage, urn: urnForm(inPage), via: 'page', waitedMs: waited() };
        }

        if (Date.now() >= deadline) break;
        await sleep(300);
      }

      // 4. Last resort: ask the catalog about the opaque path segment.
      const seg = location.pathname.split('/').filter(Boolean).pop();
      if (seg) {
        const r = await getJson(API + '/items/' + encodeURIComponent(seg));
        if (!r.error) {
          const id = normId(JSON.stringify(r.json || {}));
          if (id) return { id: id, urn: urnForm(id), via: 'catalog', waitedMs: waited() };
        }
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
      _internal: { normId: normId, urnForm: urnForm, MAX_CHARS: MAX_CHARS },
    };
  })();
}
