# lovdata-pro — maintainer notes

Implementation background for whoever (human or Claude) next touches this
skill. Not part of the skill itself — see `SKILL.md` for that, `README.md`
for the human-facing overview.

(This file is deliberately *not* named `CLAUDE.md`: a `CLAUDE.md` here would
be loaded as project instructions by every Claude Code session working in
this directory, which is not what maintainer notes are for.)

## Spike findings (2026-09-05)

Before the Playwright → Claude Desktop built-in browser (Cowork) migration
was finalised, four one-time checks were run live in Cowork against
`https://lovdata.no/pro/` to settle implementation details the plan couldn't
determine from the CLI alone. Their results are folded into the shipped
code; this is the record of *why* those values are what they are, in case
Lovdata's site changes and they need re-checking.

1. **`javascript_tool` return-size ceiling.** Tested `'x'.repeat(N)` at
   increasing N. Behavior is a hard error, not silent truncation:
   `Error: result (50,249 characters) exceeds maximum allowed tokens` at
   N=50,000; N=49,000 and below returned cleanly. The tool also appends
   ~250 characters of wrapper text (`(captured at origin …)\n\nTab
   Context: …`) on top of the raw payload. → `PAGE_SIZE = 45000` in
   `scripts/browser/lovdata_pro.js`, leaving headroom for that wrapper and
   for JSON-escaping expansion (Norwegian characters, embedded quotes).

2. **Login detection.** `location.hash` is `#myPage` in *both* the
   logged-in and logged-out states — Lovdata swaps the rendered content
   client-side without touching the hash, so hash is not a usable signal.
   Only `document.title` distinguishes them: `"Min side - Lovdata Pro"`
   when logged in, bare `"Lovdata"` when not. → `isLoggedIn()` checks
   `document.title` only (previously also required the hash, which was
   harmless but redundant given the finding).

3. **Search API.** Submitted a query via the UI and inspected network
   traffic: the only server call is
   `POST https://lovdata.no/pro/LovdataPro/GWT.rpc?fulltextSearchService`,
   whose body/response is GWT-RPC's positional/obfuscated-string-table
   serialization (e.g. `//OK["o","Bx",0,0,425,0,5,0,0,0.0,0.0,...`), not
   JSON. No direct-fetch shortcut exists — confirms what the old
   Playwright-era mapping notes predicted.

4. **Submitting a search query.** Because of (3), the query has to be
   submitted through the rendered SPA. The original spike tried (a) setting
   `input.value` + dispatching synthetic `input`/`keydown` events, (b) a
   synthetic `KeyboardEvent` Enter, (c) a **real** `computer` keyboard Enter,
   and concluded that only a real click on the 🔍 button submits.
   **That conclusion was too broad — corrected 2026-09-09.** Isolating the
   event types in a live session showed the GWT handler listens on `keyup`:
   `input` alone no, synthetic `keydown` no, synthetic `keypress` no,
   synthetic **`keyup` yes** (hash went to `#result&id=2378&q=TOSL-2023*`).
   A real Enter keypress still does nothing; a real click still works.
   → `lovdata_pro.js` now owns the flow with `search(query, n)`, and keeps
   `readSearchResults(n)` for the type-and-click fallback.

Full detail (including the discarded first pass at spike 1, which
mistakenly measured `.length` of a string rather than the string itself)
lives in the Cowork session that ran these; the summary above and the
comments in `lovdata_pro.js` / `references/lovdata-pro-mapping.md` are
what's kept long-term. The `spikes/README.md` that posed these questions
has been deleted now that all four are answered.

## Extraction fidelity: text-only `toText()`, not raw HTML (2026-09-05)

Considered whether `toText()` should keep raw HTML (or a stripped-down
semantic subset of it) instead of flattening to plain text, to preserve
formatting/links/table fidelity. Kept plain text, but fixed a real gap in
how it was extracted — two separate questions, two different answers:

- **Full or stripped-down HTML: rejected.** It's markedly more verbose per
  unit of content than extracted text, so it would hit `PAGE_SIZE` much
  sooner — more `javascript_tool` round trips for the same substantive
  content, working against the whole reason the hybrid section/grep/page
  design exists. The use case (citing text into a conversation) doesn't
  need re-rendering, so there's nothing to gain that's worth that cost. If
  a future need *does* justify richer markup (e.g. an artifact wants to
  render a document, not just cite from it), a semantic subset — keep only
  `h1-6`/`p`/`table`/`a href`/`strong`/`em`, drop all attributes — is the
  right lever, not full raw HTML.
- **Inline emphasis (bold/italic/superscript): this was a real gap, now
  fixed.** `toText()` previously read `node.textContent` for headings/`<p>`/
  `<li>`/table cells, which silently drops any `<strong>`/`<b>`/`<em>`/`<i>`/
  `<sup>` nested inside — e.g. a bold `§`-title inline in a `<p>` (common in
  forarbeider that quote full proposed statute text) would merge invisibly
  into the surrounding body text with no boundary marker at all. Fixed by
  adding `inlineText()`, which walks a block element's children and wraps
  those tags as `**bold**`/`*italic*`/`^superscript^` (composing when
  nested) instead of just concatenating text — used everywhere `toText()`
  previously called `textContent` directly. Cost is negligible (a couple of
  characters per span, not a tag's worth of markup), so this doesn't
  threaten `PAGE_SIZE` the way keeping HTML would have.
- **A related but distinct question — are Høyesterett's "(77)"-style
  avsnitt numbers literal DOM text or CSS-generated (`::before`/`::after`)
  content, which no text-extraction approach (not even raw HTML) can see —
  was checked directly against `HRSIV/avgjorelse/hr-2016-2554-p` in Cowork:
  **confirmed real DOM text** (`countInRendered` `innerText` vs.
  `countInRawText` `textContent` both 218, no numbers missing from raw
  text). Not a bug; nothing to fix. If Lovdata ever changes how a document
  type numbers its paragraphs, re-run this check before assuming it still
  holds:
  ```javascript
  (() => {
    const body = document.querySelector('#documentBody') || document.body;
    const numPattern = /\(\d{1,4}\)/g; // adjust if the real format differs
    const numsIn = (s) => new Set(s.match(numPattern) || []);
    const innerNums = numsIn(body.innerText || '');
    const textNums = numsIn(body.textContent || '');
    return {
      countInRendered: innerNums.size,
      countInRawText: textNums.size,
      numbersMissingFromRawText: [...innerNums].filter(n => !textNums.has(n)).slice(0, 15),
    };
  })()
  ```

## Verification round, 2026-09-09

The whole skill was re-checked in a live Cowork session after a round of
fixes. What that changed, beyond the search finding in (4) above:

- **Tingrett references** carry a court prefix (`TOSLO-2019-108726-2`,
  `TOSL-2022-105703`); the slug is the lower-cased reference and the
  collection is `TRSIV`/`TRSTR`. The old `TR-YYYY-N` form in the docs was
  never a real Lovdata reference.
- **Stortingsmeldinger** are `STS/forarbeid/stsg-<sesjon>-<løpenummer>`, not
  a `MELD` collection, and the løpenummer is not derivable — so the resolver
  now sends them to search instead of guessing.
- **`Innst. O./S.` and `Dok. 8:`** slugs were guesses that turned out right;
  they are now confirmed.
- **Judgments have no headings** (`toc.length === 0` for HR-2016-2554-P and
  LG-2008-135938) and **no party lines in the body** — the parties live in
  `metadata.Parter`, separated by `<br>`.
- **Lovdata emits no list markup**: litra points are one-row
  `table.listeItem` elements with `leftMargin_N` depth classes.
- **Header-only records** (St.prp., older NOUs) load successfully with zero
  body text, which is now flagged as `metadataOnly`.
- The `javascript_tool` ceiling was re-measured: 49 000 characters passes,
  50 000 fails. `PAGE_SIZE = 45000` stands.
- `preview_start` cannot be used inside `browser_batch`; `navigate` can.
  `computer.screenshot` failed with `UnknownVizError`, so `read_page` is the
  way to locate the search button.

## Naming note

`readSearchResults(n)` reads anchors already rendered in the DOM and takes no
query; `search(query, n)` submits a query and then calls it. Both are public
because the fallback flow submits the query with the computer tool.
