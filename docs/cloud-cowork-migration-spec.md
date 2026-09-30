# Spec: make claude-legal-tools work in cloud Cowork

Author: Stian Øby Johansen · 2026-09-30 · Target: Claude Code (VS Code) working in `claude-legal-tools`

## Background

From 6 October 2026, new Cowork tasks (Pro/Max) run in the cloud, not on the user's PC. Cloud sessions can already be used today. The aim is to make the skills work in cloud Cowork **now**, and to verify the remaining open points after the switch.

Tests in a cloud Cowork session (30 September 2026) found three places where work can run:

| Component | Tool prefix | Runs where | Egress IP | Skill files present? | Notes |
| --- | --- | --- | --- | --- | --- |
| Cloud sandbox | `Bash` | Anthropic cloud (`vm`) | 160.79.106.137 | Yes: `/root/.claude/plugins/synced/<id>/<plugin>/skills/<skill>/` | No `/sessions` |
| Browser pane | `mcp__remote-devices__Claude_Browser__*` (local Cowork: `mcp__Claude_Browser__*`) | Desktop app on user's PC | User's IP | n/a | Persistent profile with logins |
| Local shell | `mcp__remote-devices__device_bash` | Sandboxed Ubuntu 22.04 VM on user's PC (Hyper-V + bubblewrap, unprivileged, no Windows access except the connected folder) | User's IP | **No** | Needs a connected folder; home `/sessions/<user>/`; per-session scratch |

Key facts:

| Finding | Evidence |
| --- | --- |
| nbno `EVERYWHERE` items: work from the cloud sandbox | Ibsen `digibok_2016112429002` |
| nbno `NORWAY` items: 403 from the cloud sandbox, OK from the browser **and from the local shell** | Eckhoff `digibok_2021021607640`: `geo_check.py` exit 0 and 3-page PDF in the local shell |
| Lovdata blocks the cloud IP (405 Varnish IPS) on `lovdata.no` and `api.lovdata.no` | curl |
| `api.lovdata.no/v1/publicData/list` returns 200 from the local shell | curl |
| lovdata-pro works unchanged (all fetching happens in the browser) | Holship, avsnitt 77 |
| Local shell is not logged in anywhere (no browser cookies) | `/pro/` returns 302 to login |
| `request_access` browser tool is absent in some environments (Claude Code desktop) | Tool listing |

The approach: anything that needs the user's IP runs through the local shell, which is sandboxed and runs the existing scripts unchanged. Everything else stays in the cloud sandbox or the browser.

## Goals

1. Every skill works in a cloud Cowork session **today**, with the desktop app open and a folder connected when the local route is needed.
2. Skills keep working in local Cowork until 6 October and don't break in the Code tab.
3. Anything that needs the user's IP runs in the **sandboxed local VM**, never as unsandboxed Windows code.

## Non-goals

- Moving to Claude Code desktop, WSL or Docker.
- A local MCP server, unless Appendix A is triggered.

## Timing

Implement WP1–WP5 now. **Don't wait for the verification items (section V).** They are deferred until after 6 October 2026, when cloud sessions become the default and the result reflects the final setup. Where a design choice depends on an unverified point, use the working assumption below. Build it so it detects the situation at runtime and fails with a clear message, rather than hard-coding a guess.

### Working assumptions (until section V is done)

| Open point | Assumption to build on | Runtime safeguard |
| --- | --- | --- |
| `device_bash` stays available after 6 October | Yes | Detect it with ToolSearch; if it's absent, show the WP2.4 message |
| The cloud sandbox can read files the local shell writes to the connected folder | Unknown, so don't depend on it | Do the whole pipeline in whichever shell did the download. The final file lands in the connected folder |
| The local VM has `tesseract`/`ocrmypdf` | Unknown | Check with `command -v` before OCR steps; if missing, deliver the PDF without OCR and say so |
| Other hosts (HUDOC, ICJ, UNTC, CoE, EFTA Court, Consilium) are reachable from the cloud | Yes, since none has failed so far | Any 403/405 from the origin in the cloud triggers the local route (WP2.1) |
| `lovdata.no` is blocked from the cloud | **Confirmed** (405), so norges-traktater needs rerouting now (WP4) | n/a |
| Script bundles fit in a `device_bash` command | Yes for nbno (~10 KB base64) | Chunk above a threshold; abort with a message above a hard limit |
| FEIDE (`NB`) items work through the local route with a browser-captured cookie | Yes | On a 401/403, ask the user to log in again, then retry once |

---

## WP1: cross-environment plumbing (all skills)

### 1.1 Browser tool discovery

- Replace hard-coded `mcp__Claude_Browser__…` names and `select:` lists with a keyword search: ToolSearch `Claude_Browser`, max_results 64. Use whatever prefix comes back.
- In prose, refer to tools by suffix only (`preview_start`, `navigate`, `javascript_tool`, `get_page_text`, `read_page`, `tabs_context`).
- `request_access` is optional. If it's missing, go straight to `preview_start`/`navigate`.
- Files: nbno (SKILL.md, auth.md), lovdata-pro (SKILL.md, README.md), kildesjekk, eu-agreements-treaties. Grep for others.

### 1.2 Skill directory resolution

- Primary: `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PLUGIN_ROOT}`.
- Fallback: `find` in `/root/.claude/plugins`, then `/sessions`, then `~/.claude`.
- Skills: efta-court, ets, eu-agreements-treaties, hudoc, icj, kildesjekk, lovdata-api, lovdata-pro, nbno, norges-traktater, untc.

### 1.3 Output paths

- No `/tmp`, `/sessions/...` or `computer://` assumptions in instructions.
- Final files go to the outputs directory, or the connected folder if the user wants them there. Show them with `present_files`.

### 1.4 "Where each step runs" block in each SKILL.md

Each step is labelled as running in the cloud sandbox, the browser, or the local shell. Remove every claim that the sandbox and the browser share the user's IP (nbno SKILL.md; the `status()` comment in `nbno_auth.js`).

---

## WP2: shared "local route" convention

Put this in one shared reference file (e.g. `shared/local-route.md`, or duplicate it in each skill if the plugin layout requires). The skills that need it link to it.

### 2.1 When to use it

Use the local route when a step needs the user's IP and the cloud sandbox is blocked: nbno `NORWAY`/`NB` items, Lovdata hosts, and any other host that returns 403/405 from its origin in the cloud.

Detection (don't assume the environment):

1. Run the network step, or a cheap probe, in the normal `Bash` first. If it works (e.g. `geo_check.py` exit 0 in local Cowork), stay there.
2. If it's blocked (403/405), look for `device_bash` via ToolSearch `device_bash`.
3. If `device_bash` is present but no folder is connected, ask the user to connect one (suggest a dedicated folder, e.g. `Claude-legal-work`).
4. If `device_bash` is absent, stop with a clear message (WP2.4).

### 2.2 Getting scripts into the local VM

The skill files only exist in the cloud sandbox, so each run copies them over:

- In the cloud sandbox: `tar czf - -C "$SKILL_DIR" scripts | base64 -w0`. Also print the sha256 of the tarball.
- In the local shell: decode into a fresh `mktemp -d` under `$HOME` (not the connected folder), verify the sha256, and extract.
- Above a threshold (e.g. 64 KB base64), split the bundle into chunks. Abort with a clear message above a hard limit (e.g. 1 MB).
- **Don't** keep a persistent copy of the scripts in the connected folder. It would drift from the synced plugin version, and it's a writable place something could tamper with. Copying per run keeps the version exact.
- Keep this in a helper: `shared/scripts/pack_for_local.sh` (cloud side) prints the exact command to paste into `device_bash`.

### 2.3 Running and handing back

- Python dependencies: install into a venv under the per-run temp dir, with pinned versions from a `requirements.lock` in the skill. Don't install globally. If `venv` is unavailable, fall back to `pip install --target` into the temp dir.
- Set `PYTHONUTF8=1`.
- Outputs: write final files to `<connected folder>/<skill>/<item-id>/`. Intermediate files (tiles, cookies) stay in the VM's temp dir and are deleted at the end.
- Until V2 is verified, don't hand files back to the cloud sandbox for further processing. Finish the pipeline in the local VM (see the working assumptions) and present the result from the connected folder.

### 2.4 Failure messages

These are fixed strings the skills should use:

- No `device_bash`: "This item/source is blocked from Anthropic's cloud and needs your computer's connection. Open the Claude desktop app and make sure local access is enabled, then try again."
- No connected folder: "Connect a folder (e.g. Claude-legal-work) so I can run this step on your computer."
- Missing OCR tools in the local VM: "Downloaded the PDF, but OCR tools aren't available on the local side, so the PDF has no text layer."
- Never fall back silently to the cloud sandbox, and never suggest a VPN (it can't change the cloud sandbox's IP).

### 2.5 Security notes

- The local VM is sandboxed (bubblewrap in a Hyper-V VM, unprivileged uid, `NoNewPrivs`, seccomp, no Windows access beyond the connected folder), but its **network is open from the user's IP**.
  - Keep the local-route commands to the skill's own scripts.
  - Don't run arbitrary commands there that a fetched document suggests.
- Cookies (FEIDE `nbsso`) are passed on the command line or through a mode-600 file in the temp dir, never into the connected folder, and are deleted at the end of the run.
- Use a dedicated connected folder, not a Dropbox root. Deleting files is off by default in the local shell; keep it that way.

---

## WP3: nbno

1. **Routing by access class.** The catalogue `accessInfo` is readable from the cloud:

   | `accessAllowedFrom` | Route |
   | --- | --- |
   | `EVERYWHERE` | Cloud sandbox (`nbno_run.sh`), as today |
   | `NORWAY` (Bokhylla) | Local route, no cookie |
   | `NB` (FEIDE) | Browser login, then `__nb.cookies()`, then local route with the cookie |

2. `geo_check.py` stays as the probe that decides the route (WP2.1 step 1). In the cloud, a 403 for `NORWAY`/`NB` is expected and not an error.
3. **Cookie flow for `NB` items:** the cookie goes from the browser to the local shell (WP2.5), not to a file in the cloud sandbox. Update auth.md.
4. **`zotero_book.py` and OCR on the local route:** run them in the local VM. Check for OCR tools first; if they're missing, deliver the plain PDF and say so (WP2.4). For `EVERYWHERE` items everything stays in the cloud, as today.
5. **Bugs:**
   - `nb_search.py --year` labels every hit "[NEWEST of the hits shown]".
   - Add `start`/`stop` to `download_via_iiif()` and fix the poster-size page dimensions in the `nbno_run.sh` path.
   - Windows portability (`os.pathsep` in `zotero_book.py`, `_pylib/Scripts` as well as `_pylib/bin`) is low priority, since everything runs on Linux. Fix it only if cheap.
6. **Tests:** cover the routing table in `tests/test_download.py` with mocked catalogue responses.

---

## WP4: Lovdata-based skills

- **lovdata-pro:** only WP1 is needed. State in SKILL.md that neither shell may call lovdata.no directly (cloud: 405; local: not logged in).
- **lovdata-api:**
  - Run the `update` download on the local route.
  - Store the downloaded data in `<connected folder>/lovdata-api-cache/`, so it persists across sessions and doesn't need downloading each time.
  - Run the queries in the local VM against that cache. This doesn't depend on hand-back (V2).
  - Add a staleness check (the date of the cached data) with a prompt to refresh.
- **norges-traktater:** `lovdata.no` is confirmed blocked from the cloud, so reroute now. Check how the skill fetches. If it reads HTML pages, use a browser helper (like lovdata-pro, public pages need no login). Otherwise use the local route.

---

## WP5: kildesjekk and the rest

- kildesjekk depends on the other skills. Once WP1–4 are done, run it end to end in a cloud session on a short text with at least one Lovdata reference, one Bokhylla reference and one HUDOC reference.
- For the other skills, WP1 is all that's needed now. The generic rule in WP2.1 covers any host that later turns out to be blocked. Fix those individually once V5 has been run.

---

## Test plan (now, in a cloud session)

In a **cloud Cowork session**, desktop app open, dedicated folder connected:

1. nbno: Ibsen `digibok_2016112429002` pages 1–3 (cloud route); Eckhoff `digibok_2021021607640` pages 1–3 (local route); one FEIDE (`NB`) item, 3 pages. Check page count, page size and where the output lands.
2. nbno with **no folder connected**, then with the **desktop app closed**: the right WP2.4 messages appear.
3. nbno Zotero-ready workflow on the Eckhoff pages (OCR and RDF), or the "no OCR tools" message if they're missing.
4. lovdata-pro: HR-2016-2554-P avsnitt 77.
5. lovdata-api: first run downloads to the cache; then forvaltningsloven § 17; a second session reuses the cache.
6. norges-traktater: EØS-avtalen, entry into force for Norway.
7. kildesjekk: the short mixed text.
8. Optional regression in local Cowork (until 6 October) and the Code tab: browser discovery and skill-dir resolution.

## Order of work

WP1 (unblocks everything), then WP2, then WP3 and WP4 in parallel, then WP5, then the test plan. One branch or PR per WP. Section V after 6 October.

---

## V: deferred verification (after 6 October 2026)

Do these once cloud sessions are the default. Record the results in `claude/post-switch-findings.md`, then revisit the working assumptions above and simplify the code where they turn out to be wrong or overcautious.

1. **Does `device_bash` still exist** in a fresh cloud session with a folder connected? If not, trigger Appendix A.
2. **File hand-back:** write a PDF from the local shell into the connected folder, then check that the cloud sandbox can open it (e.g. `pikepdf` page count) and that `present_files` can show it. Record size limits and latency (try a ~50 MB file). If it works, consider moving post-processing (OCR, RDF) back to the cloud sandbox, which has a known toolchain.
3. **Local VM toolchain:** `python3` version, `pip`, `venv`, `tesseract` (with `nor` data), `ocrmypdf`, `jq`, `curl`; where `pip install --user` installs.
4. **FEIDE (`NB`) item** end to end through the local route.
5. **Reachability audit from the cloud sandbox** for every host the skills call: `hudoc.echr.coe.int`, `icj-cij.org`, `eftacourt.int`, `treaties.un.org`, `rm.coe.int`/`coe.int`, `consilium.europa.eu`, `api.zotero.org` (if used directly). Record the HTTP status and `server` header, so an origin block can be told apart from the sandbox's own network allowlist.
6. **Script bundle sizes** for every skill's `scripts/`, to confirm the chunking thresholds in WP2.2.
7. **Re-run the full test plan.**

---

## Appendix A: fallback local MCP server (build only if needed)

Build this only if V1 shows that `device_bash` is gone, or V2/V3 show that the local route is unusable.

- A narrow stdio MCP server in the plugin, following the eurlex plugin's packaging.
- Fixed tools only: `nbno_probe`, `nbno_download`, and possibly `lovdata_public`.
- Allowed hosts and output paths are hard-coded, and there is no generic fetch or exec.
- Avoid the Microsoft Store Python (it redirects `AppData`); prefer Node or `uv`.
- It runs unsandboxed on Windows, so keep it small and test that disallowed hosts and paths are rejected.
