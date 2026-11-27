#!/usr/bin/env python3
"""
geo_check.py — report the egress IP and nb.no session as nb.no sees them.

Why this exists: nb.no enforces geo-restriction at the IIIF *image resolver*,
not at the API. Manifests and catalog metadata are served worldwide with no
auth, so a run can look healthy right up until every page image returns 403.
This describes the egress IP of the shell it runs in (in a cloud Cowork session
that is Anthropic's cloud, never a Norwegian IP; in local Cowork it is the
user's own IP). The browser pane may egress from a different IP.

Deliberately talks only to nb.no. Do NOT swap in a third-party geo service
(ipinfo.io and friends) — that would leak the user's IP to an unrelated party
to learn something nb.no already tells us for free. This script does not map
the IP to a country; `https://api.nb.no/me/v1` reports the IP and the login
identity. For a geo-gated item (--id), it instead asks the image resolver for
one 1024 px tile of a mid-book page — the same request a download would make
— and nb.no's answer settles it for a NORWAY (Bokhylla) item: 200 means this
IP may read the pages, 403 that it is not Norwegian. An NB (legal-deposit)
item is `here` only when the probe is served AND the catalogue, read with
the cookie, shows the user's loan (legalDepositReservationStatus ==
TAKENBYCURRENTUSER): without a loan nb.no has served an anonymous caller
the first pages and refused the rest (2026-11-26).

Usage:
    python geo_check.py                       # anonymous view
    python geo_check.py --nbsso "nbsso=<v>"   # the user's own session
    python geo_check.py --cookie <dir>/cookie.txt   # same, from a cookie file (auth.md)
    python geo_check.py --id digibok_2008051600041   # + accessInfo + tile probe

Exit status: 0 normally; 3 when the route is norwegian-ip or
norwegian-ip+loan (this shell cannot download the pages yet); 1 when nb.no
could not be reached.

With --id the last line is `route: <here | norwegian-ip | norwegian-ip+loan |
unknown>` (also "route" in --json): what the item needs from the shell that
ran the probe. SKILL.md maps it to where the download runs.

Reading the output:
  - loginProvider null                     → not logged in (or cookie expired)
  - accessAllowedFrom EVERYWHERE           → no cookie needed
  - accessAllowedFrom NORWAY (bokhylla)    → Norwegian IP, no cookie
  - accessAllowedFrom NB                   → nbsso + a digital loan the user
                                             takes in a browser
                                             (legalDepositReservationStatus
                                             TAKENBYCURRENTUSER).
                                             Classify on this field, not on
                                             viewability/legalDepositLoginText
                                             — those invert once you log in
  - image probe: 403 on a NORWAY item     → the IP is not Norwegian; page
                                             images will 403 regardless of
                                             login. Stop before downloading.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import urllib.error
import urllib.request
from typing import Optional

# The plugin's version (plugin.json); tests/nbno checks that they agree.
VERSION = "2.0.3"
USER_AGENT = f"nbno-skill/{VERSION} (+https://github.com/StianOby/claude-legal-tools)"

ME_URL = "https://api.nb.no/me/v1"
ITEM_URL = "https://api.nb.no/catalog/v1/items/URN:NBN:no-nb_{id}"
# Two manifest endpoints with different coverage; the first 404s for many
# items (see zotero_book._fetch_manifest).
MANIFEST_URLS = (
    "https://api.nb.no/catalog/v1/items/{id}/manifest",
    "https://api.nb.no/catalog/v1/iiif/URN:NBN:no-nb_{id}/manifest",
)

# accessAllowedFrom values that mean "the resolver will geo-check you".
GEO_GATED = ("NORWAY", "NB")

# What the item needs, as far as this shell can tell. SKILL.md ("Where each
# step runs") maps it to a place: `norwegian-ip*` from the cloud sandbox means
# the local route; from the user's own machine it means the user is abroad
# (NORWAY) or has no loan / an expired cookie (NB).
ROUTES = {
    "here": "this shell can download the pages now",
    "norwegian-ip": "Bokhylla item: needs a Norwegian IP (no cookie)",
    "norwegian-ip+loan": "legal-deposit item: needs a Norwegian IP, the nbsso "
                         "cookie and an active digital loan",
    "unknown": "could not tell; see the probe line above",
}


# legalDepositReservationStatus when the caller holds the digital loan.
LOAN_TAKEN = "TAKENBYCURRENTUSER"


# probe_tile's answer when nb.no served HTTP 200 but not the 1024 px tile
# asked for: the resolver's way of refusing quietly (as it downsamples).
PROBE_SMALL = "small"
PROBE_SIZE = 1024


def decide_route(access_allowed_from: Optional[str], probe,
                 loan: Optional[str] = None, cookie: bool = False,
                 viewability: Optional[str] = None) -> str:
    if access_allowed_from == "EVERYWHERE":
        return "here"
    if access_allowed_from not in GEO_GATED:
        return "unknown"
    if access_allowed_from == "NORWAY" and (viewability or "").upper() == "NONE":
        # The catalogue says this IP may not read a Bokhylla item. On
        # 2026-11-27 the cloud sandbox got NONE here while its tile probe
        # came back 200; the user's Norwegian IP got ALL. Trust the catalogue.
        return "norwegian-ip"
    if probe == PROBE_SMALL:
        probe = 403
    if access_allowed_from == "NB":
        # A served probe is not enough: without a loan, only the first
        # pages may be served. No cookie or no loan → whatever the probe.
        if not (cookie and loan == LOAN_TAKEN):
            return "norwegian-ip+loan"
        if probe == 200:
            return "here"
        return "norwegian-ip+loan" if probe == 403 else "unknown"
    if probe == 200:
        return "here"
    if probe == 403:
        return "norwegian-ip"
    return "unknown"


def probe_canvas_index(names: list) -> Optional[int]:
    """Index of the canvas to probe: the middle numbered page, else the
    middle canvas that is not a _C2, else None (as zotero_book.py)."""
    numbered = [i for i, n in enumerate(names) if n.rsplit("_", 1)[-1].isdigit()]
    if not numbered:
        numbered = [i for i, n in enumerate(names) if not n.endswith("_C2")]
    return numbered[len(numbered) // 2] if numbered else None


def _get_json(url: str, nbsso: Optional[str], timeout: float = 30.0) -> dict:
    # `Accept: */*`, not application/json: /me/v1 serves only
    # application/hal+json and answers 406 to a narrower Accept header.
    headers = {"Accept": "*/*", "User-Agent": USER_AGENT}
    if nbsso:
        headers["cookie"] = nbsso
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def jpeg_size(data: bytes) -> Optional[tuple]:
    """(width, height) from a JPEG's SOF header, or None. No Pillow needed."""
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return (int.from_bytes(data[i + 7:i + 9], "big"),
                    int.from_bytes(data[i + 5:i + 7], "big"))
        i += 2 + length
    return None


def probe_tile(canonical: str, nbsso: Optional[str],
               timeout: float = 20.0):
    """HTTP status for one 1024 px tile of a mid-book page (200 = served),
    PROBE_SMALL when the 200 carried a smaller image than the tile asked
    for, or None when no probe could be made. Not smaller: 256 px tiles are
    served to anyone, like thumbnails; 1024 px is what the downloader
    fetches and what nb.no gates. Not the first page: those can be served
    without a loan."""
    manifest = None
    for url in MANIFEST_URLS:
        try:
            manifest = _get_json(url.format(id=canonical), nbsso, timeout)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                return None
        except (urllib.error.URLError, OSError, ValueError):
            return None
    try:
        canvases = manifest["sequences"][0]["canvases"]
        pick = probe_canvas_index([c["@id"].split("/")[-1] for c in canvases])
        base = canvases[pick]["images"][0]["resource"]["service"]["@id"]
    except (TypeError, KeyError, IndexError):
        return None
    headers = {"referer": f"https://www.nb.no/items/URN:NBN:no-nb_{canonical}",
               "User-Agent": USER_AGENT}
    if nbsso:
        headers["cookie"] = nbsso
    req = urllib.request.Request(f"{base}/0,0,1024,1024/full/0/default.jpg",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return None
    if status == 200:
        size = jpeg_size(data)
        if size is None or max(size) < PROBE_SIZE - 4:
            return PROBE_SMALL
    return status


def nbsso_from_cookie_file(path: str) -> Optional[str]:
    """The `nbsso=<v>` pair from a cookie file (a 'cookie=nbsso=<v>; _nblb=<v>'
    line, auth.md's format; an 'authorization=' line is ignored), or None.
    Tolerates leading whitespace, spaces around '=' and CRLF line endings
    (Windows captures)."""
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if not sep or key.strip().lower() != "cookie":
            continue
        for part in value.split(";"):
            name, eq, val = part.strip().partition("=")
            if eq and name.strip() == "nbsso" and val.strip():
                return f"nbsso={val.strip()}"
    return None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--nbsso", default=None,
                    help="nbsso=<value> cookie pair. Without it you see the "
                         "anonymous view, which can differ from the user's.")
    ap.add_argument("--cookie", default=None, metavar="FILE",
                    help="Cookie file in auth.md's format (a 'cookie=nbsso=...; "
                         "_nblb=...' line); its nbsso pair is used as --nbsso.")
    ap.add_argument("--id", default=None,
                    help="Optional canonical id or URN — also prints that "
                         "item's accessInfo as this IP/session sees it.")
    ap.add_argument("--json", action="store_true",
                    help="Emit raw JSON instead of the human-readable summary.")
    args = ap.parse_args(argv)
    if args.cookie and not args.nbsso:
        args.nbsso = nbsso_from_cookie_file(args.cookie)
        if not args.nbsso:
            print(f"ERROR: no nbsso=... in {args.cookie}", file=sys.stderr)
            return 1

    try:
        me = _get_json(ME_URL, args.nbsso)
    except urllib.error.URLError as exc:
        print(f"ERROR: could not reach {ME_URL}: {exc}", file=sys.stderr)
        return 1

    out = {"me": me}

    if args.id:
        canonical = args.id.split("no-nb_")[-1].strip()
        try:
            blob = _get_json(ITEM_URL.format(id=canonical), args.nbsso)
            out["id"] = canonical
            out["accessInfo"] = blob.get("accessInfo")
        except urllib.error.URLError as exc:
            print(f"ERROR: could not fetch item {canonical}: {exc}",
                  file=sys.stderr)
            return 1
        allowed = (out["accessInfo"] or {}).get("accessAllowedFrom")
        if allowed in GEO_GATED:
            out["tileProbe"] = probe_tile(canonical, args.nbsso)
        out["route"] = decide_route(
            allowed, out.get("tileProbe"),
            loan=(out["accessInfo"] or {}).get("legalDepositReservationStatus"),
            cookie=bool(args.nbsso),
            viewability=(out["accessInfo"] or {}).get("viewability"))

    refused = out.get("route") in ("norwegian-ip", "norwegian-ip+loan")

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 3 if refused else 0

    print(f"ip:            {me.get('ip')}")
    print(f"loginProvider: {me.get('loginProvider') or '(anonymous)'}")
    if me.get("displayName"):
        print(f"displayName:   {me['displayName']}")
    if me.get("roles"):
        print(f"roles:         {me['roles']}")

    ai = out.get("accessInfo")
    if ai is not None:
        print()
        print(f"item:          {out['id']}")
        print(f"  accessAllowedFrom:  {ai.get('accessAllowedFrom')}")
        print(f"  viewability:        {ai.get('viewability')}")
        print(f"  isPublicDomain:     {ai.get('isPublicDomain')}")
        if ai.get("license"):
            print(f"  license:            {ai['license']}")
        if ai.get("legalDepositReservationStatus"):
            print("  legalDepositReservationStatus: "
                  f"{ai['legalDepositReservationStatus']}")
        if ai.get("legalDepositLoginText"):
            print(f"  legalDepositLoginText: {ai['legalDepositLoginText']}")
        if ai.get("accessAllowedFrom") in GEO_GATED:
            probe = out.get("tileProbe")
            print()
            if out.get("route") == "norwegian-ip" and probe in (200, PROBE_SMALL):
                print(f"  catalogue: viewability NONE — nb.no will not let "
                      f"{me.get('ip')} read this Bokhylla item:")
                print("        the IP is not Norwegian. (The tile probe is not "
                      "trusted against that.)")
            elif probe == PROBE_SMALL:
                print("  image probe: refused — nb.no answered with a smaller "
                      "image than the 1024 px tile")
                print("        asked for. Treat it as a 403: this IP and "
                      "session will not get the pages.")
            elif probe == 200 and out.get("route") == "norwegian-ip+loan":
                print("  image probe: OK, but this legal-deposit item has no "
                      "active loan in this session")
                print(f"        (legalDepositReservationStatus must be {LOAN_TAKEN}; "
                      "pass --nbsso / --cookie after taking the loan).")
            elif probe == 200:
                print("  image probe: OK — nb.no served a page tile to this "
                      "IP and session.")
            elif probe == 403 and ai.get("accessAllowedFrom") == "NB":
                print("  image probe: 403 — either this IP is not Norwegian, "
                      "or there is no active digital")
                print("        loan, or the nbsso cookie has expired. Every "
                      "page will fail until that is fixed.")
            elif probe == 403:
                print(f"  image probe: 403 — nb.no will not serve this item's "
                      f"pages to {me.get('ip')}: the IP")
                print("        is not Norwegian. Every page image will 403 no "
                      "matter who is logged in.")
            else:
                print(f"  image probe: inconclusive ({probe or 'no response'})."
                      f" This item is served only from "
                      f"{ai['accessAllowedFrom']};")
                print(f"        confirm {me.get('ip')} is a Norwegian address "
                      "before downloading.")
    if "route" in out:
        print()
        print(f"route: {out['route']} — {ROUTES[out['route']]}")
    elif args.id is None:
        print()
        print("(pass --id <item> to also see that item's accessInfo)")

    return 3 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
