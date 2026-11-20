# SPDX-License-Identifier: Apache-2.0
"""Maris's carry dash, standing spots, sitting and visibility rules (copilot/show.py, no Blender)."""
import json
import math
import random
import unittest
from pathlib import Path

from maris3d.copilot import show

SPEC = json.loads((Path(__file__).resolve().parents[1] / "assets/maris/maris.json").read_text("utf-8"))


def box(x0, y0, x1, y1, h=1.0):
    return ((x0, y0, 0.0), (x1, y1, h))


class Visibility(unittest.TestCase):
    NAMES = ["Maris_Dress", "Maris_Hair", "Maris_SitLap", "Maris_SitDrape", "Maris_SitPool",
             "Maris_ToolSeaWand", "Maris_ToolNinjaBlade", "Maris_NinjaHood", "Maris_ToyTrain",
             "Maris_WandStar", "Maris_Spindle", "Maris_MouthSmile"]
    PROPS = {"Maris_SitLap": {"maris_pose": "sit,sit_seat"}, "Maris_SitDrape": {"maris_pose": "sit_seat"},
             "Maris_SitPool": {"maris_pose": "sit"}, "Maris_ToolSeaWand": {"maris_tool": "sea"},
             "Maris_ToolNinjaBlade": {"maris_tool": "ninja"}, "Maris_NinjaHood": {"maris_outfit": "ninja"},
             "Maris_ToyTrain": {"maris_toy": "train"}}

    def vis(self, outfit, pose):
        return show.visible(SPEC, self.NAMES, outfit, pose, self.PROPS, toy="train")

    def test_standing(self):
        v = self.vis("sea", "idle")
        self.assertTrue(v["Maris_Dress"] and v["Maris_Hair"] and v["Maris_ToyTrain"] and v["Maris_WandStar"])
        self.assertFalse(v["Maris_SitLap"] or v["Maris_ToolSeaWand"] or v["Maris_NinjaHood"])
        self.assertNotIn("Maris_MouthSmile", v)              # faces pick the mouth

    def test_sitting_swaps_the_dress(self):
        ground, seat = self.vis("sea", "sit"), self.vis("sea", "sit_seat")
        self.assertFalse(ground["Maris_Dress"] or seat["Maris_Dress"])
        self.assertTrue(ground["Maris_SitPool"] and not ground["Maris_SitDrape"])
        self.assertTrue(seat["Maris_SitDrape"] and not seat["Maris_SitPool"])
        self.assertTrue(ground["Maris_SitLap"] and seat["Maris_SitLap"])
        self.assertFalse(ground["Maris_ToyTrain"])

    def test_tool_only_when_placing_and_only_her_outfits(self):
        self.assertTrue(self.vis("sea", "place")["Maris_ToolSeaWand"])
        self.assertFalse(self.vis("sea", "place")["Maris_ToolNinjaBlade"])
        self.assertTrue(self.vis("ninja", "place")["Maris_ToolNinjaBlade"])
        self.assertFalse(self.vis("ninja", "run")["Maris_ToolNinjaBlade"])
        self.assertFalse(self.vis("sea", "run")["Maris_Spindle"] or self.vis("sea", "run")["Maris_WandStar"])
        self.assertTrue(self.vis("sea", "idle")["Maris_Spindle"])

    def test_ninja_hides_hair(self):
        v = self.vis("ninja", "ninja_idle")
        self.assertFalse(v["Maris_Hair"])
        self.assertTrue(v["Maris_NinjaHood"])


class Seats(unittest.TestCase):
    def test_seat_names(self):
        for name in ("Chair", "OfficeChair.001", "Bench", "ParkBench", "Sofa", "Stool", "Benches"):
            self.assertTrue(show.is_seat_name(name), name)
        for name in ("ChairLeg", "BenchBack", "Table", "Lamp", "Cube", ""):
            self.assertFalse(show.is_seat_name(name), name)

    def test_faces_away_from_the_back(self):
        sides = [((0.2, 0), 0.45), ((-0.2, 0), 0.45), ((0, 0.2), 0.95), ((0, -0.2), 0.45)]
        self.assertEqual(show.seat_facing(0.45, sides, 0.45), (0.0, -1.0))
        flat = [((0.2, 0), 0.45), ((-0.2, 0), 0.44), ((0, 0.2), None), ((0, -0.2), 0.45)]
        self.assertIsNone(show.seat_facing(0.45, flat, 0.45))

    def test_seat_scale(self):
        h = 1.0
        self.assertAlmostEqual(show.seat_scale(SPEC, SPEC["sitting"]["seat_height"], h), 1.0)
        self.assertIsNone(show.seat_scale(SPEC, 0.01, h))       # a rug is no seat
        self.assertIsNone(show.seat_scale(SPEC, 5.0, h))        # nor a wall

    def test_yaw_turns_her_front(self):
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0), (0.6, 0.8)):
            yaw = show.yaw_to(dx, dy)
            front = (math.sin(yaw), -math.cos(yaw))              # -Y turned by yaw about z
            self.assertAlmostEqual(front[0], dx, places=6)
            self.assertAlmostEqual(front[1], dy, places=6)


class Dash(unittest.TestCase):
    def test_free_spot_clears_things(self):
        b = box(-1, -1, 1, 1)
        x, y, _ = show.free_spot((0.2, 0.1, 0), 1.0, [b])
        self.assertFalse(show._overlaps((x, y), show.FOOT, b))
        self.assertEqual(show.free_spot((5, 5, 0), 1.0, [b]), (5, 5, 0))
        floor = ((-10, -10, 0), (10, 10, 0.01))
        self.assertEqual(show.free_spot((0.0, 0.0, 0), 1.0, [floor]), (0.0, 0.0, 0))

    def test_route_reaches_the_goal_and_handles_things(self):
        wall = box(2, -3, 2.4, 3, h=2.0)
        brick = box(4.8, -0.2, 5.2, 0.2, h=0.15)
        seen = set()
        for seed in range(40):
            steps = show.dash_route((0, 0), (8, 0), [wall, brick], 1.0, random.Random(seed))
            last = steps[-1]
            self.assertEqual(last[0], "run")
            self.assertAlmostEqual(math.dist(last[2], (8, 0)), 0.0)
            kinds = [s[0] for s in steps]
            seen |= set(kinds)
            if "crash" in kinds:
                self.assertIn("run", kinds[kinds.index("crash") + 1:])
            for s in steps:
                if s[0] == "run":                   # running legs never cross the wall
                    self.assertIsNone(show._crossing(s[1], s[2], wall, 0.0) if
                                      not show._overlaps(s[1], 0.01, wall) and
                                      not show._overlaps(s[2], 0.01, wall) else None)
        self.assertTrue({"trip", "crash", "phase", "run"} <= seen, seen)

    def test_hurry_phases_straight(self):
        wall = box(2, -3, 2.4, 3, h=2.0)
        steps = show.dash_route((0, 0), (8, 0), [wall], 1.0, random.Random(1), hurry=True)
        self.assertEqual([s[0] for s in steps], ["run", "phase", "run"])

    def test_times_and_sizes(self):
        self.assertEqual(show.carry_speedup(0), 1.0)
        self.assertEqual(show.carry_speedup(100), 4.0)
        self.assertEqual(show.hold_scale(0.2, 1.0), 1.0)          # small parts keep their size
        self.assertAlmostEqual(show.hold_scale(6.0, 1.0), 0.1)    # a big one shrinks to 0.6 of her
        self.assertLess(show.step_time(("run", (0, 0), (4, 0)), 1.0, 4.0),
                        show.step_time(("run", (0, 0), (4, 0)), 1.0, 1.0))
        rng = random.Random(3)
        for _ in range(20):
            p = show.pop_spot((0, 0, 0), 1.0, (0, -10, 2), rng)
            d = math.dist(p[:2], (0, 0))
            self.assertTrue(2.5 <= d <= 4.0)
            self.assertLess(p[1], 0.5)                         # on the camera's side


if __name__ == "__main__":
    unittest.main()
