# eurlex

A usage-guide skill for EU law. It contains no scripts: all retrieval is
done through the
[eurlex MCP server](https://github.com/Honeyfield-Org/eurlex-mcp-server),
and `SKILL.md` teaches Claude how to use that server's tools well —
converting case numbers and ECLIs to CELEX, paging long judgments by
paragraph offset, choosing consolidated versions, and citing correctly.

## Requirements

- The eurlex MCP server must be configured in the client. Minimal config:

  ```json
  {
    "mcpServers": {
      "eurlex": { "command": "npx", "args": ["-y", "eurlex-mcp-server"] }
    }
  }
  ```

- No Python, no packages, no cache directory.

## Layout

```
eurlex/
  SKILL.md    # trigger description + MCP usage guide
  README.md   # this file
```

## Installing as a Claude skill

**Recommended — Claude Desktop (for use with Cowork):**

1. Download the latest `eurlex.zip` from the
   [releases page](https://github.com/StianOby/claude-legal-tools/releases).
2. In Claude Desktop, go to **Customize → Skills**, click **+** →
   **Create skill** → **Upload a skill**, and upload the zip.

**Alternative — symlink from a local clone (Claude Code CLI):**

- macOS / Linux: `ln -s /path/to/eurlex ~/.claude/skills/eurlex`
- Windows: `mklink /D "%USERPROFILE%\.claude\skills\eurlex" "C:\path\to\eurlex"`

## Notes on scope

- EFTA Court / EEA case law → `efta-court`.
- ECtHR case law → `hudoc`.
- Council of Europe treaties → `ets`.
- Norwegian law → `lovdata-api` / `lovdata-pro`.
