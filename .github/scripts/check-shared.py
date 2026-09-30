#!/usr/bin/env python3
"""Keep the copies of shared/ files inside plugins identical to the canonical
ones. Plugins are installed in isolation, so a skill cannot reference a file
outside its own folder; shared files are copied in instead.

  .github/scripts/check-shared.py          exit 1 if any copy differs or is missing
  .github/scripts/check-shared.py --fix    rewrite the copies from shared/

Run from the repo root. After --fix, bump the version of every plugin whose
copy changed (CLAUDE.md).
"""

import sys
from pathlib import Path

# canonical file -> (plugins that carry it, path inside plugins/<p>/skills/<p>/)
SHARED = {
    "shared/local-route/local-route.md": (["nbno", "lovdata-api"], "local-route.md"),
    "shared/local-route/pack_for_local.sh": (["nbno", "lovdata-api"], "scripts/pack_for_local.sh"),
    "shared/browser-loader/load.sh": (
        ["eu-agreements-treaties", "hudoc", "lovdata-pro", "nbno", "norges-traktater"],
        "scripts/browser/load.sh",
    ),
}


def main() -> int:
    fix = "--fix" in sys.argv[1:]
    bad = 0
    for src, (plugins, rel) in SHARED.items():
        want = Path(src).read_bytes()
        for p in plugins:
            dst = Path("plugins") / p / "skills" / p / rel
            if dst.exists() and dst.read_bytes() == want:
                print(f"[ok   ] {dst}")
                continue
            if fix:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(want)
                print(f"[fixed] {dst}  <- {src} (bump plugins/{p} version)")
            else:
                print(f"[DIFF ] {dst} differs from {src}; run {sys.argv[0]} --fix")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
