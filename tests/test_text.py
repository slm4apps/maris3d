# SPDX-License-Identifier: Apache-2.0
"""The keyed text file: every key the code asks for exists, none is left unused, English is the
fallback, and the files already moved to keys say nothing to people as a literal."""
import ast, json, os, re, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from maris3d import text as T  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "maris3d"
USE = re.compile(r"""\bt\(\s*["']([a-z0-9_.]+)["']""")
# files moved to keys so far (the translation goes file by file)
KEYED = ("copilot/loop.py", "cli.py")


def used_keys():
    out = set()
    for path in SRC.rglob("*.py"):
        out.update(USE.findall(path.read_text(encoding="utf-8")))
    return out


def _shown_literals(node):
    """Strings in an expression that would reach a person as they are: not a key in t(...), not
    one side of a comparison, not a bare separator."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t":
        return []
    if isinstance(node, ast.Compare):
        return []
    if isinstance(node, ast.Subscript):                       # a["op"]: a key, not text
        return _shown_literals(node.value)
    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get":
        return _shown_literals(node.func.value)
    if isinstance(node, ast.JoinedStr):
        return [ast.unparse(node)]
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) and node.value.strip(", ;") else []
    return [x for child in ast.iter_child_nodes(node) for x in _shown_literals(child)]


class TextFile(unittest.TestCase):
    def test_every_used_key_exists(self):
        self.assertEqual(used_keys() - T.keys(), set())

    def test_no_key_is_unused(self):
        self.assertEqual(T.keys() - used_keys(), set())

    def test_the_file_is_sorted_json_with_string_values(self):
        raw = (SRC / "text" / "en.json").read_text(encoding="utf-8")
        table = json.loads(raw)
        self.assertEqual(list(table), sorted(table))
        self.assertTrue(all(isinstance(v, str) and v for v in table.values()))

    def test_values_fill_in_and_missing_keys_show_as_themselves(self):
        self.assertEqual(T.t("say.code.built", items=3, parts=12), "built 3 things, 12 parts")
        self.assertEqual(T.t("no.such.key"), "no.such.key")

    def test_an_unknown_language_falls_back_to_english(self):
        before = T.language()
        try:
            T.set_language("xx")
            self.assertEqual(T.t("speaker.router"), "Router")
        finally:
            T.set_language(before)
        self.assertEqual(T.languages()[0], "en")

    def test_keyed_files_have_no_literal_say(self):
        for rel in KEYED:
            tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) \
                        in ("_say", "_say_moved", "_ask_yes", "print"):
                    for arg in node.args:
                        self.assertEqual(_shown_literals(arg), [], f"{rel}:{node.lineno} says a literal")

    def test_the_addon_carries_the_text(self):
        from maris3d import addonbuild
        with tempfile.TemporaryDirectory() as tmp:
            ext = Path(addonbuild.assemble(tmp))
            self.assertTrue((ext / "vendor" / "text.py").exists())
            self.assertTrue((ext / "vendor" / "data" / "text" / "en.json").exists())
            self.assertIn("from .text import t", (ext / "vendor" / "loop.py").read_text(encoding="utf-8"))
            sys.path.insert(0, str(ext / "vendor"))
            try:
                import importlib
                vt = importlib.import_module("text")
                self.assertEqual(vt.t("speaker.router"), "Router")
            finally:
                sys.path.remove(str(ext / "vendor"))
                sys.modules.pop("text", None)


if __name__ == "__main__":
    unittest.main()
