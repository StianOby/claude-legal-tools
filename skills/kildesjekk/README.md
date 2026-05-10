# kildesjekk — Source check for academic legal texts

A Claude skill that verifies every reference and quotation in an academic legal
text against the original sources. The skill checks sources across Zotero,
Lovdata, EUR-Lex, HUDOC, EFTA Court, UNTC, ETS, Norges traktater, and
Nasjonalbiblioteket, then produces an `.xlsx` worklist with per-reference
status, severity-coded discrepancies, and a metadata sheet.

Trigger phrases: **kildesjekk**, **source check**, **check references**,
**verify citations**, **check footnotes** — for an academic article,
manuscript, or thesis (Norwegian or English text).

## What it does

1. Extracts all references and direct quotations from the manuscript (PDF or DOCX).
2. Creates an `.xlsx` worklist (`Kildesjekk_<documentname>.xlsx`) with one row
   per reference and columns for status, quoted text, discrepancy, severity, and
   description.
3. Looks up each source in turn using the tools listed below.
4. Checks quotations verbatim against the original source.
5. Flags discrepancies with severity (`high` / `medium` / `low`) and a short
   label (e.g. *Quotation not verbatim*, *Wrong page/section/paragraph*,
   *Claim not supported*).
6. Colour-codes rows (green / yellow / orange / red / grey) and produces summary
   statistics in the Metadata sheet.

The workflow is resumable: if a worklist file for the document already exists,
the skill picks up where it left off rather than starting over.

## Layout

```
kildesjekk/
├── SKILL.md                          # Skill manifest Claude reads
├── README.md                         # This file
└── references/
    ├── zotero-sql-caselaw.md         # SQL patterns for Norwegian case law in Zotero
    └── zotero-sql-prepworks.md       # SQL patterns for preparatory works in Zotero
```

No scripts — kildesjekk is an orchestrator that delegates to the skills and MCP
servers listed below.

## Dependencies

All of the following must be available in the same Claude session:

**MCP servers**

| MCP | Purpose |
|---|---|
| `lit-lake` | Zotero library (literature, case law, preparatory works) |
| `eurlex` | EU case law and legislation |

**Skills**

| Skill | Purpose |
|---|---|
| `efta-court` | EFTA Court decisions |
| `ets` | Council of Europe treaty database (CETS/ETS) |
| `eurlex` | EUR-Lex fallback for MCP gaps |
| `hudoc` | ECtHR case law |
| `icj` | ICJ and PCIJ case law |
| `lovdata-api` | Norwegian statutes and regulations |
| `lovdata-pro` | Norwegian case law and preparatory works |
| `nbno` | Norwegian books at Nasjonalbiblioteket |
| `norges-traktater` | Treaties to which Norway is a party |
| `untc` | UN treaty database (UNTC/UNTS) |

All skills are available in this repository. Install them alongside kildesjekk
(see below).

## How to use

Trigger the skill by describing the task in plain language (e.g. *"run a
kildesjekk on this manuscript"*), then upload or point to the PDF or DOCX file.
The skill will:

1. Confirm which tools are available.
2. Extract all references and confirm the totals before proceeding.
3. Work through the source check step by step, pausing after each category for
   confirmation unless told to continue without interruption.

For large manuscripts the work may span multiple sessions. Re-upload the same
document and existing worklist file; the skill resumes from the last saved
state.

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `kildesjekk.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.
3. Repeat for each of the dependency skills listed above.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/kildesjekk ~/.claude/skills/kildesjekk`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\kildesjekk" "C:\path\to\kildesjekk"`

Then describe the task in Claude Code and the trigger description in `SKILL.md`
will activate the skill automatically.
