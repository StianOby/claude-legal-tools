#!/usr/bin/env python3
"""Full-text search of EU case law, through the backend of InfoCuria.

    case_law_search.py '"abuse of rights" garlic' --type judgment --from 2010-01-01

The backend is undocumented (docs/eurlex.md in the repository). Anything
unexpected is therefore an error (exit 1), never "no hits"; and since an
unknown filter field silently gives 0 hits, every zero is checked with
control searches. Exit codes: 0 answered (also with 0 hits), 1 failed, 2 usage.
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request

VERSION = "1.3.3"
USER_AGENT = f"eurlex-skill/{VERSION} (+https://github.com/StianOby/claude-legal-tools)"
URL = "https://infocuriaws.curia.europa.eu/elastic-connector/search"
LANGUAGES = ("BG CS DA DE EL EN ES ET FI FR GA HR HU IT LT LV MT NL PL PT RO "
             "SK SL SV").split()
TYPES = {
    "judgment": ["ARRET", "ARRET_NP", "ARRET_DR"],
    "opinion": ["CONCL"],
    "order": ["ORD", "ORD_NP", "ORD_DR"],
}
COURTS = ("C", "T", "F")
TIMEOUT = 60
WINDOW = 200  # characters of context on each side of the first match
MARK = chr(1)  # stands for the start of a highlighted match


class SearchError(Exception):
    pass


def build_payload(query, language="EN", filters=None, page=1, size=20, sort="SCORE"):
    return {
        "multiSearchTerms": [], "searchTerm": query, "ecli": "", "publishedId": "",
        "usualName": "", "logicDocId": "",
        "pagination": {"pageNumber": page - 1, "pageSize": size},
        "sortTermList": [{"sortDirection": "DESC", "sortTerm": sort}],
        "filtersValue": filters or [], "advancedFiltersValue": [],
        "language": language, "isSearchExact": True,
        "searchSources": ["document", "metadata"],
        "tabName": "jurisprudence", "isAllTabsRequest": False,
    }


def build_filters(kind=None, court=None, date_from=None, date_to=None):
    out = []
    if kind:
        out.append({"field": "docTypeCode", "values": TYPES[kind]})
    if court:
        out.append({"field": "affairJurisdictionCode", "values": [court]})
    if date_from or date_to:
        out.append({"field": "docDate", "values": [
            date_from or "1953-01-01", date_to or datetime.date.today().isoformat()]})
    return out


def post(payload):
    req = urllib.request.Request(URL, json.dumps(payload).encode("utf-8"), {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SearchError(f"InfoCuria answered HTTP {e.code}") from e
    except OSError as e:
        raise SearchError(f"could not reach InfoCuria: {e}") from e
    try:
        return json.loads(body)
    except ValueError as e:
        raise SearchError("InfoCuria's answer was not JSON") from e


def parse(data, language="EN"):
    """(total, is_exact, hits) from an answer; SearchError if it looks wrong."""
    try:
        total, raw = data["totalHits"], data["searchHits"]
        if type(total) is not int or not isinstance(raw, list):
            raise TypeError
        hits = {}
        for h in raw:
            c = h["content"]
            hit = {
                "celex": c.get("celex") or "", "ecli": c.get("ecli") or "",
                "case": c["idPublished"], "type": c["docTypeCode"], "date": c["docDate"],
                "name": case_name(h, language), "snippet": snippet(h),
            }
            # A document in joined cases, or filed under two procedures, is
            # returned once for each: same ECLI, possibly another CELEX. A
            # summary notice (_DR) gives way to the decision itself.
            key = hit["ecli"] or hit["celex"] or c["id"]
            if key not in hits or (is_notice(hits[key]) and not is_notice(hit)):
                hits[key] = hit
    except (KeyError, TypeError, AttributeError) as e:
        raise SearchError("InfoCuria's answer has changed form") from e
    return total, data.get("totalHitsRelation") == "EQUAL_TO", list(hits.values())


def is_notice(hit):
    """A summary notice ("Judgment (Information)"), not the decision itself."""
    return hit["type"].endswith("_DR")


def case_name(hit, language):
    procedures = ((hit.get("innerHits") or {}).get("procedure") or {}).get("searchHits") or []
    names = {}
    for p in procedures:
        for entry in p["content"].get("usualNameML") or []:
            for lang, name in entry.items():
                names.setdefault(lang, name)
    return names.get(language.lower()) or names.get("fr") or ""


def snippet(hit):
    """The text around the first highlighted match, document text preferred."""
    fields = sorted((hit.get("highlightFields") or {}).items(),
                    key=lambda kv: not kv[0].startswith("contentML"))
    for _, pieces in fields:
        for piece in pieces:
            text = re.sub(r"<em\b[^>]*>", MARK, piece).replace("</em>", "")
            at = text.find(MARK)
            if at < 0:
                continue
            start, end = max(0, at - WINDOW), at + 2 * WINDOW
            cut = html.unescape(text[start:end].replace(MARK, ""))
            return ("… " if start else "") + " ".join(cut.split()) + (
                " …" if end < len(text) else "")
    return ""


def check_zero(query, language, filters):
    """What 0 hits mean, for the user; SearchError if the backend no longer
    finds what it must."""
    if filters:
        total, _, _ = parse(post(build_payload(query, language, size=1)), language)
        if total:
            return (f"Without the filters there are {total} hits. If 0 is surprising, "
                    "rerun without them: a filter may have stopped working.")
    total, _, _ = parse(post(build_payload('"judgment"', "EN", size=1)), "EN")
    if not total:
        raise SearchError("a control search that must have hits gave none")
    return "A control search passed, so the search itself works."


def iso_date(text):
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD")


def arguments(argv):
    p = argparse.ArgumentParser(description="Full-text search of EU case law (InfoCuria).")
    p.add_argument("query", help='words (all must occur), "exact phrase", AND, OR')
    p.add_argument("--language", default="EN", type=str.upper, choices=LANGUAGES)
    p.add_argument("--type", choices=sorted(TYPES), dest="kind")
    p.add_argument("--court", choices=COURTS, type=str.upper,
                   help="C Court of Justice, T General Court, F Civil Service Tribunal")
    p.add_argument("--from", dest="date_from", type=iso_date)
    p.add_argument("--to", dest="date_to", type=iso_date)
    p.add_argument("--newest", action="store_true", help="newest first, not by relevance")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=20, help="1-50")
    a = p.parse_args(argv)
    if not a.query.strip():
        p.error("the query is empty")
    if a.page < 1 or not 1 <= a.size <= 50:
        p.error("--page must be at least 1 and --size 1-50")
    return a


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    a = arguments(argv)
    filters = build_filters(a.kind, a.court, a.date_from, a.date_to)
    try:
        total, exact, hits = parse(post(build_payload(
            a.query, a.language, filters, a.page, a.size,
            "DOC_DATE" if a.newest else "SCORE")), a.language)
        if not hits and (a.page - 1) * a.size < total:
            raise SearchError("InfoCuria reports hits but returned none")
        note = "" if total else check_zero(a.query, a.language, filters)
    except SearchError as e:
        print(f"SEARCH FAILED: {e}. This is not a negative result.", file=sys.stderr)
        return 1
    print(f"{'' if exact else 'at least '}{total} hits (texts in {a.language}), "
          f"page {a.page} of {-(-total // a.size)}")
    if note:
        print(note)
    for h in hits:
        print(f"\n{h['celex'] or '(no CELEX)'} | {h['case']} {h['name']} | {h['type']} | "
              f"{h['date']} | {h['ecli'] or '(no ECLI)'}")
        if is_notice(h):
            print("   [summary notice; the full text is usually only in French and the "
                  "language of the case: fetch with FRA]")
        if h["snippet"]:
            print(f"   {h['snippet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
