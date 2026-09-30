#!/usr/bin/env python3
"""Short-page detection in per-treaty UNTS PDFs.

No network: the heights are the mediabox heights pypdf reports for
volume-34-I-541-English.pdf (the North Atlantic Treaty), whose printed
p. 246 is cropped and lacks the second paragraph of Article 5.

Run with `python tests/untc/test_short_pages.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc" / "scripts"))

import untc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


NATO = [660.0, 657.0, 491.0, 658.0, 660.0, 659.0, 659.0, 659.0, 89.0]
check("NATO: cropped p. 246 and the stub p. 255", untc.short_pages(NATO), [2, 8])
check("uniform pages", untc.short_pages([660.0, 657.0, 659.0, 658.0]), [])
check("small variation is not short", untc.short_pages([660.0, 600.0, 659.0]), [])
check("too few pages to judge", untc.short_pages([660.0, 300.0]), [])

if failures:
    sys.exit("%d failure(s)" % len(failures))
print("all ok")
