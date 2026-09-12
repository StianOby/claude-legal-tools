# Plan: turn this repo into a plugin marketplace

Status: **merged and live** (PR #1, 2026-09-12; release `skills-2026.09.12-105`).
Cowork verified: marketplace lists all eleven plugins, eurlex's bundled MCP
server and hudoc's `scripts/` work; `dependencies` is **not** honoured. See §11.

Goal: let Cowork (and Claude Code) users install the skills in this repo as
plugins via "Add marketplace → `StianOby/claude-legal-tools`", while keeping the
existing per-skill `.zip` GitHub Releases for users who upload skills by file.

Decisions:

- **One plugin per skill** — final (see §9). The ten retrieval skills are
  useful on their own, future meta-skills besides kildesjekk will depend on
  subsets of them, and Claude Code users should not pay context tokens for
  skills they don't need.
- **Keep the zip release workflow.**
- **Explicit `./plugins/<name>` sources**, not `metadata.pluginRoot` (§3).

## 1. Cowork support (verified against docs 2026-09-12)

- Cowork supports custom Git marketplaces: Customize → Plugins → **Add
  marketplace** → `owner/repo` or `https://github.com/owner/repo`. **Update** on
  the marketplace pulls the latest repo state.
  <https://claude.com/docs/cowork/guide/plugins>
- Available as a beta for **all paid Claude users** (Pro/Max included); plugins
  are stored locally on the machine.
  <https://claude.com/docs/plugins/overview>
- Same `.claude-plugin/marketplace.json` + `plugin.json` format as Claude Code.
  Reference example: <https://github.com/anthropics/knowledge-work-plugins>
  (relative `./dir` sources, no versions).
- Cowork supports skills, MCP connectors, agents, hooks, slash commands, and
  lets users **enable/disable individual skills inside a plugin**.
- Limits: 200 MB per plugin, 512 MB repo archive, 25 marketplaces per user.

Caveats:

1. Personal-tab "Add marketplace" was reported missing in June 2026
   (<https://github.com/anthropics/claude-code/issues/66184>). **Verified
   present 2026-09-12.**
2. Plugin `dependencies` (auto-install of required plugins) is documented for
   Claude Code only. **Verified 2026-09-12: Cowork ignores it** — installing
   kildesjekk does not install the ten retrieval plugins. The README and
   kildesjekk README tell Cowork users to install them by hand; the field is
   kept for Claude Code. Re-test occasionally; drop the manual-install wording
   if Cowork starts honouring it.
3. **Verified 2026-09-12: Cowork's "Update" re-fetches the repo regardless of
   `plugin.json` version** (a README change committed without a bump arrived
   after clicking Update). Versions therefore only matter for Claude Code,
   which caches by version; the automatic bump in §5 exists for that.
4. Private repos need org-managed marketplaces via the Claude GitHub App. This
   repo is public, so not relevant.

## 2. Target layout

```
.claude-plugin/
  marketplace.json                 # NEW — marketplace catalogue
plugins/
  efta-court/
    .claude-plugin/plugin.json     # NEW
    skills/efta-court/             # git mv skills/efta-court → here
      SKILL.md, README.md, scripts/, evals/ …
  ets/  hudoc/  icj/  lovdata-api/  lovdata-pro/  nbno/  norges-traktater/  untc/
  eurlex/
    .claude-plugin/plugin.json
    .mcp.json                      # NEW — bundles the eurlex MCP server
    skills/eurlex/
  kildesjekk/
    .claude-plugin/plugin.json     # declares dependencies on the 10 above
    skills/kildesjekk/
docs/
  MARKETPLACE-PLAN.md              # this file
```

Why `plugins/<name>/skills/<name>/`: plugin component paths must stay inside
the plugin root, and a `skills` path must be a *parent* directory of
`<name>/SKILL.md`. So every skill sits one level below its plugin root.

Nothing inside the SKILL.md files changes: `python3 scripts/x.py` references
are relative to the skill directory and resolve the same way. Every SKILL.md
already sets `name:` in frontmatter, so invocation names stay stable.

Use `git mv` so `git log --follow` keeps working.

## 3. `.claude-plugin/marketplace.json`

```json
{
  "name": "claude-legal-tools",
  "owner": { "name": "Stian Øby Johansen", "url": "https://github.com/StianOby" },
  "description": "Skills for retrieving and verifying legal sources: Lovdata, EUR-Lex, HUDOC, ICJ, EFTA Court, UNTC, ETS, Norges traktater, Nasjonalbiblioteket.",
  "plugins": [
    { "name": "efta-court", "source": "./plugins/efta-court", "description": "EFTA Court judgments", "category": "legal-research", "keywords": ["efta", "eea", "case-law"] },
    { "name": "ets", "source": "./plugins/ets", "description": "Council of Europe treaty series", "category": "legal-research" },
    { "name": "eurlex", "source": "./plugins/eurlex", "description": "EU legislation and case law from EUR-Lex (bundles the eurlex MCP server)", "category": "legal-research" },
    { "name": "hudoc", "source": "./plugins/hudoc", "description": "European Court of Human Rights judgments from HUDOC", "category": "legal-research" },
    { "name": "icj", "source": "./plugins/icj", "description": "ICJ and PCIJ case law, jurisdiction data, and Article 36(2) declarations", "category": "legal-research" },
    { "name": "lovdata-api", "source": "./plugins/lovdata-api", "description": "Norwegian legislation from Lovdata (free content)", "category": "legal-research" },
    { "name": "lovdata-pro", "source": "./plugins/lovdata-pro", "description": "Norwegian case law and preparatory works from Lovdata Pro", "category": "legal-research" },
    { "name": "nbno", "source": "./plugins/nbno", "description": "Documents from the National Library of Norway (Nasjonalbiblioteket)", "category": "legal-research" },
    { "name": "norges-traktater", "source": "./plugins/norges-traktater", "description": "Norway's treaty register", "category": "legal-research" },
    { "name": "untc", "source": "./plugins/untc", "description": "UN Treaty Collection — treaty texts and ratification status", "category": "legal-research" },
    { "name": "kildesjekk", "source": "./plugins/kildesjekk", "description": "Source-check an academic legal text against all retrieval skills; produces an .xlsx worklist", "category": "legal-research" }
  ]
}
```

Leave `version` out of the marketplace entries; put it in each `plugin.json`
so there is one place to bump. (Docs: setting it in both places makes Claude
Code silently prefer `plugin.json`.)

Sources are written out as `./plugins/<name>` rather than bare names under
`metadata.pluginRoot`: bare names need Claude Code ≥ 2.1.239 and the Cowork
docs don't mention `pluginRoot`. Anthropic's own knowledge-work-plugins repo
uses explicit relative paths too.

## 4. `plugin.json` per plugin

Template for the ten retrieval plugins:

```json
{
  "name": "hudoc",
  "version": "1.0.0",
  "description": "European Court of Human Rights judgments from HUDOC",
  "author": { "name": "Stian Øby Johansen" },
  "homepage": "https://github.com/StianOby/claude-legal-tools/tree/main/plugins/hudoc",
  "license": "GPL-3.0"
}
```

`LICENSE` is GPL v3 → SPDX `GPL-3.0-only`. Do **not** add `"skills": "./skills"`
to `plugin.json`: the default `skills/` directory is always scanned, and a
declared path is loaded *in addition* to it.

kildesjekk additionally declares:

```json
"dependencies": ["efta-court", "ets", "eurlex", "hudoc", "icj", "lovdata-api", "lovdata-pro", "nbno", "norges-traktater", "untc"]
```

Claude Code auto-installs these when kildesjekk is enabled. **If Cowork
ignores `dependencies`** (test in step 7.3), fallback options:

- README tells Cowork users to install all eleven plugins (one click each); or
- a script generates a committed `plugins/legal-tools/` bundle plugin containing
  copies of all skills, regenerated on release.

## 5. eurlex: bundle the MCP server

`skills/eurlex/SKILL.md` currently tells the user to add the server by hand.
Ship `plugins/eurlex/.mcp.json` instead:

```json
{ "mcpServers": { "eurlex": { "command": "npx", "args": ["-y", "eurlex-mcp-server"] } } }
```

Plugin-provided MCP servers get a different tool-name prefix than a
user-configured server: `mcp__plugin_<plugin>_<server>__<tool>`, i.e.
`mcp__plugin_eurlex_eurlex__eurlex_*` (Claude Code plugins reference). SKILL.md
now names both prefixes and keeps the "if the tools are missing, tell the
user" fallback for zip-installed users, who get no `.mcp.json`. Whether Cowork
uses the same prefix is unverified — check during 7.4.

## 6. CI

### Update `.github/workflows/release-skills.yml`

- Trigger path `plugins/**` instead of `skills/**`.
- Package loop so zip contents stay identical to today (skill dir at zip root):

  ```bash
  for p in plugins/*/; do
    name=$(basename "$p")
    (cd "$p/skills/$name" && zip -r "$GITHUB_WORKSPACE/$name.zip" . \
       -x '*__pycache__*' '*.pyc' 'evals/*')
  done
  ```

### New `.github/workflows/validate.yml` (pull_request + push)

- `npm i -g @anthropic-ai/claude-code`, then
  `claude plugin validate plugins/<each> --strict` and
  `claude plugin validate .` for the marketplace.
- The description-length check from `CLAUDE.md`, looped over
  `plugins/*/skills/*/SKILL.md` — turns the recurring ≤1024-char problem into a
  failing PR instead of a thing to remember.
- A consistency check: every `plugins/*` directory has a marketplace entry
  with `source: ./plugins/<name>`, matching `plugin.json` name, and no
  `version` in the marketplace entry.
- Version guard: `.github/scripts/check-plugin-versions.sh` fails if files
  under `plugins/<p>/` changed (vs. the PR base, or the last `skills-*` tag on
  push) but the `plugin.json` version did not. The bump itself is automated
  by the tracked `.githooks/pre-commit` hook (patch bump per changed plugin;
  enable with `git config core.hooksPath .githooks`). Release notes list the
  version of every plugin.

## 7. Migration order

1. Commit the currently uncommitted kildesjekk / nbno / norges-traktater
   changes so the move commit is clean.
2. `git mv skills/<x> plugins/<x>/skills/<x>` for all 11 — one commit, no
   content changes.
3. Add the 11 `plugin.json` files, `plugins/eurlex/.mcp.json`, and
   `.claude-plugin/marketplace.json`.
4. Local test — **Cowork first**: Customize → Plugins → Add marketplace →
   `StianOby/claude-legal-tools` (or a branch, if Cowork accepts refs; otherwise
   push to main). Install kildesjekk (checks whether `dependencies` is
   honoured) and eurlex (checks the MCP prefix). Confirm skills trigger and
   `python3 scripts/…` resolves. Then the same in Claude Code:
   `/plugin marketplace add ./` from the repo root.
5. Update the release workflow, add the validate workflow, push to a branch,
   confirm CI is green and the release zips have the same internal structure
   as before.
6. Docs (§8).
7. Merge. Add a `renames` map to marketplace.json later if a plugin is ever
   renamed.

## 8. Docs

- **README**: add "Install with Cowork" (Add marketplace → `StianOby/claude-legal-tools`
  → Install) and "Install with Claude Code"
  (`/plugin marketplace add StianOby/claude-legal-tools`,
  `/plugin install hudoc@claude-legal-tools`) *above* the existing zip
  instructions. Update all `skills/<x>/README.md` links to
  `plugins/<x>/skills/<x>/README.md`. State that kildesjekk's auto-install of
  dependencies applies to Claude Code only unless step 7.4 shows otherwise.
- **CLAUDE.md**: update the validation snippet path; add "bump `plugin.json`
  version whenever a plugin's files change"; describe the layout convention.
- **plugins/eurlex/skills/eurlex/README.md**: the "install the MCP server
  first" step applies to zip users only.

## 9. Decision: per-skill plugins (closed)

A single bundle plugin was considered and rejected:

- The "no restructure" variant does not exist: the marketplace reference says
  "plugin directory must not be repo root for relative sources", so a bundle
  would also have needed a `git mv` into `plugins/legal-tools/skills/`.
- The ten retrieval skills are independently useful; other meta-skills than
  kildesjekk are planned, each depending on a subset of them.
- Claude Code loads every skill in an installed plugin into context; per-skill
  plugins let users avoid paying for skills they don't use.

Cost accepted: Cowork users of kildesjekk install eleven plugins by hand
(unless 7.4 shows Cowork honours `dependencies`).

## 10. Risks / verify during testing

- **Python dependencies** (`ets`, `untc` ship `requirements.txt`; nbno
  pip-installs at runtime). Plugins don't auto-install Python deps. Current
  behaviour (skill tells Claude to `pip install` when missing) carries over. A
  `SessionStart` hook into `${CLAUDE_PLUGIN_DATA}` is possible but adds startup
  cost to every session — skip unless runtime installs prove flaky.
- **Skill path shown to Claude** changes from `skills/hudoc` to a plugin cache
  path. Relative `scripts/` references handle this; a grep found no hard-coded
  repo paths.
- **`evals/` directories** (efta-court, ets, untc) become usable with
  `claude plugin eval` once inside plugins — optional follow-up.

## 11. Implementation log (2026-09-12)

Done on branch `marketplace`:

- `git mv skills/<x> plugins/<x>/skills/<x>` for all eleven (one commit,
  `git log --follow` verified).
- Eleven `plugin.json` files (version 1.0.0, GPL-3.0-only, `dependencies` on
  kildesjekk), `plugins/eurlex/.mcp.json`, `.claude-plugin/marketplace.json`.
- `npx -y @anthropic-ai/claude-code@latest plugin validate` (CLI 2.1.270)
  passes for the marketplace and all eleven plugins with `--strict`.
- eurlex SKILL.md names both MCP tool prefixes; description is 1022 chars.
- Release workflow retargeted to `plugins/**`; zip contents verified to have
  the same internal layout (skill files at zip root).
- `validate.yml` added: description-length check, marketplace consistency
  check, `claude plugin validate`.
- README, CLAUDE.md, every skill README updated with plugin install steps.

Cowork test results (2026-09-12, after merge):

- Add marketplace → `StianOby/claude-legal-tools` lists all eleven. ✔
- kildesjekk's `dependencies`: **not honoured** by Cowork. Manual-install
  wording in the READMEs stays. ✘ (accepted)
- eurlex: bundled MCP server installs and its tools are used. ✔
- hudoc: `python3 scripts/hudoc.py` resolves from the plugin location. ✔

- Update without version bump (hudoc README marker, `--no-verify`): arrived
  in Cowork after **Update**. Cowork does not key on `plugin.json` version. ✔

Nothing open. Possible follow-ups: `claude plugin eval` for the skills with
`evals/`; re-test `dependencies` in Cowork now and then.
