#!/usr/bin/env python3
"""Offline tests for finding the system tessdata dir (no tesseract needed):
tesseract 4.x prints no directory in `--list-langs`, and the Cowork local VM
(4.1.1) broke OCR that way on 2026-09-30. Covers zotero_book.py and its
mirror in ocr_chunked.py.
Run: python tests/test_tessdata.py
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
os.environ["NBNO_PYLIB"] = str(Path(tempfile.mkdtemp()) / "_pylib")
import ocr_chunked  # noqa: E402
import zotero_book  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


system = Path(tempfile.mkdtemp()) / "tesseract-ocr" / "4.00" / "tessdata"
system.mkdir(parents=True)
(system / "eng.traineddata").write_bytes(b"x")
(system / "osd.traineddata").write_bytes(b"x")

V4 = "List of available languages (2):\neng\nosd\n"
V5 = f'List of available languages in "{system}/" (2):\neng\nosd\n'

for mod in (zotero_book, ocr_chunked):
    print(mod.__name__)
    mod._TESSDATA_GLOBS = (str(system.parent.parent / "*" / "tessdata"),)
    own = mod._tessdata_dir()
    for label, listing, want in [
        ("4.x: no dir printed -> standard location", V4, system),
        ("5.x: dir printed -> used as is", V5, system),
        ("own fetch dir printed -> system dir instead",
         f'List of available languages in "{own}/" (1):\nnor\n', system),
    ]:
        mod.subprocess.run = lambda *a, _o=listing, **k: SimpleNamespace(stdout=_o, stderr="")
        langs, source = mod._list_langs()
        check(label, (sorted(langs)[:1], source and source.resolve()),
              (sorted(langs)[:1], want.resolve()))
    mod._TESSDATA_GLOBS = (str(Path(tempfile.mkdtemp()) / "nothing"),)
    mod.subprocess.run = lambda *a, **k: SimpleNamespace(stdout=V4, stderr="")
    check("nothing found -> None", mod._list_langs()[1], None)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
