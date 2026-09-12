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
  version and users only receive updates when it changes. (Whether Cowork's
  update check also keys on the version is undocumented — bumping covers both
  cases.) This is automated:
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
