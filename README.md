# Øby's legal tools for Claude Cowork
Stian Øby Johansen's collection of skills and other tools for use with Claude (cowork).

## Document retrieval skills

These skills each connect Claude to a single legal database. Install the ones you need. Click the skill name in the table below to open its README file.

| Skill | What it does |
|---|---|
| [`efta-court`](plugins/efta-court/skills/efta-court/README.md) | EFTA Court judgments |
| [`ets`](plugins/ets/skills/ets/README.md) | Council of Europe treaty series |
| [`eurlex`](plugins/eurlex/skills/eurlex/README.md) | EU legislation and case law from EUR-Lex (usage guide for the [eurlex MCP server](https://github.com/Honeyfield-Org/eurlex-mcp-server), which must be installed) |
| [`hudoc`](plugins/hudoc/skills/hudoc/README.md) | European Court of Human Rights judgments from HUDOC |
| [`icj`](plugins/icj/skills/icj/README.md) | ICJ and PCIJ case law, jurisdiction data, and Article 36(2) declarations |
| [`lovdata-api`](plugins/lovdata-api/skills/lovdata-api/README.md) | Norwegian legislation from Lovdata (free content) |
| [`lovdata-pro`](plugins/lovdata-pro/skills/lovdata-pro/README.md) | Norwegian case law and preparatory works from Lovdata Pro |
| [`nbno`](plugins/nbno/skills/nbno/README.md) | Documents from the National Library of Norway (Nasjonalbiblioteket) |
| [`norges-traktater`](plugins/norges-traktater/skills/norges-traktater/README.md) | Norway's treaty register |
| [`untc`](plugins/untc/skills/untc/README.md) | UN Treaty Collection — treaty texts and ratification status |

## Research workflow skills

These skills orchestrate the document retrieval skills above to carry out broader academic research tasks. To use them, install both the workflow skill and all the retrieval skills it depends on (Claude Code does this automatically; in Cowork, install each one). Click the skill name in the table below to open its README file.

| Skill | What it does | Requires |
|---|---|---|
| [`kildesjekk`](plugins/kildesjekk/skills/kildesjekk/README.md) | Verifies every reference and quotation in an academic legal text against the original sources; produces an `.xlsx` worklist with per-reference status and severity-coded discrepancies | All document retrieval skills above |

## Installing skills

Every skill is published in two forms: as a **plugin** in this repository's marketplace (recommended — one click to install, one click to update), and as a **`.zip` file** on the Releases page for uploading by hand.

### Option 1 — Install as a plugin from the marketplace (recommended)

**Claude Cowork** (Claude Desktop for Mac and Windows; any paid plan):

1. Open the **Claude Desktop** app and click **Customize** (top left), then **Plugins**.
2. Click **Add marketplace** and enter `StianOby/claude-legal-tools`.
3. The skills above now appear as plugins. Click **Install** on each one you want.
4. Later, click **Update** on the marketplace to get the newest versions of all installed plugins.

Anthropic's guide — [Install plugins in Cowork](https://claude.com/docs/cowork/guide/plugins) — has screenshots and more detail.

**Claude Code:**

```
/plugin marketplace add StianOby/claude-legal-tools
/plugin install hudoc@claude-legal-tools
```

Installing `kildesjekk` in Claude Code also installs the retrieval plugins it depends on.

### Option 2 — Upload the skill `.zip` file

Use this if you cannot add a marketplace (for example if your organisation restricts plugins) or want to use the skills in Claude chat rather than Cowork. You will need a Claude plan that includes Skills (Pro, Team, or Enterprise).

#### Step 1 — Download the skill file

1. Go to the **[Releases](https://github.com/StianOby/claude-legal-tools/releases)** page of this repository. You can also find it by clicking **Releases** in the right-hand sidebar on the GitHub repository page.
2. Click on the top entry in the list — that is the most recent release.
3. Scroll down to the **Assets** section and click the `.zip` file for the skill you want to install — for example `eurlex.zip`. The file will download to your computer like any normal file.

#### Step 2 — Open the Skills panel in Claude Desktop

1. Open the **Claude Desktop** app.
2. Look for the **Customize** button — it is usually found at the top left of the window.
3. Click **Customize**, then click **Skills** in the menu that appears.

#### Step 3 — Upload the skill

1. In the Skills panel, click the **+** button.
2. A small menu appears. Click **Create skill**, then **Upload a skill**.
3. A file picker opens. Navigate to the `.zip` file you downloaded in Step 1, select it, and confirm.
4. Claude will process the file and the skill will appear in your list of installed skills.

That's it. The skill is now active in your Claude sessions. You do not need to type a command to activate it — Claude will use it automatically whenever your question matches what the skill can do.

> **Need more help?** Anthropic's official guide — [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) — covers the full details, including how to check whether your plan includes Skills.

#### Installing multiple skills

Each skill is a separate `.zip` file. To install several skills, choose several of the `.zip` files at the same time when using the file picker in step 3.

Note that the `eurlex` skill zip does not include the eurlex MCP server; the plugin does. See the [eurlex README](plugins/eurlex/skills/eurlex/README.md).

## Repository layout

```
.claude-plugin/marketplace.json     # the marketplace catalogue
plugins/<name>/
  .claude-plugin/plugin.json        # plugin manifest (name, version, …)
  .mcp.json                         # only eurlex: bundled MCP server
  skills/<name>/                    # the skill itself: SKILL.md, README.md, scripts/ …
```

Each plugin carries its own version number, bumped automatically on every commit that changes it (see [CLAUDE.md](CLAUDE.md)). Claude Code offers an update when the version changes; Cowork's **Update** button always pulls the current repository state.
