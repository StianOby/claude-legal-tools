#!/usr/bin/env python3
"""Offline tests for book_to_item() in scripts/zotero_book.py and the RDF the
plugin's copy of zotero_rdf.py makes from it (no network).
Run: python tests/nbno/test_zotero_item.py
"""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
import zotero_book as zb  # noqa: E402
import zotero_rdf  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


print("book_to_item")
# Eckhoff, Rettskildelære, 4. utg. (digibok_2009010704007), trimmed, plus a
# translator and an ISBN to exercise both.
book = zb.normalize_metadata({"metadata": {
    "title": "Rettskildelære",
    "titleInfos": [{"title": "Rettskildelære", "subTitle": "en innføring"}],
    "originInfo": {"issued": "1997", "edition": "4. utg.", "publisher": "Tano Aschehoug"},
    "geographic": {"placeString": "Oslo"},
    "languages": [{"code": "nob"}],
    "identifiers": {"isbn": "8251836193", "urn": "URN:NBN:no-nb_digibok_2009010704007"},
    "pageCount": 418,
    "people": [{"name": "Eckhoff, Torstein", "roles": [{"name": "cre"}]},
               {"name": "Helgesen, Jan E.", "roles": [{"name": "red"}]},
               {"name": "Oversetter", "roles": [{"name": "trl"}]}],
}})
item = zb.book_to_item(book)
check("item", item, {
    "itemType": "book",
    "title": "Rettskildelære: en innføring",
    "creators": [{"creatorType": "author", "firstName": "Torstein", "lastName": "Eckhoff"},
                 {"creatorType": "editor", "firstName": "Jan E.", "lastName": "Helgesen"},
                 {"creatorType": "translator", "name": "Oversetter"}],
    "edition": "4",
    "place": "Oslo",
    "publisher": "Tano Aschehoug",
    "date": "1997",
    "numPages": "418",
    "language": "nb",
    "ISBN": "8251836193",
    "extra": "URN: URN:NBN:no-nb_digibok_2009010704007",
})
check("no url field", "url" in item, False)
check("newspaper issue keeps its full date",
      zb.book_to_item(zb.normalize_metadata({"metadata": {
          "title": "VG", "originInfo": {"issued": "18700817"}}}))["date"], "1870-08-17")

print("RDF and Zoteus payload from the plugin's zotero_rdf.py")
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "Eckhoff_Rettskildelaere_(1997).pdf").write_bytes(b"%PDF-1.4\n")
    out = io.StringIO()
    with redirect_stdout(out):
        zotero_rdf.write_zotero_files(item, tmp, "Eckhoff_Rettskildelaere_(1997)",
                                      pdf_filename="Eckhoff_Rettskildelaere_(1997).pdf",
                                      link_url=zb.items_page_url("digibok_2009010704007"),
                                      link_title="eBok (nb.no)")
    rdf = (tmp / "Eckhoff_Rettskildelaere_(1997).rdf").read_text(encoding="utf-8")
    check("ISBN literal, not a URL", "<dc:identifier>ISBN 8251836193</dc:identifier>" in rdf, True)
    check("translators under z:translators", "<z:translators>" in rdf, True)
    check("PDF attached", "<prism:fileName>Eckhoff_Rettskildelaere_(1997).pdf</prism:fileName>" in rdf, True)
    check("web link", "<dc:title>eBok (nb.no)</dc:title>" in rdf, True)
    check("no notice", "PDF NOT ATTACHED" in out.getvalue(), False)
    payload = json.loads((tmp / "Eckhoff_Rettskildelaere_(1997).zotero.json").read_text(encoding="utf-8"))
    check("payload web link url", payload["web_link"]["url"],
          "https://www.nb.no/items/URN:NBN:no-nb_digibok_2009010704007")

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
