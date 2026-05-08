#!/usr/bin/env python3
"""
capture_cookie.py — capture an nb.no auth cookie for use with the `nbno` CLI.

Opens a real Chromium window via Playwright. You log in to nb.no — FEIDE,
BankID, Vipps, institutional sign-in, whatever method nb.no offers you — and
then open any digitised item. The script listens for the IIIF "manifest"
request the page makes when the viewer loads, captures the outgoing
`authorization` and `cookie` headers, and writes them to ~/.nbno/cookie.txt
in the format the `nbno` CLI expects:

    authorization=<token>
    cookie=<full cookie header>

After this runs once, the nbno_run.sh wrapper can pick up the cookie
automatically with `--cookie auto`. Cookies typically live ~24-48h; re-run
this script when downloads start failing with auth errors.

One-time setup (your own machine, NOT the sandbox):
    pip install playwright
    playwright install chromium

Run:
    python capture_cookie.py
    python capture_cookie.py --out C:\\Users\\me\\nbno\\cookie.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.stderr.write(
        "Playwright is not installed. Install it once with:\n"
        "    pip install playwright\n"
        "    playwright install chromium\n"
    )
    sys.exit(2)

DEFAULT_OUT = Path.home() / ".nbno" / "cookie.txt"
NBNO_HOME = "https://www.nb.no/"

# A request URL is treated as "the IIIF manifest call we need" if it contains
# all of these substrings. This matches:
#   https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb_digibok_.../manifest?fields=...
MANIFEST_PARTS = ("api.nb.no", "iiif", "manifest")
LOGIN_TIMEOUT_S = 600   # 10 minutes is plenty even with 2FA


async def capture(out_path: Path, headless: bool) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        captured: dict[str, object] = {}
        first_seen = asyncio.Event()

        async def handle_request(request) -> None:
            url = request.url
            if all(part in url for part in MANIFEST_PARTS) and not captured:
                try:
                    headers = await request.all_headers()
                except Exception as exc:
                    sys.stderr.write(f"  could not read headers: {exc}\n")
                    return
                captured["url"] = url
                captured["headers"] = headers
                first_seen.set()

        page.on(
            "request",
            lambda request: asyncio.create_task(handle_request(request)),
        )

        await page.goto(NBNO_HOME)

        print()
        print("=" * 64)
        print(" nb.no cookie capture")
        print("=" * 64)
        print()
        print(" A Chromium window has opened at https://www.nb.no/.")
        print()
        print(" 1. Click 'Logg inn' (top right).")
        print(" 2. Choose FEIDE (or BankID / Vipps / library card) and")
        print("    complete login, including any 2FA prompt.")
        print(" 3. Once logged in, open any digitised item — a book, news-")
        print("    paper, photograph, manuscript, etc. Wait for the page")
        print("    viewer to start rendering pages.")
        print()
        print(f" Listening for IIIF manifest request (timeout: "
              f"{LOGIN_TIMEOUT_S // 60} min)...")
        print()

        try:
            await asyncio.wait_for(first_seen.wait(), timeout=LOGIN_TIMEOUT_S)
        except asyncio.TimeoutError:
            sys.stderr.write(
                "ERROR: timed out without seeing a manifest request.\n"
                "       Make sure you opened a digitised item with the page\n"
                "       viewer visible, not just a search-results page.\n"
            )
            await browser.close()
            sys.exit(3)

        headers = captured.get("headers", {}) or {}
        # Playwright lowercases header names in all_headers().
        auth = headers.get("authorization", "")
        cookie = headers.get("cookie", "")

        if not cookie:
            sys.stderr.write(
                "WARNING: captured manifest request had no cookie header.\n"
                "         Login may not have completed before the request\n"
                "         fired. Try re-running and waiting until the book\n"
                "         viewer is fully loaded.\n"
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f"authorization={auth}\ncookie={cookie}\n",
            encoding="utf-8",
        )

        print()
        print(f" Cookie written to: {out_path}")
        print(f"   manifest URL was: {captured.get('url')}")
        print()
        print(" You can now run:")
        print(f"   nbno --id <ID> --cookie {out_path}")
        print(" or via the wrapper:")
        print("   bash nbno_run.sh --id <ID> --out <dir> --cookie auto")
        print()
        print(" Cookies on nb.no typically live ~24-48h. Re-run this script")
        print(" when downloads start failing with auth errors.")
        print()

        await browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Capture an nb.no auth cookie via Playwright.",
    )
    ap.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"Where to write the cookie file (default: {DEFAULT_OUT}).",
    )
    ap.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless. Only useful if you are reusing an "
             "existing Playwright user-data-dir already logged in.",
    )
    args = ap.parse_args()

    out_path = Path(args.out).expanduser()
    asyncio.run(capture(out_path, args.headless))


if __name__ == "__main__":
    main()
