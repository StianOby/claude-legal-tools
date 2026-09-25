#!/usr/bin/env python3
"""Regression tests for the XHTML-to-text conversion in lovdata.py.

No network: the fixtures are markup copied from the public gjeldende-lover
package, trimmed to the elements the conversion depends on.

Run with `python plugins/lovdata-api/skills/lovdata-api/tests/test_html_to_text.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lovdata  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


# --------------------------------------------------------------------------
# EØS-loven (nl-19921127-109), EØS-avtalen art. 8 nr. 3 bokstav b. The
# footnote reference <sup>5</sup> used to be stripped along with its tag, so
# the text read «protokoll 35» (a different protocol) instead of «protokoll 3».
# --------------------------------------------------------------------------

ART8 = (
    '<ol><li data-name="b."><article class="listArticle"><article class="legalP">'
    'varer oppført i <a href="avtale/avt-1992-05-02-1-p3">protokoll 3</a>'
    '<sup class="footnotereference" data-footnotereferencevalue="5" '
    'data-unique-footnote-counter="24">5</sup> i samsvar med de særlige '
    'bestemmelser som er fastsatt i protokollen.</article></article></li></ol>'
    '<footer class="footnotes"><article class="footnote" data-name="5" '
    'data-unique-footnote-counter="24"><span class="footnoteLabel">5</span> '
    'Gjelder i det vesentlige handel med bearbeidede landbruksprodukter.'
    '</article></footer>'
)

print("EØS-avtalen art. 8 nr. 3 b (footnote after a protocol number)")
check(
    "reference kept apart from the number",
    lovdata._html_to_text(ART8),
    "b. varer oppført i protokoll 3[fn 5] i samsvar med de særlige "
    "bestemmelser som er fastsatt i protokollen.\n"
    "[fn 5] Gjelder i det vesentlige handel med bearbeidede landbruksprodukter.",
)

# Starred footnotes («*», «5*») occur in the package too.
check(
    "starred footnote reference",
    lovdata._html_to_text('avgift<sup class="footnotereference">5*</sup>.'),
    "avgift[fn 5*].",
)

# --------------------------------------------------------------------------
# Plain <sup> is an exponent: «20 m<sup>2</sup>» must not become «20 m2».
# --------------------------------------------------------------------------

print("Exponents")
check("m²", lovdata._html_to_text("inntil 20 m<sup>2</sup> på hver"), "inntil 20 m² på hver")
check("cm³", lovdata._html_to_text("5 g/cm<sup>3</sup> som"), "5 g/cm³ som")

if failures:
    print("\n%d failure(s)" % len(failures))
    sys.exit(1)
print("\nall passed")
