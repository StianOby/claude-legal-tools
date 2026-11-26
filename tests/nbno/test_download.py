#!/usr/bin/env python3
"""Offline tests for download_via_iiif() in scripts/zotero_book.py (no
network): transient errors are retried, one failing page does not abort
the book, a page that cannot be had becomes a placeholder in its own place
(so later pages keep their numbers), and the temp folder is removed.
Also normalize_metadata()'s edition and editor role codes.
Needs Pillow. Run: python tests/nbno/test_download.py
"""

import io
import os
import sys
import tempfile
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
try:
    from PIL import Image
except ImportError:
    print("SKIP: Pillow not installed")
    sys.exit(0)
import zotero_book as zb  # noqa: E402

# The download tests below replace these; the tile tests use the real ones.
REAL_TILED, REAL_SINGLE = zb._fetch_page_tiled, zb._fetch_page_singleshot
failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


zb.time.sleep = lambda s: None  # no real backoff in tests

print("_read_url retries transient errors")
calls = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def flaky(errors):
    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        if errors:
            raise errors.pop(0)
        return Resp(b"ok")
    return urlopen


def http(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


zb.urllib.request.urlopen = flaky([http(503), TimeoutError("slow")])
check("503 then timeout then success", (zb._read_url("https://x/u", {}, 1), len(calls)), (b"ok", 3))
calls.clear()
zb.urllib.request.urlopen = flaky([http(403)])
try:
    zb._read_url("https://x/u", {}, 1)
    check("403 is not retried", "no error", "HTTPError")
except urllib.error.HTTPError:
    check("403 is not retried", len(calls), 1)
calls.clear()
zb.urllib.request.urlopen = flaky([http(429)] * 10)
try:
    zb._read_url("https://x/u", {}, 1)
except urllib.error.HTTPError:
    check("gives up after the last retry", len(calls), len(zb._RETRY_DELAYS) + 1)


print("download_via_iiif")


def jpeg(color):
    buf = io.BytesIO()
    Image.new("RGB", (100, 140), color).save(buf, "JPEG")
    return buf.getvalue()


CANVASES = ["p1", "p2", "p3_C2", "p4", "p5"]
zb._fetch_manifest = lambda cid, hdr: {"sequences": [{"canvases": [
    {"@id": f"x/{c}", "images": [{"resource": {"service": {"@id": f"https://iiif/{c}"}}}]}
    for c in CANVASES]}]}
zb._fetch_iiif_info = lambda base, hdr, timeout=15.0: {"width": 100, "height": 140, "sizes": [{"width": 100}]}
attempts = {}
BROKEN = {"p2": 1, "p4": 99}  # p2 fails once (then works), p4 never works


def singleshot(base, width, hdr, timeout=30.0):
    name = base.rsplit("/", 1)[1]
    attempts[name] = attempts.get(name, 0) + 1
    if attempts[name] <= BROKEN.get(name, 0):
        raise urllib.error.URLError("connection reset")
    return jpeg("gray"), (100, 140)


zb._fetch_page_singleshot = singleshot
zb._fetch_page_tiled = lambda base, info, hdr, scale=1: None
assembled = {}


def assemble(paths, out):
    assembled["paths"] = [Path(p).name for p in paths]
    assembled["dir"] = Path(paths[0]).parent
    assembled["exists"] = all(Path(p).exists() for p in paths)


zb._assemble_pages_to_pdf = assemble
out = io.StringIO()
with redirect_stdout(out):
    result = zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=4)
log = out.getvalue()
check("page 2 recovered on the second pass", attempts["p2"], 2)
check("PDF order: C2 skipped, page 4 is a placeholder in its place",
      assembled["paths"], ["page_0001.jpg", "page_0002.jpg", "page_0004.missing.jpg", "page_0005.jpg"])
check("all files existed when assembled", assembled["exists"], True)
check("result names the missing PDF page",
      {k: result[k] for k in ("pages", "missing")}, {"pages": 4, "missing": [3]})
check("result gives each PDF page's canvas, None for the placeholder",
      [c is None for c in result["canvases"]], [False, False, True, False])
check("the log warns about it", "placeholder pages in the PDF: [3]" in log, True)
check("temp folder removed", assembled["dir"].exists(), False)

print("download_via_iiif: start/stop range")
recorded = {}


def assemble_rec(paths, out):
    recorded["paths"] = [Path(p).name for p in paths]


zb._assemble_pages_to_pdf = assemble_rec
BROKEN.clear()
BROKEN["p4"] = 99  # p4 still never works
attempts.clear()
with redirect_stdout(io.StringIO()):
    r = zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=2,
                             start=2, stop=99)  # stop clamped to 5 canvases
check("range 2..end: only those canvases fetched", sorted(attempts), ["p2", "p4", "p5"])
check("pages are renumbered within the range, placeholder keeps its place",
      (r["pages"], r["missing"], [c is None for c in r["canvases"]]), (3, [2], [False, True, False]))
check("canvas names come from the selected range", r["canvases"][0], "p2")
attempts.clear()
with redirect_stdout(io.StringIO()):
    r = zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=2, stop=2)
check("stop only", (sorted(attempts), r["pages"]), (["p1", "p2"], 2))
for kw in ({"start": 0}, {"start": 3, "stop": 2}):
    try:
        zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", **kw)
        check(f"rejects {kw}", "no error", "ValueError")
    except ValueError:
        check(f"rejects {kw}", True, True)
try:
    with redirect_stdout(io.StringIO()):
        zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", start=9)
    check("start beyond the manifest", "no error", "SystemExit")
except SystemExit:
    check("start beyond the manifest", True, True)

print("download_via_iiif: page size and tiles")
seen = {"single": [], "tiled": []}


def single_rec(base, scale, hdr, timeout=30.0):
    seen["single"].append(scale)
    return jpeg("gray"), (100, 140)


def tiled_rec(base, info, hdr, scale=1):
    seen["tiled"].append(scale)
    return jpeg("gray")


zb._fetch_page_singleshot = single_rec
zb._fetch_page_tiled = tiled_rec
zb._assemble_pages_to_pdf = lambda paths, out: None
with redirect_stdout(io.StringIO()):
    zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=2, stop=2)
check("default: half size, one request per page", (seen["single"], seen["tiled"]), ([2, 2], []))
seen = {"single": [], "tiled": []}


def single_refused(base, scale, hdr, timeout=30.0):
    seen["single"].append(scale)
    return None, None


zb._fetch_page_singleshot = single_refused
_manifest = zb._fetch_manifest
zb._fetch_manifest = lambda cid, hdr: {"sequences": [{"canvases": [
    {"@id": f"x/p{i}", "images": [{"resource": {"service": {"@id": f"https://iiif/p{i}"}}}]}
    for i in range(1, 7)]}]}
with redirect_stdout(io.StringIO()):
    zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=1)
check("refused one request: tiles, and after 3 refusals no more one requests",
      (len(seen["single"]), len(seen["tiled"])), (3, 6))
zb._fetch_manifest = _manifest
zb._fetch_page_singleshot = single_rec
seen = {"single": [], "tiled": []}
with redirect_stdout(io.StringIO()):
    zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=2, stop=1,
                         size="full", tiles="always")
check("--size full --tiles always: full-size tiles", seen["tiled"], [1])
# A canvas 400 px wide: half size should be 200, so a 100 px answer is a
# silent downsample and the page is fetched again as tiles.
_manifest = zb._fetch_manifest
zb._fetch_manifest = lambda cid, hdr: {"sequences": [{"canvases": [
    {"@id": "x/p1", "width": 400, "images": [{"resource": {"service": {"@id": "https://iiif/p1"}}}]}]}]}
seen = {"single": [], "tiled": []}
with redirect_stdout(io.StringIO()):
    zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=1)
check("downsampled answer -> tiles", (seen["single"], seen["tiled"]), ([2], [2]))
zb._fetch_manifest = _manifest
try:
    zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", size="huge")
    check("rejects an unknown size", "no error", "ValueError")
except ValueError:
    check("rejects an unknown size", True, True)

print("download_via_iiif: stops early when the first pages all fail")
attempts.clear()


def single_dead(base, scale, hdr, timeout=30.0):
    name = base.rsplit("/", 1)[1]
    attempts[name] = attempts.get(name, 0) + 1
    raise urllib.error.URLError("refused")


zb._fetch_page_singleshot = single_dead
zb._fetch_manifest = lambda cid, hdr: {"sequences": [{"canvases": [
    {"@id": f"x/p{i}", "images": [{"resource": {"service": {"@id": f"https://iiif/p{i}"}}}]}
    for i in range(1, 31)]}]}
try:
    with redirect_stdout(io.StringIO()):
        zb.download_via_iiif("digibok_1", Path(tempfile.mkdtemp()) / "b.pdf", workers=4)
    check("aborts", "no error", "SystemExit")
except SystemExit as e:
    check("aborts with the access hint", "first 8 pages all failed" in str(e)
          and "TAKENBYCURRENTUSER" in str(e), True)
check("only the first 8 pages tried, once each", (len(attempts), max(attempts.values())), (8, 1))
zb._fetch_manifest = _manifest
zb._fetch_page_singleshot = single_rec

print("_fetch_page_tiled against a resolver that acts like nb.no on 2026-11-26")
import re  # noqa: E402

_real_read_url = zb._read_url
FULL_W, FULL_H = 2938, 4041
requested = []


def fake_resolver(behaviour):
    def read(url, hdr, timeout):
        if behaviour == "empty":
            return b""
        m = re.search(r"/(\d+),(\d+),(\d+),(\d+)/([^/]+)/0/default\.jpg$", url)
        x, y, w, h = map(int, m.groups()[:4])
        requested.append((x, y, w, h))
        if behaviour == "empty" or (behaviour == "narrow_edge_empty"
                                    and x + w == FULL_W and w < 2048):
            return b""
        size = m.group(5)
        if behaviour == "ignores_size" or size == "full":
            ow, oh = w, h
        else:
            ow = int(size.rstrip(","))
            oh = round(h * ow / w)
        buf = io.BytesIO()
        # Shade by region origin, so a misplaced tile shows.
        Image.new("RGB", (ow, oh), (x % 251, y % 251, 100)).save(buf, "JPEG")
        return buf.getvalue()
    return read


info = {"width": FULL_W, "height": FULL_H}
check("tile origins: last one moved back to keep the full step",
      (zb._tile_starts(FULL_W, 2048), zb._tile_starts(FULL_H, 2048), zb._tile_starts(1500, 2048)),
      ([0, 890], [0, 1993], [0]))
zb._read_url = fake_resolver("narrow_edge_empty")
requested.clear()
page = REAL_TILED("https://iiif/p1", info, {}, scale=2)
check("every region the full 2048 px a side", {(w, h) for _, _, w, h in requested}, {(2048, 2048)})
with Image.open(io.BytesIO(page)) as im:
    check("half-size page: 1469x2021", im.size, (1469, 2021))
    check("right and bottom edges are filled, not white",
          (im.getpixel((1468, 10))[2] < 200, im.getpixel((10, 2020))[2] < 200), (True, True))
for behaviour, why in (("ignores_size", "tile at full size"), ("empty", "empty body")):
    zb._read_url = fake_resolver(behaviour)
    try:
        REAL_TILED("https://iiif/p1", info, {}, scale=2)
        check(f"{why} fails the page", "no error", "PageImageError")
    except zb.PageImageError as e:
        check(f"{why} fails the page", True, True)
zb._read_url = fake_resolver("empty")
check("empty one-request answer counts as refused",
      REAL_SINGLE("https://iiif/p1", 2, {}), (None, None))
zb._read_url = _real_read_url

print("rescale_pdf_pages: poster PDF -> book size")
try:
    import pypdf  # noqa: F401
except ImportError:
    print("  skip (pypdf not installed)")
else:
    pdf = Path(tempfile.mkdtemp()) / "poster.pdf"
    ims = [Image.new("RGB", (1500, 2200), "white"), Image.new("RGB", (1500, 2200), "gray"),
           Image.new("RGB", (1500, 842), "white")]
    ims[0].save(str(pdf), save_all=True, append_images=ims[1:], resolution=72.0)
    heights = lambda: [round(float(pg.mediabox.height)) for pg in pypdf.PdfReader(str(pdf)).pages]
    check("starts poster-size", heights(), [2200, 2200, 842])
    check("two pages rescaled", zb.rescale_pdf_pages(pdf), 2)
    check("pages now A4 height (~842 pt), small page untouched",
          [abs(h - 842) <= 1 for h in heights()], [True, True, True])
    check("width scaled in proportion", round(float(pypdf.PdfReader(str(pdf)).pages[0].mediabox.width)),
          round(1500 * 842 / 2200))
    check("idempotent", zb.rescale_pdf_pages(pdf), 0)

print("normalize_metadata: edition and editor roles")
for raw, want in [("5. utg. [redigert av] Jan E. Helgesen", "5"), ("[2. utg.]", "2"),
                  ("6. utgave", "6"), ("Ny utg.", "Ny utg."), ("Rev.  utg.", "Rev. utg."), (None, "")]:
    check(f"edition {raw!r}", zb._edition(raw), want)
# Eckhoff, Rettskildelære, 4. utg. (digibok_2009010704007), trimmed.
book = zb.normalize_metadata({"metadata": {
    "title": "Rettskildelære",
    "originInfo": {"issued": "1997", "edition": "4. utg. [revidert av] Jan E. Helgesen"},
    "people": [{"name": "Eckhoff, Torstein", "roles": [{"name": "cre"}]},
               {"name": "Helgesen, Jan E.", "roles": [{"name": "red"}]}],
}})
check("edition field", book.edition, "4")
check("'red' alone is an editor", [c.creator_type for c in book.creators], ["author", "editor"])

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
