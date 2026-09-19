#!/usr/bin/env python3
"""Regression tests for locating a treaty inside a UNTS volume PDF.

No network: the fixtures are the page text pypdf actually extracts from the
volumes named below, trimmed to the lines the matching depends on.

Run with `python plugins/untc/skills/untc/tests/test_locate.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import untc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


# --------------------------------------------------------------------------
# Volume 15 (1948): the contents page for section II carries "No. 102." close
# enough to the top of the page that a 200-character window matches it, 300
# pages before the Chicago Convention itself. Before this was fixed,
# `text --vol 15 --reg 102` returned PDF pages 8-11 - a contents snippet.
# --------------------------------------------------------------------------

V15 = [
    "UTNONATIONS UNIES\nTreaty Series\nVOLUME 15\n",
    "Treaties and international agreements registered\nVOLUME 15 1948 L Nos. 225-244\n"
    "TABLE OF CONTENTS\nI\nPage\nNo. 225. Union of Burma:\nDeclaration ............ 1\n",
    "Traites et accords internationaux enregistris\nTABLE DES MATIERES\n"
    "No 225. Union de Birmanie:\nDeclaration ............ 1\n",
    "IV United Nations - Treaty Series 1948\nPage\nNo. 230. Poland and Bulgaria:\n"
    "Agreement concerning cultural co-operation ............ 123\n"
    "No. 231. Poland and Hungary:\nAgreement ............ 145\n",
    # the page that used to be returned as the treaty text
    "VIII United Nations - Treaty Series 1948\nII\nTreaties and international agreements\n"
    "filed and recorded from 5 April 1948 to 21 June 1498\n"
    "No. 102. Afghanistan, Australia, Belgium, Bolivia, Brazil, etc.:\n"
    "Convention on International Civil Aviation. Signed at Chicago, on\n"
    "7 D ecem ber 1944 ........................................\n"
    "No. 103. Switzerland and International Labour Organisation:\n"
    "Procs-verbal ............ 397\n",
    "Treaties and international agreements\nfiled and recorded\n",
    "",
    # printed p. 295, no folio of its own (half-title)
    "No. 102\nAFGHANISTAN, AUSTRALIA, BELGIUM,\nBOLIVIA, BRAZIL, etc.\n"
    "Convention on International Civil Aviation. Signed at Chi-\ncago, on 7 December 1944\n",
    "296 United Nations -Treaty Series 1948\nNo. 102. CONVENTION1 ON INTERNATIONAL CIVIL AVI-\n"
    "ATION. SIGNED AT CHICAGO, ON 7 DECEMBER 1944\nPREAMBLE\n",
    "1948 Nations Unies - Recueil des Traitds 297\nArticle 1\nThe contracting States recognize\n",
    "298 United Nations -Treaty Series 1948\nArticle 2\nFor the purposes of this Convention\n",
    "",
    "No. 103\nSWITZERLAND\nand\nINTERNATIONAL LABOUR ORGANISATION\n",
]

print("volume 15 / No. 102 (Chicago Convention)")
check("the section II contents page is recognised as contents",
      untc._is_contents_page(V15[4]), True)
check("the half-title is not",
      untc._is_contents_page(V15[7]), False)
check("locate_in_volume skips the contents and finds the half-title",
      untc.locate_in_volume(V15, "102"), (7, 12))
check("printed folio read off a verso running head",
      untc.printed_page_of(V15[8]), 296)
check("printed folio read off a recto running head",
      untc.printed_page_of(V15[9]), 297)
check("a contents page has no folio",
      untc.printed_page_of(V15[4]), None)
check("printed p. 295 extrapolates back onto the half-title",
      untc.index_for_printed_page(V15, 295), 7)

# The contents parse loses the page column for No. 102 and reads the date at
# the end of another entry as a page, which used to send 15 UNTS 295 to the
# last entry with a page at or below it.
V15_TOC = [
    {"reg": "225", "title": "Union of Burma: Declaration", "page": 1, "annex": ""},
    {"reg": "230", "title": "Poland and Bulgaria", "page": 123, "annex": ""},
    {"reg": "243", "title": "United States of America and Finland", "page": 273, "annex": ""},
    {"reg": "102", "title": "Afghanistan, Australia ...: Convention on International Civil Aviation",
     "page": None, "annex": ""},
]
hit = untc._resolve_page(V15, V15_TOC, 295)
check("15 UNTS 295 resolves to No. 102, not to the contents' No. 243",
      hit and hit["reg"], "102")
check("the source of the answer is reported", hit and hit["via"], "running-head")
check("the disagreement with the contents is surfaced",
      bool(hit and hit.get("warning")), True)
check("the title comes from the contents entry",
      hit and hit["title"].startswith("Afghanistan"), True)

# --------------------------------------------------------------------------
# Volume 999 (1976): OCR reads the ICCPR's half-title "No. 14668" as
# "lo. 14668", so a literal "No." match finds nothing at all.
# --------------------------------------------------------------------------

V999 = [
    "170 United Nations - Treaty Series 1976\nNo. 14667. MULTILATERAL\nFinal article\n",
    "lo. 14668\nMULTILATERAL\nInternational Covenant on Civil and Political Rights.\n"
    "Adopted by the General Assembly of the United Nations on 16 December 1966\n",
    "172 United Nations - Treaty Series 1976\nNo. 14668. INTERNATIONAL COVENANT ON CIVIL\nAND POLITICAL RIGHTS\n",
]

print("volume 999 / No. 14668 (ICCPR), half-title mangled by OCR")
check("the mangled half-title still matches",
      untc._opens_with_reg(V999[1], "14668"), True)
check("locate_in_volume finds it", untc.locate_in_volume(V999, "14668"), (1, 3))
check("999 UNTS 171 resolves to No. 14668, not the preceding No. 14667",
      untc._resolve_page(V999, [], 171)["reg"], "14668")

# --------------------------------------------------------------------------
# A page number cannot exceed the last folio printed in the volume: an entry
# reading "Signed at Paris, on 6 March 1946" must not yield page 1946.
# --------------------------------------------------------------------------

print("contents page-column sanity")
check("the volume's last folio is found", untc.max_printed_page(V15), 298)

print()
if failures:
    print("%d failing check(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all checks passed")
