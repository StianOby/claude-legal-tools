# hudoc skill

Pure-Python skill that lets Claude lookup and download European Court of
Human Rights case law from the HUDOC database — text, PDF/DOCX, structured
metadata, and citation chains.

See `SKILL.md` for the full workflow guide. Quick test:

```bash
python3 scripts/hudoc.py fetch "Soering v. UK" --format text
python3 scripts/hudoc.py search '(article:"8") AND (respondent:"NOR") AND (doctypebranch:GRANDCHAMBER)' -n 5
python3 scripts/hudoc.py citations "Big Brother Watch v. UK"
```

## Layout

```
hudoc/
├── SKILL.md
├── README.md
├── scripts/
│   └── hudoc.py            # single self-contained CLI; stdlib only
├── references/
│   └── query-fields.md     # HUDOC Lucene query syntax + field reference
├── evals/
│   ├── evals.json          # task-eval prompts (lookup, search, citations)
│   └── trigger_evals.json  # description-optimization triggering tests
└── cache/
    └── items/<itemid>/     # populated on first fetch
```

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `hudoc.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/hudoc ~/.claude/skills/hudoc`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\hudoc" "C:\path\to\hudoc"`

Then in Claude Code or Cowork: describe the task ("find Soering v UK")
and the description in `SKILL.md` will trigger it.

## Inspired by

The metadata field set, document type codes, and the idea of using DOCX as
the canonical text source were inspired by the maastrichtlawtech
[`echr-extractor`](https://github.com/maastrichtlawtech/echr-extractor)
library. This skill is narrower (interactive lookup + filtered search,
not corpus extraction) and standalone (no third-party Python deps).

## API notes

HUDOC has no official API. The skill uses two undocumented but stable
endpoints:

- `GET /app/query/results` — JSON metadata + Lucene-style search.
  **Requires** the `X-Requested-With: XMLHttpRequest` header — without it
  the CDN serves a generic 404.
- `GET /app/conversion/{docx,pdf}/?library=ECHR&id=<itemid>` —
  document download. No auth.

If either endpoint stops working, smoke-test with curl:

```bash
curl -H "X-Requested-With: XMLHttpRequest" \
  "https://hudoc.echr.coe.int/app/query/results?query=(contentsitename=ECHR)+AND+(itemid:%22001-57619%22)&select=itemid,docname,appno&start=0&length=1"
```

A working response is a `{"resultcount":1,"results":[...]}` JSON blob.
