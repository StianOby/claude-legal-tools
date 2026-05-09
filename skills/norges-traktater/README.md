# norges-traktater

Pure-Python skill that lets Claude search and retrieve Norwegian treaties from
Lovdata's public treaty register (*Norges traktater*) — roughly 5 000+ agreements
Norway is party to, from 1814 to the present. Covers metadata (signing date,
ratification, entry into force for Norway, parties, reservations) and, for most
older multilateral conventions, the full Norwegian treaty text.

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
# Search by title keyword
python3 scripts/traktater.py search "menneskerett"

# All treaties from a given year
python3 scripts/traktater.py search "" --year 1969

# Bilateral treaties with a specific country (Norwegian name)
python3 scripts/traktater.py search "" --country Sverige --max 50

# Full-text search (slower — fetches document pages)
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
- If the Norwegian text of a treaty is behind Lovdata Pro, the script will say
  so — fall back to `lovdata-pro` or the depositary source.
