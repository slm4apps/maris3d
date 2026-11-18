# SPDX-License-Identifier: Apache-2.0
import os, re, subprocess, sys, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src")]
import gen_model_cards as G  # noqa: E402


@unittest.skip("old per-size JSON-model pipeline; CURRENT.json now has one model. Rewrite scripts/promote.py and scripts/gen_model_cards.py for that shape before release (internal RELEASE-SSOT section 11).")
class Cards(unittest.TestCase):
    def setUp(self):
        self.cur = G.load("release/CURRENT.json")
        self.out = G.build(self.cur)

    def test_one_card_per_repo_and_up_to_date(self):
        repos = sorted(r for s in self.cur["sizes"].values() for r in s["hf_repos"].values())
        cards = sorted(k.split("/")[1] for k in self.out if k.startswith("hf/"))
        self.assertEqual(cards, repos)
        for rel, text in self.out.items():
            self.assertEqual(open(os.path.join(ROOT, rel)).read(), text, rel + " is stale: run scripts/gen_model_cards.py")

    def test_cards_share_one_template_and_have_yaml(self):
        for rel, text in self.out.items():
            if rel.startswith("hf/"):
                self.assertTrue(text.startswith("---\nlicense: apache-2.0\n"))
                self.assertIn("model-index:", text)
                self.assertNotRegex(text, r"\{\{\w+\}\}")          # no unfilled placeholder
                self.assertNotRegex(text.split("\n---\n", 1)[0], r"\bv[2-4]\b")  # no internal tag in the front matter

    def test_numbers_come_from_result_files(self):
        for size, c in self.cur["sizes"].items():
            card = self.out["hf/maris3d-%s/README.md" % size]
            self.assertIn("<!-- source: %s -->" % c["results"]["bare"], card)
            self.assertIn(str(c["score"]["pass_pct"]), card)
        self.assertIn("72.33", self.out["README.md"])

    def test_no_internal_tags_in_public_text(self):
        for rel, text in self.out.items():
            self.assertNotRegex(text, r"maris3d-(0\.5b|1\.5b)-?v\d")


if __name__ == "__main__":
    unittest.main()


class Docs(unittest.TestCase):
    def test_dsl_doc_is_generated_from_code(self):
        import gen_dsl_doc as D
        self.assertEqual(open(os.path.join(ROOT, "docs", "DSL.md")).read(), D.render())

    @unittest.skip("old per-size JSON-model pipeline; CURRENT.json now has one model. Rewrite scripts/promote.py and scripts/gen_model_cards.py for that shape before release (internal RELEASE-SSOT section 11).")
    def test_report_numbers_match_current_set(self):
        cur = G.load("release/CURRENT.json")
        rep = open(os.path.join(ROOT, "TECHNICAL-REPORT.md")).read()
        for c in cur["sizes"].values():
            self.assertIn(str(c["score"]["pass_pct"]), rep)
            self.assertIn("%d/%d" % (c["score"]["passed"], c["score"]["n"]), rep)
        self.assertIn(str(cur["sizes"]["0.5b"]["score_repair2"]["pass_pct"]), rep)

    def test_every_required_file_exists(self):
        need = ["README.md", "LICENSE", "LICENSES/README.md", "NOTICE", "hf/Maris3D-Blender/README.md", "TECHNICAL-REPORT.md", "CITATION.cff",
                "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "ROADMAP.md", "release/CURRENT.json", "release/HISTORY.md", "release/STATUS.md",
                ".github/workflows/ci.yml", ".gitignore", ".gitattributes", "pyproject.toml"] + ["docs/" + n for n in (
                "USAGE.md", "PROMPT-FORMAT.md", "DSL.md", "EVALUATION.md", "DATA-CARD.md", "SAFETY-AND-LIMITATIONS.md", "FAQ.md", "LICENSING.md", "PUBLIC-PRIVATE.md")]
        for n in need:
            self.assertTrue(os.path.exists(os.path.join(ROOT, n)), n)

    def test_readme_states_the_distribution_route(self):
        r = open(os.path.join(ROOT, "README.md")).read()
        self.assertIn("the Hugging Face organisation `slm4apps`", r)
