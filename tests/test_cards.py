# SPDX-License-Identifier: Apache-2.0
import os, re, subprocess, sys, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src")]


class Docs(unittest.TestCase):
    def test_dsl_doc_is_generated_from_code(self):
        import gen_dsl_doc as D
        self.assertEqual(open(os.path.join(ROOT, "docs", "DSL.md")).read(), D.render())


    def test_every_required_file_exists(self):
        need = ["README.md", "LICENSE", "LICENSES/README.md", "NOTICE", "hf/Maris3D-Blender/README.md", "TECHNICAL-REPORT.md", "CITATION.cff",
                "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "ROADMAP.md", "release/CURRENT.json", "release/HISTORY.md", "release/STATUS.md",
                ".github/workflows/ci.yml", ".gitignore", ".gitattributes", "pyproject.toml"] + ["docs/" + n for n in (
                "USAGE.md", "PROMPT-FORMAT.md", "DSL.md", "EVALUATION.md", "DATA-CARD.md", "SAFETY-AND-LIMITATIONS.md", "FAQ.md", "LICENSING.md")]
        for n in need:
            self.assertTrue(os.path.exists(os.path.join(ROOT, n)), n)

    def test_readme_states_the_distribution_route(self):
        r = open(os.path.join(ROOT, "README.md")).read()
        self.assertIn("the Hugging Face organisation `slm4apps`", r)
