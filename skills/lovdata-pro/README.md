# lovdata-pro — Norsk rettspraksis og forarbeider

A self-contained Claude skill for retrieving Norwegian case law and preparatory
works from [Lovdata Pro](https://lovdata.no/pro/). The skill never paraphrases
from training-data recall — every quote is fetched live from Lovdata's servers
using a saved browser session.

## What it can do

- Fetch Supreme Court decisions (HR-YYYY-NNNN-X, Rt. YYYY s. N)
- Fetch court of appeal decisions (LB/LA/LE/LF/LG/LH-YYYY-N)
- Fetch district court decisions (TR-YYYY-N)
- Fetch preparatory works: NOU, Prop. L, Ot.prp., Innst.
- Run full-text Pro searches
- Output documents as markdown, JSON (with metadata), HTML, or PDF

For current statute and regulation text (gjeldende lov/forskrift), use the
free `lovdata` skill instead.

## Layout

```
lovdata-pro/
├── SKILL.md                        # the skill manifest Claude reads
├── README.md                       # you are here
├── references/
│   └── lovdata-pro-mapping.md      # URL patterns and collection codes
└── scripts/
    └── lovdata_pro.py              # the CLI
```

Session state is written to a writable user directory outside the skill folder:

| Platform | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\lovdata-pro` |
| Linux / macOS | `~/.cache/lovdata-pro` (or `$XDG_CACHE_HOME/lovdata-pro`) |
| Override | Set `$LOVDATA_PRO_DATA_DIR` to any path |

Run `python scripts/lovdata_pro.py status` to see the path in use.

## Requirements

- **Python 3.8+**
- **playwright**, **beautifulsoup4**, **html2text** — install once:

  ```bash
  pip install playwright beautifulsoup4 html2text
  python -m playwright install chromium
  ```

- **Lovdata Pro subscription** — the script logs in using your existing browser
  session; no credentials are stored.
- **Network access** to `lovdata.no`.

## Quickstart

```bash
# first-time login (opens a real browser window)
python scripts/lovdata_pro.py login

# check session status
python scripts/lovdata_pro.py status

# fetch a Supreme Court decision
python scripts/lovdata_pro.py get "HR-2016-2554-P"

# fetch preparatory works
python scripts/lovdata_pro.py get "NOU 2022:8"
python scripts/lovdata_pro.py get "Prop. 107 L (2024-2025)"
python scripts/lovdata_pro.py get "Innst. 521 L (2024-2025)"

# fetch an older Rt. decision
python scripts/lovdata_pro.py get "Rt. 2000 s. 1811"

# write large documents to file (recommended for NOUs and Prop.s)
python scripts/lovdata_pro.py get "NOU 2022:8" -o nou-2022-8.md

# search
python scripts/lovdata_pro.py search "Holship boikott EØS"
python scripts/lovdata_pro.py search "presumsjonsprinsippet" -n 20

# debug: resolve a reference without fetching
python scripts/lovdata_pro.py resolve "HR-2016-2554-P"
```

## Reference formats

| Reference type | Example |
|---|---|
| Modern Supreme Court | `HR-2016-2554-P` |
| Norsk Retstidende (pre-2008) | `Rt. 2000 s. 1811` |
| Court of appeal | `LB-2021-12345`, `LA-2019-67890` |
| District court | `TR-2020-11111` |
| NOU | `NOU 2022:8` |
| Government bill (post-2009) | `Prop. 107 L (2024-2025)` |
| Government bill (pre-2009) | `Ot.prp. nr. 3 (1998-99)` |
| Committee recommendation | `Innst. 521 L (2024-2025)` |
| Raw Pro path | `HRSIV/avgjorelse/hr-2016-2554-p` |

Court codes for lagmannsrett: LB (Borgarting), LA (Agder), LE (Eidsivating),
LF (Frostating), LG (Gulating), LH (Hålogaland).

## Output formats

| Flag | Output |
|---|---|
| *(default)* | Markdown (stdout) |
| `--format json` | `{title, metadata, markdown}` — includes Stikkord, Henvisninger |
| `--format html` | Raw HTML from Lovdata's document body |
| `--format pdf -o file.pdf` | PDF rendered by the browser |

## Login and sessions

The script never stores your password. On first use, run `login` — a real
browser window opens and you complete login (SSO/FEIDE supported). The script
detects the `#myPage` state and saves only the session cookies to
`storage_state.json`. Sessions typically last several weeks; re-run `login`
when they expire.

To revoke the saved session, delete `storage_state.json` from the state
directory shown by `status`.

## Installing as a Claude skill

- macOS / Linux:
  `ln -s /path/to/lovdata-pro ~/.claude/skills/lovdata-pro`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\lovdata-pro" "C:\path\to\lovdata-pro"`

Then describe the task in Claude Code ("what did Høyesterett hold in
HR-2016-2554-P?") and the trigger description in `SKILL.md` will activate the
skill automatically.
