# SPDX-License-Identifier: Apache-2.0
"""Part placement in words: describe -> resolve gives the object back."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from maris3d.copilot import describe_parts as D  # noqa: E402
from maris3d.copilot.recipes import RECIPES  # noqa: E402

AUTHORED = os.path.join(ROOT, "internal", "release", "scene-tests", "rel", "authored", "objects-A.json")


def all_objects():
    out = [("lib:" + k, [{"name": p["name"], "size": list(p["dims"]), "centre": list(p["offset"])} for p in r["parts"]])
           for k, r in RECIPES.items() if len(r["parts"]) > 1]
    if os.path.exists(AUTHORED):
        out += [("new:" + o["name"], [{"name": p["name"], "size": p["size"], "centre": p["centre"]} for p in o["parts"]])
                for o in json.load(open(AUTHORED))]
    return out


def passes(parts):
    worst, floating, _got = D.round_trip(parts)
    return worst <= max(0.03, 0.10 * max(D.extent(parts))) and not floating


STOOL = [{"name": "Seat", "size": [0.4, 0.4, 0.04], "centre": [0, 0, 0.47]},
         {"name": "LegFL", "size": [0.04, 0.04, 0.45], "centre": [-0.18, -0.18, 0.225]},
         {"name": "LegBR", "size": [0.04, 0.04, 0.45], "centre": [0.18, 0.18, 0.225]}]


class Words(unittest.TestCase):
    def test_the_biggest_part_comes_first_and_the_rest_hang_on_it(self):
        said = D.describe(STOOL)
        self.assertEqual(said[0]["name"], "Seat")
        self.assertNotIn("place", said[0])
        self.assertNotIn("centre", said[1])                       # words only, no position numbers
        leg = next(p for p in said if p["name"] == "LegFL")["place"]
        self.assertEqual((leg["on"], leg["relation"]), ("Seat", "under"))
        self.assertEqual(leg["align"], {"x": "left", "y": "front"})

    def test_words_give_the_same_object_back_on_the_floor(self):
        got = {p["name"]: p["centre"] for p in D.resolve_parts(D.describe(STOOL))}
        self.assertAlmostEqual(got["Seat"][2], 0.47, places=3)
        self.assertAlmostEqual(got["LegFL"][0], -0.18, places=3)
        self.assertAlmostEqual(got["LegBR"][1], 0.18, places=3)
        self.assertEqual(D.floating(D.resolve_parts(D.describe(STOOL))), [])

    def test_an_unknown_word_is_centre_not_a_crash(self):
        got = D.resolve_parts([{"name": "A", "size": [1, 1, 1]},
                               {"name": "B", "size": [0.5, 0.5, 0.5], "place": {"on": "A", "relation": "on_top_of", "align": {"x": "sideways"}}}])
        self.assertAlmostEqual(got[1]["centre"][0], 0.0)
        self.assertAlmostEqual(got[1]["centre"][2], 1.25)


class Coverage(unittest.TestCase):
    def test_most_objects_survive_the_round_trip(self):
        objs = all_objects()
        failed = [name for name, parts in objs if not passes(parts)]
        print(f"\nround trip: {len(objs) - len(failed)} of {len(objs)} objects; not usable for parts data: {failed}")
        # 0.85 is the gate measured on the library plus the maintainers' authored objects; a tree
        # without those objects holds the library alone, which stands at 0.74 (its turned and
        # tilted parts have no word yet)
        gate = 0.85 if os.path.exists(AUTHORED) else 0.70
        self.assertGreaterEqual((len(objs) - len(failed)) / len(objs), gate)


class Axis(unittest.TestCase):
    """A round part lying on its side (a wheel): one word, `axis`."""
    CART = {"object": "cart", "size": [1.0, 0.7, 0.5], "parts": [
        {"name": "CartBed", "shape": "cube", "size": [1.0, 0.5, 0.2], "color": "oak"},
        {"name": "CartWheel", "shape": "cylinder", "size": [0.3, 0.1, 0.3], "axis": "y", "color": "black",
         "place": {"on": "CartBed", "relation": "front_of", "align": {"x": "left3", "z": "bottom"}}}]}

    def test_a_size_word_scales_the_usual_design_and_no_whole_size_is_needed(self):
        plain = {k: v for k, v in self.CART.items() if k != "size"}
        usual, why = D.to_recipe(plain)
        self.assertIsNone(why)
        big, why = D.to_recipe(dict(plain, size_word="big"))
        self.assertIsNone(why)
        self.assertEqual(big["size"], [round(1.5 * v, 3) for v in usual["size"]])
        tall, _ = D.to_recipe(dict(plain, size_word="tall"))
        self.assertEqual(tall["size"][:2], usual["size"][:2])
        self.assertAlmostEqual(tall["size"][2], 1.2 * usual["size"][2], places=3)
        self.assertEqual(D.check_answer(plain)[0], [])

    def test_a_size_word_outside_the_list_is_a_fault_but_still_builds_the_usual_size(self):
        plain = {k: v for k, v in self.CART.items() if k != "size"}
        faults, _ = D.check_answer(dict(plain, size_word="massive"))
        self.assertEqual(faults, ["size_word 'massive'"])
        odd, why = D.to_recipe(dict(plain, size_word="massive"))
        self.assertIsNone(why)
        self.assertEqual(odd["size"], D.to_recipe(plain)[0]["size"])

    def test_a_wheel_becomes_a_cylinder_laid_on_its_side(self):
        recipe, why = D.to_recipe(dict(self.CART, size=[1.0, 0.6, 0.3]))
        self.assertIsNone(why)
        wheel = recipe["parts"][1]
        self.assertEqual((wheel["radius"], wheel["depth"]), (0.15, 0.1))        # round in x and z, 0.1 thick
        self.assertEqual(wheel["rotation_deg"], [90.0, 0.0, 0.0])
        self.assertNotIn("rotation_deg", recipe["parts"][0])

    def test_the_source_rotation_is_read_as_an_axis_or_as_a_tilt(self):
        self.assertEqual(D.axis_of([0, 90, 0]), "x")
        self.assertEqual(D.axis_of([90, 0, 0]), "y")
        self.assertEqual(D.axis_of([0, 0, 90]), "z")                            # still standing
        self.assertIsNone(D.axis_of([26.57, 0, 0]))                             # a roof slab: tilted
        self.assertEqual(D.box_after([0.56, 0.56, 0.2], [0, 90, 0]), [0.2, 0.56, 0.56])

    def test_an_axis_on_a_box_is_a_fault(self):
        bad = json.loads(json.dumps(self.CART))
        bad["parts"][0]["axis"] = "x"
        self.assertTrue(any("axis" in f for f in D.check_answer(bad)[0]))


class TestPartsSystem(unittest.TestCase):
    def test_the_prompt_names_every_word_the_resolver_knows(self):
        text = D.PARTS_SYSTEM
        for word in list(D.RELATIONS) + list(D.STEPS[0]) + [w for w in D.SUNK if w != "none"] + list(D.PARTS_SHAPES):
            self.assertIn(word, text)
        self.assertIn("Never output coordinates", text)


if __name__ == "__main__":
    unittest.main()
