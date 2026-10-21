# untc — Zotero-ready treaties

Supplementary to [`SKILL.md`](SKILL.md). Load this file when the user wants a
UN treaty **in Zotero**: "Zotero-ready", "Zotero RDF for the ICCPR", "add the
VCLT to my Zotero library", "import the NPT into Zotero".

The result is one Zotero **statute** item with the English UNTS text attached
as a PDF. It is entered like the UNCLOS item in the shared group library
*Norsk henvisningsstandard for rettsvitenskapelige tekster – eksempler*, so it
cites correctly with that style ("1833 UNTS 3").

There are two routes. Unless the user has already said which they want, ask
once: an RDF file to drag into Zotero, or straight into their library (only
offer the second when the Zoteus tools, `zotero_*`, are available).

**Whichever route, tell the user when the item ends up without its PDF** —
see **When the PDF is not attached**.

## Make the item

Treaties deposited with the Secretary-General — an MTDSG ref or an alias:

```bash
OUT_DIR=$(mktemp -d)
python3 {SKILL_DIR}/scripts/zotero_treaty.py XXIII-1 --out "$OUT_DIR"   # or ICCPR, UNCLOS …
```

Any other treaty registered in the UNTS (NPT, Geneva Conventions, Chicago
Convention, bilaterals) — the `objid` from `untc.py lookup` or `unts-search`:

```bash
python3 {SKILL_DIR}/scripts/zotero_treaty.py --objid 08000002801d56c5 --out "$OUT_DIR"
```

For a name, run `untc.py lookup "<name>"` first and pass the ref or objid it
gives. It writes `<base>.pdf`, `<base>.rdf` and `<base>.zotero.json`, e.g.
`UNTS_1155_331_VCLT.*`. A line starting `NOTE:` names a field the UN's
records could not supply; pass it on.

What the item holds:

| Zotero field | Value | VCLT |
|---|---|---|
| Name of Act | the title as the MTDSG index or the UNTS gives it (not the capitals of the status document) | Vienna Convention on the Law of Treaties |
| Code / Code Number / Pages | `UNTS` / volume / first page; `LNTS` / volume for League of Nations treaties (no page in the UN's records) | UNTS / 1155 / 331 |
| Date Enacted | entry into force (the definitive one); **empty when not in force** or only applied provisionally | 1980-01-27 |
| Short Title | only a well-known abbreviation (ICCPR, VCLT, UNCLOS, NPT …) | VCLT |
| History | protocols, amendments, annexes and regulations: `Parent treaty: <title> (MTDSG IV-9)` | — |
| URL | the treaty's page on treaties.un.org | MTDSG details page |
| Language | English | English |
| Extra | `type: treaty`, `available-date: <conclusion>`, `provisional application: <date>`, `status: …` when not (definitively) in force, `MTDSG: <ref>`, `depositary: …`, `UN registration no.: I-18232` (series I, II, or A for an entry recorded under its parent; League treaties: `League of Nations registration no.`) | type: treaty / available-date: 1969-05-23 / MTDSG: XXIII-1 / depositary: Secretary-General of the United Nations / UN registration no.: I-18232 |

What to say when you deliver it:

- **Not in force** (or only provisionally applied): the status line is dated
  and goes stale when the treaty enters into force.
- **No UNTS page yet** (recent volumes, e.g. the TPNW in vol. 3370): the
  citation lacks the page until the volume is printed.
- **League of Nations treaties**: the LNTS page must be added by hand if the
  user cites it.
- **A text cut from a volume PDF** (the output says `[pdf] pages … of the
  UNTS volume PDF`) holds every authentic language in sequence, not only
  English.

## RDF route

Copy the `.pdf` and the `.rdf` (not the `.zotero.json`) to the outputs
directory and share both. The `.rdf` finds the PDF only when the two files
sit in the same folder, so always say this with them, in these words:

> Download both files into the same folder first, then drag the `.rdf` into
> Zotero from there. If you open the `.rdf` straight from this chat, Zotero
> imports the treaty without its PDF.

If the user would rather skip that step and the Zoteus tools are available,
offer the direct import below.

## Direct import with Zoteus

1. `zotero_whoami`. If the desktop app is not reachable, Zoteus writes
   through the cloud, which needs a Zotero API key; say so if it fails.
2. **Library:** the user's own library unless they name a group or a
   collection (group: numeric `library_id` from `zotero_groups` with
   `library_type: "group"`; collection keys from `zotero_list_collections`
   for that library).
3. **Duplicates:** `zotero_search_items` with the short title or a title
   word plus the UNTS volume, without `itemType` (statute titles are in
   `nameOfAct`, so hits may show as "(untitled)"). If an existing item looks
   like the same treaty, show it and ask: add the PDF to it, or create a new
   item.
4. **Ask before writing:** "Save *<title>* (<citation>) to <library /
   collection>?"
5. `zotero_create_items` with the `items` array from the JSON unchanged (add
   `collections` if chosen). Note the new item's key.
6. **PDF:** if the JSON's `pdf` has a `url` (a per-treaty file on
   treaties.un.org), `zotero_attach_file` with `parent` = the key and that
   `url`, `title` "Full Text PDF". A text cut from a volume PDF has no `url`
   of its own: it exists only as the `.pdf` file, so attach it through
   **Attaching a PDF that is only in the cloud** below. Do the same if
   Zoteus cannot download the `url`.
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
5. `device_commit_files` with `devicePath` = `<folder>\untc\<base>.pdf`
   (the folder as `connectedFolders` spells it; the subfolder is created).
6. `zotero_attach_file` with `parent` = the item key, `path` = the path the
   commit reports under `written`, `title` "Full Text PDF".
7. Zotero stores its own copy, so the file in `<folder>\untc\` is no
   longer needed. Do not delete it (deleting in the connected folder is off
   unless the user turns it on): tell the user it is there and can be
   deleted.

## When the PDF is not attached

The user must always learn that an item has no PDF, so they can add it
themselves. This applies when the script prints a line starting
`PDF NOT ATTACHED:` (its reason says why: not registered yet, volume not
published, League of Nations treaty …), when `zotero_attach_file` fails or
is skipped, and when the `.rdf` reaches the user without the `.pdf` beside
it. If the user says the item came in without its PDF, the usual cause is a
`.rdf` opened straight from the chat.

Say it in the reply, not only in the log: which treaty, where the text is
(the outputs folder, the link the reason gives, or the treaty's page), and
how to add it: in Zotero, drag the PDF onto the item, or right-click the
item → *Add Attachment* → *Attach Stored Copy of File*.
