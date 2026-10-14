---
name: nem-vedtak
description: |
  NEM-vedtak: use when the user needs decisions from NEM — Den nasjonale forskningsetiske komité for medisin og helsefag, the appeal body for REK decisions under helseforskningsloven — from forskningsetikk.no. Triggers: NEM-vedtak, NEM-sak, a NEM saksnr (NEM 2021/169, 2022-32), "klage på REK-vedtak", "hva har NEM sagt om dispensasjon fra taushetsplikten / samtykke / sårbare grupper / utsatt offentlighet", "NEM practice on hfl. § 35", "NEM decisions where the appellant won", or a forskningsetikk.no/…/sok-i-nems-vedtak/ link. Covers all ~234 appeal decisions since 2009: full text, outcome, REK, institution, keywords, research-ethics principles, statutes. Two modes: one decision live, or a local copy (on the user's computer) for phrase/regex search and filters, which the site's search cannot do. Do NOT use for: REK's own decisions; the other national research ethics committees (NENT, NESH, Granskingsutvalget); Norwegian statutes (lovdata-api); court decisions (lovdata-pro).
---

# NEM-vedtak — NEM's appeal decisions

**First step, before any command:** resolve `{SKILL_DIR}` as described under "Skill directory" below and use the printed path literally. Never guess it.

NEM (Den nasjonale forskningsetiske komité for medisin og helsefag) hears
appeals against decisions of the regional committees (REK) under
helseforskningsloven. Its decisions are published at
<https://www.forskningsetikk.no/om-oss/komiteer-og-utvalg/nem/sok-i-nems-vedtak/>:
about 234 decisions from 2009 on, each with its full text in HTML (and in
most cases a PDF), all of them appeals (`Klagesak`). The site's own search is
weak: it ignores quotation marks, so a phrase search returns every page that
contains any of the words. That is why this skill can keep a **local copy**
and search it properly.

One CLI, standard library only: `scripts/nem.py` (`python3`, ≥ 3.10).

**Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for this skill:" if it exists in bash.
Otherwise resolve it once and use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/nem-vedtak}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/nem-vedtak/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

## Choose the mode

| The user wants | Mode |
|---|---|
| One known decision: its text, outcome, a quote, the PDF (saksnr, title, link) | **Live** — no download |
| Anything across decisions: "what has NEM said about X", a phrase, all decisions with a given outcome, keyword, principle, statute, REK, institution or year | **Local copy** |

**Live mode always ends with one sentence** telling the user that a local
copy is available: it adds phrase/regex search across all decisions and each
decision's outcome (utfall), keywords (emneord), research-ethics principles
and statute chapters, which live lookups do not show. (`get` prints this note
as its last line; pass it on.) Do not make the copy unless they want it.

## Where each step runs

| Step | Runs in |
|---|---|
| Live `get` / `pdf` | cloud sandbox (`Bash`) |
| Local copy: `sync`, `search`, `get`, `facets` | **local shell** (`device_bash`, the local route) — the copy lives in the user's connected folder and persists |
| Local copy when there is no local shell or connected folder | cloud sandbox, in `/mnt/user-data/outputs/nem-vedtak` — **lost when the session ends**; say so |

forskningsetikk.no has not blocked any client so far. If it answers 403/405
from `Bash`, say "This source is blocked from Anthropic's cloud" and use the
local route for live lookups too.

## Live lookups

```bash
python3 {SKILL_DIR}/scripts/nem.py get "NEM 2021/169"          # saksnr (2021/169, 2022-32 …)
python3 {SKILL_DIR}/scripts/nem.py get "Psychopharm Young"     # title words, or a page URL/slug
python3 {SKILL_DIR}/scripts/nem.py get 2021/169 --section vurdering   # one section
python3 {SKILL_DIR}/scripts/nem.py get 2021/169 --meta         # metadata only (JSON)
python3 {SKILL_DIR}/scripts/nem.py pdf 2021/169 --out /mnt/user-data/outputs
```

Output is Markdown: front matter (saksnr, title, url, pdf, institusjon,
klager, forsteinstans, henvisninger), then the text under the site's own
headings — usually **Sammendrag**, **Vedtak fra NEM**, **Saksgang**,
**NEMs vurdering**, **Vedtak**. Older decisions may have other headings;
`--section` with a heading that does not exist lists the real ones.

A few saksnr are shared by two pages (e.g. NEM 2010/202 "Læring av feil ved
legevakt I" and "II"). `get` then shows the first and lists the others on
stderr; say there is more than one.

## The local copy

### Set it up (once per conversation)

1. Follow [`local-route.md`](local-route.md) to get `device_bash`, a
   connected folder and `READY <dir>`. If it stops with message A or B,
   offer the cloud fallback instead (table above) and say that copy is lost
   when the session ends; for this skill that is the only alternative to
   offer, since the site does not block the cloud.
2. The copy goes in **`<connected folder>/nem-vedtak/`**. Start every call
   with `test -f <dir>/.ready || exit 4;` and call the script by its
   absolute path with `PYTHONUTF8=1`.
3. Run `sync` at the first use in each conversation:
   ```bash
   test -f <dir>/.ready || exit 4; PYTHONUTF8=1 python3 <dir>/scripts/nem.py sync --dir "<connected folder>/nem-vedtak"
   ```
   A first sync takes about 15 s (234 pages plus the filter lists); later
   ones fetch only decisions whose sitemap date changed, and refresh the
   facets. `INCOMPLETE … run sync again` means the 140-second budget ran
   out — run the same command again; it resumes. `FAILED <slug>` lines are
   single pages that could not be fetched; a rerun retries them.
4. `status --dir …` shows what the copy holds and when it was last synced.

The copy: `vedtak/<YYYY-NNN>_<slug>.md` (one file per decision, front matter
plus text, readable by the user in any editor), `index.json` (all metadata),
and `pdf/` only for a decision whose text exists only as a PDF (none today;
its text is then extracted with `pdftotext`). Files are never deleted: a
decision that disappears from the site is marked `"removed": true` in
`index.json`.

### Search it

```bash
nem.py search --dir D "utsatt offentlighet"                      # exact phrase, case-insensitive
nem.py search --dir D "sårbar" "samtykke" --section vurdering    # all phrases, only in NEMs vurdering
nem.py search --dir D "reservasjon" "reservere" --any            # at least one
nem.py search --dir D --regex "hfl\.?\s*§\s*35|helseforskningsloven\s*§\s*35" --year 2018-2026
nem.py search --dir D --utfall "gis medhold" --forsteinstans "REK nord"   # filters only, no text
nem.py search --dir D "biobank" --json --limit 200                # machine-readable
```

- Phrases match across line breaks and any whitespace; `--regex` takes
  Python regexes (case-insensitive). Words are not stemmed: search
  `samtykke` and `samtykket` separately, or use a regex (`samtykk\w*`).
- Filters match a substring of the field, case-insensitively, and combine
  with AND: `--utfall`, `--emneord`, `--prinsipp`, `--lov` (helseforskningsloven
  chapters, other statutes and the free-text Henvisninger),
  `--forsteinstans`, `--institusjon`, `--klager`, `--year 2015` or `2015-2020`.
  `--utfall "gis medhold"` matches "Klager gis medhold" and "Klager gis
  medhold. Saken sendes tilbake …" but not "delvis medhold" or "ikke medhold".
- `facets --dir D` lists every filter value with its count: use it to find
  the exact keyword or principle names before filtering.
- Results are newest first, with saksnr, title, outcome, REK, URL, file name
  and up to three snippets labelled by section (`--snippets`, `--context`).
- Then read the decisions themselves: `get <saksnr> --dir D [--section …]`
  (from the copy, with facets) — or the Markdown file directly.

About 9 decisions have no outcome facet and some have no keywords or
principles, because the site never tagged them. A filter misses those, so
when completeness matters, also search the text (e.g. the **Vedtak**
section).

## Citing

Cite as **NEM-vedtak <saksnr> (<title>)**, with the decision date from the
text where needed, and give the page URL. The saksnr is NEM's own; older
decisions also show REK's case number (`saksnr_raw`, e.g. "NEM 2010/202,
REK vest 2010/755"). Quote from the text verbatim and name the section.
