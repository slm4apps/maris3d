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

    def test_real_current_json_scores_are_consistent(self):
        self.assertEqual(R.gate_score(self.cur).status, "ok")

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
            with open(os.path.join(d, self.cur["current"]["artifacts"]["gguf-edit-q8_0"]["file"]), "wb") as f:
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
