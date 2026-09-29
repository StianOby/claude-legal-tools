#!/usr/bin/env python3
"""
geo_check.py — report the egress IP and nb.no session as nb.no sees them.

Why this exists: nb.no enforces geo-restriction at the IIIF *image resolver*,
not at the API. Manifests and catalog metadata are served worldwide with no
auth, so a run can look healthy right up until every page image returns 403.
Both the sandbox and the browser pane egress from the user's own machine IP,
so this one call describes both.

Deliberately talks only to nb.no. Do NOT swap in a third-party geo service
(ipinfo.io and friends) — that would leak the user's IP to an unrelated party
to learn something nb.no already tells us for free. This script does not map
the IP to a country; `https://api.nb.no/me/v1` reports the IP and the login
identity. For a geo-gated item (--id), it instead asks the image resolver for
one 1024 px tile of the first numbered page — the same request a download
would make next — and nb.no's answer settles it: 200 means this IP and
session may read the pages; 403 on a NORWAY (Bokhylla) item means the IP is
not Norwegian. On an NB item a 403 can also mean no active digital loan or an
expired nbsso cookie, so it is reported as that, not as "not Norwegian".

Usage:
    python geo_check.py                       # anonymous view
    python geo_check.py --nbsso "nbsso=<v>"   # the user's own session
    python geo_check.py --id digibok_2008051600041   # + accessInfo + tile probe

Exit status: 0 normally; 3 when the tile probe was refused (403); 1 when
nb.no could not be reached.

Reading the output:
  - loginProvider null                     → not logged in (or cookie expired)
  - accessAllowedFrom EVERYWHERE           → no cookie needed, single-shot OK
  - accessAllowedFrom NORWAY (bokhylla)    → Norwegian IP, no cookie, tiles only
  - accessAllowedFrom NB                   → nbsso + a digital loan the user
                                             takes in a browser; tiles only.
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
import urllib.error
import urllib.request
from typing import Optional

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


def _get_json(url: str, nbsso: Optional[str], timeout: float = 30.0) -> dict:
    # `Accept: */*`, not application/json: /me/v1 serves only
    # application/hal+json and answers 406 to a narrower Accept header.
    headers = {"Accept": "*/*"}
    if nbsso:
        headers["cookie"] = nbsso
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def probe_tile(canonical: str, nbsso: Optional[str],
               timeout: float = 20.0) -> Optional[int]:
    """HTTP status for one 1024 px tile of the item's first numbered page
    (200 = served), or None when no probe could be made. Not smaller: 256 px
    tiles are served to anyone, like thumbnails; 1024 px is what the
    downloader fetches and what nb.no gates."""
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
        names = [c["@id"].split("/")[-1] for c in canvases]
        pick = next((i for i, n in enumerate(names)
                     if n.rsplit("_", 1)[-1].isdigit()), None)
        if pick is None:
            pick = next(i for i, n in enumerate(names) if not n.endswith("_C2"))
        base = canvases[pick]["images"][0]["resource"]["service"]["@id"]
    except (TypeError, KeyError, IndexError, StopIteration):
        return None
    headers = {"referer": f"https://www.nb.no/items/URN:NBN:no-nb_{canonical}"}
    if nbsso:
        headers["cookie"] = nbsso
    req = urllib.request.Request(f"{base}/0,0,1024,1024/full/0/default.jpg",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--nbsso", default=None,
                    help="nbsso=<value> cookie pair. Without it you see the "
                         "anonymous view, which can differ from the user's.")
    ap.add_argument("--id", default=None,
                    help="Optional canonical id or URN — also prints that "
                         "item's accessInfo as this IP/session sees it.")
    ap.add_argument("--json", action="store_true",
                    help="Emit raw JSON instead of the human-readable summary.")
    args = ap.parse_args(argv)

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
        if (out["accessInfo"] or {}).get("accessAllowedFrom") in GEO_GATED:
            out["tileProbe"] = probe_tile(canonical, args.nbsso)

    refused = out.get("tileProbe") == 403

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
            if probe == 200:
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
    elif args.id is None:
        print()
        print("(pass --id <item> to also see that item's accessInfo)")

    return 3 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
