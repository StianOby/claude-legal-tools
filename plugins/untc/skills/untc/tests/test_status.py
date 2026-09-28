#!/usr/bin/env python3
"""Offline tests for the MTDSG status cache in scripts/untc.py: the status
date comes from the PDF itself, fetched_utc is the real download time, and
an old cached status PDF is downloaded again.
Run: python tests/test_status.py
"""

import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr
from pathlib import Path

os.environ["UNTC_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import untc  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


HEADER = (b"4. INTERNATIONAL COVENANT ON CIVIL AND POLITICAL RIGHTS\nNew York, 16 December 1966\n"
          b"STATUS: Signatories: 74. Parties: 175.\n")


def fake_pdf(moddate: bytes) -> bytes:
    return b"%PDF-1.4\n1 0 obj << /Producer (Aspose) /ModDate (D:" + moddate + b"-04'00') >>\n%%EOF"


tmp = Path(tempfile.mkdtemp())
p = tmp / "a.pdf"
p.write_bytes(fake_pdf(b"20260921190007"))
check("status date from /ModDate", untc.pdf_document_date(p), "2026-09-21")
p.write_bytes(b"%PDF-1.4 << /CreationDate (D:20250102) >>")
check("falls back to /CreationDate", untc.pdf_document_date(p), "2025-01-02")
p.write_bytes(b"%PDF-1.4 nothing")
check("no date: None", untc.pdf_document_date(p), None)

downloads = []
served = {"pdf": fake_pdf(b"20260921190007")}


def fake_download(url, dest, *, force=False, timeout=180):
    if untc._has_content(dest) and not force:
        return dest
    downloads.append(url)
    dest.write_bytes(served["pdf"])
    return dest


untc.download_pdf = fake_download
untc.extract_text = lambda pdf, force=False: (pdf.with_suffix(".txt").write_bytes(HEADER), pdf.with_suffix(".txt"))[1]
ref = untc.MTDSGRef.parse("IV-4")


def status():
    err = io.StringIO()
    with redirect_stderr(err):
        return untc.fetch_status(ref), err.getvalue()


meta, _ = status()
check("first run downloads", (len(downloads), meta["status_date"], meta["parties"]), (1, "2026-09-21", 175))
pdf = untc.treaty_dir(ref) / "status.en.pdf"
old = time.time() - 3 * 86400
os.utime(pdf, (old, old))
meta, _ = status()
check("3-day-old cache is reused", len(downloads), 1)
check("fetched_utc is the download time, not now",
      meta["fetched_utc"], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(old)))
old = time.time() - (untc.STATUS_MAX_AGE_DAYS + 1) * 86400
os.utime(pdf, (old, old))
served["pdf"] = fake_pdf(b"20260928070000")
meta, note = status()
check("old cache is downloaded again", (len(downloads), meta["status_date"]), (2, "2026-09-28"))
check("… and says so", "days old" in note, True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
