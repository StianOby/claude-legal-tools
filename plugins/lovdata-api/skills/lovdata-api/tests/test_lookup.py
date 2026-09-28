#!/usr/bin/env python3
"""Regression tests for document lookup, search and section retrieval in
lovdata.py.

No network: a tiny data directory is written to a temp folder, with markup
trimmed from the public gjeldende-lover package (Grunnloven in bokmål and
nynorsk, arbeidsmiljøloven, menneskerettsloven's EMK annex) and a
delegation decision that mentions Grunnloven in its title.

Run with `python plugins/lovdata-api/skills/lovdata-api/tests/test_lookup.py`.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lovdata  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


def doc(title, short, dokid, body):
    return (
        f'<html><head><title>{title}</title></head><body><header><dl>'
        f'<dd class="dokid">{dokid}</dd><dd class="titleShort">{short}</dd>'
        f'<dd class="lastChangeInForce">2024-05-21</dd></dl></header>'
        f'<main>{body}</main></body></html>'
    )


def para(name, text):
    return (f'<article class="legalArticle" data-name="{name}"><h3>{name.replace("§", "§ ")}.</h3>'
            f'<article class="legalP">{text}</article></article>')


FILES = {
    "nl/nl-18140517-000.xml": doc(
        "Kongeriket Norges Grunnlov", "Grunnloven (bokmål) – Grl.", "NL/lov/1814-05-17",
        para("§100", "Ytringsfrihet bør finne sted.")),
    "nl/nl-18140517-000-nn.xml": doc(
        "Kongeriket Noregs grunnlov", "Grunnlova (nynorsk) – Grl.", "NL/lov/1814-05-17",
        para("§100", "Ytringsfridom skal det vere.")),
    "nl/nl-20050617-062.xml": doc(
        "Lov om arbeidsmiljø, arbeidstid og stillingsvern mv. (arbeidsmiljøloven)",
        "Arbeidsmiljøloven – aml", "NL/lov/2005-06-17-62",
        '<section class="section" data-name="kap4">'
        + para("§4-6", "Arbeidsgiver skal utarbeide oppfølgingsplan. Oppfølgingsplan skal …")
        + "</section>"
        + para("§14-3", "Deltidsansatte har fortrinnsrett til utvidet stilling fremfor at "
                        "arbeidsgiver foretar ny ansettelse. Deltid …")),
    "nl/nl-19990521-030.xml": doc(
        "Lov om styrking av menneskerettighetenes stilling i norsk rett (menneskerettsloven)",
        "Menneskerettsloven – mrl", "NL/lov/1999-05-21-30",
        '<section class="section" data-name="emkn"><h2>EMK</h2>'
        '<article class="legalArticle" data-name="emkn/a8"><h3>Art 8. Retten til respekt '
        'for privatliv og familieliv</h3><article class="legalP">Enhver har rett til respekt '
        'for sitt privatliv.</article></article>'
        '<article class="legalArticle" data-name="emkn/a9"><h3>Art 9.</h3>'
        '<article class="legalP">Tankefrihet.</article></article></section>'
        '<section class="section" data-name="emkn/p1"><h2>Protokoll 1</h2>'
        '<article class="legalArticle" data-name="emkn/p1/a1"><h3>Art 1. Vern om eiendom'
        '</h3></article></section>'),
    "sf/sf-20210917-2772.xml": doc(
        "Delegering av regjeringens myndighet etter Grunnloven § 53 bokstav b",
        "Deleg. av regjeringens myndighet etter Grunnloven § 53 bokstav b",
        "DEL/forskrift/2021-09-17-2772", para("§1", "Myndigheten delegeres.")),
    "sf/sf-19961206-1127.xml": doc(
        "Forskrift om systematisk helse-, miljø- og sikkerhetsarbeid i virksomheter",
        "Internkontrollforskriften", "SF/forskrift/1996-12-06-1127", para("§5", "Tekst.")),
}

tmp = Path(tempfile.mkdtemp(prefix="lovdata-test-"))
for rel, text in FILES.items():
    (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp / rel).write_text(text, encoding="utf-8")
lovdata.DATA_DIR = tmp  # index_path() and find_text() read files from here
index = lovdata.build_index(tmp)


def dokid_of(ref, **kw):
    path, _, _ = lovdata.resolve_ref(index, ref, **kw)
    return index[path]["dokid"] if path else None


# --------------------------------------------------------------------------
print("Grunnloven: bokmål by default, nynorsk only on request")
path, _, _ = lovdata.resolve_ref(index, "NL/lov/1814-05-17")
check("DokID gives bokmål", path, "nl/nl-18140517-000.xml")
path, _, _ = lovdata.resolve_ref(index, "NL/lov/1814-05-17", nynorsk=True)
check("--nn gives nynorsk", path, "nl/nl-18140517-000-nn.xml")
path, _, _ = lovdata.resolve_ref(index, "Grunnloven", nynorsk=True)
check("short title + --nn gives nynorsk", path, "nl/nl-18140517-000-nn.xml")
check("§ 100 in bokmål",
      lovdata.get_law_text(lovdata.index_path("nl/nl-18140517-000.xml"), "100").splitlines()[-1],
      "Ytringsfrihet bør finne sted.")

# --------------------------------------------------------------------------
print("Reference forms accepted by get")
check("LOV-", dokid_of("LOV-2005-06-17-62"), "NL/lov/2005-06-17-62")
check("FOR-", dokid_of("FOR-1996-12-06-1127"), "SF/forskrift/1996-12-06-1127")
check("lov/ without base", dokid_of("lov/2005-06-17-62"), "NL/lov/2005-06-17-62")
check("DEL/ DokID", dokid_of("DEL/forskrift/2021-09-17-2772"), "DEL/forskrift/2021-09-17-2772")
check("abbreviation", dokid_of("aml"), "NL/lov/2005-06-17-62")
check("abbreviation with dot", dokid_of("Grl."), "NL/lov/1814-05-17")
path, para_, _ = lovdata.resolve_ref(
    index, "https://lovdata.no/dokument/NL/lov/2005-06-17-62/%C2%A74-6")
check("URL with encoded §", (index[path]["dokid"], para_), ("NL/lov/2005-06-17-62", "4-6"))
path, para_, _ = lovdata.resolve_ref(index, "https://lovdata.no/lov/2005-06-17-62/§4-6")
check("short URL with §", (index[path]["dokid"], para_), ("NL/lov/2005-06-17-62", "4-6"))
path, _, problem = lovdata.resolve_ref(index, "LOV-2099-01-01-1")
check("unknown LOV- is reported", (path, bool(problem)), (None, True))

# --------------------------------------------------------------------------
print("Search ranking")
check("Grunnloven ranks the constitution first",
      lovdata.search_index(index, "Grunnloven")[0]["dokid"], "NL/lov/1814-05-17")
check("multi-word query matches word by word",
      [r["dokid"] for r in lovdata.search_index(index, "arbeidsmiljø lov")],
      ["NL/lov/2005-06-17-62"])
check("forms include the bare name", lovdata._short_forms("Grunnloven (bokmål) – Grl."),
      ["grunnloven (bokmål)", "grunnloven", "grl"])

# --------------------------------------------------------------------------
print("Annex sections and single articles")
mrl = lovdata.index_path("nl/nl-19990521-030.xml")
check("emkn/a8 is one article", lovdata.get_law_text(mrl, "emkn/a8"),
      "Art 8. Retten til respekt for privatliv og familieliv\n"
      "Enhver har rett til respekt for sitt privatliv.")
check("'emkn art 8' is the same", lovdata.get_law_text(mrl, "emkn art 8"),
      lovdata.get_law_text(mrl, "emkn/a8"))
check("protocol article", lovdata.get_law_text(mrl, "emkn protokoll 1 art. 1"),
      "Art 1. Vern om eiendom")
check("emkn excludes the protocols", "Protokoll 1" in lovdata.get_law_text(mrl, "emkn"), False)
missing = lovdata.get_law_text(mrl, "emkn/a99")
check("unknown article lists protocol sections",
      ("emkn/p1" in missing, "emkn/a8 eller emkn/p1/a1" in missing), (True, True))
check("section alias leaves plain names alone", lovdata._section_name("delII"), "delII")
check("paragraph lookup unaffected",
      lovdata.get_law_text(lovdata.index_path("nl/nl-20050617-062.xml"), "§4-6").splitlines()[0],
      "§ 4-6.")

# --------------------------------------------------------------------------
print("Full-text find")
hits = lovdata.find_text(index, "deltid")
check("finds the provision", [(h["dokid"], h["provision"]) for h in hits],
      [("NL/lov/2005-06-17-62", "§14-3")])
check("laws only by default", lovdata.find_text(index, "delegeres"), [])
check("--sf includes regulations",
      [h["provision"] for h in lovdata.find_text(index, "delegeres", include_sf=True)], ["§1"])
check("all words must match", lovdata.find_text(index, "oppfølgingsplan tankefrihet"), [])
check("nynorsk skipped by default", lovdata.find_text(index, "ytringsfridom"), [])
check("restricted to one document",
      [h["provision"] for h in lovdata.find_text(index, "art", only="nl/nl-19990521-030.xml")],
      ["emkn/a8", "emkn/a9", "emkn/p1/a1"])

if failures:
    print("\n%d failure(s)" % len(failures))
    sys.exit(1)
print("\nall passed")
