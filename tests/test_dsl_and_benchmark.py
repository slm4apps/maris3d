# SPDX-License-Identifier: Apache-2.0
"""Offline tests: the DSL compiler, the checks and the benchmark files. No Blender, no model."""
import ast, json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "eval", "maris3d_eval"))
from maris3d.dsl import tools as T            # noqa: E402
from maris3d.engine.checks import check       # noqa: E402
from prompts import P                              # noqa: E402
from tool_refs import R                            # noqa: E402


class Dsl(unittest.TestCase):
    def test_schema_has_unique_tools(self):
        names = [t["properties"]["tool"]["const"] for t in T.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(T.SCHEMA["properties"]["calls"]["maxItems"], 40)

    def test_short_system_prompt_is_the_trained_one(self):
        self.assertEqual(T.SHORT, 'Output Blender tool calls as JSON: {"calls":[...]}.')

    def test_compile_cube(self):
        code = T.compile_calls({"calls": [{"tool": "add_primitive", "shape": "cube"}]})
        self.assertIn("import bpy", code)
        ast.parse(code)

    def test_clone_object_copies_the_subtree_not_just_the_root(self):
        code = T.compile_calls({"calls": [{
            "tool": "clone_object", "object": "House", "location": [0, 12, 0],
            "count": 3, "rotation_deg": [0, 0, 90], "name": "House"}]})
        ast.parse(code)
        # the whole item must come along, and the copies must keep their parenting
        self.assertIn("children_recursive", code)
        self.assertIn("_map.get(_t.parent", code)
        # inherited matrix_parent_inverse encodes the old root, so it must be recomputed
        self.assertIn("matrix_parent_inverse.identity()", code)
        self.assertIn("math.radians", code)

    def test_every_reference_compiles_to_valid_python(self):
        for pid, calls in R.items():
            with self.subTest(pid=pid):
                ast.parse(T.compile_calls({"calls": calls}))


class Benchmark(unittest.TestCase):
    def test_206_prompts_four_levels(self):
        self.assertEqual(len(P), 206)
        self.assertEqual(sorted({p["level"] for p in P}), [1, 2, 3, 4])
        self.assertEqual(len({p["id"] for p in P}), 206)

    def test_exported_jsonl_matches_the_python_prompts(self):
        path = os.path.join(HERE, "..", "eval", "benchmark", "prompts.jsonl")
        rows = [json.loads(l) for l in open(path)]
        self.assertEqual([r["id"] for r in rows], [p["id"] for p in P])
        self.assertEqual([r["prompt"] for r in rows], [p["prompt"] for p in P])


class Checks(unittest.TestCase):
    SCENE = {"executed": True, "objects": [{"type": "MESH", "verts": 8, "modifiers": [], "materials": [], "parent": None}],
             "animated": 0}

    def test_pass_and_fail(self):
        self.assertEqual(check(self.SCENE, {"meshes": (1, 1)}), [])
        self.assertTrue(check(self.SCENE, {"meshes": (2, 2)}))

    def test_not_executed(self):
        self.assertEqual(check({"executed": False, "objects": []}, {"meshes": (1, 1)}), ["script did not execute"])


if __name__ == "__main__":
    unittest.main()
