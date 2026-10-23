#!/usr/bin/env python3
"""Offline tests for scripts/shrink_pdf.py (the bitonal, grey and jpeg
modes) and for zotero_book.py keeping the unshrunk PDF when OCR fails.

Pages are drawn here: a text page on tinted paper at nb.no's half size
(~145 dpi), the same page with a photo-like block, a quarter-size page
(~70 dpi) and a text page with a dark scan edge.
Needs Pillow, pikepdf and numpy. Run: python tests/nbno/test_shrink.py
"""

import io
import random
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
try:
    import numpy as np
    import pikepdf
    from PIL import Image, ImageDraw
except ImportError as exc:
    print(f"SKIP: {exc.name} not installed")
    sys.exit(0)
import shrink_pdf as sp  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


A4_IN = 297 / 25.4
rng = random.Random(1)


def text_page(w=1100, h=1700, paper=(222, 214, 190)):
    """Lines of dark 'words' on tinted paper with a little noise."""
    im = Image.new("RGB", (w, h), paper)
    d = ImageDraw.Draw(im)
    for y in range(120, h - 150, 34):
        x = 90
        while x < w - 140:
            n = rng.randint(3, 9)
            d.text((x, y), "abcdefghijklmnopqrstuvwxyz"[:n] * 1, fill=(40, 35, 30))
            d.rectangle([x, y + 14, x + n * 6, y + 16], fill=(40, 35, 30))
            x += n * 7 + 14
    noise = np.random.default_rng(1).normal(0, 4, (h, w, 1))
    a = np.clip(np.asarray(im, dtype=np.float32) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def with_photo(im):
    """Paste a smooth mid-grey 'photo' over ~20 % of the page."""
    im = im.copy()
    w, h = im.width // 2, im.height // 2
    yy, xx = np.mgrid[0:h, 0:w]
    g = 120 + 60 * np.sin(xx / 23.0) * np.cos(yy / 31.0)
    photo = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).convert("RGB")
    im.paste(photo, (im.width // 4, im.height // 4))
    return im


def with_dark_edge(im):
    """A scan shadow down the left edge, as old books have."""
    a = np.asarray(im, dtype=np.float32).copy()
    ramp = np.linspace(0.35, 1.0, 40)[None, :, None]
    a[:, :40, :] *= ramp
    return Image.fromarray(a.astype(np.uint8))


def make_pdf(pages, path):
    """One page per image, each page A4 high, as zotero_book builds them."""
    pdf = pikepdf.new()
    for im in pages:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        h_pt = A4_IN * 72
        w_pt = h_pt * im.width / im.height
        page = pdf.add_blank_page(page_size=(w_pt, h_pt))
        st = pdf.make_stream(buf.getvalue())
        d = st.stream_dict
        d.Type, d.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        d.Width, d.Height, d.BitsPerComponent = im.width, im.height, 8
        d.ColorSpace, d.Filter = pikepdf.Name.DeviceRGB, pikepdf.Name.DCTDecode
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=st))
        page.Contents = pdf.make_stream(f"q {w_pt} 0 0 {h_pt} 0 0 cm /Im0 Do Q".encode())
    pdf.save(str(path))


def page_images(path):
    with pikepdf.open(str(path)) as pdf:
        out = []
        for page in pdf.pages:
            raw = page.Resources.XObject.Im0
            out.append((str(raw.Filter), int(raw.Width), int(raw.Height),
                        str(raw.get("/ColorSpace")), pikepdf.PdfImage(raw).as_pil_image()))
        return out


tmp = Path(tempfile.mkdtemp())
text = text_page()
pages = [text, with_photo(text), text.resize((550, 850)), with_dark_edge(text)]
src = tmp / "book.pdf"
make_pdf(pages, src)

print("page classifier")
dpi = text.height / A4_IN
check("text page is not a picture", sp._is_picture_page(text.convert("L"), dpi), False)
check("photo block makes a picture page", sp._is_picture_page(with_photo(text).convert("L"), dpi), True)
check("dark scan edge does not", sp._is_picture_page(with_dark_edge(text).convert("L"), dpi), False)
check("tinted paper is not colour", sp._is_colour(text), False)
check("a colour cover is", sp._is_colour(Image.new("RGB", (400, 600), (180, 30, 40))), True)

print("bitonal mode")
out = tmp / "bitonal.pdf"
with redirect_stdout(io.StringIO()):
    stats = sp.recompress(src, out, mode="bitonal")
imgs = page_images(out)
check("filters: G4, JPEG (photo), JPEG (70 dpi), G4 (dark edge)",
      [i[0] for i in imgs], ["/CCITTFaxDecode", "/DCTDecode", "/DCTDecode", "/CCITTFaxDecode"])
check("half-size page scaled up 2x", imgs[0][1:3], (2200, 3400))
check("stats", (stats["images_bitonal"], stats["images_kept_picture"]), (2, 1))
want = sp.to_bitonal(page_images(src)[0][4].convert("L"), 2, dpi)  # the JPEG as stored
got = imgs[0][4].convert("1")
check("G4 decodes to the thresholded page (black stays black)",
      bool((np.asarray(got) == np.asarray(want)).all()), True)
a = np.asarray(got)
check("paper comes out white (bottom margin)", bool(a[-150:-60, 200:2000].all()), True)
check("text comes out black", 0.02 < 1 - a[240:3000, 180:2000].mean() < 0.5, True)
check("smaller than the source", out.stat().st_size < src.stat().st_size, True)

print("bitonal: idempotent")
again = tmp / "again.pdf"
with redirect_stdout(io.StringIO()):
    st2 = sp.recompress(out, again, mode="bitonal")
check("bitonal pages are left alone on a second run", st2["images_skipped_mono"], 2)

print("grey mode")
out = tmp / "grey.pdf"
with redirect_stdout(io.StringIO()):
    sp.recompress(src, out, mode="grey")
imgs = page_images(out)
check("text page: grey JPEG at its own size", imgs[0][:4], ("/DCTDecode", 1100, 1700, "/DeviceGray"))
check("no G4 in grey mode", any(i[0] == "/CCITTFaxDecode" for i in imgs), False)

print("jpeg mode")
out = tmp / "jpeg.pdf"
with redirect_stdout(io.StringIO()):
    sp.recompress(src, out, mode="jpeg")
check("resized to 800 px, colour kept", page_images(out)[0][1:4], (800, 1236, "/DeviceRGB"))

print("g4_encode")
big = Image.new("1", (3000, 4200), 1)
ImageDraw.Draw(big).rectangle([100, 100, 2900, 4100], outline=0, width=5)
data, black_is_1 = sp.g4_encode(big)
check("one strip, BlackIs1 from the TIFF", (len(data) > 0, black_is_1), (True, True))

print("zotero_book: OCR failure keeps the unshrunk PDF")
import zotero_book as zb  # noqa: E402


def fake_download(**kw):
    make_pdf([text, text], kw["out_pdf"])
    return {"pages": 2, "missing": [], "canvases": ["p1", "p2"]}


def failing_ocr(*a, **kw):
    raise SystemExit("ERROR: ocrmypdf exited with status 15:\nModuleNotFoundError: jsonschema")


zb.fetch_nb_metadata = lambda cid, nbsso=None: {
    "metadata": {"title": "Testbok", "originInfo": {"issued": "1990"},
                 "people": [{"name": "Hansen, Hans", "roles": [{"name": "cre"}]}]},
    "accessInfo": {"accessAllowedFrom": "EVERYWHERE", "viewability": "ALL", "isPublicDomain": True}}
zb.download_via_iiif = fake_download
zb.run_ocrmypdf = failing_ocr
out_dir = tmp / "zb"
log = io.StringIO()
with redirect_stdout(log):
    rc = zb.main(["--id", "digibok_2000010100001", "--out", str(out_dir), "--ocr", "tesseract"])
pdfs = sorted(p.name for p in out_dir.glob("*.pdf"))
check("exit 5", rc, 5)
check("shrunk PDF and the unshrunk copy", [p.endswith(".original.pdf") for p in pdfs], [True, False])
orig = next(out_dir.glob("*.original.pdf"))
main_pdf = next(p for p in out_dir.glob("*.pdf") if not p.name.endswith(".original.pdf"))
check("the copy is unshrunk (JPEG pages)", page_images(orig)[0][0], "/DCTDecode")
check("the delivered PDF is shrunk (G4 pages)", page_images(main_pdf)[0][0], "/CCITTFaxDecode")
check("the log gives ocrmypdf's own error", "jsonschema" in log.getvalue(), True)
check("the log says how to retry", "ocr_chunked.py --pdf" in log.getvalue(), True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
