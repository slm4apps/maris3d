# SPDX-License-Identifier: Apache-2.0
"""apply_change: every `do`, the ten edit-probe requests as answers, unknown names, batches.
No Blender: `Sim` plays the executor and follows Blender's rules for parenting, so a change is
applied, run and read back (apply_change.check) the way it is in the product."""
import json
import math
import sys
import types
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Executor, Session
from maris3d.dsl import tools as T


def rz(deg, v):
    r = math.radians(deg)
    return [math.cos(r) * v[0] - math.sin(r) * v[1], math.sin(r) * v[0] + math.cos(r) * v[1], v[2]]


class Sim(Executor):
    """Objects with a basis location, a parent and the parent's pose at the time of parenting."""

    def __init__(self):
        self.o = {}
        self.deleted = []

    def reset(self):
        self.o, self.deleted = {}, []

    def _new(self, name, loc, dims, rot=(0, 0, 0), scale=(1, 1, 1), kind="MESH"):
        self.o[name] = {"loc": [float(v) for v in loc], "dims": list(dims), "rot": list(rot), "scale": list(scale),
                        "parent": None, "pin": None, "material": None, "type": kind}

    def run_call(self, c):
        t, g = c["tool"], c.get
        if t == "add_primitive":
            sh = g("shape")
            if g("scale"):
                dims = [2 * v for v in g("scale")]
            elif sh in ("cylinder", "cone"):
                dims = [2 * g("radius"), 2 * g("radius"), g("depth")]
            elif sh == "torus":
                d = 2 * (g("major_radius") + g("minor_radius"))
                dims = [d, d, 2 * g("minor_radius")]
            else:
                dims = [2 * (g("radius") or 1)] * 3
            self._new(g("name"), g("location"), dims, rot=g("rotation_deg") or (0, 0, 0))
        elif t == "add_empty":
            self._new(g("name"), g("location") or (0, 0, 0), (0, 0, 0), kind="EMPTY")
        elif t == "parent":
            ch, pa = self.o[g("child")], self.o[g("parent")]
            ch["parent"], ch["pin"] = g("parent"), (list(pa["loc"]), pa["rot"][2])
        elif t == "set_transform":
            o = self.o.get(g("object"))
            if o is None:
                return False, "no such object"
            if g("location"):
                o["loc"] = [float(v) for v in g("location")]
            if g("rotation_deg"):
                o["rot"] = [float(v) for v in g("rotation_deg")]
            if g("scale"):
                o["scale"] = [float(v) for v in g("scale")]
        elif t == "apply_transform":
            o = self.o[g("object")]
            o["dims"], o["scale"] = [d * s for d, s in zip(o["dims"], o["scale"])], [1, 1, 1]
        elif t == "set_material":
            for n in g("objects") or [g("object")]:
                if n in self.o:
                    self.o[n]["material"] = g("name")
        elif t == "delete_object":
            todo = list(g("objects") or [g("object")])
            for n in todo:
                if n in self.o:
                    for k in [n] + [m for m, v in self.o.items() if v["parent"] == n]:
                        self.o.pop(k, None)
                        self.deleted.append(k)
        elif t == "set_object":
            if g("name") and g("object") in self.o:
                self.o[g("name")] = self.o.pop(g("object"))
                for v in self.o.values():
                    if v["parent"] == g("object"):
                        v["parent"] = g("name")
        elif t in ("shade_smooth", "add_modifier", "apply_modifier"):
            pass
        else:
            return False, f"sim does not know {t}"
        return True, None

    def world(self, name):
        o = self.o[name]
        if not o["parent"]:
            return o["loc"], o["rot"]
        p = self.o[o["parent"]]
        pin_at, pin_yaw = o["pin"]
        d = rz(p["rot"][2] - pin_yaw, [o["loc"][i] - pin_at[i] for i in range(3)])
        return [p["loc"][i] + d[i] for i in range(3)], [o["rot"][0], o["rot"][1], o["rot"][2] + p["rot"][2] - pin_yaw]

    def objects(self):
        out = []
        for n, o in self.o.items():
            loc, rot = self.world(n)
            out.append({"name": n, "type": o["type"], "loc": [round(v, 4) for v in loc],
                        "dims": [round(d * s, 4) for d, s in zip(o["dims"], o["scale"])], "material": o["material"],
                        "parent": o["parent"], "rot_deg": [round(v, 2) for v in rot]})
        return out


class FakeRuntime:
    """The one adapter: the word edit turns (role "edit") are answered from `replies`."""
    final_format = True

    def __init__(self, replies=()):
        self.replies, self.asked = list(replies), []

    def has_role(self, role):
        return role == "edit"

    def chat(self, messages, tool_names, max_tokens=1024, role=None):
        self.asked.append({"messages": messages, "role": role, "tools": tool_names})
        return {"content": self.replies.pop(0)}


def build(*items):
    """Build library things the way the copilot does; returns (copilot, session, sim)."""
    sim = Sim()
    session = Session(sim)
    cop = Copilot(FakeRuntime(), session)
    cop.run_items([{"recipe": r, "place": p} if p else {"recipe": r} for r, p in items])
    return cop, session, sim


def run(session, sim, answer):
    """Apply an answer on the session's specs, run the calls on the sim, read back."""
    done = AC.apply_answer(answer, session.specs, sim.objects())
    session.apply(done.calls)
    session.specs = done.specs
    return done, AC.check(answer, sim.objects(), done)


def ch(*changes, kind="change"):
    return {"kind": kind, "changes": list(changes)}


def statuses(rows):
    return [r["status"] for r in rows]


def box(sim, names):
    objs = {o["name"]: o for o in sim.objects()}
    lo = [min(objs[n]["loc"][i] - objs[n]["dims"][i] / 2 for n in names) for i in range(3)]
    hi = [max(objs[n]["loc"][i] + objs[n]["dims"][i] / 2 for n in names) for i in range(3)]
    return lo, hi


class SpecStore(unittest.TestCase):
    def test_a_built_thing_has_a_spec_in_words_and_metres(self):
        _c, session, _sim = build(("chair", None))
        spec = session.specs["Chair"]
        self.assertEqual(spec["parts"][0]["name"], "ChairBack")                      # the biggest part first, no place
        self.assertNotIn("place", spec["parts"][0])
        legs = [p for p in spec["parts"] if p["name"].startswith("ChairLeg")]
        self.assertEqual(len(legs), 4)
        self.assertTrue(all(p["place"]["relation"] == "under" for p in legs))
        self.assertTrue(all("centre" in p for p in spec["parts"]))                   # metres kept beside the words
        self.assertEqual(spec["parts"][0]["color"], "walnut")

    def test_undo_gives_the_specs_back_with_the_scene(self):
        cop, session, sim = build(("chair", None))
        run(session, sim, ch({"do": "remove", "object": "Chair", "parts": ["ChairBack"]}))
        self.assertNotIn("ChairBack", [p["name"] for p in session.specs["Chair"]["parts"]])
        session.undo()
        self.assertIn("ChairBack", [p["name"] for p in session.specs["Chair"]["parts"]])
        self.assertIn("ChairBack", sim.o)


class EveryDo(unittest.TestCase):
    def test_remove_parts(self):
        _c, s, sim = build(("chair", None))
        before = {o["name"]: o["loc"] for o in sim.objects()}
        done, rows = run(s, sim, ch({"do": "remove", "object": "Chair", "parts": ["ChairBack"]}))
        self.assertEqual(done.calls[0], {"tool": "delete_object", "objects": ["ChairBack"]})
        self.assertEqual(statuses(rows), ["ok"])
        self.assertNotIn("ChairBack", sim.o)
        for n in ("ChairSeat", "ChairLeg1"):                       # what stays does not move
            self.assertEqual(sim.objects()[[o["name"] for o in sim.objects()].index(n)]["loc"], before[n])

    def test_remove_a_whole_thing_takes_its_parts(self):
        _c, s, sim = build(("chair", None), ("table", {"anchor": "Chair", "relation": "next_to"}))
        done, rows = run(s, sim, ch({"do": "remove", "object": "Chair"}))
        self.assertEqual(done.calls, [{"tool": "delete_object", "object": "Chair"}])
        self.assertEqual(statuses(rows), ["ok"])
        self.assertTrue(all(not n.startswith("Chair") for n in sim.o))
        self.assertIn("Table", sim.o)
        self.assertNotIn("Chair", s.specs)

    def test_removing_what_something_stands_on_keeps_it_where_it_was(self):
        _c, s, sim = build(("snowman", None))
        top = next(o["loc"] for o in sim.objects() if o["name"] == "SnowHatTop")
        _d, rows = run(s, sim, ch({"do": "remove", "object": "Snowman", "parts": ["SnowHatBrim"]}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(next(o["loc"] for o in sim.objects() if o["name"] == "SnowHatTop"), top)

    def test_recolor(self):
        _c, s, sim = build(("sofa", None))
        done, rows = run(s, sim, ch({"do": "recolor", "object": "Sofa", "parts": ["SofaBase"], "color": "red"}))
        self.assertEqual(done.calls[0]["objects"], ["SofaBase"])
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(sim.o["SofaBase"]["material"], "Red")
        self.assertNotEqual(sim.o["SofaBack"]["material"], "Red")

    def test_recolor_with_a_finish(self):
        _c, s, sim = build(("sofa", None))
        done, rows = run(s, sim, ch({"do": "recolor", "object": "Sofa", "color": "pink", "finish": "smooth"}))
        self.assertIn("SUBSURF", json.dumps(done.calls))
        self.assertEqual(statuses(rows), ["ok"])

    def test_scale_lays_the_parts_out_again(self):
        _c, s, sim = build(("chair", None))
        seat_z = next(o["loc"][2] for o in sim.objects() if o["name"] == "ChairSeat")
        legs = [f"ChairLeg{i}" for i in range(1, 5)]
        done, rows = run(s, sim, ch({"do": "scale", "object": "Chair", "parts": legs, "by": {"z": 2}}))
        self.assertEqual(statuses(rows), ["ok"])
        objs = {o["name"]: o for o in sim.objects()}
        self.assertAlmostEqual(objs["ChairLeg1"]["dims"][2], 0.9, 2)
        self.assertAlmostEqual(objs["ChairSeat"]["loc"][2], seat_z + 0.45, 1)          # longer legs lift the seat
        lo, _hi = box(sim, [n for n in sim.o if n.startswith("Chair") and n != "Chair"])
        self.assertAlmostEqual(lo[2], 0.0, 2)                                         # still on the floor

    def test_move_by_a_shift(self):
        _c, s, sim = build(("chair", None))
        was = sim.o["Chair"]["loc"]
        done, rows = run(s, sim, ch({"do": "move", "object": "Chair", "shift": {"x": -5}}))
        self.assertEqual(done.calls, [{"tool": "set_transform", "object": "Chair",
                                       "location": [was[0] - 5, was[1], was[2]]}])
        self.assertEqual(statuses(rows), ["ok"])
        self.assertAlmostEqual(next(o["loc"][0] for o in sim.objects() if o["name"] == "ChairSeat"), -5 + 0.092 + was[0], 2)

    def test_move_to_a_place_goes_through_the_placer(self):
        _c, s, sim = build(("table", None), ("chair", {"anchor": "Table", "relation": "next_to", "distance": "medium"}))
        done, rows = run(s, sim, ch({"do": "move", "object": "Chair", "place": {
            "anchor": "Table", "relation": "behind", "distance": "small"}}))
        self.assertEqual(statuses(rows), ["ok"])
        chair, table = box(sim, [n for n in sim.o if n.startswith("Chair") and n != "Chair"]), box(sim, ["TableTop", "TableLeg"])
        self.assertGreater(chair[0][1], table[1][1])                  # behind = further +y than the table
        self.assertAlmostEqual(chair[0][1] - table[1][1], 0.175, 1)  # the word "small"

    def test_turn_by_degrees_about_the_middle(self):
        _c, s, sim = build(("sofa", None))
        was_base = next(o["loc"] for o in sim.objects() if o["name"] == "SofaBase")
        _d, rows = run(s, sim, ch({"do": "turn", "object": "Sofa", "by": 90}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(sim.o["Sofa"]["rot"][2], 90)
        # the 1.6 x 0.6 footprint now runs along y, round the same middle
        arms = [o["loc"] for o in sim.objects() if o["name"] in ("SofaLeft", "SofaRight")]
        self.assertAlmostEqual(abs(arms[0][1] - arms[1][1]), 0.8, 2)
        base = next(o["loc"] for o in sim.objects() if o["name"] == "SofaBase")     # the seat is the middle of the footprint
        self.assertAlmostEqual(base[0], was_base[0], 2)
        self.assertAlmostEqual(base[1], was_base[1], 2)

    def test_a_half_turn_is_about_the_middle_of_the_footprint_not_the_origin(self):
        _c, s, sim = build(("chair", None))                 # the chair's parts are not centred on its origin
        parts = [n for n in sim.o if n.startswith("Chair") and n != "Chair"]
        lo, hi = box(sim, parts)
        mid = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2]
        was = {o["name"]: o["loc"] for o in sim.objects()}
        _d, rows = run(s, sim, ch({"do": "turn", "object": "Chair", "by": 180}))
        self.assertEqual(statuses(rows), ["ok"])
        for o in sim.objects():
            if o["name"] in parts:
                self.assertAlmostEqual(o["loc"][0], 2 * mid[0] - was[o["name"]][0], 2)
                self.assertAlmostEqual(o["loc"][1], 2 * mid[1] - was[o["name"]][1], 2)

    def test_turn_to_face_a_thing_and_a_compass_word(self):
        _c, s, sim = build(("sofa", None), ("table", {"anchor": "Sofa", "relation": "behind", "distance": "medium"}))
        _d, rows = run(s, sim, ch({"do": "turn", "object": "Sofa", "face": "Table"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertAlmostEqual(sim.o["Sofa"]["rot"][2], 180, 1)        # the table is behind (north): the front turns round
        _d, rows = run(s, sim, ch({"do": "turn", "object": "Sofa", "face": "east"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertAlmostEqual(sim.o["Sofa"]["rot"][2], 90, 1)

    def test_add_a_part_on_a_part(self):
        _c, s, sim = build(("snowman", None))
        hat = {"name": "SnowTopHat", "shape": "cylinder", "size": [0.3, 0.3, 0.3], "color": "black",
               "place": {"on": "SnowHead", "relation": "on_top_of", "align": {"x": "centre", "y": "centre"}}}
        done, rows = run(s, sim, ch({"do": "add", "object": "Snowman", "parts": [hat]}))
        self.assertEqual(statuses(rows), ["ok"])
        objs = {o["name"]: o for o in sim.objects()}
        self.assertEqual(objs["SnowTopHat"]["parent"], "Snowman")
        self.assertEqual(objs["SnowTopHat"]["material"], "Black")
        self.assertAlmostEqual(objs["SnowTopHat"]["loc"][2] - 0.15, objs["SnowHead"]["loc"][2] + objs["SnowHead"]["dims"][2] / 2, 2)

    def test_add_after_a_move_and_a_turn_lands_in_the_right_place(self):
        _c, s, sim = build(("snowman", None))
        run(s, sim, ch({"do": "move", "object": "Snowman", "shift": {"x": 3, "y": 2}}, {"do": "turn", "object": "Snowman", "by": 90}))
        hat = {"name": "SnowTopHat", "shape": "cylinder", "size": [0.3, 0.3, 0.3], "color": "black",
               "place": {"on": "SnowHead", "relation": "on_top_of", "align": {"x": "centre", "y": "centre"}}}
        _d, rows = run(s, sim, ch({"do": "add", "object": "Snowman", "parts": [hat]}))
        self.assertEqual(statuses(rows), ["ok"])
        objs = {o["name"]: o for o in sim.objects()}
        self.assertAlmostEqual(objs["SnowTopHat"]["loc"][0], objs["SnowHead"]["loc"][0], 2)
        self.assertAlmostEqual(objs["SnowTopHat"]["loc"][1], objs["SnowHead"]["loc"][1], 2)

    def test_scale_after_a_move_and_a_turn_still_reads_back(self):
        _c, s, sim = build(("sofa", None))
        run(s, sim, ch({"do": "move", "object": "Sofa", "shift": {"x": 4}}, {"do": "turn", "object": "Sofa", "by": 90}))
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Sofa", "by": {"x": 2}}))
        self.assertEqual(statuses(rows), ["ok"])

    def test_copy_makes_a_named_second_thing(self):
        _c, s, sim = build(("chair", None))
        done, rows = run(s, sim, ch({"do": "copy", "object": "Chair", "count": 2}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertIn("Chair2", s.specs)
        self.assertIn("Chair3", s.specs)
        self.assertIn("ChairSeat2", sim.o)
        self.assertEqual(sim.o["ChairSeat2"]["parent"], "Chair2")
        a, b = box(sim, ["ChairSeat"]), box(sim, ["ChairSeat2"])
        self.assertGreaterEqual(b[0][0], a[1][0] - 1e-6)                # beside it, not on it
        _d, rows = run(s, sim, ch({"do": "remove", "object": "Chair2"}))   # a copy can be named like any thing
        self.assertEqual(statuses(rows), ["ok"])

    def test_rename_a_thing_and_a_part(self):
        _c, s, sim = build(("bench", None))
        _d, rows = run(s, sim, ch({"do": "rename", "object": "Bench", "to": "ParkBench"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertIn("ParkBench", sim.o)
        self.assertNotIn("Bench", sim.o)
        self.assertEqual(sim.o["BenchSeat"]["parent"], "ParkBench")
        _d, rows = run(s, sim, ch({"do": "rename", "object": "ParkBench", "parts": ["BenchBack"], "to": "Backrest"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertIn("Backrest", [p["name"] for p in s.specs["ParkBench"]["parts"]])


class EditProbe(unittest.TestCase):
    """The ten requests of the edit probe, as the planner is to answer them."""

    def test_1_remove_the_back_of_the_chair(self):
        _c, s, sim = build(("chair", None))
        _d, rows = run(s, sim, ch({"do": "remove", "object": "Chair", "parts": ["ChairBack"]}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertNotIn("ChairBack", sim.o)

    def test_2_chair_legs_twice_as_long(self):
        _c, s, sim = build(("chair", None))
        legs = [f"ChairLeg{i}" for i in range(1, 5)]
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Chair", "parts": legs, "by": {"z": 2}}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertAlmostEqual(sim.objects()[1]["dims"][2], 0.9, 2)

    def test_3_chair_seat_red(self):
        _c, s, sim = build(("chair", None))
        _d, rows = run(s, sim, ch({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(sim.o["ChairSeat"]["material"], "Red")

    def test_4_sofa_three_times_as_wide(self):
        _c, s, sim = build(("sofa", None))
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Sofa", "by": {"x": 3}}))
        self.assertEqual(statuses(rows), ["ok"])
        lo, hi = box(sim, [n for n in sim.o if n.startswith("Sofa") and n != "Sofa"])
        self.assertAlmostEqual(hi[0] - lo[0], 4.8, 1)
        self.assertAlmostEqual(hi[1] - lo[1], 0.6, 1)

    def test_5_sofa_blue(self):
        _c, s, sim = build(("sofa", None))
        _d, rows = run(s, sim, ch({"do": "recolor", "object": "Sofa", "color": "blue"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual({sim.o[n]["material"] for n in sim.o if n.startswith("Sofa") and n != "Sofa"}, {"Blue"})

    def test_6_remove_the_snowmans_hat(self):
        _c, s, sim = build(("snowman", None))
        _d, rows = run(s, sim, ch({"do": "remove", "object": "Snowman", "parts": ["SnowHatBrim", "SnowHatTop"]}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertFalse([n for n in sim.o if n.startswith("SnowHat")])
        self.assertIn("SnowHead", sim.o)

    def test_7_snowman_half_as_tall(self):
        _c, s, sim = build(("snowman", None))
        lo, hi = box(sim, [n for n in sim.o if n.startswith("Snow") and n != "Snowman"])
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Snowman", "by": {"z": 0.5}}))
        self.assertEqual(statuses(rows), ["ok"])
        lo2, hi2 = box(sim, [n for n in sim.o if n.startswith("Snow") and n != "Snowman"])
        self.assertAlmostEqual((hi2[2] - lo2[2]) / (hi[2] - lo[2]), 0.5, 1)
        self.assertAlmostEqual(lo2[2], lo[2], 1)

    def test_8_remove_the_bench_backrest(self):
        _c, s, sim = build(("bench", None))
        _d, rows = run(s, sim, ch({"do": "remove", "object": "Bench", "parts": ["BenchBack"]}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertNotIn("BenchBack", sim.o)
        self.assertIn("BenchSeat", sim.o)

    def test_9_bench_green(self):
        _c, s, sim = build(("bench", None))
        _d, rows = run(s, sim, ch({"do": "recolor", "object": "Bench", "color": "green"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(sim.o["BenchBack"]["material"], "Green")

    def test_10_table_half_as_tall_and_twice_as_long(self):
        _c, s, sim = build(("table", None))
        _d, rows = run(s, sim, ch({"do": "scale", "object": "Table", "by": {"z": 0.5}},
                                  {"do": "scale", "object": "Table", "by": {"x": 2}}))
        self.assertEqual(statuses(rows), ["ok", "ok"])
        objs = {o["name"]: o for o in sim.objects()}
        self.assertAlmostEqual(objs["TableTop"]["dims"][0], 2.8, 2)
        self.assertAlmostEqual(objs["TableTop"]["loc"][2] + objs["TableTop"]["dims"][2] / 2, 0.765 / 2, 1)


class Errors(unittest.TestCase):
    def setUp(self):
        _c, self.s, self.sim = build(("chair", None))

    def fails(self, change, text):
        done, rows = run(self.s, self.sim, ch(change))
        self.assertEqual(done.calls, [])
        self.assertEqual(len(done.errors), 1)
        self.assertIn(text, done.errors[0]["error"])
        self.assertEqual(statuses(rows), ["not-checked"])
        self.assertIn("ChairSeat", self.sim.o)                      # nothing happened

    def test_unknown_object_is_reported_never_guessed(self):
        self.fails({"do": "remove", "object": "chair"}, "unknown object 'chair'")        # not the same name
        self.fails({"do": "remove", "object": "Sofa"}, "the scene has: Chair")

    def test_unknown_part(self):
        self.fails({"do": "remove", "object": "Chair", "parts": ["ChairBackrest"]}, "unknown part 'ChairBackrest'")

    def test_unknown_colour_do_and_kind(self):
        self.fails({"do": "recolor", "object": "Chair", "color": "purplish"}, "colour 'purplish'")
        self.fails({"do": "polish", "object": "Chair"}, "unknown do 'polish'")
        done = AC.apply_answer({"kind": "wish"}, self.s.specs)
        self.assertIn("unknown kind", done.errors[0]["error"])

    def test_bad_numbers_and_forms(self):
        self.fails({"do": "scale", "object": "Chair", "by": {"w": 2}}, "scale needs")
        self.fails({"do": "scale", "object": "Chair", "by": {"x": 0}}, "scale needs")
        self.fails({"do": "scale", "object": "Chair", "by": {"x": "twice"}}, "scale needs")
        self.fails({"do": "move", "object": "Chair"}, "exactly one of place, shift or to")
        self.fails({"do": "turn", "object": "Chair", "by": 90, "face": "north"}, "exactly one of by, face or to_degrees")
        self.fails({"do": "turn", "object": "Chair", "face": "Moon"}, "unknown thing to face 'Moon'")
        self.fails({"do": "move", "object": "Chair", "place": {"anchor": "Moon", "relation": "behind"}}, "unknown anchor")
        self.fails({"do": "move", "object": "Chair", "place": {"anchor": "scene", "relation": "toward"}}, "unknown relation")
        self.fails({"do": "rename", "object": "Chair", "to": "Chair"}, "already used")
        self.fails({"do": "copy", "object": "Chair", "count": 0}, "count")
        self.fails({"do": "move", "object": "Chair", "parts": ["ChairSeat"], "shift": {"x": 1}}, "whole thing")

    def test_a_bad_part_to_add(self):
        floating = {"name": "Hat", "shape": "cube", "size": [0.1, 0.1, 0.1], "color": "red",
                    "place": {"on": "Nothing", "relation": "on_top_of"}}
        self.fails({"do": "add", "object": "Chair", "parts": [floating]}, "Hat: on 'Nothing'")
        taken = dict(floating, name="ChairSeat", place={"on": "ChairSeat", "relation": "on_top_of"})
        self.fails({"do": "add", "object": "Chair", "parts": [taken]}, "already in the scene")


class Batches(unittest.TestCase):
    def test_changes_apply_in_order_and_a_bad_one_does_not_stop_the_rest(self):
        _c, s, sim = build(("chair", None), ("sofa", {"anchor": "Chair", "relation": "next_to"}))
        answer = ch({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"},
                    {"do": "remove", "object": "Armchair"},
                    {"do": "scale", "object": "Sofa", "by": {"x": 2}},
                    {"do": "move", "object": "Chair", "shift": {"y": 1}})
        done, rows = run(s, sim, answer)
        self.assertEqual(statuses(rows), ["ok", "not-checked", "ok", "ok"])
        self.assertEqual([e["change"] for e in done.errors], [1])

    def test_the_second_change_sees_the_first(self):
        _c, s, sim = build(("chair", None))
        done, rows = run(s, sim, ch({"do": "rename", "object": "Chair", "to": "Seat1"},
                                    {"do": "recolor", "object": "Seat1", "color": "blue"}))
        self.assertEqual(statuses(rows), ["ok", "ok"])

    def test_check_says_wrong_when_the_scene_is_not_as_applied(self):
        _c, s, sim = build(("chair", None))
        answer = ch({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"})
        done = AC.apply_answer(answer, s.specs, sim.objects())          # calls NOT run
        rows = AC.check(answer, sim.objects(), done)
        self.assertEqual(statuses(rows), ["wrong"])
        self.assertIn("ChairSeat is Walnut, not Red", rows[0]["detail"])

    def test_check_says_not_checked_when_the_scene_cannot_tell(self):
        _c, s, sim = build(("sofa", None))
        answer = ch({"do": "turn", "object": "Sofa", "by": 90})
        done = AC.apply_answer(answer, s.specs, sim.objects())
        session = s
        session.apply(done.calls)
        no_rot = [{k: v for k, v in o.items() if k != "rot_deg"} for o in sim.objects()]
        self.assertEqual(statuses(AC.check(answer, no_rot, done)), ["not-checked"])


class Kinds(unittest.TestCase):
    def test_question_and_cannot_carry_only_the_say(self):
        for kind in ("question", "cannot"):
            done = AC.apply_answer({"kind": kind, "say": "which chair?"}, {})
            self.assertEqual((done.say, done.calls, done.errors), ("which chair?", [], []))
        self.assertTrue(AC.apply_answer({"kind": "question"}, {}).errors)

    def test_build_is_not_this_modules_business(self):
        done = AC.apply_answer({"kind": "build"}, {})
        self.assertEqual((done.kind, done.calls, done.errors), ("build", [], []))


class Loop(unittest.TestCase):
    """A change to a thing the copilot built goes to the word edit adapter; code applies the answer."""

    def copilot(self, replies):
        sim = Sim()
        cop = Copilot(FakeRuntime(), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        cop.runtime.replies = list(replies)
        return cop, sim

    def test_a_change_is_applied_by_code_and_asked_of_the_edit_adapter_only(self):
        cop, sim = self.copilot([json.dumps(ch({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"}))])
        result = cop.run_auto("make the seat red")
        self.assertEqual(result.mode, "change")
        self.assertEqual(sim.o["ChairSeat"]["material"], "Red")
        self.assertEqual([c["status"] for c in result.changed["checked"]], ["ok"])
        self.assertEqual([(a["role"], a["tools"]) for a in cop.runtime.asked], [("edit", [])])
        self.assertTrue(result.ok)

    def test_a_change_is_one_undo_unit_and_undo_restores_specs(self):
        cop, sim = self.copilot([json.dumps(ch({"do": "scale", "object": "Chair", "size": "double"},
                                               {"do": "recolor", "object": "Chair", "color": "red"}))])
        n = len(cop.session.batches)
        size = list(cop.session.specs["Chair"]["size"])
        cop.run_auto("wider and red")
        self.assertEqual(len(cop.session.batches), n + 1)
        self.assertGreater(cop.session.specs["Chair"]["size"][0], size[0] * 1.5)
        cop.undo()
        self.assertEqual(cop.session.specs["Chair"]["size"], size)

    def test_question_goes_to_the_panel_and_nothing_runs(self):
        cop, sim = self.copilot([json.dumps({"kind": "question", "say": "Which chair do you mean?"})])
        said, calls = [], len(sim.o)
        cop.say = lambda who, text: said.append((who, text))
        result = cop.run_auto("make it red")
        self.assertEqual(result.text, "Which chair do you mean?")
        self.assertEqual(result.calls, [])
        self.assertIn(("Planner", "Which chair do you mean?"), said)
        self.assertEqual(len(sim.o), calls)

    def test_an_unknown_name_is_an_error_in_the_result(self):
        cop, sim = self.copilot([json.dumps(ch({"do": "remove", "object": "Throne"}))])
        result = cop.run_auto("remove the throne")
        self.assertFalse(result.ok)
        self.assertIn("unknown object 'Throne'", result.errors[0]["error"])
        self.assertIn("ChairSeat", sim.o)

    def test_a_scene_with_nothing_built_does_not_ask_the_edit_adapter(self):
        sim = Sim()
        cop = Copilot(FakeRuntime(["{}"]), Session(sim))
        self.assertEqual(cop.session.specs, {})            # no specs: the word edit is not tried
        cop.run_auto("make the thing red")
        self.assertNotIn("edit", [a["role"] for a in cop.runtime.asked])


class FakeBpy:
    """Just enough of bpy.data.objects for the delete_object script."""

    class Obj:
        def __init__(self, name, parent=None):
            self.name, self.parent = name, parent

    class Objects(dict):
        def get(self, name):
            return dict.get(self, name)

        def remove(self, o, do_unlink=True):
            self.pop(o.name)

    def __init__(self, tree):
        self.objects = self.Objects()
        for name, parent in tree:
            self.objects[name] = self.Obj(name, self.objects.get(parent))
        for o in self.objects.values():
            o.children_recursive = [k for k in self.objects.values() if self._under(k, o)]

    def _under(self, k, o):
        while k.parent is not None:
            if k.parent is o:
                return True
            k = k.parent
        return False


class DeleteObject(unittest.TestCase):
    def run_it(self, call, tree):
        fake = FakeBpy(tree)
        module = types.ModuleType("bpy")
        module.data = fake
        scope = {}
        saved = sys.modules.get("bpy")
        sys.modules["bpy"] = module
        try:
            exec(T.compile_calls({"calls": [call]}), scope)
        finally:
            sys.modules.pop("bpy") if saved is None else sys.modules.__setitem__("bpy", saved)
        return sorted(fake.objects), scope

    TREE = [("Chair", None), ("Seat", "Chair"), ("Leg", "Seat"), ("Table", None)]

    def test_the_tool_is_declared_and_compiles(self):
        names = [t["properties"]["tool"]["const"] for t in T.TOOLS]
        self.assertIn("delete_object", names)
        import ast
        ast.parse(T.compile_calls({"calls": [{"tool": "delete_object", "object": "X"}]}))

    def test_deleting_a_group_deletes_its_children(self):
        left, scope = self.run_it({"tool": "delete_object", "object": "Chair"}, self.TREE)
        self.assertEqual(left, ["Table"])
        self.assertEqual(sorted(scope["_deleted"]), ["Chair", "Leg", "Seat"])
        self.assertEqual(scope["_missing"], [])

    def test_several_names_and_a_missing_one_is_reported_not_guessed(self):
        left, scope = self.run_it({"tool": "delete_object", "objects": ["Leg", "Tabel"]}, self.TREE)
        self.assertEqual(left, ["Chair", "Seat", "Table"])
        self.assertEqual(scope["_deleted"], ["Leg"])
        self.assertEqual(scope["_missing"], ["Tabel"])


if __name__ == "__main__":
    unittest.main()


class FlatPart(unittest.TestCase):
    def test_a_flat_part_grows_without_dividing_by_its_zero_side(self):
        from maris3d.copilot import apply_change as AC
        old = {"q": [0, 0, 0], "parts": [{"name": "Rug", "centre": [0, 0, 0], "size": [2.0, 1.0, 0.0]}]}
        new = {"q": [0, 0, 0], "pins": {"*": [0, 0, 0, 0]}, "parts": [{"name": "Rug", "centre": [0, 0, 0], "size": [3.0, 1.5, 0.0]}]}
        calls = AC._reconcile(old, new)
        scale = [c for c in calls if c["tool"] == "set_transform"][0]["scale"]
        self.assertEqual(scale, [1.5, 1.5, 1.0])


class SessionKeptAcrossRequests(unittest.TestCase):
    """The add-on makes an executor per request and keeps one session (addon/__init__.py _SESSION)."""

    class Ex:
        def __init__(self, names):
            self.names = names

        def objects(self):
            return [{"name": n} for n in self.names]

    def test_rebind_keeps_what_is_still_in_the_scene(self):
        from maris3d.copilot.session import Session
        s = Session(self.Ex([]))
        s.specs = {"Sofa": {"parts": [{"name": "SofaSeat"}]}, "Lamp": {"parts": [{"name": "LampPole"}]}}
        s.groups = {"Sofa": ["SofaSeat"], "Lamp": ["LampPole"]}
        gone = s.rebind(self.Ex(["SofaSeat"]))
        self.assertEqual(gone, ["Lamp"])
        self.assertEqual(list(s.specs), ["Sofa"])
        self.assertEqual(list(s.groups), ["Sofa"])

    def test_forget_last_gives_the_specs_back_without_running_anything(self):
        from maris3d.copilot.session import Session

        class Ex(self.Ex):
            ran = []

            def run_call(self, call):
                self.ran.append(call)
                return True, None

        ex = Ex(["A"])
        s = Session(ex)
        s.apply([{"tool": "x"}])
        s.specs = {"A": {"parts": []}}
        ran = len(ex.ran)
        self.assertTrue(s.forget_last())
        self.assertEqual(s.specs, {})
        self.assertEqual(len(ex.ran), ran)
