"""The shipped camera modes, and the standalone copy the take driver falls back to.

Every rule here is a defect found in the Christmas street demo scene, so the test names say
what went wrong on screen, not what the code does.
"""
import ast
import math

import os
import unittest

from maris3d.copilot import framing


def test_a_chair_is_not_a_plane_with_legs():
    # from above (the old "room" rule) a chair is just a plane with legs
    m = framing.mode_for("ChairSeat")
    assert m["name"] == "furniture"
    assert m["pitch"] >= 75.0


def test_a_cabin_is_a_building_not_a_kitchen_cabinet():
    # "cabin" contains "cab": the cabinet rule swallowed the Cabin at 86 degrees and 2.6 m, and
    # the house presentation never ran for it
    assert framing.mode_for("Cabin")["name"] == "building"
    assert framing.mode_for("CabinBody")["name"] == "building"
    assert framing.mode_for("Cabinet")["name"] == "wall"
    assert framing.mode_for("CabL")["name"] == "wall"


def test_a_mantelpiece_is_not_a_man():
    # FireMantel contains "man", so the people rule must anchor on the start of the name
    assert framing.mode_for("FireMantel")["name"] == "default"
    assert framing.mode_for("Man")["name"] == "people"
    assert framing.mode_for("WomanWinter")["name"] == "people"


def test_a_swing_is_framed_as_one_structure():
    # a swing is a frame plus two hangers plus a seat; framed like a generic prop the seat fell
    # out of the picture
    for name in ("SwingSeat", "SwingFrame", "SlideRamp", "Sandbox"):
        assert framing.mode_for(name)["name"] == "park", name
    assert framing.mode_for("SwingSeat")["min"] >= 6.0


def test_a_street_lamp_is_not_table_furniture():
    # the lamp is a 3.4 m pole; the furniture distance cropped it to the base
    assert framing.mode_for("LampPole")["name"] == "streetlamp"
    assert framing.mode_for("LampHead")["name"] == "streetlamp"
    # ... but the table lamp parts keep the furniture framing
    assert framing.mode_for("LampShade")["name"] == "furniture"


def test_walls_are_square_on():
    # a wall seen at an angle is a sliver
    m = framing.mode_for("HouseWindow1")
    assert m["name"] == "wall" and m["pitch"] >= 84.0


def test_a_present_is_framed_from_the_road_side():
    m = framing.mode_for("Gift")
    assert m["name"] == "gift" and m.get("street") is True and m["min"] <= 2.0


def test_a_house_keeps_its_roof_line():
    m = framing.mode_for("House")
    assert m["building"] is True and m["pitch"] < 65.0 and m["min"] >= 9.0


def test_every_mode_has_the_settings_a_viewport_needs():
    for mode, _keys, settings, _guards in framing.RULES:
        for key in ("pitch", "context", "min", "sweep", "az"):
            assert key in settings, f"{mode} has no {key}"
        assert 0.0 <= settings["pitch"] <= 90.0, mode


def test_an_unknown_subject_still_gets_a_usable_framing():
    m = framing.mode_for("Widget")
    assert m["name"] == "default" and m["min"] > 0.0
    assert framing.mode_for("")["name"] == "default"


# --- the presentation shot --------------------------------------------------------------------
def _angle_vs_front(eye, aim, front):
    dx, dy = eye[0] - aim[0], eye[1] - aim[1]
    n = math.hypot(dx, dy)
    fx, fy = front
    fn = math.hypot(fx, fy)
    dot = (dx * fx + dy * fy) / (n * fn)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def test_the_zoom_stops_where_front_and_side_are_both_visible():
    # Zooming from front to side needs a stop at an angle where
    # front and side can both be seen
    center, front = (14.5, -1.0, 4.4), (-1.0, 0.0)      # east house facing the road
    eye, aim = framing.present_targets(center, 5.8, front)
    assert 25.0 <= _angle_vs_front(eye, aim, front) <= 45.0
    assert eye[0] < center[0] or abs(eye[0]) < abs(center[0])


def test_the_zoom_never_ends_behind_the_subject():
    # the back is calibrated away, not guessed: the eye is always on the front side
    for front, center in (((-1.0, 0.0), (14.5, -1.0, 4.4)),
                          ((1.0, 0.0), (-9.4, -32.0, 4.4)),
                          ((0.0, 1.0), (0.0, 9.0, 3.0))):
        eye, aim = framing.present_targets(center, 5.0, front)
        dx, dy = eye[0] - aim[0], eye[1] - aim[1]
        assert dx * front[0] + dy * front[1] > 0.2 * math.hypot(dx, dy), front


def test_a_bigger_house_is_framed_from_further_back():
    # different house types get their own distance, not one shared number
    front = (-1.0, 0.0)
    tall = framing.present_targets((14.5, -1.4, 4.0), 6.8, front)
    small = framing.present_targets((14.5, -1.4, 2.0), 3.5, front)
    d_tall = math.dist(tall[0], tall[1])
    d_small = math.dist(small[0], small[1])
    assert d_tall > d_small


def test_the_zoom_starts_from_the_nearest_road_shot():
    # the road section is a dolly: starting 46 m away flew across the whole town in six seconds
    shots = [((0.0, -23.0, 1.7), (0.0, -2.5, 2.2)),
             ((0.0, -46.0, 1.7), (0.0, -2.5, 2.2))]
    near = framing.road_shot(shots, (14.5, -1.0, 4.4))
    assert near[0][1] == -23.0
    assert framing.road_shot([]) is None
    assert framing.road_shot(shots)[0][1] == -46.0


def test_the_presentation_is_slow_enough_to_watch():
    assert framing.PRESENT_REST_S >= 1.0
    assert framing.PRESENT_ZOOM_S >= 4.0
    assert set(framing.PRESENT_PIECES) == {"House", "Townhouse", "Cabin"}


# --- the driver's standalone copy must not drift -----------------------------------------------
def _driver_inline():
    """The take driver's own view_style fallback, loaded without bpy."""
    path = os.environ.get("MARIS3D_TAKE_DRIVER", "")
    if not os.path.exists(path):        # the take driver is not part of the public tree
        raise unittest.SkipTest("no take driver in this tree")
    src = open(path).read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_view_style_inline")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), ns)
    return ns["_view_style_inline"]


DRIVER_NAMES = [
    "Cabin", "CabinBody", "Cabinet", "HouseWindow1", "ChairSeat", "TableTop", "Cup", "Pot",
    "Leaf1", "FireMantel", "Man", "WomanWinter", "Gift", "Mountain", "RoadSnow", "Tree", "Cat",
    "SwingSeat", "SlideRamp", "LampPole", "LampHead", "LampShade", "House", "Townhouse",
    "Shelf", "Widget", "",
]


def test_the_driver_fallback_agrees_with_the_shipped_table():
    # a take on another machine runs gui_driver.py on its own; if the two tables drift, the take
    # frames things the copilot never would
    inline = _driver_inline()
    for name in DRIVER_NAMES:
        theirs = inline(name)
        ours = framing.mode_for(name)
        for key in ("pitch", "context", "min", "sweep", "az", "street", "room", "building"):
            assert theirs.get(key) == ours.get(key), f"{name}: {key} {theirs.get(key)} != {ours.get(key)}"


def test_a_house_level_with_its_neighbour_is_not_shown_from_inside_the_neighbour():
    # On the camera render: the street houses were filmed from inside the hero
    # house. These are the take's own numbers: House authored at (14.5, 0), the nearest pinned road
    # shot at (0, -9.5), the hero house at the head of the street.
    hero = ((0.0, 0.8, 4.64), [8.98, 5.51, 9.46])
    center, front = (14.5, 0.0, 2.0), (-14.5, -9.5)
    old_eye, _ = framing.present_targets(center, 5.58, front)
    assert framing.inside_box(old_eye, hero), "the defect: without avoid the eye is in the hero house"
    eye, aim = framing.present_targets(center, 5.58, front, avoid=[hero])
    assert not framing.inside_box(eye, hero)
    assert eye[1] < -5.0, "the eye is down the street, in front of the house"
    assert 25.0 <= _angle_vs_front(eye, aim, front) <= 45.0


def test_a_house_whose_door_does_not_face_the_road_is_shown_from_its_door_side():
    # On a test take: the house was still shown from the wrong angle. The
    # three street houses are built at (14.5, 0) with the door on the -y wall; the road is at -x.
    # With "front = toward the road shot" the turn left after `avoid` stood at y = +6.5: behind.
    # With front = the door side and `toward` = the road shot, the eye sees the door wall and the
    # road-facing wall. These are the take's own numbers (test_camera_classes.py runs the rows).
    hero = ((0.0, 0.8, 4.64), [8.98, 5.51, 9.46])
    center, door, shot = (14.5, 0.0, 2.0), (0.0, -1.0), (-2.65, -0.9)
    old_eye, _ = framing.present_targets(center, 5.58, (shot[0] - center[0], shot[1] - center[1]), avoid=[hero])
    assert old_eye[1] > 5.0, "the defect: the eye is behind the house"
    eye, aim = framing.present_targets(center, 5.58, door, avoid=[hero], toward=shot)
    assert eye[1] < center[1] - 5.0, "the eye is on the door side"
    assert eye[0] < center[0] - 2.0, "and on the road's side, so the road-facing wall shows too"
    assert not framing.inside_box(eye, hero)


from tests._plain import as_testcase  # noqa: E402

Plain = as_testcase(globals())
