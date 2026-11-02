#!/usr/bin/env python3
"""Tests for reading a UNTS record (showDetails.aspx) and finding it by
registration number.

No network: the fixture follows the markup of the live records for the
CRPD (No. 44910) and No. 52110 (2026-11-02), cut to the rows the parser
reads.

Run with `python tests/untc/test_record.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc" / "scripts"))

import untc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


def row(label, value):
    return ('<tr> <th> <span id="lbl"><b>%s</b></span> </th> <td> %s </td> </tr>\n' % (label, value))


def record(authentic, fmt, docs, actions=""):
    langs = "".join("<tr><td>%s</td></tr>" % a for a in authentic)
    links = " ".join('<a href="%s">%s</a>' % (d, d.rsplit("/", 1)[-1]) for d in docs)
    return ("<html><body><table>\n"
            + row("Registration Number", "44910")
            + row("Title", "Convention on the Rights of Persons with Disabilities")
            + row("Participant(s)", "")
            + row("Places/dates of conclusion", "New York 13/12/2006")
            + row("EIF information", "3 May 2008")
            + row("Authentic texts", "<table>%s</table>" % langs)
            + row("Attachments", "<div> with annex </div>")
            + row("Depositary", "Secretary-General of the United Nations")
            + row("Registration Date", "ex officio 3 May 2008")
            + row("Subject terms", "Human rights")
            + row("Agreement type", "Multilateral")
            + row("UNTS Volume Number", "2515 (p.3)")
            + row("Publication format", fmt)
            + row("Certificate Of Registration", "")
            + row("Text&nbsp;document(s)", links)
            + row("Volume In PDF", '<a href="/doc/Publication/UNTS/Volume%202515/v2515.pdf">v2515.pdf</a>')
            + row("Map(s)", "")
            + row("Corrigendum/Addendum/Note", "")
            + "</table>\n" + actions + "</body></html>")


ACTIONS = ('<table class="table" id="dgActions" width="98%">\n'
           '<tr class="thead-one"><th scope="col">Participant</th><th scope="col">Action</th>'
           '<th scope="col">Date of Notification/Deposit</th><th scope="col">Date of Effect</th></tr>'
           '<tr><td><a href="/Pages/showActionDetails.aspx?objid=0800000280005fef">Afghanistan</a></td>'
           '<td>Accession</td><td>18/09/2012</td><td>18/10/2012</td></tr>'
           '<tr><td><a href="#">Albania</a></td><td>Signature</td><td>22/12/2009</td><td>&nbsp;</td></tr>'
           '</table>')


class FakeOpener:
    def __init__(self, page):
        self.page = page

    def open(self, url, timeout=None):
        page = self.page

        class R:
            def read(self):
                return page.encode("utf-8")
        return R()


def details(page, **kw):
    untc._unts_state["opener"] = FakeOpener(page)
    try:
        return untc.unts_details("080000028017bf87", **kw)
    finally:
        untc._unts_state["opener"] = None


print("CRPD record")
d = details(record(["Spanish", "Russian", "French", "English", "Chinese", "Arabic"], "Full",
                   ["/doc/Publication/UNTS/No%20Volume/44910/Part/I-44910-080000028017bf87.pdf"],
                   ACTIONS))
check("authentic texts (a nested table)", d["authentic_texts"],
      ["Spanish", "Russian", "French", "English", "Chinese", "Arabic"])
check("publication format", d["publication_format"], "Full")
check("text documents", d["text_documents"],
      ["https://treaties.un.org/doc/Publication/UNTS/No%20Volume/44910/Part/I-44910-080000028017bf87.pdf"])
check("volume and page", (d["unts_volume"], d["unts_page"]), (2515, 3))
check("participants counted, not listed", ("participants" in d, d["participants_count"]), (False, 2))
d = details(record(["English"], "Full", [], ACTIONS), participants=True)
check("participants on request", d["participants"], [
    {"participant": "Afghanistan", "action": "Accession", "date": "18/09/2012", "effect": "18/10/2012"},
    {"participant": "Albania", "action": "Signature", "date": "22/12/2009", "effect": None}])
check("... with the caveat", d["participants_caveat"], untc.PARTICIPANTS_CAVEAT)

print("No. 52110 record (limited publication)")
d = details(record(["English"], "Limited Publication",
                   ["/doc/Publication/UNTS/Volume%203000/Part/volume-3000-I-52110.pdf"]))
check("publication format", d["publication_format"], "Limited Publication")
check("no actions table", d["participants_count"], 0)

print("record lookup never raises")
saved = untc.unts_find_reg
try:
    def boom(reg, **kw):
        raise OSError("connection reset")
    untc.unts_find_reg = boom
    check("network error", untc.unts_record(2515, "44910").get("error", "")[:26], "UNTS record not reachable ")
    untc.unts_find_reg = lambda reg, **kw: [{"reg": "A-44910", "title": "Optional Protocol", "objid": "x",
                                             "registered": "", "type": "", "concluded": "", "volume": ""}]
    check("no record for the number", untc.unts_record(2515, "44910"),
          {"error": "no UNTS record registered as I-44910"})
finally:
    untc.unts_find_reg = saved

print()
if failures:
    print("%d failure(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all ok")
