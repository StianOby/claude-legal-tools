#!/usr/bin/env python3
"""
nb_download.py — download an nb.no item as a PDF: books, newspapers,
journals, photos, posters, maps, manuscripts, sheet music.

The plain download of zotero_book.py: the same downloader, access checks
and file name (AUTHOR_TITLE_(YEAR).pdf), without OCR, shrink or Zotero RDF.

    python nb_download.py --id <URN or id> --out <dir>
        [--start N --stop M]          canvas range (1-based manifest
                                      positions, covers included)
        [--nbsso "nbsso=<v>" | --cookie <file>|auto]   FEIDE (NB) items only
        [--size half|full]            half (default) or the scan's own size
        [--keep-images]               also keep the page JPEGs in
                                      <out>/<basename>_images/
        [--shrink]                    shrink the page images (shrink_pdf.py)

Any other zotero_book.py flag is passed through (--tiles, --workers,
--force-auth). A run that stops early, or leaves placeholder pages, keeps
its pages in <out>/_pages/: re-run the same command with the same --out to
fetch only the rest.

Exit codes as zotero_book.py: 0 done, 3 some pages are placeholders,
4 no usable cookie file, 1 any other error (the message says which).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zotero_book  # noqa: E402

# Before the caller's flags, so that e.g. --shrink still wins.
FIXED = ["--no-ocr", "--no-shrink", "--no-rdf"]


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    return zotero_book.main(FIXED + argv)


if __name__ == "__main__":
    sys.exit(main())
