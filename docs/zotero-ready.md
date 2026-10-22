# Zotero-ready output — maintainer notes

Read this before any work on a skill's Zotero-ready output. The short rules
are in CLAUDE.md ("Zotero-ready output"); this file has the rest: how it is
built, how a new skill is added, the mapping decisions, testing, and status.

## How it is built

Zotero-ready output is an RDF file to drag into Zotero, or a direct import
through the Zoteus MCP (`zotero_*` tools in Claude Desktop). The shared
builder `shared/zotero-rdf/zotero_rdf.py` turns one item in Zotero's own JSON
into RDF that matches Zotero's own export translator, and also writes
`<base>.zotero.json` for `zotero_create_items`. Plugins carry copies
(`.github/scripts/check-shared.py`). `tests/zotero-rdf/` compares its output
with Zotero's own export of the 33 example items in the shared group library
*Norsk henvisningsstandard for rettsvitenskapelige tekster – eksempler*
(group 4308632), which is also the reference for every mapping decision.

Each skill has a script that builds the item (`zotero_book.py`,
`zotero_treaty.py`, `zotero_agreement.py`) and a `zotero-ready.md` that
Claude loads only for Zotero requests, so the main SKILL.md stays short.

## Handing files over in Cowork

- **RDF route:** the `.rdf` references the PDF by filename, and Zotero's
  import never downloads a URL path (a URL becomes a link, not a file). So
  the two files must sit in one folder, and every `.rdf` comes with a fixed
  message saying so. Opening the `.rdf` straight from the chat imports the
  item without its PDF.
- **Zoteus route:** `zotero_attach_file` takes a URL it can download or a
  path on the user's computer. A PDF made in the cloud sandbox goes to the
  connected folder with `device_commit_files` (source under
  `/mnt/user-data/outputs/`), and is attached by the path it reports;
  `get_device_info.connectedFolders` gives the real host path. The copy is
  left in the folder: nothing in the connected folder is ever deleted.
  Verified 2026-10-21 with a 22 MB UNTS slice.
- **30 MiB:** `SendUserFile` and `device_commit_files` take at most that.
  The builder prints `LARGE PDF:` above it. Then Zoteus by URL; else the
  local shell downloads the PDF straight into the connected folder beside the
  `.rdf` (not yet tested); else the `.rdf` with the PDF link. rm.coe.int
  refuses `curl`'s default request and serves the ets skill's user agent.
- **Duplicates:** by identifier, never by title (a full-text title search for
  a treaty gave 296 hits). Tested against a real library 2026-10-22:
  `22016A0528` and the Consilium ID find exactly the item; `"ETS No. 5"`
  needs the quotes (20 hits without, 2 with); `I-31363` finds nothing, the
  bare `31363` finds it.

## Adding a skill

1. Ask the maintainer which skill is next; they pick the order.
2. Probe the source broadly before mapping: all records when there are few
   (ets: all 234 treaties), otherwise a sample across eras and kinds plus the
   special cases (untc: 99 records; eu-agreements-treaties: 37, captured in
   Cowork because the site answers only a browser). Look for fields that
   vary, are missing, or mean something other than their name.
3. Compare with the group library's examples of the same kind, and put the
   open choices to the maintainer, with suggested extra fields.
4. Build the item script and `zotero-ready.md` from an existing skill;
   register the builder copy in `check-shared.py`. Test every variation the
   probe found offline (`tests/<name>/`), and keep a live check where the
   matching depends on a remote source.
5. Give the maintainer Cowork test prompts; update the status below.

## Testing against Zotero

When Zotero is open on the computer Claude Code runs on, its local API
answers from the shell, e.g.
`http://127.0.0.1:23119/api/users/0/items?q=…&qmode=everything&format=json`
(header `Zotero-API-Version: 3`; `/items/top` for parent items only,
`/connector/ping` returns 200 when Zotero is up). Zoteus searches through
the same API, so its search behaviour can be checked here against the real
library, including the `0_TEST` collection that Cowork tests write to. Use
it read-only: never write to the library from here. The maintainer can
always open Zotero on request.

## Status (2026-10-22)

- **nbno**: done and live-tested 2026-10-21. Tested: the RDF import, the
  Zoteus route (the Web Link as a `linked_url` child, PDF attachment, and on
  a duplicate, an offer to add the PDF to the existing item) and the
  local-route folder choice.
- **ets**: done and live-tested 2026-10-21.
- **untc**: done and live-tested 2026-10-21 (VCLT, Paris Agreement, NPT).
- **eu-agreements-treaties**: done and live-tested 2026-10-22 (2016032,
  2024009, the 1972 Accession Treaty). Cellar is reached from the cloud
  sandbox.
- **Deferred by the maintainer (2026-10-22); don't propose these until they
  raise them:**
  - norges-traktater: may be solved in lovdata-zotero (if it exposes the
    treaty metadata) rather than here.
  - hudoc, eurlex (case law), efta-court, icj: blocked on the open question
    below.
  - nem-vedtak: niche, and how NEM decisions are entered in Zotero is
    undecided.
- Not candidates: lovdata-api and lovdata-pro (Lovdata, out of scope);
  kildesjekk (reads Zotero rather than producing items for it).

## Mappings

Books (nbno): Zotero `book`, all nb.no item types included; the nb.no link
as a Web Link attachment "eBok (nb.no)", URL field empty.

Treaties (Zotero `statute`):

- The treaty number follows each source's pattern in the group library:
  `publicLawNumber` "ETS No. 5" (CoE, no leading zeros),
  `code`/`codeNumber`/`pages` (UNTS), `code`/`pages` (OJ).
- Not in force: leave `dateEnacted` empty and add a dated "status:" line in
  Extra.
- Parent treaty in History.
- URL field: the source's treaty page (ets, untc), not a Web Link
  attachment; eu-agreements-treaties uses the ELI (below).
- Registration number with its series (I-/II-/A-/LoN-) in Extra.
- untc:
  - UNTS volume/page in `code`/`codeNumber`/`pages`; LNTS and volume for
    League treaties.
  - Definitive entry into force only; a provisional date goes in Extra.
  - MTDSG reference and depositary in Extra.
- eu-agreements-treaties:
  - Flow: `__cs.zotero(id)` in the browser gives a base64 record, and
    `zotero_agreement.py --record-b64` matches it to the OJ publication in
    Cellar (publications.europa.eu/webapi/rdf/sparql).
  - OJ reference: `code` "EUT <OJ year> L" with `pages` "<issue>/<page>".
    For act-by-act OJ (from October 2023): `code` "EUT L" with `pages`
    "<year>/<number>". Always "EUT".
  - URL is the ELI, or EUR-Lex by CELEX when there is no ELI.
  - `dateEnacted` is the agreement-level entry into force.
  - ELIs with an "(n)" suffix don't resolve on EUR-Lex. That is a bug in
    EUR-Lex's resolver: keep the ELI and don't work around it. (A pre-2023
    agreement borrows the number of the Council decision it was published
    with; "(n)" is its position among the instruments of that type under
    the decision.)
  - Matching the OJ publication: exact CELEX lookups for every act the
    record's OJ issues and signature date allow, then agreements signed
    that day, then every act in the OJ issues themselves (sector-4
    conventions, primary law: the whole `…/TXT`). A conflicting signature
    date or party name rules a candidate out. 32 of a 34-agreement probe
    found, all correctly (`tests/eu-agreements-treaties/live_cellar_match.py`).
  - Cellar traps: exact `VALUES ?celex {…}` lookups take 0.1 s, but pattern
    filters take seconds to minutes; long queries need POST (GET gives HTTP
    414); it answers 503 now and then, so retry. EUR-Lex itself blocks
    scripts (an empty 202).

## Still open

- How international cases (ECtHR, CJEU, EFTA Court, ICJ) are entered. The
  group library has no examples, and the maintainer has not yet developed
  style support for them or decided whether it is feasible, so no field
  mappings exist.
