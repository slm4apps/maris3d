# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the confirmation sentence builder (python3 -m unittest discover -s tests)."""
import unittest
from maris3d.mcp import confirm as C

CUBE = {"name": "Cube", "type": "MESH", "loc": [0, 0, 0], "scale": [1, 1, 1], "color": [0.8, 0.8, 0.8]}
OK = [{"i": 1, "tool": "add_primitive", "ok": True}]


class Confirmation(unittest.TestCase):
    def test_add(self):
        t = C.confirmation("X", [], [CUBE], calls=[{"tool": "add_primitive"}], per_call=OK, check={"passed": True, "fails": []})
        self.assertEqual(t, "Done: added a cube at the origin; check passed.")

    def test_add_many(self):
        walls = [{"name": f"Wall.{i:03d}", "type": "MESH", "loc": [i, 0, 0]} for i in range(4)] + [{"name": "Roof", "type": "MESH", "loc": [0, 0, 3]}]
        t = C.confirmation("X", [], walls, calls=[{}] * 5, per_call=OK * 5, check={"passed": True, "fails": []})
        self.assertEqual(t, "Built 5 objects (4 walls, a roof); check passed.")

    def test_move(self):
        moved = dict(CUBE, loc=[-2, 0, 0])
        t = C.confirmation("X", [CUBE], [moved], calls=[{"tool": "set_transform"}], per_call=OK, check={"passed": True, "fails": []})
        self.assertEqual(t, "Moved the cube 2.0 units left; nothing else changed; check passed.")

    def test_recolour(self):
        red = dict(CUBE, color=[0.85, 0.05, 0.05])
        t = C.confirmation("X", [CUBE], [red], calls=[{"tool": "set_material"}], per_call=OK, check={"passed": True, "fails": []})
        self.assertEqual(t, "Changed the cube colour to red; nothing else changed; check passed.")

    def test_failed_check_and_invalid_call(self):
        bad = [{"i": 1, "tool": "add_door", "ok": False, "error": "compile: KeyError"}]
        t = C.confirmation("X", [], [], calls=[{"tool": "add_door"}], per_call=bad, check={"passed": False, "fails": ["meshes 0 not in (1, 60)"]}, tries=3,
                           earlier_fails=["meshes 0 not in (1, 60)"])
        self.assertTrue(t.startswith("I could not build it: the output had an invalid call to add_door."), t)
        self.assertIn("I tried 3 times", t)
        self.assertNotIn("Done", t)
        t2 = C.confirmation("X", [], [CUBE], calls=[{"tool": "add_primitive"}], per_call=OK, check={"passed": False, "fails": ["material 0 < 1"]})
        self.assertTrue(t2.startswith("I could not build it: the check failed: material 0 < 1."), t2)
        self.assertIn("does not meet the request", t2)

    def test_no_change(self):
        t = C.confirmation("X", [CUBE], [dict(CUBE)], calls=[{"tool": "set_transform"}], per_call=OK, check={"passed": True, "fails": []})
        self.assertTrue(t.startswith("Nothing changed in the scene"), t)
        t2 = C.confirmation("X", [], [], calls=[], per_call=[], check={"passed": False, "fails": ["x"]})
        self.assertTrue(t2.startswith("I could not build it: the model returned no usable tool calls."), t2)

    def test_generic_check_is_not_called_a_pass_for_the_shape(self):
        t = C.confirmation("X", [], [CUBE], calls=[{"tool": "add_primitive"}], per_call=OK, check={"passed": True, "fails": [], "generic": True})
        self.assertIn("basic check passed", t)

    def test_no_code_in_answer(self):
        t = C.with_screenshot("Done.", "/a/b.png")
        self.assertTrue(t.endswith("Screenshot: /a/b.png ![Blender scene](/a/b.png)"))
        self.assertNotIn("```", t)


if __name__ == "__main__":
    unittest.main()
