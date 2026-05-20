#!/usr/bin/env python3
"""
shrink_pdf.py — recompress embedded images in a PDF to reduce file size,
without touching the OCR text layer.

Use this instead of re-running OCR to shrink a PDF. tesseract-generated PDFs
from high-res IIIF tiles routinely come out at 800+ MB because each page is
embedded as a lossless Flate-compressed PNG. The OCR layer is already
correct — the size problem is purely image encoding. Walking each page's
XObjects and re-encoding the bitmaps as JPEG drops file size 2–3× in
~30 s/100 pages with no OCR variance, vs ~minutes to re-OCR.

Usage:

    python shrink_pdf.py --pdf book.pdf                 # in-place
    python shrink_pdf.py --pdf book.pdf --out smaller.pdf
    python shrink_pdf.py --pdf book.pdf --quality 80
    python shrink_pdf.py --pdf book.pdf --max-width 2200

What it does, per page, per image XObject:
    1. Decode via pikepdf.PdfImage → PIL.
    2. Skip 1-bit monochrome images (re-encoding them as RGB JPEG would
       grow the file *and* visibly degrade them).
    3. Optionally resize down so max(width) ≤ --max-width.
    4. Re-encode as JPEG (DCTDecode) at the given quality.
    5. Replace the in-PDF XObject stream, preserving the existing
       /Resources/XObject reference so the page's content stream still
       finds the image by name.

The PDF page tree, text-extraction layer, and bookmarks are untouched.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path
from typing import List, Optional


def _ensure_deps():
    """Import pikepdf and PIL, installing them to the persistent target if
    necessary. Mirrors the install pattern from zotero_book.py /
    ocr_chunked.py so shrink_pdf.py works as a standalone CLI too."""
    try:
        import pikepdf  # type: ignore
        from PIL import Image  # type: ignore
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

    if missing:
        import subprocess
        print(f"[shrink] installing {missing} -> {target}", file=sys.stderr)
        rc = subprocess.call([
            sys.executable, "-m", "pip", "install", "--quiet",
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
                    sample_index: Optional[int] = None) -> dict:
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
                           max_width=max_width)
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


def recompress(in_pdf: Path, out_pdf: Path, quality: int = 70,
               max_width: int = 900, jpeg_min_dim: int = 64) -> dict:
    """Recompress raster images in `in_pdf`, write to `out_pdf`.

    Returns a stats dict: {pages, images_seen, images_rewritten,
    images_skipped_mono, images_skipped_small, bytes_before, bytes_after}.
    """
    pikepdf, Image = _ensure_deps()
    from pikepdf import PdfImage, Name

    bytes_before = in_pdf.stat().st_size
    same_path = (in_pdf.resolve() == out_pdf.resolve())
    pdf = pikepdf.open(str(in_pdf), allow_overwriting_input=same_path)

    stats = {
        "pages": len(pdf.pages),
        "images_seen": 0,
        "images_rewritten": 0,
        "images_skipped_mono": 0,
        "images_skipped_small": 0,
        "bytes_before": bytes_before,
        "bytes_after": 0,
    }

    for page in pdf.pages:
        try:
            page_images = page.images
        except Exception:
            continue
        for name, raw in list(page_images.items()):
            stats["images_seen"] += 1
            try:
                pdfimg = PdfImage(raw)
                pil = pdfimg.as_pil_image()
            except Exception:
                continue
            # 1-bit monochrome scans (typical for line art) get bigger and
            # uglier as RGB JPEG — leave them alone.
            if pil.mode == "1":
                stats["images_skipped_mono"] += 1
                continue
            # Tiny stamps / icons rarely benefit and risk visible artefacts.
            if min(pil.size) < jpeg_min_dim:
                stats["images_skipped_small"] += 1
                continue

            if pil.mode not in ("RGB", "L"):
                pil = pil.convert("RGB")
            if max_width and pil.width > max_width:
                new_h = max(1, round(pil.height * max_width / pil.width))
                pil = pil.resize((max_width, new_h), Image.LANCZOS)

            buf = io.BytesIO()
            pil.save(buf, "JPEG", quality=quality, optimize=True)
            new_stream = pdf.make_stream(buf.getvalue())
            d = new_stream.stream_dict
            d[Name.Type] = Name.XObject
            d[Name.Subtype] = Name.Image
            d[Name.Width] = pil.width
            d[Name.Height] = pil.height
            d[Name.ColorSpace] = (
                Name.DeviceGray if pil.mode == "L" else Name.DeviceRGB
            )
            d[Name.BitsPerComponent] = 8
            d[Name.Filter] = Name.DCTDecode

            page.obj["/Resources"]["/XObject"][name] = new_stream
            stats["images_rewritten"] += 1

    pdf.save(str(out_pdf))
    pdf.close()
    stats["bytes_after"] = out_pdf.stat().st_size
    return stats


def _default_out_path(in_pdf: Path, quality: int, max_width: int) -> Path:
    suffix = f"_q{quality}"
    if max_width:
        suffix += f"_w{max_width}"
    return in_pdf.with_name(f"{in_pdf.stem}{suffix}.pdf")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pdf", required=True, help="Input PDF.")
    ap.add_argument("--out", default=None,
                    help="Output PDF. Default: a sibling file named "
                         "<stem>_q<quality>[_w<width>].pdf. Use --in-place "
                         "to overwrite the input instead.")
    ap.add_argument("--in-place", action="store_true",
                    help="Overwrite --pdf instead of writing to a sibling. "
                         "Discouraged for first runs: re-encoding an "
                         "already-shrunk file compounds JPEG artefacts. "
                         "Prefer the default sibling output, then rename "
                         "manually once you've inspected the result.")
    ap.add_argument("--quality", type=int, default=70,
                    help="JPEG quality 1-95 (default: 70 — targets ~143 "
                         "KB/page for text-heavy nb.no scans, i.e. ~50 MB "
                         "for a 350-page book).")
    ap.add_argument("--max-width", type=int, default=900,
                    help="Resize images so width <= this value (default: "
                         "900 px). 0 disables resizing. Default is tuned "
                         "for legible book text at typical Zotero sizes.")
    ap.add_argument("--probe-only", action="store_true",
                    help="Recompress one middle page, print the estimated "
                         "total output size, exit without writing.")
    args = ap.parse_args(argv)

    in_pdf = Path(args.pdf).expanduser().resolve()
    if not in_pdf.exists():
        sys.exit(f"ERROR: {in_pdf} does not exist.")

    if args.out:
        out_pdf = Path(args.out).expanduser().resolve()
    elif args.in_place:
        out_pdf = in_pdf
    else:
        out_pdf = _default_out_path(in_pdf, args.quality, args.max_width)

    # Pin pip installs to outputs/ so they survive Cowork bash boundaries.
    os.environ.setdefault("NBNO_OUT_DIR", str(out_pdf.parent))

    bytes_before = in_pdf.stat().st_size
    print(f"[shrink] input: {in_pdf.name} ({bytes_before/1e6:.1f} MB)")
    print(f"[shrink] settings: quality={args.quality}, "
          f"max_width={args.max_width or 'none'}")

    print("[shrink] probing one middle page to estimate output size...")
    est = estimate_output(in_pdf, args.quality, args.max_width)
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
                       max_width=args.max_width)
    saved = stats["bytes_before"] - stats["bytes_after"]
    pct = (saved / stats["bytes_before"] * 100) if stats["bytes_before"] else 0
    print(
        f"[shrink] pages={stats['pages']} "
        f"images: seen={stats['images_seen']} "
        f"rewritten={stats['images_rewritten']} "
        f"skipped_mono={stats['images_skipped_mono']} "
        f"skipped_small={stats['images_skipped_small']}"
    )
    print(
        f"[shrink] {stats['bytes_before']/1e6:.1f} MB "
        f"-> {stats['bytes_after']/1e6:.1f} MB "
        f"(saved {saved/1e6:.1f} MB, {pct:.0f}%)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())