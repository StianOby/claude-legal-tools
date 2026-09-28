#!/usr/bin/env python3
"""Offline tests for scripts/lovdata_ref.py: the module's doctests plus a
table of citation forms, Norwegian and English. Run: python tests/test_ref.py
"""

import doctest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
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
    ("TRR-2019-1234", None, ""),
    ("Rt. 2000 p. 1811", None, ""),
]

# (input, search_hint)
HINTS = [
    ("Rt. 2000 s. 1811 (Finanger I) på s. 1827", "Rt-2000-1811"),
    ("Rt. 2000 p. 1811 at p. 1827", "Rt-2000-1811"),
    ("Rt. 2000 page 1811", "Rt-2000-1811"),
    ("RG 2010 s. 100", "RG-2010-100"),
    ("TRR-2019-1234", "TRR-2019-1234"),
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
    note = lovdata_ref.explain("TRR-2019-1234").get("note", "")
    if "Trygderetten" not in note:
        print(f"FAIL explain(TRR) note: {note!r}")
        errors += 1
    total = attempted + len(CASES) + len(HINTS) + 1
    print(f"{total - errors}/{total} passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
