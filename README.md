# Øby's legal tools for Claude Cowork
Stian Øby Johansen's collection of skills and other tools for use with Claude (cowork).

## Document retrieval skills

These skills each connect Claude to a single legal database. Install the ones you need.

| Skill | What it does |
|---|---|
| `efta-court` | EFTA Court judgments |
| `ets` | Council of Europe treaty series |
| `eurlex` | EU legislation and case law from EUR-Lex |
| `hudoc` | European Court of Human Rights judgments from HUDOC |
| `icj` | ICJ and PCIJ case law, jurisdiction data, and Article 36(2) declarations |
| `lovdata-api` | Norwegian legislation from Lovdata (free content) |
| `lovdata-pro` | Norwegian case law and preparatory works from Lovdata Pro |
| `nbno` | Documents from the National Library of Norway (Nasjonalbiblioteket) |
| `norges-traktater` | Norway's treaty register |
| `untc` | UN Treaty Collection — treaty texts and ratification status |

## Research workflow skills

These skills orchestrate the document retrieval skills above to carry out broader academic research tasks. To use them, install both the workflow skill and all the retrieval skills it depends on.

| Skill | What it does | Requires |
|---|---|---|
| `kildesjekk` | Verifies every reference and quotation in an academic legal text against the original sources; produces an `.xlsx` worklist with per-reference status and severity-coded discrepancies | All document retrieval skills above |

## Installing a skill

Skills are installed through **Claude Desktop** — the desktop app for Mac and Windows. You will need a Claude plan that includes Skills (Pro, Team, or Enterprise).

### Step 1 — Download the skill file

1. Go to the **[Releases](https://github.com/StianOby/claude-legal-tools/releases)** page of this repository. You can also find it by clicking **Releases** in the right-hand sidebar on the GitHub repository page.
2. Click on the top entry in the list — that is the most recent release.
3. Scroll down to the **Assets** section and click the `.zip` file for the skill you want to install — for example `eurlex.zip`. The file will download to your computer like any normal file.

### Step 2 — Open the Skills panel in Claude Desktop

1. Open the **Claude Desktop** app.
2. Look for the **Customize** button — it is usually found at the top left of the window.
3. Click **Customize**, then click **Skills** in the menu that appears.

### Step 3 — Upload the skill

1. In the Skills panel, click the **+** button.
2. A small menu appears. Click **Create skill**, then **Upload a skill**.
3. A file picker opens. Navigate to the `.zip` file you downloaded in Step 1, select it, and confirm.
4. Claude will process the file and the skill will appear in your list of installed skills.

That's it. The skill is now active in your Claude sessions. You do not need to type a command to activate it — Claude will use it automatically whenever your question matches what the skill can do.

> **Need more help?** Anthropic's official guide — [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude) — covers the full details, including how to check whether your plan includes Skills.

### Installing multiple skills

Each skill is a separate `.zip` file. To install several skills, choose several of the .zip.files at the same time when using the file picker in step 3.
