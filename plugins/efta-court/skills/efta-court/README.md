# efta-court

Pure-Python skill that lets Claude find, read and search case law of the
EFTA Court — the court that interprets the EEA Agreement for Norway, Iceland
and Liechtenstein — and the Court's procedural texts. It works over the open
JSON API behind eftacourt.int (`api.eftacourt.int`), so:

- every case can be filtered (country, procedure, status, subject, referring
  court, who submitted observations …),
- full-text search covers every published judgment, hearing report, request
  and order (the Court's own server-side index),
- `cited-by` finds later judgments that cite a case,
- the parties' published written observations can be downloaded,
- the judicial calendar shows hearings, judgment dates and deadlines,
- the Statute, Rules of Procedure, guidance notes and the Surveillance and
  Court Agreement are searchable and kept apart from the case law.

See `SKILL.md` for the full workflow guide. Quick test:

```bash
python3 scripts/efta_court.py case E-14/15
python3 scripts/efta_court.py get E-14/15 --type judgment
python3 scripts/efta_court.py search '"collective action"'
python3 scripts/efta_court.py cited-by E-1/94
python3 scripts/efta_court.py list --pending
python3 scripts/efta_court.py calendar
python3 scripts/efta_court.py texts list
```

## Layout

```
efta-court/
├── SKILL.md
├── README.md
├── scripts/
│   ├── efta_court.py       # the CLI; stdlib only
│   └── source_text.py      # shared text rules (copy of shared/source-text/)
└── evals/
    └── evals.json          # task-eval prompts
```

Offline tests live in the repository at `tests/efta-court/`, not in the plugin
(they do not ship to users): `python tests/efta-court/test_efta_court.py`.

## Requirements

- **Python 3.9+**, no required third-party packages.
- **PDF text extraction:** `pdftotext` from poppler-utils (preferred), or
  `pip install pypdf`. Without either, the CLI still downloads the PDFs.

The cache (API data for an hour, downloaded PDFs and their text) is written to
a user-writable directory, not the skill folder:

1. `$EFTA_COURT_CACHE_DIR` — if set
2. `$XDG_CACHE_HOME/efta-court`
3. `%LOCALAPPDATA%\efta-court` on Windows
4. `~/.cache/efta-court` otherwise

Run `python3 scripts/efta_court.py status` to see the actual path.

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `efta-court` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `efta-court.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

Then in Cowork: describe the task ("find the Holship judgment", "which EFTA
Court judgments cite Restamark?") and the description in `SKILL.md` will
trigger it automatically.

## Notes on scope

- **EFTA Court** case law and procedural texts only (eftacourt.int). Press
  releases are left out.
- For **CJEU / EU law** use the `eurlex` skill; for the EEA status of EU acts
  and Joint Committee Decisions, `eea-lex`.
- For **ECtHR / ECHR case law** use the `hudoc` skill.
- For **Norges Høyesterett** use `lovdata-pro`; for Norwegian statutes,
  `lovdata-api`.
