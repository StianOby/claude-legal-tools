#!/usr/bin/env python3
"""Offline tests for scripts/nb_download.py (no network): it is zotero_book.py
without OCR, shrink or RDF, and the caller's own flags still win.
Run: python tests/nbno/test_nb_download.py
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
import nb_download  # noqa: E402
import zotero_book  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


seen = {}


def fake_main(argv):
    seen["argv"] = argv
    return 0


zotero_book.main = fake_main

print("nb_download.main")
check("exit status passed through", nb_download.main(["--id", "digibok_1", "--out", "o"]), 0)
check("download-only mode", seen["argv"][:1], ["--download-only"])
check("caller's flags after it", seen["argv"][1:], ["--id", "digibok_1", "--out", "o"])
nb_download.main(["--id", "digibok_1", "--out", "o", "--shrink"])
check("--shrink comes last, so it wins", seen["argv"][-1], "--shrink")
out = io.StringIO()
with redirect_stdout(out):
    rc = nb_download.main(["--help"])
check("--help prints its own usage", (rc, "nb_download.py --id" in out.getvalue()), (0, True))

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
