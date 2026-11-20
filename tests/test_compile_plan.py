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


class Never:
    """A server that must not be asked."""
    final_format = True

    def chat(self, *a, **kw):
        raise AssertionError("a model was asked")

    def has_role(self, role):
        return False


class Lazy(FakeExecutor):
    """An executor that drops the place of every part (what a wrong build looks like)."""

    def run_call(self, call):
        if call.get("tool") == "add_primitive":
            call = {k: v for k, v in call.items() if k != "location"}
        return FakeExecutor.run_call(self, call)


def run(executor=None, items=STATION):
    ex = executor if isinstance(executor, FakeExecutor) else FakeExecutor()
    session = Session(ex)
    runtime = Never()
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

    def test_a_part_never_carries_its_things_name(self):
        # a designed thing "Leg" with a part "Leg" must not parent the part to itself
        recipe_place = {"on": "Leg"}
        parts = [{"name": "Leg"}, {"name": "LegB", "place": recipe_place}, {"name": "LegC"}]
        CP.unclash(parts, "Leg")
        self.assertEqual([p["name"] for p in parts], ["LegMain", "LegB", "LegC"])
        self.assertEqual(parts[1]["place"]["on"], "LegMain")
        self.assertEqual(recipe_place, {"on": "Leg"})                        # the recipe's own is untouched
        calls = CP.finish_calls({"id": "Leg", "origin": [0, 0, 0], "parts": [dict(p, dims=[1, 1, 1]) for p in parts]})
        self.assertFalse([c for c in calls if c["tool"] == "parent" and c["child"] == c["parent"]])

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
    def test_the_built_parts_are_counted_exact(self):
        result, ex, session, _rt = run()
        self.assertEqual(result.built["parts"], 14)
        self.assertEqual(result.built["exact"], 14)
        self.assertEqual(result.built["missing"] + result.built["moved"], 0)
        self.assertEqual(result.built["strays"], [])
        self.assertIn("Bench2", session.groups)

    def test_compiled_parts_go_straight_to_blender_and_no_model_is_asked(self):
        # The compiler holds the exact call of every part; no model copies it
        ex = FakeExecutor()
        result = Copilot(Never(), Session(ex)).run_items(STATION)
        self.assertEqual(result.built["by"], "code")
        self.assertEqual((result.built["parts"], result.built["exact"]), (14, 14))
        self.assertEqual((result.built["moved"], result.built["missing"], result.built["unfixed"]), (0, 0, 0))
        self.assertEqual(result.built["strays"], [])
        self.assertEqual(result.errors, [])
        want = [i for i in CP.layout(STATION)[0] if i["id"] == "Bench2"][0]
        back = next(p for p in want["parts"] if p["name"] == "BenchBack2")
        self.assertEqual(ex.objs["BenchBack2"]["loc"], CP.part_location(want, back))

    def test_a_part_in_the_wrong_place_is_moved_and_counted(self):
        result, ex, _session, _rt = run(Lazy())
        self.assertEqual(result.built["moved"], 14)
        self.assertEqual(result.built["exact"], 0)
        self.assertGreater(result.built["wrong_place"], 0)      # the place is dropped, not the size:
        self.assertEqual(result.built["wrong_size"], 0)         # the two are counted apart
        want = [i for i in CP.layout(STATION)[0] if i["id"] == "Bench2"][0]
        back = next(p for p in want["parts"] if p["name"] == "BenchBack2")
        self.assertEqual(ex.objs["BenchBack2"]["loc"], CP.part_location(want, back))

    def test_a_second_request_without_a_place_stands_beside_what_is_there(self):
        ex = FakeExecutor()
        session = Session(ex)
        copilot = Copilot(Never(), session)
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
        Copilot(Never(), session).run_items([
            {"id": "station_building_1", "recipe": "station_building"},
            {"id": "chair_1", "recipe": "chair", "place": {"anchor": "station_building_1", "relation": "next_to"}}])
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        subject, place = CP.parse_move("put the bus station behind the chair", boxes)
        self.assertEqual((subject, place["anchor"], place["relation"]), ("StationBuilding", "Chair", "behind"))
        self.assertEqual(CP.parse_move("move the station to the north end", boxes)[0], "StationBuilding")
        far = CP.parse_move("shift the station far to the east of the chair", boxes)[1]
        self.assertEqual((far["relation"], far["distance"]), ("right_of", "far"))
        Copilot(Never(), session).run_items([{"id": "station_building_2", "recipe": "station_building"}])
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        self.assertIsNone(CP.parse_move("put the bus station behind the chair", boxes))   # two stations: which?

    def test_a_finish_is_ordered_by_words_and_done_by_code(self):
        ex = FakeExecutor()
        session = Session(ex)
        Copilot(Never(), session).run_items([{"id": "cat_1", "recipe": "cat"}])
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
        # the cutter is removed once the cut is applied: no `*Cut` object stays in the scene
        # (otherwise hidden `GiftBox*Cut` objects would be left behind under the item)
        cut_at = next(i for i, c in enumerate(calls) if c["tool"] == "apply_modifier" and c["object"] == "CupBody")
        deletes = [i for i, c in enumerate(calls) if c["tool"] == "delete_object"
                   and "CupBodyCut" in (c.get("objects") or [c.get("object")])]
        self.assertEqual(len(deletes), 1)
        self.assertGreater(deletes[0], cut_at)
        self.assertFalse(any(c["tool"] == "parent" and c["child"] == "CupBodyCut" for c in calls))
        self.assertFalse(any(c["tool"] == "set_object" and c["object"] == "CupBodyCut" for c in calls))
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

    class V3:
        """The one adapter: answers the outline turn with `answer`, records the roles it was asked as."""
        final_format = True

        def __init__(self, answer):
            self.answer, self.roles, self.edit_answer = answer, [], None

        def has_role(self, role):
            return role == "planner" or (role == "edit" and self.edit_answer is not None)

        def chat(self, messages, names, max_tokens=0, role=None):
            self.roles.append(role)
            if role == "edit":
                return {"content": json.dumps(self.edit_answer)}
            self.system = messages[0]["content"]
            return {"content": json.dumps(self.answer)}

    def test_one_sentence_builds_the_station(self):
        runtime = self.V3({"items": STATION})
        ex = FakeExecutor()
        session = Session(ex)
        result = Copilot(runtime, session).run_auto("a platform, a station building behind it and two benches on it")
        from maris3d.copilot import vocabulary as V
        self.assertEqual(runtime.system, V.OUTLINE_SYSTEM)             # the prompt it was trained on
        self.assertEqual([i["id"] for i in result.plan["items"]], [i["id"] for i in STATION])
        self.assertEqual(result.built["parts"], 14)      # the station building has no door
        self.assertEqual(result.built["exact"], 14)

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

    def test_an_exact_instruction_is_read_by_code_no_model_asked(self):
        runtime = self.V3({"items": STATION})
        runtime.edit_answer = {"kind": "question", "say": "Which table?"}
        ex = FakeExecutor()
        result = Copilot(runtime, Session(ex)).run_auto("Add a cube named TableTop at 1, 2, 0.75 with a scale of 0.6, 0.4, 0.03.")
        self.assertEqual(runtime.roles, [])                  # neither the planner nor the edit model
        self.assertEqual(list(ex.objs), ["TableTop"])
        self.assertEqual(result.mode, "change")

    def test_an_exact_sentence_with_more_in_it_still_goes_to_the_edit_model(self):
        runtime = self.V3({"items": STATION})
        runtime.edit_answer = {"kind": "question", "say": "Which table?"}
        ex = FakeExecutor()
        result = Copilot(runtime, Session(ex)).run_auto("Add a cube named TableTop at 1, 2, 0.75 and make it red.")
        self.assertEqual(runtime.roles, ["edit"])
        self.assertEqual(result.text, "Which table?")

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
            self.parts, self.adapters = parts, set(roles)

        def has_role(self, role):
            return role in self.adapters or PlannerV3.V3.has_role(self, role)

        def chat(self, messages, names, max_tokens=0, role=None):
            if role == "parts":
                self.roles.append(role)
                self.parts_ask = [m["content"] for m in messages]
                if isinstance(self.parts, str):
                    return {"content": self.parts}
                # "a platform", "a station building": the stand-in design under the name asked (every
                # thing is designed); anything else gets the design as it is
                ask, text = messages[-1]["content"], json.dumps(self.parts)
                words = ask.split()
                if self.parts is WINDMILL and words[0] in ("a", "an") and "windmill" not in ask:
                    noun = " ".join(words[1:])
                    text = text.replace("Mill", noun.title().replace(" ", "")).replace("windmill", noun)
                return {"content": text}
            return PlannerV3.V3.chat(self, messages, names, max_tokens, role)

    def auto(self, runtime, sentence):
        ex = FakeExecutor()
        session = Session(ex)
        return Copilot(runtime, session).run_auto(sentence), ex, session

    def test_a_thing_the_library_lacks_is_designed_and_built(self):
        from maris3d.copilot import describe_parts as D
        runtime = self.Server({"items": [{"id": "windmill_1", "recipe": "windmill"}]})
        result, ex, _s = self.auto(runtime, "make me a windmill")
        self.assertEqual(runtime.parts_ask, [D.PARTS_SYSTEM_FINAL, "make me a windmill"])   # the trained prompt, the user's words
        self.assertEqual(result.built["designed"], ["Windmill"])
        self.assertEqual((result.built["parts"], result.built["exact"], result.built["missing"]), (3, 3, 0))
        self.assertEqual(result.built["strays"], [])
        parts = [{"name": n, "size": o["dims"], "centre": o["loc"]} for n, o in ex.objs.items() if n.startswith("Mill")]
        self.assertEqual(len(parts), 3)
        self.assertEqual(D.floating(parts), [])                                   # it holds together
        self.assertAlmostEqual(min(p["centre"][2] - p["size"][2] / 2 for p in parts), 0.0, places=3)
        self.assertEqual(ex.objs["MillTower"]["parent"], "Windmill")              # one thing to move

    def test_a_designed_thing_is_placed_like_a_library_thing(self):
        runtime = self.Server({"items": [
            {"id": "platform_1", "recipe": "platform"},
            {"id": "windmill_1", "recipe": "windmill",
             "place": {"anchor": "platform_1", "relation": "behind", "distance": "small"}}]})
        result, ex, session = self.auto(runtime, "a platform and a windmill behind it")
        boxes = CP.scene_boxes(ex.objects(), session.groups)
        self.assertEqual(result.built["built"], ["Platform", "Windmill"])
        self.assertGreater(boxes["Windmill"]["lo"][1], boxes["Platform"]["hi"][1])
        self.assertEqual(runtime.roles.count("parts"), 2)                         # every thing is designed
        self.assertEqual(result.built["designed"], ["Platform", "Windmill"])

    def test_two_things_with_the_same_part_names_keep_their_own_parts(self):
        # a chair and a table that both have a "MillTower": the second thing's parts carry its name,
        # in one request and in a later one (a scene has one set of names)
        same = self.Server({"items": [{"id": "chair_1", "recipe": "chair"}, {"id": "table_1", "recipe": "table"}]},
                           parts=json.loads(json.dumps(WINDMILL)))
        same.chat = lambda messages, names, max_tokens=0, role=None, _c=same.chat, _n=[0]: (
            _c(messages, names, max_tokens, role) if role != "parts" else
            {"content": json.dumps(dict(WINDMILL, object=("chair", "table", "desk")[_n.append(0) or len(_n) - 2]))})
        ex = FakeExecutor()
        session = Session(ex)
        copilot = Copilot(same, session)
        result = copilot.run_auto("a chair and a table")
        self.assertEqual(result.built["built"], ["Chair", "Table"])
        self.assertEqual((result.built["parts"], result.built["exact"]), (6, 6))
        self.assertIn("MillTower", ex.objs)
        self.assertIn("TableMillTower", ex.objs)
        self.assertEqual(ex.objs["TableMillTower"]["parent"], "Table")
        self.assertEqual(ex.objs["MillTower"]["parent"], "Chair")
        same.plan = {"items": [{"id": "desk_1", "recipe": "desk"}]}
        result = copilot.run_auto("a desk")
        self.assertIn("DeskMillTower", ex.objs)
        self.assertEqual(ex.objs["MillTower"]["parent"], "Chair")

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

    def test_a_server_that_does_not_answer_is_said_as_such(self):
        class Down:
            adapters = {}

            def has_role(self, role):
                return True

            def chat(self, *a, **k):
                raise ConnectionRefusedError("connection refused")

        ex = FakeExecutor()
        result = Copilot(Down(), Session(ex)).run_auto("Make me a chair.")
        self.assertIn("connection refused", result.api_error)
        self.assertIn("model server did not answer", result.text)
        self.assertNotIn("could not turn that into things", result.text)
        self.assertEqual(set(ex.objs) - {"SceneNorth"}, set())   # only the compass marker, nothing built

    def test_design_first_asks_the_planner_even_for_a_library_thing(self):
        bench = json.loads(json.dumps(WINDMILL).replace("Mill", "Seat").replace("windmill", "bench"))
        runtime = self.Server({"items": [{"id": "bench_1", "recipe": "bench"}]}, parts=bench)
        ex = FakeExecutor()
        copilot = Copilot(runtime, Session(ex))
        copilot.design_first = True
        result = copilot.run_auto("a bench")
        self.assertEqual(result.built["designed"], ["Bench"])
        self.assertEqual(result.built["library"], [])
        self.assertIn("SeatTower", ex.objs)                       # the planner's parts, not the library's
        self.assertNotIn("BenchSeat", ex.objs)
        runtime.parts = "no idea"                                 # a design that cannot be built:
        ex2 = FakeExecutor()
        copilot2 = Copilot(runtime, Session(ex2))
        copilot2.design_first = True
        result = copilot2.run_auto("a bench")
        self.assertEqual(result.built["designed"], [])            # the library's bench is the fallback
        self.assertIn("BenchSeat", ex2.objs)
        self.assertEqual(result.built["library"], ["Bench"])      # ... and it is said, never silent
        self.assertTrue(any("built from the library instead" in n for n in result.built["notes"]))

    def test_a_change_the_word_edit_did_not_take_is_said_and_builds_nothing(self):
        from maris3d.addon import routing

        class NoEdit(self.Server):
            def has_role(self, role):
                return role == "planner"

        router = lambda req, objs, _turn: routing.resolve(req, bool(objs))
        ex = FakeExecutor()
        runtime = NoEdit({"items": [{"id": "chair_1", "recipe": "chair"}]})
        Copilot(runtime, Session(ex), router=router).run_auto("build me a chair")
        count = len(ex.objs)
        runtime.roles = []
        result = Copilot(runtime, Session(ex), router=router).run_auto("make the chair red")   # a new copilot, as the panel
        self.assertEqual(result.mode, "change")
        self.assertEqual(runtime.roles, [])                           # no model was asked, no fallback
        self.assertEqual(len(ex.objs), count)                         # and no second chair
        self.assertIn("which thing", result.text.lower())

    def test_without_the_parts_adapter_nothing_is_asked(self):
        runtime = self.Server({"items": [{"id": "platform_1", "recipe": "platform"},
                                         {"id": "windmill_1", "recipe": "windmill"}]}, roles=())
        result, _ex, _s = self.auto(runtime, "a platform and a windmill")
        self.assertNotIn("parts", runtime.roles)
        self.assertEqual(result.built["built"], ["Platform"])


class SizeWords(unittest.TestCase):
    """The outline format says "a small platform" as "size": "small"; numbers stay refused."""

    def test_a_size_word_passes_the_check_and_a_number_does_not(self):
        from maris3d.copilot import plan as PLAN
        self.assertEqual(PLAN.check_items({"items": [{"recipe": "bench", "size": "small"}]}), (True, None))
        self.assertFalse(PLAN.check_items({"items": [{"recipe": "bench", "size": [1, 2, 3]}]})[0])
        self.assertFalse(PLAN.check_items({"items": [{"recipe": "bench", "size": 2.0}]})[0])

    def test_the_word_scales_the_whole_thing(self):
        r = CP.RECIPES["bench"]
        small = CP.scale_recipe(r, "small")
        self.assertEqual(small["size"], [round(v * 0.75, 5) for v in r["size"]])
        self.assertEqual(small["parts"][0]["dims"], [round(v * 0.75, 5) for v in r["parts"][0]["dims"]])
        self.assertEqual(small["parts"][0]["offset"], [round(v * 0.75, 5) for v in r["parts"][0]["offset"]])
        self.assertIs(CP.scale_recipe(r, None), r)
        self.assertIs(CP.scale_recipe(r, "enormous"), r)
        inst, _ = CP.layout([{"recipe": "bench", "size": "big"}])
        self.assertEqual(inst[0]["size"], [round(v * 1.5, 5) for v in r["size"]])


if __name__ == "__main__":
    unittest.main()
