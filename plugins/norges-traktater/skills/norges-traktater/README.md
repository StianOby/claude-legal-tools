# norges-traktater

Skill that lets Claude search and retrieve Norwegian treaties from Lovdata's
public treaty register (*Norges traktater*) — 3 457 agreements Norway is party
to as of September 2026, with year ranges going back to 1661. Covers metadata
(signing date, ratification, entry into force for Norway, parties,
reservations) and, for many conventions, the full Norwegian treaty text.
`status()` reports the current counts, read live from the register.

lovdata.no blocks Anthropic's cloud (HTTP 405), and Cowork runs in the cloud,
so everything goes through the **built-in browser pane**: a helper is pasted
into a tab on lovdata.no and fetches the public treaty pages from there. No
login is needed. See `SKILL.md` for the full workflow guide.

## Layout

```
norges-traktater/
├── SKILL.md
├── README.md
└── scripts/
    └── browser/
        ├── norges_traktater.js  # the helper (window.__nt): search, meta, text,
        │                        # article, countries, status
        └── paste.py             # makes the stripped copy that is pasted (shared file)
```

Offline tests live in the repository at `tests/norges-traktater/`, not in the
plugin (they do not ship to users): `node tests/norges-traktater/test_browser.js`.

## Requirements

- Claude Desktop with Cowork and its built-in browser.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `norges-traktater` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `norges-traktater.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

Then in Cowork: describe the task ("has Norway ratified the
Genocide Convention?", "which treaties did Norway sign with Sweden in 1951?")
and the description in `SKILL.md` will trigger it automatically.

## Quickstart (in the lovdata.no tab, after pasting the helper)

```js
// Search by title keyword ({total, shown, results})
await __nt.search("menneskerett")

// All treaties from a given year
await __nt.search("", {year: 1969})

// Bilateral treaties with a specific country (Norwegian name; validated
// against the register's own list, since Lovdata silently ignores an
// unknown country and returns everything)
await __nt.search("", {country: "Sverige", max: 50})
await __nt.countries("stor")      // valid country values

// Full-text search — many more hits, ordered newest-first, not by relevance
await __nt.search("non-refoulement", {context: "tekst"})

// Metadata for one treaty, or many at once
await __nt.meta("1951-07-28-1")
await __nt.meta(["1951-07-28-1", "1950-11-04-1"])

// Full titles instead of the listing's truncated ones (one fetch per hit)
await __nt.search("", {year: 2003, max: 100, full: true})

// Full Norwegian text, in chunks: call again with {offset: next} until next is null
await __nt.text("1951-07-28-1")

// One specific article (Roman or Arabic numerals, with or without "Artikkel")
await __nt.article("1951-07-28-1", "33")

// Reachability and register counts
await __nt.status()
```

## Notes on scope

- This skill covers Norway's treaty register on **lovdata.no** only.
- The `untc` and `ets` skills each contain massive collections of treaties —
  `untc` covers the UN Treaty Series (tens of thousands of multilateral and
  bilateral agreements, including most multilateral treaties to which Norway is
  a party) and `ets` covers Council of Europe conventions; both overlap
  significantly with this register for Norway's multilateral commitments.
- For the full text of UN-deposited treaties in English/French use the `untc` skill.
- For **EU law / EEA acts** use the `eurlex` skill.
- For **ECtHR case law** (ECHR applications) use the `hudoc` skill.
- For **Norwegian statutes and case law** use `lovdata-api` or `lovdata-pro`.
- If a treaty has no free text on its register page, `text` answers
  `available: false`; `meta` often carries a lovdata.no link to where the text is.
- **The core human rights conventions are the common case here**: the European
  Convention, the two 1966 Covenants, CEDAW and the Convention on the Rights of
  the Child have metadata only in the treaty register, but their full Norwegian
  *and* English texts are free elsewhere on lovdata.no, as appendices to
  menneskerettsloven (`NL/lov/1999-05-21-30`). Fetch them with the
  `lovdata-api` skill, e.g.
  `lovdata.py get "NL/lov/1999-05-21-30" "emkn"` (`emke` for English; `spn`,
  `oskn`, `bkn`, `kdkn`, `crpdn` for the others). The protocols are separate
  sections (`emkn/p1` …) and a single article is `emkn/a8`. Lovdata Pro is the last
  resort, not the first.
