# eu-agreements-treaties — EU treaty status from the Council's database

A Claude skill for the Council of the European Union's
[Treaties Office Database](https://www.consilium.europa.eu/en/documents/treaties-agreements/),
the register of the 2 363 agreements (September 2026) to which the EU, the
EC, the EEC, Euratom or the member states are party. It answers the EU-side
questions — who signed, who has notified or ratified and when, entry into
force, provisional application, declarations and reservations, the Official
Journal reference — using Claude Desktop's built-in browser (Cowork). Every
date and status is read live from the site in the user's own browser tab;
nothing comes from training-data recall.

**This skill requires Claude Desktop with Cowork.** The site sits behind a
Cloudflare browser check that returns 403 to every non-browser client, so
the skill only works through the built-in browser: a helper script is pasted
into a tab on the database and fetches pages from inside that session. It
does not run in Claude Code CLI, and it does not try to get around the
check.

## What it can do

- Search by party, with a real **AND** across parties (the site itself only
  does OR: `Parties=NO&Parties=IS` is the union, 135, not the 42 agreements
  both are party to)
- Filter by signature or entry-into-force date and sort — with the upper
  date bound enforced locally, because the site silently ignores `DateTo`
- Search titles across the whole register in one fetch, then locally
- Show an agreement: signature date and place, entry into force, OJ
  references with an EUR-Lex pointer, observations (where provisional
  application is recorded), and the full ratification table per party with
  the site's "empty cell inherits the agreement date" rule applied
- Fetch a party's declaration or reservation text
- Look up and validate party codes before searching — the site's codes are
  not ISO 3166 (`A` Austria, `D` Germany, `SF` Finland, `IRL` Ireland, `UE`
  the EU, `CE` the European Community, and `EC` is Ecuador), and an unknown
  code returns zero hits with no error

For the text of an agreement, follow the OJ reference with the `eurlex`
skill; for Norway's own ratification and entry into force, use
`norges-traktater`.

## Layout

```
eu-agreements-treaties/
├── SKILL.md                         # the skill manifest Claude reads
├── README.md                        # you are here
├── NOTES.md                         # maintainer notes: Cloudflare finding, fixture checklist
├── data/
│   └── parties.json                 # the site's 256 party codes with short and long names
├── references/
│   └── party-codes.md               # the non-ISO codes, EU entities, collisions
├── scripts/
│   └── browser/
│       └── consilium.js             # pasted into the browser tab via javascript_tool
└── tests/
    ├── run.js                       # parser tests (dev only; npm install && npm test)
    └── fixtures/                    # pages captured from the live site, 2026-09-16
```

There is no session/state directory and nothing is stored: the database is
public, no login is involved, and the helper keeps its cache in the browser
tab's memory only.

## Requirements

- **Claude Desktop** with **Cowork** enabled (the built-in browser tool
  surface, `mcp__Claude_Browser__*`).
- Nothing else. No Python, no packages. (`tests/` uses Node and `linkedom`,
  for maintainers only.)

## Quickstart

The skill drives this itself when triggered from a natural-language request;
this is what it does under the hood, for reference.

```javascript
// In a browser tab parked on
// https://www.consilium.europa.eu/en/documents/treaties-agreements/
// (paste scripts/browser/consilium.js once per tab first)
await __cs.ready()                                   // {ok: true, parties: 256}
await __cs.parties("german")                         // → D
await __cs.search({parties: ["NO"]})                 // 101 rows; OR across several codes
await __cs.search({all: ["NO", "IS"]})               // 42 rows; AND, done locally
await __cs.search({parties: ["NO"], from: "2010", to: "2020", sort: "LSF"})
await __cs.find("schengen")                          // title match over the full register
await __cs.detail("2011036")                         // dates, OJ refs, ratification table
await __cs.declaration("2011036", "A")               // Austria's declaration text
await __cs.items(key, 60)                            // next page of a search
```

No call returns more than 45 000 characters; long results are paged with
`items()` and `page()`. See `SKILL.md` for the full workflow, the database's
traps, error handling and citation format.

## Party codes

| You type | Site meaning | Use instead |
|---|---|---|
| `AT`, `DE`, `FR`, `IT`, `IE`, `HU`, `PT`, `SE`, `FI`, `BE` | not codes | `A`, `D`, `F`, `I`, `IRL`, `H`, `P`, `S`, `SF`, `B` |
| `EU`, `EEC`, `EEA` | not codes | `UE`, `CEE`, `EEE` |
| `EC` | Ecuador | `CE` (European Community) |

The helper stops with a suggestion rather than sending a code the site does
not know. `references/party-codes.md` has the full picture, including
historical parties (`CS`, `SU`, `YU`, `RDA` …) and states that appear under
two codes.

## Installing as a Claude skill

**Recommended — install as a plugin (Claude Cowork):**

1. In Claude Desktop, go to **Customize → Plugins → Add marketplace** and enter
   `StianOby/claude-legal-tools`.
2. Find `eu-agreements-treaties` in the list and click **Install**. Click
   **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `eu-agreements-treaties.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills and Cowork on your plan.

This skill is not installable in Claude Code CLI — describing the task there
("has the EU ratified the aviation agreement with Norway?") will not trigger
it, since the built-in browser tools it depends on don't exist outside
Claude Desktop.

## Notes on scope

- This skill covers the Council's Treaties Office Database only — the EU
  side of a treaty relationship. It holds no treaty text; `detail()` returns
  the OJ reference to open with the `eurlex` skill.
- For Norway's ratification, provisional application, entry into force and
  Stortinget's consent, `norges-traktater` is authoritative; the two
  registers do not always agree, and one Consilium record can cover several
  instruments that Norway's register lists separately.
- For **UN-deposited treaties** use `untc`; for **Council of Europe
  conventions** use `ets`; for **EU legislation and CJEU case law** use
  `eurlex`.
- The 7-digit agreement ID is a registration key, not a year: a quarter of
  Norway's agreements were signed in a different year from the ID prefix.
