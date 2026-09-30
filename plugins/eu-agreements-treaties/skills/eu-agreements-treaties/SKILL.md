---
name: eu-agreements-treaties
description: >
  Use when the user needs the EU-side status of an international agreement
  concluded by the EU, EC, EEC, Euratom or EU member states — signature,
  ratification/notification per party, entry into force, provisional
  application, declarations/reservations, or the OJ reference — from the
  Council of the EU Treaties Office database (consilium.europa.eu).
  Triggers: "has the
  EU ratified", "which member states have notified", "when did X enter into
  force for the EU", "Council treaty database", "agreements between the EU and
  Norway/Iceland/Switzerland/UK", status of EEA, Schengen, Dublin or aviation
  agreements, 7-digit Consilium IDs (e.g. 2016032), party codes UE/CE/CEE.
  Requires the Cowork built-in browser (the site blocks other clients).
  NOT for: treaty text (eurlex, via the OJ reference); Norwegian
  entry into force or Stortinget consent (norges-traktater); UN-deposited
  treaties (untc); Council of Europe conventions (ets); EU legislation or
  CJEU case law (eurlex).
---

# Consilium Treaties Office database

The Council of the European Union's register of treaties and agreements to
which the EU, EC, EEC, Euratom or the member states are party (2 363 records
in September 2026). It is the authoritative source for the **EU side** of a
treaty relationship: who signed, who has notified/ratified, when it entered
into force, provisional application, and each party's declarations and
reservations. It does **not** hold treaty text — it links to the Official
Journal on EUR-Lex.

This skill is written in English. **Always answer in the user's language.**
Quote dates and party names exactly as the site gives them.

| Question | Source |
|---|---|
| Who has ratified / notified, and when? Provisional application? | **this skill** |
| What does the agreement say? | `eurlex`, via the OJ reference `detail()` returns |
| Norwegian entry into force, Stortinget consent, Norwegian text | `norges-traktater` |
| UN-deposited multilateral treaties | `untc` |
| Council of Europe conventions | `ets` |

## Prerequisites — read first

**This skill runs only in Claude Desktop with Cowork** (local or cloud). It needs
the built-in browser tools (`tabs_context`, `preview_start`, `navigate`,
`javascript_tool`, `browser_batch`, and `request_access` where it exists).

**Browser tools.** The built-in browser's tool prefix differs by environment (`mcp__Claude_Browser__…` in local
Cowork, `mcp__remote-devices__Claude_Browser__…` in cloud Cowork). They are often deferred: run one ToolSearch with
query `Claude_Browser` and `max_results` 64, and use whatever prefix comes back. This file names them by suffix only
(`tabs_context`, `preview_start`, `navigate`, `javascript_tool`, `get_page_text`, `read_page`, …).
`request_access` does not exist in every environment; if it is missing, go straight to `preview_start`/`navigate`.

Why: `www.consilium.europa.eu` sits behind a Cloudflare browser check that
returns HTTP 403 to every non-browser client — `curl`, Python, `WebFetch`,
headless browsers. Only a real browser tab that has passed the check can read
the database, and same-origin `fetch()` from inside that tab is how the
helper works. **If the browser tools are not in your tool list, stop and tell
the user this skill only works in Claude Desktop/Cowork.** Do not try
`WebFetch`, `curl` or any other route; they fail, and the skill must never
try to get around the check.

Your one script is `scripts/browser/consilium.js` in `{SKILL_DIR}`. It is pasted into the browser tab and does all fetching and
parsing in-page.

**Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for this skill:" if it exists in bash.
Otherwise resolve it once and use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/eu-agreements-treaties}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/eu-agreements-treaties/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

## Where each step runs

| Step | Runs in |
|---|---|
| Reading `consilium.js` from `{SKILL_DIR}` | cloud sandbox (`Bash`) |
| Everything that touches consilium.europa.eu (`ready`, `search`, `detail`, …) | browser pane |
| Local shell | not used |

In a cloud Cowork session `Bash` runs in Anthropic's cloud with Anthropic's IP, not the user's; only the browser pane is
sure to have the user's IP and logins. In local Cowork, `Bash` runs on the user's computer. The site blocks every
non-browser client, so nothing is fetched from `Bash`; if it returns 403, say "This source is blocked from Anthropic's
cloud" and use the browser pane. Never suggest a VPN.

## Step 0 — session (every new conversation)

1. `tabs_context` — reuse a tab already on `consilium.europa.eu` if there is
   one. Otherwise `preview_start {url:
   "https://www.consilium.europa.eu/en/documents/treaties-agreements/"}`.
2. If a tool says the site is not approved and `request_access` exists: `request_access {url:
   "https://www.consilium.europa.eu/", scope: "site"}` and retry. If the user
   declines, stop.
3. Load the helper. Run `python3 {SKILL_DIR}/scripts/browser/paste.py
   {SKILL_DIR}/scripts/browser/consilium.js` in Bash. It writes a copy
   without comments or indentation (about 30,000 characters instead of
   45,000) and prints its path. Read that file and send **all** of it via
   `javascript_tool` (`action: "javascript_exec"`). If `paste.py` fails,
   paste `consilium.js` itself. Never trim or shorten the helper.
   Idempotent; an older helper left in the tab from before a skill update
   is replaced (`__cs.VERSION` shows which one runs).
   **If the paste is refused by a safety check**, do not retry it. Tell the
   user in one sentence and use the read-only route: `navigate` to
   `https://www.consilium.europa.eu/en/documents/treaties-agreements/agreement/?id=<7-digit id>&docLanguage=en`
   and read it with `get_page_text` (or `read_page`); a search is
   `…/treaties-agreements/?DoSearch=true&Parties=<code>&Lang=en`. Without
   the helper there is no `find()` or party-code check: read the tables
   as shown and quote only what the page says.
4. `await __cs.ready()` →
   - `{ok: true, parties: 256, …}` → go on.
   - `{error: "challenge"}` → the tab is still on the Cloudflare page. Wait a
     few seconds and call `ready()` again; if it persists, ask the user to
     reload the tab in the browser panel. Never loop more than three times.
   - `{error: "wrong_origin"}` → the tab is on another site; navigate it back.

`navigate` + paste + `ready()` can go in one `browser_batch`
(`preview_start` cannot be batched). Keep the tab parked on the database —
`window.__cs` and its cache die on navigation.

## Step 1 — what the user asks → what you run

| User says | Run |
|---|---|
| "agreements between the EU and Norway" | `await __cs.search({parties: ["NO"]})` |
| "agreements Norway **and** Iceland are both party to" | `await __cs.search({all: ["NO", "IS"]})` — AND is local; the site only does OR |
| "Norway **or** Iceland" | `await __cs.search({parties: ["NO", "IS"]})` (135, not 42 — see rules) |
| "EU–Norway agreements signed 2010–2020, newest first" | `await __cs.search({parties: ["NO"], from: "2010", to: "2020", sort: "LSF"})` — `to` is enforced locally, see rule 11 |
| "…that entered into force after 2015" | `…, dateType: "eif", from: "2016"` (`dateType` is `signature` or `eif` only) |
| "anything on Schengen" (no party filter) | `await __cs.find("schengen")` — local title match over the whole register (one 1.6 MB fetch, ~2.5 s, then cached). Title words only: association agreements that do not say "Schengen" are missed |
| "agreements between the EU and X" | `search({parties: ["UE", "CE", "CEE"], …})` gives the union of the three EU-side entities; add the counterparty with `all` |
| "Ecuador's agreements" | `await __cs.search({parties: ["EC"], literal: true})` — bare `EC` is refused as ambiguous (rule 1) |
| "agreement 2016032" / "details of the aviation agreement" | `await __cs.detail("2016032")` |
| "has Austria ratified 2011036?" | `detail("2011036")` → the `parties` row for code `A` |
| "Austria's declaration to 2011036" | `await __cs.declaration("2011036", "A")` |
| "which agreements in this list mention Norway as a party?" | `await __cs.details(["2016032", "2011036", …])` — polite batch, 3 at a time |
| "what is the code for Germany / the EEC?" | `await __cs.parties("german")`, `await __cs.parties("economic community")` |
| "the French title of 2016032" | `await __cs.detail("2016032", "fr")` |
| more rows of a search | `await __cs.items(key, 60)` with the `key` the search returned |
| rest of a long declaration | `await __cs.page(key, 1)` |

Every call returns ≤ 45 000 characters. Search results come back as a
summary (`total`, `shown`, first rows, `key`); page through with `items()`
rather than asking for everything.

## Result fields

Search rows: `{id, title, signature, entry_into_force, is_proces_verbal}` —
dates ISO or `null`. The list view has **no party column**; parties are only
on the detail page. The summary also carries `site_total` (the site's own
count, before any local filter), `semantics` (`single` / `OR` / `AND` /
`local-title`) and `notes[]` explaining every local adjustment (rows dropped by
`to`, undated rows excluded, Procès-Verbaux removed). Repeat those notes to
the user when you report a count.

`detail(id)`:

```
id, title, is_proces_verbal
signature, signature_place, entry_into_force        # agreement level
oj_references: [{text, url, oj:{series,year,issue,part}, eurlex_hint}]
observations                                        # provisional application lives here
parties: [{name, code, signature, signature_inherited, inherited_signature,
           notification, entry_into_force, entry_into_force_inherited,
           inherited_entry_into_force, has_declaration, declaration_url,
           observations}]
party_codes, parties_without_code, ratification_footnote, url, caveats
```

`code` is resolved from the party's plain-text name via the site's own party
list, so it is only reliable with `lang: "en"`; in other languages most rows
land in `parties_without_code`. `*_inherited: true` marks an empty cell (the
site's footnote applies); `inherited_*` is the agreement-level date it
inherits, which can itself be `null` when the page has none (e.g. `2011036`).

## Rules — the database's traps

These are the errors a careful user of this database has actually made.
Follow them even when the user's phrasing pushes the other way.

1. **Party codes are not ISO 3166.** Ten member states use old EC codes:
   `A` Austria, `B` Belgium, `D` Germany, `F` France, `I` Italy, `IRL`
   Ireland, `H` Hungary, `P` Portugal, `S` Sweden, `SF` Finland. The rest are
   ISO (`DK`, `NL`, `ES`, `PL` …), which makes the trap worse. EU entities:
   `UE` European Union, `CE` European Community, `CEE` EEC, `CEA` Euratom,
   `EEE` EEA, `EM` the member states collectively. **`EC` is Ecuador** —
   the European Community is `CE` (its short name on the site is "EC"). Full
   list (256 codes) and historical parties in `references/party-codes.md`.
   The helper validates every code against the site's own list and returns
   `{error: "unknown_party", suggestions}` instead of searching — because the
   site itself answers an unknown code with **zero hits and no error** — and
   `{error: "ambiguous_code"}` for `EC`, which needs `literal: true` (Ecuador)
   or `CE`. Never report "no agreements" from a search whose code you did
   not see validated.
2. **Several `parties` are OR, not AND.** `Parties=NO&Parties=IS` gives the
   union (135), not the intersection (42). For "both X and Y are party" use
   `{all: [...]}`; the helper intersects per-party result sets locally. Say
   which semantics you used when you report a count.
3. **The 7-digit ID does not encode the signature year.** `2009066` was
   signed in 2011; a quarter of Norway's agreements differ. Treat the ID as
   an opaque key. Never sort, filter or cite a year from it.
4. **Empty cells in the ratification table are not "not ratified".** The
   site's footnote: *when no dates are specified, the agreement-level
   "Entry into force" and "Signature" apply, except for acceding parties.*
   The helper marks these `signature_inherited` / `entry_into_force_inherited:
   true`. Report the inherited date and say it is inherited.
5. **One Consilium record can cover several instruments.** `2007059`
   bundles four agreements that Norway's register lists as four treaties.
   When reconciling against a national register, compare titles, not counts.
6. **8 % of rows have no signature date** (e.g. `2006052` ECAA, `2010035`
   PEM, `2011036` aviation). They sort last; date filters exclude them. Say
   so when a date-filtered list is meant to be exhaustive.
7. **Procès-Verbaux de Rectification** (corrigenda to language versions) are
   listed as agreements. Pass `noPV: true` or point them out; they have a
   signature but never an entry into force.
8. **Titles carry editorial insertions** — `- See 2014013 (EEA Agreement)`,
   language lists `(BG/ES/DA/…)`. Do not present a list title as the formal
   title; take it from `detail()` or the OJ.
9. **The database is the EU perspective.** For Norway's ratification,
   provisional application and entry into force, `norges-traktater` is
   authoritative and the two do not always agree. State the source of each
   date.
10. **No treaty text here.** `detail().oj_references[].eurlex_hint` tells you
    how to open the OJ issue with the `eurlex` skill.
11. **The site has no upper date bound.** Verified 2026-09-16: `DateFrom`
    works as a lower bound, `DateTo` is **silently ignored** — a 2010–2020
    query returned agreements signed in 2026 at the top, with the site's own
    count agreeing. The helper therefore sends only `DateFrom` and applies
    `to` locally on the chosen date field; rows without that date are
    excluded from any date-filtered result (and counted in `notes`).
    `dateType: "ratification"` returns zero rows for everything and is
    refused; only `signature` and `eif` work. If you ever build a URL by hand
    for the user, warn them that the "to" box does nothing.

## Reporting

- Give the agreement's Consilium ID and URL
  (`https://www.consilium.europa.eu/en/documents/treaties-agreements/agreement/?id=<id>&docLanguage=en`)
  with every status statement, and the date you looked (the tables change).
- Suggested citation: *Council of the EU, Treaties Office Database,
  agreement 2016032, "<title>", https://…?id=2016032 (accessed 16 September
  2026).*
- When a search was filtered by party, say which codes and whether OR/AND.
- When you show fewer rows than `total`, say so.

## Errors

All functions return `{error, detail}` rather than throwing:

- `challenge` → Cloudflare page. Wait, retry `ready()` up to three times,
  then ask the user to reload the tab. Never work around it.
- `wrong_origin` → the tab left the site; navigate back and load the helper again (step 3).
- `unknown_party` → show the `suggestions` to the user; do not search.
- `ambiguous_code` → the code means something else on the site (`EC` =
  Ecuador). Show both `options`; rerun with the intended code or
  `literal: true`.
- `unsupported_date_type` / `bad_date` → only `signature`/`eif`; dates as
  `YYYY`, `YYYY-MM-DD` or `DD/MM/YYYY`.
- `bad_id` → IDs are exactly seven digits.
- `not_found` → the detail page had neither title nor ratification table;
  check the ID, then try `find()` on the title.
- `http_<n>` / `fetch_failed` → report once; do not hammer the site.
- `not_cached` → the `key` is from a previous tab or before a navigation;
  rerun the search.
- Site not approved / user declined access → stop and say so.

## Etiquette

One tab, one paste, and fetch only what the question needs. `find()` costs
one 1.6 MB request and is then free; `details()` fetches at most three
pages at a time with a delay — do not raise it. Never crawl the whole
register's detail pages in a user session; if the user wants a full export,
say it is a maintainer job (see `NOTES.md`).
