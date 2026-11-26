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

>>> # English pinpoints work the same way.
>>> r = parse_reference("HR-2016-2554-P, paras. 77-80")
>>> r.candidates[0], r.pinpoint
('HRSIV/avgjorelse/hr-2016-2554-p', 'paras. 77-80')

>>> search_hint("Rt. 2000 p. 1811 at p. 1827")
'Rt-2000-1811'

>>> # Trygderetten (TRR-) is not a tingrett.
>>> parse_reference("TRR-2019-1234").candidates
['TRR/avgjorelse/trr-2019-1234']

>>> # Nemnder, uttalelser, rundskriv: the base comes from the prefix.
>>> parse_reference("KOFA-2026-1389").candidates
['KOFA/avgjorelse/kofa-2026-1389']
>>> parse_reference("Rundskriv G-01/2016").candidates
['RDEP/rundskriv/g-2016-1', 'RDEPO/rundskriv/g-2016-1']

>>> # Reports cited by volume and page are resolved by the new Pro.
>>> explain("ND 1990 s. 140")["pro2_ref"]
'avgjorelse/nd-1990-140'

>>> parse_reference("Dokument 12:34 (2023-2024)").candidates
['GLFOR/forarbeid/dok12-34-202324']

>>> parse_reference("Innst. O. nr. 45 (2004-2005)").candidates
['INNST/forarbeid/inns-o-45-200405']

>>> parse_reference("Dok. 8:12 (1999-2000)").candidates
['REPFOR/forarbeid/dok8-12-199900']

>>> # Forms needing runtime search come back as None ...
>>> parse_reference("Rt. 2000 s. 1811") is None
True

>>> # ... with a search hint in Lovdata's own reference form.
>>> search_hint("Rt. 2000 s. 1811 (Finanger I) på s. 1827")
'Rt-2000-1811'

>>> # The new Lovdata Pro resolves the short form directly.
>>> explain("Rt. 2000 s. 1811 (Finanger I) på s. 1827")["pro2_ref"]
'avgjorelse/rt-2000-1811'
>>> explain("RG 2010 s. 100")["pro2_ref"]
'avgjorelse/rg-2010-100'

>>> # Stortingsmeldinger have a Lovdata-assigned sequence number in the
>>> # slug (STS/forarbeid/stsg-202021-355), so they cannot be resolved
>>> # offline either — explain() says where to look.
>>> parse_reference("Meld. St. 17 (2020-2021)") is None
True
>>> explain("Meld. St. 17 (2020-2021)")["note"].startswith("stortingsmeldinger")
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

# Trailing pinpoint: "avsnitt 77", "avsn. 77", "premiss 12", "s. 1827",
# "på s. 1827", "side 12", "punkt 3.4", "pkt. 3.4", "kapittel 4", "kap. 4",
# possibly several ("... avsnitt 77 flg."). English manuscripts cite the same
# places as "para. 77", "paras 77-80", "at p. 1827", "pp. 12-14",
# "section 3.4", "chapter 4", "para 77 et seq.". The keyword must start a
# word, so the "p." at the end of "Ot.prp." is never taken for a page.
_PINPOINT = re.compile(
    r"\s*(?:,|\bpå\b|\bjf\.?|\bat\b)?\s*"
    r"(?<!\w)((?:avsnitt|avsn\.?|premiss(?:ene)?|side|s\.|punkt|pkt\.?|kapittel|kap\.?|§"
    r"|paragraphs?|paras?\.?|¶|pp?\.|pages?|sections?|sec\.|chapter|ch\.)"
    r"\s*[\d][\d.\-–]*[a-z]?(?:\s*(?:flg\.?|ff\.?|et\s+seq\.?))?)\s*$",
    re.I,
)

_LAGMANNSRETT = ("LB", "LA", "LE", "LF", "LG", "LH")

# Lovdata's own references of the form PREFIX-YYYY-N[suffix] for special
# courts, publications, uttalelser and nemnder (type avgjorelse), mapped to
# the base the new Lovdata Pro files them under (base-tree, 2026-11-26;
# references/lovdata-pro-mapping.md). The id is the lower-cased reference.
# When the id carries a suffix the citation leaves out (ND-2025-23 is
# nd-2025-23-23s), the full path misses and load() resolves the short form
# avgjorelse/<id> on pro2 instead, which finds the suffixed id and the base.
# Only prefixes in use today are listed; older ones (BKN-, LKN-, ENV- …)
# go through the generic pro2_ref in explain().
_AVG_PREFIXES = {
    # Spesialdomstoler
    "AR": ("ARD",), "ARD": ("ARD",), "TRR": ("TRR",), "HFK": ("HFK",),
    "FKR": ("FKR",), "UTMA": ("UTMA",), "UNT": ("UNT",),
    # Publikasjoner
    "ND": ("NDS", "NDSENG"), "NAD": ("NAD",),
    # Uttalelser, and the rundskriv bases filed as avgjorelse
    "JDLOV": ("JDLOV",), "SOM": ("SOMB",), "SOMB": ("SOMB",), "SOMFOR": ("SOMFOR",),
    "BFU": ("BFU",), "USKD": ("USKD",), "UFIN": ("UFIN",), "UMD": ("UMD",),
    "TUDEP": ("TUDEP",), "BFJR": ("BFJR",), "RA": ("RA", "RAO"), "SKM": ("SKM",),
    # Nemnder og utvalg
    "ADN": ("ADN",), "ADT": ("ADT",), "AN": ("AN",), "APN": ("APN",), "BVHN": ("BVHN",),
    "DIN": ("DIN",), "DOK": ("DOK",), "ELKN": ("ELKN",), "ENK": ("ENK",),
    "FINKN": ("FINKNB", "FINKNF", "FINKNI"), "FTK": ("FTK",), "FKU": ("FKU",),
    "FOV": ("FOV",), "FREN": ("FREN",), "GK": ("GK",), "HPN": ("HPN",), "HTU": ("HTU",),
    "KTN": ("KTN",), "KEOS": ("KEOS",), "UKN": ("UKN",), "KDF": ("KDF",),
    "KFIR": ("KFIR",), "INTOPS": ("INTOPS",), "KMVA": ("KMVA",), "KMI": ("KMI",),
    "NSK": ("NSK",), "KOFA": ("KOFA",), "PSK": ("PSK",), "KTKN": ("KTKN",),
    "KT": ("KT",), "KTKD": ("KTKD",), "LOTN": ("LOTN",), "MR": ("MR",), "MKN": ("MKN",),
    "NKU": ("NKU",), "OB": ("OB",), "PRKN": ("PRKN",), "PARKN": ("PARKN",),
    "PLN": ("PLN",), "PSN": ("PSN",), "PSA": ("PSA",), "PS": ("PS",), "PVN": ("PVN",),
    "PGD": ("PGD",), "RFE": ("RFE",), "SKN": ("SKNS", "SKN"), "SKU": ("SKU",),
    "SINN": ("SINN",), "VSPES": ("VSPES",), "ESTR": ("ESTR",), "REHJ": ("REHJ",),
    "VMM": ("VMM",), "VEM": ("VEM",), "STKN": ("STKN",), "TUSAK": ("TUSAK", "TUSAKENG"),
    "TGLA": ("TGLA",), "FLYKN": ("FLYKN",), "KOLLKN": ("KOLLKN",), "SJTKN": ("SJTKN",),
    "TLN": ("TLN",), "UNESV": ("UNESV",), "VVN": ("VVN",), "VPOD": ("VPOD",), "RAV": ("RAV",),
}

# Rundskriv (type rundskriv): the current base first, then the base for
# repealed ones. The departments' series letters (G, GI, R, H, I, …) are
# all in RDEP; IS- (Helsedirektoratet) is in ROO.
_RUNDSKRIV_PREFIXES = {
    "IS": ("ROO", "ROOO"), "RFT": ("RFT", "RFTO"), "RPOD": ("RPOD", "RPODO"),
    "RUDI": ("RUDI", "RUDIO"), "UNEPN": ("RUNE", "RUNEO"), "GI": ("RDEP", "RDEPO"),
}
_RDEP = ("RDEP", "RDEPO")

# Lovdata's reference: PREFIX-YYYY-N with an optional suffix (BVHN-2026-199-BRO,
# KT-2026-3V, OB-2024-4-1); the number can carry a letter (ADN-2026-D24673).
# A trailing "(23)" (ND's running number) is dropped.
_PREFIXED = re.compile(
    r"(?:rundskriv\s+)?([A-Za-z]{1,6}\d?)-(\d{4})-([A-Za-z]?)(\d+)((?:-?[A-Za-z0-9]+)*)(?:\s*\(\d+\))?", re.I)
# Departmental circulars as the ministries print them: G-01/2016, rundskriv R-5/2025.
_RUNDSKRIV_SLASH = re.compile(r"(?:rundskriv\s+)?([A-Za-z]{1,5})-0*(\d+)\s*/\s*(\d{4})", re.I)

# Reports cited by volume and page, like Rt./RG: ND 1990 s. 140, NAD 1984
# s. 123, ARD 1990 s. 123, Utv. 2017 s. 1057. The new Pro resolves
# avgjorelse/<nd-1990-140> to the judgment (several hits can share a page).
_REPORTERS = r"Rt|RG|ND|NAD|ARD|Utv"


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
    alt_slugs: tuple = ()
    note: str = ""

    @property
    def path(self):
        # No collection: Lovdata's short form (lov/2005-06-17-62), which the
        # new Pro resolves to the right base (NL, NLO, LTI …).
        if not self.collection:
            return f"{self.type}/{self.slug}"
        return f"{self.collection}/{self.type}/{self.slug}"

    @property
    def candidates(self):
        out = [self.path]
        for c in self.alt_collections:
            out.append(f"{c}/{self.type}/{self.slug}")
        for s in self.alt_slugs:
            out.append(f"{self.collection}/{self.type}/{s}")
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
        # ("Rt. 2000 p. 1811" in English text is the same citation.)
        if re.fullmatch(rf"({_REPORTERS})\.?\s*[-–]?\s*\d{{4}}", rest.strip(), re.I):
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
    m = re.match(rf"({_REPORTERS})\.?\s*[-–]?\s*(\d{{4}})\s*(?:s\.?|side|p\.?|page|[-–])\s*(\d+)", s, re.I)
    if m:
        rep = m.group(1).upper()
        rep = "Rt" if rep == "RT" else rep
        return f"{rep}-{m.group(2)}-{m.group(3)}"
    return s


_MONTHS = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

_LAW_NOTE = (
    "the law or regulation itself, current, repealed or (for an amending act) as "
    "published in Lovtidend; earlier versions: __lp.versions(path, {asOf}) on the "
    "new Lovdata Pro. Current text is also in lovdata-api")


def _parse_law(s):
    """(type, id) for LOV-/FOR- references and the prose forms; else None."""
    m = re.fullmatch(r"(LOV|FOR)-(\d{4}-\d{2}-\d{2})(?:-(\d+))?", s, re.I)
    if m:
        kind = "lov" if m.group(1).upper() == "LOV" else "forskrift"
        return kind, m.group(2) + (f"-{m.group(3)}" if m.group(3) else "")
    m = re.fullmatch(
        r"(lov(?:en)?|forskrift(?:en)?)\s+(?:av\s+)?(?:(\d{4}-\d{2}-\d{2})|(\d{1,2})\.\s*([a-zæøå]+)\s+(\d{4}))"
        r"(?:\s+nr\.?\s*(\d+))?", s, re.I)
    if m:
        kind = "lov" if m.group(1).lower().startswith("lov") else "forskrift"
        if m.group(2):
            date = m.group(2)
        else:
            month = _MONTHS.get(m.group(4).lower())
            if not month:
                return None
            date = f"{m.group(5)}-{month:02d}-{int(m.group(3)):02d}"
        return kind, date + (f"-{m.group(6)}" if m.group(6) else "")
    return None


def _parse_prefixed(s, ref_):
    """PREFIX-YYYY-N references of special courts, nemnder, uttalelser and
    rundskriv (see _AVG_PREFIXES); None for a prefix not in the tables."""
    m = _RUNDSKRIV_SLASH.fullmatch(s)
    if m:
        prefix, num, year = m.group(1).upper(), m.group(2), m.group(3)
        rest = ""
    else:
        m = _PREFIXED.fullmatch(s)
        if not m:
            return None
        prefix, year = m.group(1).upper(), m.group(2)
        # Lovdata's ids never pad the number (G-1958-0005 is g-1958-5).
        num = m.group(3) + (m.group(4).lstrip("0") or "0")
        rest = m.group(5)
    slug = f"{prefix.lower()}-{year}-{num.lower()}{rest.lower()}"
    if prefix in _AVG_PREFIXES and not m.re is _RUNDSKRIV_SLASH:
        bases = _AVG_PREFIXES[prefix]
        return ref_(bases[0], "avgjorelse", slug, alt_collections=bases[1:])
    if prefix.startswith("SKN") and re.fullmatch(r"SKN[AS]\d", prefix):
        # Skatteklagenemnda: the avdeling is in the prefix (SKNA2-, SKNS1-).
        return ref_("SKN", "avgjorelse", slug)
    if prefix in _RUNDSKRIV_PREFIXES:
        bases = _RUNDSKRIV_PREFIXES[prefix]
        return ref_(bases[0], "rundskriv", slug, alt_collections=bases[1:])
    if len(prefix) == 1:
        # Departmental series letter (G-2019-3, R-2025-9).
        return ref_(_RDEP[0], "rundskriv", slug, alt_collections=_RDEP[1:])
    if prefix != "JDLOV" and re.fullmatch(r"J[A-Z]{2,5}", prefix):
        # Jordskifte: JO<court> is a jordskifteoverrett (JOAG-), J<court> a
        # jordskifterett (JMOR-).
        base = "JSO" if prefix.startswith("JO") else "JSR"
        return ref_(base, "avgjorelse", slug)
    return None


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
    m = re.fullmatch(r"([A-Z0-9]+)/(avgjorelse|forarbeid|rundskriv|lov|forskrift|isl)/([a-z0-9\-*]+)", s_for_parse, re.I)
    if m:
        return ref_(m.group(1).upper(), m.group(2).lower(), m.group(3).lower())

    # Statsrådsforedrag: PRE-YYYY-MM-DD-N.
    m = re.fullmatch(r"PRE-(\d{4}-\d{2}-\d{2})-(\d+)", s_for_parse, re.I)
    if m:
        return ref_("PRE", "forarbeid", f"pre-{m.group(1)}-{m.group(2)}")

    # Laws and regulations: LOV-2005-06-17-62, FOR-2011-12-06-1360,
    # "lov 17. juni 2005 nr. 62", "forskrift 2011-12-06 nr. 1360". The
    # candidate is the short form lov|forskrift/<id>: the new Pro resolves it
    # to the consolidated text (NL, SF, LF), the repealed one (NLO, SFO, LFO)
    # or, for an amending act with no consolidated text, the Lovtidend item
    # (LTI). Laws without a number (1687, 1814) are just the date.
    law = _parse_law(s_for_parse)
    if law:
        kind, lid = law
        return ref_("", kind, lid, note=_LAW_NOTE)

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

    # Special courts, nemnder, uttalelser, rundskriv. Before the tingrett
    # rule: TRR- (Trygderetten), TLN-, TGLA-, TUSAK-, TUDEP- are not tingretter.
    r = _parse_prefixed(s_for_parse, ref_)
    if r:
        return r

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

    # Prop. N L|S|... (YYYY-YY)
    m = re.match(r"Prop\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"prop-{n}-{kind}-{sess}" if kind else f"prop-{n}-{sess}"
            return ref_("PROP", "forarbeid", slug)

    # Innst. O. nr. N / Innst. S. nr. N (YYYY-YY) — pre-2009 committee
    # recommendations. Same "inns-" rule as the post-2009 form, with the
    # chamber letter in place of the document kind. Confirmed against Pro.
    # Ot.meld. nr. N (YYYY-YY) — Odelstingsmeldinger, to 2006-07.
    m = re.match(r"Ot\.?\s*meld\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("OTMELD", "forarbeid", f"otmeld-{m.group(1)}-{sess}")

    # Besl. O. nr. N (YYYY-YY) and Lovvedtak N (YYYY-YY) — LOVVED.
    m = re.match(r"Besl\.?\s*O\.?\s*nr\.?\s*(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("LOVVED", "forarbeid", f"besl-o-{m.group(1)}-{sess}")
    m = re.match(r"Lovvedtak\s*(?:nr\.?\s*)?(\d+)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("LOVVED", "forarbeid", f"lovvedtak-{m.group(1)}-{sess}")

    # Innst. O./S. nr. N; the oldest ones are numbered in Roman numerals
    # (Innst. O. nr. VII (1898-99) is inns-o-vii-189899).
    m = re.match(r"Innst\.?\s*([OS])\.?\s*nr\.?\s*(\d+|[IVXLC]+\b)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(3))
        if sess:
            return ref_("INNST", "forarbeid",
                        f"inns-{m.group(1).lower()}-{m.group(2).lower()}-{sess}")

    # Innst. N L|S|... (YYYY-YY) - collection INNST, slug uses 'inns-'
    m = re.match(r"Innst\.?\s*(\d+)\s*([LSa-zA-Z]*)\s*\(([^)]+)\)", s, re.I)
    if m:
        n, kind, sess_raw = m.group(1), m.group(2).lower(), m.group(3)
        sess = _encode_session(sess_raw)
        if sess:
            slug = f"inns-{n}-{kind}-{sess}" if kind else f"inns-{n}-{sess}"
            return ref_("INNST", "forarbeid", slug)

    # Meld. St. N / St.meld. nr. N and St.prp. nr. N are handled by
    # search_hint(), not here: their slugs contain a Lovdata-assigned
    # sequence number that cannot be derived from the citation (see below).

    # Dok. 8:N (YYYY-YY) — private members' bills; REPFOR/forarbeid/dok8-N-YYYYYY
    # Confirmed against Pro.
    m = re.match(r"Dok(?:ument)?\.?\s*(?:nr\.?\s*)?8\s*:\s*(\d+)\s*([LS]?)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(3))
        if sess:
            kind = m.group(2).lower()
            if kind:
                # From 2009 the id is representantforslag-N-sess; the dok8
                # form with the letter resolves too (references).
                return ref_("REPFOR", "forarbeid", f"representantforslag-{m.group(1)}-{sess}",
                            alt_slugs=(f"dok8-{m.group(1)}-{kind}-{sess}",))
            return ref_("REPFOR", "forarbeid", f"dok8-{m.group(1)}-{sess}")

    # Representantforslag N S (YYYY-YY) — the same document as Dokument 8:N S.
    m = re.match(r"Representantforslag\s*(?:nr\.?\s*)?(\d+)\s*([LS]?)\s*\(([^)]+)\)", s, re.I)
    if m:
        sess = _encode_session(m.group(3))
        if sess:
            kind = m.group(2).lower()
            alts = (f"dok8-{m.group(1)}-{kind}-{sess}",) if kind else (f"dok8-{m.group(1)}-{sess}",)
            return ref_("REPFOR", "forarbeid", f"representantforslag-{m.group(1)}-{sess}", alt_slugs=alts)

    # Dokument 12:N / Grunnlovsforslag N (YYYY-YY) — GLFOR, id dok12-N-sess.
    m = (re.match(r"Dok(?:ument)?\.?\s*(?:nr\.?\s*)?12\s*:\s*(\d+)\s*\(([^)]+)\)", s, re.I)
         or re.match(r"Grunnlovsforslag\s*(?:nr\.?\s*)?(\d+)\s*\(([^)]+)\)", s, re.I))
    if m:
        sess = _encode_session(m.group(2))
        if sess:
            return ref_("GLFOR", "forarbeid", f"dok12-{m.group(1)}-{sess}")

    # Other Dokument series (Dokument 5 (2025-2026), Dokument nr. 7 (1972-73))
    # — SDOK, id dokN-sess. With a sub-number (Dokument 3:2) the id is assumed
    # to be dokN-M-sess (not yet seen in Pro).
    m = re.match(r"Dok(?:ument)?\.?\s*(?:nr\.?\s*)?(\d+)(?:\s*:\s*(\d+))?\s*\(([^)]+)\)", s, re.I)
    if m and m.group(1) not in ("8", "12"):
        sess = _encode_session(m.group(3))
        if sess:
            sub = f"-{m.group(2)}" if m.group(2) else ""
            return ref_("SDOK", "forarbeid", f"dok{m.group(1)}{sub}-{sess}", note=(
                "recent Stortingsdokumenter are often in Pro only as the original PDF: "
                "load() then answers metadataOnly with originalFile"))

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
        if parsed.note:
            out["note"] = parsed.note
        if parsed.type == "lov" and not parsed.collection:
            # Lovdata's register of the law's forarbeider (RFA).
            out["forarbeider"] = f"RFA/lov/{parsed.slug}"
    else:
        s, pin = split_pinpoint(ref.strip())
        if pin:
            out["pinpoint"] = pin
        out["search_hint"] = search_hint(ref)
        hint = out["search_hint"]
        if re.fullmatch(rf"({_REPORTERS})-\d{{4}}-\d+", hint, re.I):
            # The new Lovdata Pro resolves Lovdata's own short form (the form
            # its links use) to the underlying judgment: load() takes it.
            out["pro2_ref"] = f"avgjorelse/{hint.lower()}"
        elif (re.fullmatch(r"[A-Za-z]{1,6}\d?-\d{4}-[A-Za-z]?\d+(?:-?[A-Za-z0-9]+)*", hint)
              and not re.match(r"(LOV|FOR)-", hint, re.I)):
            # A Lovdata reference with a prefix not in the tables (older
            # names such as BKN-, LKN-, ENV-): the short form finds the base.
            out["pro2_ref"] = f"avgjorelse/{hint.lower()}"
        if re.match(r"(Meld\.?\s*St\.?|St\.?\s*meld\.?)", s, re.I):
            out["note"] = (
                "stortingsmeldinger live in STS/forarbeid/stsg-<sesjon>-<løpenummer> "
                "in Lovdata Pro Klassisk (e.g. Meld. St. 17 (2020-2021) is "
                "STS/forarbeid/stsg-202021-355). The løpenummer is assigned by Lovdata and "
                "cannot be derived from the citation — search for the search_hint in quotes (\"Meld. St. 17 (2020-2021)\"; unquoted, Klassisk returns only Prop./NOU hits) and verify "
                "the hit's title. The new Lovdata Pro (pro2) has no stortingsmeldinger "
                "(2026-11-11): use Klassisk")
        elif re.match(r"St\.?\s*prp\.?", s, re.I):
            out["note"] = (
                "non-law propositions (St.prp.) are not full-text indexed in Lovdata Pro "
                "— at most a header record with a PDF link, and a search may return "
                "nothing at all. Say so rather than quoting from elsewhere")
        elif "pro2_ref" in out:
            out["note"] = ("no deterministic path for this citation form: on the new Lovdata Pro "
                           "load the pro2_ref (if load() lists alternatives, several documents "
                           "share the reference: check the title); else search for the search_hint")
        else:
            out["note"] = ("no deterministic slug for this citation form (Rt./RG/other); "
                           "on the new Lovdata Pro load the pro2_ref if there is one, "
                           "else search Lovdata Pro for the search_hint and verify the hit")
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
