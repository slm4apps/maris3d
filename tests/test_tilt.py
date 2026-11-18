"""`tilt`: a part that leans 15 / 30 / 45 degrees. `size` is its own size; the placer uses the
leaned box. Built by the harness, not yet in the parts prompt.

Measured in Blender (headless, dsl.tools.compile_calls): a roof slab 0.1 x 1.6 x 1.2 leaning
right steep on walls 2 x 1.6 x 1 and a post leaning front medium came out with the resolver's box
and centre to 1 mm; the slab's top moved to +x, the post's to -y (front).
"""
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot import describe_parts as DP

from tests.test_apply_change import build, ch, run, statuses

WALLS = {"name": "Walls", "shape": "cube", "size": [2.0, 1.6, 1.0], "color": "brick"}


def slab(by="steep", toward="right", **kw):
    return dict({"name": "RoofL", "shape": "cube", "size": [0.1, 1.6, 1.2], "color": "red",
                 "tilt": {"toward": toward, "by": by},
                 "place": {"on": "Walls", "relation": "on_top_of", "align": {"x": "left"}}}, **kw)


class Tilt(unittest.TestCase):
    def test_not_in_the_prompt_yet(self):
        self.assertNotIn("tilt", DP.PARTS_SYSTEM)

    def test_turns(self):
        self.assertEqual(DP.tilt_turn(slab()), [0.0, 45.0, 0.0])
        self.assertEqual(DP.tilt_turn(slab("slight", "left")), [0.0, -15.0, 0.0])
        self.assertEqual(DP.tilt_turn(slab("medium", "front")), [30.0, 0.0, 0.0])
        self.assertEqual(DP.tilt_turn(slab("medium", "back")), [-30.0, 0.0, 0.0])
        self.assertIsNone(DP.tilt_turn(slab("very")))
        self.assertIsNone(DP.tilt_turn(slab(shape="cylinder", axis="x")))
        self.assertIsNone(DP.tilt_turn(slab(shape="prism")))

    def test_placed_by_its_leaned_box(self):
        faults, built = DP.check_answer({"object": "house", "parts": [WALLS, slab()]})
        self.assertEqual(faults, [])
        roof = built[1]
        self.assertEqual(roof["own"], [0.1, 1.6, 1.2])
        self.assertAlmostEqual(roof["size"][0], 0.9192, places=3)          # 0.1 cos45 + 1.2 sin45
        self.assertAlmostEqual(roof["centre"][2] - roof["size"][2] / 2, 1.0, places=3)   # sits on the walls
        rp = DP.recipe_part(roof, roof["centre"], "RoofL")
        self.assertEqual((rp["dims"], rp["rotation_deg"]), ([0.1, 1.6, 1.2], [0.0, 45.0, 0.0]))

    def test_bad_tilt_is_a_fault(self):
        for bad in (slab("very"), slab(toward="up"), slab(shape="prism"), dict(slab(), tilt="steep")):
            faults, _ = DP.check_answer({"parts": [WALLS, bad]})
            self.assertTrue(any("tilt" in f for f in faults), bad)

    def test_words_give_back_the_own_size(self):
        _f, built = DP.check_answer({"parts": [WALLS, slab()]})
        again = AC._words(built)
        self.assertEqual(again[1]["size"], [0.1, 1.6, 1.2])
        self.assertNotIn("own", again[1])
        self.assertEqual(DP.resolve_parts(again)[1]["size"], built[1]["size"])

    def test_added_by_a_change_and_scaled(self):
        _c, s, sim = build(("sofa", None))
        back = {"name": "SofaShade", "shape": "cube", "size": [1.0, 0.05, 0.6], "color": "red",
                "tilt": {"toward": "back", "by": "slight"},
                "place": {"on": "SofaSeat", "relation": "on_top_of"}}
        if "SofaSeat" not in sim.o:
            back["place"]["on"] = next(n for n in sim.o if n.startswith("Sofa") and n != "Sofa")
        _d, rows = run(s, sim, ch({"do": "add", "object": "Sofa", "parts": [back]}))
        self.assertEqual(statuses(rows), ["ok"])
        part = {p["name"]: p for p in s.specs["Sofa"]["parts"]}["SofaShade"]
        self.assertEqual(part["own"], [1.0, 0.05, 0.6])
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Sofa", "parts": ["SofaShade"], "by": {"z": 2}}))
        self.assertEqual(statuses(rows), ["ok"])
        part = {p["name"]: p for p in s.specs["Sofa"]["parts"]}["SofaShade"]
        self.assertEqual(part["own"], [1.0, 0.05, 1.2])


if __name__ == "__main__":
    unittest.main()


class FromSources(unittest.TestCase):
    """The data builders' side: a source rotation -> tilt words, and back through describe."""

    def test_tilt_of(self):
        self.assertEqual(DP.tilt_of([0, 27, 0]), {"toward": "right", "by": "medium"})
        self.assertEqual(DP.tilt_of([-44, 0, 0]), {"toward": "back", "by": "steep"})
        self.assertEqual(DP.tilt_of([0, 405, 0]), {"toward": "right", "by": "steep"})
        for no in ([0, 60, 0], [10, 20, 0], [0, 0, 30], None):
            self.assertIsNone(DP.tilt_of(no))
        for toward in DP.LEAN:
            for by in DP.TILTS:
                t = {"toward": toward, "by": by}
                self.assertEqual(DP.tilt_of(DP.tilt_turn({"tilt": t})), t)

    def test_describe_says_the_own_size_and_comes_back(self):
        _f, built = DP.check_answer({"parts": [WALLS, slab()]})
        said = DP.describe(built)
        roof = {p["name"]: p for p in said}["RoofL"]
        self.assertEqual(roof["size"], [0.1, 1.6, 1.2])
        self.assertEqual(roof["tilt"], {"toward": "right", "by": "steep"})
        self.assertNotIn("own", roof)
        worst, floating, _got = DP.round_trip(built)
        self.assertLess(worst, 0.01)
        self.assertEqual(floating, [])
