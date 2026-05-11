---
name: eurlex
description: Fetch EU legal documents (regulations, directives, CJEU judgments, opinions) from EUR-Lex when the eurlex MCP returns "Document not found", truncates at its 50 000-character cap, or returns empty content (char_count 0). Use as a SECONDARY path — always try the eurlex MCP first. Trigger when a CELEX/ECLI lookup via the MCP fails, when the user needs paragraphs past ~50 KB of a long judgment, when the user provides a CELEX you've previously seen the MCP reject, or when the MCP returns empty content.
---

# eurlex

A small toolkit that wraps the EUR-Lex content-negotiated CELLAR endpoint
(`publications.europa.eu/resource/celex/<CELEX>.<LANG>`) so you can retrieve
documents that the `mcp__eurlex__*` tools cannot return: older judgments that
the MCP reports as "Document not found", and long judgments that it truncates
at the hard-coded 50 000-character cap.

## Prerequisites

This skill requires the eurlex MCP to be available as the primary path. If
`mcp__eurlex__*` tools are missing, install the MCP server first:
[Honeyfield-Org/eurlex-mcp-server](https://github.com/Honeyfield-Org/eurlex-mcp-server)

## When to invoke this skill

Use the eurlex MCP **first**. Only fall back to this skill when one of the
following is true:

1. `mcp__eurlex__eurlex_fetch` raises `Document not found` for a CELEX you have
   reason to believe exists (e.g. it appears in a citation, in scholarly
   writing, on the Curia website, or has a valid CELEX shape).
2. The MCP returned content but it is clearly truncated — i.e. the cited
   paragraph number is higher than the last paragraph in the response, or the
   reply ends mid-sentence near the 50 000-character mark.
3. The user asks for a specific paragraph range from a long judgment and you
   need to be sure you are not paging past the MCP's cap.
4. `mcp__eurlex__eurlex_consolidated` returns "not available" / "nicht verfügbar"
   for a directive or regulation you have reason to believe exists (e.g. it
   appears in a citation or has a valid CELEX shape, like `32003L0088`). Use
   `scripts/eurlex_fetch.py` with the CELEX — the script handles directives and
   regulations the same way it handles judgments.
5. `mcp__eurlex__eurlex_fetch` returned success but `char_count` is 0 or the
   body is empty — the MCP silently succeeds for judgments whose CELLAR rendition
   is still being generated. Treat any zero-length result as "not found" and fall
   back to `eurlex_fetch.py` (which retries HTTP 202 with backoff). If that also
   fails after retries, try `eurlex_curia_fetch.py`.

If the MCP returns a complete document under its limit, do **not** invoke this
skill — there is no value in re-fetching.

## What the toolkit does

Three thin Python scripts (no compiled deps, only `requests` + `pypdf`):

- `scripts/eurlex_fetch.py` — fetch a CELEX by content negotiation. Tries
  `Accept: text/html`, then `application/xml` (XHTML rendition of FMX4), then
  PDF (text-extracted with `pypdf`). Retries up to 3× when CELLAR returns HTTP
  202 (rendition being generated on-the-fly). Caches results to `~/.cache/eurlex/`.
- `scripts/eurlex_curia_fetch.py` — fetch from InfoCuria (curia.europa.eu) as a
  last resort when all CELLAR endpoints fail. Converts the CELEX to a case
  number (e.g. `62021CJ0488` → `C-488/21`), searches InfoCuria for the docid,
  and fetches the printable HTML rendition. Accepts CELEX or case number directly.
  Caches to the same `~/.cache/eurlex/` directory.
- `scripts/eurlex_paragraphs.py` — slice the cached plain text by paragraph
  number range (e.g. `--from 73 --to 91`) for CJEU/General Court judgments.
- `scripts/eurlex_search.py` — thin wrapper over the EUR-Lex public search
  page; intended only as a last resort if the MCP's SPARQL search also fails.

## Quick start

```bash
# 1. Install once per environment
pip install --user requests pypdf

# 2. Fetch a judgment the MCP rejected (retries HTTP 202 automatically)
python3 scripts/eurlex_fetch.py 62002CJ0371 --lang ENG --plain
# -> prints full plain text; cached to ~/.cache/eurlex/

# 3. Get just paragraphs 73-91 from a long judgment
python3 scripts/eurlex_fetch.py 62016CJ0569 --lang ENG --plain > /tmp/bauer.txt
python3 scripts/eurlex_paragraphs.py /tmp/bauer.txt --from 73 --to 91

# 4. Curia fallback when EUR-Lex CELLAR still fails after retries
python3 scripts/eurlex_curia_fetch.py 62021CJ0488 --lang ENG
# or with the case number directly:
python3 scripts/eurlex_curia_fetch.py "C-488/21" --lang EN
```

## Why not the kevin91nl/eurlex PyPI package?

The package was the obvious fallback candidate, but it has two problems for
this use case:

1. It pins `pandas==1.2.4`, which has to compile from source on modern Python
   and pulls in a heavy build chain.
2. Its parser is **regulation-centric** — it returns a DataFrame keyed on
   `article` / `article_subtitle` / `ref`. Judgments are paragraph-numbered
   with no Articles, so the parser produces empty frames for them.

The **fetcher** in that package is just a content-negotiated GET against the
exact same `publications.europa.eu/resource/celex/<CELEX>` URL plus
multiple-choice handling. We do the same in `eurlex_fetch.py` with `requests`
directly, no pandas, no SPARQL, plus paragraph-aware parsing.

## Failure modes the toolkit handles

| Failure                                  | Fallback path                                                    |
|------------------------------------------|------------------------------------------------------------------|
| MCP "Document not found" — old judgments | `Accept: text/html` on `/resource/celex/<CELEX>.<LANG>`          |
| HTML 404 — newer judgments (≈2014+)      | `Accept: application/xml` returns the XHTML rendition            |
| Both 404 — non-public docs               | `Accept: application/pdf` + `pypdf` text extraction              |
| HTTP 202 — rendition being generated     | `eurlex_fetch.py` retries up to 3× at 5–10 s intervals          |
| MCP returns empty content (char_count 0) | Same as above — 202 is the usual root cause                      |
| All CELLAR endpoints exhausted           | `eurlex_curia_fetch.py` searches InfoCuria (independent store)   |
| 50 000-char MCP truncation               | Native fetch has no cap; cache plain text and slice it           |

## Curia fallback

`eurlex_curia_fetch.py` uses InfoCuria's search-then-fetch pattern:

1. Converts CELEX to a case number: `62021CJ0488` → `C-488/21`
2. GETs `https://curia.europa.eu/juris/liste.jsf?num=C-488%2F21&language=EN`
3. Parses the result page for a `docid` parameter in document links
4. GETs the printable rendition:
   `https://curia.europa.eu/juris/document/document_print.jsf?docid=<ID>&doclang=EN&part=1`
5. Strips HTML to plain text and caches under `~/.cache/eurlex/<CELEX>_<LANG>/curia.*`

The script also accepts a case number directly (`C-488/21`) if you don't have the CELEX.

## Failure modes the toolkit does NOT solve

- Cases with no electronic full text anywhere (some old orders, some AG opinions
  that predate digital archiving). If `eurlex_curia_fetch.py` also fails, the
  user needs the printed *Reports of Cases* or a library with Westlaw EU.
- Documents that are paywalled (rare on EUR-Lex, more common for early reporter
  texts). Direct the user to a library copy.
- Pinpoint citations to footnotes inside an AG opinion — the paragraph parser
  follows main-body paragraph numbering only.

## Notes on language selection

CELEX language codes on the CELLAR endpoint are three-letter ISO 639-2/B:
`ENG`, `FRA`, `DEU`, `SPA`, `ITA`, `NLD`, `POL`, `SWE`, `DAN`, `FIN`, etc.
Norwegian is **not** an EU official language and EUR-Lex does not host
Norwegian translations of CJEU judgments. If the user reads Norwegian, fetch
the English (`ENG`) text — that is what Norwegian academic legal writing
typically cites alongside the original-language version.
