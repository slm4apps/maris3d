# SPDX-License-Identifier: Apache-2.0
import unittest

from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Executor, Session


class SceneExec(Executor):
    def __init__(self, objs):
        self.objs = objs

    def reset(self):
        pass

    def run_call(self, call):
        return True, None

    def objects(self):
        return list(self.objs)


SCENE = [
    {"name": "House", "type": "EMPTY"},
    {"name": "Band", "type": "MESH", "parent": "House"},
    {"name": "Door", "type": "MESH", "parent": "House"},
    {"name": "Chair", "type": "EMPTY"},
    {"name": "Seat", "type": "MESH", "parent": "Chair"},
    {"name": "Legs", "type": "MESH", "parent": "Chair"},
    {"name": "Camera", "type": "CAMERA"},
    {"name": "LampPost", "type": "MESH"},
    {"name": "Car", "type": "MESH"},
    {"name": "RoofA", "type": "MESH", "parent": "House"},
    {"name": "RoofB", "type": "MESH", "parent": "House"},
    {"name": "HouseWindow1", "type": "MESH", "parent": "House"},
]


def guard(request, calls):
    return Copilot(None, Session(SceneExec(SCENE)))._edit_guard(request, calls)


class EditGuardTests(unittest.TestCase):
    def test_paint_all_is_narrowed_to_the_named_object(self):
        out, off = guard("Make Band red.", [{"tool": "set_material", "object": "all", "name": "Red"}])
        self.assertEqual(off, 0)
        self.assertEqual(out, [{"tool": "set_material", "name": "Red", "objects": ["Band"]}])

    def test_paint_all_on_a_group_goes_to_its_parts(self):
        out, _ = guard("make the chair red", [{"tool": "set_material", "object": "all", "name": "Red"}])
        self.assertEqual(out[0]["objects"], ["Legs", "Seat"])

    def test_a_part_is_named_by_its_main_word(self):
        out, _ = guard("Make the roof red.", [{"tool": "set_material", "object": "all", "name": "Red"}])
        self.assertEqual(out[0]["objects"], ["RoofA", "RoofB"])
        out, _ = guard("paint the windows white", [{"tool": "set_material", "object": "all", "name": "White"}])
        self.assertEqual(out[0]["objects"], ["HouseWindow1"])

    def test_edits_on_things_not_named_are_dropped(self):
        calls = [{"tool": "set_material", "object": "Band", "name": "Red"},
                 {"tool": "set_transform", "object": "Camera", "location": [1, 2, 3]},
                 {"tool": "set_transform", "object": "LampPost", "location": [7.36, -6.93, 4.96]},
                 {"tool": "set_object", "object": "Car"},
                 {"tool": "duplicate", "object": "Band"}]
        out, off = guard("Make Band red.", calls)
        self.assertEqual(off, 3)
        self.assertEqual([c["object"] for c in out], ["Band", "Band"])

    def test_parts_of_a_named_group_may_be_edited(self):
        out, off = guard("move the house left", [{"tool": "set_transform", "object": "Door", "location": [0, 0, 0]}])
        self.assertEqual((len(out), off), (1, 0))

    def test_objects_list_is_trimmed(self):
        out, off = guard("paint the chair blue",
                         [{"tool": "set_material", "objects": ["Seat", "Car"], "name": "Blue"}])
        self.assertEqual(out[0]["objects"], ["Seat"])
        self.assertEqual(off, 0)

    def test_new_objects_and_other_tools_pass(self):
        calls = [{"tool": "add_primitive", "shape": "cube", "name": "Box"},
                 {"tool": "set_material", "object": "Box", "name": "Red"},
                 {"tool": "add_light", "kind": "AREA"}]
        out, off = guard("put a red box on the Car", calls)
        self.assertEqual((out, off), (calls, 0))

    def test_sentence_naming_nothing_keeps_off_camera_and_lights(self):
        paint = {"tool": "set_material", "object": "all", "name": "Red"}
        cam = {"tool": "set_transform", "object": "Camera", "location": [0, 0, 0]}
        self.assertEqual(guard("make it all red", [paint, cam]), ([paint], 1))
        self.assertEqual(guard("point the camera down", [cam]), ([cam], 0))

    def test_name_inside_another_word_does_not_count(self):
        # "Car" inside "cards", "Door" inside "doorway" are not names in the sentence
        calls = [{"tool": "set_transform", "object": "LampPost", "location": [0, 0, 0]}]
        self.assertEqual(guard("stack the cards by the doorway", calls), (calls, 0))


if __name__ == "__main__":
    unittest.main()
