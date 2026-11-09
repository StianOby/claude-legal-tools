#!/usr/bin/env bash
# Print the path of a Python 3.13 to run the skill's scripts with on the local
# route (canonical copy: shared/local-route/; check-shared.py syncs it): the
# version the cloud sandbox has (Python 3.13.18, 2026-11-09) and the skills'
# requirements.txt is compiled for. The Cowork local VM is an unprivileged
# Ubuntu 22.04 with Python 3.10, which recent releases no longer support
# (Pillow's security fixes since 13.0.0 need 3.11+, current ocrmypdf too).
#
#     PY=$(bash <dir>/scripts/local_python.sh <dir>)   # <dir>: the run directory
#
# Uses python3.13 (or python3, if it is 3.13+) when there is one. Otherwise
# pip-installs uv (the version pinned in the skill's requirements.txt, if it
# has one) and lets uv fetch a standalone CPython 3.13 (python-build-standalone,
# checked against the checksums built into uv; ~33 MB, ~3 s on 2026-11-09).
# Everything goes under
# <dir>, so `rm -rf <dir>` removes it; nothing is installed system-wide and
# no root is needed. Progress goes to stderr, the path alone to stdout.
# Exit 1 when no Python 3.13 can be had: the caller runs with python3 then.
set -euo pipefail

WANT=3.13
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${1:-$(dirname "$HERE")}"

for cand in "python$WANT" python3; do
  if command -v "$cand" >/dev/null 2>&1 \
     && "$cand" -c "import sys; sys.exit(sys.version_info[:2] < (3, 13))" 2>/dev/null; then
    command -v "$cand"
    exit 0
  fi
done

UVT="$DIR/uv"
export UV_PYTHON_INSTALL_DIR="$DIR/python" UV_PYTHON_BIN_DIR="$DIR/python/bin" UV_CACHE_DIR="$DIR/uv-cache"
if [[ ! -x "$UVT/bin/uv" ]]; then
  echo "[python] installing uv into $UVT (one-time)" >&2
  PIP=(python3 -m pip install --quiet --no-cache-dir --target "$UVT")
  if ! { [[ -f "$HERE/requirements.txt" ]] && "${PIP[@]}" -c "$HERE/requirements.txt" uv >/dev/null 2>&1; }; then
    "${PIP[@]}" uv >/dev/null 2>&1 || { echo "[python] could not install uv" >&2; exit 1; }
    [[ -f "$HERE/requirements.txt" ]] && echo "[python] WARNING: the pinned uv could not be installed; used the newest" >&2
  fi
fi
if ! "$UVT/bin/uv" python find "$WANT" >/dev/null 2>&1; then
  echo "[python] fetching a standalone Python $WANT with uv (one-time, ~33 MB)" >&2
  "$UVT/bin/uv" python install --quiet "$WANT" >&2 || { echo "[python] uv could not install Python $WANT" >&2; exit 1; }
fi
"$UVT/bin/uv" python find "$WANT"
