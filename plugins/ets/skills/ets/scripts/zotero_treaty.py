#!/usr/bin/env python3
"""
zotero_treaty.py — a Zotero-ready item for one Council of Europe treaty.

    python3 zotero_treaty.py <ref> --out DIR

<ref> is anything coe.py accepts (5, 005, ECHR, "CETS 210", a title). Writes
into DIR:

    <base>.pdf          the English treaty text from rm.coe.int
    <base>.rdf          Zotero RDF — drag into Zotero; the PDF must sit beside it
    <base>.zotero.json  the same item for Zoteus's zotero_create_items

The item is a Zotero `statute`, following the ECHR item in the shared group
library "Norsk henvisningsstandard for rettsvitenskapelige tekster -
eksempler":

    nameOfAct        English title without "(ETS No. 005)" / "(*)"
    publicLawNumber  "ETS No. 5" (1-193) / "CETS No. 210" (194 on); no zeros
    dateEnacted      entry into force; empty when not in force
    shortTitle       only a well-known abbreviation (SHORT_TITLES)
    history          "Parent treaty: ETS No. 5" for protocols
    url              the treaty's page on coe.int
    extra            type: treaty / available-date: <opening for signature>
                     / status: not in force (as of <today>) / UN registration no.

Exit 0 when the PDF is attached; the RDF is written either way, and a missing
PDF is reported with a line starting "PDF NOT ATTACHED:".
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import coe          # noqa: E402  (after sys.path mutation)
import zotero_rdf   # noqa: E402

# Short titles only where one is established; the Treaty Office's own
# "common names" are descriptions ("Tax Matters", "Abolition of death
# penalty"), not abbreviations, so they are not used.
SHORT_TITLES = {
    "005": "ECHR",
    "104": "Bern Convention",
    "108": "Convention 108",
    "126": "ECPT",
    "143": "Valletta Convention",
    "157": "FCNM",
    "164": "Oviedo Convention",
    "185": "Budapest Convention",
    "199": "Faro Convention",
    "201": "Lanzarote Convention",
    "210": "Istanbul Convention",
    "211": "MEDICRIME Convention",
    "215": "Macolin Convention",
    "218": "Saint-Denis Convention",
    "223": "Convention 108+",
}

# "(ETS No. 005)", "(CETS No. 210)", "(CETS No 231)", "(CETS 230)", each
# possibly followed by "(*)", the mark of an amending protocol whose text
# has been integrated into its parent treaty.
_TITLE_TAIL = re.compile(r"\s*\((?:C?ETS)(?:\s+No\.?)?\s+\d+[A-Z]?\)(?:\s*\(\*\))?\s*$")


def treaty_number(num: str) -> str:
    """"005" -> "ETS No. 5", "012A" -> "ETS No. 12A", "210" -> "CETS No. 210".
    The series was renamed CETS from no. 194 (2004)."""
    m = re.fullmatch(r"0*(\d+)([A-Z]?)", num)
    n, letter = int(m.group(1)), m.group(2)
    return f"{'CETS' if n >= 194 else 'ETS'} No. {n}{letter}"


def clean_title(title: str) -> str:
    return _TITLE_TAIL.sub("", " ".join(title.split()))


def detail_url(num: str) -> str:
    return ("https://www.coe.int/en/web/conventions/full-list"
            f"?module=treaty-detail&treatynum={num}")


def treaty_to_item(t: dict, today: str = "") -> dict:
    """The Zotero item for one record of the Treaty Office index."""
    num = t["Numero_traite"]
    today = today or _dt.date.today().isoformat()
    extra = ["type: treaty"]
    if t.get("Date_ste"):
        extra.append(f"available-date: {t['Date_ste'][:10]}")
    if not t.get("Date_vigueur_ste"):
        extra.append(f"status: not in force (as of {today})")
    if t.get("Numero_enreg_onu"):
        # A protocol is recorded under its parent's UN registration.
        extra.append(f"UN registration no.: {t['Numero_enreg_onu']}")
    item = {
        "itemType": "statute",
        "nameOfAct": clean_title(t["Libelle_titre_ENG"]),
        "publicLawNumber": treaty_number(num),
    }
    if t.get("Date_vigueur_ste"):
        item["dateEnacted"] = t["Date_vigueur_ste"][:10]
    if num in SHORT_TITLES:
        item["shortTitle"] = SHORT_TITLES[num]
    if t.get("Numero_traite_parent"):
        history = f"Parent treaty: {treaty_number(t['Numero_traite_parent'])}"
        if t.get("Code_integration") == 1:
            history += " (this amending protocol is integrated into it)"
        item["history"] = history
    item["url"] = detail_url(num)
    item["language"] = "English"
    item["extra"] = "\n".join(extra)
    return item


def basename(item: dict) -> str:
    """ETS_5_ECHR, CETS_210_Istanbul_Convention, ETS_61B_Protocol_to_…"""
    label = item.get("shortTitle") or item["nameOfAct"]
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9+]+", "_", s).strip("_")
    if len(s) > 60:   # cut at a word, not inside one
        s = s[:61].rsplit("_", 1)[0]
    return item["publicLawNumber"].replace(" No. ", "_") + "_" + s.replace("+", "plus")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("ref", help="CETS number or name (005, ECHR, 'Istanbul Convention')")
    ap.add_argument("--out", required=True, help="Folder for the .pdf + .rdf pair.")
    args = ap.parse_args(argv)

    try:
        ref, t = coe.resolve_treaty(args.ref)
    except coe.ServiceUnavailable as e:
        print(f"TREATY OFFICE DATA SERVICE UNAVAILABLE: {e.url} {e.detail}.", file=sys.stderr)
        return 7
    item = treaty_to_item(t)
    base = basename(item)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[meta] {item['publicLawNumber']}: {item['nameOfAct']}")
    print(f"[meta] entry into force: {item.get('dateEnacted') or 'not in force'}")

    pdf_name, pdf_url, missing = None, None, "no English treaty PDF in the Treaty Office index"
    url, lang = coe._pick_url(t, "traite", "en")
    if url and lang == "en":
        pdf_url = url
        try:
            doc, kind = coe.download_document(url, coe.treaty_dir(ref) / "text.en")
        except (OSError, SystemExit) as e:
            doc, kind = None, None
            missing = f"the treaty PDF could not be downloaded ({e})"
        if kind == "pdf":
            pdf_name = f"{base}.pdf"
            shutil.copyfile(doc, out_dir / pdf_name)
            print(f"[pdf] {out_dir / pdf_name}")
        elif kind:
            missing = "the Treaty Office serves this text as a web page, not a PDF"

    zotero_rdf.write_zotero_files(item, out_dir, base, pdf_filename=pdf_name,
                                  missing_reason=missing, item_id=base.lower(),
                                  pdf_url=pdf_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
