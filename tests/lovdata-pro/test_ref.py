#!/usr/bin/env python3
"""Offline tests for scripts/lovdata_ref.py: the module's doctests plus a
table of citation forms, Norwegian and English. Run: python tests/lovdata-pro/test_ref.py
"""

import doctest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugins", "lovdata-pro", "skills", "lovdata-pro", "scripts"))
import lovdata_ref  # noqa: E402

HR = "HRSIV/avgjorelse/hr-2016-2554-p"

# (input, first candidate or None, pinpoint)
CASES = [
    ("HR-2016-2554-P avsnitt 77", HR, "avsnitt 77"),
    ("HR-2016-2554-P avsn. 77 flg.", HR, "avsn. 77 flg."),
    ("HR-2016-2554-P para. 77", HR, "para. 77"),
    ("HR-2016-2554-P para 77", HR, "para 77"),
    ("HR-2016-2554-P paras 77–80", HR, "paras 77–80"),
    ("HR-2016-2554-P, paragraph 77", HR, "paragraph 77"),
    ("HR-2016-2554-P at para. 77 et seq.", HR, "para. 77 et seq."),
    ("HR-2016-2554-P ¶ 77", HR, "¶ 77"),
    ("HR-2016-2554-P (Holship) para. 77", HR, "para. 77"),
    ("NOU 2022:8 section 3.4", "NOU/forarbeid/nou-2022-8", "section 3.4"),
    ("NOU 2022:8 chapter 4", "NOU/forarbeid/nou-2022-8", "chapter 4"),
    ("NOU 2022: 8 punkt 3.4", "NOU/forarbeid/nou-2022-8", "punkt 3.4"),
    ("Ot.prp. nr. 3 (1998-99) p. 12", "PROP/forarbeid/otprp-3-199899", "p. 12"),
    ("Ot.prp. nr. 3 (1998-99) pp. 12-14", "PROP/forarbeid/otprp-3-199899", "pp. 12-14"),
    ("Ot.prp. nr. 3 (1998-99) s. 12", "PROP/forarbeid/otprp-3-199899", "s. 12"),
    ("Prop. 71 L (2024-2025) page 40", "PROP/forarbeid/prop-71-l-202425", "page 40"),
    ("TOSLO-2019-12345", "TRSIV/avgjorelse/toslo-2019-12345", ""),
    ("TRR-2019-1234", "TRR/avgjorelse/trr-2019-1234", ""),
    # Special courts, publications, nemnder, uttalelser, rundskriv
    # (base codes from the new Pro's base-tree, 2026-11-26).
    ("AR-2026-38", "ARD/avgjorelse/ar-2026-38", ""),
    ("JOAG-2014-13", "JSO/avgjorelse/joag-2014-13", ""),
    ("JMOR-2025-119750", "JSR/avgjorelse/jmor-2025-119750", ""),
    ("UTMA-2024-92925", "UTMA/avgjorelse/utma-2024-92925", ""),
    ("ND-2025-23 (23)", "NDS/avgjorelse/nd-2025-23", ""),
    ("KOFA-2026-1389 avsnitt 30", "KOFA/avgjorelse/kofa-2026-1389", "avsnitt 30"),
    ("FinKN-2026-1252", "FINKNB/avgjorelse/finkn-2026-1252", ""),
    ("SKNA2-2026-51", "SKN/avgjorelse/skna2-2026-51", ""),
    ("SKN-2008-106", "SKNS/avgjorelse/skn-2008-106", ""),
    ("ADN-2026-D24673", "ADN/avgjorelse/adn-2026-d24673", ""),
    ("BVHN-2026-199-BRO", "BVHN/avgjorelse/bvhn-2026-199-bro", ""),
    ("SOM-2025-2770", "SOMB/avgjorelse/som-2025-2770", ""),
    ("JDLOV-2024-5261", "JDLOV/avgjorelse/jdlov-2024-5261", ""),
    ("TLN-2026-98", "TLN/avgjorelse/tln-2026-98", ""),
    ("TGLA-1900-1", "TGLA/avgjorelse/tgla-1900-1", ""),
    ("TUDEP/avgjorelse/tudep-2026-2656-*", "TUDEP/avgjorelse/tudep-2026-2656-*", ""),
    ("RA-2026-819", "RA/avgjorelse/ra-2026-819", ""),
    ("G-1958-0005", "RDEP/rundskriv/g-1958-5", ""),
    ("rundskriv GI-2026-8", "RDEP/rundskriv/gi-2026-8", ""),
    ("IS-2026-9003", "ROO/rundskriv/is-2026-9003", ""),
    ("UNEPN-2025-1", "RUNE/rundskriv/unepn-2025-1", ""),
    ("Rt-1944-640", None, ""),
    ("ND 1990 s. 140", None, ""),
    # Forarbeider og stortingsdokumenter beyond Prop./NOU/Innst.
    ("PRE-2026-11-20-2434", "PRE/forarbeid/pre-2026-11-20-2434", ""),
    # Laws and regulations: the short form, which the new Pro resolves to
    # the consolidated, repealed or Lovtidend text.
    ("LOV-2026-06-23-69", "lov/2026-06-23-69", ""),
    ("LOV-2005-06-17-62 § 14-9", "lov/2005-06-17-62", "§ 14-9"),
    ("LOV-1687-04-15", "lov/1687-04-15", ""),
    ("FOR-2011-12-06-1360", "forskrift/2011-12-06-1360", ""),
    ("lov 17. juni 2005 nr. 62", "lov/2005-06-17-62", ""),
    ("loven av 4. februar 1977 nr. 4", "lov/1977-02-04-4", ""),
    ("forskrift 2011-12-06 nr. 1360", "forskrift/2011-12-06-1360", ""),
    ("HIST/lov/2005-06-17-62-20190101", "HIST/lov/2005-06-17-62-20190101", ""),
    ("RFA/lov/2005-06-17-62", "RFA/lov/2005-06-17-62", ""),
    ("Ot.meld. nr. 1 (2006-2007)", "OTMELD/forarbeid/otmeld-1-200607", ""),
    ("Besl. O. nr. 75 (1977-78)", "LOVVED/forarbeid/besl-o-75-197778", ""),
    ("Lovvedtak 2 (2026-2027)", "LOVVED/forarbeid/lovvedtak-2-202627", ""),
    ("Innst. O. nr. VII (1898-99)", "INNST/forarbeid/inns-o-vii-189899", ""),
    ("Representantforslag 59 S (2026-2027)", "REPFOR/forarbeid/representantforslag-59-202627", ""),
    ("Dokument 8:59 S (2026-2027)", "REPFOR/forarbeid/representantforslag-59-202627", ""),
    ("Grunnlovsforslag 34 (2023-2024)", "GLFOR/forarbeid/dok12-34-202324", ""),
    ("Dokument 5 (2025-2026)", "SDOK/forarbeid/dok5-202526", ""),
    ("Rt. 2000 p. 1811", None, ""),
]

# (input, search_hint)
HINTS = [
    ("Rt. 2000 s. 1811 (Finanger I) på s. 1827", "Rt-2000-1811"),
    ("Rt. 2000 p. 1811 at p. 1827", "Rt-2000-1811"),
    ("Rt. 2000 page 1811", "Rt-2000-1811"),
    ("RG 2010 s. 100", "RG-2010-100"),
    ("ND 1990 s. 140", "ND-1990-140"),
    ("Utv. 2017 s. 1057", "UTV-2017-1057"),
]


def main():
    failed, attempted = doctest.testmod(lovdata_ref)
    errors = failed
    for ref, want, pin in CASES:
        r = lovdata_ref.parse_reference(ref)
        got = r.candidates[0] if r else None
        gotpin = r.pinpoint if r else lovdata_ref.split_pinpoint(ref)[1]
        if got != want or gotpin != pin:
            print(f"FAIL {ref!r}: got {got!r} / {gotpin!r}, want {want!r} / {pin!r}")
            errors += 1
    for ref, want in HINTS:
        got = lovdata_ref.search_hint(ref)
        if got != want:
            print(f"FAIL search_hint({ref!r}) = {got!r}, want {want!r}")
            errors += 1
    # pro2_ref: the short form the new Pro resolves, for reports cited by
    # volume and page and for prefixes not in the tables.
    for ref, want in [("NAD 1988 s. 1369", "avgjorelse/nad-1988-1369"),
                      ("BKN-1988-1", "avgjorelse/bkn-1988-1"),
                      ("LOV-2005-06-17-62-x", None)]:
        got = lovdata_ref.explain(ref).get("pro2_ref")
        if got != want:
            print(f"FAIL explain({ref!r}) pro2_ref = {got!r}, want {want!r}")
            errors += 1
    got = lovdata_ref.explain("LOV-2005-06-17-62").get("forarbeider")
    if got != "RFA/lov/2005-06-17-62":
        print(f"FAIL explain(LOV) forarbeider = {got!r}")
        errors += 1
    total = attempted + len(CASES) + len(HINTS) + 4
    print(f"{total - errors}/{total} passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
