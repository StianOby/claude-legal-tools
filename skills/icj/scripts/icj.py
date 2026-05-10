#!/usr/bin/env python3
"""
icj — CLI for the icj skill.

Subcommands:
  cases list|show|recent|search           ICJ contentious + advisory cases
  pcij  list|show                         Permanent Court of International Justice
  jurisdiction states|non-un|non-parties|basis|treaties|organs
  declarations list|show|compare          Article 36(2) optional-clause declarations
  status                                  Show cache freshness for jurisdiction pages
  refresh                                 Re-fetch jurisdiction pages

Common flags:
  --json                                  Emit JSON instead of human prose
  --force-refresh                         Bypass cache for this call
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make sibling modules importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cases as cases_mod  # noqa: E402
import declarations as decl_mod  # noqa: E402
import jurisdiction as jur_mod  # noqa: E402
import pcij as pcij_mod  # noqa: E402
from _common import emit, freshness_report  # noqa: E402


# --- Pretty printers ----------------------------------------------------

def _print_states(payload):
    print(f"States entitled to appear  ({len(payload['states'])} entries)")
    print(f"  source: {payload['url']}")
    print(f"  fetched: {time.strftime('%Y-%m-%d', time.gmtime(payload['fetched_at']))}")
    print()
    for s in payload["states"]:
        decl = f"  declaration: {s['declaration_date']}" if s.get("declaration_date") else ""
        print(f"- {s['state']:<55} admitted {s['admission_date']}{decl}")


def _print_decl_index(payload):
    print(f"Article 36(2) declarations on file: {payload['count']}")
    print(f"  source: {payload['url']}")
    print()
    for s in payload["states"]:
        print(f"  {s['iso2']}  {s['state']:<35}  {s['deposit_date']}")


def _print_decl_show(payload):
    if "error" in payload:
        print(f"ERROR: {payload['error']}")
        for k in ("hint", "matches"):
            if k in payload:
                print(f"  {k}: {payload[k]}")
        return
    print(f"=== {payload['state']}  ({payload['iso2']}) ===")
    print(f"source: {payload['url']}")
    print()
    print(payload["text"])


def _print_decl_compare(payload):
    for d in payload["declarations"]:
        _print_decl_show(d)
        print()
        print("-" * 72)
        print()


def _print_cases_list(payload):
    src = payload.get("source_url", "")
    print(
        f"{payload['count_returned']} cases (of {payload['count_total']} total)  "
        f"source: {src}"
    )
    for c in payload["cases"][:200]:
        cid = c["case_id"] if c["case_id"] is not None else "  -"
        print(
            f"  [{cid}] {c['title'][:90]:<90}  "
            f"{c['year_introduced']}/{c['year_concluded']}  {c['kind']}"
        )


def _print_case_show(payload):
    print(f"=== {payload['title']} (case {payload['case_id']}) ===")
    print(f"  url: {payload['url']}")
    print(
        f"  decision documents: {payload['decision_documents_count']}  "
        f"(pleadings excluded: {payload['pleadings_excluded_count']})"
    )
    print()
    for sec in payload.get("decision_sections", []):
        print(f"--- {sec['section']} ---")
        for it in sec["items"]:
            date = it.get("date") or ""
            print(f"  {date:<11} {it['label']}")
            print(f"      {it['url']}")
        print()
    if payload.get("pleadings_sections"):
        for sec in payload["pleadings_sections"]:
            print(f"--- {sec['section']} (pleadings — included on request) ---")
            for it in sec["items"]:
                print(f"  {it['label']}  {it['url']}")
            print()
    if payload.get("unknown_sections"):
        print("--- other sections ---")
        for sec in payload["unknown_sections"]:
            print(f"  ({sec['section']}: {len(sec['items'])} items)")


def _print_recent(payload):
    print(f"Latest decisions ({payload['count']}):")
    for d in payload["decisions"]:
        print(f"  {d['decision_title']}  --  {d['case_title']}  (case {d['case_id']})")
        if d.get("subtitle"):
            print(f"     {d['subtitle']}")
        for p in d["pdfs"]:
            print(f"     {p['lang']}: {p['url']}")


def _print_pcij_list(payload):
    if "error" in payload:
        print(f"ERROR: {payload['error']}")
        return
    for series, data in payload.items():
        print(f"=== PCIJ Series {series.upper()} ({len(data['cases'])} cases) ===")
        for c in data["cases"]:
            print(f"  {c['code']}  {c.get('title') or '(no title)'}")
        print()


def _print_pcij_show(payload):
    if "error" in payload:
        print(f"ERROR: {payload['error']}")
        return
    c = payload["case"]
    print(f"=== {c['code']}  {c.get('title') or ''} ===")
    print(f"  series: {payload['series']}  source: {payload['source_url']}")
    for d in c["documents"]:
        print(f"  - {d['label']}")
        print(f"      {d['url']}")


def _print_treaties(payload):
    print(f"Treaties conferring jurisdiction: {payload['count']} matched")
    for t in payload["items"][:200]:
        print(f"  - {t['text'][:120]}")
        if t.get("url"):
            print(f"      {t['url']}")


def _print_text_block(payload):
    print(f"source: {payload['url']}")
    print(f"fetched: {time.strftime('%Y-%m-%d', time.gmtime(payload['fetched_at']))}")
    print()
    print(payload["text"])


def _print_freshness(reports):
    for r in reports:
        if not r.get("cached"):
            print(f"  {r['url']}  -- not cached")
            continue
        flag = "CHANGED" if r.get("changed") else "ok"
        reason = f" ({r['reason']})" if r.get("reason") else ""
        print(f"  {flag:<8} {r['url']}  age={r['age_days']}d  head={r.get('head_status')}{reason}")


# --- Argument parsing ---------------------------------------------------

def _add_common_flags(p):
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.add_argument("--force-refresh", action="store_true", help="bypass cache")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="icj", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="report cache freshness for jurisdiction pages")
    p_status.add_argument("--json", action="store_true")

    p_refresh = sub.add_parser("refresh", help="re-fetch jurisdiction pages that have changed")
    p_refresh.add_argument("--all", action="store_true",
                           help="refresh every page, not just changed ones")
    p_refresh.add_argument("--json", action="store_true")

    p_cases = sub.add_parser("cases")
    cases_sub = p_cases.add_subparsers(dest="sub", required=True)
    pl = cases_sub.add_parser("list")
    _add_common_flags(pl)
    pl.add_argument("--year", type=int)
    pl.add_argument("--country", type=str)
    pl.add_argument("--advisory", action="store_true")
    pl.add_argument("--contentious", action="store_true")
    pl.add_argument("--pending", action="store_true")
    psh = cases_sub.add_parser("show")
    _add_common_flags(psh)
    psh.add_argument("case_id", type=int)
    psh.add_argument("--include-pleadings", action="store_true",
                     help="include pleadings + verbatim records (off by default)")
    prc = cases_sub.add_parser("recent")
    _add_common_flags(prc)
    prc.add_argument("--limit", type=int, default=20)
    psr = cases_sub.add_parser("search")
    _add_common_flags(psr)
    psr.add_argument("query", type=str)

    p_pcij = sub.add_parser("pcij")
    pcij_sub = p_pcij.add_subparsers(dest="sub", required=True)
    pp_list = pcij_sub.add_parser("list")
    _add_common_flags(pp_list)
    pp_list.add_argument("--series", choices=["a", "b", "ab", "all"], default="all")
    pp_show = pcij_sub.add_parser("show")
    _add_common_flags(pp_show)
    pp_show.add_argument("code", type=str, help="e.g. A10, B04, A/B53")

    p_jur = sub.add_parser("jurisdiction")
    jur_sub = p_jur.add_subparsers(dest="sub", required=True)
    for name in ["states", "non-un", "non-parties", "basis", "organs"]:
        sp = jur_sub.add_parser(name)
        _add_common_flags(sp)
    pt = jur_sub.add_parser("treaties")
    _add_common_flags(pt)
    pt.add_argument("--year", type=int)
    pt.add_argument("--search", type=str)

    p_decl = sub.add_parser("declarations")
    decl_sub = p_decl.add_subparsers(dest="sub", required=True)
    dl = decl_sub.add_parser("list")
    _add_common_flags(dl)
    ds = decl_sub.add_parser("show")
    _add_common_flags(ds)
    ds.add_argument("state", type=str)
    dc = decl_sub.add_parser("compare")
    _add_common_flags(dc)
    dc.add_argument("states", type=str, nargs="+")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        from _common import _load_manifest
        urls = jur_mod.all_jurisdiction_urls()
        manifest = _load_manifest()
        urls = urls + sorted(u for u in manifest.keys() if "/declarations/" in u and u not in urls)
        rep = freshness_report(urls)
        emit(rep, as_json=args.json, human_fn=_print_freshness)
        return 0

    if args.cmd == "refresh":
        from _common import _load_manifest, fetch_cached
        urls = jur_mod.all_jurisdiction_urls()
        manifest = _load_manifest()
        urls = urls + sorted(u for u in manifest.keys() if "/declarations/" in u and u not in urls)
        if args.all:
            targets = urls
        else:
            rep = freshness_report(urls)
            targets = [r["url"] for r in rep if r.get("changed")]
        results = []
        for u in targets:
            try:
                _, entry, _ = fetch_cached(u, force_refresh=True)
                results.append({"url": u, "ok": True, "fetched_at": entry.fetched_at})
            except Exception as e:
                results.append({"url": u, "ok": False, "error": str(e)})

        def _hum(r):
            if not r:
                print("(nothing to refresh)")
                return
            for x in r:
                tag = "ok  " if x["ok"] else "FAIL"
                err = f"  -- {x.get('error','')}" if not x["ok"] else ""
                print(f"  {tag} {x['url']}{err}")

        emit(results, as_json=args.json, human_fn=_hum)
        return 0

    if args.cmd == "cases":
        if args.sub == "list":
            payload = cases_mod.list_all(force_refresh=args.force_refresh, year=args.year,
                                         country=args.country, advisory=args.advisory,
                                         contentious=args.contentious, pending=args.pending)
            emit(payload, as_json=args.json, human_fn=_print_cases_list)
        elif args.sub == "show":
            payload = cases_mod.show(args.case_id, force_refresh=args.force_refresh,
                                     include_pleadings=args.include_pleadings)
            emit(payload, as_json=args.json, human_fn=_print_case_show)
        elif args.sub == "recent":
            payload = cases_mod.recent(limit=args.limit, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_recent)
        elif args.sub == "search":
            payload = cases_mod.search(args.query, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_cases_list)
        return 0

    if args.cmd == "pcij":
        if args.sub == "list":
            payload = pcij_mod.list_cases(series=args.series, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_pcij_list)
        elif args.sub == "show":
            payload = pcij_mod.show(args.code, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_pcij_show)
        return 0

    if args.cmd == "jurisdiction":
        if args.sub == "states":
            payload = jur_mod.states(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_states)
        elif args.sub == "non-un":
            payload = jur_mod.non_un_parties(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_text_block)
        elif args.sub == "non-parties":
            payload = jur_mod.non_parties(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_text_block)
        elif args.sub == "basis":
            payload = jur_mod.basis(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_text_block)
        elif args.sub == "treaties":
            payload = jur_mod.treaties(force_refresh=args.force_refresh, year=args.year, search=args.search)
            emit(payload, as_json=args.json, human_fn=_print_treaties)
        elif args.sub == "organs":
            payload = jur_mod.organs(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_text_block)
        return 0

    if args.cmd == "declarations":
        if args.sub == "list":
            payload = decl_mod.index(force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_decl_index)
        elif args.sub == "show":
            payload = decl_mod.show(args.state, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_decl_show)
        elif args.sub == "compare":
            payload = decl_mod.compare(args.states, force_refresh=args.force_refresh)
            emit(payload, as_json=args.json, human_fn=_print_decl_compare)
        return 0

    parser.error("no subcommand")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
