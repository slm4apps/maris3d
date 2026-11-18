# SPDX-License-Identifier: Apache-2.0
"""Sizes in words: nouns, multipliers, ratio words -> metres."""
import unittest

from maris3d.copilot import describe_parts as DP
from maris3d.copilot import size_words as SW


def stool(object_size="half door"):
    return {"object": "stool", "size": object_size, "parts": [
        {"name": "Seat", "shape": "cylinder", "size": ["half", "half", "tenth"], "color": "oak"},
        {"name": "Leg", "shape": "cylinder", "size": ["tenth", "tenth", "double"], "color": "pine",
         "place": {"on": "Seat", "relation": "under"}}]}


class Nouns(unittest.TestCase):
    def test_ladder_doubles_from_hair_to_tower(self):
        vals = list(SW.NOUNS.values())
        self.assertEqual(list(SW.NOUNS)[0], "hair")
        self.assertEqual(list(SW.NOUNS)[-1], "tower")
        for a, b in zip(vals, vals[1:]):
            self.assertAlmostEqual(b / a, 2.0, delta=0.15)

    def test_multiplier_times_noun_without_model_maths(self):
        self.assertEqual(SW.noun_metres("door"), 1.9)
        self.assertAlmostEqual(SW.noun_metres("half door"), 0.95)
        self.assertAlmostEqual(SW.noun_metres("one_and_half chair"), 1.44)
        self.assertIsNone(SW.noun_metres("double door"))       # past 1.5 the next noun is the word
        self.assertIsNone(SW.noun_metres("teapot"))
        self.assertIsNone(SW.noun_metres(1.9))

    def test_object_word_round_trip(self):
        for m in (0.0002, 0.004, 0.09, 0.9, 1.8, 4.5, 30):
            self.assertLess(abs(SW.noun_metres(SW.object_word(m)) / m - 1), 0.13, m)


class ToMetres(unittest.TestCase):
    def test_first_part_against_the_object_then_parts_against_their_anchor(self):
        out, faults = SW.to_metres(stool())
        self.assertEqual(faults, [])
        self.assertNotIn("size", out)
        self.assertEqual(out["parts"][0]["size"], [0.475, 0.475, 0.095])
        self.assertEqual(out["parts"][1]["size"], [0.0475, 0.0475, 0.19])

    def test_absolute_noun_on_a_part(self):
        a = stool()
        a["parts"][1]["size"] = ["pea", "pea", "half chair"]
        out, faults = SW.to_metres(a)
        self.assertEqual(faults, [])
        self.assertEqual(out["parts"][1]["size"], [0.0075, 0.0075, 0.48])

    def test_numbers_and_unknown_words_are_faults(self):
        a = stool()
        a["parts"][0]["size"] = [0.4, "half", "tenth"]
        self.assertTrue(SW.to_metres(a)[1])
        self.assertTrue(SW.to_metres(stool("teapot"))[1])
        b = stool()
        b["parts"][1]["size"] = ["tenth", "lots", "double"]
        self.assertTrue(SW.to_metres(b)[1])

    def test_known_parts_anchor_an_added_part(self):
        add = {"parts": [{"name": "Knob", "shape": "uv_sphere", "size": ["quarter", "quarter", "quarter"],
                          "color": "brass", "place": {"on": "Door", "relation": "front_of"}}]}
        out, faults = SW.to_metres(add, known={"Door": [0.8, 0.04, 2.0]})
        self.assertEqual(faults, [])
        self.assertEqual(out["parts"][0]["size"], [0.2, 0.01, 0.5])

    def test_check_answer_builds_a_word_answer(self):
        faults, built = DP.check_answer(stool())
        self.assertEqual(faults, [])
        self.assertAlmostEqual(DP.extent(built)[2], 0.095 + 0.19, places=3)

    def test_check_answer_refuses_a_bad_word(self):
        faults, built = DP.check_answer(stool("teapot"))
        self.assertTrue(faults)
        self.assertEqual(built, [])

    def test_old_metres_answers_still_read(self):
        old = {"object": "box", "parts": [{"name": "Box", "shape": "cube", "size": [1, 1, 1], "color": "red"}]}
        self.assertFalse(SW.uses_words(old))
        self.assertEqual(DP.check_answer(old)[0], [])


class ToWords(unittest.TestCase):
    def test_words_rebuild_the_design_closely(self):
        parts = [{"name": "Top", "shape": "cube", "size": [1.2, 0.7, 0.04], "color": "oak"},
                 {"name": "Leg", "shape": "cube", "size": [0.05, 0.05, 0.71], "color": "oak",
                  "place": {"on": "Top", "relation": "under"}}]
        words = SW.to_words(parts, 1.2)
        self.assertTrue(all(isinstance(w, str) for p in words for w in p["size"]))
        out, faults = SW.to_metres({"size": SW.object_word(1.2), "parts": words})
        self.assertEqual(faults, [])
        for got, want in zip(out["parts"], parts):
            for g, w in zip(got["size"], want["size"]):
                self.assertLess(abs(g / w - 1), 0.15, (got["name"], g, w))


class Vendored(unittest.TestCase):
    def test_every_copilot_import_of_a_vendored_module_is_vendored(self):
        """A module the add-on imports (even inside a function) must be in the add-on."""
        import os
        import re
        from maris3d import addonbuild
        src = os.path.join(os.path.dirname(addonbuild.__file__), "copilot")
        vendored = {os.path.basename(k)[:-3] for k in addonbuild._VENDOR if k.startswith("copilot/")}
        for mod in vendored:
            with open(os.path.join(src, mod + ".py")) as fh:
                text = fh.read()
            for name in re.findall(r"^\s*from \. import (\w+)", text, re.M):
                self.assertIn(name, vendored, f"{mod}.py imports {name}, which the add-on does not ship")


class EditAdd(unittest.TestCase):
    def test_an_added_design_in_words_gets_metres(self):
        from maris3d.copilot import edit_words as EW
        from tests.test_edit_words import Words
        w = Words(); w.setUp()

        def design(what):
            return {"object": what, "size": "half shoebox", "parts": [
                {"name": "Brim", "shape": "cylinder", "size": ["same", "same", "tenth"], "color": "black"},
                {"name": "Crown", "shape": "cylinder", "size": ["two_thirds", "two_thirds", "five_times"],
                 "color": "black", "place": {"on": "Brim", "relation": "on_top_of", "align": {}}}]}
        ans = {"kind": "change", "changes": [{"do": "add", "object": "Chair", "what": "hat", "on": "ChairSeat",
                                              "relation": "on_top_of"}]}
        out = EW.apply_words(ans, w.specs, design=design)
        self.assertEqual(out.errors, [])
        brim = next(p for p in out.specs["Chair"]["parts"] if p["name"] == "HatBrim")
        self.assertEqual(brim["size"], [0.12, 0.12, 0.012])


class Vocabulary(unittest.TestCase):
    def test_size_words_are_listed_and_unknown_ones_found(self):
        from maris3d.copilot import vocabulary as V
        a = stool()
        used = V.words_in("parts", a)
        self.assertIn(("size_multiplier", "half"), used)
        self.assertIn(("size_noun", "door"), used)
        self.assertIn(("size_ratio", "tenth"), used)
        self.assertEqual(V.unknown_words("parts", a), [])
        a["parts"][0]["size"][0] = "heaps"
        self.assertEqual(V.unknown_words("parts", a), [("size_ratio", "heaps")])


if __name__ == "__main__":
    unittest.main()
