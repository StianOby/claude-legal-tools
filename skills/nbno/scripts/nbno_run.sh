#!/usr/bin/env bash
#
# nbno_run.sh — wrapper around the `nbno` CLI for the nbno skill.
#
# Responsibilities:
#   1. Make sure `nbno` is installed in the sandbox.
#   2. Normalise the user-provided identifier (URN, items URL, raw ID).
#   3. Run the download with --pdf.
#   4. Move the resulting PDF into the requested output directory and remove
#      the per-page image folder (user preference: PDF only).
#
# Usage:
#   nbno_run.sh --id <ID> --out <dir> [--cookie <file>|auto]
#               [--start N] [--stop N] [--resize N] [--title] [--cover]
#               [--keep-images]
#
# `--cookie auto` resolves to ~/.nbno/cookie.txt, a durable cookie file the
# user creates by copying nbsso out of their browser's DevTools (see auth.md).
#
# Cookie-file format (two lines; the second is the one that matters):
#   authorization=<token>      # optional — may be empty or omitted entirely
#   cookie=nbsso=<v>; _nblb=<v>
# api.nb.no authenticates by cookie, so captures from the built-in browser
# carry no bearer token. An empty `authorization=` line is accepted: it is
# stripped before the file reaches the nbno CLI, which would otherwise send a
# literal empty Authorization header on every request.
#
# Exit codes:
#   0 success, PDF placed in <out>
#   1 invalid arguments
#   2 unable to install or run nbno
#   3 nbno ran but produced no PDF (likely auth/geo issue)
#   4 cookie file missing, unreadable, or without a usable cookie= line

set -uo pipefail

ID=""
OUT=""
COOKIE=""
START=""
STOP=""
RESIZE=""
TITLE=0
COVER=0
KEEP_IMAGES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id)        ID="$2"; shift 2 ;;
    --out)       OUT="$2"; shift 2 ;;
    --cookie)    COOKIE="$2"; shift 2 ;;
    --start)     START="$2"; shift 2 ;;
    --stop)      STOP="$2"; shift 2 ;;
    --resize)    RESIZE="$2"; shift 2 ;;
    --title)     TITLE=1; shift ;;
    --cover)     COVER=1; shift ;;
    --keep-images) KEEP_IMAGES=1; shift ;;
    -h|--help)   sed -n '2,33p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ID" || -z "$OUT" ]]; then
  echo "ERROR: --id and --out are required." >&2
  exit 1
fi

# --- 0. Resolve --cookie auto -----------------------------------------------
DEFAULT_COOKIE="$HOME/.nbno/cookie.txt"
if [[ "$COOKIE" == "auto" ]]; then
  if [[ -f "$DEFAULT_COOKIE" ]]; then
    COOKIE="$DEFAULT_COOKIE"
    echo "Using cookie file: $COOKIE"
  else
    echo "ERROR: --cookie auto specified but no file at $DEFAULT_COOKIE." >&2
    echo "       Create it on your own machine: log in to nb.no, open" >&2
    echo "       DevTools (F12) -> Application -> Cookies -> www.nb.no, and" >&2
    echo "       copy the nbsso value into two lines:" >&2
    echo "         authorization=" >&2
    echo "         cookie=nbsso=<value>; _nblb=<value>" >&2
    echo "       Then make sure the file is reachable from this sandbox" >&2
    echo "       (mount the ~/.nbno folder or upload cookie.txt)." >&2
    exit 4
  fi
elif [[ -n "$COOKIE" && ! -f "$COOKIE" ]]; then
  echo "ERROR: --cookie path '$COOKIE' does not exist." >&2
  exit 4
fi

# --- 0b. Validate and sanitise the cookie file ------------------------------
# The nbno CLI copies every `authorization=`/`cookie=` line straight into its
# request headers. A capture from the built-in browser has no bearer token, so
# its `authorization=` line is empty — which would make the CLI send a literal
# empty Authorization header on every request. Strip it instead.
SANITISED_COOKIE=""
cleanup_cookie() { [[ -n "$SANITISED_COOKIE" ]] && rm -f "$SANITISED_COOKIE"; }
trap cleanup_cookie EXIT

if [[ -n "$COOKIE" ]]; then
  if [[ ! -r "$COOKIE" ]]; then
    echo "ERROR: cookie file '$COOKIE' is not readable." >&2
    exit 4
  fi
  # Step 3 cds into a scratch WORKDIR before invoking nbno, so a relative
  # --cookie path would no longer resolve. Absolutise it here.
  COOKIE="$(cd "$(dirname "$COOKIE")" && pwd)/$(basename "$COOKIE")"
  # Tolerates leading whitespace and CRLF line endings (Windows captures).
  COOKIE_VAL="$(sed -n 's/\r$//; s/^[[:space:]]*cookie[[:space:]]*=[[:space:]]*//p' "$COOKIE" | head -n1)"
  AUTH_VAL="$(sed -n 's/\r$//; s/^[[:space:]]*authorization[[:space:]]*=[[:space:]]*//p' "$COOKIE" | head -n1)"

  if [[ -z "$COOKIE_VAL" ]]; then
    echo "ERROR: cookie file '$COOKIE' has no non-empty 'cookie=' line." >&2
    echo "       Expected format (authorization may be empty or absent):" >&2
    echo "         authorization=" >&2
    echo "         cookie=nbsso=<value>; _nblb=<value>" >&2
    exit 4
  fi

  if [[ "$COOKIE_VAL" != *nbsso=* ]]; then
    echo "Note: cookie file has no nbsso= pair. That is fine for public-domain" >&2
    echo "      and Bokhylla items (Bokhylla only needs a Norwegian IP), but" >&2
    echo "      FEIDE-licensed items will 403 on every page without it." >&2
  fi

  if [[ -z "$AUTH_VAL" ]]; then
    echo "Cookie file carries no bearer token — expected; api.nb.no authenticates by cookie."
    SANITISED_COOKIE="$(mktemp)"
    printf 'cookie=%s\n' "$COOKIE_VAL" > "$SANITISED_COOKIE"
    COOKIE="$SANITISED_COOKIE"
  fi
fi

# --- 1. Normalise the ID -----------------------------------------------------
ID="${ID#URN:NBN:no-nb_}"
ID="${ID#urn:nbn:no-nb_}"
ID="${ID#urn:nbn:no-nb:}"

if [[ "$ID" =~ ^https?:// ]]; then
  echo "ERROR: A nb.no URL was passed. The /items/<hash> form does not" >&2
  echo "       contain the canonical ID. Ask the user to click 'Referere'" >&2
  echo "       on nb.no and paste the URN (URN:NBN:no-nb_digibok_...)." >&2
  exit 1
fi

if ! [[ "$ID" =~ ^(digibok|digavis|digifoto|digitidsskrift|digikart|digimanus|digiprogramrapport|pliktmonografi|pliktperiodika)_[0-9A-Za-z_]+$ ]]; then
  echo "ERROR: ID '$ID' does not look like a canonical nb.no media ID." >&2
  echo "       Expected something like 'digibok_2008051600041'." >&2
  exit 1
fi

# --- 2. Ensure nbno is installed --------------------------------------------
# Persistent install target. In Cowork ~/.local/ is wiped between bash calls,
# but a directory under --out (or anywhere passed via NBNO_PYLIB) survives.
# Callers can override by setting NBNO_PYLIB explicitly.
if [[ -n "${NBNO_PYLIB:-}" ]]; then
  PYLIB="$NBNO_PYLIB"
else
  PYLIB="$OUT/_pylib"
fi
mkdir -p "$PYLIB/bin"
export PATH="$PYLIB/bin:$PATH"
export PYTHONPATH="$PYLIB${PYTHONPATH:+:$PYTHONPATH}"

NBNO_BIN=""
if [[ -x "$PYLIB/bin/nbno" ]]; then
  NBNO_BIN="$PYLIB/bin/nbno"
elif command -v nbno >/dev/null 2>&1; then
  NBNO_BIN="$(command -v nbno)"
elif [[ -x "$HOME/.local/bin/nbno" ]]; then
  NBNO_BIN="$HOME/.local/bin/nbno"
fi

if [[ -z "$NBNO_BIN" ]]; then
  echo "Installing nbno (one-time, persistent at $PYLIB)..."
  if ! pip install --break-system-packages --target "$PYLIB" --upgrade --quiet nbno >/dev/null 2>&1; then
    echo "ERROR: pip install nbno failed." >&2
    exit 2
  fi
  if [[ -x "$PYLIB/bin/nbno" ]]; then
    NBNO_BIN="$PYLIB/bin/nbno"
  elif command -v nbno >/dev/null 2>&1; then
    NBNO_BIN="$(command -v nbno)"
  fi
fi

if [[ -z "$NBNO_BIN" ]]; then
  echo "ERROR: nbno installed but binary not found on PATH." >&2
  exit 2
fi

# --- 3. Run nbno in a working dir, with --pdf -------------------------------
mkdir -p "$OUT"
WORKDIR="$(mktemp -d)"
cd "$WORKDIR" || { echo "ERROR: could not cd to $WORKDIR" >&2; exit 2; }

ARGS=(--id "$ID" --pdf)
if [[ -n "$COOKIE" ]]; then ARGS+=(--cookie "$COOKIE"); fi
if [[ -n "$START"  ]]; then ARGS+=(--start  "$START");  fi
if [[ -n "$STOP"   ]]; then ARGS+=(--stop   "$STOP");   fi
if [[ -n "$RESIZE" ]]; then ARGS+=(--resize "$RESIZE"); fi
if [[ "$TITLE" -eq 1 ]]; then ARGS+=(--title); fi
if [[ "$COVER" -eq 1 ]]; then ARGS+=(--cover); fi

echo "Running: nbno ${ARGS[*]}"
"$NBNO_BIN" "${ARGS[@]}"
NBNO_STATUS=$?
if [[ $NBNO_STATUS -ne 0 ]]; then
  echo "ERROR: nbno exited with status $NBNO_STATUS" >&2
  exit 2
fi

# --- 4. Locate the PDF and move it into --out ------------------------------
shopt -s nullglob globstar
PDFS=( "$WORKDIR"/**/*.pdf "$WORKDIR"/*.pdf )
if [[ ${#PDFS[@]} -eq 0 ]]; then
  echo "ERROR: nbno produced no PDF. Check auth/geo restrictions." >&2
  exit 3
fi

for pdf in "${PDFS[@]}"; do
  base="$(basename "$pdf")"
  mv "$pdf" "$OUT/$base"
  echo "PDF: $OUT/$base"
done

# --- 5. Clean up image folders unless --keep-images ------------------------
if [[ "$KEEP_IMAGES" -ne 1 ]]; then
  find "$WORKDIR" -mindepth 1 -maxdepth 2 -type d -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$WORKDIR"
fi

echo "Done."
