"""`prism`: a gable roof in one part. Built by the harness, not yet in the parts prompt.

Measured in Blender (headless, dsl.tools.compile_calls): size [2, 1, 0.6] ridge x and
[1.2, 3, 0.9] ridge y came out with exactly that box, centred on the location, 2 vertices on top.
"""
import unittest

from maris3d.copilot import compile_plan as CP
from maris3d.copilot import describe_parts as DP
from maris3d.dsl.tools import compile_calls


def roof(axis=None, size=(2.0, 1.0, 0.6)):
    p = {"name": "Roof", "shape": "prism", "size": list(size), "color": "red"}
    if axis:
        p["axis"] = axis
    return p


class Prism(unittest.TestCase):
    def test_not_in_the_prompt_yet(self):
        self.assertNotIn("prism", DP.PARTS_SYSTEM)
        self.assertNotIn("prism", DP.PARTS_SHAPES)
        self.assertIn("prism", DP.NEXT_SHAPES)

    def test_ridge_along_x_by_default(self):
        rp = DP.recipe_part(roof(), [1, 2, 3], "Roof")
        self.assertEqual(rp["rotation_deg"], [0.0, -90.0, 0.0])
        self.assertEqual(rp["dims"], [0.6, 1.0, 2.0])           # own axes: tip, base, ridge
        self.assertAlmostEqual(rp["scale"][1] * DP.PRISM_BOX[1], 1.0, places=4)

    def test_ridge_along_y(self):
        rp = DP.recipe_part(roof("y", (1.2, 3.0, 0.9)), [0, 0, 0], "Roof")
        self.assertEqual(rp["rotation_deg"], [0.0, -90.0, 90.0])
        self.assertEqual(rp["dims"], [0.9, 1.2, 3.0])

    def test_call_and_blender_code(self):
        call = CP.part_call({"origin": [0, 0, 0]}, DP.recipe_part(roof(), [1, 2, 3], "Roof"))
        self.assertEqual((call["shape"], call["location"]), ("prism", [1, 2, 3]))
        code = compile_calls({"calls": [call]})
        self.assertIn("primitive_cylinder_add(", code)
        self.assertIn("vertices=3, radius=1.0, depth=1.0", code)
        self.assertIn("_v.co.x, _v.co.y", code)

    def test_checked_and_placed(self):
        house = [{"name": "Walls", "shape": "cube", "size": [2.0, 1.0, 1.0], "color": "brick"},
                 dict(roof(), place={"on": "Walls", "relation": "on_top_of"})]
        faults, built = DP.check_answer({"object": "house", "parts": house})
        self.assertEqual(faults, [])
        top = {p["name"]: p for p in built}["Roof"]
        self.assertAlmostEqual(top["centre"][2], 1.3, places=3)
        self.assertIn("triangular prism", CP.part_sentence({"origin": [0, 0, 0]},
                                                           DP.recipe_part(roof(), [0, 0, 0], "Roof")))

    def test_axis_words(self):
        for axis, ok in (("x", True), ("y", True), ("z", False)):
            faults, _ = DP.check_answer({"parts": [roof(axis)]})
            self.assertEqual(not any("axis" in f for f in faults), ok, axis)
        faults, _ = DP.check_answer({"parts": [dict(roof(), hollow="open_top")]})
        self.assertTrue(any("hollow" in f for f in faults))


if __name__ == "__main__":
    unittest.main()
