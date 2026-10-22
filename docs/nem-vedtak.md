# nem-vedtak — why the decisions are not bundled

Decided 2026-10-14: the NEM decisions are **not** shipped in the repo.
Single decisions are fetched live; cross-corpus search uses a persistent
local copy in a connected folder (CLAUDE.md, "Design rules": corpora).
Don't propose bundling again unless the maintainer raises it.

## Reasons

- Named appellants would stay in the repo after NEM edits or withdraws a
  decision: a copy in a public repo is a new publication, and it stays in git
  history and in every installed plugin copy (CLAUDE.md, "Personal data").
- There may be a database right (åvl. § 24, cf. Lovdata v. Rettspraksis.no).
- Copyright is probably not a problem (åvl. § 14).

## If the maintainer raises it again

A design is ready:

- bundled `data/` plus a `snapshots.json` entry
- `sync --base <bundle> --dir <scratch>` fetches only sitemap-lastmod deltas
  (lastmod is per page and reliable; 158 pages carry a 2021 migration date)
- removed slugs are hidden at search time
- optionally, a scheduled GitHub Action refreshes the data and bumps the version