# SPDX-License-Identifier: Apache-2.0
"""Exact numbers: do `shape` (one primitive the user typed) and the absolute move / turn / scale
(`to`, `to_degrees`). Applied, run on a stand-in executor and read back like test_apply_change."""
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot import edit_words as EW

from tests.test_apply_change import Sim, build, ch, run, statuses


class ShapeSim(Sim):
    """Sim, with primitives made the way Blender makes them from their arguments."""

    def run_call(self, c):
        if c["tool"] == "add_primitive" and c.get("shape") in AC.SHAPES and "offset" not in c:
            self._new(c["name"], c["location"], AC.primitive_dims(c["shape"], c),
                      rot=c.get("rotation_deg") or (0, 0, 0), scale=c.get("scale") or (1, 1, 1))
            return True, None
        return super().run_call(c)


def shape_session(*changes):
    from maris3d.copilot.session import Session
    sim = ShapeSim()
    session = Session(sim)
    done, rows = run(session, sim, ch(*changes))
    return session, sim, done, rows


def obj(sim, name):
    return next(o for o in sim.objects() if o["name"] == name)


class PrimitiveDims(unittest.TestCase):
    def test_blender_defaults(self):
        self.assertEqual(AC.primitive_dims("cube"), [2.0, 2.0, 2.0])
        self.assertEqual(AC.primitive_dims("uv_sphere", {"radius": 0.5}), [1.0, 1.0, 1.0])
        self.assertEqual(AC.primitive_dims("cylinder", {"radius": 0.1, "depth": 0.18}), [0.2, 0.2, 0.18])
        self.assertEqual(AC.primitive_dims("torus", {"major_radius": 1, "minor_radius": 0.5}), [3.0, 3.0, 1.0])
        self.assertEqual(AC.primitive_dims("plane", {"size": 4}), [4.0, 4.0, 0.0])

    def test_unknown_shape(self):
        with self.assertRaises(AC.ChangeError):
            AC.primitive_dims("teapot")


class ShapeDo(unittest.TestCase):
    def test_one_call_with_the_typed_numbers_and_no_renamed_part(self):
        s, sim, done, rows = shape_session({"do": "shape", "shape": "cylinder", "name": "Cup",
                                            "at": [-1.55, 0.75, 0.86], "radius": 0.1, "depth": 0.18})
        self.assertEqual(done.calls, [{"tool": "add_primitive", "shape": "cylinder", "name": "Cup",
                                       "location": [-1.55, 0.75, 0.86], "radius": 0.1, "depth": 0.18}])
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(list(sim.o), ["Cup"])
        self.assertEqual([p["name"] for p in s.specs["Cup"]["parts"]], ["Cup"])

    def test_rotation_and_scale_are_passed_on(self):
        _s, sim, done, rows = shape_session({"do": "shape", "shape": "cube", "name": "Box", "at": [0, 0, 1],
                                             "rotation": [0, 0, 30], "scale": [1, 2, 0.5]})
        self.assertEqual(done.calls[0]["rotation_deg"], [0.0, 0.0, 30.0])
        self.assertEqual(done.calls[0]["scale"], [1.0, 2.0, 0.5])
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(obj(sim, "Box")["dims"], [2.0, 4.0, 1.0])

    def test_bad_values_are_errors_not_guesses(self):
        for bad in ({"shape": "teapot", "name": "T"}, {"shape": "cube"}, {"shape": "cube", "name": "A", "at": [1, 2]},
                    {"shape": "cube", "name": "A", "radius": -1}):
            _s, _sim, done, _rows = shape_session(dict(bad, do="shape"))
            self.assertTrue(done.errors, bad)
            self.assertEqual(done.calls, [])

    def test_a_taken_name_is_refused(self):
        _c, s, sim = build(("chair", None))
        done, _rows = run(s, sim, ch({"do": "shape", "shape": "cube", "name": "Chair"}))
        self.assertTrue(done.errors)


class AbsoluteOnAShape(unittest.TestCase):
    def setUp(self):
        self.s, self.sim, _d, _r = shape_session({"do": "shape", "shape": "cube", "name": "Box", "at": [0, 0, 1],
                                                  "size": 1})

    def go(self, change):
        return run(self.s, self.sim, ch(dict(change, object="Box")))

    def test_move_to(self):
        done, rows = self.go({"do": "move", "to": [1, 2, 0.5]})
        self.assertEqual(done.calls, [{"tool": "set_transform", "object": "Box", "location": [1.0, 2.0, 0.5]}])
        self.assertEqual(statuses(rows), ["ok"])

    def test_turn_to_three_angles(self):
        done, rows = self.go({"do": "turn", "to_degrees": [90, 0, 45]})
        self.assertEqual(done.calls, [{"tool": "set_transform", "object": "Box", "rotation_deg": [90.0, 0.0, 45.0]}])
        self.assertEqual(statuses(rows), ["ok"])

    def test_turn_by_keeps_the_tilt(self):
        self.go({"do": "turn", "to_degrees": [90, 0, 0]})
        done, _rows = self.go({"do": "turn", "by": 90})
        self.assertEqual(done.calls[0]["rotation_deg"], [90.0, 0.0, 90.0])

    def test_scale_to_then_by(self):
        done, rows = self.go({"do": "scale", "to": 2})
        self.assertEqual(done.calls, [{"tool": "set_transform", "object": "Box", "scale": [2.0, 2.0, 2.0]}])
        self.assertEqual(statuses(rows), ["ok"])
        done, rows = self.go({"do": "scale", "by": {"z": 1.5}})
        self.assertEqual(done.calls[0]["scale"], [2.0, 2.0, 3.0])
        self.assertEqual(obj(self.sim, "Box")["dims"], [2.0, 2.0, 3.0])

    def test_copy_rename_recolor_remove(self):
        done, rows = self.go({"do": "copy", "count": 1})
        self.assertEqual(done.calls[0]["tool"], "add_primitive")
        self.assertEqual(statuses(rows), ["ok"])
        _d, rows = self.go({"do": "rename", "to": "Crate"})
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual([p["name"] for p in self.s.specs["Crate"]["parts"]], ["Crate"])
        _d, rows = run(self.s, self.sim, ch({"do": "recolor", "object": "Crate", "color": "red"}))
        self.assertEqual(statuses(rows), ["ok"])
        _d, rows = run(self.s, self.sim, ch({"do": "remove", "object": "Crate"}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(sorted(self.sim.o), ["Box2"])

    def test_no_parts_can_be_added(self):
        done, _rows = self.go({"do": "add", "parts": [{"name": "Lid", "shape": "cube", "size": [1, 1, 0.1]}]})
        self.assertTrue(done.errors)


class AbsoluteOnABuiltThing(unittest.TestCase):
    def test_move_to_puts_the_thing_there(self):
        _c, s, sim = build(("chair", None))
        done, rows = run(s, sim, ch({"do": "move", "object": "Chair", "to": [3, -2, 0]}))
        self.assertEqual(done.calls, [{"tool": "set_transform", "object": "Chair", "location": [3.0, -2.0, 0.0]}])
        self.assertEqual(statuses(rows), ["ok"])

    def test_turn_to_a_yaw(self):
        _c, s, sim = build(("chair", None))
        run(s, sim, ch({"do": "turn", "object": "Chair", "by": 30}))
        done, rows = run(s, sim, ch({"do": "turn", "object": "Chair", "to_degrees": 90}))
        self.assertEqual(done.calls[0]["rotation_deg"], [0.0, 0.0, 90.0])
        self.assertEqual(statuses(rows), ["ok"])

    def test_a_tilting_rotation_is_refused_for_a_thing_of_parts(self):
        _c, s, sim = build(("chair", None))
        done, _rows = run(s, sim, ch({"do": "turn", "object": "Chair", "to_degrees": [30, 0, 0]}))
        self.assertTrue(done.errors)

    def test_scale_to_is_from_the_built_size(self):
        _c, s, sim = build(("chair", None))
        size = list(s.specs["Chair"]["size"])
        run(s, sim, ch({"do": "scale", "object": "Chair", "by": {"x": 2, "y": 2, "z": 2}}))
        done, rows = run(s, sim, ch({"do": "scale", "object": "Chair", "to": [1, 1, 1]}))
        self.assertEqual(statuses(rows), ["ok"])
        self.assertEqual(s.specs["Chair"]["scale"], [1.0, 1.0, 1.0])
        for a, b in zip(s.specs["Chair"]["size"], size):          # laid out again from words: a few cm
            self.assertAlmostEqual(a, b, delta=0.06 * b)

    def test_two_ways_at_once_is_an_error(self):
        _c, s, sim = build(("chair", None))
        done, _rows = run(s, sim, ch({"do": "move", "object": "Chair", "to": [0, 0, 0], "shift": {"x": 1}}))
        self.assertTrue(done.errors)


if __name__ == "__main__":
    unittest.main()


class ExactRoute(unittest.TestCase):
    def _copilot(self, reply):
        from maris3d.copilot.loop import Copilot
        from maris3d.copilot.session import Session
        from tests.test_apply_change import FakeRuntime

        class Runtime(FakeRuntime):
            def has_role(self, role):
                return role == "edit"

        sim = ShapeSim()
        cop = Copilot(Runtime([reply]), Session(sim))
        return cop, sim

    def test_an_exact_sentence_goes_to_the_edit_model(self):
        answer = {"kind": "change", "changes": [{"do": "shape", "shape": "cube", "name": "Box", "at": [1, 2, 0],
                                                 "size": 0.5}]}
        cop, sim = self._copilot(EW.wrap(answer))
        cop.run_auto("Add a cube named Box at 1, 2, 0 with a size of 0.5")
        asked = cop.runtime.asked[0]["messages"][0]["content"]
        self.assertEqual(asked, EW.EDIT_SYSTEM_EXACT)
        self.assertEqual(obj(sim, "Box")["loc"], [1.0, 2.0, 0.0])
        self.assertEqual(obj(sim, "Box")["dims"], [0.5, 0.5, 0.5])

    def test_the_adapter_in_use_keeps_its_prompt_bytes(self):
        self.assertNotIn("do shape", EW.EDIT_SYSTEM)
        self.assertNotIn("percent", EW.EDIT_SYSTEM)
        self.assertIn("do shape", EW.EDIT_SYSTEM_EXACT)
        self.assertIn("unit: mm|cm|m", EW.EDIT_SYSTEM_EXACT)
        self.assertIn(EW.SHOW_SYSTEM, EW.EDIT_SYSTEM_EXACT)
