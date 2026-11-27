#!/usr/bin/env python3
"""Offline tests for finding the system tessdata dir (no tesseract needed):
tesseract 4.x prints no directory in `--list-langs`, and the Cowork local VM
(4.1.1) broke OCR that way on 2026-09-30. Covers zotero_book.py and its
mirror in ocr_chunked.py.
Run: python tests/nbno/test_tessdata.py
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
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

print("fetch_tessdata: no github.com repo path, falls back in order")
import urllib.error  # noqa: E402
for mod in (zotero_book, ocr_chunked):
    tag = mod.__name__
    check(f"{tag}: no github.com/<repo> URL (blocked in the cloud sandbox)",
          any(u.startswith("https://github.com/") for u in mod.TESSDATA_URLS), False)
    tried = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"model"

    def fake_urlopen(req, timeout=60, _t=tried):
        _t.append(req.full_url)
        if len(_t) == 1:
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", None, None)
        return Resp()

    real = mod.urllib.request.urlopen
    mod.urllib.request.urlopen = fake_urlopen
    try:
        check(f"{tag}: first source 403 -> second serves it", mod.fetch_tessdata("nor"), b"model")
        check(f"{tag}: tried in order", tried,
              [u.format(code="nor") for u in mod.TESSDATA_URLS[:2]])
    finally:
        mod.urllib.request.urlopen = real

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
