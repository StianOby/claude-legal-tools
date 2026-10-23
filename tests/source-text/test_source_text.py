#!/usr/bin/env python3
"""Tests for shared/source-text/source_text.py: emphasis markers,
superscripts, list numbers, search folding.
Run: python tests/source-text/test_source_text.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "source-text"))
import source_text as st  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def html(s):
    return st.finish(st.mark_emphasis(s))


print("emphasis")
check("italic", html("endossere vekslen <i>in blanco</i> eller"), "endossere vekslen *in blanco* eller")
check("bold", html("<strong>§ 1.</strong> Formål"), "**§ 1.** Formål")
check("both", html("<b><i>Holship</i></b>"), "***Holship***")
check("nested part", html("<i>see <b>Holship</b>, para 90</i>"), "*see **Holship**, para 90*")
check("inner ends first", html("<b><i>a</i> b</b>"), "***a* b**")
check("spaced runs merge", html("<i>a</i> <i>b</i>"), "*a b*")
check("spaces go outside", html("a<i> b </i>c"), "a *b* c")
check("empty emphasis dropped", html("a<i> </i>b<b></b>c"), "a bc")
check("adjacent runs merge", html("<i>Grendse</i><i>-Tractat</i>"), "*Grendse-Tractat*")
check("word with a suffix", html("<i>Holship</i>-saken"), "*Holship*-saken")
check("never spans a line", html("<i>first\nsecond</i>"), "*first*\n*second*")
check("attributes", html('<em class="x">y</em>'), "*y*")
check("unbalanced close ignored", html("a</i> b"), "a b")
check("plain() drops markers", st.plain(st.mark_emphasis("<b>Title</b>")), "Title")
check("no markers: unchanged", st.finish("a * b"), "a * b")

print("superscript")
check("digit", st.superscript("2"), "²")
check("signs", st.superscript("-1"), "⁻¹")
check("letters", st.superscript("er"), "^er^")
check("TM", st.superscript("TM"), "^TM^")
check("empty", st.superscript(""), "")

print("lists")
check("decimal", st.list_label(3, "1"), "3")
check("alpha", st.list_label(28, "a"), "ab")
check("roman", st.list_label(14, "I"), "XIV")
check("type attr", st.ol_kind(' type="i" class="x"'), "i")
check("css", st.ol_kind(' style="list-style-type: upper-alpha"'), "A")
check("default", st.ol_kind(""), "1")
check("start", st.ol_start(' start="4"'), 4)
check("value", st.li_value(' value="7"'), 7)

print("spaces, fold")
check("nbsp", "Art.\xa020 § 3".translate(st.SPACES), "Art. 20 § 3")
check("fold", st.fold("*in blanco* helse\xadundersøkelse"), "in blanco helseundersøkelse")

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
