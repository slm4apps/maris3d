# SPDX-License-Identifier: Apache-2.0
import copy
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src")]
import release_check as R  # noqa: E402


class Gates(unittest.TestCase):
    def setUp(self):
        self.cur = R.load()

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "internal", "release", "bench-external", "out", "assist-route", "summary.json")),
                         "maintainer run summary (internal/) not in this tree")
    def test_score_gate_compares_the_product_figure_with_the_one_run(self):
        """The product number is one 180-row run (assist-route), not the per-row oracle."""
        one_run = os.path.join(ROOT, "internal", "release", "bench-external", "out", "assist-route", "summary.json")
        self.assertTrue(os.path.exists(one_run), "the one-run product summary is missing")
        ok = copy.deepcopy(self.cur)
        ok["current"]["score_routed"] = {"pass": 51, "partial": 109, "fail": 20, "n": 180,
                                         "pass_pct": 28.3, "usable_pct": 88.9}
        self.assertEqual(R.gate_score(ok).status, "ok")
        bad = copy.deepcopy(ok)
        bad["current"]["score_routed"] = {"pass": 49, "partial": 87, "fail": 44, "n": 180,
                                          "pass_pct": 27.2, "usable_pct": 75.6}
        self.assertEqual(R.gate_score(bad).status, "fail")
        self.assertIn("assist-route", R.gate_score(bad).detail)

    def test_score_gate_catches_wrong_numbers(self):
        bad = copy.deepcopy(self.cur)
        bad["current"]["score"]["pass_pct"] = 50.0
        self.assertEqual(R.gate_score(bad).status, "fail")
        bad = copy.deepcopy(self.cur)
        bad["current"]["score"]["fail"] += 1
        self.assertEqual(R.gate_score(bad).status, "fail")

    def test_tools_manifest(self):
        self.assertEqual(R.gate_tools().status, "ok")

    def test_artifact_pending_without_file_and_fail_on_wrong_size(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(R.gate_artifact(self.cur, d).status, "pending")
            with open(os.path.join(d, self.cur["current"]["artifacts"]["gguf-q8_0"]["file"]), "wb") as f:
                f.write(b"short")
            self.assertEqual(R.gate_artifact(self.cur, d).status, "fail")

    def test_open_decisions_are_pending_not_fail(self):
        # the real file has every decision made (org, repo, adapter)
        self.assertEqual(R.gate_open_decisions(self.cur).status, "ok")
        bad = copy.deepcopy(self.cur)
        bad["hf_org"] = "TBD"
        bad["current"]["public_name"] = "TBD"
        g = R.gate_open_decisions(bad)
        self.assertEqual(g.status, "pending")
        self.assertIn("public name", g.detail)


if __name__ == "__main__":
    unittest.main()
