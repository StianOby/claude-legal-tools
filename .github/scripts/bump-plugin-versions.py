#!/usr/bin/env python3
"""Bump plugin versions, and every copy of the version in the plugin's code.

    bump-plugin-versions.py --base origin/main            # every plugin changed since
                                                           # the base whose version is
                                                           # still the base's (patch)
    bump-plugin-versions.py nbno kildesjekk --part minor  # named plugins

A plugin's version lives in plugins/<name>/.claude-plugin/plugin.json and is
copied into its scripts, where the tests compare the two:
  - `VERSION = "<version>"` (Python, shell),
  - `<name>-skill/<version>` (User-Agent strings),
  - `const HELPER_VERSION = '<version>'` in a browser helper, only when that
    helper itself changed since the base (CLAUDE.md: a helper's version
    changes only with the helper).
Comments that mention old versions are left alone.

Used by .github/workflows/dependabot-bump.yml on Dependabot's PRs, which
change a lock file without touching plugin.json; idempotent, so a re-run
on a PR already bumped changes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def version_at(ref: str, name: str):
    try:
        return json.loads(git("show", f"{ref}:plugins/{name}/.claude-plugin/plugin.json"))["version"]
    except subprocess.CalledProcessError:
        return None


def bumped(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def changed_files(base: str, name: str) -> list:
    out = git("diff", "--name-only", base, "HEAD", "--", f"plugins/{name}")
    return [f for f in out.splitlines() if f != f"plugins/{name}/.claude-plugin/plugin.json"]


def bump(name: str, part: str, base) -> str:
    manifest = ROOT / "plugins" / name / ".claude-plugin" / "plugin.json"
    text = manifest.read_text(encoding="utf-8")
    old = json.loads(text)["version"]
    new = bumped(old, part)
    manifest.write_text(text.replace(f'"version": "{old}"', f'"version": "{new}"', 1), encoding="utf-8")
    patterns = [
        (re.compile(r'(\bVERSION = ")' + re.escape(old) + '"'), r"\g<1>" + new + '"'),
        (re.compile(r"(\b" + re.escape(name) + r"-skill/)" + re.escape(old) + r"\b"), r"\g<1>" + new),
    ]
    changed = set(changed_files(base, name)) if base else set()
    touched = []
    for path in sorted((ROOT / "plugins" / name / "skills").rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".sh", ".js") or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        out = src
        if "/scripts/browser/" in rel:
            if rel in changed:
                out = out.replace(f"const HELPER_VERSION = '{old}'", f"const HELPER_VERSION = '{new}'")
        else:
            for pat, repl in patterns:
                out = pat.sub(repl, out)
        if out != src:
            path.write_text(out, encoding="utf-8")
            touched.append(rel)
    print(f"{name}: {old} -> {new}" + (f" ({', '.join(touched)})" if touched else ""))
    return new


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plugins", nargs="*", help="plugins to bump (default: those changed since --base)")
    ap.add_argument("--base", help="git ref to compare with, e.g. origin/main")
    ap.add_argument("--part", choices=("patch", "minor", "major"), default="patch")
    args = ap.parse_args(argv)
    if not args.plugins and not args.base:
        ap.error("name the plugins, or give --base")
    names = args.plugins or [
        p.name for p in sorted((ROOT / "plugins").iterdir())
        if (p / ".claude-plugin" / "plugin.json").exists() and changed_files(args.base, p.name)
        and version_at(args.base, p.name) == json.loads(
            (p / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    ]
    for name in names:
        bump(name, args.part, args.base)
    if not names:
        print("nothing to bump")
    return 0


if __name__ == "__main__":
    sys.exit(main())
