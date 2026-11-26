#!/usr/bin/env python3
"""Offline tests for scripts/ocr_chunked.py's main loop (no network, no
ocrmypdf): the environment handed to each page carries the TESSDATA_PREFIX
that tesseract_preflight() sets, and a call where every page fails stops
after a few pages instead of failing the whole book until the time budget
runs out (both seen on 2026-11-26).
Run: python tests/nbno/test_ocr_chunked.py
"""

import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
import ocr_chunked as oc  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


PAGES = 30
os.environ.pop("TESSDATA_PREFIX", None)
work = Path(tempfile.mkdtemp())
pdf = work / "book.pdf"
pdf.write_bytes(b"%PDF-1.4 stub")
fetched = str(work / "_tessdata")


def preflight(langs):
    os.environ["TESSDATA_PREFIX"] = fetched   # as after a tessdata_fast fetch
    return langs


def split(pikepdf, pdf_path, pages_dir):
    pages_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, PAGES + 1):
        (pages_dir / f"page-{i:04d}.pdf").write_bytes(b"x")
    return PAGES


calls = []


def ocr_page(binary, src, dst, langs, env):
    calls.append(env.get("TESSDATA_PREFIX"))
    return dst, 1, "Please install the appropriate language data"


oc._ensure_pikepdf = lambda: object()
oc._ensure_ocrmypdf = lambda: "ocrmypdf"
oc._ensure_pylib_on_path = lambda: work
oc.tesseract_preflight = preflight
oc._split_pages = split
oc._purge_corrupt_cache = lambda pikepdf, d: 0
oc._ocr_page = ocr_page

print("ocr_chunked.main: every page fails")
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
    code = oc.main(["--pdf", str(pdf), "--jobs", "1", "--time-budget", "600"])
check("each page saw the fetched TESSDATA_PREFIX", set(calls), {fetched})
check("stopped after 4 failures, not all 30 pages", len(calls), 4)
check("exit 1 (re-running will not help)", code, 1)
check("says so", "no page could be OCRed" in err.getvalue(), True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
