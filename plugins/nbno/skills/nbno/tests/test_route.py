#!/usr/bin/env python3
"""Offline tests for the routing decision in scripts/geo_check.py (no
network): each access class, with the catalogue and the tile probe mocked,
gives the right `route` and exit status.
Run: python tests/test_route.py
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import geo_check as gc  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


CLOUD_IP = "160.79.106.137"


def run(access, probe, nbsso=None, json_out=True):
    """geo_check.main with the catalogue answering `access` and the tile probe
    answering `probe`. Returns (exit, parsed JSON or text)."""
    def get_json(url, cookie, timeout=30.0):
        if url == gc.ME_URL:
            return {"ip": CLOUD_IP, "loginProvider": "feide" if cookie else None}
        return {"accessInfo": access}

    probes = []
    gc._get_json = get_json
    gc.probe_tile = lambda canonical, cookie, timeout=20.0: probes.append(canonical) or probe
    argv = ["--id", "URN:NBN:no-nb_digibok_2021021607640"]
    if nbsso:
        argv += ["--nbsso", nbsso]
    if json_out:
        argv.append("--json")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = gc.main(argv)
    out = buf.getvalue()
    return code, (json.loads(out) if json_out else out), probes


print("decide_route table")
for allowed, probe, want in [
    ("EVERYWHERE", None, "here"),
    ("NORWAY", 200, "here"),
    ("NORWAY", 403, "norwegian-ip"),
    ("NORWAY", None, "unknown"),
    ("NB", 200, "here"),
    ("NB", 403, "norwegian-ip+loan"),
    ("NB", 500, "unknown"),
    (None, None, "unknown"),
    ("SOMETHING_NEW", 200, "unknown"),
]:
    check(f"{allowed} / {probe}", gc.decide_route(allowed, probe), want)

print("main(): open item, as from the cloud sandbox")
code, out, probes = run({"accessAllowedFrom": "EVERYWHERE", "license": "publicdomain"}, None)
check("route here", out.get("route"), "here")
check("exit 0", code, 0)
check("no tile probe for an open item", probes, [])

print("main(): Bokhylla item from the cloud (403)")
code, out, probes = run({"accessAllowedFrom": "NORWAY", "license": "bokhylla"}, 403)
check("route norwegian-ip", out.get("route"), "norwegian-ip")
check("exit 3", code, 3)
check("probed once, canonical id", probes, ["digibok_2021021607640"])

print("main(): Bokhylla item from a Norwegian IP (200)")
code, out, _ = run({"accessAllowedFrom": "NORWAY"}, 200)
check("route here", out.get("route"), "here")
check("exit 0", code, 0)

print("main(): legal-deposit item from the cloud with a cookie (403)")
code, out, _ = run({"accessAllowedFrom": "NB"}, 403, nbsso="nbsso=x")
check("route norwegian-ip+loan", out.get("route"), "norwegian-ip+loan")
check("exit 3", code, 3)

print("main(): legal-deposit item, Norwegian IP, loan active (200)")
code, out, _ = run({"accessAllowedFrom": "NB"}, 200, nbsso="nbsso=x")
check("route here", out.get("route"), "here")

print("main(): text output ends with the route line")
code, text, _ = run({"accessAllowedFrom": "NORWAY"}, 403, json_out=False)
check("last line", text.strip().splitlines()[-1].split(" — ")[0], "route: norwegian-ip")

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
