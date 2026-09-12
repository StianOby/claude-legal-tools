# ets

Talks to the Council of Europe Treaty Office's JSON backend at
`conventions-ws.coe.int` to download ETS / CETS treaty source
documents:

1. Treaty text (PDF on `rm.coe.int`)
2. Explanatory Report (PDF on `rm.coe.int`)
3. Chart of signatures and ratifications per state
4. Declarations and reservations (full text per state)

See `SKILL.md` for the full description, triggers, and CLI table.

Downloads are cached outside the skill folder, in `$ETS_CACHE_DIR` if
set and otherwise `~/.cache/ets`. The bundled `data/index.json` seeds
that cache so the first lookup needs no network call; a treaty number
missing from it triggers an automatic refresh from the live API.

## Layout

```
ets/
  SKILL.md                 # Skill description and usage policy
  README.md                # This file
  requirements.txt         # Optional Python dependency (pypdf)
  data/
    index.json             # Bundled snapshot of the master treaty index (~230 records)
  evals/
    trigger_evals.json     # Trigger evaluation test cases
  scripts/
    coe.py                 # Self-contained CLI
```

## Requirements

- **Python 3.8+**
- **`pdftotext`** (from `poppler-utils`) is strongly preferred for
  column-aware PDF extraction. On Debian/Ubuntu:
  `sudo apt install poppler-utils`. On macOS: `brew install poppler`.
- If `pdftotext` is unavailable, `pip install pypdf` provides a
  fallback (with worse table extraction).

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `ets` and click
  **Install**. Click **Update** on the marketplace later to get new versions.
- *Claude Code:* `/plugin marketplace add StianOby/claude-legal-tools`, then
  `/plugin install ets@claude-legal-tools`.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `ets.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code, for development):**

- macOS / Linux:
  `ln -s /path/to/ets ~/.claude/skills/ets`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\ets" "C:\path\to\ets"`

Then in Claude Code: ask about any ETS/CETS convention by name or
number ("get me the ECHR", "CETS 210 signatures") and the trigger
description in `SKILL.md` will activate the skill automatically.

## Quickstart

```sh
# Build the master treaty index (one POST, ~230 records)
python3 scripts/coe.py index

# Resolve a name to a number + download all four artefacts
python3 scripts/coe.py fetch ECHR

# Just the text PDF for one treaty
python3 scripts/coe.py text 210

# Just the chart of signatures
python3 scripts/coe.py signatures 005

# Search the cached index
python3 scripts/coe.py lookup "data protection"
```

## Why the SSL workaround?

`conventions-ws.coe.int` still serves a 1024-bit DH key. Modern
OpenSSL 3 refuses it by default. The CLI sets
`SSL_CONTEXT.set_ciphers("DEFAULT@SECLEVEL=0")` for its own requests —
no global config change required. The same context is also used for
`rm.coe.int` (the document host): it sits behind Cloudflare, which
returns 403 to Python's default TLS client hello but accepts this one.
Certificate verification is not disabled in either case.

## Notes on scope

- This skill handles the numbered ETS / CETS series. Bilateral CoE
  agreements and partial-agreements (EUR-OPA, GRECO statute, etc.)
  live at separate `api/AccordPartiel/...` endpoints; the SKILL.md
  *Extending later* section sketches how to add them.
- This skill does **not** retrieve ECtHR (Strasbourg court)
  judgments — those are case law, not treaty text. Use a dedicated
  HUDOC skill or web search for those.
- This skill does **not** retrieve EU law (use `eurlex`) or
  UN-deposited treaties (use `untc`).
- Norwegian law — use `lovdata` / `lovdata-pro`.
