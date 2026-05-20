#!/usr/bin/env python3
"""
build_zotero_rdf.py — emit a Zotero-compatible RDF file for one nb.no book.

The generated RDF imports into Zotero with:
  * a Book item with full metadata (title, creators, publisher, place, year,
    language, ISBN, page count, abstract);
  * an imported-file PDF attachment (linkMode 1) referenced relative to the
    RDF's own location — by default just the bare filename, so the .rdf and
    the .pdf sit side by side in the outputs folder;
  * a linked-URL "Web Link" attachment titled "eBok (nb.no)" pointing at the
    nb.no items URL (linkMode 3).

The Zotero "URL" metadata field is intentionally NOT populated. The link
to nb.no lives only as the Web Link attachment.

Usable both as a CLI and as a library:

    from build_zotero_rdf import build_rdf, NormalizedBook, Creator
    rdf_xml = build_rdf(book, pdf_filename="Hamsun_Sult_(1890).pdf",
                        nb_url="https://www.nb.no/items/URN:NBN:no-nb_digibok_...")
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import List, Optional
from xml.sax.saxutils import escape as _xml_escape


# ---------------------------------------------------------------------------
# Normalized metadata
# ---------------------------------------------------------------------------

@dataclass
class Creator:
    """A person or organisation associated with the book.

    creator_type:  "author" (default), "editor", "translator", "contributor".
    """

    surname: str = ""
    given: str = ""
    organization: str = ""    # used when surname/given are empty
    creator_type: str = "author"

    @property
    def is_person(self) -> bool:
        return bool(self.surname or self.given)


@dataclass
class NormalizedBook:
    """Subset of book metadata the RDF builder needs.

    Build this from whatever source (nb.no API, MODS, RIS, user input)
    before calling build_rdf().
    """

    title: str
    short_title: str = ""           # optional, used for citekey
    subtitle: str = ""
    creators: List[Creator] = field(default_factory=list)
    publisher: str = ""
    place: str = ""
    year: str = ""                  # ISO year as string ("1890")
    language: str = ""              # ISO 639 code, two- or three-letter
    isbn: str = ""
    num_pages: str = ""             # string to allow "[358]" etc.
    abstract: str = ""
    series: str = ""
    edition: str = ""
    extra: str = ""                 # extra free-text Zotero field


# ---------------------------------------------------------------------------
# RDF emission
# ---------------------------------------------------------------------------

# Zotero RDF dialect: this mirrors what Zotero's own "Zotero RDF" translator
# produces. The shape is conservative and exercised by Zotero's import path —
# linkMode is emitted as a numeric string, attachment paths are relative.
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
    """XML-escape an element's inline text content."""
    return _xml_escape(s.strip(), {'"': "&quot;"})


def _esc_attr(s: str) -> str:
    """XML-escape for use in an attribute value."""
    return _xml_escape(s, {'"': "&quot;", "'": "&apos;"})


def _person_element(c: Creator) -> str:
    """Render a foaf:Person (or foaf:Organization) element."""
    if c.is_person:
        parts = ["<foaf:Person>"]
        if c.surname:
            parts.append(f"<foaf:surname>{_esc(c.surname)}</foaf:surname>")
        if c.given:
            parts.append(f"<foaf:givenName>{_esc(c.given)}</foaf:givenName>")
        parts.append("</foaf:Person>")
        return "".join(parts)
    return f"<foaf:Organization><foaf:name>{_esc(c.organization)}</foaf:name></foaf:Organization>"


def _creators_block(creators: List[Creator]) -> str:
    """Group creators by type and emit Zotero's nested-Seq structure."""
    # Map our type names to Zotero's bib: predicates.
    type_to_predicate = {
        "author":      "bib:authors",
        "editor":      "bib:editors",
        "translator":  "bib:translators",
        "contributor": "bib:contributors",
    }
    blocks = []
    # Stable iteration order by predicate to keep output deterministic.
    for kind in ("author", "editor", "translator", "contributor"):
        group = [c for c in creators if c.creator_type == kind]
        if not group:
            continue
        predicate = type_to_predicate[kind]
        items = "".join(f"<rdf:li>{_person_element(c)}</rdf:li>" for c in group)
        blocks.append(f"<{predicate}><rdf:Seq>{items}</rdf:Seq></{predicate}>")
    return "\n  ".join(blocks)


def _publisher_block(publisher: str, place: str) -> str:
    if not publisher and not place:
        return ""
    parts = ["<dc:publisher><foaf:Organization>"]
    if place:
        parts.append(
            "<vcard:adr><vcard:Address>"
            f"<vcard:locality>{_esc(place)}</vcard:locality>"
            "</vcard:Address></vcard:adr>"
        )
    if publisher:
        parts.append(f"<foaf:name>{_esc(publisher)}</foaf:name>")
    parts.append("</foaf:Organization></dc:publisher>")
    return "".join(parts)


def _book_links(pdf_about: str, url_about: str) -> str:
    """Emit the <link:link rdf:resource="..."/> pointers from the book to
    its two attachments."""
    return (
        f'<link:link rdf:resource="{_esc_attr(pdf_about)}"/>\n  '
        f'<link:link rdf:resource="{_esc_attr(url_about)}"/>'
    )


def _pdf_attachment(pdf_about: str, pdf_filename: str) -> str:
    """Imported-file attachment (linkMode 1)."""
    return (
        f'<z:Attachment rdf:about="{_esc_attr(pdf_about)}">\n'
        "  <z:itemType>attachment</z:itemType>\n"
        f'  <rdf:resource rdf:resource="{_esc_attr(pdf_about)}"/>\n'
        f"  <dc:title>{_esc(pdf_filename)}</dc:title>\n"
        "  <z:linkMode>1</z:linkMode>\n"
        "  <link:type>application/pdf</link:type>\n"
        f"  <prism:fileName>{_esc(pdf_filename)}</prism:fileName>\n"
        "</z:Attachment>"
    )


def _url_attachment(url: str, title: str = "eBok (nb.no)") -> str:
    """Web Link attachment (linkMode 3) — Zotero's 'linked URL'."""
    return (
        f'<z:Attachment rdf:about="{_esc_attr(url)}">\n'
        "  <z:itemType>attachment</z:itemType>\n"
        f'  <rdf:resource rdf:resource="{_esc_attr(url)}"/>\n'
        f"  <dc:title>{_esc(title)}</dc:title>\n"
        "  <z:linkMode>3</z:linkMode>\n"
        "  <link:type>text/html</link:type>\n"
        "</z:Attachment>"
    )


def build_rdf(
    book: NormalizedBook,
    pdf_filename: str,
    nb_url: str,
    item_id: str = "item_1",
) -> str:
    """Render a complete Zotero-RDF document as a string.

    Parameters
    ----------
    book : NormalizedBook
        Source metadata. Empty/missing fields are skipped.
    pdf_filename : str
        Filename of the PDF, e.g. "Hamsun_Sult_(1890).pdf". Assumed to live
        in the same folder as the .rdf file at import time.
    nb_url : str
        Public nb.no URL for the book (used in the Web Link attachment).
    item_id : str
        Anchor identifier for the book within the RDF document. Default
        "item_1" is fine for single-item files.
    """
    book_about = f"#{item_id}"
    pdf_about = pdf_filename                 # relative to the .rdf
    url_about = nb_url                       # the nb.no URL itself

    parts: List[str] = [RDF_HEAD]

    # ---- the Book item ----------------------------------------------------
    parts.append(f'<bib:Book rdf:about="{_esc_attr(book_about)}">')
    parts.append("  <z:itemType>book</z:itemType>")

    title = book.title.strip()
    if book.subtitle:
        title = f"{title}: {book.subtitle.strip()}"
    parts.append(f"  <dc:title>{_esc(title)}</dc:title>")

    if book.short_title:
        parts.append(f"  <z:shortTitle>{_esc(book.short_title)}</z:shortTitle>")

    if book.creators:
        parts.append("  " + _creators_block(book.creators))

    if book.year:
        parts.append(f"  <dc:date>{_esc(book.year)}</dc:date>")

    pub = _publisher_block(book.publisher, book.place)
    if pub:
        parts.append("  " + pub)

    if book.edition:
        parts.append(f"  <prism:edition>{_esc(book.edition)}</prism:edition>")

    if book.num_pages:
        parts.append(f"  <z:numPages>{_esc(book.num_pages)}</z:numPages>")

    if book.language:
        parts.append(f"  <z:language>{_esc(book.language)}</z:language>")

    if book.isbn:
        parts.append(
            "  <dc:identifier>"
            f"<dcterms:URI><rdf:value>ISBN {_esc(book.isbn)}</rdf:value></dcterms:URI>"
            "</dc:identifier>"
        )

    if book.series:
        parts.append(
            "  <dcterms:isPartOf>"
            "<bib:Series>"
            f"<dc:title>{_esc(book.series)}</dc:title>"
            "</bib:Series>"
            "</dcterms:isPartOf>"
        )

    if book.abstract:
        parts.append(f"  <dcterms:abstract>{_esc(book.abstract)}</dcterms:abstract>")

    if book.extra:
        # Zotero collects unknown z:* into the Extra field via dc:description.
        parts.append(f"  <dc:description>{_esc(book.extra)}</dc:description>")

    # NB: the Zotero URL field is deliberately left unset.

    parts.append("  " + _book_links(pdf_about, url_about))
    parts.append("</bib:Book>")

    # ---- the two attachments ---------------------------------------------
    parts.append(_pdf_attachment(pdf_about, pdf_filename))
    parts.append(_url_attachment(url_about, title="eBok (nb.no)"))

    parts.append(RDF_TAIL)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _book_from_json(path: str) -> NormalizedBook:
    """Read a NormalizedBook from a JSON dump.

    The JSON shape mirrors NormalizedBook with a "creators" list of
    {surname, given, organization, creator_type} dicts.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    creators_raw = data.pop("creators", []) or []
    creators = [Creator(**c) for c in creators_raw]
    return NormalizedBook(creators=creators, **data)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--book-json", required=True,
                    help="Path to a NormalizedBook JSON dump.")
    ap.add_argument("--pdf-filename", required=True,
                    help="Filename of the PDF, e.g. Hamsun_Sult_(1890).pdf")
    ap.add_argument("--nb-url", required=True,
                    help="Public nb.no URL for the book.")
    ap.add_argument("--out", required=True,
                    help="Where to write the .rdf file.")
    ap.add_argument("--item-id", default="item_1",
                    help="RDF anchor for the book element (default: item_1).")
    args = ap.parse_args(argv)

    book = _book_from_json(args.book_json)
    rdf = build_rdf(
        book,
        pdf_filename=args.pdf_filename,
        nb_url=args.nb_url,
        item_id=args.item_id,
    )
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(rdf)
    print(f"RDF: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
