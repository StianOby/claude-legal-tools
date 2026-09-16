# claude-legal-tools

A collection of Claude Code skills for working with legal and library sources
(Lovdata, EUR-Lex, HUDOC, ICJ, Nasjonalbiblioteket, etc.).

## Skill authoring rules

### Description length limit: 1024 characters

Every `SKILL.md` frontmatter `description:` field must be **≤ 1024 characters
after YAML parsing** (i.e. the joined string the loader sees, not the raw
source with line breaks and indentation). Skills with longer descriptions are
rejected by the loader.

This has been a recurring problem in this repo. When writing or editing a
description:

- Pack the trigger list densely — list keywords/identifiers as a
  comma-separated group, not as separate "or" clauses.
- Cut redundant phrasings of the same trigger (e.g. don't include both
  "fetch this old Norwegian newspaper" and "save these pages from
  Nasjonalbiblioteket" — one example per category is enough).
- Keep the structure: (1) when to use, (2) trigger keywords/URL patterns,
  (3) scope of material covered, (4) any sub-workflow variants, (5) what NOT
  to use it for.
- Verify before committing:

  ```bash
  python3 -c "
  import yaml, sys
  text = open(sys.argv[1]).read()
  fm = text.split('---', 2)[1]
  print(len(yaml.safe_load(fm)['description']))
  " plugins/<name>/skills/<name>/SKILL.md
  ```

  The number printed must be ≤ 1024. CI (`.github/workflows/validate.yml`)
  runs the same check on every PR.

## Repository layout

The repo is a Claude plugin marketplace (`.claude-plugin/marketplace.json`).
Each skill is its own plugin:

```
plugins/<name>/
  .claude-plugin/plugin.json   # manifest; holds the version
  .mcp.json                    # optional bundled MCP servers (eurlex only)
  skills/<name>/SKILL.md       # the skill; scripts/, references/ … beside it
```

Rules:

- A skill lives at `plugins/<name>/skills/<name>/` — the plugin name and the
  skill name are always the same. The `skills` path must be a *parent* of the
  `SKILL.md` directory, which is why there are two levels.
- **Every commit that touches a plugin's files must bump `version` in
  `plugins/<name>/.claude-plugin/plugin.json`.** Claude Code caches plugins by
  version and users only receive updates when it changes. (Cowork's Update
  re-fetches the repo regardless of version — verified 2026-09-12 — so the
  bump is for Claude Code users.) This is automated:
  - `.githooks/pre-commit` bumps the patch version of every plugin with
    staged changes. Enable it once per clone with
    `git config core.hooksPath .githooks`. Bump minor/major by hand for
    notable changes; the hook leaves a manually changed version alone.
  - CI (`validate.yml` → `.github/scripts/check-plugin-versions.sh`) fails a
    PR or push where a plugin changed without a version change.
- Never put `version` in the marketplace.json entries — it belongs in
  `plugin.json` only.
- Add new plugins to `.claude-plugin/marketplace.json` with
  `"source": "./plugins/<name>"` (explicit path; do not rely on
  `metadata.pluginRoot`, which needs a recent Claude Code and is not
  documented for Cowork). If a plugin is ever renamed, add a `renames` entry.
- The release workflow zips `plugins/<name>/skills/<name>/` so the `.zip`
  layout stays identical to the pre-marketplace releases.
- Validate locally with `npx -y @anthropic-ai/claude-code plugin validate .`
  and `… plugin validate plugins/<name> --strict`.

## Cached data snapshots

Some skills ship data fetched from a live source (the untc and ets treaty
indexes, the eu-agreements-treaties party list). Users get whatever was
checked in, so these go stale silently. `snapshots.json` at the repo root
lists every such file with its source, `last_refreshed` date and refresh
command; `.github/scripts/snapshots.py` keeps them honest.

The routine — no fixed schedule, just a check whenever the skills are
being worked on:

1. **At the start of any session that will change files under `plugins/`,
   run `.github/scripts/snapshots.py check`.** The pre-commit hook and CI
   run the same check and print a warning for anything older than
   `max_age_days` (30); neither blocks.
2. If a snapshot is stale and has a `refresh` command, refresh it with
   `.github/scripts/snapshots.py refresh <name>` (or `--all`). The script
   runs the command, prints the before/after record count, refuses to stamp
   if the count dropped by more than 10 % (a partial fetch), and writes
   today's date into `snapshots.json`. Commit the data, the manifest and
   the plugin's version bump together as their own commit —
   `<plugin>: refresh <name> snapshot (YYYY-MM-DD, N records)` — separate
   from whatever feature work prompted the session.
3. If a snapshot has `"refresh": null`, it needs a manual procedure
   (`refresh_manual`; currently `eu-agreements-parties`, which can only be
   captured from the Cowork built-in browser). Tell the user it is due and
   how; do not silently skip it. After the manual refresh, run
   `.github/scripts/snapshots.py mark <name>`.
4. Do not refresh a snapshot that is not stale unless asked; a refresh is a
   network fetch and a data diff, not part of ordinary edits.

When a skill gains a new checked-in file that is generated from a live
source, add an entry to `snapshots.json` in the same commit — `path`,
`source`, `last_refreshed`, and either a `refresh` shell command (run from
the repo root, must leave the file in place) or `refresh: null` plus a
`refresh_manual` description. Hand-written reference tables
(`references/*.md`) are not snapshots.
