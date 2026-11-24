#!/usr/bin/env python3
"""Offline tests for eurlex's case_law_search.py (answers are made up)."""
import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "eurlex"
SCRIPT = PLUGIN / "skills" / "eurlex" / "scripts" / "case_law_search.py"
spec = importlib.util.spec_from_file_location("case_law_search", SCRIPT)
cls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cls)


def hit(celex="62099CJ0001", ecli="ECLI:EU:C:2099:1", text=None, **content):
    return {
        "content": {"id": celex + "-1", "celex": celex, "ecli": ecli, "idPublished": "C-1/99",
                    "docTypeCode": "ARRET", "docDate": "2099-01-02", **content},
        "highlightFields": {"contentML.en.exact": [
            text or "the <em class='highlight'>abuse of rights</em> claim"]},
        "innerHits": {"procedure": {"searchHits": [
            {"content": {"usualNameML": [{"fr": "Exemple"}, {"en": "Example"}]}}]}},
    }


def answer(*hits, total=None):
    return {"totalHits": len(hits) if total is None else total,
            "totalHitsRelation": "EQUAL_TO", "searchHits": list(hits)}


def run(argv, *answers):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cls, "post", side_effect=list(answers)) as post, \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cls.main(argv)
    return code, out.getvalue(), err.getvalue(), post


class Search(unittest.TestCase):
    def test_version_matches_plugin(self):
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text("utf-8"))
        self.assertEqual(cls.VERSION, manifest["version"])
        self.assertTrue(cls.USER_AGENT.startswith("eurlex-skill/"))

    def test_hit_is_printed(self):
        code, out, _, post = run(['"abuse of rights"'], answer(hit(), total=382))
        self.assertEqual(code, 0)
        self.assertIn("382 hits (texts in EN), page 1 of 20", out)
        self.assertIn("62099CJ0001 | C-1/99 Example | ARRET | 2099-01-02 | ECLI:EU:C:2099:1", out)
        self.assertIn("the abuse of rights claim", out)
        self.assertEqual(post.call_count, 1)

    def test_name_follows_language_then_french(self):
        self.assertEqual(cls.parse(answer(hit()), "FR")[2][0]["name"], "Exemple")
        self.assertEqual(cls.parse(answer(hit()), "SV")[2][0]["name"], "Exemple")

    def test_joined_cases_are_one_hit(self):
        data = answer(hit(), hit(celex="62099CJ0002"), hit(ecli="ECLI:EU:C:2099:9"))
        self.assertEqual(len(cls.parse(data)[2]), 2)

    def test_missing_identifiers_survive(self):
        code, out, _, _ = run(["x"], answer(hit(celex="", ecli=None, id="a"),
                                            hit(celex="", ecli="", id="b")))
        self.assertEqual(code, 0)
        self.assertIn("(no CELEX)", out)
        self.assertIn("(no ECLI)", out)

    def test_snippet(self):
        long = "a" * 900 + " <em class='highlight'>match</em> &amp;\n " + "b" * 900
        s = cls.snippet(hit(text=long))
        self.assertIn("match & b", s)
        self.assertTrue(s.startswith("… ") and s.endswith(" …"))
        self.assertLess(len(s), 700)
        self.assertNotIn("<", s)
        self.assertEqual(cls.snippet({"highlightFields": None}), "")

    def test_filters(self):
        _, _, _, post = run(["x", "--type", "judgment", "--court", "t", "--from", "2020-01-01",
                             "--to", "2021-12-31", "--page", "2", "--newest"], answer(hit()))
        p = post.call_args[0][0]
        self.assertEqual(p["filtersValue"], [
            {"field": "docTypeCode", "values": ["ARRET", "ARRET_NP", "ARRET_DR"]},
            {"field": "affairJurisdictionCode", "values": ["T"]},
            {"field": "docDate", "values": ["2020-01-01", "2021-12-31"]}])
        self.assertEqual(p["pagination"]["pageNumber"], 1)
        self.assertEqual(p["sortTermList"][0]["sortTerm"], "DOC_DATE")


class ZeroAndFailure(unittest.TestCase):
    def test_zero_with_passing_control(self):
        code, out, _, _ = run(["x"], answer(), answer(hit()))
        self.assertEqual(code, 0)
        self.assertIn("0 hits", out)
        self.assertIn("control search passed", out)

    def test_zero_with_failing_control_is_an_error(self):
        code, out, err, _ = run(["x"], answer(), answer())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a negative result", err)

    def test_zero_only_with_filter_is_flagged(self):
        code, out, _, _ = run(["x", "--court", "C"], answer(), answer(hit(), total=7))
        self.assertEqual(code, 0)
        self.assertIn("Without the filters there are 7 hits", out)

    def test_hits_reported_but_not_returned(self):
        self.assertEqual(run(["x"], answer(total=5))[0], 1)

    def test_page_past_the_end_is_fine(self):
        self.assertEqual(run(["x", "--page", "3"], answer(total=5))[0], 0)

    def test_changed_form_is_an_error(self):
        for bad in ({}, [], {"totalHits": "5", "searchHits": []},
                    {"totalHits": 1, "searchHits": [{"document": {}}]}):
            self.assertEqual(run(["x"], bad)[0], 1, bad)

    def test_refusal_is_an_error(self):
        self.assertEqual(run(["x"], cls.SearchError("InfoCuria answered HTTP 403"))[0], 1)

    def test_usage_errors(self):
        for argv in ([" "], ["x", "--size", "51"], ["x", "--page", "0"],
                     ["x", "--language", "NO"], ["x", "--from", "2020"]):
            with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
                cls.arguments(argv)
            self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
