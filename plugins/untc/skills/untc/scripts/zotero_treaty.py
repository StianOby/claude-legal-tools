#!/usr/bin/env python3
"""
zotero_treaty.py — a Zotero-ready item for one UN treaty.

    python3 zotero_treaty.py <MTDSG ref or alias> --out DIR
    python3 zotero_treaty.py --objid <UNTS objid> --out DIR   # UNTS-only treaties

The MTDSG ref (IV-4, XXIII-1, XI-B-16-171) or an alias (ICCPR, UNCLOS) is for
treaties deposited with the UN Secretary-General; `--objid` (from `untc.py
lookup` / `unts-search`) for any other treaty registered in the UNTS (NPT,
Geneva Conventions, bilaterals). Writes into DIR:

    <base>.pdf          the English UNTS text (the treaty's own pages)
    <base>.rdf          Zotero RDF — drag into Zotero; the PDF must sit beside it
    <base>.zotero.json  the same item for Zoteus's zotero_create_items

The item is a Zotero `statute`, following the UNCLOS item in the shared group
library "Norsk henvisningsstandard for rettsvitenskapelige tekster -
eksempler":

    nameOfAct            title (the MTDSG index's form, not the capitals of
                         the status document)
    code / codeNumber /  "UNTS" / volume / first page; "LNTS" / volume for
      pages              League of Nations treaties
    dateEnacted          (definitive) entry into force; empty when not in force
    shortTitle           only a well-known abbreviation (SHORT_TITLES)
    history              "Parent treaty: <title> (MTDSG IV-9)" for protocols,
                         amendments, annexes and regulations
    url                  the treaty's page on treaties.un.org
    extra                type: treaty / available-date: <conclusion> /
                         provisional application / status / MTDSG / depositary /
                         UN registration no. (with its series: I-, II-, A-, LoN-)

A missing PDF is reported with a line starting "PDF NOT ATTACHED:"; a field
the sources could not supply with a line starting "NOTE:".
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import untc         # noqa: E402  (after sys.path mutation)
import zotero_rdf   # noqa: E402

# Short titles only where one is established (cf. untc.ALIASES).
SHORT_TITLES = {
    "IV-1": "Genocide Convention",
    "IV-2": "ICERD",
    "IV-3": "ICESCR",
    "IV-4": "ICCPR",
    "IV-8": "CEDAW",
    "IV-9": "CAT",
    "IV-9-b": "OPCAT",
    "IV-11": "CRC",
    "IV-13": "ICRMW",
    "IV-15": "CRPD",
    "IV-16": "ICPPED",
    "V-2": "Refugee Convention",
    "III-3": "VCDR",
    "III-6": "VCCR",
    "XVIII-10": "Rome Statute",
    "XVIII-12": "UNTOC",
    "XVIII-14": "UNCAC",
    "XXI-6": "UNCLOS",
    "XXIII-1": "VCLT",
    "XXVI-4": "CTBT",
    "XXVI-5": "Ottawa Convention",
    "XXVI-8": "ATT",
    "XXVI-9": "TPNW",
    "XXVII-7": "UNFCCC",
    "XXVII-7-a": "Kyoto Protocol",
    "XXVII-7-d": "Paris Agreement",
    "XXVII-8": "CBD",
}
UNTS_SHORT_TITLES = {"I-10485": "NPT"}

SG = "Secretary-General of the United Nations"
_DATE = r"\d{1,2} [A-Z][a-z]+ \d{4}"
_DEPOSITED = re.compile(r"\s*\(deposited in the archives of the (Government of [^)]+)\)\s*$")
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def iso(date: str) -> str:
    """'23 May 1969' or '23/05/1969' -> '1969-05-23'; '' if neither."""
    m = re.fullmatch(r"(\d{1,2}) ([A-Z][a-z]+) (\d{4})", date.strip())
    if m and m.group(2) in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", date.strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def parse_eif(text: Optional[str]) -> dict:
    """The entry-into-force field of a status document or UNTS record.

    {"date": definitive entry into force or "", "provisional": date or "",
     "readable": False when there is text but no date could be read from it}.
    "provisionally on 1 January 1978 … and definitively on 2 January 1980"
    gives both; a leading date is the entry into force; anything else (a
    text starting ". The Agreement was extended …") is not guessed at."""
    text = (text or "").strip()
    if not text or text == "None":
        return {"date": "", "provisional": "", "readable": True}
    prov = re.match(rf"provisionally on ({_DATE})", text)
    if prov:
        defin = re.search(rf"definitively on ({_DATE})", text)
        return {"date": iso(defin.group(1)) if defin else "",
                "provisional": iso(prov.group(1)), "readable": True}
    lead = re.match(rf"({_DATE})", text)
    if lead:
        return {"date": iso(lead.group(1)), "provisional": "", "readable": True}
    return {"date": "", "provisional": "", "readable": False}


def clean_title(title: str) -> tuple:
    """(title, depositary) from an MTDSG index title: the footnote mark of
    "International Sugar Agreement, 1977*" goes, and "(deposited in the
    archives of the Government of …)" becomes the depositary."""
    title = re.sub(r"\s*\*+$", "", " ".join(title.split()))
    m = _DEPOSITED.search(title)
    if m:
        return title[:m.start()], m.group(1)
    return title, SG


def parent_ref(ref: str, index: dict) -> Optional[str]:
    """IV-9-b -> IV-9, XI-B-16-171 -> XI-B-16, III-2-1 -> III-2; None for a
    treaty with no parent in the index."""
    parts = ref.split("-")
    while len(parts) > 2:
        parts = parts[:-1]
        cand = "-".join(parts)
        if cand in index:
            return cand
    return None


def _series_from_pdfs(pdfs) -> Optional[str]:
    """'volume-75-I-970-English.pdf' -> 'I', '/LON/' -> 'LoN', 'A-33941-…' -> 'A'."""
    for p in pdfs or []:
        if "/LON/" in p:
            return "LoN"
        m = re.search(r"volume-\d+-(I|II)-\d+-", p) or re.search(r"/(A|I|II)-\d+-[0-9a-f]+\.pdf", p)
        if m:
            return m.group(1)
    return None


def _lnts_volume(pdfs) -> Optional[int]:
    for p in pdfs or []:
        m = re.search(r"/LON/Volume%20(\d+)/", p)
        if m:
            return int(m.group(1))
    return None


def unts_record(title: str, reg: Optional[str]) -> Optional[dict]:
    """The UNTS Online row for an MTDSG treaty: the registration number with
    its series ("I-18232", "LoN-11", "A-4789") and the objid. Matched on the
    number when the status document gives one, else on the exact title."""
    try:
        _, _, rows = untc.unts_find(title, limit=10)
    except Exception as e:   # the site being down must not stop the item
        print(f"NOTE: UNTS search failed ({e}); registration series not checked", file=sys.stderr)
        return None
    key = untc._title_key(html.unescape(title))
    for r in rows:
        num = r["reg"].split("-")[-1]
        if (reg and num == str(reg)) or (not reg and untc._title_key(html.unescape(r["title"])) == key):
            return r
    return None


def build_item(*, title, conclusion, eif_text, registered, reg_full, depositary,
               volume, page, lnts_volume, url, ref=None, parent=None,
               short_title=None, today="") -> tuple:
    """The Zotero item, plus the NOTE lines for fields the sources lacked."""
    today = today or _dt.date.today().isoformat()
    notes = []
    eif = parse_eif(eif_text)
    extra = ["type: treaty"]
    if conclusion:
        extra.append(f"available-date: {conclusion}")
    if eif["provisional"]:
        extra.append(f"provisional application: {eif['provisional']}")
    if not eif["date"]:
        if eif["provisional"]:
            extra.append(f"status: provisionally applied, not definitively in force (as of {today})")
        elif not eif["readable"]:
            notes.append("the entry-into-force date could not be read from the source; "
                         f"check {url} and add it by hand")
        elif registered:
            # Registered (so in force) but no date given, e.g. the annexes of III-2.
            notes.append(f"no entry-into-force date in the source; check {url}")
        else:
            extra.append(f"status: not in force (as of {today})")
    if ref:
        extra.append(f"MTDSG: {ref}")
    if depositary:
        extra.append(f"depositary: {depositary}")
    if reg_full:
        if reg_full.startswith("LoN-"):
            extra.append(f"League of Nations registration no.: {reg_full[4:]}")
        else:
            extra.append(f"UN registration no.: {reg_full}")

    item = {"itemType": "statute", "nameOfAct": title}
    if volume:
        item["code"] = "UNTS"
        item["codeNumber"] = str(volume)
        if page:
            item["pages"] = str(page)
        else:
            notes.append(f"UNTS vol. {volume} has no page for this treaty yet")
    elif lnts_volume:
        item["code"] = "LNTS"
        item["codeNumber"] = str(lnts_volume)
        notes.append(f"LNTS vol. {lnts_volume}: the first page is not in the UN's records; "
                     "add it by hand if you cite the page")
    elif registered or reg_full:
        notes.append("no UNTS volume/page for this treaty yet")
    if eif["date"]:
        item["dateEnacted"] = eif["date"]
    if short_title:
        item["shortTitle"] = short_title
    if parent:
        item["history"] = f"Parent treaty: {parent[1]} (MTDSG {parent[0]})"
    item["url"] = url
    item["language"] = "English"
    item["extra"] = "\n".join(extra)
    return item, notes


def item_for_ref(ref_slug: str, today: str = "") -> tuple:
    """(item, notes, text source) for an MTDSG treaty."""
    ref = untc.MTDSGRef.parse(ref_slug)
    meta = untc.fetch_status(ref)
    index = {e["ref"]: e for e in untc.load_index()["treaties"]}
    entry = index.get(ref.slug, {})
    title, depositary = clean_title(entry.get("title") or meta.get("title") or "")
    concluded = iso(meta.get("date") or "")
    if not concluded:   # the vehicle regulations' status documents have no date
        dm = re.search(rf"{_DATE}$", entry.get("place_date") or "")
        concluded = iso(dm.group()) if dm else ""
    reg = meta.get("registration_number")
    row = unts_record(title, reg)
    reg_full = row["reg"] if row and row["reg"] != "N/A" else (reg and str(reg))
    lnts, lnts_pdf = None, None
    if row and row["reg"].startswith("LoN-") and not meta.get("unts_volume"):
        pdfs = untc.unts_details(row["objid"]).get("text_pdfs")
        lnts = _lnts_volume(pdfs)
        lnts_pdf = next((x for x in pdfs or [] if "/LON/" in x), None)
    p = parent_ref(ref.slug, index)
    item, notes = build_item(
        title=title, conclusion=concluded, eif_text=meta.get("entry_into_force"),
        registered=bool(reg), reg_full=reg_full, depositary=depositary,
        volume=meta.get("unts_volume"), page=meta.get("unts_page"), lnts_volume=lnts,
        url=meta.get("details_url"), ref=ref.slug,
        parent=(p, " ".join(index[p]["title"].split())) if p else None,
        short_title=SHORT_TITLES.get(ref.slug), today=today)
    return item, notes, {"ref": ref, "row": row if row and row["reg"] != "N/A" else None,
                         "registered": bool(reg), "lnts_pdf": lnts_pdf,
                         "details_url": meta.get("details_url")}


def item_for_objid(objid: str, today: str = "") -> tuple:
    """(item, notes, text source) for a treaty registered in the UNTS only."""
    d = untc.unts_details(objid)
    if d.get("mtdsg"):
        raise SystemExit("this treaty is deposited with the UN Secretary-General: find its MTDSG ref "
                         "with `untc.py lookup \"<title>\"` and run zotero_treaty.py <ref>")
    series = _series_from_pdfs(d.get("text_pdfs"))
    reg = d.get("registration_number")
    reg_full = f"{series}-{reg}" if series and reg else reg
    dates = re.findall(r"\d{2}/\d{2}/\d{4}", d.get("conclusion") or "")
    depositary = "; ".join(x.strip() for x in (d.get("depositary") or "").split("|") if x.strip())
    item, notes = build_item(
        title=" ".join(html.unescape(d.get("title") or "").split()),
        conclusion=iso(dates[0]) if dates else "",
        eif_text=d.get("entry_into_force"), registered=True, reg_full=reg_full,
        depositary=depositary or None, volume=d.get("unts_volume"), page=d.get("unts_page"),
        lnts_volume=_lnts_volume(d.get("text_pdfs")) if series == "LoN" else None,
        url=d["details_url"], short_title=UNTS_SHORT_TITLES.get(reg_full), today=today)
    return item, notes, {"details": d}


def _slice(volume_pdf: Path, first: int, last: int, dest: Path) -> None:
    """Pages first..last (1-based, inclusive) of a volume PDF into dest."""
    from pypdf import PdfReader, PdfWriter
    reader, writer = PdfReader(str(volume_pdf)), PdfWriter()
    for i in range(first - 1, last):
        writer.add_page(reader.pages[i])
    with open(dest, "wb") as f:
        writer.write(f)


def _own_text_pdf(d: dict, dest: Path) -> Optional[str]:
    """A UNTS record's own English text file (or, for records with no volume
    yet, its single "No Volume" file) at dest; its URL, or None."""
    pdfs = d.get("text_pdfs") or []
    own = next((p for p in pdfs if p.endswith("-English.pdf")), None) \
        or next((p for p in pdfs if "/No%20Volume/" in p), None)
    if own:
        try:
            untc.download_pdf(own, dest)
            return own
        except Exception:
            return None
    return None


def fetch_pdf(source: dict, item: dict, dest: Path) -> tuple:
    """Put the English text at dest. Returns (public PDF URL or None, reason
    the PDF is missing or None). The reasons are for the user."""
    where = source.get("details_url") or item["url"]
    try:
        if "ref" in source:
            if source.get("lnts_pdf"):
                return None, ("League of Nations treaties have no UNTS text; the League of Nations "
                              f"Treaty Series volume is at {source['lnts_pdf']}")
            if not source.get("registered"):
                return None, ("the treaty is not registered in the UNTS yet (that happens once it is "
                              f"in force); the certified true copy is linked from {where}")
            try:
                info = untc.fetch_text(source["ref"])
            except SystemExit:
                # Treaties recorded under a parent (the vehicle regulations,
                # A-4789) have no volume of their own, but their UNTS record
                # often links the text.
                if source.get("row"):
                    url = _own_text_pdf(untc.unts_details(source["row"]["objid"]), dest)
                    if url:
                        return url, None
                raise
        else:
            d = source["details"]
            url = _own_text_pdf(d, dest)
            if url:
                return url, None
            if not (d.get("unts_volume") and d.get("unts_page")):
                return None, "the UN has published no English text file for this treaty"
            info = untc.fetch_text(volume=d["unts_volume"], page=d["unts_page"])
    except SystemExit as e:
        msg = " ".join(str(e).split())
        vol = re.search(r"UNTS volume (\d+) is not published", msg)
        if vol:
            return None, (f"UNTS vol. {vol.group(1)} is not published on treaties.un.org yet; "
                          f"the certified true copy is linked from {where}")
        return None, f"no UNTS text file was found for it (see {where})"
    if info.get("via") == "treaty-pdf":
        shutil.copyfile(info["text_pdf"], dest)
        return info["source_url"], None
    first, last = info["pdf_pages"]
    try:
        _slice(Path(info["text_pdf"]), first, last, dest)
    except ImportError:
        return None, ("the text is only in the whole UNTS volume PDF and pypdf, which cuts out "
                      f"the treaty's pages, is not installed: pages {first}-{last} of "
                      f"{info['source_url']}")
    print(f"[pdf] pages {first}-{last} of the UNTS volume PDF {info['source_url']} "
          "(every authentic language in sequence)")
    return None, None


def basename(item: dict) -> str:
    """UNTS_1155_331_VCLT, LNTS_1_International_Agreement_…, Treaty_on_…"""
    label = item.get("shortTitle") or item["nameOfAct"]
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    if len(s) > 60:   # cut at a word, not inside one
        s = s[:61].rsplit("_", 1)[0]
    cite = "_".join(item[k] for k in ("code", "codeNumber", "pages") if item.get(k))
    return f"{cite}_{s}" if cite else s


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("ref", nargs="?", help="MTDSG ref (IV-4) or alias (ICCPR)")
    ap.add_argument("--objid", help="UNTS objid of a treaty not deposited with the Secretary-General")
    ap.add_argument("--out", required=True, help="Folder for the .pdf + .rdf pair.")
    args = ap.parse_args(argv)
    if bool(args.ref) == bool(args.objid):
        ap.error("give an MTDSG ref/alias or --objid, not both")

    if args.objid:
        item, notes, source = item_for_objid(args.objid)
    else:
        ref = untc.ALIASES.get(args.ref.strip().lower(), args.ref)
        if not untc.looks_like_ref(ref):
            raise SystemExit(f"{args.ref!r} is not an MTDSG ref or alias: run `untc.py lookup "
                             f"{args.ref!r}` and pass the ref (or --objid for a UNTS-only treaty)")
        item, notes, source = item_for_ref(ref)
    base = basename(item)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cite = " ".join(item[k] for k in ("codeNumber", "code", "pages") if item.get(k))
    print(f"[meta] {item['nameOfAct']}" + (f" ({cite})" if cite else ""))
    print(f"[meta] entry into force: {item.get('dateEnacted') or 'none recorded'}")

    pdf_name = f"{base}.pdf"
    pdf_url, missing = fetch_pdf(source, item, out_dir / pdf_name)
    if missing or not (out_dir / pdf_name).exists():
        pdf_name = None
    for n in notes:
        print(f"NOTE: {n}")
    zotero_rdf.write_zotero_files(item, out_dir, base, pdf_filename=pdf_name,
                                  missing_reason=missing or "no text was found",
                                  item_id=re.sub(r"[^a-z0-9_]", "_", base.lower()),
                                  pdf_url=pdf_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
