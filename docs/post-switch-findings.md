# Post-switch findings (spec §V)

Cloud Cowork, 2026-10-07 (run 9). Device: Windows 11, desktop app 2.26454.0.
Synced plugins: nbno 1.3.12, norges-traktater 1.2.5.

## Session facts

- **Cowork is cloud-only** from the switch on. The cloud sandbox's `hostname` is `vm`, and it has `/mnt/user-data/{outputs,uploads,working}`. The skills no longer tell cloud and local sessions apart; every local-Cowork branch was removed.
- **The local-shell tools are deferred.** `mcp__remote-devices__device_bash`, `device_request_folder_access` and `device_stage_files` were not in the tool list; on 2026-09-30, `device_bash` had been loaded up front. They load only with ToolSearch `select:…`, because a keyword search can miss them. So "device_bash is in your tool list" is not a usable test.

## Results

| § | Item | Result |
|---|---|---|
| V1 | `device_bash` exists | **Yes**, once a folder is connected. User `rcw-<session id>`, Ubuntu (kernel 6.8), and the connected folder at `$HOME/mnt/<folder>/` (a hidefs mount). Appendix A is not needed. |
| V2 | File hand-back | **Yes, via `device_stage_files`.** It copies a connected-folder file to `/mnt/user-data/uploads/<folder>/<path>`, read-only, at ≤ 400 MB per file and ≤ 500 MB per call; a 50 MB PDF arrived and pypdf read it at once. Without staging, the cloud sees nothing. `SendUserFile` caps at **30 MiB**, and `device_commit_files` at 30 MB per file. `present_files` does not exist in cloud sessions. |
| V3 | Local VM toolchain | Python 3.10.12, pip 25.3, venv, tesseract 4.1.1 (`eng`, `osd`; `nor` is fetched by nbno), jq 1.6, curl 7.81, pypdf, pikepdf, reportlab, Pillow, img2pdf, qpdf, gs, pdftoppm. `ocrmypdf` and PyMuPDF are missing; nbno pip-installs `ocrmypdf` into the run directory. 5.3 GB free on `/sessions`. |
| V4 | FEIDE (`NB`) item end to end | **Pass.** Ruud & Ulfstein, *Innføring i folkerett* (2018), canvases 10–12. The route was `norwegian-ip+loan`, then local, then `here`. Download, OCR, shrink and RDF took 62 s, and cleanup left nothing behind. |
| V5 | Reachability from the cloud sandbox | 200: hudoc, icj, eftacourt, treaties.un.org, api.zotero.org, nb.no, api.nb.no, publications SPARQL. 403 (Cloudflare): rm.coe.int, coe.int/conventions, consilium (`cf-mitigated: challenge`). 405 (Varnish IPS): lovdata.no, api.lovdata.no. 202 (AWS WAF challenge): eur-lex. **Every block comes from the origin:** the proxy answered `200 Connection Established` first, whereas an allowlist denial is `000` with `connect_rejected`. hudoc and icj answer 200 only on the front page; documents and PDFs got 403 in run 2. |
| V6 | Script bundle sizes (base64 of gzip) | nbno 74 KB (2 chunks in `--bundle`), icj 28 KB, untc 24 KB, lovdata-api 20 KB, all others < 20 KB. Everything is far under the 1 MB limit, so the thresholds stay as they are. |
| V7 | Full test plan | Not re-run as one session. WP1–5 were each tested in runs 1–8. |
| V8 | norges-traktater: Python or JS only | The cloud session went straight to the browser (Bash was not tried), in 5 tool calls costing about 13–14k tokens for the helper. **Decided: JS-only** (1.3.0). `traktater.py`, its test and the parity test were removed, and `test_browser.js` keeps the same 32 cases as plain fixtures. |

## Changes made from these findings

- Cloud-only: the cloud-vs-local branches are gone from every skill. lovdata-api goes straight to the local route, without a `Bash` attempt. nbno routes by `geo_check.py` alone, and local-route.md loads the local-shell tools with one ToolSearch `select:` call. Files go to the user with `SendUserFile`; `present_files` is gone.
- local-route.md §3 now states the hand-back facts (`device_stage_files` and the 30 MiB `SendUserFile` cap), and that skills never delete in the connected folder.
- nbno's delivery step mentions the 30 MiB cap.
- norges-traktater opens its own tab when another skill's tab is in front.
- The helper skills say that `VERSION` is the plugin version at the helper's last change, so it can be lower than the plugin's.

Not adopted: making the GitHub loader the default for `__nt`/`__nb`. The Cowork safety check blocks fetching a helper and running it with eval as "Code from External" (2026-09-30), which is why the stripped paste replaced the loader (CLAUDE.md).
