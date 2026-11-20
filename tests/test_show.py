# SPDX-License-Identifier: Apache-2.0
"""The scene show core (copilot/show.py): effects, the event director, designs."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from maris3d.copilot import show

SPEC = json.loads((Path(__file__).resolve().parents[1] / "assets/maris/maris.json").read_text())


class Effects(unittest.TestCase):
    def test_every_effect_starts_and_ends(self):
        for eff in show.EFFECTS:
            start = show.effect_frame(eff, 0.0, n_chars=10)
            late = show.effect_frame(eff, 30.0, n_chars=10)
            if eff == "float":
                self.assertFalse(late["done"])
                continue
            self.assertTrue(late["done"], eff)
            if eff != "dissolve":
                self.assertAlmostEqual(late["scale"], 1.0, places=3, msg=eff)
                self.assertEqual(late["chars"], 10, eff)
            self.assertLessEqual(start["scale"], 1.0, eff)

    def test_type_shows_letters_one_by_one(self):
        shown = [show.effect_frame("type", t * 0.045, n_chars=5)["chars"] for t in range(7)]
        self.assertEqual(shown, [1, 2, 3, 4, 5, 5, 5])

    def test_no_motion_is_plain_fade(self):
        self.assertEqual(show.effect_frame("pop", 0.1, 4, motion=False),
                         show.effect_frame("fade", 0.1, 4))

    def test_unknown_effect(self):
        with self.assertRaises(ValueError):
            show.effect_frame("explode", 0.1)


class DirectorTest(unittest.TestCase):
    def test_inspections_are_rate_limited(self):
        d = show.Director()
        cues = [d.cue("built_exact", t * 0.5) for t in range(7)]
        self.assertEqual([c is not None for c in cues], [True, False, False, True, False, False, True])

    def test_faces(self):
        d = show.Director()
        self.assertEqual(d.cue("corrected", 0)["face"], "grumpy")
        self.assertEqual(d.cue("error", 0.1)["face"], "sad")
        self.assertEqual(d.cue("done", 0.2)["face"], "woo")

    def test_switches(self):
        self.assertIsNone(show.Director(maris=False).cue("intro", 0))
        self.assertEqual(show.Director(fun_finish=False).cue("done", 0)["pose"], "thumbs_up")
        self.assertIn(show.Director(seed=3).cue("done", 0)["pose"], show.FUN_FINISHES)

    def test_poses_and_faces_exist_in_the_maris(self):
        for pose, face in show.REACTIONS.values():
            self.assertIn(pose, SPEC["poses"])
            self.assertIn(face, SPEC["faces"])
        for pose in show.FUN_FINISHES:
            self.assertIn(pose, SPEC["poses"])


class Designs(unittest.TestCase):
    def test_presets_are_designs(self):
        presets = show.preset_designs(SPEC)
        self.assertEqual(list(presets), list(SPEC["outfits"]))
        for d in presets.values():
            self.assertEqual(show.design_faults(SPEC, d), [])
            self.assertEqual(set(show.design_materials(SPEC, d)), set(SPEC["slots"]))

    def test_save_load_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "designs.json")
            mine = {"label": "Night sky", "outfit": "winter", "skin": "mocha",
                    "colours": {"dress": {"name": "navy", "look": "satin"}, "hair": "silver_grey"}}
            key = show.save_user_design(path, SPEC, mine)
            self.assertEqual(key, "night_sky")
            self.assertEqual(show.load_user_designs(path, SPEC)[key], mine)
            # a shipped name is never overwritten, a second save gets a new key
            self.assertEqual(show.save_user_design(path, SPEC, dict(mine, label="Sea")), "sea_2")
            self.assertEqual(show.save_user_design(path, SPEC, mine), "night_sky_2")
            allk = list(show.all_designs(SPEC, path))
            self.assertEqual(allk[:len(SPEC["outfits"])], list(SPEC["outfits"]))
            self.assertTrue(show.delete_user_design(path, SPEC, "sea_2"))
            self.assertNotIn("sea_2", show.load_user_designs(path, SPEC))
            mats = show.design_materials(SPEC, mine)
            self.assertEqual(mats["skin"][0], "maris_skin.mocha")
            self.assertEqual(mats["dress"][0], "maris_dress.navy_satin")
            self.assertEqual(mats["hair"][0], "maris_hair.silver_grey")      # custom wins
            redhead = dict(mine, hair="cinnamon", colours={})
            mats = show.design_materials(SPEC, redhead)
            self.assertEqual(mats["hair"][0], "maris_hair.cinnamon")
            self.assertEqual(mats["brow"][0], "maris_brow.cinnamon_dark")
            self.assertTrue(show.design_faults(SPEC, dict(mine, hair="green_mohawk")))

    def test_bad_designs(self):
        self.assertTrue(show.design_faults(SPEC, {"label": "x", "outfit": "pirate", "skin": "light"}))
        self.assertTrue(show.design_faults(SPEC, {"label": "x", "outfit": "sea", "skin": "light",
                                                   "colours": {"dress": "plaid"}}))
        with self.assertRaises(ValueError):
            show.save_user_design("/nonexistent/x.json", SPEC, {"label": ""})

    def test_broken_file_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "d.json")
            Path(path).write_text("{not json")
            self.assertEqual(show.load_user_designs(path, SPEC), {})


class Toys(unittest.TestCase):
    def test_three_christmas_three_everyday(self):
        themes = [t["theme"] for t in SPEC["toys"].values()]
        self.assertEqual(themes.count("christmas"), 3)
        self.assertEqual(themes.count("everyday"), 3)
        for o in SPEC["outfits"].values():
            self.assertIn(o["toy_theme"], ("christmas", "everyday"))

    def test_toys_are_built(self):
        script = (Path(__file__).resolve().parents[1] / "assets/maris/build_maris.py").read_text()
        for name in SPEC["toys"]:
            self.assertIn(f'"{name}": toy_{name}', script, name)

    def test_fixed_toy(self):
        d = {"label": "x", "outfit": "sea", "skin": "light", "toy": "teddy"}
        self.assertEqual(show.design_faults(SPEC, d), [])
        self.assertEqual(show.pick_toy(SPEC, d), "teddy")

    def test_random_fits_the_outfit_and_never_repeats(self):
        import random
        rng = random.Random(7)
        for outfit, theme in (("winter", "christmas"), ("sea", "everyday"), ("conductor", "everyday")):
            d = {"label": "x", "outfit": outfit, "skin": "light", "toy": "random"}
            last = None
            for _ in range(20):
                t = show.pick_toy(SPEC, d, rng, last)
                self.assertEqual(SPEC["toys"][t]["theme"], theme)
                self.assertNotEqual(t, last)
                last = t

    def test_random_any_reaches_every_toy(self):
        import random
        rng = random.Random(3)
        d = {"label": "x", "outfit": "sea", "skin": "light", "toy": "random_any"}
        seen = {show.pick_toy(SPEC, d, rng) for _ in range(200)}
        self.assertEqual(seen, set(SPEC["toys"]))

    def test_bad_toy_and_old_designs(self):
        self.assertTrue(show.design_faults(SPEC, {"label": "x", "outfit": "sea", "skin": "light", "toy": "kite"}))
        old = {"label": "x", "outfit": "sea", "skin": "light", "colours": {}}   # saved before toys
        self.assertEqual(show.design_faults(SPEC, old), [])
        self.assertIn(show.pick_toy(SPEC, old), SPEC["toys"])

    def test_presets_choose_random(self):
        for d in show.preset_designs(SPEC).values():
            self.assertEqual(d["toy"], SPEC["default_toy"])


class Names(unittest.TestCase):
    def test_names(self):
        self.assertEqual(show.msg_name("say", 3), "msg_say_003")
        self.assertTrue(show.is_show_name("Maris_Head"))
        self.assertFalse(show.is_show_name("Bench"))
        self.assertAlmostEqual(show.scene_scale([40, 10, 5]), 3.0)
        self.assertAlmostEqual(show.scene_scale([1, 1, 1]), 0.4)


if __name__ == "__main__":
    unittest.main()
