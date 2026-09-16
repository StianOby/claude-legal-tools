#!/usr/bin/env python3
"""Keep the checked-in data snapshots (snapshots.json) from going stale.

  snapshots.py check            list snapshots, exit 1 if any is stale
  snapshots.py check --quiet    print only stale ones (used by the pre-commit hook)
  snapshots.py refresh NAME     run the snapshot's refresh command, show the
                                before/after record count, stamp today's date
  snapshots.py refresh --all    refresh every snapshot that has a command
  snapshots.py mark NAME        stamp today's date without refreshing (after a
                                manual refresh, e.g. one done in Cowork)

A snapshot is stale when `last_refreshed` is more than `max_age_days` ago.
Snapshots with `"refresh": null` need a manual procedure; `check` prints
`refresh_manual` for those.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(ROOT, "snapshots.json")
TODAY = dt.date.today()


def load():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def save(m):
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
        f.write("\n")


def age_days(s):
    return (TODAY - dt.date.fromisoformat(s["last_refreshed"])).days


def count(s):
    """Number of records in the snapshot file, or None if unreadable."""
    try:
        with open(os.path.join(ROOT, s["path"]), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    key = s.get("count_key")
    if key:
        data = data.get(key)
    return len(data) if isinstance(data, (list, dict)) else None


def find(m, name):
    for s in m["snapshots"]:
        if s["name"] == name:
            return s
    sys.exit(f"snapshots.py: no snapshot named {name!r} "
             f"(have: {', '.join(x['name'] for x in m['snapshots'])})")


def cmd_check(args):
    m = load()
    max_age = m["max_age_days"]
    stale = []
    for s in m["snapshots"]:
        age = age_days(s)
        is_stale = age > max_age
        if is_stale:
            stale.append(s)
        if args.quiet and not is_stale:
            continue
        n = count(s)
        n_txt = f", {n} records" if n is not None else ""
        status = "STALE" if is_stale else "ok"
        print(f"[{status:5}] {s['name']}: refreshed {s['last_refreshed']} "
              f"({age} d ago{n_txt})")
        if is_stale:
            if s.get("refresh"):
                print(f"        refresh: .github/scripts/snapshots.py refresh {s['name']}")
            else:
                print(f"        manual:  {s.get('refresh_manual', '(no procedure recorded)')}")
        if is_stale and os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning file=snapshots.json::{s['name']} last refreshed "
                  f"{s['last_refreshed']} ({age} days ago, max {max_age})")
    if stale:
        print(f"{len(stale)} stale snapshot(s) (max age {max_age} days); "
              "see CLAUDE.md → 'Cached data snapshots'.", file=sys.stderr)
        return 1
    return 0


def refresh_one(m, s):
    if not s.get("refresh"):
        sys.exit(f"{s['name']}: no automatic refresh — {s.get('refresh_manual', '')}\n"
                 f"When done, run: snapshots.py mark {s['name']}")
    before = count(s)
    print(f"== {s['name']}: {before} records before; running refresh …")
    subprocess.run(["bash", "-euo", "pipefail", "-c", s["refresh"]], cwd=ROOT, check=True)
    after = count(s)
    print(f"== {s['name']}: {before} → {after} records")
    if after is None or (before and after < 0.9 * before):
        sys.exit(f"{s['name']}: record count dropped from {before} to {after} — "
                 "the fetch probably failed partway. Not stamping; inspect "
                 f"`git diff {s['path']}` and `git checkout` it if wrong.")
    s["last_refreshed"] = TODAY.isoformat()
    save(m)
    print(f"== {s['name']}: stamped {s['last_refreshed']}")


def cmd_refresh(args):
    m = load()
    targets = ([s for s in m["snapshots"] if s.get("refresh")] if args.all
               else [find(m, args.name)])
    for s in targets:
        refresh_one(m, s)
    return 0


def cmd_mark(args):
    m = load()
    s = find(m, args.name)
    s["last_refreshed"] = TODAY.isoformat()
    save(m)
    print(f"{s['name']}: stamped {s['last_refreshed']} ({count(s)} records)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("check", help="report stale snapshots (exit 1 if any)")
    p.add_argument("--quiet", action="store_true", help="print only stale ones")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("refresh", help="run a snapshot's refresh command and stamp it")
    p.add_argument("name", nargs="?")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_refresh)
    p = sub.add_parser("mark", help="stamp today's date after a manual refresh")
    p.add_argument("name")
    p.set_defaults(fn=cmd_mark)
    args = ap.parse_args()
    if not args.cmd:
        args.cmd, args.quiet, args.fn = "check", False, cmd_check
    if args.cmd == "refresh" and not args.all and not args.name:
        ap.error("refresh needs NAME or --all")
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
