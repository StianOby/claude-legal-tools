#!/usr/bin/env python3
"""
ocr_chunked.py — OCR a PDF in resumable chunks that fit the 45s Cowork bash
sandbox.

Splits the input PDF into single-page PDFs, OCRs each with ocrmypdf
(--skip-text, full preprocessing — same quality as a one-shot ocrmypdf run),
caches per-page output on disk, and concatenates when every page is done.
Each invocation picks up where the previous one left off, so:

    # Call until exit 0:
    python ocr_chunked.py --pdf book.pdf --out book.searchable.pdf

works whether the book is 20 pages or 500.

Cache layout (under --cache-dir, default <pdf_dir>/.ocr_cache/<pdf_stem>/):

    pages/         single-page PDFs extracted from the input
      page-0001.pdf
      ...
    ocred/         per-page OCR output (idempotent — skipped if present)
      page-0001.pdf
      ...
    manifest.json  {input_path, input_mtime, total_pages, languages}

Exit codes:
    0  every page OCRed and the merged PDF was written.
    2  partial progress — re-invoke to continue (still inside time budget).
    1  invalid arguments / unrecoverable error.

Designed for orchestration by an outer loop (`while ! python ocr_chunked.py
...; do :; done`) or for repeated invocation in a chat sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple


# Mirror the install-target / preflight helpers from zotero_book.py.
# Kept inline so ocr_chunked.py is usable as a standalone script too.

def _pylib_target() -> Path:
    out = os.environ.get("NBNO_PYLIB")
    if out:
        return Path(out).expanduser().resolve()
    out_dir = os.environ.get("NBNO_OUT_DIR")
    if out_dir:
        return Path(out_dir).expanduser().resolve() / "_pylib"
    return Path.home() / ".local" / "share" / "nbno" / "_pylib"


def _ensure_pylib_on_path() -> Path:
    target = _pylib_target()
    target.mkdir(parents=True, exist_ok=True)
    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    bin_dir = target / "bin"
    bin_dir.mkdir(exist_ok=True)
    if str(bin_dir) not in os.environ.get("PATH", "").split(":"):
        os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
    cur_pp = os.environ.get("PYTHONPATH", "")
    if str(target) not in cur_pp.split(":"):
        os.environ["PYTHONPATH"] = (
            f"{target}:{cur_pp}" if cur_pp else str(target)
        )
    return target


def _pip_install(packages: List[str]) -> int:
    target = _ensure_pylib_on_path()
    return subprocess.call([
        sys.executable, "-m", "pip", "install", "--quiet",
        "--break-system-packages", "--target", str(target), "--upgrade",
        *packages,
    ])


def _which(binary: str) -> Optional[str]:
    found = shutil.which(binary)
    if found:
        return found
    cand = _pylib_target() / "bin" / binary
    if cand.exists() and os.access(cand, os.X_OK):
        return str(cand)
    return None


def tesseract_preflight(requested: str) -> str:
    """Drop missing language packs from `requested`; warn if any are missing."""
    if shutil.which("tesseract") is None:
        return requested
    try:
        out = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return requested
    available = {
        ln.strip() for ln in (out.stdout + out.stderr).splitlines()
        if ln.strip() and not ln.startswith("List of available")
    }
    codes = [c for c in requested.split("+") if c]
    kept = [c for c in codes if c in available]
    missing = [c for c in codes if c not in available]
    if missing and kept:
        print(f"[ocr] missing tesseract pack(s): {'+'.join(missing)}; "
              f"degrading to {'+'.join(kept)}", file=sys.stderr)
        return "+".join(kept)
    return requested


def _ensure_ocrmypdf() -> str:
    binary = _which("ocrmypdf")
    if binary:
        return binary
    print("[ocr] installing ocrmypdf to persistent target...", file=sys.stderr)
    rc = _pip_install(["ocrmypdf"])
    binary = _which("ocrmypdf")
    if rc != 0 or binary is None:
        sys.exit(
            "ERROR: failed to install ocrmypdf. Install manually with: "
            f"pip install --target {_pylib_target()} ocrmypdf"
        )
    return binary


def _ensure_pikepdf():
    try:
        import pikepdf  # type: ignore
        return pikepdf
    except ImportError:
        pass
    print("[ocr] installing pikepdf to persistent target...", file=sys.stderr)
    rc = _pip_install(["pikepdf"])
    if rc != 0:
        sys.exit(
            "ERROR: failed to install pikepdf. Install manually with: "
            f"pip install --target {_pylib_target()} pikepdf"
        )
    _ensure_pylib_on_path()
    import pikepdf  # type: ignore
    return pikepdf


def _pdf_cache_key(pdf_path: Path) -> str:
    """Stable per-input-file key.

    Hashes (absolute_path, mtime, size) so re-OCRing the same file picks up
    where it left off, but a re-downloaded PDF with the same name correctly
    invalidates the cache.
    """
    st = pdf_path.stat()
    payload = f"{pdf_path.resolve()}::{st.st_mtime_ns}::{st.st_size}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _split_pages(pikepdf, pdf_path: Path, pages_dir: Path) -> int:
    """Extract each page as page-NNNN.pdf. Skips files that already exist."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    with pikepdf.Pdf.open(str(pdf_path)) as src:
        total = len(src.pages)
        for i, page in enumerate(src.pages, start=1):
            out = pages_dir / f"page-{i:04d}.pdf"
            if out.exists():
                continue
            single = pikepdf.Pdf.new()
            single.pages.append(page)
            single.save(str(out))
            single.close()
    return total


def _ocr_page(ocrmypdf_bin: str, src: Path, dst: Path,
              languages: str) -> Tuple[Path, int]:
    """OCR a single-page PDF. Returns (dst, returncode)."""
    rc = subprocess.call(
        [ocrmypdf_bin, "--language", languages, "--skip-text",
         "--optimize", "1", "--quiet", str(src), str(dst)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return dst, rc


def _is_valid_pdf(pikepdf, path: Path) -> bool:
    """Quick structural check.

    Sandbox timeouts can kill ocrmypdf mid-write, leaving files that look
    fine in `ls` but raise "root of pages tree has no /Kids array" on open.
    Without this check the resumable batch treats them as done and skips,
    so the failure only surfaces during the final merge.
    """
    try:
        with pikepdf.Pdf.open(str(path)) as src:
            return len(src.pages) > 0
    except Exception:
        return False


def _purge_corrupt_cache(pikepdf, ocred_dir: Path) -> int:
    """Walk the OCR cache and delete any file that won't open.

    Run once at startup so partially-written files from a previous,
    killed call get regenerated on this pass.
    """
    removed = 0
    for p in sorted(ocred_dir.glob("page-*.pdf")):
        if not _is_valid_pdf(pikepdf, p):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _cleanup_cache(cache_dir: Path, keep: bool) -> None:
    """Delete the per-page cache directory after a successful merge.

    Called only on the success path; partial exits leave the cache so the
    next call can resume. Also prunes the empty parent (`.ocr_cache/<stem>/`)
    to avoid littering — but only if it's actually empty after our removal.
    """
    if keep:
        print(f"[ocr] keeping intermediates: {cache_dir}", file=sys.stderr)
        return
    parent = cache_dir.parent
    shutil.rmtree(cache_dir, ignore_errors=True)
    try:
        parent.rmdir()
    except OSError:
        pass


def _merge(pikepdf, ocred_dir: Path, out_path: Path, total: int) -> None:
    merged = pikepdf.Pdf.new()
    try:
        for i in range(1, total + 1):
            p = ocred_dir / f"page-{i:04d}.pdf"
            if not p.exists():
                raise SystemExit(
                    f"ERROR: page {i} missing from OCR cache ({p})"
                )
            with pikepdf.Pdf.open(str(p)) as src:
                merged.pages.extend(src.pages)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged.save(str(out_path))
    finally:
        merged.close()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pdf", required=True, help="Input PDF to OCR.")
    ap.add_argument("--out", default=None,
                    help="Output PDF (default: overwrite --pdf in place).")
    ap.add_argument("--langs", default="nor+nno",
                    help="Tesseract language string (default: nor+nno).")
    ap.add_argument("--cache-dir", default=None,
                    help="Per-page cache root (default: "
                         "<pdf_dir>/.ocr_cache/<pdf_stem>/<hash>).")
    ap.add_argument("--time-budget", type=float, default=35.0,
                    help="Stop launching new pages after this many seconds "
                         "(default: 35; leaves headroom under a 45s sandbox).")
    ap.add_argument("--jobs", type=int, default=4,
                    help="Parallel ocrmypdf workers (default: 4).")
    ap.add_argument("--keep-intermediates", action="store_true",
                    help="Keep the per-page cache directory after merging. "
                         "By default the cache is deleted on a successful "
                         "merge; partial exits always preserve the cache so "
                         "the next call can resume.")
    args = ap.parse_args(argv)

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        sys.exit(f"ERROR: {pdf_path} does not exist.")
    out_path = Path(args.out).expanduser().resolve() if args.out else pdf_path

    # Pin pip --target installs to the output directory so they survive
    # across bash invocations in Cowork.
    os.environ.setdefault("NBNO_OUT_DIR", str(out_path.parent))

    cache_root = (
        Path(args.cache_dir).expanduser().resolve()
        if args.cache_dir
        else pdf_path.parent / ".ocr_cache" / pdf_path.stem
    )
    key = _pdf_cache_key(pdf_path)
    cache_dir = cache_root / key
    pages_dir = cache_dir / "pages"
    ocred_dir = cache_dir / "ocred"
    ocred_dir.mkdir(parents=True, exist_ok=True)

    pikepdf = _ensure_pikepdf()
    ocrmypdf_bin = _ensure_ocrmypdf()
    langs = tesseract_preflight(args.langs)

    print(f"[ocr] splitting {pdf_path.name} into per-page PDFs...",
          file=sys.stderr)
    total = _split_pages(pikepdf, pdf_path, pages_dir)

    purged = _purge_corrupt_cache(pikepdf, ocred_dir)
    if purged:
        print(f"[ocr] removed {purged} corrupt cache file(s) from a prior "
              "killed run; they will be regenerated.", file=sys.stderr)

    manifest = {
        "input_path": str(pdf_path),
        "input_mtime_ns": pdf_path.stat().st_mtime_ns,
        "total_pages": total,
        "languages": langs,
    }
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    pending: List[Path] = [
        pages_dir / f"page-{i:04d}.pdf"
        for i in range(1, total + 1)
        if not (ocred_dir / f"page-{i:04d}.pdf").exists()
    ]
    done_before = total - len(pending)
    print(f"[ocr] {done_before}/{total} pages already OCRed; "
          f"{len(pending)} pending. Budget: {args.time_budget:.0f}s, "
          f"jobs: {args.jobs}.", file=sys.stderr)

    if not pending:
        print("[ocr] all pages cached; merging output...", file=sys.stderr)
        _merge(pikepdf, ocred_dir, out_path, total)
        _cleanup_cache(cache_dir, keep=args.keep_intermediates)
        print(f"[ocr] DONE: {out_path} ({out_path.stat().st_size/1e6:.1f} MB)")
        return 0

    t0 = time.time()
    ocred_now = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        in_flight = {}
        for src in pending:
            if time.time() - t0 >= args.time_budget:
                break
            dst = ocred_dir / src.name
            fut = pool.submit(_ocr_page, ocrmypdf_bin, src, dst, langs)
            in_flight[fut] = dst
        for fut in as_completed(in_flight):
            dst, rc = fut.result()
            if rc == 0 and dst.exists() and _is_valid_pdf(pikepdf, dst):
                ocred_now += 1
            else:
                # Remove partial / structurally-broken output so the next
                # call retries. Without the _is_valid_pdf gate, sandbox
                # timeouts that kill us mid-write would leave files that
                # only fail at merge time.
                try:
                    dst.unlink()
                except OSError:
                    pass

    elapsed = time.time() - t0
    done_now = sum(
        1 for i in range(1, total + 1)
        if (ocred_dir / f"page-{i:04d}.pdf").exists()
    )
    print(f"[ocr] this call: {ocred_now} pages in {elapsed:.1f}s. "
          f"Total cached: {done_now}/{total}.", file=sys.stderr)

    if done_now < total:
        print("[ocr] PARTIAL — re-invoke to continue.", file=sys.stderr)
        return 2

    print("[ocr] all pages OCRed; merging output...", file=sys.stderr)
    _merge(pikepdf, ocred_dir, out_path, total)
    _cleanup_cache(cache_dir, keep=args.keep_intermediates)
    print(f"[ocr] DONE: {out_path} ({out_path.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
