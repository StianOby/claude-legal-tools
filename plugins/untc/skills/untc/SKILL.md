---
name: untc
description: |
  Retrieve UN Treaty Collection source documents — UN Treaty Series (UNTS) treaty text or MTDSG status docs (parties, ratifications, reservations, declarations, objections) for treaties deposited with the UN Secretary-General; for treaties with another depositary (NATO, Geneva Conventions, Chicago Convention) the UNTS text only. Trigger on: a treaty by name/acronym (ICCPR, ICESCR, CAT, CRPD, CEDAW, CRC, VCLT, Genocide/Refugee Convention, Rome Statute, UNCLOS, NPT, CTBT, TPNW); an MTDSG ref like IV-4 or XXIII-1; a UNTS citation (e.g. 729 UNTS 161) or volume + registration number; verbs like fetch the text, what reservations did [state] make, list parties to, who ratified, when did X enter into force; casual phrasing counts. Prefer over web search. Do NOT trigger for: Norwegian law (lovdata-api); EU law (eurlex); ECHR / Council of Europe treaties (hudoc, ets); WIPO/WTO procedure; UN GA/SC resolutions; news about draft treaties; contractual reservation clauses.
---

# UN Treaty Collection (UNTC) skill

This skill talks to `treaties.un.org` to download:

1. **MTDSG status documents** — the authoritative consolidation of the
   text-as-deposited, the participant table (signatures, ratifications,
   accessions, succession), and every state-by-state reservation,
   declaration and objection. One PDF per treaty deposited with the
   UN Secretary-General.
2. **UNTS treaty text** — the text of each registered treaty as
   published in the UN Treaty Series. This covers far more than the
   MTDSG: every treaty registered under Article 102 of the Charter,
   including thousands of bilateral treaties and multilateral treaties
   with another depositary (NPT, Geneva Conventions, ...). Those have no
   status document, only text.

## When to use

Trigger this skill whenever the user wants any of:

- The text of a multilateral or bilateral treaty registered with the UN
- The list of states parties / signatories to a UN-deposited treaty
- A specific state's reservations, declarations or objections
- Dates of signature, ratification, accession, succession
- The MTDSG reference (e.g. "IV-4") or UNTS volume / registration number
- What is in a given UNTS volume, or which treaty a citation such as
  *729 UNTS 161* refers to

## Mental model

UNTC publishes everything you actually need at predictable
`doc/Publication/...` URLs:

```
MTDSG status doc (English and French only):
  https://treaties.un.org/doc/Publication/MTDSG/Volume {I|II}/Chapter {ROMAN}/{REF}.{en|fr}.pdf
  e.g. .../Volume II/Chapter XXIII/XXIII-1.en.pdf   (Vienna Convention)

UNTS treaty text (per-treaty file, where one exists):
  https://treaties.un.org/doc/Publication/UNTS/Volume {N}/volume-{N}-I-{regNum}-{English|French|Other}.pdf
  e.g. .../Volume 1155/volume-1155-I-18232-English.pdf   (Vienna Convention)

UNTS full volume (always exists once the volume is published):
  https://treaties.un.org/doc/Publication/UNTS/Volume {N}/v{N}.pdf
```

The MTDSG status doc *contains* the UNTS volume + registration number,
so once you have the status doc the CLI derives the text URL itself.
Many recent volumes have no per-treaty files; the CLI then downloads the
full volume PDF and slices out the pages of the registration number.

Volume rule for MTDSG: **chapters I–XII → Volume I, chapters XIII–XXIX → Volume II**.

## Where each step runs

| Step | Runs in |
|---|---|
| Treaty text, MTDSG status documents, volume slicing (`scripts/untc.py`) | cloud sandbox (`Bash`) |
| Reading the extracted text, quoting | cloud sandbox (`Bash`) |

Cowork runs in the cloud: `Bash` has Anthropic's IP, not the user's; only the browser pane is
sure to have the user's IP and logins. `treaties.un.org` has worked from the cloud so far; if
it answers 403/405 from `Bash`, tell the user "This source is blocked from Anthropic's cloud" rather than retrying.

## How to use

The skill is a single self-contained CLI: `scripts/untc.py` (Python
3.8+, needs `pypdf`; `pdftotext` is only a fallback). Run it with
`python3` from anywhere, with the full path under `{SKILL_DIR}` (below). Everything it downloads goes to
`~/.cache/untc/` (or `$UNTC_CACHE_DIR`), never into the skill folder.

**Skill directory (`{SKILL_DIR}`).** Use the path after "Base directory for this skill:" if it exists in bash.
Otherwise resolve it once and use the printed path literally in later commands:
```bash
for d in "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/untc}"; do [ -n "$d" ] && [ -f "$d/SKILL.md" ] && { echo "$d"; exit; }; done; f=$(find /root/.claude/plugins /sessions ~/.claude -path '*/skills/untc/SKILL.md' -not -path '*/.trash/*' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-); [ -n "$f" ] && dirname "$f" || echo "SKILL.md not found" >&2
```

Concrete invocations Claude should use:

| User says | Run |
|---|---|
| "get me the ICCPR" / "fetch the Vienna Convention text" | `python3 scripts/untc.py fetch "ICCPR"` |
| "what's the ratification status of CEDAW" | `python3 scripts/untc.py status IV-8` (the status doc has the parties table) |
| "show me reservations to the ICCPR by France" | `python3 scripts/untc.py status IV-4`, then grep `France` in the `status_txt` file the command prints |
| "I have ref XXIII-1, give me everything" | `python3 scripts/untc.py fetch XXIII-1` |
| "the Optional Protocol to CAT" / "OPCAT" | `python3 scripts/untc.py fetch OPCAT` (or `status IV-9-b`) |
| "I need the French version" | add `--lang fr` (`status`/`fetch`) or `--lang fr` / `--lang other` (`text`) |
| "the NPT" / a treaty not deposited with the SG | `python3 scripts/untc.py fetch NPT` → text only, with a note that there is no status doc |
| "729 UNTS 161" / "vol. 999 p. 171" | `python3 scripts/untc.py text --vol 729 --page 161` |
| "registration No. 14668 in vol. 999" | `python3 scripts/untc.py text --vol 999 --reg 14668` |
| "what treaties are in UNTS volume 2404?" | `python3 scripts/untc.py volume 2404 [--search geneva]` |

Available subcommands (`python3 scripts/untc.py --help` shows all):

- `lookup <query>` — fuzzy-search the cached index by title or acronym.
  Known acronyms (ICCPR, OPCAT, CRPD-OP, UNCLOS, Paris Agreement, ...)
  resolve directly; UNTS-only treaties in the built-in list (NPT, Geneva
  Conventions I–IV, Additional Protocols I–II, NATO, Chicago Convention,
  Antarctic Treaty, Outer Space Treaty, Statute of the Council of Europe)
  are reported with their volume/registration number. Output starting
  `NO MATCH` means no SG-deposited title contains the query; any titles
  listed under it merely share a word and are not the treaty.
- `status <ref> [--lang en|fr]` — download + parse the MTDSG status doc.
  Writes `meta.json` with title, place/date, entry into force,
  registration date + number, UNTS volume + page, signatories, parties,
  and the treaty's `details_url` on treaties.un.org. Two dates tell you
  how current it is: `status_date` is when the UN generated the status
  document (the date its participant list reflects), `fetched_utc` when
  this copy was downloaded. A cached status document older than 7 days
  is downloaded again; `--force` does it now.
- `text [<ref>] [--vol N --reg M | --vol N --page P] [--lang en|fr|other]`
  — download the UNTS treaty text. With a ref, the volume/registration
  are read from the cached status doc (fetched first if needed). With
  `--page`, the cited page is mapped to a registration number from the
  running headers printed in the volume itself, with the parsed contents
  as a cross-check. Falls back to slicing the full volume PDF when there
  is no per-treaty file (the output then says `"via": "volume-pdf"` and
  gives both the PDF page range and the `printed_pages` those pages
  carry). `--from-volume` slices the volume PDF even when a per-treaty
  file exists (see step 7).
- `volume <N> [--search STR] [--json]` — list a UNTS volume's table of
  contents: registration number, first page, title (Annex A entries,
  i.e. later actions on earlier treaties, are flagged).
- `fetch <name-or-ref> [--no-text]` — combo: resolve a name (or accept a
  ref), grab the status doc, then the text. If a name is ambiguous the
  command lists the candidates and exits; re-run with the ref.
- `show <ref> [--kind status|text] [--lang ..]` / `show --vol N --reg M`
  — print a previously cached extracted-text file.
- `index [--refresh]` — rebuild the chapter index (about 35 page
  fetches, 1–2 min). Not needed for normal use: the bundled snapshot
  (`cache/index.json`, 670 treaties incl. optional protocols and all of
  chapter XI) is seeded automatically.

## Cache layout

```
~/.cache/untc/index.json                             # title -> ref index (seeded from the bundled snapshot)
~/.cache/untc/treaties/<chapter>/<ref>/meta.json     # parsed metadata (English; meta.fr.json for French)
~/.cache/untc/treaties/<chapter>/<ref>/status.en.pdf
~/.cache/untc/treaties/<chapter>/<ref>/status.en.txt
~/.cache/untc/treaties/<chapter>/<ref>/text.en.pdf
~/.cache/untc/treaties/<chapter>/<ref>/text.en.txt
~/.cache/untc/unts/v<vol>-I-<reg>/text.en.{pdf,txt} # texts fetched by --vol/--reg or --page
~/.cache/untc/unts/volumes/v<vol>.pdf                # full volume PDFs (+ v<vol>.pages.json)
```

`status.en.txt` is the most useful file: one line per participant with
the signature and ratification/accession dates
(`Norway ....... 20 Mar 1968 13 Sep 1972`), followed by the full text of
every declaration, reservation and objection, organised by state. It's
plain text and easy to grep.

`meta.json` holds the parsed bits. Read this first when answering quick
factual questions (parties count, entry into force, registration number)
to avoid re-reading the PDF text.

## MTDSG ref format

Refs are written exactly as UNTC writes them (the CLI also accepts
`iv-11b`, `IV.11.b` and normalises them):

| Form | Example | When used |
|---|---|---|
| `ROMAN-N` | `IV-4`, `XXIII-1` | Standard treaties |
| `ROMAN-N-x` | `IV-11-b`, `IV-9-b`, `XXVII-7-d` | Optional protocols and amendments (`a`, `b`, ... in adoption order — `IV-11-a` is an *amendment* to the CRC, the protocols are `IV-11-b/c/d`) |
| `ROMAN-L-N` | `XI-B-16`, `XI-A-1` | Chapter XI (transport) is split into sub-chapters A–E |
| `ROMAN-L-N-N` | `XI-B-16-1` | The UN vehicle Regulations annexed to the 1958 Agreement |

`status`, `text`, and `fetch` resolve refs directly from the
predictable `doc/Publication` URL — **no index needed** when the ref
is known. The index is only used for name-based `lookup` / `fetch`.

## Workflow guidance

1. **If the ref is already known** (e.g. "IV-4", "IV-11-b") call
   `status` or `fetch` directly.
2. **If only a name is given**, use `fetch "<name>"` or `lookup
   "<name>"`. Acronyms resolve through the alias table; other names
   through the bundled index. If `fetch` reports the name as ambiguous,
   pick the right ref from its candidate list.
3. **Prefer reading `meta.json` for factual questions** (parties count,
   entry into force, registration number) — it's already parsed.
4. **For "what reservations did $STATE make"** open
   `status.<lang>.txt` and search for the state name. The participant
   table comes first (one row per state); reservations and declarations
   follow, organised by state in alphabetical order.
5. **For the actual treaty text** open `text.<lang>.txt`. The `en`
   file is the English text; `fr` the French; `other` the remaining
   authentic languages in one file. A text sliced from a volume PDF
   contains every authentic language in sequence.
6. **For a treaty with no MTDSG entry** (bilateral treaties, treaties
   with another depositary such as the NPT, NATO or the Geneva
   Conventions): there is no status doc, so parties and reservations must
   come from the depositary. The text is still in the UNTS, and is often
   the best source for it: use `fetch NPT` / `fetch NATO` for the
   built-in ones, otherwise `text --vol N --page P` from the
   citation, or `volume N --search ...` to find the registration number.
7. **Check the pages you were given before quoting a sliced text.** The
   output of `text` carries `printed_pages` — the folios the slice
   actually holds — and `resolved_from.entry` when a `--page` citation
   was mapped to a registration number. If either carries a `warning`,
   or the printed pages do not contain the page cited, the contents of
   that volume were mis-parsed: run `volume N --search <title words>`
   and confirm the registration number before reading. The early volumes
   are OCR'd, and their contents page column is the first thing to go.
   `printed_pages` does not catch a page that is present but cropped:
   some per-treaty PDFs have a page shorter than the rest, with text cut
   off (the NATO treaty's p. 246 loses the second paragraph of Article
   5). `text` then returns `short_pages` and a `warning`; re-run with
   `--from-volume` and quote the named printed page from that slice.
8. **If a download fails**, the CLI says whether the status doc, the
   per-treaty file or the whole volume is missing. The newest volumes
   (e.g. vol. 3370, the TPNW) are not yet published as PDFs; the error
   then gives the treaty's details page, where the certified true copy
   is linked. Never reconstruct treaty text from memory.

## Citation

Always cite the source URL UNTC uses. `status` and `text` both write
their `source_url` into the JSON output. Format:

> *MTDSG status as of [status_date], UN Treaty Collection, [source_url]*

Use `status_date` from the JSON, not today's date: the participant list
is only as current as the document the UN last generated. If the
question turns on a very recent ratification, run `status <ref> --force`
and check the treaty's `details_url` page as well.
>
> *UNTS [volume] p. [page], registration No. [reg], [source_url]*

For a text sliced from a volume PDF, cite the volume PDF URL and the
printed page — `printed_pages` in the output, or the running header on
the page you quote — not the PDF page index. Do not take the page from
the parsed contents alone; in the OCR'd early volumes that column is
unreliable.

## Out of scope

- Depositary notifications (CN feed) and structured JSON extraction of
  the parties table / reservations — the status text has them and is
  greppable.
- League of Nations Treaty Series (LNTS) and the "filed and recorded"
  series II are not indexed; `text --series II --vol --reg` builds the
  URL if you have the numbers.
- Council of Europe treaties (use `ets`), EU law (`eurlex`), ICJ
  jurisdiction declarations (`icj`).
