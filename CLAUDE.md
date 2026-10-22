# claude-legal-tools

A collection of Claude Code skills for working with legal and library sources
(Lovdata, EUR-Lex, HUDOC, ICJ, Nasjonalbiblioteket, etc.).

## Skill authoring rules

### Description length limit: 1024 characters

Every `SKILL.md` frontmatter `description:` field must be **≤ 1024 characters
after YAML parsing** (i.e. the joined string the loader sees, not the raw
source with line breaks and indentation). Skills with longer descriptions are
rejected by the loader.

This has been a recurring problem in this repo. When writing or editing a
description:

- Pack the trigger list densely — list keywords/identifiers as a
  comma-separated group, not as separate "or" clauses.
- Cut redundant phrasings of the same trigger (e.g. don't include both
  "fetch this old Norwegian newspaper" and "save these pages from
  Nasjonalbiblioteket" — one example per category is enough).
- Keep the structure: (1) when to use, (2) trigger keywords/URL patterns,
  (3) scope of material covered, (4) any sub-workflow variants, (5) what NOT
  to use it for.
- Verify before committing:

  ```bash
  python3 -c "
  import yaml, sys
  text = open(sys.argv[1]).read()
  fm = text.split('---', 2)[1]
  print(len(yaml.safe_load(fm)['description']))
  " plugins/<name>/skills/<name>/SKILL.md
  ```

  The number printed must be ≤ 1024. CI (`.github/workflows/validate.yml`)
  runs the same check on every PR.

## Repository layout

The repo is a Claude plugin marketplace (`.claude-plugin/marketplace.json`).
Each skill is its own plugin:

```
plugins/<name>/
  .claude-plugin/plugin.json   # manifest; holds the version
  skills/<name>/SKILL.md       # the skill; scripts/, references/ … beside it
```

Rules:

- A skill lives at `plugins/<name>/skills/<name>/` — the plugin name and the
  skill name are always the same. The `skills` path must be a *parent* of the
  `SKILL.md` directory, which is why there are two levels.
- **Every commit that touches a plugin's files must bump `version` in
  `plugins/<name>/.claude-plugin/plugin.json` by hand** (patch for ordinary
  changes, minor/major for notable ones). Claude Code caches plugins by
  version and users only receive updates when it changes. (Cowork's Update
  re-fetches the repo regardless of version — verified 2026-09-12 — so the
  bump is for Claude Code users.) CI (`validate.yml` →
  `.github/scripts/check-plugin-versions.sh`) fails a PR or push where a
  plugin changed without a version change.
- Browser helpers pasted into a tab (`scripts/browser/*.js`: hudoc, lovdata-pro,
  eu-agreements-treaties, nbno, norges-traktater) carry `const HELPER_VERSION = '<plugin
  version>'`. Re-pasting the same version is a no-op; a tab still holding an
  older helper gets it replaced. When you change a helper, set its
  `HELPER_VERSION` to the plugin's new version by hand; CI fails a changed
  helper whose `HELPER_VERSION` differs from its plugin's version.
  The skills paste a stripped copy made by `scripts/browser/paste.py` (shared
  from `shared/browser-paste/`): no comments, indentation or blank lines,
  30–55 % smaller, with strings, templates, regexes and line breaks untouched.
  Keep helpers stripper-friendly (plain JS; a regex literal never follows
  `)`), and keep one `window.__x = ` assignment and the `HELPER_VERSION`.
  `tests/browser-helpers/test_paste.js` reruns each helper's own suite on the
  stripped copy (via `stripped_preload.js`). Do not go back to fetching the
  helper from GitHub and `eval`-ing it: the Cowork safety check blocks that
  as "Code from External" (live session, 2026-09-30).
- **Tests live in `tests/<name>/` at the repo root, never inside a plugin.**
  Installing a plugin copies its whole folder (there is no ignore file), so
  anything under `plugins/` ships to every user. Tests find the skill via
  `Path(__file__).resolve().parents[2] / "plugins" / "<name>" / "skills" / "<name>"`
  (Python) or `path.join(__dirname, '..', '..', 'plugins', '<name>', 'skills', '<name>')`
  (Node). CI runs `tests/*/test_*.py` and `tests/*/test_*.js`.
- **No `\uXXXX` escapes in browser helpers.** `javascript_tool` decodes them
  before running the pasted code, so a decoded U+2028/U+2029 in a regex
  literal is a SyntaxError (norges-traktater, 2026-09-30). Use
  `String.fromCharCode(...)` or `\xNN`. `tests/browser-helpers/test_paste_safe.js`
  checks every helper.
- Never put `version` in the marketplace.json entries — it belongs in
  `plugin.json` only.
- Add new plugins to `.claude-plugin/marketplace.json` with
  `"source": "./plugins/<name>"` (explicit path; do not rely on
  `metadata.pluginRoot`, which needs a recent Claude Code and is not
  documented for Cowork). If a plugin is ever renamed, add a `renames` entry.
- The release workflow zips `plugins/<name>/skills/<name>/` so the `.zip`
  layout stays identical to the pre-marketplace releases.
- Validate locally with `npx -y @anthropic-ai/claude-code plugin validate .`
  and `… plugin validate plugins/<name> --strict`.
- **Shared files** (`shared/`, e.g. `shared/local-route/`) are the canonical
  copies of files several plugins carry — a plugin cannot reference anything
  outside its own folder. Edit only the canonical copy, then run
  `.github/scripts/check-shared.py --fix` and bump every plugin whose copy
  changed. The mapping lives in that script; CI fails if a copy differs.
  Keep `pack_for_local.sh` in step with the repo URL: the local route
  downloads scripts from `main` on GitHub and checks them by sha256.

## Cached data snapshots

Some skills ship data fetched from a live source (currently only the untc
treaty index; the ets index and the eu-agreements-treaties party list were
dropped on 2026-10-21 — both are now read live). Users get whatever was
checked in, so these go stale silently. Ship a snapshot only when building
the data live costs real time in every session (untc: a ~30 s crawl);
otherwise fetch it live on first use. `snapshots.json` at the repo root
lists every such file with its source, `last_refreshed` date and refresh
command; `.github/scripts/snapshots.py` keeps them honest.

The routine — no fixed schedule, just a check whenever the skills are
being worked on:

1. **At the start of any session that will change files under `plugins/`,
   run `.github/scripts/snapshots.py check`.** CI runs the same
   check and prints a warning for anything older than `max_age_days` (30);
   it does not block.
2. If a snapshot is stale and has a `refresh` command, refresh it with
   `.github/scripts/snapshots.py refresh <name>` (or `--all`). The script
   runs the command, prints the before/after record count, refuses to stamp
   if the count dropped by more than 10 % (a partial fetch), and writes
   today's date into `snapshots.json`. Commit the data, the manifest and
   the plugin's version bump together as their own commit —
   `<plugin>: refresh <name> snapshot (YYYY-MM-DD, N records)` — separate
   from whatever feature work prompted the session.
3. If a snapshot has `"refresh": null`, it needs a manual procedure
   (`refresh_manual`; none at present). Tell the user it is due and
   how; do not silently skip it. After the manual refresh, run
   `.github/scripts/snapshots.py mark <name>`.
4. Do not refresh a snapshot that is not stale unless asked; a refresh is a
   network fetch and a data diff, not part of ordinary edits.

**A snapshot is only a starting point, never the answer's limit.** Users
must never miss a newer treaty or party because a skill read old data. So a
skill that ships a snapshot must, at runtime, either refresh it from the live
source before relying on it for "not found" (untc: a miss on an index
older than 7 days rebuilds it), or read the live source directly (ets fetches
its index live on first use; eu-agreements-treaties reads the party list from
the live search form).
If it cannot refresh, it must print a `COVERAGE WARNING` with the snapshot's
date, and the SKILL.md must tell Claude to pass that on to the user.

When a skill gains a new checked-in file that is generated from a live
source, add an entry to `snapshots.json` in the same commit — `path`,
`source`, `last_refreshed`, and either a `refresh` shell command (run from
the repo root, must leave the file in place) or `refresh: null` plus a
`refresh_manual` description. Hand-written reference tables
(`references/*.md`) are not snapshots.

## Audience: Cowork only

The skills are built for Claude Cowork (Claude Desktop), not the Claude Code
CLI. The users are legal academics who install through Customize → Plugins /
Skills, so CLI-only features (`/plugin install`, `dependencies`
auto-install) cannot be assumed. Check every distribution mechanism against
the Cowork docs (claude.com/docs/cowork/guide/plugins) and test in Cowork.

## Design rules

- **Don't pin external dependencies.** Packages and servers the skills
  install at run time (eurlex-mcp-server via npx; nbno, ocrmypdf etc. via
  pip) use the bare name, with no version and not even `@latest`. Existing
  `--upgrade` flags are fine. The maintainer prefers the newest upstream
  release, and accepts the risk that upstream changes break something, over
  stale packages. Don't propose pinning in reviews or fixes.
- **Corpora: live lookup or a persistent local copy, never a session-only
  cloud copy.** For a skill over a downloadable corpus (first case:
  nem-vedtak; why it is not bundled: `docs/nem-vedtak.md`), fetch a single
  known item live, with no cache and no question.
  Cross-corpus search uses a local copy in a connected folder via the local
  route; ask for it once. If the user declines a folder, say that search
  needs the local copy and offer single lookups. A cloud copy is lost when
  the session ends, so the whole corpus would be downloaded again in every
  session.
- **Personal data.** Before checking in any source data (snapshots, bundled
  corpora, test fixtures), check it for personal data. Under the GDPR, a copy
  in this public repo is a new publication with the repo owner as
  controller. It also cannot easily be withdrawn: it stays in git history and
  in every installed plugin copy, and proper removal needs a history rewrite.
  Fetching or syncing live lets the source's removals and anonymisations
  take effect. Prefer metadata-only bundles or live routes when the texts
  name people. Anonymise fixtures the way `tests/nem-vedtak/fixtures/` does
  ("Person A", "Person B", …).

## Zotero-ready output

Several skills can make a Zotero item (an RDF file, or a direct import via
the Zoteus MCP), built by `shared/zotero-rdf/zotero_rdf.py`, each skill's
route in its own `zotero-ready.md`. **Before any Zotero work, read
`docs/zotero-ready.md`**: how it is built, how a skill is added, the mapping
decisions, testing against the local Zotero API, and status. The rules:

- Added one skill at a time; the maintainer picks the order and makes the
  mapping decisions, so ask before building the next skill.
- Always tell the user when an item ends up without its PDF.
- On the RDF route the `.rdf` must sit beside the `.pdf` (Zotero's import
  never downloads a URL path), so every `.rdf` comes with a fixed message
  telling the user to download both files into one folder.
- Duplicate checks search by identifier, never by title.
- For very old sources, don't add workarounds for quirks in a single item;
  look for fixes that help a whole class of items, and leave the rest with a
  note asking the user to add the field by hand.
- Lovdata material is out of scope for this repo.

## Tool quirks when editing this repo

- The Bash tool collapses a doubled backslash in its command text into a
  single one, even inside a quoted heredoc. A Python patch script sent as
  `python3 - <<'EOF'` therefore gets corrupted: an escaped `\b` in a regex
  becomes a literal backspace, and an escaped `\n` becomes a real newline.
  This once broke a regex in the icj skill. For any patch that contains
  backslashes, write the script to a file with the Write tool and run it, or
  build the backslash with `chr(92)`. In `re.sub` replacement strings, use a
  plain `str.replace` instead.
- The Write tool decodes a backslash-u escape in file content, just as
  `javascript_tool` does with pasted helpers. Never pass a literal
  backslash-u escape through a tool. Build it with `chr(92) + "u"` (Python)
  or `String.fromCharCode(92)` (JS).
