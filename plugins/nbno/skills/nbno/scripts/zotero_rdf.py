#!/usr/bin/env python3
"""
zotero_rdf.py — turn one Zotero item (Zotero's own JSON) into a Zotero RDF
file, with an optional PDF and Web Link attachment.

Shared by the skills that make "Zotero-ready" output. The canonical copy is
shared/zotero-rdf/zotero_rdf.py; plugins carry copies (check-shared.py).

The item is the JSON Zotero itself uses: the Web API's `data` object, the
group library's `format=json` export, and what Zoteus's `zotero_create_items`
takes, e.g.

    {"itemType": "case", "caseName": "HR-2016-2554-P (Holship …)",
     "court": "Norges Høyesterett", "dateDecided": "2016-12-16",
     "creators": [{"creatorType": "author", "name": "Høyesterett"}]}

So one record serves both routes: drag the .rdf into Zotero, or pass the item
to Zoteus. The RDF follows Zotero's own "Zotero RDF" export translator
(zotero/translators, `Zotero RDF.js`): type-specific fields are written under
their base field (caseName -> dc:title, docketNumber -> prism:number, court
-> z:authority …), the reporter/volume/number of a case go in its
bib:CourtReporter, creators other than author/editor/contributor go under
z:<type>s, and identifiers such as ISBN are plain "ISBN …" literals.

Library use:

    from zotero_rdf import build_rdf, write_zotero_files
    rdf = build_rdf(item, pdf_filename="X.pdf",
                    link_url="https://…", link_title="eBok (nb.no)")

CLI (edit an item JSON by hand, then re-render):

    python zotero_rdf.py --item-json X.zotero.json --out X.rdf \\
        [--pdf-filename X.pdf] [--link-url URL --link-title TITLE]

When no PDF goes into the RDF, a line starting `PDF NOT ATTACHED:` is
printed; the skill tells the user to add the PDF in Zotero by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as _xml_escape

SUPPORTED_TYPES = ("book", "case", "statute", "bill")

# Type-specific field -> the base field Zotero's export writes it under.
# From the Zotero schema; only the four supported types.
BASE_FIELDS: Dict[str, Dict[str, str]] = {
    "case": {
        "caseName": "title",
        "court": "authority",
        "dateDecided": "date",
        "docketNumber": "number",
        "reporterVolume": "volume",
        "firstPage": "pages",
    },
    "statute": {
        "nameOfAct": "title",
        "dateEnacted": "date",
        "publicLawNumber": "number",
    },
    "bill": {
        "billNumber": "number",
        "codeVolume": "volume",
        "codePages": "pages",
        "legislativeBody": "authority",
    },
    "book": {},
}

# Fields that go on the container (bib:CourtReporter for a case) when the
# type has one, as in the export translator.
_CONTAINER_TYPES = {"case": "bib:CourtReporter"}
_RESOURCE_TYPES = {"book": "bib:Book", "case": "bib:Document",
                   "statute": "bib:Legislation", "bill": "bib:Legislation"}
# Fields the API JSON carries that are not bibliographic data.
_SKIP = {"key", "version", "itemType", "creators", "tags", "collections",
         "relations", "dateAdded", "dateModified", "parentItem", "deleted"}
_BIBLIO_CREATORS = ("author", "editor", "contributor")

RDF_HEAD = """\
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
 xmlns:z="http://www.zotero.org/namespaces/export#"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:bib="http://purl.org/net/biblio#"
 xmlns:foaf="http://xmlns.com/foaf/0.1/"
 xmlns:link="http://purl.org/rss/1.0/modules/link/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:vcard="http://nwalsh.com/rdf/vCard#"
 xmlns:prism="http://prismstandard.org/namespaces/1.2/basic/"
 xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
"""
RDF_TAIL = "</rdf:RDF>\n"


def _esc(s: str) -> str:
    """XML-escape an element's text."""
    return _xml_escape(str(s).strip(), {'"': "&quot;"})


def _esc_attr(s: str) -> str:
    """XML-escape an attribute value."""
    return _xml_escape(str(s), {'"': "&quot;", "'": "&apos;"})


def _el(tag: str, value: str) -> str:
    return f"<{tag}>{_esc(value)}</{tag}>"


def base_fields(item: dict) -> Dict[str, str]:
    """The item's non-empty fields keyed by base field name, in item order."""
    itype = item.get("itemType", "")
    if itype not in SUPPORTED_TYPES:
        raise ValueError(f"itemType {itype!r} is not supported "
                         f"(supported: {', '.join(SUPPORTED_TYPES)})")
    mapping = BASE_FIELDS[itype]
    out: Dict[str, str] = {}
    for field, value in item.items():
        if field in _SKIP or value in (None, ""):
            continue
        out[mapping.get(field, field)] = str(value)
    return out


def _person(c: dict) -> str:
    """foaf:Person as the export writes it. A single-field name ("name")
    becomes a surname with no given name, which the importer reads back as
    a single-field creator (fieldMode 1)."""
    surname = c.get("lastName") or c.get("name") or ""
    given = c.get("firstName") or ""
    parts = ["<foaf:Person>", _el("foaf:surname", surname)]
    if given:
        parts.append(_el("foaf:givenName", given))
    parts.append("</foaf:Person>")
    return "".join(parts)


def _creators(creators: List[dict]) -> List[str]:
    """One rdf:Seq per creator type, in order of first appearance."""
    groups: Dict[str, List[dict]] = {}
    for c in creators or []:
        if c.get("lastName") or c.get("name") or c.get("firstName"):
            groups.setdefault(c.get("creatorType") or "author", []).append(c)
    out = []
    for ctype, group in groups.items():
        tag = f"bib:{ctype}s" if ctype in _BIBLIO_CREATORS else f"z:{ctype}s"
        lis = "".join(f"<rdf:li>{_person(c)}</rdf:li>" for c in group)
        out.append(f"<{tag}><rdf:Seq>{lis}</rdf:Seq></{tag}>")
    return out


def _uri(value: str) -> str:
    return ("<dc:identifier><dcterms:URI>"
            f"{_el('rdf:value', value)}"
            "</dcterms:URI></dc:identifier>")


def _item_body(itype: str, f: Dict[str, str]) -> List[str]:
    """Elements for the item's own fields, following the export translator."""
    container_tag = _CONTAINER_TYPES.get(itype)
    container: List[str] = []
    series: List[str] = []
    publisher: List[str] = []
    body: List[str] = []
    # The container (case: bib:CourtReporter) takes these; without one they
    # go on the item itself.
    to_container = container if container_tag else body
    for prop, value in f.items():
        if prop == "title":
            body.append(_el("dc:title", value))
        elif prop == "url":
            body.append(_uri(value))
        elif prop == "rights":
            body.append(_el("dc:rights", value))
        elif prop in ("edition", "version"):
            body.append(_el("prism:edition", value))
        elif prop == "date":
            body.append(_el("dc:date", value))
        elif prop == "accessDate":
            body.append(_el("dcterms:dateSubmitted", value))
        elif prop == "pages":
            body.append(_el("bib:pages", value))
        elif prop == "extra":
            body.append(_el("dc:description", value))
        elif prop in ("ISBN", "ISSN", "DOI"):
            to_container.append(_el("dc:identifier", f"{prop} {value}"))
        elif prop in ("publicationTitle", "reporter"):
            to_container.append(_el("dc:title", value))
        elif prop == "volume":
            to_container.append(_el("prism:volume", value))
        elif prop in ("issue", "number"):
            to_container.append(_el("prism:number", value))
        elif prop == "callNumber":
            body.append("<dc:subject><dcterms:LCC>"
                        f"{_el('rdf:value', value)}</dcterms:LCC></dc:subject>")
        elif prop == "abstractNote":
            body.append(_el("dcterms:abstract", value))
        elif prop == "series":
            series.append(_el("dc:title", value))
        elif prop == "seriesTitle":
            series.append(_el("dcterms:alternative", value))
        elif prop == "seriesText":
            series.append(_el("dc:description", value))
        elif prop == "seriesNumber":
            series.append(_el("dc:identifier", value))
        elif prop == "publisher":
            publisher.append(_el("foaf:name", value))
        elif prop == "place":
            publisher.insert(0, "<vcard:adr><vcard:Address>"
                             f"{_el('vcard:locality', value)}"
                             "</vcard:Address></vcard:adr>")
        elif prop == "archiveLocation":
            body.append(_el("dc:coverage", value))
        elif prop == "section":
            body.append("<dcterms:isPartOf><bib:Part>"
                        f"{_el('dc:title', value)}</bib:Part></dcterms:isPartOf>")
        else:
            body.append(_el(f"z:{prop}", value))
    head: List[str] = []
    if series:
        series_xml = ("<dcterms:isPartOf><bib:Series>" + "".join(series)
                      + "</bib:Series></dcterms:isPartOf>")
        # The translator hangs the series off the container when there is one.
        (container if container_tag else head).append(series_xml)
    if container_tag and container:
        head.append(f"<dcterms:isPartOf><{container_tag}>" + "".join(container)
                    + f"</{container_tag}></dcterms:isPartOf>")
    if publisher:
        head.append("<dc:publisher><foaf:Organization>" + "".join(publisher)
                    + "</foaf:Organization></dc:publisher>")
    return head + body


def _pdf_attachment(about: str, filename: str) -> str:
    """Imported-file attachment (linkMode 1), path relative to the .rdf."""
    return (
        f'<z:Attachment rdf:about="{_esc_attr(about)}">\n'
        "  <z:itemType>attachment</z:itemType>\n"
        f'  <rdf:resource rdf:resource="{_esc_attr(filename)}"/>\n'
        f"  {_el('dc:title', filename)}\n"
        "  <z:linkMode>1</z:linkMode>\n"
        "  <link:type>application/pdf</link:type>\n"
        f"  {_el('prism:fileName', filename)}\n"
        "</z:Attachment>"
    )


def _link_attachment(url: str, title: str) -> str:
    """Web Link attachment (linkMode 3, Zotero's "linked URL")."""
    return (
        f'<z:Attachment rdf:about="{_esc_attr(url)}">\n'
        "  <z:itemType>attachment</z:itemType>\n"
        f'  <rdf:resource rdf:resource="{_esc_attr(url)}"/>\n'
        f"  {_el('dc:title', title)}\n"
        "  <z:linkMode>3</z:linkMode>\n"
        "  <link:type>text/html</link:type>\n"
        "</z:Attachment>"
    )


def build_rdf(item: dict, pdf_filename: Optional[str] = None,
              link_url: Optional[str] = None, link_title: Optional[str] = None,
              item_id: str = "item_1") -> str:
    """Render one item, and its attachments, as a Zotero RDF document.

    pdf_filename: the PDF's bare filename; it must sit next to the .rdf at
        import time. None leaves the PDF out (the caller reports that).
    link_url / link_title: a Web Link attachment, e.g. the source's page.
    """
    itype = item.get("itemType", "")
    f = base_fields(item)
    about = f.get("url") or f"#{item_id}"
    parts = [RDF_HEAD,
             f'<{_RESOURCE_TYPES[itype]} rdf:about="{_esc_attr(about)}">',
             f"  {_el('z:itemType', itype)}"]
    parts += ["  " + x for x in _creators(item.get("creators") or [])]
    parts += ["  " + x for x in _item_body(itype, f)]
    attachments = []
    if pdf_filename:
        attachments.append((pdf_filename, _pdf_attachment(pdf_filename, pdf_filename)))
    if link_url:
        attachments.append((link_url, _link_attachment(link_url, link_title or link_url)))
    parts += [f'  <link:link rdf:resource="{_esc_attr(a)}"/>' for a, _ in attachments]
    parts.append(f"</{_RESOURCE_TYPES[itype]}>")
    parts += [xml for _, xml in attachments]
    parts.append(RDF_TAIL)
    return "\n".join(parts)


def pdf_missing_notice(reason: str, where: Optional[str] = None) -> str:
    """The fixed line the skills pass on to the user."""
    line = f"PDF NOT ATTACHED: {reason}."
    if where:
        line += f" The PDF is at {where}."
    return (line + " Add it in Zotero by hand: drag the PDF onto the item, or"
            " right-click the item > Add Attachment > Attach Stored Copy of File.")


def zoteus_payload(item: dict, pdf_filename: Optional[str] = None,
                   link_url: Optional[str] = None,
                   link_title: Optional[str] = None) -> dict:
    """What the Zoteus route needs: `items` goes to zotero_create_items as
    is; `web_link` is created as a child once the parent's key is known
    (set its parentItem); `pdf` names the file for zotero_attach_file."""
    payload: dict = {"items": [item]}
    if link_url:
        payload["web_link"] = {"itemType": "attachment", "linkMode": "linked_url",
                               "title": link_title or link_url, "url": link_url,
                               "parentItem": "<key of the created item>"}
    if pdf_filename:
        payload["pdf"] = {"filename": pdf_filename, "content_type": "application/pdf"}
    return payload


def write_zotero_files(item: dict, out_dir: Path, base: str,
                       pdf_filename: Optional[str] = None,
                       link_url: Optional[str] = None,
                       link_title: Optional[str] = None,
                       missing_reason: str = "no PDF was made for this item",
                       item_id: str = "item_1") -> Tuple[Path, Path]:
    """Write <base>.rdf and <base>.zotero.json into out_dir. Prints the
    PDF NOT ATTACHED line when pdf_filename is None or not in out_dir."""
    out_dir = Path(out_dir)
    if pdf_filename and not (out_dir / pdf_filename).exists():
        missing_reason = f"{pdf_filename} is not in {out_dir}"
        pdf_filename = None
    rdf_path = out_dir / f"{base}.rdf"
    json_path = out_dir / f"{base}.zotero.json"
    rdf_path.write_text(build_rdf(item, pdf_filename, link_url, link_title, item_id),
                        encoding="utf-8")
    json_path.write_text(json.dumps(zoteus_payload(item, pdf_filename, link_url, link_title),
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[rdf] {rdf_path}")
    print(f"[rdf] {json_path}  (item for zotero_create_items)")
    if not pdf_filename:
        print(pdf_missing_notice(missing_reason))
    return rdf_path, json_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--item-json", required=True,
                    help="A Zotero item as JSON, or a .zotero.json written "
                         "by this script (its first item is used).")
    ap.add_argument("--out", required=True, help="Where to write the .rdf.")
    ap.add_argument("--pdf-filename", default=None,
                    help="The PDF's filename; it must sit next to the .rdf.")
    ap.add_argument("--link-url", default=None, help="Web Link attachment URL.")
    ap.add_argument("--link-title", default=None, help="Web Link attachment title.")
    ap.add_argument("--item-id", default="item_1")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.item_json).read_text(encoding="utf-8"))
    item = data["items"][0] if isinstance(data, dict) and "items" in data else data
    if isinstance(data, dict) and "web_link" in data and not args.link_url:
        args.link_url = data["web_link"]["url"]
        args.link_title = args.link_title or data["web_link"]["title"]
    out = Path(args.out)
    out.write_text(build_rdf(item, args.pdf_filename, args.link_url,
                             args.link_title, args.item_id), encoding="utf-8")
    print(f"[rdf] {out}")
    if not args.pdf_filename:
        print(pdf_missing_notice("no --pdf-filename was given"))
    elif not (out.parent / args.pdf_filename).exists():
        print(f"WARNING: {args.pdf_filename} is not next to {out.name}; "
              "Zotero will not find it at import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
