#!/usr/bin/env python3
"""Offline tests for scripts/nem.py (no network): page and list parsing on
real forskningsetikk.no pages (fixtures/), saksnr normalisation, file names,
and a full sync + search + get run against a fake site.
Run: python tests/nem-vedtak/test_nem.py
"""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "plugins" / "nem-vedtak" / "skills" / "nem-vedtak" / "scripts"))
import nem  # noqa: E402

FIX = HERE / "fixtures"
failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def fixture(name):
    return (FIX / name).read_text(encoding="utf-8")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        nem.main(list(argv))
    return out.getvalue()


print("saksnr and file names")
for raw, want in [("2026/52", "2026/52"), ("2022-32", "2022/32"), ("NEM 2010/202, REK vest 2010/755", "2010/202"),
                  ("Saksnr. NEM 2018/309 REK Vest 14659", "2018/309"), ("NEM 2016/84", "2016/84"), ("", None)]:
    check(repr(raw), nem.norm_saksnr(raw), want)
check("short slug", nem.file_name("2026/52", "faktoranalyse-av-core-om"), "2026-052_faktoranalyse-av-core-om.md")
check("no saksnr", nem.file_name(None, "x"), "0000-000_x.md")
long = "a" * 80
fn = nem.file_name("2013/99", long)
check("long slug trimmed + hash", (fn.startswith("2013-099_" + "a" * 60 + "-"), len(fn)), (True, 9 + 60 + 5 + 3))
check("slug of escaped URL", nem.slug_of("/om-oss/komiteer-og-utvalg/nem/sok-i-nems-vedtak/?x=1"), "sok-i-nems-vedtak")
check("slug trailing", nem.slug_of(nem.LIST_URL + "crux1/"), "crux1")

print("decision page (2026 format)")
meta, body = nem.parse_page(fixture("vedtak_2026-52.html"), nem.LIST_URL + "faktoranalyse-av-core-om/")
check("title", meta["title"], "Faktoranalyse av CORE-OM")
check("saksnr", meta["saksnr"], "2026/52")
check("sakstype", meta["sakstype"], "Klagesak")
check("institusjon", meta["institusjon"], ["Akershus universitetssykehus HF"])
check("forsteinstans", meta["forsteinstans"], ["REK sør-øst C"])
check("klager", meta["klager"], "Person A")
check("henvisninger", meta["henvisninger"], "Helsepersonelloven § 29")
check("pdf", meta["pdf"].endswith("nem-vedtak---faktoranalyse-av-core-om.pdf"), True)
heads = [h for h, _ in nem.sections(body) if h]
check("sections", heads, ["Sammendrag", "Vedtak fra NEM", "Saksgang", "NEMs vurdering", "Vedtak"])
check("subheading kept", "### Kort om prosjektet" in body, True)
check("no metadata in body", "Person A" in body or "Last ned PDF" in body, False)
check("no nbsp", "\xa0" in body or " " in body, False)

check("soft hyphen kept", nem.html_to_md("<p>helse&shy;undersøkelsene</p>"), "helse\xadundersøkelsene\n")
check("emphasis kept", nem.html_to_md("<p><strong>Stikkord</strong>: <em>Risiko-nytte</em>&nbsp;m.m.</p>"),
      "**Stikkord**: *Risiko-nytte* m.m.\n")
check("no emphasis in headings", nem.html_to_md("<h2><strong>Vedtak</strong></h2><p>x</p>"), "## Vedtak\n\nx\n")
check("ol numbers", nem.html_to_md('<ol><li>a</li><li>b</li></ol><ol type="a" start="3"><li>c</li></ol>'),
      "1. a\n2. b\n\nc. c\n")
check("ul bullets", nem.html_to_md("<ul><li>a</li><li>b</li></ul>"), "- a\n- b\n")
check("metadata plain", nem.html_to_md("<em>Person A</em>", emphasis=False), "Person A\n")

print("decision page (older formats)")
meta, body = nem.parse_page(fixture("vedtak_2010-202_ii.html"), nem.LIST_URL + "laring-av-feil-ved-legevakt-ii/")
check("saksnr", meta["saksnr"], "2010/202")
check("saksnr_raw", meta["saksnr_raw"], "NEM 2010/202, REK vest 2010/755")
check("title", meta["title"], "Læring av feil ved legevakt II")
check("body has text", len(body) > 2000, True)
meta, body = nem.parse_page(fixture("vedtak_2022-32.html"), nem.LIST_URL + "et-3-dagers-kurs-for-cfs-me/")
check("dash saksnr", meta["saksnr"], "2022/32")
check("several klagere", meta["klager"].count("\n"), 2)

print("list page")
page = fixture("list.html")
total, slugs = nem.parse_list(page)
check("total", total, 234)
check("10 per page", len(slugs), nem.PAGE_SIZE)
items = nem.parse_list_items(page)
check("item saksnr", items[0]["saksnr"], "2026/52")
f = nem.parse_filters(page)
check("filter groups", sorted(set(nem.FACETS) - set(f)), [])
check("outcome values", "Klager gis ikke medhold" in f["ndt"], True)
check("emneord count", len(f["nt"]), 24)

print("Markdown round trip")
m = {"saksnr": "2026/52", "title": "T", "utfall": ["Klager gis medhold"], "klager": "A\nB"}
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "x.md"
    p.write_text(nem.render_md(m, "## Vedtak\n\nTekst.\n"), encoding="utf-8")
    back, b = nem.read_md(p)
check("front matter", {k: back[k] for k in m}, m)
check("body", b.strip(), "## Vedtak\n\nTekst.")

print("sync, search, get against a fake site")
A, B = "faktoranalyse-av-core-om", "laring-av-feil-ved-legevakt-ii"
SITEMAP = f"""<urlset>
<url><loc>{nem.LIST_URL}</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{nem.LIST_URL}{A}/</loc><lastmod>2026-10-08</lastmod></url>
<url><loc>{nem.LIST_URL}{B}/</loc><lastmod>2020-01-01</lastmod></url>
<url><loc>https://www.forskningsetikk.no/annet/</loc></url>
</urlset>"""
FACET_PAGE = {("ndt", "Klager gis ikke medhold"): [A], ("ndt", "Klager gis medhold"): [B],
              ("nt", "Samtykke"): [A, B], ("nre", "Selvbestemmelsesprinsippet"): [A]}
FILTERS = "".join(f'<input name="{p}" data-filter-input value="{v}" />' for p, v in FACET_PAGE)
calls = []


def fake_fetch(url, binary=False, tries=3):
    calls.append(url)
    if url == nem.SITEMAP_URL:
        return SITEMAP
    if url == nem.LIST_URL:
        return FILTERS
    if url.startswith(nem.LIST_URL + "?"):
        q = dict(nem.urllib.parse.parse_qsl(url.split("?", 1)[1]))
        p = [k for k in q if k != "p"][0]
        sl = FACET_PAGE.get((p, q[p]), [])
        arts = "".join(f'<article>\n<a href="{nem.LIST_PATH}{s}/"><h3>x</h3></a></article>' for s in sl)
        return f"{len(sl)} resultater {arts}"
    if url == nem.LIST_URL + A + "/":
        return fixture("vedtak_2026-52.html")
    if url == nem.LIST_URL + B + "/":
        return fixture("vedtak_2010-202_ii.html")
    raise AssertionError("unexpected URL " + url)


nem.fetch = fake_fetch
with tempfile.TemporaryDirectory() as d:
    out = run("sync", "--dir", d, "--workers", "2")
    check("sync ok", out.strip().splitlines()[-1].startswith("OK: 2 decisions"), True)
    idx = json.loads((Path(d) / "index.json").read_text(encoding="utf-8"))
    check("index slugs", sorted(idx["vedtak"]), sorted([A, B]))
    check("README.txt written", (Path(d) / "README.txt").read_text(encoding="utf-8"), nem.README_TXT)
    meta, _ = nem.read_md(Path(d) / "vedtak" / "2026-052_faktoranalyse-av-core-om.md")
    check("facets in front matter", (meta["utfall"], meta["emneord"], meta["prinsipper"]),
          (["Klager gis ikke medhold"], ["Samtykke"], ["Selvbestemmelsesprinsippet"]))
    check("lastmod", meta["lastmod"], "2026-10-08")

    calls.clear()
    out = run("sync", "--dir", d, "--no-facets")
    check("incremental: nothing refetched", ("0 new/changed" in out, [c for c in calls if c.endswith("/") and c != nem.LIST_URL]),
          (True, []))

    SITEMAP = SITEMAP.replace("2020-01-01", "2026-10-14")
    calls.clear()
    out = run("sync", "--dir", d, "--no-facets")
    check("changed lastmod refetched", [c for c in calls if c.endswith(B + "/")], [nem.LIST_URL + B + "/"])

    idx = json.loads((Path(d) / "index.json").read_text(encoding="utf-8"))
    del idx["vedtak"][A]["text_format"]  # as written by 0.3.5 and older
    (Path(d) / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    calls.clear()
    out = run("sync", "--dir", d, "--no-facets")
    check("older text format refetched", [c for c in calls if c.endswith("/") and c != nem.LIST_URL],
          [nem.LIST_URL + A + "/"])

    fa = Path(d) / "vedtak" / "2026-052_faktoranalyse-av-core-om.md"
    fa.write_text(fa.read_text(encoding="utf-8").replace("pasientgruppe", "pasient\xadgruppe"), encoding="utf-8")
    out = json.loads(run("search", "--dir", d, "sårbar   pasientgruppe", "--json"))
    check("phrase across whitespace and soft hyphen", [h["saksnr"] for h in out["hits"]], ["2026/52"])
    out = json.loads(run("search", "--dir", d, "--regex", r"sårbar\s+pasientgruppe", "--json"))
    check("regex across soft hyphen", [h["saksnr"] for h in out["hits"]], ["2026/52"])
    out = json.loads(run("search", "--dir", d, "nem la vekt", "--json", "--snippets", "1"))
    snip = out["hits"][0]["snippets"][0]
    check("snippet keeps case + section", (snip["section"], "NEM la vekt" in snip["text"]), ("Sammendrag", True))
    out = json.loads(run("search", "--dir", d, "nem la vekt", "--section", "vurdering", "--json"))
    check("--section narrows", out["hits"], [])
    out = json.loads(run("search", "--dir", d, "--utfall", "gis medhold", "--json"))
    check("utfall filter excludes 'ikke medhold'", [h["saksnr"] for h in out["hits"]], ["2010/202"])
    out = json.loads(run("search", "--dir", d, "--emneord", "samtykke", "--year", "2020-2026", "--json"))
    check("emneord + year", [h["saksnr"] for h in out["hits"]], ["2026/52"])
    out = json.loads(run("search", "--dir", d, "--regex", r"helsepersonelloven\s*§\s*29", "--json"))
    check("regex", [h["saksnr"] for h in out["hits"]], ["2026/52"])
    out = json.loads(run("search", "--dir", d, "CORE-OM", "legevakt", "--any", "--json"))
    check("--any", sorted(h["saksnr"] for h in out["hits"]), ["2010/202", "2026/52"])
    out = json.loads(run("search", "--dir", d, "CORE-OM", "legevakt", "--json"))
    check("AND by default", out["hits"], [])
    out = json.loads(run("search", "--dir", d, "Person A", "--json"))
    check("metadata not searched as text", out["hits"], [])

    out = run("get", "NEM 2026/52", "--dir", d, "--section", "vurdering")
    check("get local section", (out.startswith("---\nsaksnr: \"2026/52\""), "## NEMs vurdering" in out,
                                "## Saksgang" in out, nem.LIVE_NOTE in out), (True, True, False, False))
    meta = json.loads(run("get", "Læring av feil", "--dir", d, "--meta"))
    check("get by title", meta["saksnr"], "2010/202")

print("PDF-only decision")
PDF_ONLY = ('<main><div id="contents"><h1>Bare PDF</h1><h2><span >2012/7</span> | [<span >Klagesak</span>]</h2>'
            '<div class="download download--big">Last ned PDF<br/><strong><a href="/globalassets/x.pdf">x.pdf</a>'
            '</strong></div><h2>Sammendrag</h2><p>Se PDF.</p></div></div></article></main>')
nem.fetch = lambda url, binary=False, tries=3: b"%PDF-1.4 fake" if binary else PDF_ONLY
nem.pdf_text = lambda p: "Vedtak\n\nNEM gir klager medhold.\f"
with tempfile.TemporaryDirectory() as d:
    meta, body = nem.fetch_decision("bare-pdf", nem.LIST_URL + "bare-pdf/", Path(d))
    check("pdf saved", [p.name for p in (Path(d) / "pdf").iterdir()], ["2012-007_bare-pdf.pdf"])
check("text from pdf", (meta["text_source"], "NEM gir klager medhold." in body), ("pdf", True))
nem.pdf_text = lambda p: None
with tempfile.TemporaryDirectory() as d:
    meta, body = nem.fetch_decision("bare-pdf", nem.LIST_URL + "bare-pdf/", Path(d))
check("no pdftotext reported", meta["text_source"].startswith("pdf (no pdftotext"), True)

print("live get")
nem.fetch = lambda url, binary=False, tries=3: (
    '<article>\n<a href="/om-oss/komiteer-og-utvalg/nem/sok-i-nems-vedtak/faktoranalyse-av-core-om/">'
    '<h3 class="bold">Faktoranalyse av CORE-OM</h3></a><strong>2026/52 [Klagesak]</strong></article>'
    if "?q=" in url else fixture("vedtak_2026-52.html"))
with tempfile.TemporaryDirectory() as d:
    out = run("get", "2026/52")
check("live note", out.rstrip().endswith(nem.LIVE_NOTE), True)
check("live has no facet keys", "utfall:" in out, False)

print(f"\n{'FAILED: ' + str(failures) if failures else 'all passed'}")
sys.exit(1 if failures else 0)
