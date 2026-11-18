# SPDX-License-Identifier: GPL-3.0-or-later
"""The maris contract (assets/maris/maris.json) must agree with the build script."""
import json
import re
import unittest
from pathlib import Path

from maris3d.copilot import colours, show

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "assets/maris/maris.json").read_text(encoding="utf-8"))
SCRIPT = (ROOT / "assets/maris/build_maris.py").read_text(encoding="utf-8")


class MarisSpec(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(SPEC["version"], r"^\d+\.\d+\.\d+$")

    def test_every_pose_has_a_sequence(self):
        for pose in SPEC["poses"]:
            self.assertRegex(SCRIPT, rf'"{pose}": \[', pose)

    def test_faces_use_known_mouths(self):
        self.assertEqual(len(SPEC["faces"]), 5)
        for name, face in SPEC["faces"].items():
            self.assertIn(face["mouth"], SPEC["mouths"], name)
            self.assertLess(abs(face["lift"]), 0.03, name)
            self.assertLessEqual(abs(face["tilt"]), 30, name)

    def test_mouths_are_built(self):
        for mouth in SPEC["mouths"]:
            self.assertTrue(f'"{mouth}"' in SCRIPT or f'"Mouth{mouth}"' in SCRIPT, mouth)

    def test_outfits(self):
        outfits = SPEC["outfits"]
        self.assertIn(SPEC["default_outfit"], outfits)
        self.assertGreaterEqual(len(outfits), 3)
        built = set(re.findall(r'piece\("(\w+)", "(\w+)"', SCRIPT))
        built |= {(o, f"{base}{i}") for o, base in
                  re.findall(r'piece\("(\w+)", f"(\w+)\{i\}"', SCRIPT) for i in range(3)}
        seen = set()
        for name, outfit in outfits.items():
            self.assertTrue(outfit["label"] and outfit["about"], name)
            for slot, answer in outfit["colours"].items():
                self.assertIn(slot, SPEC["slots"], (name, slot))
                self.assertEqual(colours.faults(answer), [], (name, slot))
            for piece in outfit["pieces"]:
                self.assertIn((name, piece), built, f"{name}: {piece} not built")
                self.assertNotIn(piece, seen, "pieces belong to one outfit")
                seen.add(piece)
        self.assertEqual({p for _, p in built}, seen, "built pieces missing from maris.json")

    def test_distinct_outfits(self):
        looks = {json.dumps([o["colours"], o["pieces"]], sort_keys=True)
                 for o in SPEC["outfits"].values()}
        self.assertEqual(len(looks), len(SPEC["outfits"]))

    def test_colours_are_planner_colour_answers(self):
        """Every maris colour speaks the planner / edit colour language, so the panel can offer
        the same options the models use."""
        for slot, info in SPEC["slots"].items():
            self.assertTrue(info["label"], slot)
            self.assertEqual(colours.faults(info["colour"]), [], slot)
        self.assertIn(SPEC["default_skin"], SPEC["skins"])
        for name, answer in SPEC["skins"].items():
            self.assertEqual(colours.faults(answer), [], name)
        self.assertIn(SPEC["default_hair"], SPEC["hairs"])
        for name, pair in SPEC["hairs"].items():
            self.assertEqual(set(pair), {"hair", "brow"}, name)
            for slot, answer in pair.items():
                self.assertEqual(colours.faults(answer), [], (name, slot))

    def test_materials_resolve(self):
        for slot in SPEC["slots"]:
            for outfit in SPEC["outfits"]:
                key, mat = show.maris_material(SPEC, slot, outfit=outfit)
                self.assertTrue(key.startswith("maris_" + slot + "."))
                self.assertEqual(len(mat["color"]), 3)
        key, mat = show.maris_material(SPEC, "dress", custom={"dress": {"name": "holly", "look": "glossy"}})
        self.assertEqual(key, "maris_dress.holly_glossy")
        self.assertLess(mat["roughness"], 0.2)
        key, _ = show.maris_material(SPEC, "skin", skin="mocha")
        self.assertEqual(key, "maris_skin.mocha")


if __name__ == "__main__":
    unittest.main()
