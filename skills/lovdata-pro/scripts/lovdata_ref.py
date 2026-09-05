#!/usr/bin/env python3
"""Pure-Python reference resolver for Lovdata Pro citations.

Translates a human legal citation ("HR-2016-2554-P", "Ot.prp. nr. 3
(1998-99)", "Innst. 521 L (2024-2025)") into candidate Lovdata Pro paths
of the form <COLLECTION>/<TYPE>/<SLUG>, using the deterministic slug rules
recorded in ../references/lovdata-pro-mapping.md.

No network access, no browser. Citation forms that need runtime search
(Rt., RG, and other irregular slugs) come back with parsed=false and an
empty candidate list — the caller (the SKILL.md workflow, driving the
built-in browser's __lp.search()) handles those.

>>> parse_reference("HR-2016-2554-P").candidates
['HRSIV/avgjorelse/hr-2016-2554-p', 'HRSTR/avgjorelse/hr-2016-2554-p']

>>> parse_reference("LB-2021-12345").candidates
['LBSIV/avgjorelse/lb-2021-12345', 'LBSTR/avgjorelse/lb-2021-12345']

>>> parse_reference("LG-2008-135938").candidates
['LGSIV/avgjorelse/lg-2008-135938', 'LGSTR/avgjorelse/lg-2008-135938']

>>> parse_reference("TR-2020-11111").candidates
['TRSIV/avgjorelse/tr-2020-11111', 'TRSTR/avgjorelse/tr-2020-11111']

>>> parse_reference("Ot.prp. nr. 3 (1998-99)").candidates
['PROP/forarbeid/otprp-3-199899', 'OTPRP/forarbeid/otprp-3-199899']

>>> # Common Norwegian typo "Ot.prop." (extra letter) still parses.
>>> parse_reference("Ot.prop. nr. 3 (1998-99)").candidates
['PROP/forarbeid/otprp-3-199899', 'OTPRP/forarbeid/otprp-3-199899']

>>> parse_reference("Prop. 71 L (2024-2025)").candidates
['PROP/forarbeid/prop-71-l-202425']

>>> parse_reference("Innst. 521 L (2024-2025)").candidates
['INNST/forarbeid/inns-521-l-202425']

>>> parse_reference("NOU 2022:8").candidates
['NOU/forarbeid/nou-2022-8']

>>> parse_reference("NOU 2022: 8").candidates
['NOU/forarbeid/nou-2022-8']

>>> # Already-resolved raw path passes through unchanged.
>>> parse_reference("HRSIV/avgjorelse/hr-2016-2554-p").candidates
['HRSIV/avgjorelse/hr-2016-2554-p']

>>> # Trailing parenthetical case names are stripped before parsing...
>>> parse_reference("HR-2016-2554-P (Holship)").candidates
['HRSIV/avgjorelse/hr-2016-2554-p', 'HRSTR/avgjorelse/hr-2016-2554-p']

>>> # ...but a real session-year span in parens is preserved, not stripped.
>>> parse_reference("Ot.prp. nr. 3 (1998-99)").raw
'Ot.prp. nr. 3 (1998-99)'

>>> # Forms needing runtime search come back as None.
>>> parse_reference("Rt. 2000 s. 1811") is None
True
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass


# Year-pair encoding observed from real Lovdata Pro slugs:
#   (2024-2025) -> 202425 (full first year + last 2 of second)
#   (1998-99)   -> 199899
#   (1961-62)   -> 196162
_YEAR_PAIR = re.compile(r"\(?\s*(\d{4})\s*[-–/]\s*(\d{2,4})\s*\)?")


def _encode_session(years):
    m = _YEAR_PAIR.search(years)
    if not m:
        return None
    return f"{m.group(1)}{m.group(2)[-2:]}"


@dataclass
class Reference:
    collection: str
    type: str
    slug: str
    alt_collections: tuple = ()
    raw: str = ""

    @property
    def path(self):
        return f"{self.collection}/{self.type}/{self.slug}"

    @property
    def candidates(self):
        out = [self.path]
        for c in self.alt_collections:
            out.append(f"{c}/{self.type}/{self.slug}")
        return out


def parse_reference(ref):
    """Best-effort parse of a Norwegian legal citation.

    Returns None when the citation form needs runtime search (Rt., RG, etc.).
    See the module docstring for supported forms and examples.
    """
    s = ref.strip()
    raw = s
    # Strip a trailing parenthetical name suffix when it doesn't look like a
    # year span. Year spans contain only digits, hyphens, and en-dashes.
    s_for_parse = re.sub(r"\s*\((?![\d–\-]+\))[^)]*\)\s*$", "", s).strip()

    # Already-resolved path
    m = re.fullmatch(r"([A-Z]+)/(avgjorelse|forarbeid)/([a-z0-9\-]+)", s_for_parse, re.I)
    if m:
        return Reference(m.group(1).upper(), m.group(2).lower(), m.group(3).lower(), raw=raw)

    # Modern Supreme Court: HR-YYYY-NNNN-X
    m = re.fullmatch(r"HR-(\d{4})-(\d+)-([A-Z])", s_for_parse, re.I)
    if m:
        slug = f"hr-{m.group(1)}-{m.group(2)}-{m.group(3).lower()}"
        return Reference("HRSIV", "avgjorelse", slug,
                         alt_collections=("HRSTR",), raw=raw)

    # Lagmannsrett: LB/LA/LE/LF/LG/LH-YYYY-N
    m = re.fullmatch(r"(LB|LA|LE|LF|LG|LH)-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        court = m.group(1).upper()
        slug = f"{court.lower()}-{m.group(2)}-{m.group(3)}{m.group(4).lower()}"
        return Reference(f"{court}SIV", "avgjorelse", slug,
                         alt_collections=(f"{court}STR",), raw=raw)

    # Tingrett TR-YYYY-N
    m = re.fullmatch(r"TR-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        slug = f"tr-{m.group(1)}-{m.group(2)}{m.group(3).lower()}"
        return Reference("TRSIV", "avgjorelse", slug,
                         alt_collections=("TRSTR",), raw=raw)

    # Ot.prp. nr. N (YYYY-YY) - matches both "prp" and the typo "prop"
    m = re.match(r"Ot\.?\s*pr[op]p?\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return Reference("PROP", "forarbeid",
                             f"otprp-{m.group(1)}-{sess}",
                             alt_collections=("OTPRP",), raw=raw)

    # Prop. N L|S|... (YYYY-YY)
    m = re.match(r"Prop\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"prop-{n}-{kind}-{sess}" if kind else f"prop-{n}-{sess}"
            return Reference("PROP", "forarbeid", slug, raw=raw)

    # Innst. N L|S|... (YYYY-YY) - collection INNST, slug uses 'inns-'
    m = re.match(r"Innst\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"inns-{n}-{kind}-{sess}" if kind else f"inns-{n}-{sess}"
            return Reference("INNST", "forarbeid", slug, raw=raw)

    # NOU YYYY: N (also "NOU YYYY:N" or "NOU YYYY N")
    m = re.match(r"NOU\s*(\d{4})\s*[:\s]\s*(\d+[A-Za-z]?)", s, re.I)
    if m:
        return Reference("NOU", "forarbeid",
                         f"nou-{m.group(1)}-{m.group(2).lower()}", raw=raw)

    return None


def cmd_resolve(args):
    parsed = parse_reference(args.ref)
    if args.json_array:
        print(json.dumps(parsed.candidates if parsed else [], ensure_ascii=False))
        return 0 if parsed else 1
    result = {
        "input": args.ref,
        "parsed": parsed is not None,
        "candidates": parsed.candidates if parsed else [],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if parsed else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="lovdata_ref.py",
        description="Resolve a Norwegian legal citation to Lovdata Pro path candidates (no network access).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser(
        "resolve", help="Print candidate Lovdata Pro paths for a reference.")
    p_resolve.add_argument("ref")
    p_resolve.add_argument(
        "--json-array", action="store_true",
        help="Print just the candidate list, e.g. for pasting into __lp.load([...]).")
    p_resolve.set_defaults(func=cmd_resolve)

    return p


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
