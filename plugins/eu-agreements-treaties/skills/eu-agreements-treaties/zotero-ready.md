# eu-agreements-treaties — Zotero-ready agreements

Supplementary to [`SKILL.md`](SKILL.md). Load this file when the user wants
an agreement from the Council's Treaties Office database **in Zotero**:
"Zotero-ready", "Zotero RDF for the EEA Agreement", "add 2016032 to my Zotero
library".

The result is one Zotero **statute** item with the English text as published
in the Official Journal attached as a PDF. It is entered like the Dublin and
Schengen items in the shared group library *Norsk henvisningsstandard for
rettsvitenskapelige tekster – eksempler*: `code` "EUT 2001 L", `pages`
"93/40", the ELI as URL.

An ELI with a sequence suffix, such as `…/2016/837(1)/oj` (the first
agreement published with Council Decision 2016/837), lands on "No results
found" in EUR-Lex (seen 2026-10-22), although EUR-Lex shows that ELI on the
agreement's own page. It is EUR-Lex's bug, and the item keeps the ELI. If
the user reports the link as broken, say so and give the EUR-Lex address by
CELEX (`https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:<CELEX>`,
the CELEX is in Extra) as a working link for now.

There are two routes. Unless the user has already said which they want, ask
once: an RDF file to drag into Zotero, or straight into their library (only
offer the second when the Zoteus tools, `zotero_*`, are available).

**Whichever route, tell the user when the item ends up without its PDF or
its OJ citation** — see **When the PDF is not attached**.

## Make the item

Two steps, because the database answers only the browser tab and the rest
comes from the EU Publications Office (Cellar), which the cloud sandbox
reaches:

1. In the tab (Step 0 of SKILL.md done), `await __cs.zotero("2016032")`. It
   returns `{b64, title, is_proces_verbal}`. A Procès-Verbal of
   Rectification is a correction to language versions, not an agreement: say
   so and make the item for the agreement it corrects instead.
2. In `Bash`, pass the `b64` string unchanged (it is base64, so quotes in
   titles cannot break the command):

   ```bash
   OUT_DIR=$(mktemp -d)
   python3 {SKILL_DIR}/scripts/zotero_agreement.py --record-b64 '<b64>' --out "$OUT_DIR"
   ```

It writes `<base>.pdf`, `<base>.rdf` and `<base>.zotero.json`, e.g.
`EUT_2016_L_141_3_Agreement_between_the_European_Union_Iceland_the.*`.
About a second or two per agreement; Cellar answers 503 now and then, which
the script retries.

What the item holds:

| Zotero field | Value | 2016032 |
|---|---|---|
| Name of Act | the database's title without its editorial insertions ("- See 2014013 (EEA Agreement)", "(BG/ES/…)", "(Deposited with …)", "(including …)") | Agreement between the European Union, Iceland, the Principality of Liechtenstein and the Kingdom of Norway on an EEA Financial Mechanism 2014-2021 |
| Code | `EUT <OJ year> <series>`; `EUT L` in the act-by-act OJ (since October 2023) | EUT 2016 L |
| Pages | `<issue>/<first page>`; `<year>/<act number>` in the act-by-act OJ | 141/3 |
| Date Enacted | the agreement-level entry into force; **empty when not in force** | 2017-09-01 |
| URL | the ELI; the EUR-Lex address by CELEX for older agreements without one | http://data.europa.eu/eli/agree_internation/2016/837(1)/oj |
| Language | English | English |
| Extra | `type: treaty`, `available-date: <signature>`, `provisional application: <date>`, `status: …` when not in force, `CELEX: …`, `Consilium: <id>`, `depositary: …` | type: treaty / available-date: 2016-05-03 / provisional application: 2016-08-01 / CELEX: 22016A0528(01) / Consilium: 2016032 |

How the OJ publication is found: the database lists every OJ reference of an
agreement — its text, but also Council decisions, notices of entry into
force, corrigenda and amendments, and sometimes with a wrong date. The script
looks up every act in those issues, and the agreements signed that day, and
picks the agreement itself by signature date and title. When that finds
nothing, it reads every act published in the OJ issues themselves: that
finds conventions numbered after their decision (Lugano 1988) and primary
law such as the 1994 Accession Treaty, whose whole text (`11994N/TXT`) it
takes over the treaty's separately catalogued parts; a primary-law match is
always reported as one to check. In a probe of 34 agreements from 1972 to
2026 it found 32, all correctly. It left two without a citation, rightly:
an exchange of letters not published on its own, and the 1972 Accession
Treaty, whose signature date Cellar has wrong (1970-04-22). It prefers no
citation to a wrong one.

Lines starting `NOTE:` are for the user; pass them on:

- **"the OJ publication of the agreement could not be identified"**: the
  item has no `code`/`pages`, its URL is the Treaties Office record, and the
  note lists the OJ references the database gives. Say the citation must be
  added by hand.
- **"matched to CELEX … on a weak title match"**: the signature date could
  not confirm the match. Show the user the matched title and ask whether it
  is the same agreement.
- **"the database lists this record as a bundle"**: the item describes the
  main agreement only.
- **"no ELI …"** / **"the first page … is not in Cellar"**: say which field
  is missing.

Also say, when it applies: the status line is dated and is the **EU's
perspective** (for Norway's own entry into force, `norges-traktater` is
authoritative); and an act-by-act OJ citation has no page.

## RDF route

Copy the `.pdf` and the `.rdf` (not the `.zotero.json`) to the outputs
directory and share both. The `.rdf` finds the PDF only when the two files
sit in the same folder, so always say this with them, in these words:

> Download both files into the same folder first, then drag the `.rdf` into
> Zotero from there. If you open the `.rdf` straight from this chat, Zotero
> imports the agreement without its PDF.

If the user would rather skip that step and the Zoteus tools are available,
offer the direct import below.

### A PDF over 30 MiB

The script prints `LARGE PDF:` when the PDF is over 30 MiB, the most
`SendUserFile` and `device_commit_files` take (the EEA Agreement with its
annexes is 37 MiB). The PDF then cannot leave the cloud sandbox, so:

1. **Prefer the Zoteus route** if its tools are available: Zotero downloads
   the PDF itself from `pdf.url`, whatever its size.
2. Otherwise put both files in the connected folder, the PDF fetched from
   the user's own computer (not yet tested in Cowork):
   - copy the `.rdf` there as in **Attaching a PDF that is only in the
     cloud**, steps 1 and 3–5 (the folder `<folder>\eu-agreements-treaties\`);
   - load `device_bash` (ToolSearch `select:mcp__remote-devices__device_bash`)
     and download the PDF into the same folder, under the name the `.rdf`
     expects:
     `curl -fsSL -o "$HOME/mnt/<folder name>/eu-agreements-treaties/<base>.pdf" "<pdf.url>"`
     (`$HOME/mnt/<folder name>/` is the connected folder as the local shell
     sees it; `ls -d "$HOME"/mnt/*/` lists it);
   - tell the user to drag the `.rdf` into Zotero from that folder.
3. If neither works, deliver the `.rdf` alone, give the PDF link
   (`pdf.url`), and say the PDF must be downloaded into the same folder as
   the `.rdf` before the import, or added to the item afterwards.

## Direct import with Zoteus

1. `zotero_whoami`. If the desktop app is not reachable, Zoteus writes
   through the cloud, which needs a Zotero API key; say so if it fails.
2. **Library:** the user's own library unless they name a group or a
   collection (group: numeric `library_id` from `zotero_groups` with
   `library_type: "group"`; collection keys from `zotero_list_collections`
   for that library).
3. **Duplicates:** search by an identifier, not the title: titles of
   agreements are generic and a full-text search for one gives hundreds of
   hits. `zotero_search_items` with `q` = the CELEX without its sequence
   (`22016A0528`) and `itemType: "statute"`; then the Consilium ID
   (`2016032`). Both found exactly the item in a real library (2026-10-22).
   An item entered by hand has neither, so if both find nothing, search the
   OJ citation's issue/page (`141/3`) and a distinctive title word.
   Confirm a hit by its Code and Pages before calling it a duplicate. If it
   is the same agreement, show it and ask: add the PDF to it, or create a new
   item.
4. **Ask before writing:** "Save *<title>* (<code> <pages>) to <library /
   collection>?"
5. `zotero_create_items` with the `items` array from the JSON unchanged (add
   `collections` if chosen). Note the new item's key.
6. **PDF:** `zotero_attach_file` with `parent` = the key and `url` = `pdf.url`
   from the JSON (a public https link on publications.europa.eu; Zoteus
   downloads it), `title` "Full Text PDF". If Zoteus cannot download it,
   attach the `.pdf` the script made: **Attaching a PDF that is only in the
   cloud** below.
7. Report what was made: library, collection, OJ citation yes/no, PDF yes/no.

## Attaching a PDF that is only in the cloud

Zoteus runs on the user's computer, so `zotero_attach_file` takes a file only
from a `url` it can download or a `path` on that computer. A PDF the script
made in the cloud sandbox gets there through the connected folder (verified
2026-10-21 with a 22 MB UNTS slice):

1. Load the tools with one ToolSearch call:
   `select:mcp__remote-devices__get_device_info,mcp__remote-devices__device_commit_files,mcp__remote-devices__device_request_folder_access`.
   If they are not there, follow **When the PDF is not attached**.
2. **Over 30 MB → stop here** and follow **When the PDF is not attached**:
   that is the copying cap.
3. Copy the PDF to `/mnt/user-data/outputs/` (`device_commit_files` takes
   files only from there, or a `fileUuid` from an earlier `SendUserFile`).
4. **Folder:** `get_device_info` → `connectedFolders`, which gives the real
   path on the user's computer (e.g. `C:\Users\…\Claude-legal-work`). With
   more than one, ask which. With none, ask the user which folder to connect
   (offer the folders you have seen exist, plus "another folder") and request
   exactly that one with `device_request_folder_access`; if they decline,
   follow **When the PDF is not attached**.
5. `device_commit_files` with `devicePath` = `<folder>\eu-agreements-treaties\<base>.pdf`
   (the folder as `connectedFolders` spells it; the subfolder is created).
6. `zotero_attach_file` with `parent` = the item key, `path` = the path the
   commit reports under `written`, `title` "Full Text PDF".
7. Zotero stores its own copy, so the file in `<folder>\eu-agreements-treaties\`
   is no longer needed. Do not delete it (deleting in the connected folder is
   off unless the user turns it on): tell the user it is there and can be
   deleted.

## When the PDF is not attached

The user must always learn that an item has no PDF, so they can add it
themselves. This applies when the script prints a line starting
`PDF NOT ATTACHED:` (no OJ publication identified, no English PDF in Cellar,
download failed), when `zotero_attach_file` fails or is skipped, and when
the `.rdf` reaches the user without the `.pdf` beside it. If the user says
the item came in without its PDF, the usual cause is a `.rdf` opened
straight from the chat.

Say it in the reply, not only in the log: which agreement, where the text is
(the outputs folder, or the OJ reference to open with the `eurlex` skill),
and how to add it: in Zotero, drag the PDF onto the item, or right-click the
item → *Add Attachment* → *Attach Stored Copy of File*.
