# SPDX-License-Identifier: Apache-2.0
"""Maris's behaviour rules (bpy-free): what she carries or grows in, her size, ground, where carried
parts come from, group moves and turning."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from maris3d.copilot import show  # noqa: E402


class Choice(unittest.TestCase):
    def test_house_block_is_carried(self):
        self.assertEqual(show.carry_choice("MESH", False, False, 2.6, 1.0, 0), "carry")

    def test_small_and_attached_parts_grow_in(self):
        self.assertEqual(show.carry_choice("MESH", False, False, 0.3, 1.0, 0), "grow")      # a bauble
        self.assertEqual(show.carry_choice("MESH", False, False, 1.1, 1.0, 0, attached=True), "grow")

    def test_groups_and_huge_parts_are_watched(self):
        self.assertEqual(show.carry_choice("MESH", True, False, 1.0, 1.0, 0), "watch")
        self.assertEqual(show.carry_choice("MESH", False, False, 12.0, 1.0, 0), "watch")
        self.assertEqual(show.carry_choice("CURVE", False, False, 1.0, 1.0, 0), "watch")

    def test_attached_to_a_wall_but_not_on_top(self):
        wall = ((-2.9, 0.6, 0.0), (-0.3, 2.6, 1.6))
        door = ((-1.5, 0.55, 0.0), (-0.9, 0.61, 1.1))
        roof = ((-3.3, -0.1, 1.6), (0.1, 3.3, 2.5))
        self.assertTrue(show.attached_to(door, [wall], 1.0))
        self.assertFalse(show.attached_to(roof, [wall], 1.0))
        self.assertFalse(show.attached_to(door, [], 1.0))

    def test_grow_scale(self):
        self.assertAlmostEqual(show.grow_scale(0.0), 0.01)
        self.assertAlmostEqual(show.grow_scale(1.0), 1.0)
        self.assertGreater(max(show.grow_scale(x / 20) for x in range(21)), 1.0)   # a little past full


class Ground(unittest.TestCase):
    def test_is_ground(self):
        self.assertTrue(show.is_ground((12, 12, 0.1), 1.0))       # snow disc
        self.assertTrue(show.is_ground((0.8, 4.0, 0.02), 1.0))    # a path
        self.assertFalse(show.is_ground((1.2, 0.4, 0.08), 1.0))   # a bench seat board
        self.assertFalse(show.is_ground((2.6, 2.0, 1.6), 1.0))    # walls

    def test_ground_top(self):
        g = [((-6, -6, -0.1), (6, 6, 0.0)), ((-1.6, -4.2, 0.0), (-0.8, -0.2, 0.02))]
        self.assertAlmostEqual(show.ground_top(g, 0, 0), 0.0)
        self.assertAlmostEqual(show.ground_top(g, -1.2, -2), 0.02)
        self.assertIsNone(show.ground_top(g, 9, 9))


class Size(unittest.TestCase):
    def test_person_sized(self):
        self.assertAlmostEqual(show.person_height(1.6, 1.0), 1.0)    # within a third: keeps
        self.assertAlmostEqual(show.person_height(3.0, 1.0), 1.95)
        self.assertAlmostEqual(show.person_height(20.0, 1.0), 3.0)
        self.assertAlmostEqual(show.person_height(0.0, 1.3), 1.3)    # only ground: keeps


class Rim(unittest.TestCase):
    def test_on_the_edge_toward_the_place(self):
        g = ((-6, -6, -0.1), (6, 6, 0.0))
        x, y, _ = show.rim_spot(g, (3.0, 0.0, 0.0), 1.0)
        self.assertAlmostEqual(math.hypot(x, y), 6.45, places=2)
        self.assertGreater(x, 6.0)

    def test_middle_goes_toward_the_viewer(self):
        g = ((-6, -6, -0.1), (6, 6, 0.0))
        x, y, _ = show.rim_spot(g, (0.1, 0.0, 0.0), 1.0, eye=(0, -20, 5), rng=random.Random(1))
        self.assertLess(y, -4.0)


class Moves(unittest.TestCase):
    def test_moved_groups(self):
        before = {"Ball1": (0, 0, 0.4), "Ball2": (0, 0, 1.0), "Lamp": (3, 3, 0), "Box": (1, 1, 0)}
        after = {"Ball1": (1, -1.3, 0.4), "Ball2": (1, -1.3, 1.0), "Lamp": (3, 3, 0), "Box": (1.1, 1, 0)}
        got = show.moved_groups(before, after, 1.0)
        self.assertEqual(list(got.values()), [["Ball1", "Ball2"]])

    def test_turn_step_short_way(self):
        y = show.turn_step(math.radians(170), math.radians(-170), rate=1.0)
        self.assertAlmostEqual(math.degrees(y) % 360, 190, places=4)


if __name__ == "__main__":
    unittest.main()
