"""The scene in words: words -> placer -> describe gives the same words back."""
import itertools
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot import describe_scene as DS
from maris3d.copilot import place as PLACE


def thing(tid, noun, size, at, color="oak", yaw=0.0):
    part = {"name": tid + "Body", "shape": "cube", "size": list(size), "color": color,
            "centre": [0.0, 0.0, size[2] / 2.0]}
    s = AC._spec(tid, noun, [part], at)
    s["yaw"] = yaw
    return s


class RoundTrip(unittest.TestCase):
    def test_words_come_back(self):
        sofa = thing("Sofa", "sofa", [2.0, 0.9, 0.8], [0.0, 0.0, 0.0])
        anchor = AC._spec_box(sofa)
        size = [0.6, 0.6, 1.2]
        for rel, dist in itertools.product(("left_of", "right_of", "front_of", "behind"),
                                           ("touching", "tiny", "small", "medium", "large", "far")):
            c = PLACE.resolve({"relation": rel, "distance": dist}, anchor, size)["centre"]
            tree = thing("Tree", "tree", size, [c[0], c[1], c[2] - size[2] / 2.0], "green")
            got = DS.place_words(AC._spec_box(tree), {"Sofa": anchor})
            self.assertEqual((got["anchor"], got["relation"], got["distance"]), ("Sofa", rel, dist), (rel, dist))

    def test_on_top_of(self):
        table = thing("Table", "table", [1.2, 0.8, 0.75], [0, 0, 0])
        lamp = thing("Lamp", "lamp", [0.2, 0.2, 0.4], [0.1, 0.0, 0.75])
        got = DS.place_words(AC._spec_box(lamp), {"Table": AC._spec_box(table)})
        self.assertEqual((got["relation"], got["distance"]), ("on_top_of", "touching"))


class Lines(unittest.TestCase):
    def setUp(self):
        self.specs = {"Sofa": thing("Sofa", "sofa", [2, 0.9, 0.8], [0, 0, 0]),
                      "ChristmasTree": thing("ChristmasTree", "ChristmasTree", [1, 1, 2], [-1.6, 0, 0], "green")}
        for k in range(1, 4):
            h = thing(f"House{k}", "house", [6, 8, 5], [-20 + 8 * k, 30, 0], "brick")
            h["parts"][0]["name"] = f"HouseBody{k}"
            self.specs[h["id"]] = h

    def test_no_numbers_in_the_scene(self):
        text = DS.describe_scene(self.specs, open_things=("Sofa",))
        body = "\n".join(l for l in text.splitlines() if not l.startswith(("Parts of", "Last:")))
        # names may carry a number (House1); nothing else may
        for word in body.replace(",", " ").replace(":", " ").split():
            if any(ch.isdigit() for ch in word):
                self.assertRegex(word, r"^(House\d+(-House\d+)?|x\d+)$", text)

    def test_copies_are_one_line_and_parts_only_when_open(self):
        text = DS.describe_scene(self.specs, open_things=("ChristmasTree",))
        self.assertIn("House1-House3 (house) x3:", text)
        self.assertIn("ChristmasTree (christmas tree): left_of Sofa, small, facing south, green", text)
        self.assertIn("Parts of ChristmasTree: ChristmasTreeBody cube green", text)
        self.assertNotIn("Parts of Sofa", text)
        self.assertTrue(text.endswith("Last: House3"))

    def test_facing(self):
        self.assertEqual(DS.facing_word(0), "south")
        self.assertEqual(DS.facing_word(92), "east")
        self.assertEqual(DS.facing_word(-90), "west")


if __name__ == "__main__":
    unittest.main()


class EditInput(unittest.TestCase):
    def setUp(self):
        self.specs = {}
        for k in range(1, 21):
            h = thing(f"House{k}", "house", [6, 8, 5], [8 * k, 30, 0], "brick")
            h["parts"][0]["name"] = f"HouseBody{k}"
            self.specs[h["id"]] = h
        self.specs["Sofa"] = thing("Sofa", "sofa", [2, 0.9, 0.8], [0, 0, 0])

    def test_expand(self):
        self.assertEqual(len(DS.expand("House1-House20", self.specs)), 20)
        self.assertEqual(len(DS.expand("House3-House5", self.specs)), 3)
        self.assertEqual(len(DS.expand("houses", self.specs)), 20)
        self.assertEqual(DS.expand("Sofa", self.specs), ["Sofa"])
        self.assertEqual(DS.expand("piano", self.specs), [])

    def test_input_parts(self):
        text, notes = DS.edit_input(self.specs, "make the sofa red", clarified=["the big one"])
        self.assertIn("House1-House20 (house) x20", text)
        self.assertIn("Focus: Sofa:", text)
        self.assertTrue(text.endswith("Request: make the sofa red\nClarified: the big one"))
        self.assertEqual(notes, [])

    def test_focus_and_scene_cut_to_budget(self):
        text, notes = DS.edit_input(self.specs, "make all houses pink", focus=["houses"], budget=700)
        self.assertIn("Too many to show", text)
        self.assertLessEqual(DS.est_tokens(text) + DS.SYSTEM_TOKENS, 700 + 50)
        text, notes = DS.edit_input(self.specs, "x", budget=490)
        self.assertTrue(text.startswith("Scene: house x20, sofa"), text)
