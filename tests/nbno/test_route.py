#!/usr/bin/env python3
"""Offline tests for the routing decision in scripts/geo_check.py (no
network): each access class, with the catalogue and the tile probe mocked,
gives the right `route` and exit status.
Run: python tests/nbno/test_route.py
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "nbno" / "skills" / "nbno" / "scripts"))
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
LOAN = "TAKENBYCURRENTUSER"
for allowed, probe, loan, cookie, want in [
    ("EVERYWHERE", None, None, False, "here"),
    ("NORWAY", 200, None, False, "here"),
    ("NORWAY", 403, None, False, "norwegian-ip"),
    ("NORWAY", None, None, False, "unknown"),
    ("NB", 200, LOAN, True, "here"),
    ("NB", 403, LOAN, True, "norwegian-ip+loan"),
    ("NB", 500, LOAN, True, "unknown"),
    # Served first pages without a loan (2026-11-26): not "here".
    ("NB", 200, None, False, "norwegian-ip+loan"),
    ("NB", 200, "NOTRESERVED", True, "norwegian-ip+loan"),
    ("NB", 200, LOAN, False, "norwegian-ip+loan"),
    ("NB", None, None, False, "norwegian-ip+loan"),
    (None, None, None, False, "unknown"),
    ("SOMETHING_NEW", 200, None, False, "unknown"),
]:
    check(f"{allowed} / {probe} / {loan} / cookie={cookie}",
          gc.decide_route(allowed, probe, loan=loan, cookie=cookie), want)
# Cloud sandbox, 2026-11-27: viewability NONE but the tile probe said 200.
check("NORWAY, viewability NONE, probe 200 -> norwegian-ip",
      gc.decide_route("NORWAY", 200, viewability="NONE"), "norwegian-ip")
check("NORWAY, viewability ALL, probe 200 -> here",
      gc.decide_route("NORWAY", 200, viewability="ALL"), "here")
check("NORWAY, a too-small 200 counts as refused",
      gc.decide_route("NORWAY", gc.PROBE_SMALL, viewability="ALL"), "norwegian-ip")
check("NB, viewability NONE is normal anonymously (not geo)",
      gc.decide_route("NB", 200, loan=LOAN, cookie=True, viewability="NONE"), "here")

print("jpeg_size")
import struct  # noqa: E402
def fake_jpeg(w, h):
    # SOI, an APP0 segment, then SOF0 with height/width.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"
check("reads width and height", gc.jpeg_size(fake_jpeg(1024, 768)), (1024, 768))
check("not a JPEG", gc.jpeg_size(b"<html>"), None)

print("probe_canvas_index: a mid-book numbered page")
check("middle numbered page", gc.probe_canvas_index(
    ["x_C1", "x_C2", "x_I1", "x_0001", "x_0002", "x_0003", "x_0004", "x_C3"]), 5)
check("no numbered page: middle non-C2", gc.probe_canvas_index(["a_C1", "a_C2", "a_C3"]), 2)
check("nothing to probe", gc.probe_canvas_index(["a_C2"]), None)

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
code, out, _ = run({"accessAllowedFrom": "NORWAY", "viewability": "ALL"}, 200)
check("route here", out.get("route"), "here")
check("exit 0", code, 0)

print("main(): Bokhylla item from the cloud, viewability NONE, probe 200 (2026-11-27)")
code, text, _ = run({"accessAllowedFrom": "NORWAY", "viewability": "NONE"}, 200, json_out=False)
check("route norwegian-ip", text.strip().splitlines()[-1].split(" — ")[0], "route: norwegian-ip")
check("exit 3", code, 3)
check("says why", "viewability NONE" in text, True)

print("main(): legal-deposit item from the cloud with a cookie (403)")
code, out, _ = run({"accessAllowedFrom": "NB"}, 403, nbsso="nbsso=x")
check("route norwegian-ip+loan", out.get("route"), "norwegian-ip+loan")
check("exit 3", code, 3)

print("main(): legal-deposit item, Norwegian IP, loan active (200)")
code, out, _ = run({"accessAllowedFrom": "NB", "legalDepositReservationStatus": LOAN},
                   200, nbsso="nbsso=x")
check("route here", out.get("route"), "here")
check("exit 0", code, 0)

print("main(): legal-deposit item, Norwegian IP, anonymous, probe served (200)")
code, out, _ = run({"accessAllowedFrom": "NB"}, 200)
check("route norwegian-ip+loan", out.get("route"), "norwegian-ip+loan")
check("exit 3", code, 3)

print("main(): text output ends with the route line")
code, text, _ = run({"accessAllowedFrom": "NORWAY"}, 403, json_out=False)
check("last line", text.strip().splitlines()[-1].split(" — ")[0], "route: norwegian-ip")

print("nbsso_from_cookie_file(): the cookie file auth.md describes")
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    ck = Path(d) / "cookie.txt"
    ck.write_text("authorization=\ncookie=nbsso=abc123; _nblb=lb9\n", encoding="utf-8")
    check("nbsso pair", gc.nbsso_from_cookie_file(str(ck)), "nbsso=abc123")
    ck.write_bytes(b"authorization=\r\n  Cookie = _nblb=lb9 ; nbsso = abc123\r\n")
    check("CRLF, indent, spaces, any order", gc.nbsso_from_cookie_file(str(ck)), "nbsso=abc123")
    ck.write_text("authorization=\ncookie=nbsso=; _nblb=lb9\n", encoding="utf-8")
    check("empty nbsso value", gc.nbsso_from_cookie_file(str(ck)), None)
    ck.write_text("authorization=\ncookie=_nblb=lb9\n", encoding="utf-8")
    check("no nbsso", gc.nbsso_from_cookie_file(str(ck)), None)
    check("missing file", gc.nbsso_from_cookie_file(str(Path(d) / "nope.txt")), None)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
