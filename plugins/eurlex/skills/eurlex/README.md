# eurlex

A usage-guide skill for EU law. Retrieval is done through the
[eurlex MCP server](https://github.com/Honeyfield-Org/eurlex-mcp-server),
and `SKILL.md` teaches Claude how to use that server's tools well —
converting case numbers and ECLIs to CELEX, paging long judgments by
paragraph offset, choosing consolidated versions, and citing correctly.

The server cannot search inside the texts. For case law, a small script fills
that gap with a full-text search in the Court's
[InfoCuria](https://infocuria.curia.europa.eu/). It is used only when a question
needs full-text search, and only to find cases: they are read and quoted through
the MCP server. The service behind InfoCuria is undocumented, so this search may
stop working without notice; Claude then says so. Full-text search of
legislation is not covered.

## Requirements

- The eurlex MCP server, installed by you — neither the plugin nor the skill
  zip bundles it, so that you keep control of its settings (e.g. tool
  permission defaults) in Claude Desktop. Add it under **Settings →
  Developer → Edit Config** (`claude_desktop_config.json`) and restart
  Claude Desktop; it needs `npx` (Node.js). Minimal config:

  ```json
  {
    "mcpServers": {
      "eurlex": { "command": "npx", "args": ["-y", "eurlex-mcp-server"] }
    }
  }
  ```

- Full-text search runs in the cloud sandbox (Python standard library only).
  No packages, no cache directory.

## Layout

```
eurlex/
  SKILL.md    # trigger description + MCP usage guide
  README.md   # this file
  scripts/case_law_search.py   # full-text search of case law
```

## Installing as a Claude skill

**Recommended — install as a plugin:**

- *Claude Cowork:* in Claude Desktop, go to **Customize → Plugins → Add
  marketplace**, enter `StianOby/claude-legal-tools`, find `eurlex` and click
  **Install**. Click **Update** on the marketplace later to get new versions.

**Alternative — upload the skill zip (Claude Desktop):**

1. Download the latest `eurlex.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

## Notes on scope

- EFTA Court / EEA case law → `efta-court`.
- ECtHR case law → `hudoc`.
- Council of Europe treaties → `ets`.
- Norwegian law → `lovdata-api` / `lovdata-pro`.
