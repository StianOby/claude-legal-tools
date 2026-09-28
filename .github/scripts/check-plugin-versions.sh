#!/usr/bin/env bash
# Fail if any plugin's files changed between $BASE and HEAD without a change to
# its plugin.json version. Usage: check-plugin-versions.sh <base-ref>
set -euo pipefail
base="$1"
fail=0
for plugin_dir in plugins/*/; do
  plugin=$(basename "$plugin_dir")
  manifest="plugins/$plugin/.claude-plugin/plugin.json"
  changed=$(git diff --name-only "$base" HEAD -- "plugins/$plugin" | grep -v -x "$manifest" || true)
  [ -z "$changed" ] && continue
  old=$(git show "$base:$manifest" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])' 2>/dev/null || echo "<new>")
  new=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$manifest")
  if [ "$old" = "$new" ]; then
    echo "::error file=$manifest::$plugin changed since $base but version is still $new — bump it (or enable the pre-commit hook: git config core.hooksPath .githooks)"
    fail=1
  else
    echo "$plugin: $old → $new"
  fi
  # A changed browser helper must carry the new version, or a tab holding the
  # old helper keeps it after the next paste (see .githooks/pre-commit).
  for js in $(printf '%s\n' "$changed" | grep -E '/scripts/browser/[^/]+\.js$' || true); do
    [ -f "$js" ] || continue
    hv=$(sed -n -E "s/.*const HELPER_VERSION = '([^']*)'.*/\1/p" "$js" | head -n1)
    [ -z "$hv" ] && continue
    if [ "$hv" != "$new" ]; then
      echo "::error file=$js::HELPER_VERSION is '$hv' but $plugin is $new — set it to $new (the pre-commit hook does this)"
      fail=1
    fi
  done
done
exit $fail
