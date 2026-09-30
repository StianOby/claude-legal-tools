#!/usr/bin/env bash
# load.sh — run in Bash (cloud sandbox or local Cowork). Prints ONE line of
# JavaScript to send through javascript_tool instead of pasting a whole
# browser helper (30–45 KB) into the tab.
#
# Shared file: the canonical copy is shared/browser-loader/ in the repo; every
# plugin with a browser helper carries an identical copy at
# scripts/browser/load.sh (CI checks it).
#
# Usage:  bash <skill_dir>/scripts/browser/load.sh <skill_dir>/scripts/browser/<helper>.js
#
# The printed line, run in the tab, fetches the helper from the public repo's
# main branch, checks its sha256 against the copy synced into this session,
# runs it and returns one word plus detail:
#   LOADED <global> <version>   helper installed
#   ALREADY <global> <version>  this exact file was already loaded by the loader
#                               (a pasted or trimmed copy with the same VERSION
#                               is replaced, not accepted)
#   MISMATCH <sha>              GitHub main differs from the synced copy
#   FETCH_FAILED <why>          the site blocked the request (CSP, network)
#   EVAL_FAILED <why>           the site blocked running it
# Anything but LOADED/ALREADY: paste the whole helper file as before.
set -euo pipefail

REPO_RAW="${CLT_RAW_BASE:-https://raw.githubusercontent.com/StianOby/claude-legal-tools/main}"

f="${1:?usage: load.sh <skill_dir>/scripts/browser/<helper>.js}"
[ -f "$f" ] || { echo "load.sh: no such file: $f" >&2; exit 2; }
skill_dir=$(cd "$(dirname "$f")/../.." && pwd)
skill=$(basename "$skill_dir")
skill=${skill%%~*}   # Cowork syncs updated plugins into <name>~gN folders
name=$(basename "$f")
url="$REPO_RAW/plugins/$skill/skills/$skill/scripts/browser/$name"
sha=$(sha256sum "$f" | cut -d' ' -f1)
global=$(grep -oE 'window\.__[a-z]+ = ' "$f" | head -1 | sed -E 's/^window\.(__[a-z]+) = $/\1/')
version=$(grep -oE "const HELPER_VERSION = '[^']+'" "$f" | head -1 | sed -E "s/.*'([^']+)'/\1/")
[ -n "$global" ] && [ -n "$version" ] || { echo "load.sh: $name has no window.__x global or HELPER_VERSION" >&2; exit 2; }

# No backslashes in the output: javascript_tool decodes escapes (CLAUDE.md).
cat <<EOF
await (async () => { const u = '$url', want = '$sha', g = '$global', v = '$version'; if (window[g] && window[g].VERSION === v && window[g].LOADER_SHA === want) return 'ALREADY ' + g + ' ' + v; let b; try { const r = await fetch(u, { cache: 'no-store', credentials: 'omit' }); if (!r.ok) return 'FETCH_FAILED HTTP ' + r.status; b = await r.arrayBuffer(); } catch (e) { return 'FETCH_FAILED ' + e.message; } const h = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', b)), (x) => x.toString(16).padStart(2, '0')).join(''); if (h !== want) return 'MISMATCH ' + h; try { delete window[g]; (0, eval)(new TextDecoder().decode(b)); } catch (e) { return 'EVAL_FAILED ' + e.message; } if (!window[g] || window[g].VERSION !== v) return 'EVAL_FAILED ' + g + ' not set'; window[g].LOADER_SHA = want; return 'LOADED ' + g + ' ' + v; })()
EOF
