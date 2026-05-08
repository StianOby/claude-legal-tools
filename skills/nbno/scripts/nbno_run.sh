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
# `--cookie auto` resolves to ~/.nbno/cookie.txt (populated by the companion
# capture_cookie.py script that drives a Playwright login flow against
# nb.no).
#
# Exit codes:
#   0 success, PDF placed in <out>
#   1 invalid arguments
#   2 unable to install or run nbno
#   3 nbno ran but produced no PDF (likely auth/geo issue)
#   4 cookie file missing or invalid path

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
    -h|--help)   sed -n '2,28p' "$0"; exit 0 ;;
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
    echo "       Run capture_cookie.py on your machine to populate it:" >&2
    echo "         pip install playwright && playwright install chromium" >&2
    echo "         python scripts/capture_cookie.py" >&2
    echo "       Then make sure the file is reachable from this sandbox" >&2
    echo "       (mount the ~/.nbno folder or upload cookie.txt)." >&2
    exit 4
  fi
elif [[ -n "$COOKIE" && ! -f "$COOKIE" ]]; then
  echo "ERROR: --cookie path '$COOKIE' does not exist." >&2
  exit 4
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

if ! [[ "$ID" =~ ^(digibok|digavis|digifoto|digitidsskrift|digikart|digimanus|digiprogramrapport|pliktmonografi|pliktperiodika)_[0-9A-Za-z]+$ ]]; then
  echo "ERROR: ID '$ID' does not look like a canonical nb.no media ID." >&2
  echo "       Expected something like 'digibok_2008051600041'." >&2
  exit 1
fi

# --- 2. Ensure nbno is installed --------------------------------------------
NBNO_BIN=""
if command -v nbno >/dev/null 2>&1; then
  NBNO_BIN="$(command -v nbno)"
elif [[ -x "$HOME/.local/bin/nbno" ]]; then
  NBNO_BIN="$HOME/.local/bin/nbno"
fi

if [[ -z "$NBNO_BIN" ]]; then
  echo "Installing nbno (one-time)..."
  if ! pip install --break-system-packages --quiet nbno >/dev/null 2>&1; then
    echo "ERROR: pip install nbno failed." >&2
    exit 2
  fi
  if command -v nbno >/dev/null 2>&1; then
    NBNO_BIN="$(command -v nbno)"
  elif [[ -x "$HOME/.local/bin/nbno" ]]; then
    NBNO_BIN="$HOME/.local/bin/nbno"
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
