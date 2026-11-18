"""The camera tie-in for the show: the framing never chases Maris or a
message, Maris lands where the camera sees it, and messages sit above her, toward the view."""
import math
import unittest

from maris3d.copilot import framing as F

BOX = ((-2.0, -1.0, 0.0), (2.0, 1.0, 1.5))          # a 4 x 2 m scene on the ground


def _angle_deg(eye, centre, point):
    """Horizontal angle at the eye between the view's centre line and the point."""
    a = math.atan2(centre[1] - eye[1], centre[0] - eye[0])
    b = math.atan2(point[1] - eye[1], point[0] - eye[0])
    return abs((math.degrees(b - a) + 180.0) % 360.0 - 180.0)


def _right_of_view(eye, centre, point):
    """> 0 when the point is on the right of the eye's view toward the centre."""
    dx, dy = centre[0] - eye[0], centre[1] - eye[1]
    px, py = point[0] - eye[0], point[1] - eye[1]
    return dx * py - dy * px < 0


class FramingSkipsTheShow(unittest.TestCase):
    def test_the_camera_never_frames_the_maris_or_a_message(self):
        boxes = [("Maris_Rig", ((3, 0, 0), (3.3, 0.3, 0.6))), ("msg_say_1", ((3, 0, 1), (4, 0.1, 1.2))),
                 ("Table", ((0, 0, 0), (1, 1, 0.8)))]
        self.assertEqual([n for n, _b in F.follow_boxes(boxes)], ["Table"])

    def test_a_scene_of_only_show_objects_frames_nothing(self):
        boxes = [("Maris_Body", ((0, 0, 0), (0.3, 0.3, 0.6))), ("msg_hello_2", ((0, 0, 1), (1, 0.1, 1.2)))]
        self.assertEqual(F.follow_boxes(boxes), [])


class MarisLandsInView(unittest.TestCase):
    def test_without_a_view_she_stands_at_the_front_right_corner(self):
        spot = F.landing_spot(BOX, None, 0.5)
        self.assertAlmostEqual(spot[0], 2.0 + 0.5 * F.LAND_GAP)
        self.assertAlmostEqual(spot[1], -1.0)
        self.assertEqual(spot[2], 0.0)

    def test_she_lands_on_the_ground_beside_the_scene_on_the_cameras_right_and_in_frame(self):
        centre = (0.0, 0.0, 0.75)
        for deg in (270, 300, 0, 45, 135, 200):            # the camera all round the scene
            a = math.radians(deg)
            eye = (12 * math.cos(a), 12 * math.sin(a), 5.0)
            spot = F.landing_spot(BOX, eye, 0.5)
            with self.subTest(camera_deg=deg):
                self.assertEqual(spot[2], 0.0)
                self.assertFalse(F.inside_box(spot, BOX, margin=0.0), spot)
                self.assertTrue(_right_of_view(eye, centre, spot), spot)
                self.assertLessEqual(_angle_deg(eye, centre, spot), F.FRAME_HALF_DEG + 1e-6)

    def test_a_close_camera_pulls_her_in_rather_than_out_of_frame(self):
        eye = (0.0, -4.0, 2.0)                             # close: the scene's right edge is near the frame edge
        spot = F.landing_spot(BOX, eye, 0.5)
        self.assertLessEqual(_angle_deg(eye, (0, 0, 0.75), spot), F.FRAME_HALF_DEG + 1e-6)
        self.assertEqual(spot[2], 0.0)


class MessagesSitAboveHer(unittest.TestCase):
    def test_lines_stack_upward_above_her_head(self):
        a = F.message_spot((1.0, 0.0, 0.0), 0.5, None, 0)
        b = F.message_spot((1.0, 0.0, 0.0), 0.5, None, 1)
        self.assertEqual(a, (1.0, 0.0, 0.5 * 1.15))
        self.assertAlmostEqual(b[2] - a[2], 0.5 * 0.25)

    def test_a_line_leans_toward_the_camera_so_she_does_not_hide_it(self):
        spot = F.message_spot((0.0, 0.0, 0.0), 1.0, (0.0, -10.0, 3.0), 0)
        self.assertLess(spot[1], 0.0)                      # moved toward the eye
        self.assertAlmostEqual(math.hypot(spot[0], spot[1]), F.MSG_LEAN * 1.0)


if __name__ == "__main__":
    unittest.main()
