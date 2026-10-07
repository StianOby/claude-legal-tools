#!/usr/bin/env python3
"""Offline tests for scripts/coe.py (no network): aliases, and when a
cached treaty document or the cached index is fetched again.
Run: python tests/ets/test_coe.py
"""

import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr
from pathlib import Path

os.environ["ETS_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "ets" / "skills" / "ets" / "scripts"))
import coe  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def quiet(fn, *a):
    err = io.StringIO()
    with redirect_stderr(err):
        out = fn(*a)
    return out, err.getvalue()


print("aliases")
for q, want in [("FCNM", "157"), ("Framework Convention for the Protection of National Minorities", "157"),
                ("Tromsø Convention", "205"), ("tromso", "205"), ("ECHR", "005"),
                ("Istanbul Convention", "210"), ("anti-trafficking convention", "197")]:
    check(q, quiet(coe.lookup_ref, q)[0][:2], (want, 100))
(ref, _, _), note = quiet(coe.lookup_ref, "Warsaw Convention")
check("Warsaw Convention is 198", ref, "198")
check("… with a note naming 196 and 197", ("196" in note and "197" in note), True)
check("no note for a plain number", quiet(coe.lookup_ref, "198")[1], "")

print("cached documents follow the index")


class FakeResponse(io.BytesIO):
    headers = {"Content-Type": "application/pdf"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


downloads = []


def fake_urlopen(req, **kw):
    downloads.append(req.full_url)
    return FakeResponse(b"%PDF-1.4 " + req.full_url.encode())


coe.urllib.request.urlopen = fake_urlopen
stem = coe.treaty_dir("210") / "text.en"
txt = stem.with_name("text.en.txt")

p, kind = quiet(coe.download_document, "https://rm.coe.int/old", stem)[0]
check("first download", (kind, p.read_bytes().endswith(b"old"), len(downloads)), ("pdf", True, 1))
txt.write_text("extracted from old", encoding="utf-8")
quiet(coe.download_document, "https://rm.coe.int/old", stem)
check("same URL: cached, no request", len(downloads), 1)
(p, _), note = quiet(coe.download_document, "https://rm.coe.int/new", stem)
check("new URL in the index: fetched again", (len(downloads), p.read_bytes().endswith(b"new")), (2, True))
check("… the old extracted text is dropped", txt.exists(), False)
check("… and it says so", "new document" in note, True)
stem.with_name("text.en.url").unlink()
(p, _), note = quiet(coe.download_document, "https://rm.coe.int/new", stem)
check("cache from before this change (no .url): fetched once", (len(downloads), "not recorded" in note), (3, True))
quiet(coe.download_document, "https://rm.coe.int/new", stem)
check("… and then reused", len(downloads), 3)

print("the cached index is refreshed when old")
coe._seed_index_if_needed()
refreshes = []
coe.refresh_index = lambda lang="en": refreshes.append(1) or coe._load_json(coe.INDEX_PATH)
quiet(coe.resolve_treaty, "005")
check("fresh index: no refresh", len(refreshes), 0)
old = time.time() - (coe.INDEX_MAX_AGE_DAYS + 1) * 86400
os.utime(coe.INDEX_PATH, (old, old))
quiet(coe.resolve_treaty, "005")
check("index older than the limit: refreshed", len(refreshes), 1)


def failing_refresh(lang="en"):
    raise coe.urllib.error.URLError("offline")


coe.refresh_index = failing_refresh
(ref, t), note = quiet(coe.resolve_treaty, "005")
check("failed refresh keeps the cached index", (ref, "using the cached index" in note), ("005", True))

# The data service redirecting to the coe.int portal (2026-10-07) or answering
# HTML is an outage, reported with the URL that was called, not followed.
import urllib.request  # noqa: E402

api_url = coe.API_BASE + "api/signatures?NumSte=210"
req = urllib.request.Request(api_url)
try:
    coe._NoRedirect().redirect_request(req, None, 301, "Moved", {}, "http://www.coe.int/?NumSte=210")
    got = None
except coe.ServiceUnavailable as e:
    got = (e.url, e.detail)
check("redirect is ServiceUnavailable with the original URL", got,
      (api_url, "HTTP 301 redirect to http://www.coe.int/?NumSte=210"))


class FakeResponse(io.BytesIO):
    headers = {"Content-Type": "text/html"}


try:
    coe._api_json(FakeResponse(b"<!doctype html><title>Portal</title>"), api_url)
    got = None
except coe.ServiceUnavailable as e:
    got = e.detail
check("HTML body is ServiceUnavailable", got, "answered text/html, not JSON")
check("JSON body is parsed", coe._api_json(FakeResponse(b'{"a": 1}'), api_url), {"a": 1})

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
