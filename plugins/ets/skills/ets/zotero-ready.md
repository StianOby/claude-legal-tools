# ets — Zotero-ready treaties

Supplementary to [`SKILL.md`](SKILL.md). Load this file when the user wants a
Council of Europe treaty **in Zotero**: "Zotero-ready", "Zotero RDF for the
ECHR", "add CETS 210 to my Zotero library", "import the Istanbul Convention
into Zotero".

The result is one Zotero **statute** item with the English treaty text
attached as a PDF. It is entered like the ECHR item in the shared group
library *Norsk henvisningsstandard for rettsvitenskapelige tekster –
eksempler*, so it cites correctly with that style.

There are two routes. Unless the user has already said which they want, ask
once: an RDF file to drag into Zotero, or straight into their library (only
offer the second when the Zoteus tools, `zotero_*`, are available).

**Whichever route, tell the user when the item ends up without its PDF** —
see **When the PDF is not attached**.

## Make the item

```bash
OUT_DIR=$(mktemp -d)
python3 {SKILL_DIR}/scripts/zotero_treaty.py <ref> --out "$OUT_DIR"
```

`<ref>` is anything `coe.py` accepts (`5`, `ECHR`, `"CETS 210"`, a title).
It writes `<base>.pdf`, `<base>.rdf` and `<base>.zotero.json`, e.g.
`ETS_5_ECHR.*` or `CETS_210_Istanbul_Convention.*`. Exit 7 is the same
Treaty Office outage as in SKILL.md.

What the item holds:

| Zotero field | Value | ECHR |
|---|---|---|
| Name of Act | English title, without "(ETS No. 005)" | Convention for the Protection of Human Rights and Fundamental Freedoms |
| Public Law Number | `ETS No. N` (1–193), `CETS No. N` (194 on), no leading zeros | ETS No. 5 |
| Date Enacted | entry into force; **empty when not in force** | 1953-09-03 |
| Short Title | only a well-known abbreviation (ECHR, FCNM, Istanbul Convention …) | ECHR |
| History | protocols only: `Parent treaty: ETS No. 5`, plus "(this amending protocol is integrated into it)" where the Treaty Office says so | — |
| URL | the treaty's page on coe.int | …treaty-detail&treatynum=005 |
| Language | English | English |
| Extra | `type: treaty`, `available-date: <opened for signature>`, `status: not in force (as of <today>)` when not in force, `UN registration no.: N` | type: treaty / available-date: 1950-11-04 / UN registration no.: 2889 |

A protocol carries its parent's UN registration number; that is how the UN
records protocols. For a treaty not in force, say so when you deliver it: the
status line is dated and goes stale when the treaty enters into force.

The attached text is the one the Treaty Office publishes now. For the ECHR
that is the text as amended by the later protocols, not the 1950 original.

## RDF route

Copy the `.pdf` and the `.rdf` (not the `.zotero.json`) to the outputs
directory and share both. The `.rdf` finds the PDF only when the two files
sit in the same folder, so always say this with them, in these words:

> Download both files into the same folder first, then drag the `.rdf` into
> Zotero from there. If you open the `.rdf` straight from this chat, Zotero
> imports the treaty without its PDF.

If the user would rather skip that step and the Zoteus tools are available,
offer the direct import below.

### A PDF over 30 MiB

The script prints `LARGE PDF:` when the PDF is over 30 MiB, the most
`SendUserFile` and `device_commit_files` take. The PDF then cannot leave the
cloud sandbox, so:

1. **Prefer the Zoteus route** if its tools are available: Zotero downloads
   the PDF itself from `pdf.url`, whatever its size.
2. Otherwise put both files in the connected folder, the PDF fetched from
   the user's own computer (not yet tested in Cowork):
   - copy the `.rdf` there as in **Attaching a PDF that is only in the
     cloud**, steps 1 and 3–5 (the folder `<folder>\ets\`);
   - load `device_bash` (ToolSearch `select:mcp__remote-devices__device_bash`)
     and download the PDF into the same folder, under the name the `.rdf`
     expects. rm.coe.int refuses `curl`'s default request (403) and serves
     the one the skill sends:
     `curl -fsSL -A "ets-skill/0.2 (treaty research tool, Python-urllib)" -H "Accept: application/pdf,*/*" -o "$HOME/mnt/<folder name>/ets/<base>.pdf" "<pdf.url>"`
     (`$HOME/mnt/<folder name>/` is the connected folder as the local shell
     sees it; `ls -d "$HOME"/mnt/*/` lists it);
   - tell the user to drag the `.rdf` into Zotero from that folder.
3. If neither works, deliver the `.rdf` alone, give the PDF link
   (`pdf.url`), and say the PDF must be downloaded into the same folder as
   the `.rdf` before the import, or added to the item afterwards.

Treaty texts on rm.coe.int are small (100–500 KB for the ones tried), so
this is rare.

## Direct import with Zoteus

1. `zotero_whoami`. If the desktop app is not reachable, Zoteus writes
   through the cloud, which needs a Zotero API key; say so if it fails.
2. **Library:** the user's own library unless they name a group or a
   collection (group: numeric `library_id` from `zotero_groups` with
   `library_type: "group"`; collection keys from `zotero_list_collections`
   for that library).
3. **Duplicates:** search by the treaty number, not the title: titles of
   treaties are generic and a full-text search for one gives hundreds of hits.
   `zotero_search_items` with `q` = the number **with double quotes around
   it as part of the query** (`"ETS No. 5"`) and `itemType: "statute"`. Unquoted, Zotero matches
   each word on its own, and every CoE treaty has "ETS" and "No" (20 hits for
   `ETS No. 5`, 2 for `"ETS No. 5"`, tested against a real library
   2026-10-22). It also finds items entered by hand, which carry the number
   in the same field. Confirm a hit by its Public Law Number before calling
   it a duplicate (`"ETS No. 5"` also matches "ETS No. 5" inside a longer
   text). If it is the same treaty, show it and ask: add the PDF to it, or
   create a new item.
4. **Ask before writing:** "Save *<title>* (<number>) to <library /
   collection>?"
5. `zotero_create_items` with the `items` array from the JSON unchanged (add
   `collections` if chosen). Note the new item's key.
6. **PDF:** `zotero_attach_file` with `parent` = the key and `url` = `pdf.url`
   from the JSON (a public rm.coe.int link; Zoteus downloads it), `title`
   "Full Text PDF". If rm.coe.int refuses Zoteus, attach the `.pdf` the
   script made instead: **Attaching a PDF that is only in the cloud** below.
7. Report what was made: library, collection, PDF yes/no.

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
5. `device_commit_files` with `devicePath` = `<folder>\ets\<base>.pdf`
   (the folder as `connectedFolders` spells it; the subfolder is created).
6. `zotero_attach_file` with `parent` = the item key, `path` = the path the
   commit reports under `written`, `title` "Full Text PDF".
7. Zotero stores its own copy, so the file in `<folder>\ets\` is no
   longer needed. Do not delete it (deleting in the connected folder is off
   unless the user turns it on): tell the user it is there and can be
   deleted.

## When the PDF is not attached

The user must always learn that an item has no PDF, so they can add it
themselves. This applies when the script prints a line starting
`PDF NOT ATTACHED:`, when `zotero_attach_file` fails, and when the `.rdf`
reaches the user without the `.pdf` beside it. If the user says the item
came in without its PDF, the usual cause is a `.rdf` opened straight from
the chat.

Say it in the reply, not only in the log: which treaty, where the PDF is
(the outputs folder, or its rm.coe.int link), and how to add it: in Zotero,
drag the PDF onto the item, or right-click the item → *Add Attachment* →
*Attach Stored Copy of File*.
