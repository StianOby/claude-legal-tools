#!/usr/bin/env python3
"""Pure-Python reference resolver for Lovdata Pro citations.

Translates a human legal citation ("HR-2016-2554-P", "Ot.prp. nr. 3
(1998-99)", "Innst. 521 L (2024-2025)") into candidate Lovdata Pro paths
of the form <COLLECTION>/<TYPE>/<SLUG>, using the deterministic slug rules
recorded in ../references/lovdata-pro-mapping.md.

No network access, no browser. Citation forms that need runtime search
(Rt., RG, and other irregular slugs) come back with parsed=false, an
empty candidate list and a `search_hint` — the caller (the SKILL.md
workflow, driving the built-in browser) handles those.

>>> parse_reference("HR-2016-2554-P").candidates
['HRSIV/avgjorelse/hr-2016-2554-p', 'HRSTR/avgjorelse/hr-2016-2554-p']

>>> parse_reference("LB-2021-12345").candidates
['LBSIV/avgjorelse/lb-2021-12345', 'LBSTR/avgjorelse/lb-2021-12345']

>>> parse_reference("LG-2008-135938").candidates
['LGSIV/avgjorelse/lg-2008-135938', 'LGSTR/avgjorelse/lg-2008-135938']

>>> # District courts: Lovdata's references carry a court prefix
>>> # (TOSLO = Oslo tingrett before the 2021 court reform, TOSL after it).
>>> parse_reference("TOSLO-2019-12345").candidates
['TRSIV/avgjorelse/toslo-2019-12345', 'TRSTR/avgjorelse/toslo-2019-12345']

>>> parse_reference("TOSL-2022-123456").candidates
['TRSIV/avgjorelse/tosl-2022-123456', 'TRSTR/avgjorelse/tosl-2022-123456']

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

>>> # NOUs split into parts keep the part letter in the slug.
>>> parse_reference("NOU 2001: 32 A").candidates
['NOU/forarbeid/nou-2001-32a']

>>> # Already-resolved raw path passes through unchanged.
>>> parse_reference("HRSIV/avgjorelse/hr-2016-2554-p").candidates
['HRSIV/avgjorelse/hr-2016-2554-p']

>>> # Trailing parenthetical case names are stripped before parsing...
>>> parse_reference("HR-2016-2554-P (Holship)").candidates
['HRSIV/avgjorelse/hr-2016-2554-p', 'HRSTR/avgjorelse/hr-2016-2554-p']

>>> # ...but a real session-year span in parens is preserved, not stripped.
>>> parse_reference("Ot.prp. nr. 3 (1998-99)").raw
'Ot.prp. nr. 3 (1998-99)'

>>> # Pinpoints (avsnitt, side, punkt) are split off and reported.
>>> r = parse_reference("HR-2016-2554-P avsnitt 77")
>>> r.candidates[0], r.pinpoint
('HRSIV/avgjorelse/hr-2016-2554-p', 'avsnitt 77')

>>> # Forms whose slug rule is inferred but not yet confirmed in Pro are
>>> # returned with unverified=True so the caller falls back to search.
>>> r = parse_reference("Meld. St. 17 (2020-2021)")
>>> r.candidates, r.unverified
(['MELD/forarbeid/meldst-17-202021'], True)

>>> # Forms needing runtime search come back as None ...
>>> parse_reference("Rt. 2000 s. 1811") is None
True

>>> # ... with a search hint in Lovdata's own reference form.
>>> search_hint("Rt. 2000 s. 1811 (Finanger I) på s. 1827")
'Rt-2000-1811'
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

# Trailing pinpoint: "avsnitt 77", "avsn. 77", "premiss 12", "s. 1827",
# "på s. 1827", "side 12", "punkt 3.4", "pkt. 3.4", "kapittel 4", "kap. 4",
# possibly several ("... avsnitt 77 flg.").
_PINPOINT = re.compile(
    r"\s*(?:,|på|jf\.?)?\s*"
    r"((?:avsnitt|avsn\.?|premiss(?:ene)?|side|s\.|punkt|pkt\.?|kapittel|kap\.?|§)"
    r"\s*[\d][\d.\-–]*[a-z]?(?:\s*(?:flg\.?|ff\.?))?)\s*$",
    re.I,
)

_LAGMANNSRETT = ("LB", "LA", "LE", "LF", "LG", "LH")


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
    pinpoint: str = ""
    unverified: bool = False
    note: str = ""

    @property
    def path(self):
        return f"{self.collection}/{self.type}/{self.slug}"

    @property
    def candidates(self):
        out = [self.path]
        for c in self.alt_collections:
            out.append(f"{c}/{self.type}/{self.slug}")
        return out


def split_pinpoint(s):
    """Return (citation, pinpoint) — pinpoint is "" when there is none."""
    pins = []
    while True:
        m = _PINPOINT.search(s)
        if not m or m.start() == 0:
            break
        rest = s[:m.start()].rstrip(" ,")
        # "Rt. 2000 s. 1811" / "RG 2010 s. 100": the page IS the citation,
        # not a pinpoint — stop when only the reporter + year would remain.
        if re.fullmatch(r"(Rt|RG)\.?\s*[-–]?\s*\d{4}", rest.strip(), re.I):
            break
        pins.insert(0, re.sub(r"\s+", " ", m.group(1)).strip())
        s = rest
    return s.strip(), " ".join(pins)


def search_hint(ref):
    """Best search query for a citation that has no deterministic slug.

    Lovdata's own reference form (Rt-2000-1811, RG-2010-100) is what the
    Pro quick search matches most precisely; a free-text query with spaces
    and "s." mostly returns documents that *cite* the decision.
    """
    s, _ = split_pinpoint(ref.strip())
    s = re.sub(r"\s*\((?![\d–\-]+\))[^)]*\)\s*$", "", s).strip()
    m = re.match(r"(Rt|RG)\.?\s*[-–]?\s*(\d{4})\s*(?:s\.?|side|[-–])\s*(\d+)", s, re.I)
    if m:
        return f"{m.group(1).capitalize() if m.group(1).lower() == 'rt' else 'RG'}-{m.group(2)}-{m.group(3)}"
    return s


def parse_reference(ref):
    """Best-effort parse of a Norwegian legal citation.

    Returns None when the citation form needs runtime search (Rt., RG, etc.).
    See the module docstring for supported forms and examples.
    """
    raw = ref.strip()
    s, pinpoint = split_pinpoint(raw)
    # Strip a trailing parenthetical name suffix when it doesn't look like a
    # year span. Year spans contain only digits, hyphens, and en-dashes.
    s_for_parse = re.sub(r"\s*\((?![\d–\-]+\))[^)]*\)\s*$", "", s).strip()

    def ref_(*a, **kw):
        kw.setdefault("raw", raw)
        kw.setdefault("pinpoint", pinpoint)
        return Reference(*a, **kw)

    # Already-resolved path
    m = re.fullmatch(r"([A-Z]+)/(avgjorelse|forarbeid)/([a-z0-9\-]+)", s_for_parse, re.I)
    if m:
        return ref_(m.group(1).upper(), m.group(2).lower(), m.group(3).lower())

    # Modern Supreme Court: HR-YYYY-NNNN-X
    m = re.fullmatch(r"HR-(\d{4})-(\d+)-([A-Z])", s_for_parse, re.I)
    if m:
        slug = f"hr-{m.group(1)}-{m.group(2)}-{m.group(3).lower()}"
        return ref_("HRSIV", "avgjorelse", slug, alt_collections=("HRSTR",))

    # Lagmannsrett: LB/LA/LE/LF/LG/LH-YYYY-N
    m = re.fullmatch(r"(LB|LA|LE|LF|LG|LH)-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        court = m.group(1).upper()
        slug = f"{court.lower()}-{m.group(2)}-{m.group(3)}{m.group(4).lower()}"
        return ref_(f"{court}SIV", "avgjorelse", slug, alt_collections=(f"{court}STR",))

    # Tingrett: court-prefixed references such as TOSLO-2019-12345 (Oslo
    # tingrett before the 2021 reform), TOSL-2022-123456 (after it),
    # TBERG-, TSTAV-, THOD- ... The generic TR-YYYY-N form is accepted too.
    m = re.fullmatch(r"(T[A-Z]{1,5})-(\d{4})-(\d+)([A-Za-z\-0-9]*)", s_for_parse, re.I)
    if m:
        slug = f"{m.group(1).lower()}-{m.group(2)}-{m.group(3)}{m.group(4).lower()}"
        return ref_("TRSIV", "avgjorelse", slug, alt_collections=("TRSTR",))

    # Ot.prp. nr. N (YYYY-YY) - matches both "prp" and the typo "prop"
    m = re.match(r"Ot\.?\s*pr[op]p?\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("PROP", "forarbeid", f"otprp-{m.group(1)}-{sess}",
                        alt_collections=("OTPRP",))

    # St.prp. nr. N (YYYY-YY) — never full-text indexed in Pro (header + PDF
    # link only); the slug follows the Ot.prp. pattern but is unconfirmed.
    m = re.match(r"St\.?\s*prp\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("PROP", "forarbeid", f"stprp-{m.group(1)}-{sess}",
                        unverified=True,
                        note="St.prp. are not full-text indexed in Lovdata Pro (header + PDF only)")

    # Prop. N L|S|... (YYYY-YY)
    m = re.match(r"Prop\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"prop-{n}-{kind}-{sess}" if kind else f"prop-{n}-{sess}"
            return ref_("PROP", "forarbeid", slug)

    # Innst. O. nr. N / Innst. S. nr. N (YYYY-YY) — pre-2009 committee
    # recommendations. Slug inferred from the post-2009 "inns-N-l-YYYYYY"
    # rule; not yet confirmed against Pro.
    m = re.match(r"Innst\.?\s*([OS])\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(3))
        if sess:
            return ref_("INNST", "forarbeid",
                        f"inns-{m.group(1).lower()}-{m.group(2)}-{sess}",
                        unverified=True)

    # Innst. N L|S|... (YYYY-YY) - collection INNST, slug uses 'inns-'
    m = re.match(r"Innst\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"inns-{n}-{kind}-{sess}" if kind else f"inns-{n}-{sess}"
            return ref_("INNST", "forarbeid", slug)

    # Meld. St. N (YYYY-YY) (from 2009) / St.meld. nr. N (YYYY-YY) (before).
    # Collection and slug are inferred (mapping: "likely MELD"), unconfirmed.
    m = re.match(r"Meld\.?\s*St\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("MELD", "forarbeid", f"meldst-{m.group(1)}-{sess}", unverified=True)
    m = re.match(r"St\.?\s*meld\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("MELD", "forarbeid", f"stmeld-{m.group(1)}-{sess}", unverified=True)

    # Dok. 8:N (YYYY-YY) — private members' bills; REPFOR/forarbeid/dok8-N-YYYYYY
    m = re.match(r"Dok(?:ument)?\.?\s*(?:nr\.?\s*)?8\s*:\s*(\d+)\s*([LS]?)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(3))
        if sess:
            kind = m.group(2).lower()
            slug = f"dok8-{m.group(1)}-{kind}-{sess}" if kind else f"dok8-{m.group(1)}-{sess}"
            return ref_("REPFOR", "forarbeid", slug)

    # NOU YYYY: N (also "NOU YYYY:N" or "NOU YYYY N"), optional part letter
    # ("NOU 2001: 32 A" -> nou-2001-32a).
    m = re.match(r"NOU\s*(\d{4})\s*[:\s]\s*(\d+)(?:\s*([A-Ba-b]))?(?![A-Za-z])", s, re.I)
    if m:
        part = (m.group(3) or "").lower()
        return ref_("NOU", "forarbeid", f"nou-{m.group(1)}-{m.group(2)}{part}")

    return None


def explain(ref):
    """Full resolution result as a JSON-serialisable dict."""
    parsed = parse_reference(ref)
    out = {
        "input": ref,
        "parsed": parsed is not None,
        "candidates": parsed.candidates if parsed else [],
    }
    if parsed:
        if parsed.pinpoint:
            out["pinpoint"] = parsed.pinpoint
        if parsed.unverified:
            out["unverified"] = True
            out["note"] = parsed.note or (
                "slug inferred from the pattern of related document types but "
                "not confirmed in Lovdata Pro — if load() reports not_found, "
                "fall back to search")
        elif parsed.note:
            out["note"] = parsed.note
    else:
        _, pin = split_pinpoint(ref.strip())
        if pin:
            out["pinpoint"] = pin
        out["search_hint"] = search_hint(ref)
        out["note"] = ("no deterministic slug for this citation form (Rt./RG/other); "
                       "search Lovdata Pro for the search_hint and verify the hit")
    return out


def cmd_resolve(args):
    parsed = parse_reference(args.ref)
    if args.json_array:
        print(json.dumps(parsed.candidates if parsed else [], ensure_ascii=False))
        return 0 if parsed else 1
    print(json.dumps(explain(args.ref), indent=2, ensure_ascii=False))
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
