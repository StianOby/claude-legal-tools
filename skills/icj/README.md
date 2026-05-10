#  ICJ/PCIJ skill

## What the skill does

Three things, all rooted at icj-cij.org:

1. **Case law** — ICJ contentious + advisory cases (`/list-of-all-cases`, `/case/<N>`, `/decisions`) and PCIJ Series A/B/A/B (judgments and advisory opinions, 1922-1940).
2. **Jurisdiction** — the seven `/index.php/...` pages: states-entitled-to-appear, states-not-members, states-not-parties, basis-of-jurisdiction, treaties, organs-agencies-authorized, declarations.
3. **Article 36(2) declarations** — the verbatim text of every state's optional-clause declaration, accessible by name or ISO-2 code; supports `compare` for side-by-side reading.

Pleadings and verbatim records are deliberately excluded — a separate skill is better for those.

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `icj.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

See [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
for full details, including how to enable Skills on your plan.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux:
  `ln -s /path/to/icj ~/.claude/skills/icj`
- Windows:
  `mklink /D "%USERPROFILE%\.claude\skills\icj" "C:\path\to\icj"`

## CLI

```
python scripts/icj.py --help
python scripts/icj.py declarations compare no fi      # the worked example
python scripts/icj.py cases search "nicaragua"
python scripts/icj.py pcij show A10                   # Lotus
python scripts/icj.py status                          # cache freshness
python scripts/icj.py refresh                         # update changed pages
```

Requires `requests` and `beautifulsoup4`:

```
pip install requests beautifulsoup4
```

## Cache

`data/cache/` holds scraped HTML keyed by URL with a manifest tracking
`fetched_at`, `Last-Modified`, `ETag`, and a SHA-256 of the body.
`status` does HEAD requests against the cached URLs to flag changes;
`refresh` re-downloads anything stale (or `--all` for everything). Default
TTL: 14 days.
