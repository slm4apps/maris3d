# SPDX-License-Identifier: Apache-2.0
"""Motion by code (copilot/animate.py): the sentence is read, keyframes are written, no model."""
import unittest

from maris3d.copilot import animate as A
from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Session

from tests.test_apply_change import Sim
from tests.test_change_words import Runtime


class Read(unittest.TestCase):
    def test_kinds_nouns_and_seconds(self):
        cases = {
            "take a cube and move it over to the other side of the scene in one second": [("move", "cube", 1.0)],
            "a red ball bouncing twice over two seconds": [("bounce", "ball", 2.0)],
            "spin it once around over one second": [("spin", "", 1.0)],
            "a moon going round a planet once, the planet stays still": [("orbit", "moon", 2.0)],
            "a robot waving its arm up and down": [("swing", "arm", 2.0)],
            "three fan blades parented to a central empty, then spin the empty one full turn": [("spin", "empty", 2.0)],
        }
        for text, want in cases.items():
            self.assertEqual([(m.kind, m.noun, m.seconds) for m in A.parse(text)], want, text)

    def test_poses_and_plain_edits_are_not_motion(self):
        for text in ("turn it 90 degrees", "rotate the cube by 45 degrees", "make the chair red",
                     "move the bench next to the station", "put a lamp on the desk"):
            self.assertEqual(A.parse(text), [], text)

    def test_orbit_circles_the_centre(self):
        objects = [{"name": "Planet", "type": "MESH", "loc": [0, 0, 1], "dims": [2, 2, 2]},
                   {"name": "Moon", "type": "MESH", "loc": [4, 0, 1], "dims": [0.5, 0.5, 0.5]}]
        calls, notes, missing = A.plan_calls(A.parse("a moon going round a planet once"), objects)
        keys = [c for c in calls if c["tool"] == "keyframe"]
        self.assertTrue(keys and all(c["object"] == "Moon" for c in keys))
        self.assertEqual(missing, [])
        xs = [c["value"][0] for c in keys]
        self.assertLess(min(xs), -3)                    # it goes to the far side
        self.assertEqual(calls[-1]["tool"], "set_frame_end")


class InTheCopilot(unittest.TestCase):
    def test_spin_it_on_a_built_thing_needs_no_model(self):
        sim = Sim()
        cop = Copilot(Runtime([]), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        result = cop.run_auto("spin it once around over one second")
        self.assertEqual(result.mode, "animate")
        keys = [c for c in result.calls if c["tool"] == "keyframe"]
        self.assertEqual({c["property"] for c in keys}, {"rotation_deg"})
        self.assertEqual(keys[-1]["value"][2] - keys[0]["value"][2], 360.0)
        self.assertEqual(cop.runtime.asked, [])

    def test_a_follow_up_about_a_missing_part_goes_on(self):
        sim = Sim()
        cop = Copilot(Runtime([]), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        self.assertIsNone(cop.run_animate("make its tail wag", A.parse("make the flag wave")))

    def test_a_new_thing_with_a_motion_after_other_builds_is_built_and_animated(self):
        sim = Sim()
        cop = Copilot(Runtime([]), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        result = cop.run_animate("a ball bouncing twice", A.parse("a ball bouncing twice"))
        self.assertIsNotNone(result)
        keys = [c for c in result.calls if c["tool"] == "keyframe"]
        self.assertTrue(keys and all("ball" in c["object"].lower() for c in keys))

    def test_introduces_reads_the_article(self):
        self.assertTrue(A.introduces("a ball bouncing twice", ["ball"]))
        self.assertTrue(A.introduces("two red wheels spinning", ["wheel"]))
        self.assertFalse(A.introduces("make the flag wave", ["flag"]))
        self.assertFalse(A.introduces("spin it", []))
