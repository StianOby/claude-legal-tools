# Plan: turn this repo into a plugin marketplace

Status: **draft, not started** (2026-09-12).

Goal: let Cowork (and Claude Code) users install the skills in this repo as
plugins via "Add marketplace → `StianOby/claude-legal-tools`", while keeping the
existing per-skill `.zip` GitHub Releases for users who upload skills by file.

Decisions so far:

- **One plugin per skill** (see §9 for the alternative to reconsider).
- **Keep the zip release workflow.**

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
   (<https://github.com/anthropics/claude-code/issues/66184>). Docs now describe
   it as present. **Verify in Cowork before doing the restructure.**
2. Plugin `dependencies` (auto-install of required plugins) is documented for
   Claude Code only; Cowork docs never mention it. Assume kildesjekk's
   dependency list may be a no-op in Cowork — see §4 for the fallback.
3. Cowork has no version pinning; updates replace the plugin with current repo
   state. The version-bump CI guard in §5 only matters for Claude Code caching.
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
  "metadata": { "pluginRoot": "./plugins" },
  "plugins": [
    { "name": "efta-court", "source": "efta-court", "description": "EFTA Court judgments", "category": "legal-research", "keywords": ["efta", "eea", "case-law"] },
    { "name": "ets", "source": "ets", "description": "Council of Europe treaty series", "category": "legal-research" },
    { "name": "eurlex", "source": "eurlex", "description": "EU legislation and case law from EUR-Lex (bundles the eurlex MCP server)", "category": "legal-research" },
    { "name": "hudoc", "source": "hudoc", "description": "European Court of Human Rights judgments from HUDOC", "category": "legal-research" },
    { "name": "icj", "source": "icj", "description": "ICJ and PCIJ case law, jurisdiction data, and Article 36(2) declarations", "category": "legal-research" },
    { "name": "lovdata-api", "source": "lovdata-api", "description": "Norwegian legislation from Lovdata (free content)", "category": "legal-research" },
    { "name": "lovdata-pro", "source": "lovdata-pro", "description": "Norwegian case law and preparatory works from Lovdata Pro", "category": "legal-research" },
    { "name": "nbno", "source": "nbno", "description": "Documents from the National Library of Norway (Nasjonalbiblioteket)", "category": "legal-research" },
    { "name": "norges-traktater", "source": "norges-traktater", "description": "Norway's treaty register", "category": "legal-research" },
    { "name": "untc", "source": "untc", "description": "UN Treaty Collection — treaty texts and ratification status", "category": "legal-research" },
    { "name": "kildesjekk", "source": "kildesjekk", "description": "Source-check an academic legal text against all retrieval skills; produces an .xlsx worklist", "category": "legal-research" }
  ]
}
```

Leave `version` out of the marketplace entries; put it in each `plugin.json`
so there is one place to bump.

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

(Confirm the SPDX id against `LICENSE`.)

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

Verify: plugin-provided MCP servers may get a different tool-name prefix than a
user-configured server (SKILL.md refers to `mcp__eurlex__eurlex_*`). After a
local install, check the actual prefix and adjust SKILL.md wording. Keep the
"if the tools are missing, tell the user" fallback for zip-installed users, who
get no `.mcp.json`.

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
- Optional (Claude Code only): fail if files under `plugins/<p>/` changed since
  the last `skills-*` tag but `plugins/<p>/.claude-plugin/plugin.json` version
  did not. Claude Code caches plugins by version.

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

## 9. Open decision: per-skill vs. single bundle

Because Cowork lets users toggle individual skills *inside* an installed
plugin, the main argument for per-skill plugins ("install only what you need")
is weaker for a Cowork-only audience. A single `legal-tools` bundle plugin
would mean:

- no directory restructure (`.claude-plugin/plugin.json` at repo root with
  `"skills": "./skills"`, marketplace entry `"source": "./"`);
- no `dependencies` uncertainty for kildesjekk;
- one install click; users disable e.g. `lovdata-pro` in the plugin's Skills tab.

Cost: Claude Code users can't pick and choose, and the marketplace shows one
entry instead of eleven. Decide after step 7.4 confirms how Cowork behaves.

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
