# efta-court

Pure-Python skill that lets Claude look up and download case law from the
EFTA Court — the court that interprets the EEA Agreement for Norway, Iceland,
and Liechtenstein. Covers advisory opinions, infringement actions by ESA, and
direct actions brought against ESA.

See `SKILL.md` for the full workflow guide. Quick test:

```bash
python3 scripts/efta_court.py fetch E-14/15
python3 scripts/efta_court.py list --pending --limit 20
python3 scripts/efta_court.py get E-14/15 --type judgment
```

## Layout

```
efta-court/
├── SKILL.md
├── README.md
├── scripts/
│   └── efta_court.py       # single self-contained CLI; stdlib only
├── evals/
│   └── evals.json          # task-eval prompts
└── cache/                  # written to a user dir at runtime (see below)
```

## Requirements

- **Python 3.8+**
- No required third-party packages — the basic flows (index, fetch, search)
  use the standard library only.
- **PDF text extraction** (optional but recommended):
  - `pip install pypdf` — pure-Python, good for modern PDFs.
  - Or install `pdftotext` from `poppler-utils` as a system binary.
    On Debian/Ubuntu: `sudo apt install poppler-utils`.
    On macOS: `brew install poppler`.
  - Without either, the CLI still downloads PDFs; it just can't extract text.

The cache is written to a user-writable directory, not the skill folder
itself (so the skill can be installed read-only):

1. `$EFTA_COURT_CACHE_DIR` — if set
2. `$XDG_CACHE_HOME/efta-court`
3. `%LOCALAPPDATA%\efta-court` on Windows
4. `~/.cache/efta-court` otherwise

Run `python3 scripts/efta_court.py status` to see the actual path.

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `efta-court.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/efta-court ~/.claude/skills/efta-court`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\efta-court" "C:\path\to\efta-court"`

Then in Claude Code or Cowork: describe the task ("find the Holship judgment",
"list pending EFTA Court cases") and the description in `SKILL.md` will
trigger it automatically.

## Quickstart

```sh
# Pull the full case index from the WP REST API (~450 cases)
python3 scripts/efta_court.py update

# Show cache location and freshness
python3 scripts/efta_court.py status

# List the 10 most recent decided cases
python3 scripts/efta_court.py list --decided --limit 10

# All pending cases
python3 scripts/efta_court.py list --pending

# Cases referred from Norway in 2024
python3 scripts/efta_court.py list --year 2024 --country NO

# Fetch case metadata and document list for Holship
python3 scripts/efta_court.py fetch E-14/15

# Download the judgment PDF and extract text
python3 scripts/efta_court.py get E-14/15 --type judgment

# Search by party name
python3 scripts/efta_court.py search "Norway" --party-only

# Free-text search across cached judgment text
python3 scripts/efta_court.py search "state aid" --full-text
```

## Notes on scope

- This skill covers **EFTA Court** case law only (eftacourt.int).
- For **CJEU / EU law** use the `eurlex` skill.
- For **ECtHR / ECHR case law** use the `hudoc` skill.
- For **Norges Høyesterett** use the `lovdata-pro` skill (requires a Lovdata
  Pro subscription); `lovdata-api` is an alternative only if an API key is
  available.
- For Norwegian statutes use `lovdata-api`.
