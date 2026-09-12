# norges-traktater

Pure-Python skill that lets Claude search and retrieve Norwegian treaties from
Lovdata's public treaty register (*Norges traktater*) — 3 457 agreements Norway
is party to as of September 2026, with year ranges going back to 1661. Covers
metadata (signing date, ratification, entry into force for Norway, parties,
reservations) and, for many conventions, the full Norwegian treaty text.
`status` prints the current counts, read live from the register.

See `SKILL.md` for the full workflow guide. Quick test:

```bash
python3 scripts/traktater.py search "Wien"
python3 scripts/traktater.py meta 1950-11-04-1
python3 scripts/traktater.py text 1951-07-28-1
```

## Layout

```
norges-traktater/
├── SKILL.md
├── README.md
└── scripts/
    └── traktater.py    # single self-contained CLI; stdlib only
```

## Requirements

- **Python 3.8+**
- No third-party packages — stdlib only.

The cache is written to a user-writable directory, not the skill folder
itself (so the skill can be installed read-only):

1. `$NORGES_TRAKTATER_DATA_DIR` — if set
2. `$XDG_CACHE_HOME/norges-traktater`
3. `%LOCALAPPDATA%\norges-traktater` on Windows
4. `~/.cache/norges-traktater` otherwise

Run `python3 scripts/traktater.py status` to see the actual path.

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `norges-traktater.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/norges-traktater ~/.claude/skills/norges-traktater`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\norges-traktater" "C:\path\to\norges-traktater"`

Then in Claude Code or Cowork: describe the task ("has Norway ratified the
Genocide Convention?", "which treaties did Norway sign with Sweden in 1951?")
and the description in `SKILL.md` will trigger it automatically.

## Quickstart

```sh
# Search by title keyword (prints "showing N of M hits")
python3 scripts/traktater.py search "menneskerett"

# All treaties from a given year
python3 scripts/traktater.py search "" --year 1969

# Bilateral treaties with a specific country (Norwegian name; validated
# against the register's own list, since Lovdata silently ignores an
# unknown country and returns everything)
python3 scripts/traktater.py search "" --country Sverige --max 50
python3 scripts/traktater.py countries stor      # valid --country values

# Full-text search — many more hits, ordered newest-first, not by relevance
python3 scripts/traktater.py search "non-refoulement" --context tekst

# Metadata for one treaty (signing/ratification dates, parties, reservations)
python3 scripts/traktater.py meta 1951-07-28-1

# Full Norwegian text
python3 scripts/traktater.py text 1951-07-28-1

# One specific article (Roman or Arabic numerals, with or without "Artikkel")
python3 scripts/traktater.py article 1951-07-28-1 33

# Show cache location and network status
python3 scripts/traktater.py status
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
- If a treaty has no free text on its register page, the script says so and
  prints any lovdata.no link Lovdata itself gives for the document.
- **The core human rights conventions are the common case here**: the European
  Convention, the two 1966 Covenants, CEDAW and the Convention on the Rights of
  the Child have metadata only in the treaty register, but their full Norwegian
  *and* English texts are free elsewhere on lovdata.no, as appendices to
  menneskerettsloven (`NL/lov/1999-05-21-30`). Fetch them with the
  `lovdata-api` skill, e.g.
  `lovdata.py get "NL/lov/1999-05-21-30" "emkn"` (`emke` for English; `spn`,
  `oskn`, `bkn`, `kdkn`, `crpdn` for the others). Lovdata Pro is the last
  resort, not the first.
