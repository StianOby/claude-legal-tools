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
identity, and whether that IP is Norwegian is a question for the user.

Usage:
    python geo_check.py                       # anonymous view
    python geo_check.py --nbsso "nbsso=<v>"   # the user's own session
    python geo_check.py --id digibok_2008051600041   # + this item's accessInfo

Reading the output:
  - loginProvider null                     → not logged in (or cookie expired)
  - accessAllowedFrom EVERYWHERE           → no cookie needed, single-shot OK
  - accessAllowedFrom NORWAY (bokhylla)    → Norwegian IP, no cookie, tiles only
  - accessAllowedFrom NB + legalDepositLoginText
                                           → nbsso + a digital loan the user
                                             takes in a browser; tiles only
  - accessAllowedFrom NORWAY/NB from a non-Norwegian IP
                                           → page images will 403 regardless
                                             of login. Stop before downloading.
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

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

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
            print()
            print(f"  NOTE: this item is served only from {ai['accessAllowedFrom']}."
                  f" Confirm {me.get('ip')} is a Norwegian address before")
            print("        downloading — if it is not, every page image will "
                  "403 no matter who is logged in.")
    elif args.id is None:
        print()
        print("(pass --id <item> to also see that item's accessInfo)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
