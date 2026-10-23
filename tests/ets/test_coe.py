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

# No index ships with the skill; tests start from a saved copy of the live one.
FIXTURE_INDEX = Path(__file__).resolve().parent / "fixtures" / "index.json"
coe.CACHE_DIR.mkdir(parents=True, exist_ok=True)
coe.INDEX_PATH.write_bytes(FIXTURE_INDEX.read_bytes())

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

print("the index is fetched live when there is none, and refreshed when old")
refreshes = []


def fake_refresh(lang="en"):
    refreshes.append(1)
    coe.INDEX_PATH.write_bytes(FIXTURE_INDEX.read_bytes())
    return coe._load_json(coe.INDEX_PATH)


coe.refresh_index = fake_refresh
coe.INDEX_PATH.unlink()
coe._INDEX_REFRESHED = False
quiet(coe.resolve_treaty, "005")
check("no cached index: fetched live on first use", len(refreshes), 1)
coe._INDEX_REFRESHED = False
quiet(coe.resolve_treaty, "005")
check("fresh index: no refresh", len(refreshes), 1)
old = time.time() - (coe.INDEX_MAX_AGE_DAYS + 1) * 86400
os.utime(coe.INDEX_PATH, (old, old))
quiet(coe.resolve_treaty, "005")
check("index older than the limit: refreshed", len(refreshes), 2)

print("a name that matches nothing refreshes once, then says what it searched")
coe._INDEX_REFRESHED = False
try:
    quiet(coe.lookup_ref, "zzqx wyvp")
    got = None
except SystemExit as e:
    got = str(e)
check("one refresh on the miss", len(refreshes), 3)
check("message names the index searched", bool(got and "searched the cached index from" in got), True)


def failing_refresh(lang="en"):
    raise coe.urllib.error.URLError("offline")


coe.refresh_index = failing_refresh
coe._INDEX_REFRESHED = False
old = time.time() - (coe.INDEX_MAX_AGE_DAYS + 1) * 86400
os.utime(coe.INDEX_PATH, (old, old))
(ref, t), note = quiet(coe.resolve_treaty, "005")
check("failed refresh keeps the cached index, with a coverage warning",
      (ref, "COVERAGE WARNING" in note and "using the cached index from" in note), ("005", True))

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

print("HTML documents: text as the browser shows it")
HTML = ("<html><body><h1>Title</h1>\n<p>Article\n1 of the <i>Convention</i>, see <b>Rule</b>&nbsp;39.</p>"
        '<ol type="a"><li>first</li><li>second</li></ol><ul><li>x</li></ul>'
        "<table><tr><td>A</td><td><em>B</em></td></tr></table><p>wo<span>rd</span></p></body></html>")
check("converted", coe._html_to_text(HTML),
      "Title\n\nArticle 1 of the *Convention*, see **Rule** 39.\n\na. first\nb. second\n\n- x\n\nA | *B*\n\nword\n")
with tempfile.TemporaryDirectory() as d:
    doc = Path(d) / "text.en.html"
    doc.write_text(HTML, encoding="utf-8")
    (Path(d) / "text.en.txt").write_text("Article 1 of the Convention , see Rule 39.\n", encoding="utf-8")
    txt = coe.extract_text(doc, "html")
    check("text from an older converter is made again", "*Convention*" in txt.read_text(encoding="utf-8"), True)
    check("format recorded", (Path(d) / "text.en.format").read_text(encoding="utf-8"), coe.HTML_TEXT_FORMAT)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
