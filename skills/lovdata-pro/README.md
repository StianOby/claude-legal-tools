# lovdata-pro — Norsk rettspraksis og forarbeider

A Claude skill for retrieving Norwegian case law and preparatory works from
[Lovdata Pro](https://lovdata.no/pro/), using Claude Desktop's built-in
browser (Cowork). The skill never paraphrases from training-data recall —
every quote is fetched live from Lovdata's servers in the user's own,
already-logged-in browser session.

**This skill requires Claude Desktop with Cowork.** It does not run in
Claude Code CLI — there is no built-in browser tool surface there.

## What it can do

- Fetch Supreme Court decisions (HR-YYYY-NNNN-X, Rt. YYYY s. N)
- Fetch court of appeal decisions (LB/LA/LE/LF/LG/LH-YYYY-N)
- Fetch district court decisions (TOSLO-2019-12345, TOSL-2022-123456 —
  Lovdata prefixes the court, and the abbreviations changed with the 2021
  court reform)
- Fetch preparatory works: NOU, Prop. L, Ot.prp., Innst.
- Navigate large documents by table of contents, section, or full-text grep
  instead of dumping the whole thing (judgments usually have no headings, so
  grep and paging are the tools there)
- Run full-text Pro searches from a single JS call
- Write a full local copy to file on request (dump mode)

For current statute and regulation text (gjeldende lov/forskrift), use the
free `lovdata-api` skill instead.

## Layout

```
lovdata-pro/
├── SKILL.md                         # the skill manifest Claude reads
├── README.md                        # you are here
├── references/
│   └── lovdata-pro-mapping.md       # URL patterns, collection codes, DOM notes
└── scripts/
    ├── lovdata_ref.py               # pure Python: citation -> Pro path candidates
    └── browser/
        └── lovdata_pro.js           # pasted into the browser tab via javascript_tool
```

There is no session/state directory and no stored credentials of any kind.
Cowork's built-in browser has its own persistent profile on the user's
machine — the user logs in to Lovdata Pro once in the browser pane, and
cookies persist across turns and conversations the same way they would in
any browser.

## Requirements

- **Claude Desktop** with **Cowork** enabled (the built-in browser tool
  surface, `mcp__Claude_Browser__*`).
- **Python 3.8+** — only for `scripts/lovdata_ref.py`, which has no
  dependencies beyond the standard library.
- **Lovdata Pro subscription**, with the user able to log in interactively
  in the browser pane (SSO/FEIDE supported, same as lovdata.no normally).

## Quickstart

The skill drives this itself when triggered from a natural-language request;
this is what it does under the hood, for reference.

```bash
# Step 1 — resolve a reference to candidate Pro paths (no network access)
python scripts/lovdata_ref.py resolve "HR-2016-2554-P"
python scripts/lovdata_ref.py resolve "NOU 2022:8" --json-array
```

```javascript
// Step 2 — in the browser tab, via javascript_tool:
// (paste scripts/browser/lovdata_pro.js once per tab first)
await __lp.isLoggedIn()
await __lp.load(["HRSIV/avgjorelse/hr-2016-2554-p", "HRSTR/avgjorelse/hr-2016-2554-p"])
await __lp.section("HRSIV/avgjorelse/hr-2016-2554-p", 3)
await __lp.grep("NOU/forarbeid/nou-2022-8", "urfolk")
await __lp.page("PROP/forarbeid/otprp-3-199899", 0)
```

`grep` matches its term literally by default (so `§ 4-6 (2)` works); pass a
fifth argument `true` for a real regular expression. `page` never returns
more than `PAGE_SIZE` characters.

```javascript
// Search: one call. Lovdata's GWT search submits on a synthetic `keyup`,
// which is what search() dispatches; if it times out, the fallback is to
// type the query with the computer tool, click the 🔍 button, and read the
// rendered results back with readSearchResults().
await __lp.search("Rt-2000-1811", 10)
await __lp.readSearchResults(10)
```

See `SKILL.md` for the full workflow, error handling, and citation format.

## Reference formats

| Reference type | Example |
|---|---|
| Modern Supreme Court | `HR-2016-2554-P` |
| Norsk Retstidende (pre-2008) | `Rt. 2000 s. 1811` (needs search — see below) |
| Court of appeal | `LB-2021-12345`, `LA-2019-67890` |
| District court | `TOSLO-2019-12345` (pre-2021), `TOSL-2022-123456` (post-reform) |
| NOU | `NOU 2022:8` |
| Government bill (post-2009) | `Prop. 107 L (2024-2025)` |
| Government bill (pre-2009) | `Ot.prp. nr. 3 (1998-99)` |
| Committee recommendation | `Innst. 521 L (2024-2025)` |
| Raw Pro path | `HRSIV/avgjorelse/hr-2016-2554-p` |

Court codes for lagmannsrett: LB (Borgarting), LA (Agder), LE (Eidsivating),
LF (Frostating), LG (Gulating), LH (Hålogaland). District-court references
carry an abbreviation of the court itself (`TOSLO` Oslo, `TBERG` Bergen,
`TSTAV` Stavanger …), shortened again after the 2021 court reform (`TOSL`);
the resolver accepts any `T<letters>-YYYY-N` form and maps it to the
`TRSIV`/`TRSTR` collections.

Pre-2008 Rt. decisions, RG decisions, stortingsmeldinger (whose slugs carry
a Lovdata-assigned sequence number) and other irregular citations don't have
a deterministic slug — `lovdata_ref.py resolve` returns `parsed: false` for
these, together with a `search_hint` in Lovdata's own reference form and a
note on where that document type lives, and the skill falls back to
`__lp.search()`.

## Login and sessions

The skill never sees or stores a password. The user logs in to Lovdata Pro
directly in the Cowork browser pane (SSO/FEIDE supported); Claude only
checks `__lp.isLoggedIn()` and waits for confirmation. Sessions persist in
the browser's own profile the same way they would in any browser — there is
nothing for the skill to save or expire on its end. When a session does
expire (Lovdata's own timeout, typically some weeks), `isLoggedIn()` catches
it and the skill asks the user to log in again.

## Installing as a Claude skill

1. Download the latest `lovdata-pro.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills and Cowork on your plan.

This skill is not installable in Claude Code CLI — describing the task there
("what did Høyesterett hold in HR-2016-2554-P?") will not trigger it, since
the built-in browser tools it depends on don't exist outside Claude Desktop.
