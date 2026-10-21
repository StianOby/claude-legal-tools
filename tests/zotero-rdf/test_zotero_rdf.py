#!/usr/bin/env python3
"""Offline tests for shared/zotero-rdf/zotero_rdf.py.

The fixtures are items from the shared Zotero group library "Norsk
henvisningsstandard for rettsvitenskapelige tekster - eksempler" (group
4308632): fixtures/library_items.json is the Web API's `format=json` data,
fixtures/library_export.rdf Zotero's own `format=rdf_zotero` export of the
same items. Every item in the export must come out of build_rdf() with the
same fields in the same places.
Run: python tests/zotero-rdf/test_zotero_rdf.py
"""

import io
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared" / "zotero-rdf"))
import zotero_rdf as zr  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
Z = "{http://www.zotero.org/namespaces/export#}"
DC = "{http://purl.org/dc/elements/1.1/}"
# Export-only output that does not come from item fields (tags, related
# items, a display title Zotero derives) or links to attachments.
IGNORE = {Z + "displayTitle", DC + "subject", DC + "relation",
          "{http://purl.org/rss/1.0/modules/link/}link"}

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def leaves(el, path=()):
    """(path of tags, text) for every text-bearing descendant; the order of
    rdf:li inside a Seq is kept through its index."""
    out = []
    lis = 0
    for child in el:
        if child.tag in IGNORE:
            continue
        tag = child.tag
        if tag == RDF + "li":
            tag += f"[{lis}]"
            lis += 1
        text = (child.text or "").strip()
        if text:
            out.append((path + (tag,), text))
        out += leaves(child, path + (tag,))
    return out


def items(rdf_text):
    """{title: (resource type, sorted leaves)} for every non-attachment item."""
    root = ET.fromstring(rdf_text)
    got = {}
    for res in root:
        itype = res.find(Z + "itemType")
        if itype is None or itype.text == "attachment":
            continue
        got[res.findtext(DC + "title")] = (res.tag, sorted(leaves(res)))
    return got


library = json.loads((FIX / "library_items.json").read_text(encoding="utf-8"))
by_title = {}
for it in library:
    by_title[it.get("title") or it.get("caseName") or it.get("nameOfAct")] = it
exported = items((FIX / "library_export.rdf").read_text(encoding="utf-8"))

print(f"same fields as Zotero's own export ({len(exported)} items)")
for title, want in exported.items():
    it = by_title[title]
    got = items(zr.build_rdf(it))[title]
    check(f"{it['itemType']}: {title[:50]}", got, want)

print("every library item renders and parses")
for it in library:
    title = it.get("title") or it.get("caseName") or it.get("nameOfAct")
    check(f"{it['itemType']}: {title[:50]}", title in items(zr.build_rdf(it)), True)

print("creators and identifiers as the importer reads them")
book = {"itemType": "book", "title": "Rettskildelære", "ISBN": "82-00-12345-6",
        "publisher": "Universitetsforlaget", "place": "Oslo",
        "creators": [{"creatorType": "author", "firstName": "Torstein", "lastName": "Eckhoff"},
                     {"creatorType": "translator", "firstName": "A", "lastName": "B"},
                     {"creatorType": "editor", "name": "Redaksjonen"}]}
root = ET.fromstring(zr.build_rdf(book))
res = root.find("{http://purl.org/net/biblio#}Book")
# The import translator reads translators only from z:translators.
check("translator under z:translators", res.find(Z + "translators") is not None, True)
check("no bib:translators", res.find("{http://purl.org/net/biblio#}translators"), None)
# A dcterms:URI identifier is imported as the URL; ISBN must be a literal.
check("ISBN is a plain literal", res.findtext(DC + "identifier"), "ISBN 82-00-12345-6")
check("no URL field without url", "dcterms:URI" in zr.build_rdf(book), False)
single = res.find(".//{http://purl.org/net/biblio#}editors//{http://xmlns.com/foaf/0.1/}Person")
check("single-field name has no given name",
      [c.tag.split("}")[1] for c in single], ["surname"])
try:
    zr.build_rdf({"itemType": "journalArticle", "title": "x"})
    check("journalArticle refused", False, True)
except ValueError:
    check("journalArticle refused", True, True)

print("attachments and the PDF NOT ATTACHED notice")
rdf = zr.build_rdf(book, pdf_filename="Eckhoff_(1997).pdf",
                   link_url="https://www.nb.no/items/URN:NBN:no-nb_digibok_1",
                   link_title="eBok (nb.no)")
root = ET.fromstring(rdf)
atts = root.findall(Z + "Attachment")
check("two attachments", [a.findtext(Z + "linkMode") for a in atts], ["1", "3"])
check("web link title", atts[1].findtext(DC + "title"), "eBok (nb.no)")
# Zotero saves a link from attachment.url, read only from a dcterms:URI; an
# rdf:resource would be taken as a file path and the link silently dropped.
check("web link url as dcterms:URI",
      atts[1].findtext(f"{DC}identifier/{{http://purl.org/dc/terms/}}URI/{RDF}value"),
      "https://www.nb.no/items/URN:NBN:no-nb_digibok_1")
check("web link has no rdf:resource", atts[1].find(RDF + "resource"), None)
check("PDF keeps its rdf:resource path",
      atts[0].find(RDF + "resource").get(RDF + "resource"), "Eckhoff_(1997).pdf")
check("book links both", len(root.find("{http://purl.org/net/biblio#}Book")
                             .findall("{http://purl.org/rss/1.0/modules/link/}link")), 2)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    out = io.StringIO()
    with redirect_stdout(out):
        zr.write_zotero_files(book, tmp, "Eckhoff_(1997)", pdf_filename="Eckhoff_(1997).pdf",
                              link_url="https://www.nb.no/items/x", link_title="eBok (nb.no)")
    check("missing file -> notice", "PDF NOT ATTACHED: Eckhoff_(1997).pdf is not in" in out.getvalue(), True)
    check("missing file -> no PDF in RDF",
          "linkMode>1<" in (tmp / "Eckhoff_(1997).rdf").read_text(encoding="utf-8"), False)
    (tmp / "Eckhoff_(1997).pdf").write_bytes(b"%PDF-1.4\n")
    out = io.StringIO()
    with redirect_stdout(out):
        zr.write_zotero_files(book, tmp, "Eckhoff_(1997)", pdf_filename="Eckhoff_(1997).pdf",
                              link_url="https://www.nb.no/items/x", link_title="eBok (nb.no)")
    check("PDF present -> no notice", "PDF NOT ATTACHED" in out.getvalue(), False)
    payload = json.loads((tmp / "Eckhoff_(1997).zotero.json").read_text(encoding="utf-8"))
    check("payload item is the item", payload["items"], [book])
    check("payload web link", (payload["web_link"]["linkMode"], payload["web_link"]["url"]),
          ("linked_url", "https://www.nb.no/items/x"))
    with redirect_stdout(io.StringIO()):
        zr.write_zotero_files(book, tmp, "with_url", pdf_filename="Eckhoff_(1997).pdf",
                              pdf_url="https://example.org/e.pdf")
    payload_url = json.loads((tmp / "with_url.zotero.json").read_text(encoding="utf-8"))
    check("payload pdf url", payload_url["pdf"],
          {"content_type": "application/pdf", "filename": "Eckhoff_(1997).pdf",
           "url": "https://example.org/e.pdf"})
    check("pdf url stays out of the RDF",
          "example.org" in (tmp / "with_url.rdf").read_text(encoding="utf-8"), False)
    out = io.StringIO()
    with redirect_stdout(out):
        zr.main(["--item-json", str(tmp / "Eckhoff_(1997).zotero.json"),
                 "--out", str(tmp / "again.rdf")])
    check("CLI without --pdf-filename -> notice", "PDF NOT ATTACHED" in out.getvalue(), True)
    check("CLI keeps the web link", "eBok (nb.no)" in (tmp / "again.rdf").read_text(encoding="utf-8"), True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
