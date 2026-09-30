#!/usr/bin/env bash
# pack_for_local.sh — run in the CLOUD sandbox. Prints the command to paste
# into the local shell (device_bash) so it gets an exact copy of this skill's
# scripts. See local-route.md.
#
# Shared file: the canonical copy is shared/local-route/ in the repo; every
# plugin that uses the local route carries an identical copy (CI checks it).
#
# Usage:
#   bash pack_for_local.sh <skill_dir>            # GitHub + sha256 check (default)
#   bash pack_for_local.sh --bundle <skill_dir>   # fallback: base64 copy
#
# Default mode prints ONE command. The local shell downloads the scripts from
# the public repo and checks each file against the sha256 of the copy synced
# into this sandbox, so the version is exact; a mismatch exits 3 and you run
# --bundle instead. --bundle prints one or more commands (chunked above
# 64,000 characters; refuses above 1,000,000); paste them in order.
#
# Every printed command uses one literal directory under $HOME/.clt/, created
# here with a random suffix; shell state does not carry across device_bash
# calls, so later commands must use that literal path too. The last line the
# local shell prints is "READY <dir>".
set -euo pipefail

REPO_RAW="${CLT_RAW_BASE:-https://raw.githubusercontent.com/StianOby/claude-legal-tools/main}"
CHUNK=64000
LIMIT=1000000

mode=github
if [ "${1:-}" = "--bundle" ]; then mode=bundle; shift; fi
dir="${1:?usage: pack_for_local.sh [--bundle] <skill_dir>}"
dir="${dir%/}"
[ -f "$dir/SKILL.md" ] || { echo "pack_for_local: no SKILL.md in $dir" >&2; exit 2; }
skill=$(basename "$dir")
rand=$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')
run="\$HOME/.clt/$skill-$rand"

# Everything under scripts/ except the browser helpers (they run in the
# browser pane, never in a shell) and caches.
files=$(cd "$dir" && find scripts -type f ! -path 'scripts/browser/*' \
          ! -path '*/__pycache__/*' ! -name '*.pyc' | LC_ALL=C sort)
[ -n "$files" ] || { echo "pack_for_local: nothing under $dir/scripts" >&2; exit 2; }

if [ "$mode" = github ]; then
  manifest=$(cd "$dir" && sha256sum $files)
  cat <<EOF
R="$run"; mkdir -p "\$R" && chmod 700 "\$R" && python3 - "\$R" <<'PY'
import hashlib, os, sys, urllib.request
root = sys.argv[1]
base = "$REPO_RAW/plugins/$skill/skills/$skill/"
manifest = """$manifest"""
bad = []
for line in manifest.strip().splitlines():
    want, name = line.split(None, 1)
    name = name.lstrip("*")
    try:
        data = urllib.request.urlopen(base + name, timeout=30).read()
    except Exception as e:
        bad.append(f"{name} ({e})"); continue
    if hashlib.sha256(data).hexdigest() != want:
        bad.append(name); continue
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
if bad:
    print("MISMATCH (use pack_for_local.sh --bundle):", *bad, sep="\n  ")
    sys.exit(3)
open(os.path.join(root, ".ready"), "w").write("ok\n")
print("READY", root)
PY
EOF
  exit 0
fi

# --bundle
tgz=$(mktemp)
trap 'rm -f "$tgz"' EXIT
(cd "$dir" && tar czf - $files) > "$tgz"
sum=$(sha256sum "$tgz" | cut -d' ' -f1)
b64=$(base64 -w0 < "$tgz")
n=${#b64}
if [ "$n" -gt "$LIMIT" ]; then
  echo "pack_for_local: bundle is $n characters (limit $LIMIT); too big to paste." >&2
  exit 4
fi
parts=$(( (n + CHUNK - 1) / CHUNK ))
echo "# $parts command(s); paste each into device_bash in order."
for ((i = 0; i < parts; i++)); do
  chunk=${b64:i*CHUNK:CHUNK}
  pre=""
  [ "$i" -eq 0 ] && pre="R=\"$run\"; mkdir -p \"\$R\" && chmod 700 \"\$R\" && : > \"\$R/b.b64\" && "
  [ "$i" -gt 0 ] && pre="R=\"$run\"; "
  post=""
  [ "$i" -eq $((parts - 1)) ] && post=" && base64 -d \"\$R/b.b64\" > \"\$R/b.tgz\" && echo \"$sum  \$R/b.tgz\" | sha256sum -c --quiet && tar xzf \"\$R/b.tgz\" -C \"\$R\" && rm \"\$R/b.b64\" \"\$R/b.tgz\" && echo ok > \"\$R/.ready\" && echo \"READY \$R\""
  echo "# --- command $((i + 1))/$parts ---"
  echo "${pre}printf %s '$chunk' >> \"\$R/b.b64\"${post}"
done
