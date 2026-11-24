# eurlex: what the skill adds to the MCP server

The skill covers only what the eurlex MCP server's own tool descriptions do
not (reviewed 2026-11-24 against eurlex-mcp-server 2.4.5). Parameters are left
to the server, so they cannot go stale here.

Why a skill is still needed: the server sends no `instructions`, and its
guide is an MCP *prompt* (`eurlex_guide`), which clients normally leave to
the user to pick. Claude normally sees only the tool descriptions. The skill
adds triggering, installation help, case number to CELEX, quoting by
paragraph, citation, authentic language, routing to the other skills, and the
traps below.

## Traps, as tested on 2.4.5

| Trap | Evidence | Upstream |
|---|---|---|
| `eurlex_consolidated` returns future versions | 32013L0034 and 32009L0138 → 2027-01-30 | [#85](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/85) |
| No way to read a dated consolidation, or to outline one | `celex_id` pattern rejects the hyphen; dated ELI not resolved; GDPR Art. 2 offset 155643 is Art. 65 territory in the consolidated text | [#86](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/86) |
| Case number in `query` depends on the hyphen used in the title | C-131/12 only with U+2011; C-311/18 and C-252/21 only with U+002D | [#87](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/87) |
| Guide is only a prompt | `src/server.ts` | [#88](https://github.com/Honeyfield-Org/eurlex-mcp-server/issues/88) |
| `eurlex_metadata` times out (about 92 s) | 3 of 9 calls | – |
| No paragraph outline | 62012CJ0131, 61962CJ0026; opinions 62012CC0131, 62021CC0252, 62024CC0312; 62000CJ0112 lacks paragraph 1 | – |
| Undecoded HTML entities in plain text | 62000CJ0112, 62024CC0312 | – |
| `eurlex_summary` on a judgment gives another case's summary | 62012CJ0131 → headed C-507/17 | – |
| Consolidated version exists but is not retrievable | 32003L0088 | – |

## Keeping it current

When the server releases a new version, rerun the calls in the table. Remove
a trap from SKILL.md once its fix is released: `npx -y` gives users the
newest version.
