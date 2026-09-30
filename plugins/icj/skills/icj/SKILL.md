---
name: icj
description: |
  Use whenever the user needs ICJ or PCIJ material — case law, advisory opinions,
  jurisdictional facts, optional-clause declarations, or treaty bases. Triggers
  include named cases (Nicaragua, Lotus, Chorzów, Whaling, Bosnia Genocide, Israeli
  Wall, Chagos, etc.); ICJ case numbers or PCIJ series codes; Article 36(2) optional
  clause, compulsory jurisdiction, reservations, reciprocity; questions like "could
  state A bring B before the ICJ", "find the PCIJ Lotus judgment", "hva sa ICJ i
  Whaling-saken". Use even when the Court isn't named: if answering requires an ICJ
  or PCIJ judgment or jurisdictional text, this is the right tool. Prefer over
  training-data recall — declarations change and only icj-cij.org is authoritative.
  Do NOT use for: ECtHR/Strasbourg (hudoc); CJEU/EU law (eurlex); Norwegian domestic
  law (lovdata-api); Council of Europe treaties (ets); UN treaty status (untc); EFTA Court.
  Pleadings and verbatim records are out of scope.
---

# ICJ — International Court of Justice

This skill talks to `icj-cij.org` to find and retrieve ICJ and PCIJ case law, jurisdictional facts, and optional-clause declarations. It uses a small Python CLI that scrapes the site and caches the slow-changing parts on disk.

---

## What this skill covers

| Question type | Examples |
|---|---|
| **Case law lookup** | "what did the Court say in Nicaragua", "list pending cases", "find the PCIJ Lotus judgment" |
| **Jurisdictional analysis** | "could state A bring state B to the ICJ", "which states accept compulsory jurisdiction", "which agencies can request advisory opinions" |
| **Declaration text** | verbatim text of a state's Article 36(2) declaration, comparing reservations, checking whether a particular dispute is covered |

Pleadings, written observations, and verbatim records of hearings are deliberately **out of scope**.

---

## Where each step runs

| Step | Runs in |
|---|---|
| Cases, PCIJ, jurisdiction pages, declaration texts (`scripts/icj.py`) | cloud sandbox (`Bash`) |
| Reading the extracted text, quoting | cloud sandbox (`Bash`) |
| Judgment/opinion PDFs (Cloudflare blocks every script) | browser pane (see **Fetching PDF text**) |

In a cloud Cowork session `Bash` runs in Anthropic's cloud with Anthropic's IP, not the user's; only the browser pane is
sure to have the user's IP and logins. In local Cowork, `Bash` runs on the user's computer. `icj-cij.org` has worked from the cloud so far; if
it answers 403/405 from `Bash` in a cloud session, tell the user "This source is blocked from Anthropic's cloud" rather than retrying.

## Setup

All scripts live in `scripts/`. They are plain Python 3 (3.9+) using only the standard library — no packages to install. Run them from the skill directory (`{SKILL_DIR}`).

**Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for this skill:" if it exists in bash.
Otherwise resolve it once and use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/icj}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/icj/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

The CLI entry point is `scripts/icj.py`. Run `python3 scripts/icj.py --help` for the subcommand list. Cached data lives in `~/.cache/icj/` (override with `$ICJ_CACHE_DIR`) and is created on first use; the cache is never written inside the skill folder.

## Cache and freshness

Jurisdiction pages (the seven `/index.php/...` pages listed below) and the per-state declaration texts change over time as states deposit new declarations, terminate them, or amend reservations. The skill keeps a local cache and offers explicit freshness controls so you don't silently serve stale answers:

- `python scripts/icj.py status` — for every cached jurisdiction and declaration page: when it was last fetched, the server's `Last-Modified` header (if any), and whether a HEAD request now reports it as changed. Then one line on the other cached pages (case lists, case pages, PCIJ pages).
- `python scripts/icj.py refresh` — re-fetch the jurisdiction and declaration pages that have changed. `refresh --all` re-fetches every cached page, case pages included.
- Jurisdiction and declaration pages are cached for 14 days, then re-fetched on the next read.
- Case lists (`list-of-all-cases`, `pending-cases`, `decisions`) and case pages are cached for **one day**, so a new order in a pending case, or a case moving from pending to concluded, shows up the next day. For something from today, pass `--force-refresh`.

When the user asks a question that hinges on the *current* state of jurisdiction (e.g., "does Iceland still accept compulsory jurisdiction"), run `status` first; if anything is stale or changed, run `refresh` before answering. When the question is about historical facts (e.g., what the Lotus judgment said), the cache age does not matter — case-law PDFs at `icj-cij.org` are immutable.

## Subcommands

The CLI groups functionality by data type. Each subcommand prints either machine-friendly JSON (with `--json`) or a short human-readable summary. PDFs are referenced by URL. Direct HTTP download of icj-cij.org PDFs is blocked by Cloudflare — see **Fetching PDF text** below for how to read them anyway.

### `cases` — ICJ contentious + advisory cases

- `cases list [--pending] [--year YYYY] [--country XX] [--advisory] [--contentious]` — list the Court's cases. The site's `list-of-all-cases` page holds only *concluded* cases (with years and type); pending cases live on `pending-cases` with title only. The default merges both (pending entries carry `"pending": true`, blank years, and a case type inferred from the title); `--pending` shows only the pending ones.
- `cases show <case_id>` — show a case: title and links to all judgments / orders / advisory opinions / summaries / press releases / institution documents, grouped by section. The documents are read from the per-section subpages (`/case/<N>/orders`, `/judgments`, `/press-releases`, `/institution-proceedings`, `/summaries`, `/other-documents`, and for advisory cases `/request-advisory-opinion`, `/advisory-opinions`) — the case page itself only lists "latest developments". **Pleadings and oral proceedings are intentionally omitted** unless you pass `--include-pleadings` (see "Out of scope" below).
- `cases recent [--limit N]` — the latest decisions across all cases (mirrors the `/decisions` page).
- `cases search "query"` — word search over case titles: every word must start a word of the title, in any order, ignoring accents and case, so `"Bosnia Genocide"`, `"Ukraine v. Russia"` (Russian Federation), `"Gabcikovo"` and `"Nicaragua v. USA"` all work. Common nicknames whose words are not in the title (`"Israeli Wall"`, `"Tehran hostages"`, `"Yerodia"`, `"Rohingya"`, `"Bakassi"`, `"Cumaraswamy"`, `"Mortished"`, `"Habré"`, `"Nicaragua"` for Military and Paramilitary Activities) put that case first. `CERD` is read as "racial discrimination", and "Yugoslavia" falls back to "Serbia and Montenegro", the name the Court now uses in those titles. Word order is ignored, so "USA v Iran" lists every United States/Iran case — check the parties in the title. PCIJ cases (Lotus, Chorzów) are not here — use `pcij list`.

### `pcij` — Permanent Court of International Justice (1922-1946)

- `pcij list [--series a|b|ab]` — list PCIJ cases in Series A (Judgments 1923-1930), Series B (Advisory Opinions 1923-1930), or Series A/B (from 1931). Default: all three.
- `pcij show <code>` — show a PCIJ case (e.g. `A10` for Lotus, `B04` for Nationality Decrees in Tunis and Morocco, `A/B53` for Eastern Greenland). Lists judgment, dissenting opinions, declarations, orders, annexes — each with its PDF URL.

PCIJ Series C (pleadings/oral arguments), Series D (organisational acts), Series E (annual reports) and Series F (indexes) are listed in `references/pcij-series.md` for completeness but are not exposed as commands — the same hearing-documents-out-of-scope rule applies.

### `jurisdiction` — the seven jurisdictional pages

- `jurisdiction states [--with-declaration] [--un-member] [--non-un]` — the table of all 193 UN members plus historical entries, with admission date and (where applicable) the date their Article 36(2) declaration was deposited. Source: `/states-entitled-to-appear`.
- `jurisdiction non-un` — text of `/states-not-members` (states that became party to the Statute without being UN members).
- `jurisdiction non-parties` — text of `/states-not-parties` (states not party to the Statute to which the Court may be open under Art. 35(2) and SC Resolution 9 (1946)).
- `jurisdiction basis` — text of `/basis-of-jurisdiction` (the Court's own description of how jurisdiction can be founded: special agreement, treaty clause, optional clause, forum prorogatum, Article 35).
- `jurisdiction treaties [--year YYYY] [--search QUERY]` — the table of treaties that confer jurisdiction on the Court (year, date, place, title and clause, contracting parties). `--search` matches title and parties; note the page lists treaties *notified to the Registry*, so well-known compromissory clauses (Genocide Convention Art. IX) may be absent — check the convention itself via `untc` or `ets`.
- `jurisdiction organs` — text of `/organs-agencies-authorized` (UN organs and specialized agencies entitled to request advisory opinions, with the list of opinions each has requested).

### `declarations` — Article 36(2) optional-clause declarations

- `declarations list` — every state currently shown on `/declarations`, with ISO-2 country code and date of deposit.
- `declarations show <state>` — full text of one state's declaration. `<state>` may be the ISO-2 code (`no`, `fi`, `gb`) or a unique name prefix (`Norway`, `United Kingdom`).
- `declarations compare <state1> <state2> [<stateN> ...]` — print the texts side by side. Useful for deciding whether two states' declarations would intersect over a given subject matter (see workflow below).

## Workflow: "Could states X and Y litigate dispute Z at the ICJ?"

This is the headline use case the user described — e.g. *would Norway's and Finland's Article 36(2) declarations allow an ICJ case concerning a territorial dispute between them*. The analysis has a fixed shape:

1. **Confirm both states are parties to the Statute.** Run `jurisdiction states` and check both are listed (all UN members are; otherwise check `non-un` or `non-parties`).
2. **Confirm both have made a declaration under Article 36(2).** Run `declarations list` — if either is missing, compulsory jurisdiction under the optional clause is unavailable and you must look for a treaty basis (`jurisdiction treaties`) or special agreement (`jurisdiction basis`).
3. **Pull both texts.** `declarations compare no fi`. Read the full text — the date the declaration came into force, its duration / termination clause, and crucially the *reservations*.
4. **Apply reciprocity.** Under Article 36(2) and the Court's case law (Norwegian Loans, Interhandel), each state can invoke the other's reservations against it. So a dispute is covered by the optional clause only if it falls outside *both* states' reservations.
5. **Map reservations to the dispute.** Common reservation categories: disputes covered by another method of settlement; disputes arising before a date X; disputes with members of the Commonwealth; disputes concerning the law of the sea (e.g. Norway's UNCLOS carve-out); disputes concerning national defence or military activities; disputes that the state notifies in advance.
6. **Conclude.** Either the dispute fits within both declarations (compulsory jurisdiction available); or it does not, in which case the parties would need a special agreement or another jurisdictional treaty.

Always quote the relevant reservation language verbatim from the declaration text — paraphrasing reservations changes their legal effect.

## How to ground answers

When answering substantive questions:

- For **case law**, link to the official PDF on `icj-cij.org` (the URLs returned by `cases show` / `pcij show` are the canonical ones). If the user wants the text of a judgment, direct HTTP download is blocked by Cloudflare — read it through the Claude Cowork internal browser as described in **Fetching PDF text** below.
- For **jurisdictional facts**, cite the page name (e.g. "States entitled to appear before the Court") and the date the cache was last refreshed. Always check `status` first if the user's question is about the current legal position.
- For **declarations**, quote the deposit date and the relevant clause exactly as it appears in the cached text. The skill stores the canonical English version published by the Court.

## Fetching PDF text

Direct HTTP requests to `icj-cij.org` PDF URLs — via `curl`, `urllib` or any script, whatever the User-Agent — are answered by Cloudflare with a 403 challenge page instead of the PDF (verified September 2026). The HTML pages the CLI uses are not affected. To read a judgment, use the **Claude Cowork internal browser**, which passes the challenge like an ordinary browser:

1. Get the PDF URL from `cases show <N>` or `pcij show <code>`.
2. In the internal browser, first open the HTML case page (e.g. `https://www.icj-cij.org/case/82`) so the Cloudflare cookies are set, then open the PDF URL in the same browser session. The built-in PDF viewer renders the text; read and quote from it there, with the paragraph numbers.
3. If the user needs the file itself, save it from the browser (download). Where the browser tool can only run page scripts, copy it across in pieces — one reply from the browser tool holds only about 45,000 characters, and a judgment PDF is typically 0.5–5 MB (0.7–7 MB as base64):
   - From the case page, load the PDF into the tab and report its size:
     ```javascript
     const r = await fetch(pdfUrl, { credentials: 'include' });
     const blob = await r.blob();
     window.__pdf = await new Promise((ok) => { const f = new FileReader(); f.onload = () => ok(f.result.split(',')[1]); f.readAsDataURL(blob); });
     ({ status: r.status, type: blob.type, bytes: blob.size, chunks: Math.ceil(window.__pdf.length / 40000) })
     ```
     `type` must be `application/pdf`; `text/html` means Cloudflare answered instead — open the case page first and try again.
   - If the pane shows a Cloudflare "Verify you are human" check (Turnstile), you cannot pass it yourself: `navigate` the pane to the PDF URL, ask the user to tick the box in the browser pane and say when it's done, then retry once. If it still answers `text/html`, give the user the PDF URL and stop.
   - For `i` = 0 … `chunks`−1, get `window.__pdf.slice(i * 40000, (i + 1) * 40000)` and append it to `outputs/<name>.b64` (outputs = `/mnt/user-data/outputs` in cloud Cowork) with bash (`printf '%s' '<chunk>' >> …`).
   - Then `base64 -d outputs/<name>.b64 > outputs/<name>.pdf` and check the page count with a PDF tool.

   Tell the user up front how many calls it takes; for reading and quoting, the PDF viewer (step 2) is much quicker.

If no browser tool is available in the session, give the user the PDF URL and quote only what `cases show` / the summaries page provides; do not reconstruct judgment text from memory.

## Out of scope (deliberately)

This skill does not expose:

- **Pleadings, written observations, counter-memorials, or verbatim records of oral hearings.** Even when present in a case page, they are filtered out of `cases show` output. A separate skill will handle hearing documents.
- **PDF text extraction via simple HTTP.** Direct download from icj-cij.org is blocked by Cloudflare; read PDFs through the Claude Cowork internal browser as described in **Fetching PDF text** above.
- **Translation.** Documents are surfaced in English by default. French URLs are noted when present but not parsed.
- **Live-scraping every request.** Jurisdiction data is cached for 14 days, case lists and case pages for one day. The user-facing freshness contract is described above.

## File layout

```
icj/
├── SKILL.md
├── scripts/
│   ├── icj.py            # CLI entry point; thin dispatcher to the modules below
│   ├── _common.py        # HTTP (urllib), cache manifest, freshness, country codes
│   ├── _html.py          # minimal DOM over html.parser (no BeautifulSoup needed)
│   ├── jurisdiction.py   # the 7 /index.php/... pages
│   ├── declarations.py   # /declarations and /declarations/<cc>
│   ├── cases.py          # /list-of-all-cases, /pending-cases, /case/<N>/<section>, /decisions
│   └── pcij.py           # /pcij-series-{a,b,ab}
├── references/
│   ├── url-patterns.md       # all URLs, PDF naming, doc-type codes
│   ├── jurisdiction-overview.md  # Statute Articles 34-36, optional clause, reciprocity
│   ├── declaration-analysis.md   # how to compare two declarations (Norway-Finland worked example)
│   ├── pcij-series.md            # Series A/B/A/B/C/D/E/F overview
│   └── data-codes.md             # ISO-2 codes, document-type codes used in PDF filenames
                                  # runtime cache: ~/.cache/icj/ (or $ICJ_CACHE_DIR)
```

When a question maps to one of the reference files, read the relevant file before answering — they encode case-law nuance the SKILL.md keeps short.
