# lovdata-api — Norsk lovdatabase

A self-contained Claude skill for looking up, citing, and verifying Norwegian
law using [Lovdata's](https://lovdata.no) free data packages. The skill never
cites legislation from training-data recall — every quote is fetched from the
downloaded XML files, which are updated daily.

## What it can do

- Download and keep current Lovdata's two free data packages:
  - **NL** — all current Norwegian laws (about 760 XML files)
  - **SF** — all current central regulations (over 5 000 XML files)
- Search across titles, Lovdata's short titles / abbreviations (`aml`,
  `fvl`, `Grl.`) and document IDs.
- Full-text search across the provisions themselves (`find`), for when the
  law that governs a topic is not known.
- Retrieve the full text of any law or regulation (to stdout or a file).
- Retrieve a single numbered section (paragraph) with amendment history,
  or a whole chapter — or a single convention article from the
  human-rights annexes of menneskerettsloven (`emkn/a8`, `emkn/p1/a1`).
- Accept a document as DokID, `LOV-…`/`FOR-…` reference, lovdata.no URL
  or unambiguous short title; the Grunnloven in bokmål by default and in
  nynorsk with `--nn`.
- Report download status and data freshness.

Local regulations (LF) are not included in the free packages.

## Layout

```
lovdata-api/
├── SKILL.md          # the skill manifest Claude reads
├── README.md         # you are here
├── scripts/
│   └── lovdata.py    # the CLI
└── tests/            # offline regression tests (python tests/test_*.py)
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

# search by keyword or abbreviation (titles, short titles, document IDs)
python scripts/lovdata.py search "arbeidsmiljø"
python scripts/lovdata.py search "aml"

# retrieve a full law by DokID (full texts can be very long; --out writes to a file)
python scripts/lovdata.py get "NL/lov/2005-06-17-62" --out aml.txt

# retrieve a single section
python scripts/lovdata.py get "NL/lov/2005-06-17-62" "§4-6"
# or without the § sign:
python scripts/lovdata.py get "NL/lov/2005-06-17-62" "4-6"

# retrieve a whole chapter
python scripts/lovdata.py get "NL/lov/2005-06-17-62" "kap4"

# other ways to name the document; the § in a URL is used as the section
python scripts/lovdata.py get LOV-2005-06-17-62 4-6
python scripts/lovdata.py get "https://lovdata.no/dokument/NL/lov/2005-06-17-62/§4-6"
python scripts/lovdata.py get aml 4-6

# one article of the ECHR annex of menneskerettsloven (Norwegian text)
python scripts/lovdata.py get NL/lov/1999-05-21-30 emkn/a8

# the Grunnloven in nynorsk
python scripts/lovdata.py get Grunnloven 100 --nn

# full-text search: every word must occur in the provision
python scripts/lovdata.py find "deltid"
python scripts/lovdata.py find "rimelig tid" --phrase
python scripts/lovdata.py find "oppfølgingsplan" aml
```

Section text keeps list markers (`a.`, `b.`, `1.`) so that "annet ledd
bokstav b" can be quoted and located.

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

If the DokID is unknown, use `search` to find it; Lovdata's own short
titles (`Arbeidsmiljøloven – aml`) are indexed, so searching for the
abbreviation usually works.

## Update mechanism

`lovdata.py update` calls `https://api.lovdata.no/v1/publicData/list`
(no authentication) and compares the `lastModified` timestamps against
those recorded in `state.json`. If a package has been updated, the new
tarball is downloaded to a temporary file and extracted into a temporary
directory that replaces the old one only after extraction succeeded, so an
interrupted update never leaves a half-populated data set. The search index
(`data/index.json`) is rebuilt after every update and keyed by path relative
to the data directory, so the directory can be moved. Subsequent runs are
near-instant when nothing has changed.

If the network is down, `update` keeps the data from the last successful
download and prints a warning with its dates; it fails only when there is
no local data at all.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `lovdata-api` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `lovdata-api.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

Then in Cowork: describe the task ("what does aml. § 4-6 say?") and the
trigger description in `SKILL.md` will activate the skill automatically.
