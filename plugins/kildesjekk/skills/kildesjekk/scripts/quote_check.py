#!/usr/bin/env python3
"""quote_check.py - compare the quotations of a batch with the saved passages.

    python quote_check.py kildesjekk_batches/<name>.json

For every row of the batch (written by `worklist.py batch`) this reads the
row's evidence file and compares the quotation with the passage, character
for character. It writes the result to the batch's quotes file and prints a
line per row. It gives a verdict on the wording only - never on severity,
and never on whether the passage supports the claim:

    exact            the quotation is in the passage as written
    marks_only       it is there once quotation marks are treated as alike
    differs          a near match was found; the differences are listed
    not_in_passage   no near match
    no_quotation     the row has no quoted text
    no_passage       the evidence holds no passage (outcome is not "found")

What is tolerated, and nothing else: runs of whitespace count as one space,
non-breaking spaces count as spaces, and soft hyphens are ignored. An
ellipsis splits a quotation into parts that must occur in order; a bracketed
insertion does the same and is listed for the reader to assess. Emphasis
(*italic*, **bold**) is compared only when the evidence says the source
text carries it (emphasis_known: yes).

Exit status: 0 when every row had usable evidence, 1 when some evidence was
missing or malformed (those rows are listed), 2 when the batch file could
not be read.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

PASSAGE_MARK = "--- passage ---"
EVIDENCE_FIELDS = ("key", "outcome", "source", "route", "locator",
                   "pinpoint_matches", "emphasis_known", "tools_tried", "note")
OUTCOMES = ("found", "not_here", "unavailable")

# Layout characters: built with chr() so that no tool can decode an escape
# on the way into this file.
NBSP, NARROW_NBSP, SOFT_HYPHEN = chr(0xA0), chr(0x202F), chr(0xAD)
_LAYOUT = {ord(NBSP): " ", ord(NARROW_NBSP): " ", ord(SOFT_HYPHEN): None}

DOUBLE_MARKS = "«»“”„‟\""
SINGLE_MARKS = "‘’‚'"
_UNIFY = {ord(c): '"' for c in DOUBLE_MARKS + SINGLE_MARKS}
OUTER_PAIRS = {("«", "»"), ("»", "«"), ("“", "”"), ("„", "“"), ("„", "”"),
               ('"', '"'), ("‘", "’"), ("'", "'")}

_DOTS = r"(?:\.\s?\.\s?\.|…)"
GAP = re.compile(r"\[\s*%s\s*\]|\(\s*%s\s*\)|%s|\[[^\]]*\]" % (_DOTS, _DOTS, _DOTS))
SEVERAL = re.compile(r"«[^«»]*»|“[^“”]*”")

VERDICT_ORDER = ("exact", "marks_only", "differs", "not_in_passage")


# --------------------------------------------------------------------------
# evidence files


def evidence_name(key):
    """The file name of a row's evidence: readable, and unique per key."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_") or "row"
    return "%s-%s.txt" % (slug, hashlib.sha1(key.encode("utf-8")).hexdigest()[:6])


def read_evidence(path, key=None):
    """Parse an evidence file. Returns (record, problems)."""
    problems = []
    path = Path(path)
    if not path.is_file():
        return None, ["no evidence file (%s)" % path.name]
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    record = {f: "" for f in EVIDENCE_FIELDS}
    record["passage"] = ""
    last = None
    at = None
    for i, line in enumerate(lines):
        if line.strip() == PASSAGE_MARK:
            at = i
            break
        m = re.match(r"^([a-z_]+)\s*:\s?(.*)$", line)
        if m and m.group(1) in EVIDENCE_FIELDS:
            last = m.group(1)
            record[last] = m.group(2).strip()
        elif line.strip() and last:
            record[last] = (record[last] + " " + line.strip()).strip()
        elif line.strip():
            problems.append("line %d is not a field: %r" % (i + 1, line[:60]))
    if at is not None:
        record["passage"] = "\n".join(lines[at + 1:]).strip("\n")

    outcome = record["outcome"].lower()
    record["outcome"] = outcome
    if not record["key"]:
        problems.append("no key field")
    elif key is not None and record["key"] != key:
        problems.append("the key field is %r, expected %r" % (record["key"], key))
    if outcome not in OUTCOMES:
        problems.append("outcome is %r; must be one of %s"
                        % (record["outcome"], "/".join(OUTCOMES)))
    elif outcome == "found":
        if at is None:
            problems.append('outcome is found, but there is no "%s" line' % PASSAGE_MARK)
        elif not record["passage"].strip():
            problems.append("outcome is found, but the passage is empty")
        for f in ("source", "locator"):
            if not record[f]:
                problems.append("outcome is found, but %s is empty" % f)
    else:
        if not record["tools_tried"]:
            problems.append("outcome is %s, but tools_tried is empty" % outcome)
    record["emphasis_known"] = record["emphasis_known"].lower() in ("yes", "true")
    return record, problems


# --------------------------------------------------------------------------
# text with emphasis flags


def parse(text, emphasis):
    """Text -> (plain, flags): whitespace collapsed, asterisks removed.

    flags[i] is 1 for italic, 2 for bold, 3 for both - all 0 when the text
    is read without emphasis.
    """
    text = (text or "").translate(_LAYOUT)
    plain, flags = [], []
    italic = bold = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "*":
            n = 1
            while i + n < len(text) and text[i + n] == "*":
                n += 1
            if emphasis:
                if n >= 3:
                    italic, bold = not italic, not bold
                elif n == 2:
                    bold = not bold
                else:
                    italic = not italic
            i += n
            continue
        state = (1 if italic else 0) | (2 if bold else 0)
        if c.isspace():
            if plain and plain[-1] != " ":
                plain.append(" ")
                flags.append(state)
        else:
            plain.append(c)
            flags.append(state)
        i += 1
    if plain and plain[-1] == " ":
        plain.pop()
        flags.pop()
    return "".join(plain), flags


def cut(plain, flags, a, b):
    """The slice [a:b] with spaces trimmed off both ends."""
    while a < b and plain[a] == " ":
        a += 1
    while b > a and plain[b - 1] == " ":
        b -= 1
    return plain[a:b], flags[a:b]


def render(plain, flags):
    """(plain, flags) back to text with *italic* and **bold** markers."""
    out = []
    i = 0
    while i < len(plain):
        j = i
        while j < len(plain) and flags[j] == flags[i]:
            j += 1
        run = plain[i:j]
        mark = "*" * {0: 0, 1: 1, 2: 2, 3: 3}[flags[i]]
        if mark and run.strip():
            lead = run[:len(run) - len(run.lstrip(" "))]
            trail = run[len(run.rstrip(" ")):]
            run = lead + mark + run.strip(" ") + mark + trail
        out.append(run)
        i = j
    return "".join(out)


def split_quotations(plain, flags):
    """The quotations in a "quoted text" cell, without their outer marks."""
    plain, flags = cut(plain, flags, 0, len(plain))
    spans = list(SEVERAL.finditer(plain))
    if (len(spans) > 1 and spans[0].start() == 0
            and spans[-1].end() == len(plain)):
        return [cut(plain, flags, m.start() + 1, m.end() - 1) for m in spans]
    if len(plain) >= 2 and (plain[0], plain[-1]) in OUTER_PAIRS:
        return [cut(plain, flags, 1, len(plain) - 1)]
    return [(plain, flags)]


def split_segments(plain, flags):
    """Split a quotation at ellipses and bracketed insertions.

    Returns (segments, insertions, omissions). A segment is a dict with the
    text, its flags, and whether each end touches an insertion with no
    space between (as in "[T]he"), where a word boundary is not expected.
    """
    segments, insertions, omissions = [], [], 0
    pos = 0
    prev_insert = False
    gaps = list(GAP.finditer(plain)) + [None]
    for m in gaps:
        end = m.start() if m else len(plain)
        raw = plain[pos:end]
        is_insert = False
        if m:
            token = m.group()
            inner = token[1:-1].strip()
            is_insert = token.startswith("[") and not re.fullmatch(_DOTS, inner)
            if is_insert:
                insertions.append(inner)
            else:
                omissions += 1
        text, fl = cut(plain, flags, pos, end)
        if text:
            segments.append({
                "text": text, "flags": fl,
                "glued_left": prev_insert and not raw.startswith(" "),
                "glued_right": is_insert and not raw.endswith(" "),
            })
        if m:
            pos = m.end()
            prev_insert = is_insert
    return segments, insertions, omissions


# --------------------------------------------------------------------------
# matching


def _occurrences(passage, seg):
    """Starts of seg in passage where it does not begin or end mid-word."""
    text = seg["text"]
    found = []
    start = passage.find(text)
    while start != -1:
        end = start + len(text)
        left_ok = (seg["glued_left"] or start == 0 or not text[0].isalnum()
                   or not passage[start - 1].isalnum())
        right_ok = (seg["glued_right"] or end == len(passage)
                    or not text[-1].isalnum() or not passage[end].isalnum())
        if left_ok and right_ok:
            found.append(start)
        start = passage.find(text, start + 1)
    return found


def _words(text):
    return re.findall(r"\S+", text)


def word_differences(source, quotation):
    """The places where two texts differ, word by word."""
    a, b = _words(source), _words(quotation)
    out = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append({
            "quotation": " ".join(b[j1:j2]),
            "source": " ".join(a[i1:i2]),
            "after": " ".join(a[max(0, i1 - 4):i1]),
        })
    return out


def nearest(passage, seg):
    """The stretch of the passage most like seg: (start, end, ratio) or None."""
    text = seg["text"]
    if len(text) < 4 or not passage:
        return None
    sm = difflib.SequenceMatcher(None, passage, text, autojunk=False)
    blocks = sorted((b for b in sm.get_matching_blocks() if b.size),
                    key=lambda b: -b.size)[:6]
    slack = max(10, len(text) // 5)
    best = None
    for block in blocks:
        lo = max(0, block.a - block.b - slack)
        hi = min(len(passage), block.a - block.b + len(text) + slack)
        window = passage[lo:hi]
        ops = difflib.SequenceMatcher(None, window, text, autojunk=False).get_opcodes()
        while ops and ops[0][0] == "delete":
            ops = ops[1:]
        while ops and ops[-1][0] == "delete":
            ops = ops[:-1]
        if not ops:
            continue
        a, b = lo + ops[0][1], lo + ops[-1][2]
        if not seg["glued_left"]:
            while 0 < a < len(passage) and passage[a - 1].isalnum() and passage[a].isalnum():
                a -= 1
        if not seg["glued_right"]:
            while 0 < b < len(passage) and passage[b - 1].isalnum() and passage[b].isalnum():
                b += 1
        ratio = difflib.SequenceMatcher(None, passage[a:b], text, autojunk=False).ratio()
        if best is None or ratio > best[2]:
            best = (a, b, ratio)
    if best and best[2] >= 0.7:
        return best
    return None


def check_quotation(q_plain, q_flags, p_plain, p_flags, emphasis_known):
    """Compare one quotation with the passage."""
    segments, insertions, omissions = split_segments(q_plain, q_flags)
    part = {"quotation": render(q_plain, q_flags) if emphasis_known else q_plain,
            "verdict": "exact", "differences": [], "insertions": insertions,
            "omissions": omissions, "emphasis": "not_compared", "source_text": ""}
    if not segments:
        part["verdict"] = "not_in_passage"
        return part

    p_unified = p_plain.translate(_UNIFY)
    placed = []          # (segment, start, end, how)
    pos = 0
    in_order = True
    for seg in segments:
        how = "exact"
        occ = _occurrences(p_plain, seg)
        if not occ:
            unified = dict(seg, text=seg["text"].translate(_UNIFY))
            occ = _occurrences(p_unified, unified)
            how = "marks_only"
        if occ:
            later = [o for o in occ if o >= pos]
            if not later:
                in_order = False
            start = later[0] if later else occ[0]
            end = start + len(seg["text"])
            if how == "marks_only":
                part["differences"].append({
                    "quotation": seg["text"], "source": p_plain[start:end],
                    "after": "", "note": "quotation marks only"})
        else:
            near = nearest(p_plain, seg)
            if near is None:
                placed.append((seg, None, None, "missing"))
                part["differences"].append({
                    "quotation": seg["text"], "source": "", "after": "",
                    "note": "this part of the quotation was not found in the passage"})
                continue
            start, end, _ = near
            how = "differs"
            part["differences"].extend(word_differences(p_plain[start:end], seg["text"]))
        placed.append((seg, start, end, how))
        pos = max(pos, end)

    hows = [h for _, _, _, h in placed]
    if all(h == "missing" for h in hows):
        part["verdict"] = "not_in_passage"
    elif "missing" in hows or "differs" in hows or not in_order:
        part["verdict"] = "differs"
    elif "marks_only" in hows:
        part["verdict"] = "marks_only"
    if not in_order:
        part["differences"].append({
            "quotation": "", "source": "", "after": "",
            "note": "the parts of the quotation occur in the passage, but not "
                    "in the order the quotation gives them"})

    spans = [(s, e) for _, s, e, h in placed if h != "missing"]
    if spans:
        a, b = min(s for s, _ in spans), max(e for _, e in spans)
        if b - a <= 3 * len(q_plain) + 200:
            part["source_text"] = (render(p_plain[a:b], p_flags[a:b])
                                   if emphasis_known else p_plain[a:b])

    if emphasis_known and part["verdict"] in ("exact", "marks_only"):
        part["emphasis"] = "same"
        for seg, start, end, _ in placed:
            theirs = p_flags[start:end]
            for i, c in enumerate(seg["text"]):
                if c != " " and seg["flags"][i] != theirs[i]:
                    part["emphasis"] = "differs"
                    break
    return part


def check_row(quoted, evidence):
    """Compare a row's quoted text with its evidence record."""
    if not (quoted or "").strip():
        return {"verdict": "no_quotation", "parts": []}
    if evidence["outcome"] != "found" or not evidence["passage"].strip():
        return {"verdict": "no_passage", "parts": []}
    known = evidence["emphasis_known"]
    p_plain, p_flags = parse(evidence["passage"], known)
    q_plain, q_flags = parse(quoted, known)
    parts = [check_quotation(qp, qf, p_plain, p_flags, known)
             for qp, qf in split_quotations(q_plain, q_flags)]
    worst = max(parts, key=lambda p: VERDICT_ORDER.index(p["verdict"]))
    result = {"verdict": worst["verdict"], "parts": parts}
    if known and any(p["emphasis"] == "differs" for p in parts):
        result["emphasis"] = "differs"
    elif known and all(p["emphasis"] == "same" for p in parts):
        result["emphasis"] = "same"
    else:
        result["emphasis"] = "not_compared"
    return result


# --------------------------------------------------------------------------
# command line


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def run(batch_path):
    try:
        batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
        rows = batch["rows"]
        quotes_file = batch["quotes_file"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("cannot read the batch file %s: %s" % (batch_path, e), file=sys.stderr)
        return 2
    results, failed = [], []
    for row in rows:
        key = row["key"]
        evidence, problems = read_evidence(row["evidence_file"], key)
        if problems:
            failed.append((key, problems))
            results.append({"key": key, "verdict": "no_evidence",
                            "problems": problems, "parts": []})
            continue
        result = check_row(row.get("quoted", ""), evidence)
        result = dict({"key": key, "outcome": evidence["outcome"]}, **result)
        results.append(result)
    write_json(quotes_file, {"batch": batch.get("batch", ""), "rows": results})

    print("%s - %d rows" % (Path(batch_path).name, len(rows)))
    for r in results:
        extra = ""
        if r.get("emphasis") == "differs":
            extra = " (emphasis differs)"
        if r["verdict"] in ("differs", "marks_only"):
            n = sum(len(p["differences"]) for p in r["parts"])
            extra += " (%d difference%s)" % (n, "" if n == 1 else "s")
        print("  %-18s %s%s" % (r["key"], r["verdict"], extra))
    print("  written: %s" % quotes_file)
    if failed:
        print("  %d row(s) without usable evidence:" % len(failed))
        for key, problems in failed:
            print("    %s: %s" % (key, "; ".join(problems)))
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("batch", help="the batch file written by worklist.py batch")
    args = parser.parse_args(argv)
    return run(args.batch)


if __name__ == "__main__":
    sys.exit(main())
