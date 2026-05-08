# eurlex

A small skill that handles the cases where the `eurlex` MCP cannot return a
document.

## Layout

```
eurlex/
  SKILL.md                 # Skill description and usage policy
  README.md                # This file
  scripts/
    eurlex_fetch.py        # Fetch a CELEX with content negotiation + cache
    eurlex_paragraphs.py   # Extract paragraph ranges from a fetched judgment
    eurlex_search.py       # Last-resort HTML search wrapper
```

Drop the whole `eurlex/` folder into a Claude skills directory
(e.g. `~/.claude/skills/eurlex/`) and the SKILL.md auto-loads on
matching triggers.

## Two failure modes the MCP has, and how this skill handles them

| MCP behaviour | Cause | Fallback path |
|---|---|---|
| `Document not found` for older CJEU judgments (Björnekulla, Van Gend, Pasquini, Wagner Miret, Costa, Impact, etc.) | The MCP looks up the document via SPARQL/CELLAR but the format manifestation it expects is missing. Static legacy HTML is still served via content negotiation. | `Accept: text/html` on `publications.europa.eu/resource/celex/<CELEX>.<LANG>` |
| Truncated content for long judgments (Bauer C-569/16 cuts at para 72; Instituto Madrileño C-726/19 cuts at para 63; X C-715/20 cuts at para 68) | The MCP `eurlex_fetch` tool caps at 50 000 chars. Some judgments exceed this. | Native fetch with no cap. Newer judgments respond to `Accept: application/xml` (GENDOC2XHTML rendition of the FMX4 source) when `text/html` returns 404. |
| Both fail | Some non-public docs | `Accept: application/pdf` + `pypdf` text extraction |

The toolkit also caches every fetch under `~/.cache/eurlex/` so repeat
lookups are free.

## Quick reference

```bash
# Fetch and cache (auto-tries HTML, then XHTML, then PDF)
python3 scripts/eurlex_fetch.py 62016CJ0569 --info

# Print just the cited paragraph range
python3 scripts/eurlex_paragraphs.py --celex 62016CJ0569 --from 73 --to 91

# Pin specific paragraphs only
python3 scripts/eurlex_paragraphs.py --celex 62019CJ0726 --paragraphs 78,82,86

# Optional: search EUR-Lex HTML (only if MCP search returns nothing)
python3 scripts/eurlex_search.py "Björnekulla" --limit 5
```

## Dependencies

```
pip install requests pypdf
```

That's it. No pandas, no SPARQL client, no headless browser.

## Attribution

The content-negotiation approach (`publications.europa.eu/resource/celex/<CELEX>` with `Accept` headers, no SPARQL) is inspired by [kevin91nl/eurlex](https://pypi.org/project/eurlex/).
