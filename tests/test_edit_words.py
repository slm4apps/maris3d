"""The edit answer in words: every word form becomes the change apply_change makes."""
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot import edit_words as EW


def chair():
    parts = [{"name": "ChairSeat", "shape": "cube", "size": [0.5, 0.5, 0.06], "color": "oak"},
             {"name": "ChairBack", "shape": "cube", "size": [0.5, 0.05, 0.5], "color": "oak",
              "place": {"on": "ChairSeat", "relation": "on_top_of", "align": {"y": "back"}}}]
    return AC.spec_from_answer({"object": "chair", "parts": parts}, "Chair", [0.0, 0.0, 0.0])


def hat_design(what):
    return {"object": what, "parts": [
        {"name": "Brim", "shape": "cylinder", "size": [0.3, 0.3, 0.02], "color": "black"},
        {"name": "Crown", "shape": "cylinder", "size": [0.18, 0.18, 0.15], "color": "black",
         "place": {"on": "Brim", "relation": "on_top_of", "align": {}}}]}


class Words(unittest.TestCase):
    def setUp(self):
        self.specs = {"Chair": chair()}

    def test_scale_words(self):
        c = EW.to_change({"do": "scale", "object": "Chair", "size": "a_bit_bigger", "along": "height"}, self.specs)
        self.assertEqual(c["by"], {"z": 1.2})
        c = EW.to_change({"do": "scale", "object": "Chair", "size": "double"}, self.specs)
        self.assertEqual(c["by"], {"x": 2.0, "y": 2.0, "z": 2.0})
        c = EW.to_change({"do": "scale", "object": "Chair", "times": 2.5, "along": "width"}, self.specs)
        self.assertEqual(c["by"], {"x": 2.5})
        with self.assertRaises(EW.WordError):
            EW.to_change({"do": "scale", "object": "Chair", "size": "massive"}, self.specs)

    def test_numbers_as_words_code_computes(self):
        c = EW.to_change({"do": "scale", "object": "Chair", "times": "two_and_half"}, self.specs)
        self.assertEqual(c["by"], {"x": 2.5, "y": 2.5, "z": 2.5})
        c = EW.to_change({"do": "scale", "object": "Chair", "percent": 30, "way": "more", "along": "height"},
                         self.specs)
        self.assertAlmostEqual(c["by"]["z"], 1.3)
        c = EW.to_change({"do": "scale", "object": "Chair", "percent": 20, "way": "less"}, self.specs)
        self.assertAlmostEqual(c["by"]["x"], 0.8)
        for bad in ({"times": "lots"}, {"percent": 30}, {"percent": 100, "way": "less"}):
            with self.assertRaises(EW.WordError):
                EW.to_change(dict({"do": "scale", "object": "Chair"}, **bad), self.specs)
        c = EW.to_change({"do": "move", "object": "Chair", "shift": {"toward": "right", "amount": 30, "unit": "cm"}},
                         self.specs)
        self.assertAlmostEqual(c["shift"]["x"], 0.3)
        with self.assertRaises(EW.WordError):
            EW.to_change({"do": "move", "object": "Chair", "shift": {"toward": "right", "amount": 30}}, self.specs)

    def test_size_like_another_thing(self):
        specs = {"Chair": chair(), "Tree": dict(chair(), id="Tree", size=[1.0, 1.0, 4.0])}
        own = specs["Chair"]["size"]
        c = EW.to_change({"do": "scale", "object": "Chair", "like": "Tree", "along": "height"}, specs)
        self.assertAlmostEqual(c["by"]["z"], round(4.0 / own[2], 4))
        c = EW.to_change({"do": "scale", "object": "Chair", "like": "Tree", "times": "half", "along": "height"}, specs)
        self.assertAlmostEqual(c["by"]["z"], round(2.0 / own[2], 4))
        with self.assertRaises(EW.WordError):
            EW.to_change({"do": "scale", "object": "Chair", "like": "Moon"}, specs)

    def test_one_size_table(self):
        from maris3d.copilot import describe_parts as DP
        self.assertIs(EW.SIZE_WORD_FACTOR, DP.SIZE_WORDS)

    def test_shift_and_turn_words(self):
        c = EW.to_change({"do": "move", "object": "Chair", "shift": {"toward": "left", "by": "small"}}, self.specs)
        self.assertEqual(c["shift"], {"x": -0.175})
        c = EW.to_change({"do": "move", "object": "Chair", "shift": {"toward": "up", "metres": 5}}, self.specs)
        self.assertEqual(c["shift"], {"z": 5.0})
        self.assertEqual(EW.to_change({"do": "turn", "object": "Chair", "by": "quarter_left"}, self.specs)["by"], 90.0)
        self.assertEqual(EW.to_change({"do": "turn", "object": "Chair", "face": "north"}, self.specs)["face"], "north")

    def test_recolor_words_apply(self):
        out = EW.apply_words({"kind": "change", "changes": [{"do": "recolor", "object": "Chair",
                              "color": {"name": "teal", "shade": "dark", "look": "glossy"}}]}, self.specs)
        self.assertEqual(out.errors, [])
        mat = [c for c in out.calls if c["tool"] == "set_material"][0]
        self.assertEqual(sorted(mat["objects"]), ["ChairBack", "ChairSeat"])

    def test_tilt_whole_and_part(self):
        out = EW.apply_words({"kind": "change", "changes": [{"do": "tilt", "object": "Chair", "toward": "back", "by": "slight"}]}, self.specs)
        self.assertEqual(out.errors, [])
        self.assertEqual(out.calls[0]["rotation_deg"], [-15.0, 0.0, 0.0])
        out = EW.apply_words({"kind": "change", "changes": [{"do": "tilt", "object": "Chair", "parts": ["ChairBack"],
                                                             "toward": "back", "by": "slight"}]}, self.specs)
        self.assertEqual(out.errors, [])
        self.assertTrue(any(c.get("rotation_deg") == [-15.0, 0.0, 0.0] and c["object"] == "ChairBack" for c in out.calls))

    def test_add_through_the_parts_planner(self):
        ans = {"kind": "change", "changes": [{"do": "add", "object": "Chair", "what": "hat", "on": "ChairSeat",
                                              "relation": "on_top_of", "color": "gold"}]}
        out = EW.apply_words(ans, self.specs, design=hat_design)
        self.assertEqual(out.errors, [])
        names = [p["name"] for p in out.specs["Chair"]["parts"]]
        self.assertIn("HatBrim", names)
        self.assertIn("HatCrown", names)
        self.assertTrue(any(c["tool"] == "set_material" and "HatBrim" in c.get("objects", []) for c in out.calls))
        bad = EW.apply_words(dict(ans, changes=[dict(ans["changes"][0], on="ChairLeg")]), self.specs, design=hat_design)
        self.assertTrue(bad.errors)
        self.assertTrue(EW.apply_words(ans, self.specs).errors)          # no planner: said, not guessed

    def test_look(self):
        out = EW.apply_words({"kind": "look", "things": ["Chair", "Nope"]}, self.specs)
        self.assertEqual((out.kind, out.look), ("look", ["Chair"]))


if __name__ == "__main__":
    unittest.main()


class Prompt(unittest.TestCase):
    def test_wrap_round_trip(self):
        ans = {"kind": "change", "changes": [{"do": "remove", "object": "Chair"}]}
        text = EW.wrap(ans)
        self.assertTrue(text.startswith("<tool_call>") and EW.TOOL_NAME in text)
        self.assertEqual(EW.unwrap(text), ans)
        self.assertEqual(EW.unwrap('{"kind":"build"}'), {"kind": "build"})
        self.assertIsNone(EW.unwrap("no json here"))

    def test_prompt_has_no_numbers_to_work_out(self):
        self.assertNotIn("metres:", EW.EDIT_SYSTEM)
        for w in ("look", "tilt", "Clarified", "a_bit_bigger", "quarter_left", "see_through"):
            self.assertIn(w, EW.EDIT_SYSTEM)

    def test_length_of_a_standing_part_is_its_height(self):
        spec = chair()
        c = EW.to_change({"do": "scale", "object": "Chair", "parts": ["ChairBack"], "size": "bigger",
                          "along": "length"}, {"Chair": spec})
        self.assertEqual(c["by"], {"z": 1.5})
        c = EW.to_change({"do": "scale", "object": "Chair", "size": "bigger", "along": "length"}, {"Chair": spec})
        self.assertEqual(list(c["by"]), ["x"])


class Groups(unittest.TestCase):
    def test_group_change_expands(self):
        specs = {}
        for k in (1, 2, 3):
            s = chair()
            s["id"] = f"Chair{k}"
            specs[s["id"]] = s
        out = EW.apply_words({"kind": "change", "changes": [{"do": "recolor", "object": "Chair1-Chair3", "color": "pink"}]}, specs)
        self.assertEqual(out.errors, [])
        self.assertEqual(len([c for c in out.calls if c["tool"] == "set_material"]), 3)
        bad = EW.apply_words({"kind": "change", "changes": [{"do": "rename", "object": "chairs", "to": "X"}]}, specs)
        self.assertTrue(bad.errors)
