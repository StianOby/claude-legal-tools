# lovdata-api — Norsk lovdatabase

A self-contained Claude skill for looking up, citing, and verifying Norwegian
law using [Lovdata's](https://lovdata.no) free data packages. The skill never
cites legislation from training-data recall — every quote is fetched from the
downloaded XML files, which are updated daily.

## What it can do

- Download and keep current Lovdata's two free data packages:
  - **NL** — all current Norwegian laws (782 XML files)
  - **SF** — all current central regulations (3 733 XML files)
- Search across titles and document IDs.
- Retrieve the full text of any law or regulation.
- Retrieve a single numbered section (paragraph) with amendment history.
- Report download status and data freshness.

Local regulations (LF) are not included in the free packages.

## Layout

```
lovdata-api/
├── SKILL.md          # the skill manifest Claude reads
├── README.md         # you are here
└── scripts/
    └── lovdata.py    # the CLI
```

Data and state are written to a writable user directory outside the skill
folder (the skill folder is often read-only when installed as a plugin):

| Platform | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\lovdata` |
| Linux / macOS | `~/.cache/lovdata` (or `$XDG_CACHE_HOME/lovdata`) |
| Override | Set `$LOVDATA_DATA_DIR` to any path |

Run `python scripts/lovdata.py status` to see the path in use.

## Requirements

- **Python 3.8+** — no third-party packages required (uses `urllib` and the
  standard library only).
- Network access to `api.lovdata.no` and `lovdata.no` for the initial
  download and daily update checks (~6 MB for laws, ~21 MB for regulations).

## Quickstart

```bash
# download / update both packages (safe to run repeatedly — skips if current)
python scripts/lovdata.py update

# check what is downloaded and when
python scripts/lovdata.py status

# search by keyword (searches titles and document IDs)
python scripts/lovdata.py search "arbeidsmiljø"

# retrieve a full law by DokID
python scripts/lovdata.py get "NL/lov/2005-06-17-62"

# retrieve a single section
python scripts/lovdata.py get "NL/lov/2005-06-17-62" "§4-6"
# or without the § sign:
python scripts/lovdata.py get "NL/lov/2005-06-17-62" "4-6"
```

## DokID format

| Source | Format | Example |
|---|---|---|
| Norwegian law | `NL/lov/YYYY-MM-DD-NNN` | `NL/lov/2005-06-17-62` |
| Central regulation | `SF/forskrift/YYYY-MM-DD-NNN` | `SF/forskrift/1996-12-06-1127` |

Common laws and their short-form IDs:

| Short form | DokID |
|---|---|
| aml. (arbeidsmiljøloven) | `NL/lov/2005-06-17-62` |
| fvl. (forvaltningsloven) | `NL/lov/1967-02-10` |
| offl. (offentleglova) | `NL/lov/2006-05-19-16` |
| strl. (straffeloven) | `NL/lov/2005-05-20-28` |
| strpl. (straffeprosessloven) | `NL/lov/1981-05-22-25` |
| tvl. (tvisteloven) | `NL/lov/2005-05-20-25` |
| pasientrettighetsloven | `NL/lov/1999-07-02-63` |
| helsepersonelloven | `NL/lov/1999-07-02-64` |
| internkontrollforskriften (HMS) | `SF/forskrift/1996-12-06-1127` |

If the DokID is unknown, use `search` to find it.

## Update mechanism

`lovdata.py update` calls `https://api.lovdata.no/v1/publicData/list`
(no authentication) and compares the `lastModified` timestamps against
those recorded in `state.json`. If a package has been updated, the new
tarball is downloaded and extracted. Subsequent runs are near-instant when
nothing has changed.

## With an API key

If `api_key` is set in `state.json`, the script gains access to additional
Lovdata endpoints (live search, history, etc.). Keys are not yet generally
available; the free packages cover all current statute text.

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `lovdata-api.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/lovdata-api ~/.claude/skills/lovdata-api`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\lovdata-api" "C:\path\to\lovdata-api"`

Then in Claude Code: describe the task ("what does aml. § 4-6 say?") and the
trigger description in `SKILL.md` will activate the skill automatically.
