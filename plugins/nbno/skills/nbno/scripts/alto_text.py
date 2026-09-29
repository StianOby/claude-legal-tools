#!/usr/bin/env python3
"""
alto_text.py — give a downloaded nb.no PDF nb.no's own OCR as its text layer.

nb.no OCRed its scans with ABBYY and serves the result as ALTO XML, one file
per page, at

    https://api.nb.no/catalog/v1/metadata/<URN>/altos            (index)
    https://api.nb.no/catalog/v1/metadata/<URN>/altos/<canvas>   (one page)

Public-domain items serve it to anyone. For Bokhylla and FEIDE-licensed items
the endpoint answers 401 even with a logged-in session and an active loan
(verified 2026-09-29), so those books still need Tesseract.

Where ALTO is available this replaces OCR entirely: every word is written as
invisible text (render mode 3) at its ALTO position, and each page is resized
to the physical size ALTO records, the same thing nb.no's own "PDF with text"
downloads contain. The page images are not touched, so shrink_pdf.py works
on the result as usual.

The text layer uses Helvetica with WinAnsi encoding and a flat 500-unit
width for every glyph, so a word is stretched to its box with Tz without
needing font metrics. Characters outside WinAnsi (Greek, for instance)
become "?" in the text layer.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

ALTO_BASE = "https://api.nb.no/catalog/v1/metadata"

# (hpos, vpos, width, height, text) in ALTO units
Word = Tuple[float, float, float, float, str]
# (line vpos, line height, words)
Line = Tuple[float, float, List[Word]]

# Page size in ALTO units → PDF points.
_UNIT_TO_PT = {"mm10": 72 / 254, "inch1200": 72 / 1200}

_FONT_NAME = "/FNbAlto"
_GLYPH_WIDTH = 0.5   # every glyph is 500/1000 em wide in our font dict


class AltoPage:
    __slots__ = ("width", "height", "unit", "lines")

    def __init__(self, width: float, height: float, unit: str,
                 lines: List[Line]) -> None:
        self.width = width
        self.height = height
        self.unit = unit
        self.lines = lines

    @property
    def words(self) -> int:
        return sum(len(ws) for _, _, ws in self.lines)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_alto(data: bytes) -> Optional[AltoPage]:
    """Parse one ALTO file. Namespace-agnostic (nb.no serves ALTO 1.2 without
    a namespace; later versions carry one). Returns None when there is no
    Page element."""
    root = ET.fromstring(data)
    unit = "pixel"
    page_el = None
    for el in root.iter():
        name = _local(el.tag)
        if name == "MeasurementUnit" and el.text:
            unit = el.text.strip()
        elif name == "Page" and page_el is None:
            page_el = el
    if page_el is None:
        return None
    try:
        pw = float(page_el.get("WIDTH"))
        ph = float(page_el.get("HEIGHT"))
    except (TypeError, ValueError):
        return None

    lines: List[Line] = []
    for tl in page_el.iter():
        if _local(tl.tag) != "TextLine":
            continue
        words: List[Word] = []
        for el in tl:
            name = _local(el.tag)
            if name == "String":
                try:
                    words.append((float(el.get("HPOS")), float(el.get("VPOS")),
                                  float(el.get("WIDTH")), float(el.get("HEIGHT")),
                                  el.get("CONTENT") or ""))
                except (TypeError, ValueError):
                    continue
            elif name == "HYP" and words:
                # Keep the hyphen the page shows, and stretch the word over it.
                x, y, w, h, t = words[-1]
                end = float(el.get("HPOS") or x + w) + float(el.get("WIDTH") or 0)
                words[-1] = (x, y, max(w, end - x), h, t + (el.get("CONTENT") or "-"))
        words = [w for w in words if w[4].strip()]
        if not words:
            continue
        try:
            lv, lh = float(tl.get("VPOS")), float(tl.get("HEIGHT"))
        except (TypeError, ValueError):
            lv = min(w[1] for w in words)
            lh = max(w[1] + w[3] for w in words) - lv
        lines.append((lv, lh, words))
    return AltoPage(pw, ph, unit, lines)


def alto_index(urn: str, read: Callable[[str], bytes]) -> Optional[set]:
    """Canvas names that have ALTO, or None when the item's ALTO is not
    available to us (401/403/404, or no index)."""
    import json
    import urllib.error
    try:
        blob = json.loads(read(f"{ALTO_BASE}/{urn}/altos").decode("utf-8"))
    except urllib.error.HTTPError:
        return None
    links = (blob.get("_links") or {}).get("alto") or []
    names = {l["href"].rsplit("/", 1)[-1] for l in links if l.get("href")}
    return names or None


def fetch_alto_pages(urn: str, canvases: List[str], read: Callable[[str], bytes],
                     workers: int = 8) -> Dict[str, AltoPage]:
    """Fetch and parse ALTO for each canvas name. Canvases whose ALTO fails
    to download or parse are left out; the caller reports them."""

    def one(canvas: str) -> Tuple[str, Optional[AltoPage]]:
        try:
            return canvas, parse_alto(read(f"{ALTO_BASE}/{urn}/altos/{canvas}"))
        except Exception:  # noqa: BLE001 — one bad page must not stop the book
            return canvas, None

    out: Dict[str, AltoPage] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for canvas, page in pool.map(one, canvases):
            if page is not None:
                out[canvas] = page
    return out


def _pdf_hex(text: str) -> str:
    return "<" + text.encode("cp1252", errors="replace").hex() + ">"


def _text_ops(page: AltoPage, w_pt: float, h_pt: float) -> bytes:
    sx, sy = w_pt / page.width, h_pt / page.height
    ops = ["BT", "3 Tr"]
    for lv, lh, words in page.lines:
        fs = max(lh * sy, 1.0)
        baseline = h_pt - (lv + lh) * sy + 0.2 * fs
        for i, (x, _y, w, _h, t) in enumerate(words):
            # Stretch the word over its own box, then let a trailing space
            # run into the gap, so selection matches the image and text
            # extraction still gets word breaks.
            natural = len(t) * _GLYPH_WIDTH * fs
            tz = 100.0 * w * sx / natural if natural else 100.0
            if i + 1 < len(words):
                t += " "
            ops.append(f"{_FONT_NAME} {fs:.2f} Tf {tz:.1f} Tz "
                       f"1 0 0 1 {x * sx:.2f} {baseline:.2f} Tm {_pdf_hex(t)} Tj")
    ops.append("ET")
    return ("\n".join(ops) + "\n").encode("ascii")


def apply_alto(pdf_path, page_canvases: List[Optional[str]],
               altos: Dict[str, AltoPage], physical_size: bool = True) -> dict:
    """Write each page's ALTO words as invisible text, in place.

    `page_canvases[i]` is the canvas name of PDF page i+1 (None for a
    placeholder page). With `physical_size`, a page whose ALTO is measured in
    a physical unit is scaled to that size. Returns {"pages_with_text",
    "words", "resized"}.
    """
    import pikepdf
    from pikepdf import Array, Dictionary, Name

    pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica,
        Encoding=Name.WinAnsiEncoding, FirstChar=32, LastChar=255,
        Widths=Array([int(_GLYPH_WIDTH * 1000)] * 224),
    ))
    stats = {"pages_with_text": 0, "words": 0, "resized": 0}
    for page, canvas in zip(pdf.pages, page_canvases):
        alto = altos.get(canvas) if canvas else None
        if alto is None:
            continue
        x0, y0, x1, y1 = (float(v) for v in page.mediabox)
        w_pt, h_pt = x1 - x0, y1 - y0
        factor = _UNIT_TO_PT.get(alto.unit)
        if physical_size and factor:
            nw, nh = alto.width * factor, alto.height * factor
            if abs(nw - w_pt) > 0.5 or abs(nh - h_pt) > 0.5:
                kx, ky = nw / w_pt, nh / h_pt
                page.contents_add(pdf.make_stream(
                    f"q {kx:.6f} 0 0 {ky:.6f} {-x0 * kx:.4f} {-y0 * ky:.4f} cm\n"
                    .encode("ascii")), prepend=True)
                page.contents_add(pdf.make_stream(b"Q\n"))
                page.mediabox = Array([0, 0, nw, nh])
                for box in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
                    if box in page.obj:
                        del page.obj[box]
                w_pt, h_pt = nw, nh
                stats["resized"] += 1
        if not alto.lines:
            continue
        page.add_resource(font, Name.Font, Name(_FONT_NAME))
        page.contents_add(pdf.make_stream(_text_ops(alto, w_pt, h_pt)))
        stats["pages_with_text"] += 1
        stats["words"] += alto.words
    pdf.save(str(pdf_path))
    pdf.close()
    return stats
