"""Colour words -> material: every word builds, the old 26 keep their materials."""
import unittest

from maris3d.copilot import colours as C
from maris3d.copilot import describe_parts as DP
from maris3d.dsl import tools as T


class Names(unittest.TestCase):
    def test_old_colours_first_and_unchanged(self):
        self.assertEqual(C.COLOUR_NAMES[:len(DP.PARTS_COLORS)], DP.PARTS_COLORS)
        for name, mat in DP.PARTS_MATERIALS.items():
            self.assertEqual(C.material(name), mat)

    def test_every_name_builds(self):
        self.assertGreaterEqual(len(C.COLOUR_NAMES), 130)
        for name in C.COLOUR_NAMES:
            m = C.material(name)
            self.assertEqual(len(m["color"]), 3, name)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in m["color"]), name)

    def test_names_are_one_word(self):
        for name in C.COLOUR_NAMES:
            self.assertRegex(name, r"^[a-z]+(_[a-z]+)*$")


class Words(unittest.TestCase):
    def test_shades_move_the_colour(self):
        base = C.material("teal")["color"]
        self.assertGreater(sum(C.material({"name": "teal", "shade": "light"})["color"]), sum(base))
        self.assertLess(sum(C.material({"name": "teal", "shade": "dark"})["color"]), sum(base))

    def test_see_through_and_look(self):
        m = C.material({"name": "blue", "see_through": "half", "look": "glossy"})
        self.assertEqual(m["alpha"], 0.5)
        self.assertEqual(m["roughness"], C.LOOKS["glossy"]["roughness"])
        self.assertNotIn("alpha", C.material({"name": "blue", "see_through": "none"}))
        glow = C.material({"name": "gold", "look": "glow"})
        self.assertEqual(glow["emission_color"], glow["color"])

    def test_gradient(self):
        m = C.material({"name": "red", "gradient": {"to": "white", "direction": "down"}})
        self.assertEqual(m["gradient_axis"], "-z")
        self.assertEqual(m["gradient_color"], C.material("white")["color"])

    def test_typed_numbers_only_as_given(self):
        self.assertEqual(C.material({"hex": "#ffffff"})["color"], [1.0, 1.0, 1.0])
        self.assertEqual(C.material({"rgb": [255, 0, 0]})["color"], [1.0, 0.0, 0.0])

    def test_faults_are_named_never_guessed(self):
        self.assertTrue(C.faults("purplish"))
        self.assertTrue(C.faults({"name": "red", "shade": "medium"}))
        self.assertTrue(C.faults({"name": "red", "gradient": {"to": "sky"}}))
        self.assertTrue(C.faults({"hex": "#zzz"}))
        self.assertTrue(C.faults({"name": "red", "size": 2}))
        with self.assertRaises(ValueError):
            C.material("purplish")

    def test_words_of(self):
        w = C.words_of({"name": "red", "shade": "dark", "gradient": {"to": "gold", "direction": "up"}})
        self.assertIn(("color", "gold"), w)
        self.assertIn(("shade", "dark"), w)
        self.assertIn(("gradient_direction", "up"), w)


class GradientTool(unittest.TestCase):
    def test_gradient_code_and_prompt_unchanged(self):
        code = T.compile_calls({"calls": [{"tool": "set_material", "object": "Box", "name": "Fade", "color": [1, 0, 0],
                          "gradient_color": [1, 1, 1], "gradient_axis": "-z"}]})
        self.assertIn("ShaderNodeValToRGB", code)
        self.assertIn("outputs['Z']", code)
        # the build model's trained prompt does not learn of the new arguments
        self.assertNotIn("gradient", T.PROMPT)


if __name__ == "__main__":
    unittest.main()
