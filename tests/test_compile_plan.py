# SPDX-License-Identifier: Apache-2.0
"""The plan -> build step: layout by words, exact instructions, checks, and the placer for moves.

No Blender and no model: a tiny executor keeps objects as dicts, and the "model" is a function
that either answers every instruction exactly, answers nothing, or answers wrongly -- the three
cases the step has to count honestly.
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from maris3d.copilot import compile_plan as CP  # noqa: E402
from maris3d.copilot.loop import Copilot  # noqa: E402
from maris3d.copilot.session import Session  # noqa: E402

STATION = [
    {"id": "platform_1", "recipe": "platform"},
    {"id": "station_1", "recipe": "station_building",
     "place": {"anchor": "platform_1", "relation": "behind", "distance": "small"}},
    {"id": "bench_1", "recipe": "bench", "count": 2,
     "place": {"anchor": "platform_1", "relation": "on_top_of", "distance": "touching"}},
]


class FakeExecutor:
    """Objects as dicts; just enough of the tools the step uses."""

    def __init__(self):
        self.objs = {}

    def reset(self):
        self.objs = {}

    def objects(self):
        return [dict(o) for o in self.objs.values()]

    def run_call(self, call):
        tool = call.get("tool")
        if tool == "add_primitive":
            if "scale" in call:
                dims = [2.0 * v for v in call["scale"]]
            elif "radius" in call:
                dims = [2.0 * call["radius"], 2.0 * call["radius"], call.get("depth", 2.0)]
            else:
                dims = [2.0, 2.0, 2.0]
            name = call.get("name") or f"Cube{len(self.objs)}"
            self.objs[name] = {"name": name, "type": "MESH", "loc": list(call.get("location", [0, 0, 0])),
                               "dims": dims}
        elif tool == "add_empty":
            self.objs[call["name"]] = {"name": call["name"], "type": "EMPTY",
                                       "loc": list(call.get("location", [0, 0, 0])), "dims": [0, 0, 0],
                                       "children": []}
        elif tool == "parent":
            self.objs[call["parent"]]["children"].append(call["child"])
            self.objs[call["child"]]["parent"] = call["parent"]
        elif tool == "set_transform":
            o = self.objs.get(call["object"])
            if o is None:
                return False, "no such object"
            if "location" in call:
                delta = [call["location"][i] - o["loc"][i] for i in range(3)]
                o["loc"] = list(call["location"])
                for child in o.get("children", []):          # children follow their parent
                    c = self.objs[child]
                    c["loc"] = [c["loc"][i] + delta[i] for i in range(3)]
            if "scale" in call:
                o["dims"] = [o["dims"][i] * call["scale"][i] for i in range(3)]
        return True, None


SENTENCE = re.compile(r"Add an? (cube|ico sphere|plane|cylinder|cone|torus) named (\S+) at "
                      r"(-?[\d.]+), (-?[\d.]+), (-?[\d.]+) with (.*?)\.(?= Add|$)")


def exact_calls(text):
    calls = []
    for shape, name, x, y, z, rest in SENTENCE.findall(text):
        call = {"tool": "add_primitive", "shape": shape.split()[0], "name": name,
                "location": [float(x), float(y), float(z)]}
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", rest)]
        if "scale" in rest:
            call["scale"] = nums[:3]
        elif "radius" in rest and "depth" in rest:
            call["radius"], call["depth"] = nums[0], nums[1]
        calls.append(call)
    return calls


class Runtime:
    """behaviour: 'exact' answers every instruction, 'silent' answers nothing, 'lazy' drops the place."""
    planner_id = None

    def __init__(self, behaviour="exact"):
        self.behaviour, self.asked = behaviour, []

    def chat(self, messages, names, lora_scale=0.0, max_tokens=0, **_kw):
        if messages[-1]["role"] != "user":                 # after the tool results: nothing more to add
            return {"content": "done"}
        self.asked.append(messages[-1]["content"])
        calls = exact_calls(messages[-1]["content"]) if self.behaviour != "silent" else []
        if self.behaviour == "extra":                      # one nobody asked for, one twice, a repaint
            calls = calls + [{"tool": "add_primitive", "shape": "ico_sphere", "name": "Extra9"},
                             dict(calls[0]), {"tool": "set_material", "object": "all", "color": [0.5, 0.5, 0.5]}]
        if self.behaviour == "lazy":
            calls = [{k: v for k, v in c.items() if k != "location"} for c in calls]
        return {"content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function",
             "function": {"name": c["tool"], "arguments": {k: v for k, v in c.items() if k != "tool"}}}
            for i, c in enumerate(calls)]}


def run(behaviour, items=STATION):
    ex = FakeExecutor()
    session = Session(ex)
    runtime = Runtime(behaviour)
    result = Copilot(runtime, session).run_items(items)
    return result, ex, session, runtime


class Layout(unittest.TestCase):
    def test_words_become_places_and_nothing_stacks(self):
        instances, notes = CP.layout(STATION)
        self.assertEqual(notes, [])
        self.assertEqual([i["id"] for i in instances], ["Platform", "StationBuilding", "Bench", "Bench2"])
        by = {i["id"]: i for i in instances}
        self.assertEqual(by["Platform"]["origin"], [0.0, 0.0, 0.0])
        self.assertGreater(by["StationBuilding"]["origin"][1], 2.0)          # behind = +y, clear of it
        self.assertAlmostEqual(by["Bench"]["origin"][2], 0.315, places=3)    # standing ON the platform
        self.assertLess(by["Bench"]["origin"][0], 0)                         # spread along it,
        self.assertGreater(by["Bench2"]["origin"][0], 0)                     # not on one spot
        self.assertEqual({p["name"] for p in by["Bench2"]["parts"]},
                         {"BenchSeat2", "BenchBack2", "BenchLegL2", "BenchLegR2"})

    def test_a_thing_listed_before_its_anchor_still_stands_by_it(self):
        plan = [{"id": "car_1", "recipe": "car",
                 "place": {"anchor": "station_building_1", "relation": "behind", "distance": "small"}},
                {"id": "station_building_1", "recipe": "station_building"}]
        instances, notes = CP.layout(plan)
        car = next(i for i in instances if i["id"] == "Car")
        station = next(i for i in instances if i["id"] == "StationBuilding")
        self.assertEqual(notes, [])
        self.assertEqual((car["anchor"], car["relation"]), ("StationBuilding", "behind"))
        self.assertGreater(car["origin"][1] - car["size"][1] / 2, station["origin"][1] + station["size"][1] / 2)
        circle = [{"id": "a_1", "recipe": "car", "place": {"anchor": "b_1", "relation": "behind"}},
                  {"id": "b_1", "recipe": "bench", "place": {"anchor": "a_1", "relation": "behind"}}]
        self.assertEqual(len(CP.layout(circle)[0]), 2)                 # a circle does not hang

    def test_an_unknown_recipe_is_reported_not_guessed(self):
        instances, notes = CP.layout([{"recipe": "spaceship"}])
        self.assertEqual(instances, [])
        self.assertIn("spaceship", notes[0])

    def test_planner_words_map_onto_the_library(self):
        self.assertEqual(CP.recipe_key("pine"), "tree")
        self.assertEqual(CP.recipe_key("lamp_post"), "lamp_post")
        self.assertIsNone(CP.recipe_key("dragon"))

    def test_a_copied_word_is_still_the_relation(self):
        self.assertEqual(CP.relation_word("rear_of"), "behind")
        self.assertEqual(CP.relation_word("upon"), "on_top_of")
        self.assertEqual(CP.relation_word("left_of"), "left_of")
        self.assertIsNone(CP.relation_word("reel"))
        items = [{"recipe": "platform"}, {"recipe": "bench", "place": {"anchor": "platform_1", "relation": "upon",
                                                                    "distance": "nearish"}}]
        instances, notes = CP.layout(items)
        self.assertEqual(instances[1]["relation"], "on_top_of")
        self.assertEqual(notes, [])

    def test_both_planner_shapes_give_items(self):
        self.assertEqual(len(CP.plan_items({"recipe": "bench", "count": 3, "zone": "platform"})), 1)
        self.assertEqual(len(CP.plan_items({"items": STATION})), 3)
        self.assertEqual(CP.plan_items(None), [])


class Build(unittest.TestCase):
    def test_a_model_that_follows_is_counted_exact(self):
        result, ex, session, runtime = run("exact")
        self.assertEqual(result.built["parts"], 15)
        self.assertEqual(result.built["exact"], 15)
        self.assertEqual(result.built["missing"] + result.built["moved"], 0)
        self.assertEqual(result.built["strays"], [])
        self.assertTrue(all(len(CP.SENTENCE_NAMES(t)) <= CP.CHUNK for t in runtime.asked))
        self.assertIn("Bench2", session.groups)

    def test_a_model_that_says_nothing_still_gets_the_scene_and_it_is_counted(self):
        result, ex, _session, _runtime = run("silent")
        self.assertEqual(result.built["missing"], 15)
        self.assertEqual(result.built["exact"], 0)
        seat = ex.objs["BenchSeat"]
        self.assertAlmostEqual(seat["dims"][0], 1.7, places=3)

    def test_a_part_in_the_wrong_place_is_moved_and_counted(self):
        result, ex, _session, _runtime = run("lazy")
        self.assertEqual(result.built["moved"], 15)
        self.assertEqual(result.built["exact"], 0)
        self.assertGreater(result.built["wrong_place"], 0)      # "lazy" drops the place, not the size:
        self.assertEqual(result.built["wrong_size"], 0)         # the two are counted apart
        want = [i for i in CP.layout(STATION)[0] if i["id"] == "Bench2"][0]
        back = next(p for p in want["parts"] if p["name"] == "BenchBack2")
        self.assertEqual(ex.objs["BenchBack2"]["loc"], CP.part_location(want, back))

    def test_what_was_not_asked_is_not_run(self):
        result, ex, _session, _runtime = run("extra")
        self.assertEqual(result.built["strays"], [])
        self.assertNotIn("Extra9", ex.objs)
        self.assertEqual(result.built["exact"], 15)
        self.assertGreater(result.built["dropped"], 0)
        self.assertFalse(any(c.get("tool") == "set_material" and c.get("object") == "all" for c in result.calls))

    def test_a_part_of_the_wrong_shape_is_not_run_and_the_harness_makes_it(self):
        class Cubes(Runtime):                              # answers every part as a cube
            def chat(self, messages, names, lora_scale=0.0, max_tokens=0, **kw):
                out = Runtime.chat(self, messages, names, lora_scale, max_tokens)
                for call in out.get("tool_calls") or []:
                    args = call["function"]["arguments"]
                    if args.get("shape") != "cube":
                        args["shape"] = "cube"
                return out
        ex = FakeExecutor()
        items = [{"id": "table_1", "recipe": "table"}]     # a table is two cylinders
        result = Copilot(Cubes("exact"), Session(ex)).run_items(items)
        self.assertEqual(result.built["wrong_shape"], 2)
        self.assertEqual((result.built["exact"], result.built["missing"]), (0, 2))
        self.assertEqual(result.built["unfixed"], 0)       # the harness made both, and that was checked
        self.assertIn("TableTop", ex.objs)

    def test_a_second_request_without_a_place_stands_beside_what_is_there(self):
        ex = FakeExecutor()
        session = Session(ex)
        copilot = Copilot(Runtime("exact"), session)
        copilot.run_items([{"id": "chair_1", "recipe": "chair"}])
        result = copilot.run_items([{"id": "table_1", "recipe": "table"}])
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        chair, table = boxes["Chair"], boxes["Table"]
        apart = any(table["lo"][i] >= chair["hi"][i] - 1e-6 or table["hi"][i] <= chair["lo"][i] + 1e-6
                    for i in range(2))
        self.assertTrue(apart, (chair, table))                       # not through the chair
        self.assertAlmostEqual(table["lo"][2], 0.0, places=3)        # and on the floor
        self.assertTrue(any("no place stated" in n for n in result.built["notes"]))

    def test_a_thing_is_found_by_one_word_of_its_name(self):
        ex = FakeExecutor()
        session = Session(ex)
        Copilot(Runtime("exact"), session).run_items([
            {"id": "station_building_1", "recipe": "station_building"},
            {"id": "chair_1", "recipe": "chair", "place": {"anchor": "station_building_1", "relation": "next_to"}}])
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        subject, place = CP.parse_move("put the bus station behind the chair", boxes)
        self.assertEqual((subject, place["anchor"], place["relation"]), ("StationBuilding", "Chair", "behind"))
        self.assertEqual(CP.parse_move("move the station to the north end", boxes)[0], "StationBuilding")
        far = CP.parse_move("shift the station far to the east of the chair", boxes)[1]
        self.assertEqual((far["relation"], far["distance"]), ("right_of", "far"))
        Copilot(Runtime("exact"), session).run_items([{"id": "station_building_2", "recipe": "station_building"}])
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        self.assertIsNone(CP.parse_move("put the bus station behind the chair", boxes))   # two stations: which?

    def test_a_finish_is_ordered_by_words_and_done_by_code(self):
        ex = FakeExecutor()
        session = Session(ex)
        Copilot(Runtime("exact"), session).run_items([{"id": "cat_1", "recipe": "cat"}])
        objects = ex.objects()
        whole = CP.parse_finish("make the cat smooth", objects)
        self.assertEqual(whole[0][0], "smooth")
        self.assertEqual(len(whole[0][1]), 9)                                    # every part of the cat
        mixed = dict(CP.parse_finish("smooth the cat's head and ears but keep the legs sharp", objects))
        self.assertEqual(sorted(mixed["smooth"]), ["CatEar1", "CatEar2", "CatHead"])
        self.assertEqual(sorted(mixed["sharp"]), ["CatLeg1", "CatLeg2", "CatLeg3", "CatLeg4"])
        merged = CP.parse_finish("merge the head and the body of the cat into one", objects)
        self.assertEqual((merged[0][0], sorted(merged[0][1])), ("merge", ["CatBody", "CatHead"]))
        two = CP.parse_finish("merge the body and head of the cat into one and smooth the tail", objects)
        self.assertEqual([(k, sorted(n)) for k, n in two], [("merge", ["CatBody", "CatHead"]), ("smooth", ["CatTail"])])
        self.assertIsNone(CP.parse_finish("a smooth round table next to the cat", []))   # nothing there yet
        self.assertIsNone(CP.parse_finish("add a dog", objects))
        class Never(Runtime):                                                    # no model is asked
            def chat(self, *a, **kw):
                raise AssertionError("a finish order needs no model")
        result = Copilot(Never(), session).run_auto("smooth the cat's head but keep the legs sharp")
        self.assertEqual(result.mode, "finish")
        tools = [(c["tool"], c.get("modifier"), c["object"]) for c in result.calls]
        self.assertIn(("add_modifier", "SUBSURF", "CatHead"), tools)
        self.assertIn(("add_modifier", "BEVEL", "CatHead"), tools)
        self.assertIn(("shade_smooth", None, "CatLeg1"), tools)
        self.assertFalse(any(c.get("modifier") == "SUBSURF" and c["object"].startswith("CatLeg") for c in result.calls))
        skin = Copilot(Never(), session).run_auto("merge the head and the body of the cat")
        self.assertEqual([c["objects"] for c in skin.calls if c["tool"] == "join"], [["CatBody", "CatHead"]])
        self.assertTrue(any(c.get("modifier") == "REMESH" for c in skin.calls))

    def test_the_spec_can_ask_for_a_finish_a_skin_and_a_hollow_part(self):
        from maris3d.copilot import describe_parts as D
        answer = {"object": "cup", "size": [0.08, 0.08, 0.1], "finish": "smooth", "parts": [
            {"name": "CupBody", "shape": "cylinder", "size": [0.08, 0.08, 0.1], "color": "white", "hollow": "open_top"},
            {"name": "CupWater", "shape": "cylinder", "size": [0.058, 0.058, 0.07], "color": "water", "finish": "sharp",
             "place": {"on": "CupBody", "relation": "inside", "align": {"x": "centre", "y": "centre", "z": "centre"}}}]}
        self.assertEqual(D.check_answer(answer)[0], [])
        recipe, why = D.to_recipe(answer)
        self.assertIsNone(why)
        body, water = recipe["parts"]
        self.assertEqual((body.get("hollow"), body.get("finish"), water.get("finish")), ("open_top", "smooth", None))
        self.assertEqual(water["material"]["alpha"], 0.55)                        # water is see-through
        inst, _notes = CP.layout([{"id": "cup_1", "recipe": "cup"}], None, {"cup": recipe})
        calls = CP.finish_calls(inst[0])
        self.assertTrue(any(c["tool"] == "add_modifier" and c["modifier"] == "BOOLEAN" and c["target"] == "CupBodyCut"
                            for c in calls))
        self.assertTrue(any(c["tool"] == "set_object" and c["object"] == "CupBodyCut" and c["hide_render"] for c in calls))
        # a hollowed part is never subdivided (its opening would close): smooth shading only
        self.assertFalse(any(c.get("modifier") == "SUBSURF" for c in calls))
        self.assertTrue(any(c["tool"] == "shade_smooth" and c["object"] == "CupBody" for c in calls))
        bad = dict(answer, finish="shiny")
        self.assertIsNotNone(D.to_recipe(bad)[0])                                 # a wrong finish word costs the finish only
        skinned = {"object": "blob", "size": [0.2, 0.2, 0.3], "parts": [
            {"name": "BlobBody", "shape": "ico", "size": [0.2, 0.2, 0.2], "color": "pink", "skin": "body"},
            {"name": "BlobHead", "shape": "ico", "size": [0.12, 0.12, 0.12], "color": "pink", "skin": "body",
             "place": {"on": "BlobBody", "relation": "on_top_of", "align": {"x": "centre", "y": "centre"}, "sunk": "quarter"}},
            {"name": "BlobEye", "shape": "ico", "size": [0.02, 0.02, 0.02], "color": "black",
             "place": {"on": "BlobHead", "relation": "front_of", "align": {"x": "centre", "z": "centre"}, "sunk": "half"}}]}
        recipe, _why = D.to_recipe(skinned)
        inst, _notes = CP.layout([{"id": "blob_1", "recipe": "blob"}], None, {"blob": recipe})
        calls = CP.finish_calls(inst[0])
        self.assertEqual([c["objects"] for c in calls if c["tool"] == "join"], [["BlobBody", "BlobHead"]])   # the eye stays its own piece

    def test_on_the_platform_stands_on_it(self):
        scene = {"Platform": {"lo": [-12, -2, 0], "hi": [12, 2, 0.3]}}
        inst, _notes = CP.layout([{"id": "man_1", "recipe": "man", "count": 1, "zone": "platform"},
                                  {"id": "woman_1", "recipe": "woman", "count": 1, "zone": "platform",
                                   "place": {"anchor": "man_1", "relation": "next_to"}}], scene)
        man, woman = inst
        self.assertAlmostEqual(man["origin"][2], 0.315, places=2)      # on the slab, not in it
        self.assertAlmostEqual(woman["origin"][2], man["origin"][2], places=2)
        self.assertLess(abs(woman["origin"][0] - man["origin"][0]), 1.5)   # beside him, not at the slab's end

    def test_one_request_is_one_undo(self):
        _result, _ex, session, _runtime = run("exact")
        self.assertEqual(len(session.batches), 1)


class Move(unittest.TestCase):
    def setUp(self):
        _r, self.ex, self.session, self.runtime = run("exact")
        self.copilot = Copilot(self.runtime, self.session)

    def test_put_it_behind_moves_the_whole_item(self):
        seat_before = list(self.ex.objs["BenchSeat"]["loc"])
        result = self.copilot.run_move("put the bench behind the station building, close to it")
        self.assertIsNotNone(result)
        self.assertEqual(result.moved["object"], "Bench")
        self.assertEqual(result.moved["place"]["relation"], "behind")
        self.assertEqual(result.moved["place"]["distance"], "small")
        self.assertNotEqual(self.ex.objs["BenchSeat"]["loc"], seat_before)   # the parts came along
        boxes = CP.scene_boxes(self.ex.objects(), self.session.groups)
        self.assertGreater(boxes["Bench"]["lo"][1], boxes["StationBuilding"]["hi"][1])

    def test_a_blocked_place_slides_along_one_axis_only(self):
        from maris3d.copilot import place as PLACE
        anchor = {"lo": [0, 0, 0], "hi": [1, 1, 1]}
        wall = {"lo": [-3, -2, 0], "hi": [-0.2, 2, 3]}                 # where "left of" would be
        res = PLACE.resolve({"relation": "left_of", "distance": "small"}, anchor, [1, 1, 1], obstacles=[wall])
        self.assertAlmostEqual(res["centre"][1], 0.5)                  # not pushed back
        self.assertAlmostEqual(res["centre"][2], 0.5)                  # not lifted
        self.assertLess(res["centre"][0], -3.0)                        # further LEFT, past the wall

    def test_a_long_way_round_loses_to_a_short_step_sideways(self):
        from maris3d.copilot import place as PLACE
        anchor = {"lo": [6, 4.5, 0], "hi": [8, 5.5, 3]}                # a tree beside a long building
        building = {"lo": [-5.6, 2.4, 0], "hi": [5.6, 7.6, 3.6]}
        res = PLACE.resolve({"relation": "left_of", "distance": "small"}, anchor, [1, 1, 2], obstacles=[building])
        self.assertGreater(res["centre"][0], 4.0)                      # still by the tree, not 12 m away
        self.assertAlmostEqual(res["centre"][2], 1.0)                  # on the ground
        self.assertLess(res["pushed"], 4.0)

    def test_next_to_takes_the_free_side(self):
        from maris3d.copilot import place as PLACE
        anchor = {"lo": [-7, 4.5, 0], "hi": [-6.2, 5.5, 2]}            # a snowman at a building's left end
        building = {"lo": [-5.6, 2.4, 0], "hi": [5.6, 7.6, 3.6]}
        res = PLACE.resolve({"relation": "next_to"}, anchor, [0.7, 0.7, 0.5], obstacles=[building])
        self.assertLess(res["centre"][0], -7.0)                        # its left side is free
        self.assertEqual(res["pushed"], 0.0)

    def test_metres_pick_the_distance_word(self):
        result = self.copilot.run_move("move the Bench2 to the left of the bench, 1.5 metres away")
        self.assertEqual(result.moved["place"], {"anchor": "Bench", "relation": "left_of", "distance": "far"})

    def test_a_sentence_that_is_not_a_move_is_left_to_the_model(self):
        self.assertIsNone(self.copilot.run_move("make the bench red"))
        self.assertIsNone(self.copilot.run_move("put a dragon behind the castle"))


class World(unittest.TestCase):
    """The scene as an anchor, and compass words."""

    def setUp(self):
        _r, self.ex, self.session, self.runtime = run("exact")
        self.copilot = Copilot(self.runtime, self.session)

    def boxes(self):
        return CP.scene_boxes(self.ex.objects(), self.session.groups)

    def test_the_north_end_is_beyond_the_last_thing_on_plus_y(self):
        far = max(b["hi"][1] for n, b in self.boxes().items() if not n.startswith("Bench2"))
        result = self.copilot.run_move("put the Bench2 at the north end.")
        self.assertEqual(result.moved["place"]["anchor"], "scene")
        self.assertEqual(result.moved["place"]["relation"], "behind")
        self.assertGreater(self.boxes()["Bench2"]["lo"][1], far)

    def test_each_compass_word_is_its_side(self):
        for word, axis, sign in (("north", 1, 1), ("south", 1, -1), ("east", 0, 1), ("west", 0, -1)):
            self.copilot.run_move(f"move the Bench2 to the {word} of the station building")
            b, st = self.boxes()["Bench2"], self.boxes()["StationBuilding"]
            if sign > 0:
                self.assertGreaterEqual(b["lo"][axis], st["hi"][axis], word)
            else:
                self.assertLessEqual(b["hi"][axis], st["lo"][axis], word)

    def test_the_scene_does_not_count_the_thing_being_moved(self):
        self.copilot.run_move("put the Bench2 at the east end")
        first = self.boxes()["Bench2"]["lo"][0]
        self.copilot.run_move("put the Bench2 at the east end")          # said twice: it stays
        self.assertAlmostEqual(self.boxes()["Bench2"]["lo"][0], first, places=3)

    def test_the_middle_of_the_scene(self):
        result = self.copilot.run_move("place the Bench2 in the middle of the scene")
        self.assertEqual(result.moved["place"], {"anchor": "scene", "relation": "centre_of", "distance": "small"})

    def test_on_the_ground_is_not_read_as_a_side_of_the_scene(self):
        self.assertIsNone(self.copilot.run_move("put the Bench2 on the ground"))
        self.assertIsNone(self.copilot.run_move("put the Bench2 at the north end of the platform"))

    def test_a_plan_item_takes_the_scene_as_anchor(self):
        far = max(b["hi"][1] for b in self.boxes().values())
        instances, notes = CP.layout([{"id": "tree_1", "recipe": "tree",
                                       "place": {"anchor": "scene", "relation": "north_of", "distance": "small"}}],
                                     self.boxes())
        self.assertEqual(notes, [])
        self.assertGreater(instances[0]["origin"][1], far)

    def test_an_empty_scene_is_a_box_at_the_origin(self):
        instances, _n = CP.layout([{"id": "tree_1", "recipe": "tree",
                                    "place": {"anchor": "world", "relation": "centre_of"}}], {})
        self.assertEqual(instances[0]["origin"][:2], [0.0, 0.0])
        self.assertEqual(CP.relation_word("east of"), "right_of")
        self.assertEqual(CP.relation_word("at the south end"), "front_of")

    def test_a_thing_called_ground_wins_over_the_word(self):
        name, _box = CP.find_anchor("ground", {"Ground": {"lo": [0, 0, 0], "hi": [1, 1, 1]}})
        self.assertEqual(name, "Ground")


class PlannerV3(unittest.TestCase):
    """One sentence end to end: the v3 planner's answer is compiled, built and placed."""

    class V3(Runtime):
        planner_id, planner_version = 1, 3

        def __init__(self, answer):
            Runtime.__init__(self, "exact")
            self.answer = answer

        def chat(self, messages, names, lora_scale=0.0, max_tokens=0, planner=False, **kw):
            if planner:
                self.system = messages[0]["content"]
                return {"content": json.dumps(self.answer)}
            return Runtime.chat(self, messages, names, lora_scale, max_tokens)

    def test_one_sentence_builds_the_station(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        session = Session(ex)
        result = Copilot(runtime, session).run_auto("a platform, a station building behind it and two benches on it")
        from maris3d.copilot import plan as PLAN
        self.assertEqual(runtime.system, PLAN.PLANNER_V3_SYSTEM)       # the prompt it was trained on
        self.assertEqual(result.plan, {"items": STATION})
        self.assertEqual(result.built["parts"], 15)
        self.assertEqual(result.built["exact"], 15)

    def test_north_is_marked_once_and_leaves_with_the_first_request(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        session = Session(ex)
        copilot = Copilot(runtime, session)
        copilot.run_auto("a station")
        self.assertEqual(ex.objs["SceneNorth"]["type"], "EMPTY")
        self.assertEqual(len(session.batches), 1)                      # marker + request: one undo
        runtime.answer = {"items": [{"id": "tree_1", "recipe": "tree",
                                     "place": {"anchor": "scene", "relation": "north", "distance": "small"}}]}
        far = max(b["hi"][1] for b in CP.scene_boxes(ex.objects(), session.groups).values())
        result = Copilot(runtime, session).run_auto("a tree at the north end of the scene")
        self.assertEqual(result.built["strays"], [])
        self.assertGreater(ex.objs["Tree"]["loc"][1], far)
        self.assertEqual(sum(1 for n in ex.objs if n.startswith("SceneNorth")), 1)
        copilot.undo()
        copilot.undo()
        self.assertEqual(ex.objs, {})

    def test_a_move_the_planner_read_moves_and_does_not_build(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        session = Session(ex)
        Copilot(runtime, session).run_auto("a station")
        runtime.answer = {"items": [{"id": "bench_1", "recipe": "bench", "count": 1,
                                     "place": {"anchor": "station_building_1", "relation": "rear_of"}}]}
        before = len(ex.objs)
        result = Copilot(runtime, session).run_auto("shift that bench round the back of the station building")
        self.assertEqual(result.mode, "place")
        self.assertEqual(result.moved["place"]["relation"], "behind")   # the copied word, mapped back
        self.assertEqual(len(ex.objs), before)                           # nothing new was built

    def test_an_exact_instruction_is_not_planned(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        Copilot(runtime, Session(ex)).run_auto("Add a cube named TableTop at 1, 2, 0.75 with a scale of 0.6, 0.4, 0.03.")
        self.assertEqual(sorted(ex.objs), ["TableTop"])          # the top, not a whole table

    def test_a_server_without_the_planner_is_left_as_it_was(self):
        runtime = Runtime("exact")                               # planner_id None
        ex = FakeExecutor()
        result = Copilot(runtime, Session(ex)).run_auto("Add a cube named A at 0, 0, 1 with a scale of 1, 1, 1.")
        self.assertIsNone(result.built)
        self.assertEqual(result.mode, "build")

    def test_a_new_session_still_knows_what_was_built(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        Copilot(runtime, Session(ex)).run_auto("a station")
        fresh = Session(ex)                                      # the add-on starts one per request
        self.assertEqual(fresh.groups, {})
        result = Copilot(runtime, fresh).run_move("put the bench behind the station building")
        self.assertEqual(result.moved["object"], "Bench")
        self.assertGreater(ex.objs["BenchSeat"]["loc"][1], 5.0)  # its parts came along

    def test_a_plan_with_coordinates_is_refused(self):
        from maris3d.copilot import plan as PLAN
        self.assertFalse(PLAN.check_items({"items": [{"recipe": "bench", "location": [0, 0, 0]}]})[0])
        self.assertTrue(PLAN.check_items({"items": [{"recipe": "bench"}]})[0])


WINDMILL = {"object": "windmill", "size": [1.2, 1.2, 3.3], "parts": [
    {"name": "MillTower", "shape": "cylinder", "size": [1.2, 1.2, 3.0], "color": "white"},
    {"name": "MillCap", "shape": "cone", "size": [1.2, 1.2, 0.3], "color": "red",
     "place": {"on": "MillTower", "relation": "on_top_of", "align": {"x": "centre", "y": "centre"}}},
    {"name": "MillDoor", "shape": "cube", "size": [0.4, 0.05, 0.8], "color": "oak",
     "place": {"on": "MillTower", "relation": "front_of", "align": {"x": "centre", "z": "bottom"}}}]}


class Designed(unittest.TestCase):
    """"make me a <thing the library does not have>" (R9), and build v2 for compiled chunks (R5)."""

    class Server(PlannerV3.V3):
        def __init__(self, plan, parts=WINDMILL, roles=("parts",)):
            PlannerV3.V3.__init__(self, plan)
            self.parts, self.adapters, self.roles = parts, {r: 2 + i for i, r in enumerate(roles)}, []

        def has_role(self, role):
            return role in self.adapters or role == "planner"

        def chat(self, messages, names, lora_scale=0.0, max_tokens=0, planner=False, role=None, **kw):
            self.roles.append("planner" if planner else role)
            if role == "parts":
                self.parts_ask = [m["content"] for m in messages]
                return {"content": self.parts if isinstance(self.parts, str) else json.dumps(self.parts)}
            return PlannerV3.V3.chat(self, messages, names, lora_scale, max_tokens, planner=planner)

    def auto(self, runtime, sentence):
        ex = FakeExecutor()
        session = Session(ex)
        return Copilot(runtime, session).run_auto(sentence), ex, session

    def test_a_thing_the_library_lacks_is_designed_and_built(self):
        from maris3d.copilot import describe_parts as D
        runtime = self.Server({"items": [{"id": "windmill_1", "recipe": "windmill"}]})
        result, ex, _s = self.auto(runtime, "make me a windmill")
        self.assertEqual(runtime.parts_ask, [D.PARTS_SYSTEM, "make me a windmill"])   # the trained prompt, the user's words
        self.assertEqual(result.built["designed"], ["Windmill"])
        self.assertEqual((result.built["parts"], result.built["exact"], result.built["missing"]), (3, 3, 0))
        self.assertEqual(result.built["strays"], [])
        parts = [{"name": n, "size": o["dims"], "centre": o["loc"]} for n, o in ex.objs.items() if n.startswith("Mill")]
        self.assertEqual(len(parts), 3)
        self.assertEqual(D.floating(parts), [])                                   # it holds together
        self.assertAlmostEqual(min(p["centre"][2] - p["size"][2] / 2 for p in parts), 0.0, places=3)
        self.assertEqual(ex.objs["MillTower"]["parent"], "Windmill")              # one thing to move
        self.assertNotIn("build", runtime.roles)                                  # no build v2 loaded

    def test_a_designed_thing_is_placed_like_a_library_thing(self):
        runtime = self.Server({"items": [
            {"id": "platform_1", "recipe": "platform"},
            {"id": "windmill_1", "recipe": "windmill",
             "place": {"anchor": "platform_1", "relation": "behind", "distance": "small"}}]})
        result, ex, session = self.auto(runtime, "a platform and a windmill behind it")
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        self.assertEqual(result.built["built"], ["Platform", "Windmill"])
        self.assertGreater(boxes["Windmill"]["lo"][1], boxes["Platform"]["hi"][1])
        self.assertEqual(runtime.roles.count("parts"), 1)                         # the library item is not asked

    def test_an_answer_that_cannot_be_built_builds_nothing_of_it(self):
        broken = json.loads(json.dumps(WINDMILL))
        broken["parts"][1]["place"]["on"] = "Nothing"
        for answer in (broken, "a windmill has sails", dict(WINDMILL, parts=[dict(WINDMILL["parts"][0], location=[0, 0, 0],
                                                                         size=[0, 1, 1])])):
            runtime = self.Server({"items": [{"id": "platform_1", "recipe": "platform"},
                                             {"id": "windmill_1", "recipe": "windmill"}]}, parts=answer)
            result, ex, _s = self.auto(runtime, "a platform and a windmill")
            self.assertEqual(result.built["built"], ["Platform"])
            self.assertEqual(result.built["designed"], [])
            self.assertTrue(any("windmill" in n and "cannot be built" in n for n in result.built["notes"]))
            self.assertFalse([n for n in ex.objs if n.startswith("Mill")])

    def test_a_stated_colour_reaches_the_parts_planner(self):
        runtime = self.Server({"items": [{"id": "windmill_1", "recipe": "windmill", "material": "red"}]})
        self.auto(runtime, "make me a small red windmill")
        self.assertEqual(runtime.parts_ask[1], "make me a small red windmill")    # the size word is not lost
        placed = self.Server({"items": [{"id": "platform_1", "recipe": "platform"},
                                        {"id": "windmill_1", "recipe": "windmill", "material": "red"}]})
        self.auto(placed, "a platform and a red windmill")
        self.assertEqual(placed.parts_ask[1], "a red windmill")                   # several things: rebuilt per item

    def test_design_first_asks_the_planner_even_for_a_library_thing(self):
        bench = json.loads(json.dumps(WINDMILL).replace("Mill", "Seat").replace("windmill", "bench"))
        runtime = self.Server({"items": [{"id": "bench_1", "recipe": "bench"}]}, parts=bench)
        ex = FakeExecutor()
        copilot = Copilot(runtime, Session(ex))
        copilot.design_first = True
        result = copilot.run_auto("a bench")
        self.assertEqual(result.built["designed"], ["Bench"])
        self.assertIn("SeatTower", ex.objs)                       # the planner's parts, not the library's
        self.assertNotIn("BenchSeat", ex.objs)
        runtime.parts = "no idea"                                 # a design that cannot be built:
        ex2 = FakeExecutor()
        copilot2 = Copilot(runtime, Session(ex2))
        copilot2.design_first = True
        result = copilot2.run_auto("a bench")
        self.assertEqual(result.built["designed"], [])            # the library's bench is the fallback
        self.assertIn("BenchSeat", ex2.objs)

    def test_a_change_goes_to_the_edit_model_and_builds_nothing(self):
        from maris3d.addon import routing

        class Edits(self.Server):
            def chat(self, messages, names, lora_scale=0.0, max_tokens=0, planner=False, role=None, **kw):
                if not planner and lora_scale == 1.0:
                    if messages[-1]["role"] != "user":
                        return {"content": "done"}
                    self.edit_ask = messages[-1]["content"]
                    return {"content": "", "tool_calls": [{"id": "e0", "type": "function", "function": {
                        "name": "set_material", "arguments": {"object": "Chair", "name": "Red", "color": [1, 0, 0]}}}]}
                return self.Server_chat(messages, names, lora_scale, max_tokens, planner=planner, role=role)
        Edits.Server_chat = self.Server.chat

        class Paints(FakeExecutor):
            def run_call(self, call):
                if call.get("tool") == "set_material":
                    for name in call.get("objects") or [call.get("object")]:
                        if name in self.objs and self.objs[name]["type"] == "MESH":
                            self.objs[name]["material"] = call.get("name")
                    return True, None
                return FakeExecutor.run_call(self, call)

        router = lambda req, objs, _turn: routing.resolve(req, bool(objs), "AUTO")
        ex = Paints()
        runtime = Edits({"items": [{"id": "chair_1", "recipe": "chair"}]})
        Copilot(runtime, Session(ex), router=router).run_auto("build me a chair")
        count = len(ex.objs)
        runtime.roles = []
        result = Copilot(runtime, Session(ex), router=router).run_auto("make the chair red")   # a new copilot, as the panel
        self.assertEqual(result.mode, "edit")
        self.assertNotIn("planner", runtime.roles)                    # the planner was not asked
        self.assertEqual(len(ex.objs), count)                         # and no second chair
        self.assertIn("[Scene objects: ", runtime.edit_ask)           # the edit model is told the scene,
        self.assertIn("Chair (group, 6 parts)", runtime.edit_ask)     # one line per built thing
        self.assertNotIn("ChairSeat", runtime.edit_ask)
        self.assertEqual({ex.objs[n].get("material") for n in ex.objs if n.startswith("Chair") and n != "Chair"},
                         {"Red"})                                     # painting the group paints its parts

    def test_without_the_parts_adapter_nothing_is_asked(self):
        runtime = self.Server({"items": [{"id": "platform_1", "recipe": "platform"},
                                         {"id": "windmill_1", "recipe": "windmill"}]}, roles=())
        result, _ex, _s = self.auto(runtime, "a platform and a windmill")
        self.assertNotIn("parts", runtime.roles)
        self.assertEqual(result.built["built"], ["Platform"])

    def test_build_v2_answers_compiled_chunks_and_only_those(self):
        runtime = self.Server({"items": STATION}, roles=("build",))
        ex = FakeExecutor()
        copilot = Copilot(runtime, Session(ex))
        copilot.run_auto("a platform, a station building behind it and two benches on it")
        self.assertEqual(set(runtime.roles), {"planner", "build"})
        runtime.roles.clear()
        copilot.run("add a red cube", mode="build")                               # a normal Build: the base
        self.assertEqual(set(runtime.roles), {None})

    def test_compiled_chunks_can_be_sent_to_the_edit_adapter(self):
        scales = []

        class Recording(Runtime):
            def chat(self, messages, names, lora_scale=0.0, max_tokens=0, **kw):
                scales.append(lora_scale)
                return Runtime.chat(self, messages, names, lora_scale, max_tokens)

        for want in (0.0, 1.0):
            scales.clear()
            copilot = Copilot(Recording("exact"), Session(FakeExecutor()))
            copilot.chunk_scale = want
            result = copilot.run_items(STATION)
            self.assertEqual(set(scales), {want})
            self.assertEqual(result.built["exact"], 15)

    def test_the_server_is_told_one_adapter_per_turn(self):
        from maris3d.runtimes.llama_server import LlamaServer
        from maris3d.addon import client
        loaded = [{"id": 0, "path": "/m/maris3d-slm-blender-parts-v1-lora-f16.gguf"},
                  {"id": 1, "path": "/m/maris3d-slm-blender-0.5b-edit-lora-f16.gguf"},
                  {"id": 2, "path": "/m/maris3d-slm-blender-planner-v31-lora-f16.gguf"},
                  {"id": 3, "path": "/m/maris3d-slm-blender-0.5b-build-v2-lora-f16.gguf"}]
        self.assertEqual(client.adapter_ids(loaded), (1, 2))                      # by name, not by position
        self.assertEqual(client.adapter_roles(loaded), {"parts": 0, "build": 3})
        self.assertEqual(client.planner_version(loaded), 3)
        server = LlamaServer(adapter_id=1, planner_id=2)
        server.adapters = {"parts": 0, "build": 3}
        scales = lambda **kw: {a["id"]: a["scale"] for a in server.body([], [], 0.7, 10, **kw)["lora"]}
        self.assertEqual(scales(), {1: 0.7, 2: 0.0, 0: 0.0, 3: 0.0})              # an edit turn
        self.assertEqual(scales(planner=True), {1: 0.0, 2: 1.0, 0: 0.0, 3: 0.0})
        self.assertEqual(scales(role="parts"), {1: 0.0, 2: 0.0, 0: 1.0, 3: 0.0})
        self.assertEqual(scales(role="build"), {1: 0.0, 2: 0.0, 0: 0.0, 3: 1.0})
        plain = LlamaServer(adapter_id=0, planner_id=1)                           # today's two-adapter server
        self.assertEqual(plain.body([], [], 0.0, 10, planner=True)["lora"],
                         [{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}])


if __name__ == "__main__":
    unittest.main()
