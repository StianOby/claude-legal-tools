---
name: nem-vedtak
description: |
  NEM-vedtak: use when the user needs decisions from NEM — Den nasjonale forskningsetiske komité for medisin og helsefag, the appeal body for REK decisions under helseforskningsloven — from forskningsetikk.no. Triggers: NEM-vedtak, NEM-sak, a NEM saksnr (NEM 2021/169, 2022-32), "klage på REK-vedtak", "hva har NEM sagt om dispensasjon fra taushetsplikten / samtykke / sårbare grupper / utsatt offentlighet", "NEM practice on hfl. § 35", "NEM decisions where the appellant won", or a forskningsetikk.no/…/sok-i-nems-vedtak/ link. Covers all ~234 appeal decisions since 2009: full text, outcome, REK, institution, keywords, research-ethics principles, statutes. One known decision is fetched live; searches use a local copy on the user's computer (asks first) with phrase/regex search and filters the site lacks. Do NOT use for: REK's own decisions; the other national research ethics committees (NENT, NESH, Granskingsutvalget); Norwegian statutes (lovdata-api); court decisions (lovdata-pro).
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

## Start here: which route

**One known decision** (a saksnr, title or link; its text, outcome, a quote,
the PDF) → **look it up live** with `get` / `pdf` in the cloud sandbox
(`Bash`, "Live lookups" below). No local copy, no cache, no question —
even if a local copy exists. If title words do not give one clear match
(no hit, or several plausible decisions), treat the request as a search
across decisions (below).

**Anything across decisions** ("what has NEM said about X", a phrase, all
decisions with a given outcome, keyword, principle, statute, REK, institution
or year) → **local copy** in a folder on the user's computer. There is no
cloud copy: it would download the whole corpus again every session. Settle
this once per conversation, before the first search:

1. **Is there a copy already?** Load the local-shell tools
   ([`local-route.md`](local-route.md) §1, step 1). If `device_bash` works,
   look for a copy anywhere in the connected folders, not just at their top
   level (the user may have connected a parent or a sibling of the folder
   used last time):
   ```bash
   timeout 30 find "$HOME"/mnt -maxdepth 5 -path '*/nem-vedtak/index.json' -printf '%T@ %h\n' 2>/dev/null | sort -rn | cut -d' ' -f2-
   ```
   Each line is a copy's folder, most recently synced first. Use the first
   one without asking (set up as in "The local copy" below, with `--dir`
   that folder, and run `sync`); if there are several, say where the others
   are.
2. **Otherwise ask** before searching. For example: "Shall I keep a local copy
   of all NEM decisions (about 3 MB, roughly 15 seconds) in a folder on your
   computer? It stays between sessions, allows exact-phrase searches, and
   shows each decision's outcome, keywords and principles. It needs a
   connected folder (e.g. Claude-legal-work). If you already have a copy
   from an earlier conversation, connect that folder instead, and I'll use
   it." If the user then connects a folder, run the search in step 1 again
   before making a new copy.
   - **Yes** → "The local copy" below; the local route asks for a folder
     if none is connected.
   - **No**, or the user cannot connect a folder after local-route message
     A or B → say that searching across decisions needs the local copy, and
     offer live lookups of decisions they can name. Do not run the search
     some other way (no cloud copy, no looping over live lookups), and do not
     ask again in this conversation.

| Route | Runs in | Use |
|---|---|---|
| Live: `get`, `pdf` without `--dir` | cloud sandbox (`Bash`), straight from the site | one known decision — always |
| Local copy: `sync`, `search`, `facets`, `get --dir` | **local shell** (`device_bash`, the local route), in `<connected folder>/nem-vedtak/` — persists | searches across decisions |

A live `get` ends with a note on what a local copy adds. Pass it on as one
sentence the first time in a conversation, unless the user has already
declined a local copy; never repeat it.

forskningsetikk.no has not blocked any client so far. If it answers 403/405
from `Bash`, say "This source is blocked from Anthropic's cloud"; then run
live lookups and searches through the local route instead.

## Live lookups (one known decision)

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
   give the message and let the user act; if they then cannot or will not
   connect, there is no search (see "Start here").
2. The copy is the one found in "Start here" step 1; a new copy goes in
   **`<connected folder>/nem-vedtak/`**. Call that the copy folder. Start every call
   with `test -f <dir>/.ready || exit 4;` and call the script by its
   absolute path with `PYTHONUTF8=1`.
3. Run `sync` at the first use in each conversation:
   ```bash
   test -f <dir>/.ready || exit 4; PYTHONUTF8=1 python3 <dir>/scripts/nem.py sync --dir "<copy folder>"
   ```
   A first sync takes about 15 s (234 pages plus the filter lists); later
   ones fetch only decisions whose sitemap date changed, and refresh the
   facets. `INCOMPLETE … run sync again` means the 140-second budget ran
   out — run the same command again; it resumes. `FAILED <slug>` lines are
   single pages that could not be fetched; a rerun retries them.
4. `status --dir …` shows what the copy holds and when it was last synced.

The copy: `vedtak/<YYYY-NNN>_<slug>.md` (one file per decision, front matter
plus text, readable by the user in any editor), `index.json` (all metadata),
`README.txt` (says what the folder is and to connect it again next time),
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
