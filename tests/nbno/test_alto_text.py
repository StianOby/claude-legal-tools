#!/usr/bin/env python3
"""Offline tests for scripts/alto_text.py: every ALTO character reaches the
PDF text layer as it is (Sámi, Greek, characters outside the BMP), which the
WinAnsi font up to nbno 1.4.7 turned into "?". The round trip through a PDF
needs pikepdf and pypdf and is skipped without them.
Run: python tests/nbno/test_alto_text.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
import alto_text  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
<Description><MeasurementUnit>mm10</MeasurementUnit></Description>
<Layout><Page WIDTH="2100" HEIGHT="2970"><PrintSpace>
<TextLine VPOS="200" HEIGHT="60">
 <String HPOS="100" VPOS="200" WIDTH="300" HEIGHT="60" CONTENT="Blåbærsyltetøy"/>
 <String HPOS="450" VPOS="200" WIDTH="300" HEIGHT="60" CONTENT="Čáhcegáddi"/>
 <String HPOS="800" VPOS="200" WIDTH="200" HEIGHT="60" CONTENT="đŋŧ"/>
</TextLine>
<TextLine VPOS="300" HEIGHT="60">
 <String HPOS="100" VPOS="300" WIDTH="300" HEIGHT="60" CONTENT="Ἀθῆναι"/>
 <String HPOS="450" VPOS="300" WIDTH="300" HEIGHT="60" CONTENT="ſtatens"/>
 <String HPOS="800" VPOS="300" WIDTH="200" HEIGHT="60" CONTENT="\U0001d509raktur"/>
 <String HPOS="1100" VPOS="300" WIDTH="300" HEIGHT="60" CONTENT="under"/>
 <HYP HPOS="1400" WIDTH="20" CONTENT="-"/>
</TextLine>
</PrintSpace></Page></Layout></alto>"""
WORDS = ["Blåbærsyltetøy", "Čáhcegáddi", "đŋŧ", "Ἀθῆναι", "ſtatens", "\U0001d509raktur", "under-"]

print("encoding")
page = alto_text.parse_alto(ALTO.encode("utf-8"))
check("ALTO words", [w[4] for _lv, _lh, ws in page.lines for w in ws], WORDS)
extra = alto_text._extra_cids([page])
check("non-BMP character gets a CID of its own", extra, {"\U0001d509": 0xD800})
check("CID = code point", alto_text._pdf_hex("Čø", extra), "<010c00f8>")
check("non-BMP via its CID", alto_text._pdf_hex("\U0001d509", extra), "<d800>")
cmap = alto_text._to_unicode(extra).decode("ascii")
check("ToUnicode maps the BMP", ("<0100> <01ff> <0100>" in cmap, "<d800> <d8ff>" in cmap), (True, False))
check("ToUnicode maps the extra CID", "<d800> <d835dd09>" in cmap, True)

print("round trip through a PDF")
try:
    import pikepdf
    from pypdf import PdfReader
except ImportError as e:
    print(f"  skip ({e.name} not installed)")
else:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "p.pdf"
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(595, 842))
        pdf.save(out)
        stats = alto_text.apply_alto(out, ["c1"], {"c1": page})
        check("words written", stats["words"], 7)
        text = PdfReader(out).pages[0].extract_text()
        check("every character comes back", [w for w in WORDS if w not in text], [])
        check("no ?", "?" in text, False)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
