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
directory and share both. Tell the user to save them in the same folder,
then drag the `.rdf` into Zotero.

## Direct import with Zoteus

1. `zotero_whoami`. If the desktop app is not reachable, Zoteus writes
   through the cloud, which needs a Zotero API key; say so if it fails.
2. **Library:** the user's own library unless they name a group or a
   collection (group: numeric `library_id` from `zotero_groups` with
   `library_type: "group"`; collection keys from `zotero_list_collections`
   for that library).
3. **Duplicates:** `zotero_search_items` with the treaty number as printed
   ("ETS No. 5") and a title word, without `itemType` (statute titles are in
   `nameOfAct`, so hits may show as "(untitled)"). If an existing item looks
   like the same treaty, show it and ask: add the PDF to it, or create a new
   item.
4. **Ask before writing:** "Save *<title>* (<number>) to <library /
   collection>?"
5. `zotero_create_items` with the `items` array from the JSON unchanged (add
   `collections` if chosen). Note the new item's key.
6. **PDF:** `zotero_attach_file` with `parent` = the key and `url` = `pdf.url`
   from the JSON (a public rm.coe.int link; Zoteus downloads it), `title`
   "Full Text PDF". If it fails, follow **When the PDF is not attached**.
7. Report what was made: library, collection, PDF yes/no.

## When the PDF is not attached

The user must always learn that an item has no PDF, so they can add it
themselves. This applies when the script prints a line starting
`PDF NOT ATTACHED:`, when `zotero_attach_file` fails, and when the `.rdf`
reaches the user without the `.pdf` beside it.

Say it in the reply, not only in the log: which treaty, where the PDF is
(the outputs folder, or its rm.coe.int link), and how to add it: in Zotero,
drag the PDF onto the item, or right-click the item → *Add Attachment* →
*Attach Stored Copy of File*.
