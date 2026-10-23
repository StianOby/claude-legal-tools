#!/usr/bin/env python3
"""
shrink_pdf.py — recompress embedded images in a PDF to reduce file size,
without touching the OCR text layer.

Use this instead of re-running OCR to shrink a PDF. The OCR layer is already
correct — the size problem is purely image encoding — so this walks each
page's image XObjects and re-encodes them.

Usage:

    python shrink_pdf.py --pdf book.pdf                     # sibling file
    python shrink_pdf.py --pdf book.pdf --in-place
    python shrink_pdf.py --pdf book.pdf --mode grey         # keep grey tones
    python shrink_pdf.py --pdf book.pdf --mode jpeg --max-width 800

Modes (--mode):
    bitonal (default) — text pages become pure black and white, scaled up
        2x from nb.no's half-size pages and stored losslessly as CCITT G4
        (fax compression; every PDF reader shows it). About 60 KB a page
        and sharper than JPEG. Pages with pictures (more than 1 % of the
        page in photo-like blocks: covers, photos, marbled endpapers) and
        pages below 100 dpi stay greyscale/colour JPEG instead. Loses grey
        tones on text pages: faint pencil turns black, stamps become
        outlines. Thresholding is adaptive (Sauvola), so yellowed paper and
        shadows near the spine come out clean.
    grey — JPEG at the image's own size, greyscale unless the page is a
        picture page. For books where grey tones matter. ~200 KB a page.
    jpeg — the pre-1.5 shrink: JPEG resized to --max-width (default 800 px),
        colour kept. Soft on small print.

What it does, per page, per image XObject (including images nested inside
Form XObjects, which `page.images` does not see):
    1. Decode via pikepdf.PdfImage → PIL.
    2. Skip 1-bit images (already bitonal), masked images and tiny ones.
    3. Re-encode per --mode.
    4. Replace the in-PDF XObject stream in whichever /XObject dictionary
       referenced it (the page's, or a form's), so the content stream still
       finds the image by name. An image shared by several pages is
       re-encoded once and every reference is pointed at the new stream.

The PDF page tree, text-extraction layer, and bookmarks are untouched.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple


MODES = ("bitonal", "grey", "jpeg")


def _ensure_deps():
    """Import pikepdf and PIL (and numpy, which the bitonal mode needs),
    installing them to the persistent target if necessary. Mirrors the
    install pattern from zotero_book.py / ocr_chunked.py so shrink_pdf.py
    works as a standalone CLI too."""
    try:
        import pikepdf  # type: ignore
        from PIL import Image  # type: ignore
        import numpy  # type: ignore  # noqa: F401
        return pikepdf, Image
    except ImportError:
        pass

    target = os.environ.get("NBNO_PYLIB")
    if not target:
        out = os.environ.get("NBNO_OUT_DIR")
        target = str((Path(out) / "_pylib").resolve()) if out else str(
            Path.home() / ".local" / "share" / "nbno" / "_pylib"
        )
    Path(target).mkdir(parents=True, exist_ok=True)
    if target not in sys.path:
        sys.path.insert(0, target)

    missing = []
    try:
        import pikepdf  # type: ignore  # noqa
    except ImportError:
        missing.append("pikepdf")
    try:
        from PIL import Image  # type: ignore  # noqa
    except ImportError:
        missing.append("Pillow")
    try:
        import numpy  # type: ignore  # noqa
    except ImportError:
        missing.append("numpy")

    if missing:
        import subprocess
        print(f"[shrink] installing {missing} -> {target}", file=sys.stderr)
        rc = subprocess.call([
            sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
            "--break-system-packages", "--target", target, "--upgrade",
            *missing,
        ])
        if rc != 0:
            sys.exit(
                f"ERROR: failed to install {missing}. "
                f"pip install --target {target} {' '.join(missing)}"
            )
    import pikepdf  # type: ignore
    from PIL import Image  # type: ignore
    return pikepdf, Image


def estimate_output(in_pdf: Path, quality: int, max_width: int,
                    sample_index: Optional[int] = None,
                    mode: str = "bitonal") -> dict:
    """Probe one representative page; extrapolate to full PDF.

    Halving dimensions and quality does *not* halve text-heavy book pages —
    high-frequency typographic detail is incompressible at any reasonable
    JPEG quality. Predicting size from a heuristic burns time; probing one
    page and multiplying converges to the target in one shot.

    Returns a dict with: pages (int), probe_page (1-based index),
    probe_bytes (size of the recompressed single-page PDF on disk),
    estimated_total_bytes (probe_bytes * pages * 0.95, accounting for
    shared resources amortising over the full PDF).
    """
    import tempfile
    pikepdf, _ = _ensure_deps()

    def _mkpath(prefix: str) -> Path:
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix=prefix)
        os.close(fd)
        return Path(path)

    probe_src: Optional[Path] = None
    probe_out: Optional[Path] = None
    try:
        with pikepdf.Pdf.open(str(in_pdf)) as src:
            n_pages = len(src.pages)
            if n_pages == 0:
                return {"pages": 0, "probe_page": 0, "probe_bytes": 0,
                        "estimated_total_bytes": 0}
            # Middle page by default — covers and title pages are atypical
            # and would skew the estimate.
            idx = sample_index if sample_index is not None else n_pages // 2
            idx = max(0, min(idx, n_pages - 1))
            probe = pikepdf.Pdf.new()
            probe.pages.append(src.pages[idx])
            probe_src = _mkpath("shrink-probe-in-")
            probe.save(str(probe_src))
            probe.close()
        probe_out = _mkpath("shrink-probe-out-")
        stats = recompress(probe_src, probe_out, quality=quality,
                           max_width=max_width, mode=mode)
        probe_bytes = stats["bytes_after"]
        estimated = int(probe_bytes * n_pages * 0.95)
        return {
            "pages": n_pages,
            "probe_page": idx + 1,
            "probe_bytes": probe_bytes,
            "estimated_total_bytes": estimated,
        }
    finally:
        for p in (probe_src, probe_out):
            if p is None:
                continue
            try:
                p.unlink()
            except OSError:
                pass


def _iter_images(resources, Name, depth: int = 0):
    """Yield (xobject_dict, name, stream) for every image XObject reachable
    from a /Resources dictionary, descending into Form XObjects.

    Walks the dictionaries directly instead of using `page.images`, which
    is deprecated in pikepdf 10.11 and only lists images placed straight on
    the page: a scan wrapped in a Form XObject (some producers do this)
    made the old loop report images_seen=0 and leave the file unshrunk.
    """
    if resources is None or depth > 16:
        return
    try:
        xobjs = resources.get("/XObject")
    except Exception:
        return
    if xobjs is None:
        return
    for name, obj in list(xobjs.items()):
        try:
            subtype = obj.get("/Subtype")
        except Exception:
            continue
        if subtype == Name.Image:
            yield xobjs, name, obj
        elif subtype == Name.Form:
            try:
                inner = obj.get("/Resources")
            except Exception:
                continue
            yield from _iter_images(inner, Name, depth + 1)


# Bitonal needs ~250 dpi of black and white to draw letters cleanly: pages
# at or above that are thresholded as they are, pages from 100 dpi (nb.no's
# half size is ~110-150) are scaled up 2x first, and pages below that
# (nb.no's quarter size, ~70 dpi) come out blotchy and stay JPEG.
BITONAL_NATIVE_DPI = 250
BITONAL_MIN_DPI = 100
# A page is a picture page when more than this share of its ~11 mm blocks
# are mostly mid-grey. Measured 2026-10-23 on nb.no scans: text pages,
# line-drawn maps and sections 0-0.3 %; a text page with a photo covering
# 8 % of it 7.5 %; covers and marbled endpapers 84-100 %.
PICTURE_BLOCK_SHARE = 0.01


def _image_dpi(pil, page) -> float:
    """Vertical resolution of an image drawn over the page's full height.
    nbno's PDFs put one page-filling image on each page; for an image that
    covers less of the page this underestimates, which only errs towards
    JPEG or a 2x scale-up."""
    try:
        box = [float(v) for v in page.mediabox]
        height_in = abs(box[3] - box[1]) / 72.0
    except Exception:
        return 0.0
    return pil.height / height_in if height_in > 0 else 0.0


def _is_picture_page(grey, dpi: float) -> bool:
    """True when the page has photo-like areas that thresholding would ruin.

    Levels are normalised from the page's own ink (1st percentile) to its
    paper (90th), so yellowed paper and faint print count the same as
    fresh ones; then each ~11 mm block's share of mid-grey pixels is taken.
    Text and line art only have mid-grey at letter edges (at most ~25 % of
    a block); halftone photos and marbling are mostly mid-grey. The range
    is at least 80 grey levels below the paper, or the texture of a nearly
    blank page (title pages, a library slip) would count as mid-grey.
    """
    import numpy as np
    g = np.asarray(grey, dtype=np.float32)
    ink, paper = np.percentile(g, 1), np.percentile(g, 90)
    span = max(float(paper - ink), 80.0)
    n = (g - (paper - span)) / span
    mid = ((n > 0.2) & (n < 0.8)).astype(np.float32)
    b = max(16, round((dpi or 145) * 0.44))
    h, w = (mid.shape[0] // b) * b, (mid.shape[1] // b) * b
    if h < 3 * b or w < 3 * b:
        return False
    blocks = mid[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    # The outermost ring of blocks is left out: it holds the shadow at the
    # edge of the scan and the gutter, which old books have on every page.
    return float((blocks[1:-1, 1:-1] > 0.35).mean()) > PICTURE_BLOCK_SHARE


def _sauvola_threshold(a, window: int, k: float = 0.15, r: float = 128.0):
    """Sauvola's local threshold surface for an 8-bit grey array, from box
    sums over `window` x `window` pixels (integral images)."""
    import numpy as np
    a = a.astype(np.float64)
    pad = window // 2
    p = np.pad(a, ((pad + 1, pad), (pad + 1, pad)), mode="reflect")
    ii = p.cumsum(0).cumsum(1)
    ii2 = (p * p).cumsum(0).cumsum(1)
    h, w = a.shape

    def box(i):
        return (i[window:window + h, window:window + w] - i[0:h, window:window + w]
                - i[window:window + h, 0:w] + i[0:h, 0:w])
    n = float(window * window)
    mean = box(ii) / n
    std = np.sqrt(np.maximum(box(ii2) / n - mean * mean, 0))
    return mean * (1 + k * (std / r - 1))


def to_bitonal(grey, factor: int, dpi: float):
    """Grey PIL image at `dpi` -> mode "1" image `factor` times as large.

    The threshold surface is computed at half the source size, over a
    window of ~2.7 mm (31 px at 290 dpi, the size that worked on nb.no
    scans), and scaled up with the bicubically enlarged page. That is 4x
    cheaper than thresholding the enlarged page and agreed with it on
    99.9 % of pixels on a test page, with no visible difference.
    """
    import numpy as np
    from PIL import Image
    small = grey.resize((max(1, grey.width // 2), max(1, grey.height // 2)), Image.BOX)
    window = max(3, round(dpi / 2 * 2.7 / 25.4) | 1)
    th = _sauvola_threshold(np.asarray(small, dtype=np.uint8), window)
    th = Image.fromarray(np.clip(th + 0.5, 0, 255).astype(np.uint8))
    size = (grey.width * factor, grey.height * factor)
    big = grey.resize(size, Image.BICUBIC) if factor > 1 else grey
    return Image.fromarray(np.asarray(big) > np.asarray(th.resize(size, Image.BILINEAR)))


def g4_encode(bw) -> Tuple[bytes, bool]:
    """Mode "1" image -> (CCITT G4 data, BlackIs1) for a /CCITTFaxDecode
    stream. Pillow (libtiff) writes a one-strip TIFF; the strip is the
    stream. BlackIs1 follows the TIFF's photometric tag: Pillow writes
    MinIsBlack, which needs BlackIs1 true (checked by rendering the PDF
    with MuPDF: pixel for pixel the same image)."""
    buf = io.BytesIO()
    bw.save(buf, "TIFF", compression="group4", strip_size=1 << 30)
    data = buf.getvalue()
    from PIL import Image
    tif = Image.open(io.BytesIO(data))
    offsets, counts = tif.tag_v2[273], tif.tag_v2[279]
    if len(offsets) != 1:
        raise ValueError(f"expected one TIFF strip, got {len(offsets)}")
    return data[offsets[0]:offsets[0] + counts[0]], tif.tag_v2.get(262, 0) == 1


def _is_colour(pil) -> bool:
    """A colour picture (a cover), as opposed to a grey page on tinted
    paper: yellowed paper reaches ~40 on the 95th-percentile spread
    between channels, colour covers ~50-100."""
    if pil.mode != "RGB":
        return False
    import numpy as np
    a = np.asarray(pil.resize((max(1, pil.width // 4), max(1, pil.height // 4))), dtype=np.int16)
    return float(np.percentile(a.max(2) - a.min(2), 95)) > 45


def _jpeg_stream(pdf, Name, pil, quality: int):
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=quality, optimize=True)
    st = pdf.make_stream(buf.getvalue())
    d = st.stream_dict
    d[Name.Type] = Name.XObject
    d[Name.Subtype] = Name.Image
    d[Name.Width] = pil.width
    d[Name.Height] = pil.height
    d[Name.ColorSpace] = Name.DeviceGray if pil.mode == "L" else Name.DeviceRGB
    d[Name.BitsPerComponent] = 8
    d[Name.Filter] = Name.DCTDecode
    return st


def _g4_stream(pdf, pikepdf, Name, bw):
    data, black_is_1 = g4_encode(bw)
    st = pdf.make_stream(data)
    d = st.stream_dict
    d[Name.Type] = Name.XObject
    d[Name.Subtype] = Name.Image
    d[Name.Width] = bw.width
    d[Name.Height] = bw.height
    d[Name.ColorSpace] = Name.DeviceGray
    d[Name.BitsPerComponent] = 1
    d[Name.Filter] = Name.CCITTFaxDecode
    d[Name.DecodeParms] = pikepdf.Dictionary(
        K=-1, Columns=bw.width, Rows=bw.height, BlackIs1=black_is_1)
    return st


def recompress(in_pdf: Path, out_pdf: Path, quality: int = 60,
               max_width: Optional[int] = None, jpeg_min_dim: int = 64,
               mode: str = "bitonal") -> dict:
    """Recompress raster images in `in_pdf`, write to `out_pdf`.

    `max_width` resizes in jpeg mode only (default 800 there); grey and
    bitonal keep each image's own size.

    Returns a stats dict: {pages, images_seen, images_rewritten,
    images_bitonal, images_kept_picture, images_skipped_mono,
    images_skipped_small, bytes_before, bytes_after}.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    pikepdf, Image = _ensure_deps()
    from pikepdf import PdfImage, Name
    if mode == "jpeg" and max_width is None:
        max_width = 800

    bytes_before = in_pdf.stat().st_size
    same_path = (in_pdf.resolve() == out_pdf.resolve())
    pdf = pikepdf.open(str(in_pdf), allow_overwriting_input=same_path)

    stats = {
        "pages": len(pdf.pages),
        "images_seen": 0,
        "images_rewritten": 0,
        "images_bitonal": 0,
        "images_kept_picture": 0,
        "images_skipped_mono": 0,
        "images_skipped_small": 0,
        "bytes_before": bytes_before,
        "bytes_after": 0,
    }

    # objgen of an original image stream -> the stream that replaced it, so
    # a bitmap referenced from several pages (or several forms) is decoded
    # and re-encoded once, and no reference keeps the old bytes alive in
    # the output.
    replaced = {}

    for page in pdf.pages:
        try:
            # pikepdf pushes inherited /Resources down onto the page, so a
            # missing key here means the page really has none.
            resources = page.obj.get("/Resources")
        except Exception:
            continue
        for xobjs, name, raw in list(_iter_images(resources, Name)):
            stats["images_seen"] += 1
            try:
                key = tuple(raw.objgen)
            except Exception:
                key = None
            if key and key != (0, 0) and key in replaced:
                xobjs[name] = replaced[key]
                stats["images_rewritten"] += 1
                continue
            # Masks and decode arrays change what the pixels mean; leave
            # such images as they are.
            if any(k in raw for k in ("/SMask", "/Mask", "/Decode", "/ImageMask")):
                continue
            try:
                pdfimg = PdfImage(raw)
                pil = pdfimg.as_pil_image()
            except Exception:
                continue
            # 1-bit images (line art, or already bitonal) get bigger and
            # uglier as JPEG and have nothing to gain — leave them alone.
            if pil.mode == "1":
                stats["images_skipped_mono"] += 1
                continue
            # Tiny stamps / icons rarely benefit and risk visible artefacts.
            if min(pil.size) < jpeg_min_dim:
                stats["images_skipped_small"] += 1
                continue

            if pil.mode not in ("RGB", "L"):
                pil = pil.convert("RGB")
            new_stream = None
            if mode == "jpeg":
                if max_width and pil.width > max_width:
                    new_h = max(1, round(pil.height * max_width / pil.width))
                    pil = pil.resize((max_width, new_h), Image.LANCZOS)
                new_stream = _jpeg_stream(pdf, Name, pil, quality)
            else:
                grey = pil.convert("L")
                dpi = _image_dpi(pil, page)
                picture = _is_picture_page(grey, dpi)
                if mode == "bitonal" and not picture and dpi >= BITONAL_MIN_DPI:
                    factor = 1 if dpi >= BITONAL_NATIVE_DPI else 2
                    new_stream = _g4_stream(pdf, pikepdf, Name, to_bitonal(grey, factor, dpi))
                    stats["images_bitonal"] += 1
                else:
                    if picture:
                        stats["images_kept_picture"] += 1
                    keep = pil if picture and _is_colour(pil) else grey
                    new_stream = _jpeg_stream(pdf, Name, keep, quality)

            xobjs[name] = new_stream
            if key and key != (0, 0):
                replaced[key] = new_stream
            stats["images_rewritten"] += 1

    pdf.save(str(out_pdf))
    pdf.close()
    stats["bytes_after"] = out_pdf.stat().st_size
    return stats


def _default_out_path(in_pdf: Path, mode: str, quality: int,
                      max_width: Optional[int]) -> Path:
    suffix = f"_{mode}"
    if mode != "bitonal":
        suffix += f"_q{quality}"
    if mode == "jpeg" and max_width:
        suffix += f"_w{max_width}"
    return in_pdf.with_name(f"{in_pdf.stem}{suffix}.pdf")


def format_stats(stats: dict) -> str:
    line = (f"[shrink] pages={stats['pages']} "
            f"images: seen={stats['images_seen']} "
            f"rewritten={stats['images_rewritten']}")
    if stats.get("images_bitonal") or stats.get("images_kept_picture"):
        line += (f" bitonal={stats['images_bitonal']} "
                 f"picture_pages_kept_as_jpeg={stats['images_kept_picture']}")
    return line + (f" skipped_mono={stats['images_skipped_mono']} "
                   f"skipped_small={stats['images_skipped_small']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pdf", required=True, help="Input PDF.")
    ap.add_argument("--out", default=None,
                    help="Output PDF. Default: a sibling file named "
                         "<stem>_<mode>[_q<quality>][_w<width>].pdf. Use "
                         "--in-place to overwrite the input instead.")
    ap.add_argument("--in-place", action="store_true",
                    help="Overwrite --pdf instead of writing to a sibling. "
                         "Re-encoding an already-shrunk file compounds JPEG "
                         "artefacts (bitonal pages are left alone), so keep "
                         "the original until you have checked the result.")
    ap.add_argument("--mode", choices=MODES, default="bitonal",
                    help="bitonal (default): text pages as black-and-white "
                         "CCITT G4 (~60 KB/page from nb.no's half-size "
                         "pages), picture pages as JPEG. grey: greyscale JPEG "
                         "at the image's own size (~200 KB/page), for books "
                         "where grey tones matter. jpeg: the pre-1.5 shrink, "
                         "JPEG resized to --max-width.")
    ap.add_argument("--quality", type=int, default=60,
                    help="JPEG quality 1-95 for JPEG-encoded pages "
                         "(default: 60).")
    ap.add_argument("--max-width", type=int, default=None,
                    help="jpeg mode only: resize images so width <= this "
                         "value (default: 800 px). 0 disables resizing.")
    ap.add_argument("--probe-only", action="store_true",
                    help="Recompress one middle page, print the estimated "
                         "total output size, exit without writing.")
    args = ap.parse_args(argv)

    in_pdf = Path(args.pdf).expanduser().resolve()
    if not in_pdf.exists():
        sys.exit(f"ERROR: {in_pdf} does not exist.")

    if args.max_width is None and args.mode == "jpeg":
        args.max_width = 800
    if args.out:
        out_pdf = Path(args.out).expanduser().resolve()
    elif args.in_place:
        out_pdf = in_pdf
    else:
        out_pdf = _default_out_path(in_pdf, args.mode, args.quality, args.max_width)

    # Pin pip installs to outputs/ so they survive Cowork bash boundaries.
    os.environ.setdefault("NBNO_OUT_DIR", str(out_pdf.parent))

    bytes_before = in_pdf.stat().st_size
    print(f"[shrink] input: {in_pdf.name} ({bytes_before/1e6:.1f} MB)")
    print(f"[shrink] settings: mode={args.mode}, quality={args.quality}"
          + (f", max_width={args.max_width or 'none'}" if args.mode == "jpeg" else ""))

    print("[shrink] probing one middle page to estimate output size...")
    est = estimate_output(in_pdf, args.quality, args.max_width, mode=args.mode)
    if est["pages"]:
        print(f"[shrink] probe: page {est['probe_page']}/{est['pages']} "
              f"recompresses to {est['probe_bytes']/1e3:.0f} KB")
        print(f"[shrink] estimated output: "
              f"~{est['estimated_total_bytes']/1e6:.0f} MB "
              f"(probe × pages × 0.95)")
    if args.probe_only:
        return 0

    print(f"[shrink] writing to {out_pdf.name}"
          + (" (in place)" if out_pdf == in_pdf else ""))
    stats = recompress(in_pdf, out_pdf, quality=args.quality,
                       max_width=args.max_width, mode=args.mode)
    saved = stats["bytes_before"] - stats["bytes_after"]
    pct = (saved / stats["bytes_before"] * 100) if stats["bytes_before"] else 0
    print(format_stats(stats))
    print(
        f"[shrink] {stats['bytes_before']/1e6:.1f} MB "
        f"-> {stats['bytes_after']/1e6:.1f} MB "
        f"(saved {saved/1e6:.1f} MB, {pct:.0f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())