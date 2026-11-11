#!/usr/bin/env python3
"""Tests for worklist.py batch and apply: the steps that run with workers.

Builds a small worklist, plays the retrieval worker (evidence files) and the
judging worker (results file) by hand, and checks what `apply` accepts,
what it refuses, and what it writes.

Run with `python tests/kildesjekk/test_apply.py`.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "kildesjekk" / "skills" / "kildesjekk" / "scripts"))

try:
    from openpyxl import Workbook, load_workbook
except ImportError:
    sys.exit("these tests need openpyxl: pip install openpyxl")

import quote_check  # noqa: E402
import worklist  # noqa: E402

HEADERS = ["footnote no./location in text", "checked", "reference",
           "quoted text", "discrepancy", "type of discrepancy", "severity",
           "description", "link/reference to the source you have consulted"]

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


def quiet(fn, *args, **kwargs):
    """Run a command; return (exit status, what it printed)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            status = fn(*args, **kwargs)
        except SystemExit as e:
            status = e.code
    return status, out.getvalue()


ROWS = [
    ["1", "no", "Lotus, p. 18", '"jurisdiction is certainly territorial"'],
    ["2a", "no", "Ryngaert (2015) p. 49", ""],
    ["2b", "no", "Mann (1964) p. 30", ""],
    ["text p. 3a", "no", "Akehurst (1973) p. 152", '"a genuine link"'],
]
CLAIMS = [{"key": r[0], "claim": "The sentence that note %s supports." % r[0],
           "full_reference": r[2]} for r in ROWS]
PASSAGE = "In this sense jurisdiction is certainly territorial; it cannot be exercised abroad."


def new_job(tmp, name):
    """A fresh worklist with its claims file, in its own directory."""
    base = Path(tmp) / name
    base.mkdir()
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for r in ROWS:
        sheet.append(r + [""] * (len(HEADERS) - len(r)))
    meta = book.create_sheet("Metadata")
    for key, value in [("Document name", "Art.docx"), ("Date of source check", "2026-11-11"),
                       ("Total references identified", 4), ("Footnote references", 3),
                       ("Main-text references", 1)]:
        meta.append([key, value])
    path = base / "Kildesjekk_Art.xlsx"
    book.save(path)
    claims = base / "kildesjekk_claims.json"
    claims.write_text(json.dumps(CLAIMS), encoding="utf-8")
    return path, claims


def evidence(row, outcome, passage="", **fields):
    """Play the retrieval worker for one row."""
    lines = ["key: %s" % row["key"], "outcome: %s" % outcome]
    values = {"source": "Zotero ABCD1234", "route": "zoteus", "locator": "p. 18",
              "pinpoint_matches": "yes", "emphasis_known": "no",
              "tools_tried": "zotero_search_items by author and title", "note": ""}
    values.update(fields)
    lines += ["%s: %s" % kv for kv in values.items()]
    if outcome == "found":
        lines += [quote_check.PASSAGE_MARK, passage]
    Path(row["evidence_file"]).write_text("\n".join(lines) + "\n", encoding="utf-8")


def cells(path, key):
    sheet = load_workbook(path).worksheets[0]
    for r in range(2, sheet.max_row + 1):
        if sheet.cell(row=r, column=1).value == key:
            return ([sheet.cell(row=r, column=c).value for c in range(1, 10)],
                    {sheet.cell(row=r, column=c).fill.start_color.rgb[-6:]
                     for c in range(1, 10) if sheet.cell(row=r, column=c).fill.fill_type})
    return None, None


def result(key, checked, discrepancy="", type_="", severity="", description="",
           source=""):
    return {"key": key, "checked": checked, "discrepancy": discrepancy,
            "type": type_, "severity": severity, "description": description,
            "source": source}


with tempfile.TemporaryDirectory() as tmp:
    print("batch")
    path, claims = new_job(tmp, "a")
    keys = [r[0] for r in ROWS]
    status, out = quiet(worklist.main, ["batch", str(path), "--claims", str(claims),
                                        "--name", "zotero-01", "--keys"] + keys)
    check("a batch is written", status, 0)
    batch_file = path.parent / "kildesjekk_batches" / "zotero-01.json"
    batch = json.loads(batch_file.read_text(encoding="utf-8"))
    check("with a row per key, in order", [r["key"] for r in batch["rows"]], keys)
    check("the quotation comes from the worklist", batch["rows"][0]["quoted"], ROWS[0][3])
    check("the claim comes from the claims file", batch["rows"][1]["claim"],
          "The sentence that note 2a supports.")
    check("each row has its own evidence file",
          len({r["evidence_file"] for r in batch["rows"]}), 4)
    check("the evidence directory exists", Path(batch["rows"][0]["evidence_file"]).parent.is_dir(), True)

    status, out = quiet(worklist.main, ["batch", str(path), "--claims", str(claims),
                                        "--name", "zotero-01", "--keys", "1"])
    check("an existing batch name is refused", (status, "exists already" in out), (1, True))
    status, out = quiet(worklist.main, ["batch", str(path), "--claims", str(claims),
                                        "--name", "x", "--keys", "1", "99"])
    check("an unknown key is refused", (status, "'99' matches 0 rows" in out), (1, True))
    check("and nothing is written", (path.parent / "kildesjekk_batches" / "x.json").exists(), False)
    claims.write_text(json.dumps(CLAIMS[1:]), encoding="utf-8")
    status, out = quiet(worklist.main, ["batch", str(path), "--claims", str(claims),
                                        "--name", "y", "--keys", "1"])
    check("a row without a claim is refused", (status, "no claim for '1'" in out), (1, True))

    print("apply: a good batch")
    rows = {r["key"]: r for r in batch["rows"]}
    evidence(rows["1"], "found", PASSAGE)
    evidence(rows["2a"], "found", "Some text about territoriality.", locator="p. 51",
             pinpoint_matches="no")
    evidence(rows["2b"], "not_here")
    evidence(rows["text p. 3a"], "unavailable")
    check("the quotation check runs", quiet(quote_check.main, [str(batch_file)])[0], 0)
    good = {"rows": [
        result("1", "yes", "no", source="Zotero ABCD1234, p. 18"),
        result("2a", "yes", "yes", "Wrong page/section/paragraph", "low",
               "The passage is at p. 51, not p. 49.", "Zotero EFGH5678, p. 51"),
        result("2b", "no"),
        result("text p. 3a", "source unavailable",
               description="In Zotero without a PDF; searched by author and title."),
    ]}
    results_file = Path(batch["results_file"])
    results_file.parent.mkdir(parents=True, exist_ok=True)
    results_file.write_text(json.dumps(good), encoding="utf-8")
    before = path.read_bytes()
    status, out = quiet(worklist.main, ["apply", str(path), str(batch_file)])
    check("it is applied and the worklist validates", status, 0)
    values, fills = cells(path, "1")
    check("a clean row is written green", (values[1], values[4], fills), ("yes", "no", {"C6EFCE"}))
    values, fills = cells(path, "2a")
    check("a finding gets its colour", (values[5], values[6], fills),
          ("Wrong page/section/paragraph", "low", {"FFEB9C"}))
    values, fills = cells(path, "2b")
    check("a row left for a later step is untouched", (values[1], fills), ("no", set()))
    values, fills = cells(path, "text p. 3a")
    check("an unavailable row is grey with empty verdict columns",
          (values[1], values[4], values[5], values[6], fills),
          ("source unavailable", None, None, None, {"E5E5E5"}))
    check("the reference and quotation are not touched", cells(path, "1")[0][2:4], ROWS[0][2:4])
    status, out = quiet(worklist.main, ["apply", str(path), str(batch_file)])
    check("applying twice is refused", (status, "already" in out), (1, True))
    status, out = quiet(worklist.main, ["apply", str(path), str(batch_file), "--recheck"])
    check("unless --recheck is given", status, 0)

    print("apply: refusals")

    def refused(name, change, expect, prepare=None):
        """Apply a changed copy of the good results to a fresh job."""
        job = Path(tmp) / ("r%d" % len(list(Path(tmp).iterdir())))
        shutil.copytree(path.parent, job)
        wl = job / path.name
        wl.write_bytes(before)
        b = json.loads(batch_file.read_text(encoding="utf-8"))
        for r in b["rows"]:
            r["evidence_file"] = str(job / "kildesjekk_evidence" / Path(r["evidence_file"]).name)
        b["quotes_file"] = str(job / "kildesjekk_quotes" / "zotero-01.json")
        b["results_file"] = str(job / "kildesjekk_results" / "zotero-01.json")
        bf = job / "kildesjekk_batches" / "zotero-01.json"
        bf.write_text(json.dumps(b), encoding="utf-8")
        data = json.loads(json.dumps(good))
        change(data["rows"])
        Path(b["results_file"]).write_text(json.dumps(data), encoding="utf-8")
        if prepare:
            prepare(b)
        status, out = quiet(worklist.main, ["apply", str(wl), str(bf)])
        check(name, (status, expect in out), (1, True))
        if expect not in out:
            print(out)
        check("  and the worklist is unchanged", wl.read_bytes() == before, True)

    refused("a missing row", lambda rows: rows.pop(), "no row for 'text p. 3a'")
    refused("a row that is not in the batch",
            lambda rows: rows.append(result("7", "yes", "no", source="Zotero X")),
            "not in the batch")
    refused("a key given twice", lambda rows: rows.append(dict(rows[0])), "2 times")
    refused("checked = yes without a source read",
            lambda rows: rows.__setitem__(2, result("2b", "yes", "no", source="Zotero Y")),
            "the evidence outcome is 'not_here'")
    refused("unavailable for a source that was read",
            lambda rows: rows.__setitem__(0, result("1", "source unavailable", description="x")),
            "the evidence outcome is 'found'")
    refused("a finding without a severity",
            lambda rows: rows[1].update(severity=""), "severity = ''")
    refused("a verdict on an unavailable row",
            lambda rows: rows[3].update(discrepancy="no"), "it must be empty")
    refused("a checked row without the source consulted",
            lambda rows: rows[0].update(source=""), "no link/reference")
    refused("a row left for later with a verdict",
            lambda rows: rows[2].update(description="x"), "the other fields must be empty")
    refused("a status that is not permitted",
            lambda rows: rows[0].update(checked="done"), "checked = 'done'")

    def tamper(b):
        evidence(b["rows"][0], "found", PASSAGE.replace("certainly", "clearly"))
        quiet(quote_check.main, [str(Path(b["results_file"]).parents[1]
                                     / "kildesjekk_batches" / "zotero-01.json")])

    refused("a quotation difference passed over in silence", lambda rows: None,
            "the quotation check says 'differs'", prepare=tamper)

print()
if failures:
    print("%d failing check(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all checks passed")
