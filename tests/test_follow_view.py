# SPDX-License-Identifier: Apache-2.0
"""Follow the build: the eye the copilot picks can see the subject (pure numbers, no Blender)."""
import math
import unittest

from maris3d.copilot import framing

HERO = ((0.0, 0.8, 4.64), [8.98, 5.51, 9.46])     # the house at the origin of the street


class FollowEye(unittest.TestCase):
    def test_the_whole_box_fits_the_narrow_side_of_the_view(self):
        eye, aim = framing.follow_eye((2.0, 3.0, 1.0), (2.0, 2.0, 2.0), "Crate", tans=(0.36, 0.242))
        dist = math.dist(eye, aim)
        radius = 0.5 * math.sqrt(12.0)
        self.assertEqual(aim, (2.0, 3.0, 1.0))
        self.assertGreaterEqual(dist * 0.242, radius)          # the box's sphere is inside the frame
        self.assertGreater(eye[2], aim[2])                     # never from below

    def test_a_wall_is_seen_nearly_level_and_a_default_subject_from_above(self):
        wall, aim = framing.follow_eye((0, 0, 1), (4, 0.2, 2), "WallBack")
        thing, _ = framing.follow_eye((0, 0, 1), (4, 0.2, 2), "Thing")
        elev = lambda e: math.degrees(math.asin((e[2] - 1) / math.dist(e, aim)))
        self.assertLess(elev(wall), 10.0)
        self.assertGreater(elev(thing), 20.0)


class SightGuard(unittest.TestCase):
    def test_an_eye_in_the_neighbouring_house_is_a_fault(self):
        # measured in the TAKE31 camera render: the Woman on the pavement, shot from the hero's wall
        self.assertTrue(framing.eye_in_building((3.53, -1.82, 1.64), (5.2, -6.6, 0.82), [HERO]))

    def test_a_subject_inside_the_house_may_be_shot_from_inside_it(self):
        self.assertFalse(framing.eye_in_building((2.9, -1.5, 1.6), (-2.0, 0.6, 0.4), [HERO]))

    def test_an_eye_above_the_roof_is_not_in_the_building(self):
        self.assertFalse(framing.eye_in_building((0.0, 0.8, 12.0), (20.0, 0.0, 1.0), [HERO]))

    def test_candidates_keep_the_distance_and_never_repeat_the_rejected_eye(self):
        eye, aim = (3.53, -1.82, 1.64), (5.2, -6.6, 0.82)
        cands = framing.eye_candidates(eye, aim)
        self.assertEqual(len(cands), 47)
        self.assertNotIn(eye, [tuple(round(v, 2) for v in c) for c in cands])
        first = cands[:7]                                   # same height, walked round the subject
        for c in first:
            self.assertAlmostEqual(math.dist(c, aim), math.dist(eye, aim), places=6)

    def test_the_nearest_clear_eye_is_taken_and_the_reason_is_reported(self):
        aim = (5.2, -6.6, 0.82)
        fault = lambda e: "inside-building" if framing.eye_in_building(e, aim, [HERO]) else ""
        eye, why = framing.first_clear_eye((3.53, -1.82, 1.64), aim, fault)
        self.assertEqual(why, "inside-building")
        self.assertFalse(framing.eye_in_building(eye, aim, [HERO]))
        self.assertGreaterEqual(eye[2], 1.2)

    def test_a_good_eye_is_left_alone(self):
        eye, why = framing.first_clear_eye((9.0, -9.0, 2.0), (5.2, -6.6, 0.82), lambda e: "")
        self.assertEqual((eye, why), ((9.0, -9.0, 2.0), ""))

    def test_when_nothing_is_clear_the_asked_for_eye_is_kept_and_it_says_so(self):
        eye, why = framing.first_clear_eye((1.0, 1.0, 1.0), (0.0, 0.0, 0.0), lambda e: "blocked")
        self.assertEqual((eye, why), ((1.0, 1.0, 1.0), "stuck:blocked"))


if __name__ == "__main__":
    unittest.main()


class Glide(unittest.TestCase):
    """The view glides to a new subject instead of jumping."""

    def test_the_ground_and_the_north_marker_are_not_framed(self):
        boxes = [("Ground", ((-50, -50, 0), (50, 50, 0.1))), ("Bench", ((0, 0, 0), (2, 1, 1))),
                 ("SceneNorth", ((0, 0, 0), (0, 0, 0)))]
        self.assertEqual([n for n, _b in framing.follow_boxes(boxes)], ["Bench"])

    def test_a_backdrop_alone_is_still_framed(self):
        boxes = [("Ground", ((-50, -50, 0), (50, 50, 0.1)))]
        self.assertEqual(framing.follow_boxes(boxes), boxes)

    def test_the_glide_starts_and_stops_gently(self):
        self.assertEqual(framing.ease(0.0), 0.0)
        self.assertEqual(framing.ease(1.0), 1.0)
        self.assertEqual(framing.ease(0.5), 0.5)
        self.assertLess(framing.ease(0.1), 0.1)          # slow out of the old view
        self.assertGreater(framing.ease(0.9), 0.9)       # slow into the new one

    def test_a_bigger_move_takes_longer_within_bounds(self):
        short = framing.glide_seconds(6.0, 6.0, 0.5)
        long = framing.glide_seconds(6.0, 6.0, 15.0)
        self.assertLess(short, long)
        self.assertGreaterEqual(short, 0.8)
        self.assertLessEqual(framing.glide_seconds(86.0, 1.5, 80.0), 2.0)

    def test_the_zoom_is_even_in_ratio(self):
        self.assertAlmostEqual(framing.glide_distance(10.0, 1.0, 0.5), math.sqrt(10.0))
