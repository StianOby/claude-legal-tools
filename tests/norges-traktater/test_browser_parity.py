#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parity baseline for scripts/browser/norges_traktater.js.

Runs traktater.py's own functions over the saved lovdata.no pages in
fixtures/ (no network) for every case in fixtures/parity_cases.json and
compares the result with fixtures/parity_expected.json. tests/test_browser.js
feeds the same cases to the JS helper and expects the same expected file, so
Python == expected == JS.

    python test_browser_parity.py            check (this is what CI runs)
    python test_browser_parity.py --write    regenerate parity_expected.json
                                             (after changing traktater.py or
                                             the cases; review the diff)
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "plugins" / "norges-traktater" / "skills" / "norges-traktater"
FIX = HERE / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))
import traktater as t  # noqa: E402

ROUTES = json.loads((FIX / "routes.json").read_text(encoding="utf-8"))
CASES = json.loads((FIX / "parity_cases.json").read_text(encoding="utf-8"))
requests = []


def canon(url):
    """Path plus sorted query parameters, so encodings and order don't matter."""
    u = urllib.parse.urlsplit(url)
    q = sorted(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
    return u.path + ("?" + urllib.parse.urlencode(q) if q else "")


def read(name):
    p = FIX / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def route(url):
    u = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(u.query))
    if u.path == "/register/traktater":
        if not q:
            return read("register.html")
        if q.get("search") == "menneskerett":
            return read(f"search_menneskerett_{q.get('offset', '0')}.html")
        return read("search_wien_0.html")
    tid = u.path.rsplit("/", 1)[-1]
    return read(f"doc_{ROUTES['aliases'].get(tid, tid)}.html")


def fake_fetch(url, ttl, no_cache=False):
    requests.append(canon(url))
    return route(url)


t._fetch = fake_fetch


def run(case):
    op, a = case["op"], case["args"]
    try:
        if op == "search":
            payload = t.search(a.get("query", ""), year=a.get("year"), country=a.get("country"),
                               context=a.get("context", "tittel"), max_results=a.get("max", 20))
            if a.get("full") and payload["results"]:
                t.add_full_titles(payload["results"])
                payload["full_titles"] = True
            return payload
        if op == "meta":
            return t.get_meta(a["id"])
        if op == "meta_batch":
            ids = []
            for line in a["ids"]:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                try:
                    tid = t.normalize_id(line)
                except ValueError:
                    continue
                if tid not in ids:
                    ids.append(tid)
            out = []
            for tid in ids:
                try:
                    out.append(t.get_meta(tid))
                except FileNotFoundError as e:
                    out.append({"id": tid, "url": f"{t.DOC_BASE}/{tid}", "error": str(e)})
            return out
        if op == "text":
            return t.get_text(a["id"])
        if op == "article":
            return t.get_article(a["id"], a["article"])
        if op == "countries":
            opts = t.countries()
            if a.get("query"):
                opts = [o for o in opts if a["query"].lower() in o.lower()]
            return {"count": len(opts), "countries": opts}
        if op == "status":
            html = t._fetch(t.REGISTER, t.LIST_TTL)
            yrs = t.years()
            return {"reachable": "Norges traktater" in html or "register/traktater" in html,
                    "total": t._hit_count(html),
                    "years": {"first": yrs[-1], "last": yrs[0], "count": len(yrs)},
                    "countries": len(t.countries())}
    except (ValueError, FileNotFoundError, SystemExit) as e:
        return {"__error": str(e)}
    raise AssertionError(op)


def compute():
    out = []
    for case in CASES:
        requests.clear()
        result = run(case)
        out.append({"name": case["name"], "result": result, "requests": sorted(set(requests))})
    return out


if __name__ == "__main__":
    got = compute()
    path = FIX / "parity_expected.json"
    if "--write" in sys.argv:
        path.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {path} ({len(got)} cases)")
        sys.exit(0)
    want = json.loads(path.read_text(encoding="utf-8"))
    bad = 0
    for g, w in zip(got, want):
        if json.loads(json.dumps(g)) != w:
            bad += 1
            print("FAIL", g["name"])
    if len(got) != len(want):
        bad += 1
        print("FAIL: case count differs; regenerate with --write")
    print(f"{bad} failure(s)" if bad else f"all ok ({len(got)} parity cases)")
    sys.exit(1 if bad else 0)
