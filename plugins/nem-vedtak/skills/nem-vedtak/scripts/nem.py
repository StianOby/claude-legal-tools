#!/usr/bin/env python3
"""nem.py — NEM-vedtak (Den nasjonale forskningsetiske komité for medisin og
helsefag) from forskningsetikk.no: a local full-text copy, or one decision live.

  nem.py sync   --dir D [--workers 4] [--time-budget 150] [--force] [--no-facets]
  nem.py status --dir D
  nem.py search --dir D [PHRASE ...] [--regex] [--any] [--section S]
                [--utfall X] [--emneord X] [--prinsipp X] [--lov X]
                [--forsteinstans X] [--institusjon X] [--klager X] [--year Y[-Y]]
                [--context N] [--snippets N] [--limit N] [--json]
  nem.py get    REF [--dir D] [--section S] [--meta]
  nem.py facets --dir D
  nem.py pdf    REF --out DIR [--dir D]

REF is a saksnr (2026/52, NEM 2022-32), a page URL, a slug, or title words.
Without --dir, `get` and `pdf` look the decision up live on the website.

The copy in D: one Markdown file per decision in D/vedtak/ (front matter with
saksnr, parties, outcome, keywords, principles, statutes; then the text by
section) and D/index.json. `sync` is incremental (sitemap lastmod) and
resumable: when the time budget runs out it saves what it has and says
INCOMPLETE; run it again. Standard library only (Python >= 3.10).
"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

BASE = "https://www.forskningsetikk.no"
LIST_PATH = "/om-oss/komiteer-og-utvalg/nem/sok-i-nems-vedtak/"
LIST_URL = BASE + LIST_PATH
SITEMAP_URL = BASE + "/sitemaps/forskningsetikk/no/content.xml"
UA = "nem-vedtak-skill/0.3.6 (+https://github.com/StianOby/claude-legal-tools)"
PAGE_SIZE = 10
# How a decision's text is converted. A decision in the copy with another
# (or no) text_format is fetched again on the next sync. 2 (0.3.6): soft
# hyphens are kept, PDF text keeps its printed lines (pdftotext -raw).
TEXT_FORMAT = 2

# List-page filter parameter -> front-matter key. Institusjon (ni) and
# Førsteinstans (nfi) are on the decision pages themselves.
FACETS = {
    "ndt": "utfall",
    "nt": "emneord",
    "nre": "prinsipper",
    "nra": "helseforskningsloven",
    "nol": "andre_lover",
}
FACET_KEYS = list(FACETS.values())
DL_KEYS = {"Institusjon": "institusjon", "Klager": "klager",
           "Førsteinstans": "forsteinstans", "Henvisninger": "henvisninger"}
LIVE_NOTE = ("Note: looked up live. A local copy (`sync`) adds phrase/regex search "
             "across all decisions and each decision's utfall, emneord, "
             "forskningsetiske prinsipper and statute chapters.")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- fetching

def fetch(url, binary=False, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 405, 410):
                raise
            last = e
        except Exception as e:  # network hiccup
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


def list_url(params):
    return LIST_URL + "?" + urllib.parse.urlencode(params) if params else LIST_URL


# ---------------------------------------------------------------- parsing

def clean(s):
    s = html.unescape(s).replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def strip_tags(s):
    return clean(re.sub(r"<[^>]+>", "", s))


def slug_of(url):
    path = urllib.parse.urlparse(urllib.parse.unquote(html.unescape(url))).path
    return path.rstrip("/").rsplit("/", 1)[-1]


def norm_saksnr(raw):
    m = re.search(r"(\d{4})\s*[/-]\s*(\d+)", raw or "")
    return f"{m.group(1)}/{int(m.group(2))}" if m else None


def file_name(saksnr, slug):
    head = "{}-{:03d}".format(*map(int, saksnr.split("/"))) if saksnr else "0000-000"
    tail = slug[:60] + ("-%04x" % (zlib.crc32(slug.encode()) & 0xFFFF) if len(slug) > 60 else "")
    return f"{head}_{tail}.md"


def html_to_md(fragment):
    """Body HTML of a decision -> Markdown with ## section headings."""
    s = re.sub(r"<(script|style)\b.*?</\1>", "", fragment, flags=re.S | re.I)
    s = re.sub(r"<h2[^>]*class=\"[^\"]*h3[^\"]*\"[^>]*>(.*?)</h2>",
               lambda m: "\n\n### " + strip_tags(m.group(1)) + "\n\n", s, flags=re.S | re.I)
    s = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>",
               lambda m: "\n\n" + "#" * max(2, int(m.group(1))) + " " + strip_tags(m.group(2)) + "\n\n",
               s, flags=re.S | re.I)
    s = re.sub(r"<li[^>]*>", "\n- ", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</?(p|div|ul|ol|table|tr|blockquote|dl|dt|dd)\b[^>]*>", "\n\n", s, flags=re.I)
    s = re.sub(r"</t[dh]>", " | ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    lines = [clean(l) for l in s.split("\n")]
    out, blank = [], True
    for l in lines:
        if not l:
            if not blank:
                out.append("")
            blank = True
            continue
        if l.startswith("#") and not blank:
            out.append("")
        out.append(l)
        blank = l.startswith("#")
        if blank:
            out.append("")
    return "\n".join(out).strip() + "\n"


def parse_page(page, url):
    """Decision page HTML -> metadata dict + Markdown body."""
    m = re.search(r'<div id="contents">(.*)</div>\s*</div>\s*</article>', page, flags=re.S)
    c = m.group(1) if m else page[page.find("<main"):page.find("</main>")]
    meta = {"url": BASE + LIST_PATH + slug_of(url) + "/", "slug": slug_of(url)}
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", c, flags=re.S)
    meta["title"] = strip_tags(h1.group(1)) if h1 else meta["slug"]
    h2 = re.search(r"<h2[^>]*>\s*<span[^>]*>(.*?)</span>\s*\|\s*\[\s*<span[^>]*>(.*?)</span>\s*\]\s*</h2>", c, flags=re.S)
    raw = strip_tags(h2.group(1)) if h2 else ""
    meta["saksnr"] = norm_saksnr(raw)
    meta["saksnr_raw"] = raw
    meta["sakstype"] = strip_tags(h2.group(2)).capitalize() if h2 else None
    dl = re.search(r"<dl>(.*?)</dl>", c, flags=re.S)
    for key in DL_KEYS.values():
        meta[key] = [] if key in ("institusjon", "forsteinstans") else ""
    if dl:
        for dt, dd in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", dl.group(1), flags=re.S):
            key = DL_KEYS.get(strip_tags(dt))
            if not key:
                continue
            links = [strip_tags(a) for a in re.findall(r"<a[^>]*>(.*?)</a>", dd, flags=re.S)]
            meta[key] = links if key in ("institusjon", "forsteinstans") and links else \
                ([strip_tags(dd)] if key in ("institusjon", "forsteinstans") else
                 re.sub(r"\n{2,}", "\n", html_to_md(dd)).strip())
    pdf = re.search(r'href="([^"]+\.pdf)"', c, flags=re.I)
    meta["pdf"] = urllib.parse.urljoin(BASE, html.unescape(pdf.group(1))) if pdf else None
    # Body: everything after the metadata block / PDF box.
    start = 0
    for pat in (r"</dl>", r'class="download[^"]*"[^>]*>.*?</div>'):
        mm = None
        for mm in re.finditer(pat, c, flags=re.S):
            pass
        if mm:
            start = max(start, mm.end())
    if not start and h2:
        start = h2.end()
    body = html_to_md(c[start:])
    return meta, body


def parse_list(page):
    """Result list page -> (total, [slug, ...])."""
    tot = re.search(r"(\d+)\s+resultat", page)
    slugs = [slug_of(h) for h in re.findall(
        r'<article>\s*<a href="([^"]*sok-i-nems-vedtak/[^"]+)"', page)]
    return (int(tot.group(1)) if tot else 0), slugs


def parse_list_items(page):
    """Result list page -> [{slug, title, saksnr_raw}] for live lookups."""
    out = []
    for art in re.findall(r"<article>(.*?)</article>", page, flags=re.S):
        a = re.search(r'<a href="([^"]*sok-i-nems-vedtak/[^"]+)"[^>]*>\s*<h3[^>]*>(.*?)</h3>', art, flags=re.S)
        if not a:
            continue
        st = re.search(r"<strong>(.*?)</strong>", art, flags=re.S)
        raw = strip_tags(st.group(1)) if st else ""
        out.append({"slug": slug_of(a.group(1)), "title": strip_tags(a.group(2)),
                    "saksnr": norm_saksnr(raw), "saksnr_raw": raw})
    return out


def parse_filters(page):
    """List page -> {param: [value, ...]} for the filter checkboxes."""
    out = {}
    for name, val in re.findall(r'<input[^>]*name="(n[a-z]+)"[^>]*value="([^"]*)"', page):
        out.setdefault(name, [])
        v = html.unescape(val)
        if v not in out[name]:
            out[name].append(v)
    return out


def parse_sitemap(xml):
    out = {}
    for block in re.findall(r"<url>(.*?)</url>", xml, flags=re.S):
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block)
        if not loc or "/sok-i-nems-vedtak/" not in loc.group(1):
            continue
        slug = slug_of(loc.group(1))
        if not slug or slug == "sok-i-nems-vedtak":
            continue
        lm = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", block)
        out[slug] = {"url": html.unescape(loc.group(1)), "lastmod": lm.group(1) if lm else None}
    return out


# ---------------------------------------------------------------- Markdown files

FM_ORDER = ["saksnr", "saksnr_raw", "title", "sakstype", "url", "pdf", "lastmod",
            "institusjon", "klager", "forsteinstans", "henvisninger",
            *FACET_KEYS, "text_source"]


def render_md(meta, body):
    fm = ["---"] + [f"{k}: {json.dumps(meta[k], ensure_ascii=False)}" for k in FM_ORDER if k in meta] + ["---", ""]
    return "\n".join(fm) + f"# {meta.get('title')}\n\n" + body


def read_md(path):
    t = Path(path).read_text(encoding="utf-8")
    if not t.startswith("---\n"):
        return {}, t
    end = t.index("\n---\n", 4)
    meta = {}
    for line in t[4:end].splitlines():
        k, _, v = line.partition(": ")
        try:
            meta[k] = json.loads(v)
        except ValueError:
            meta[k] = v
    body = t[end + 5:]
    body = re.sub(r"\A\s*# .*\n+", "", body)
    return meta, body


def sections(body):
    """Body -> [(heading, text)] split on ## headings ('' before the first)."""
    out, head, buf = [], "", []
    for line in body.splitlines():
        if line.startswith("## "):
            out.append((head, "\n".join(buf)))
            head, buf = line[3:].strip(), []
        else:
            buf.append(line)
    out.append((head, "\n".join(buf)))
    return [(h, t) for h, t in out if t.strip() or h]


# ---------------------------------------------------------------- sync

def pdf_text(pdf_path):
    # -raw: the default mode joins each paragraph into one line and drops a
    # hyphen at a line break even where the word has one ("non-\nprofit").
    if not shutil.which("pdftotext"):
        return None
    r = subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", str(pdf_path), "-"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def fetch_decision(slug, url, root):
    page = fetch(url)
    meta, body = parse_page(page, url)
    meta["text_source"] = "html"
    if len(re.sub(r"\s+", "", body)) < 400 and meta.get("pdf"):
        # PDF-only decision: keep the PDF and use its text.
        pdir = root / "pdf"
        pdir.mkdir(exist_ok=True)
        dest = pdir / (Path(file_name(meta["saksnr"], slug)).stem + ".pdf")
        dest.write_bytes(fetch(meta["pdf"], binary=True))
        txt = pdf_text(dest)
        if txt:
            body = "## Tekst fra PDF\n\n" + re.sub(r"\n{3,}", "\n\n", txt.replace("\f", "\n\n")).strip() + "\n"
            meta["text_source"] = "pdf"
        else:
            meta["text_source"] = "pdf (no pdftotext: text not extracted)"
    return meta, body


def fetch_facets(workers, deadline):
    """{slug: {facet_key: [values]}} by paging every filter value."""
    first = fetch(LIST_URL)
    filters = parse_filters(first)
    jobs = [(p, v) for p in FACETS for v in filters.get(p, [])]
    if not jobs:
        raise RuntimeError("no filter values found on the list page (site changed?)")
    result, pages = {}, {}

    def one(p, v, n):
        return p, v, n, parse_list(fetch(list_url({p: v, "p": n} if n else {p: v})))

    with ThreadPoolExecutor(workers) as ex:
        todo = [ex.submit(one, p, v, 0) for p, v in jobs]
        while todo:
            nxt = []
            for f in as_completed(todo):
                if time.time() > deadline:
                    ex.shutdown(cancel_futures=True)
                    raise TimeoutError
                p, v, n, (total, slugs) = f.result()
                pages.setdefault((p, v), {})[n] = slugs
                if n == 0:
                    for k in range(1, -(-total // PAGE_SIZE)):
                        nxt.append(ex.submit(one, p, v, k))
            todo = nxt
    for (p, v), by_page in pages.items():
        for slugs in by_page.values():
            for s in slugs:
                lst = result.setdefault(s, {}).setdefault(FACETS[p], [])
                if v not in lst:
                    lst.append(v)
    return result, {FACETS[p]: filters.get(p, []) for p in FACETS}


def load_index(root):
    f = root / "index.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"vedtak": {}}


def save_index(root, idx):
    (root / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


README_TXT = """\
NEM-vedtak – lokal kopi / local copy

Denne mappen er en lokal kopi av NEMs vedtak fra forskningsetikk.no, laget av
nem-vedtak-skillen (https://github.com/StianOby/claude-legal-tools). Koble til
den samme mappen (eller en mappe over den) i Claude neste gang, så brukes og
oppdateres denne kopien i stedet for at det lages en ny. Vedtakene ligger som
tekstfiler i vedtak/ og kan leses i en hvilken som helst editor.

This folder is a local copy of NEM's decisions from forskningsetikk.no, made by
the nem-vedtak skill. Connect this same folder (or a folder above it) in Claude
next time, and this copy is reused and updated instead of a new one being made.
The decisions are plain-text files in vedtak/.
"""


def cmd_sync(a):
    root = Path(a.dir)
    (root / "vedtak").mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists() or readme.read_text(encoding="utf-8") != README_TXT:
        readme.write_text(README_TXT, encoding="utf-8")
    deadline = time.time() + a.time_budget
    idx = load_index(root)
    ved = idx["vedtak"]
    sm = parse_sitemap(fetch(SITEMAP_URL))
    if not sm:
        sys.exit("sitemap has no NEM decisions (site changed?)")

    facets = idx.get("facets_by_slug")
    facets_fresh = False
    if not a.no_facets:
        try:
            facets, idx["facet_values"] = fetch_facets(a.workers, deadline)
            idx["facets_by_slug"], idx["facets_fetched"] = facets, date.today().isoformat()
            facets_fresh = True
        except TimeoutError:
            print("facets: time budget ran out; keeping the previous facets")
        except Exception as e:
            print(f"facets: failed ({e}); keeping the previous facets")
    facets = facets or {}

    todo = [s for s, v in sm.items()
            if a.force or s not in ved or ved[s].get("lastmod") != v["lastmod"]
            or ved[s].get("text_format") != TEXT_FORMAT
            or not (root / "vedtak" / ved[s]["file"]).exists()]
    done, failed, timed_out, seen = 0, [], False, set()

    def write(slug, meta, body):
        seen.add(slug)
        meta["lastmod"] = sm[slug]["lastmod"]
        for k in FACET_KEYS:
            meta[k] = facets.get(slug, {}).get(k, []) if facets else None
        fn = file_name(meta.get("saksnr"), slug)
        old = ved.get(slug, {}).get("file")
        (root / "vedtak" / fn).write_text(render_md(meta, body), encoding="utf-8")
        if old and old != fn:
            print(f"note: {old} renamed to {fn}; the old file is left in place")
        ved[slug] = {k: meta.get(k) for k in FM_ORDER} | {"file": fn, "text_format": TEXT_FORMAT}

    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch_decision, s, sm[s]["url"], root): s for s in todo}
        try:
            for f in as_completed(futs):
                s = futs[f]
                try:
                    write(s, *f.result())
                    done += 1
                except Exception as e:
                    failed.append(f"{s}: {e}")
                if time.time() > deadline:
                    timed_out = True
                    break
        finally:
            if timed_out:
                ex.shutdown(cancel_futures=True)
                for f in futs:
                    if f.done() and not f.cancelled() and futs[f] not in seen:
                        try:
                            write(futs[f], *f.result())
                            done += 1
                        except Exception:
                            pass

    # Facets changed for decisions that were not refetched: rewrite front matter.
    retagged = 0
    if facets_fresh:
        for s, rec in ved.items():
            if s in todo or s not in sm:
                continue
            new = {k: facets.get(s, {}).get(k, []) for k in FACET_KEYS}
            if any(rec.get(k) != new[k] for k in FACET_KEYS):
                p = root / "vedtak" / rec["file"]
                if p.exists():
                    meta, body = read_md(p)
                    meta.update(new)
                    p.write_text(render_md(meta, body), encoding="utf-8")
                    rec.update(new)
                    retagged += 1

    removed = [s for s in ved if s not in sm and not ved[s].get("removed")]
    for s in removed:
        ved[s]["removed"] = True  # files in the user's folder are never deleted
    idx["source"], idx["last_sync"] = LIST_URL, date.today().isoformat()
    idx["count"] = sum(1 for v in ved.values() if not v.get("removed"))
    save_index(root, idx)

    left = len(todo) - done - len(failed)
    print(f"sitemap: {len(sm)} decisions; fetched {done} new/changed, "
          f"{len(sm) - len(todo)} unchanged; facets {'updated' if facets_fresh else 'not updated'}"
          f"{f' (front matter updated for {retagged})' if retagged else ''}")
    if removed:
        print(f"no longer on the site (marked removed in index.json): {', '.join(removed)}")
    for f in failed:
        print("FAILED", f)
    if not a.no_facets and not idx.get("facets_by_slug"):
        print("facets missing (utfall, emneord, … are empty); run sync again")
    if left > 0:
        print(f"INCOMPLETE: {left} decisions left; run sync again")
    else:
        print(f"OK: {idx['count']} decisions in {root / 'vedtak'}")


def cmd_status(a):
    root = Path(a.dir)
    if not (root / "index.json").exists():
        print(f"no copy in {root}; run sync")
        return
    idx = load_index(root)
    v = [x for x in idx["vedtak"].values() if not x.get("removed")]
    years = sorted(x["saksnr"][:4] for x in v if x.get("saksnr"))
    print(f"{len(v)} decisions ({years[0] if years else '?'}–{years[-1] if years else '?'}), "
          f"last sync {idx.get('last_sync')}, facets {idx.get('facets_fetched') or 'missing'}")
    srcs = {}
    for x in v:
        srcs[x.get("text_source")] = srcs.get(x.get("text_source"), 0) + 1
    print("text source:", ", ".join(f"{k}: {n}" for k, n in srcs.items()))


# ---------------------------------------------------------------- search

def norm(s):
    return re.sub(r"\s+", " ", s.replace("\xad", "")).casefold()


def load_corpus(root):
    idx = load_index(root)
    if not idx["vedtak"]:
        sys.exit(f"no copy in {root}; run sync first")
    out = []
    for slug, rec in idx["vedtak"].items():
        if rec.get("removed"):
            continue
        p = root / "vedtak" / rec["file"]
        if p.exists():
            meta, body = read_md(p)
            out.append((slug, meta, body))
    return out


def year_ok(saksnr, spec):
    if not spec:
        return True
    if not saksnr:
        return False
    y = int(saksnr[:4])
    lo, _, hi = spec.partition("-")
    return int(lo) <= y <= int(hi or lo)


def field_ok(meta, keys, needle):
    if not needle:
        return True
    n = norm(needle)
    for k in keys:
        v = meta.get(k)
        vals = v if isinstance(v, list) else [v] if v else []
        if any(n in norm(str(x)) for x in vals):
            return True
    return False


def cmd_search(a):
    corpus = load_corpus(Path(a.dir))
    if a.regex:
        pats = [re.compile(t, re.I | re.S) for t in a.terms]
    else:  # phrase: case-insensitive, any whitespace between words
        pats = [re.compile(r"\s+".join(map(re.escape, t.split())), re.I) for t in a.terms]
    filters = [(["utfall"], a.utfall), (["emneord"], a.emneord), (["prinsipper"], a.prinsipp),
               (["helseforskningsloven", "andre_lover", "henvisninger"], a.lov),
               (["forsteinstans"], a.forsteinstans), (["institusjon"], a.institusjon),
               (["klager"], a.klager)]
    hits = []
    for slug, meta, body in corpus:
        if not year_ok(meta.get("saksnr"), a.year):
            continue
        if not all(field_ok(meta, k, n) for k, n in filters):
            continue
        # The text keeps the site's soft hyphens ("helse\xadundersøkelsene");
        # search it without them so a typed word matches.
        secs = [(h, t.replace("\xad", "")) for h, t in sections(body)
                if not a.section or norm(a.section) in norm(h)]
        if a.section and not secs:
            continue
        found, snips = set(), []
        for i, p in enumerate(pats):
            for h, t in secs:
                for m in p.finditer(t):
                    found.add(i)
                    if len(snips) < a.snippets:
                        s0, s1 = max(0, m.start() - a.context), min(len(t), m.end() + a.context)
                        snip = re.sub(r"\s+", " ", t[s0:s1]).strip()
                        snips.append({"section": h or "(innledning)",
                                      "text": ("…" if s0 else "") + snip + ("…" if s1 < len(t) else "")})
                    if len(snips) >= a.snippets and i in found:
                        break
        if pats and not (found if a.any else len(found) == len(pats)):
            continue
        hits.append({"saksnr": meta.get("saksnr"), "title": meta.get("title"),
                     "utfall": meta.get("utfall"), "forsteinstans": meta.get("forsteinstans"),
                     "url": meta.get("url"), "file": file_name(meta.get("saksnr"), slug),
                     "snippets": snips})
    hits.sort(key=lambda h: tuple(map(int, (h["saksnr"] or "0/0").split("/"))), reverse=True)
    if a.json:
        print(json.dumps({"total": len(hits), "searched": len(corpus), "hits": hits[:a.limit]},
                         ensure_ascii=False, indent=1))
        return
    print(f"{len(hits)} of {len(corpus)} decisions match" +
          (f"; showing {a.limit}" if len(hits) > a.limit else ""))
    for h in hits[:a.limit]:
        ut = "; ".join(h["utfall"] or []) or "?"
        print(f"\nNEM {h['saksnr']} — {h['title']}\n  {ut} | {', '.join(h['forsteinstans'] or [])} | {h['url']}\n  file: vedtak/{h['file']}")
        for s in h["snippets"]:
            print(f"  [{s['section']}] {s['text']}")


def cmd_facets(a):
    idx = load_index(Path(a.dir))
    vals = idx.get("facet_values") or {}
    by = idx.get("facets_by_slug") or {}
    live = {s for s, v in idx["vedtak"].items() if not v.get("removed")}
    for key in FACET_KEYS:
        print(f"\n{key}:")
        for v in vals.get(key, []):
            n = sum(1 for s in live if v in by.get(s, {}).get(key, []))
            print(f"  {n:4d}  {v}")
    for key in ("forsteinstans", "institusjon"):
        cnt = {}
        for s in live:
            for v in idx["vedtak"][s].get(key) or []:
                cnt[v] = cnt.get(v, 0) + 1
        print(f"\n{key}:")
        for v, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {n:4d}  {v}")


# ---------------------------------------------------------------- get / pdf

def resolve_local(root, ref):
    idx = load_index(root)
    ved = {s: v for s, v in idx["vedtak"].items() if not v.get("removed")}
    sn = norm_saksnr(ref) if re.fullmatch(r"\s*(NEM\s*)?\d{4}\s*[/-]\s*\d+\s*", ref, re.I) else None
    if sn:
        return [s for s, v in ved.items() if v.get("saksnr") == sn]
    slug = slug_of(ref) if "/" in ref else ref.strip()
    if slug in ved:
        return [slug]
    n = norm(ref)
    return [s for s, v in ved.items() if n in norm(v.get("title") or "")]


def resolve_live(ref):
    """REF -> [(slug, title, saksnr)] using the site's own search."""
    if ref.startswith("http"):
        return [(slug_of(ref), None, None)]
    sn = norm_saksnr(ref) if re.fullmatch(r"\s*(NEM\s*)?\d{4}\s*[/-]\s*\d+\s*", ref, re.I) else None
    q = sn or ref
    found = []
    for n in range(6):
        page = fetch(list_url({"q": q, "p": n} if n else {"q": q}))
        items = parse_list_items(page)
        for it in items:
            if sn and it["saksnr"] == sn:
                found.append((it["slug"], it["title"], it["saksnr"]))
            elif not sn and norm(ref) in norm(it["title"]):
                found.append((it["slug"], it["title"], it["saksnr"]))
        if len(items) < PAGE_SIZE or (found and not sn):
            break
    if not found and not sn and re.fullmatch(r"[a-z0-9-]+", ref):
        found = [(ref, None, None)]
    return found


def pick(cands, ref):
    if not cands:
        sys.exit(f"no NEM decision found for {ref!r}")
    if len(cands) > 1:
        print(f"{len(cands)} decisions match {ref!r}; showing the first. Others:", file=sys.stderr)
        for c in cands[1:]:
            print("  ", *[x for x in (c if isinstance(c, tuple) else (c,)) if x], file=sys.stderr)
    return cands[0]


def cmd_get(a):
    if a.dir and (Path(a.dir) / "index.json").exists():
        root = Path(a.dir)
        slug = pick(resolve_local(root, a.ref), a.ref)
        meta, body = read_md(root / "vedtak" / load_index(root)["vedtak"][slug]["file"])
        live = False
    else:
        slug = pick(resolve_live(a.ref), a.ref)[0]
        meta, body = fetch_decision(slug, LIST_URL + slug + "/", Path(a.dir or "."))
        live = True
    if a.meta:
        print(json.dumps({k: meta.get(k) for k in FM_ORDER if not (live and k in FACET_KEYS)},
                         ensure_ascii=False, indent=1))
    else:
        if a.section:
            secs = [(h, t) for h, t in sections(body) if norm(a.section) in norm(h)]
            if not secs:
                sys.exit("no section matching %r; sections: %s" % (
                    a.section, ", ".join(h for h, _ in sections(body) if h)))
            body = "\n".join(f"## {h}\n{t}" for h, t in secs)
        print(render_md(meta, body))
    if live:
        print("\n" + LIVE_NOTE)


def cmd_pdf(a):
    if a.dir and (Path(a.dir) / "index.json").exists():
        slug = pick(resolve_local(Path(a.dir), a.ref), a.ref)
        url = load_index(Path(a.dir))["vedtak"][slug].get("pdf")
        saksnr = load_index(Path(a.dir))["vedtak"][slug].get("saksnr")
    else:
        slug = pick(resolve_live(a.ref), a.ref)[0]
        meta, _ = parse_page(fetch(LIST_URL + slug + "/"), LIST_URL + slug + "/")
        url, saksnr = meta.get("pdf"), meta.get("saksnr")
    if not url:
        sys.exit("this decision has no PDF on the site; the HTML text is the only version")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / (Path(file_name(saksnr, slug)).stem + ".pdf")
    dest.write_bytes(fetch(url, binary=True))
    print(f"saved {dest} ({dest.stat().st_size // 1024} KB) from {url}")


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("sync", help="download or update the local copy")
    p.add_argument("--dir", required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--time-budget", type=float, default=140,
                   help="seconds (default 140; a Cowork call dies at ~170 s)")
    p.add_argument("--force", action="store_true", help="refetch every decision")
    p.add_argument("--no-facets", action="store_true")
    p.set_defaults(fn=cmd_sync)

    p = sp.add_parser("status", help="what the local copy holds")
    p.add_argument("--dir", required=True)
    p.set_defaults(fn=cmd_status)

    p = sp.add_parser("search", help="phrase/regex search in the local copy")
    p.add_argument("--dir", required=True)
    p.add_argument("terms", nargs="*", help="phrases (all must occur; --any: at least one)")
    p.add_argument("--regex", action="store_true", help="terms are Python regexes (case-insensitive)")
    p.add_argument("--any", action="store_true")
    p.add_argument("--section", help="only sections whose heading contains this (e.g. vurdering)")
    for f in ("utfall", "emneord", "prinsipp", "lov", "forsteinstans", "institusjon", "klager"):
        p.add_argument("--" + f)
    p.add_argument("--year", help="YYYY or YYYY-YYYY (from saksnr)")
    p.add_argument("--context", type=int, default=200)
    p.add_argument("--snippets", type=int, default=3)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_search)

    p = sp.add_parser("get", help="one decision (local copy, else live)")
    p.add_argument("ref")
    p.add_argument("--dir")
    p.add_argument("--section")
    p.add_argument("--meta", action="store_true")
    p.set_defaults(fn=cmd_get)

    p = sp.add_parser("facets", help="list facet values with counts")
    p.add_argument("--dir", required=True)
    p.set_defaults(fn=cmd_facets)

    p = sp.add_parser("pdf", help="download the official PDF of one decision")
    p.add_argument("ref")
    p.add_argument("--out", required=True)
    p.add_argument("--dir")
    p.set_defaults(fn=cmd_pdf)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
