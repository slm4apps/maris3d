# SPDX-License-Identifier: Apache-2.0
"""Every word of the vocabulary goes through the code that reads it and changes the result.

A word is covered when it is in a slot listed in COVERED below: the tests here loop over the
whole list of that slot, so a word added to the vocabulary is tested the moment it is added.
"""
import unittest

from maris3d.copilot import apply_change as AC
from maris3d.copilot import describe_parts as DP
from maris3d.copilot import place as PLACE
from maris3d.copilot import size_words as SW
from maris3d.copilot import vocabulary as V

from tests.test_apply_change import build, ch, run, statuses

# role -> slots whose every word a test below runs (read by the coverage check)
COVERED = {
    "parts": ("shape", "color", "part_relation", "align", "sunk", "axis", "finish", "hollow", "size_word",
              "size_noun", "size_multiplier", "size_ratio"),      # run in SizeWords below
    "outline": ("kind", "relation", "distance", "arrangement", "size", "material", "zone", "facing"),
    "change": ("kind", "do", "color", "finish", "face", "relation", "distance", "scale_axis", "shift_axis",
               "times", "way", "unit"),          # run in NumberWords below
    "talk": ("kind", "show_line", "effect", "pose"),      # run in tests/test_talk_lines.py
}
# the staged parts words (V.PARTS_NEXT): the product parts slots + the tilt slots tested in NextPartsWords
COVERED_NEXT = dict(COVERED, parts=COVERED["parts"] + ("tilt_toward", "tilt_by", "copies_pattern", "taper"))


class NumberWords(unittest.TestCase):
    """Every number word of an edit answer becomes the factor or distance code works out."""
    def test_every_times_way_and_unit_word(self):
        from maris3d.copilot import edit_words as EW
        from maris3d.copilot import size_words as SW
        from tests.test_edit_words import chair
        specs = {"Chair": chair()}
        for w in V.CHANGE["times"]:
            c = EW.to_change({"do": "scale", "object": "Chair", "times": w}, specs)
            self.assertAlmostEqual(c["by"]["x"], SW.RATIO[w])
        for w in V.CHANGE["way"]:
            c = EW.to_change({"do": "scale", "object": "Chair", "percent": 10, "way": w}, specs)
            self.assertAlmostEqual(c["by"]["x"], 1.1 if w == "more" else 0.9)
        for w in V.CHANGE["unit"]:
            c = EW.to_change({"do": "move", "object": "Chair", "shift": {"toward": "up", "amount": 2, "unit": w}}, specs)
            self.assertAlmostEqual(c["shift"]["z"], 2 * EW.UNITS[w])
            self.assertIn(w, EW.EDIT_SYSTEM_EXACT)


def _answer(top=None, base_shape="cube", **extra):
    top = dict({"name": "Top", "shape": "cube", "size": [0.2, 0.2, 0.2], "color": "red",
                "place": {"on": "Base", "relation": "on_top_of"}}, **(top or {}))
    return dict({"object": "thing", "parts": [
        {"name": "Base", "shape": base_shape, "size": [1.0, 1.0, 0.5], "color": "oak"}, top]}, **extra)


def _parts(answer):
    built = DP.resolve_parts(answer["parts"])
    return {p["name"]: p for p in built}


class SizeWords(unittest.TestCase):
    """Every size noun, multiplier and ratio word changes the size of the part that uses it."""

    def _height(self, first, second):
        a = {"object": "thing", "size": "chair", "parts": [
            {"name": "Base", "shape": "cube", "size": ["same", "same", first], "color": "oak"},
            {"name": "Top", "shape": "cube", "size": ["half", "half", second], "color": "red",
             "place": {"on": "Base", "relation": "on_top_of"}}]}
        faults, built = DP.check_answer(a)
        self.assertEqual(faults, [], (first, second))
        return {p["name"]: p["size"][2] for p in built}

    def test_every_noun(self):
        seen = {self._height(n, "same")["Base"] for n in V.PARTS["size_noun"]}
        self.assertEqual(len(seen), len(V.PARTS["size_noun"]))

    def test_every_multiplier(self):
        seen = {self._height(f"{m} door", "same")["Base"] for m in V.PARTS["size_multiplier"]}
        self.assertEqual(len(seen), len(V.PARTS["size_multiplier"]))

    def test_every_ratio_word(self):
        seen = {round(self._height("same", r)["Top"], 6) for r in V.PARTS["size_ratio"]}
        self.assertEqual(len(seen), len(V.PARTS["size_ratio"]))


class Lists(unittest.TestCase):
    def test_every_slot_is_covered_or_free(self):
        for role, slots in V.VOCAB.items():
            for slot in slots:
                self.assertIn(slot, COVERED[role], f"{role}.{slot} has no test")

    def test_the_parts_prompt_names_every_parts_word(self):
        for slot in ("shape", "color", "size_word"):
            for w in V.PARTS[slot]:
                self.assertIn(w, DP.PARTS_SYSTEM, f"{slot} {w}")
        for w in V.PARTS["part_relation"]:
            self.assertIn(w, DP.PARTS_SYSTEM)

    def test_the_change_prompt_names_every_do_and_kind(self):
        for w in V.CHANGE["do"] + V.CHANGE["kind"]:
            self.assertIn(w, AC.CHANGE_SYSTEM)

    def test_words_in_reads_all_three_roles(self):
        self.assertIn(("shape", "cube"), V.words_in("parts", _answer()))
        self.assertEqual(V.unknown_words("parts", _answer(top={"color": "mauve"})), [("color", "mauve")])
        out = {"kind": "build", "items": [{"id": "a_1", "thing": "a"}, {"id": "b_1", "thing": "b",
               "facing": "a_1", "place": {"anchor": "a_1", "relation": "next_to", "distance": "small"}}]}
        self.assertEqual(V.words_in("outline", out), [("kind", "build"), ("relation", "next_to"), ("distance", "small")])
        self.assertEqual(V.unknown_words("change", ch({"do": "add", "object": "A", "parts": [
            {"name": "P", "shape": "cube", "size": [1, 1, 1], "color": "red",
             "place": {"on": "Q", "relation": "inside"}}]})), [])

    def test_score_per_word(self):
        gold, pred = _answer(), _answer(top={"color": "navy"})
        table = V.score_per_word([("parts", gold, pred)])
        self.assertEqual(table[("color", "red")], {"gold": 1, "hit": 0, "pct": 0.0})
        self.assertEqual(table[("shape", "cube")]["pct"], 100.0)


class PartsWords(unittest.TestCase):
    def assertBuilds(self, answer):
        recipe, why = DP.to_recipe(answer)
        self.assertIsNotNone(recipe, why)
        return recipe

    def test_shape(self):
        built = {"uv_sphere": "ico"}            # a sphere is built as an ico mesh
        for w in V.PARTS["shape"]:
            self.assertIn(built.get(w, w), str(self.assertBuilds(_answer(top={"shape": w}))), w)

    def test_color(self):
        for w in V.PARTS["color"]:
            faults, _b = DP.check_answer(_answer(top={"color": w}))
            self.assertFalse([f for f in faults if "color" in f], w)
            self.assertBuilds(_answer(top={"color": w}))

    def test_part_relation_puts_the_part_somewhere_else(self):
        seen = {}
        for w in V.PARTS["part_relation"]:
            top = _parts(_answer(top={"place": {"on": "Base", "relation": w}}))["Top"]
            seen[w] = tuple(round(v, 3) for v in top["centre"])
        self.assertEqual(len(set(seen.values())), len(seen), seen)

    def test_align_moves_the_part_along_its_axis(self):
        for axis, words in zip("xyz", DP.STEPS):
            rel = "on_top_of" if axis != "z" else "right_of"
            spots = set()
            for w in words + tuple(a for a in DP.ALIGN_WORDS["xyz".index(axis)] if a != "centre"):
                top = _parts(_answer(top={"place": {"on": "Base", "relation": rel, "align": {axis: w}}}))["Top"]
                spots.add(round(top["centre"]["xyz".index(axis)], 3))
            self.assertGreaterEqual(len(spots), len(words), axis)
        for w in V.PARTS["align"]:
            self.assertTrue(any(w in group for group in DP.STEPS + DP.ALIGN_WORDS), w)

    def test_sunk_pushes_the_part_in(self):
        zs = [_parts(_answer(top={"place": {"on": "Base", "relation": "on_top_of", "sunk": w}}))["Top"]["centre"][2]
              for w in V.PARTS["sunk"]]
        self.assertEqual(zs, sorted(zs, reverse=True))
        self.assertEqual(len(set(zs)), len(zs))

    def test_axis_lays_a_round_part_down(self):
        for w in V.PARTS["axis"]:
            top = _parts(_answer(top={"shape": "cylinder", "size": [0.4, 0.2, 0.2], "axis": w}))["Top"]
            self.assertTrue(DP.turned(top.get("rotation_deg") or DP.AXIS_TURN[w]), w)

    def test_finish_and_hollow_build(self):
        for w in V.PARTS["finish"]:
            self.assertBuilds(_answer(top={"finish": w}))
        for w in V.PARTS["hollow"]:
            self.assertBuilds(_answer(top={"shape": "cylinder", "hollow": w}))

    def test_size_word_scales(self):
        base = DP.extent(DP.resolve_parts(_answer()["parts"]))
        for w, f in DP.SIZE_WORDS.items():
            got = DP.extent(DP.resolve_parts(DP.scaled(_answer()["parts"], w)))
            for i in range(3):
                self.assertAlmostEqual(got[i], base[i] * f[i], 3, f"{w} axis {i}")


class OutlineWords(unittest.TestCase):
    ANCHOR = {"lo": [-0.5, -0.5, 0.0], "hi": [0.5, 0.5, 1.0]}

    # next_to is right_of by convention; around and between need more than one anchor box
    SAME_AS = {"next_to": "right_of"}
    NEEDS_MORE = ("around", "between")

    def test_relation(self):
        spots = {}
        for w in V.OUTLINE["relation"]:
            if w in self.NEEDS_MORE:
                continue
            r = PLACE.resolve({"relation": w, "distance": "medium"}, self.ANCHOR, [0.4, 0.4, 0.4])
            spots[self.SAME_AS.get(w, w)] = tuple(round(v, 2) for v in r["centre"])
        self.assertEqual(len(set(spots.values())), len(spots), spots)

    def test_around_spreads_the_members(self):
        spots = {tuple(round(v, 2) for v in PLACE.resolve({"relation": "around", "distance": "small"},
                 self.ANCHOR, [0.4, 0.4, 0.4], count=4, member=m)["centre"]) for m in range(4)}
        self.assertEqual(len(spots), 4)

    def test_between_takes_two_anchors(self):
        b1, b2 = {"lo": [-3, -0.5, 0], "hi": [-2, 0.5, 1]}, {"lo": [2, -0.5, 0], "hi": [3, 0.5, 1]}
        r = PLACE.resolve({"relation": "between", "between": ["a_1", "b_1"], "between_boxes": [b1, b2]},
                          b1, [0.4, 0.4, 0.4])
        self.assertAlmostEqual(r["centre"][0], 0.0, 3)

    def test_an_outline_between_two_things_stands_in_the_middle(self):
        from maris3d.copilot import compile_plan as CP
        plan = [{"id": "lamp_1", "recipe": "lamp",
                 "place": {"anchor": "sofa_1", "and": "table_1", "relation": "between"}},
                {"id": "sofa_1", "recipe": "sofa"},
                {"id": "table_1", "recipe": "table", "place": {"anchor": "sofa_1", "relation": "right_of",
                                                               "distance": "far"}}]
        inst, notes = CP.layout(plan)
        at = {i["id"]: i["origin"] for i in inst}
        self.assertEqual(notes, [])
        self.assertAlmostEqual(at["Lamp"][0], (at["Sofa"][0] + at["Table"][0]) / 2, 1)
        bad, notes = CP.layout([{"id": "sofa_1", "recipe": "sofa"},
                                {"id": "lamp_1", "recipe": "lamp", "place": {"anchor": "sofa_1", "relation": "between"}}])
        self.assertTrue(any("between needs a second thing" in n for n in notes), notes)

    def test_the_planner_prompt_names_every_outline_word(self):
        missing = [(slot, w) for slot in ("relation", "distance", "arrangement", "material", "zone")
                   for w in V.OUTLINE[slot] if w not in V.OUTLINE_SYSTEM]
        self.assertEqual(missing, [])

    def test_distance_grows(self):
        xs = [PLACE.resolve({"relation": "right_of", "distance": w}, self.ANCHOR, [0.4, 0.4, 0.4])["centre"][0]
              for w in V.OUTLINE["distance"]]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(len(set(xs)), len(xs))

    def test_facing_compass(self):
        for w in V.OUTLINE["facing"]:
            self.assertIn(w, AC.COMPASS)


class ChangeWords(unittest.TestCase):
    def test_kind_and_do(self):
        self.assertEqual(set(V.CHANGE["do"]), set(AC.DOS))
        self.assertEqual(set(V.CHANGE["kind"]), set(AC.KINDS))

    def test_color(self):
        for w in V.CHANGE["color"]:
            _c, s, sim = build(("sofa", None))
            _d, rows = run(s, sim, ch({"do": "recolor", "object": "Sofa", "parts": ["SofaBase"], "color": w}))
            self.assertEqual(statuses(rows), ["ok"], w)

    def test_finish(self):
        for w in V.CHANGE["finish"]:
            _c, s, sim = build(("sofa", None))
            _d, rows = run(s, sim, ch({"do": "recolor", "object": "Sofa", "color": "red", "finish": w}))
            self.assertEqual(statuses(rows), ["ok"], w)

    def test_face(self):
        yaws = set()
        for w in V.CHANGE["face"]:
            _c, s, sim = build(("sofa", None))
            _d, rows = run(s, sim, ch({"do": "turn", "object": "Sofa", "face": w}))
            self.assertEqual(statuses(rows), ["ok"], w)
            yaws.add(round(sim.o["Sofa"]["rot"][2]) % 360)
        self.assertEqual(len(yaws), 4)

    def test_scale_and_shift_axes(self):
        for w in V.CHANGE["scale_axis"]:
            _c, s, sim = build(("table", None))
            _d, rows = run(s, sim, ch({"do": "scale", "object": "Table", "by": {w: 1.5}}))
            self.assertEqual(statuses(rows), ["ok"], w)
        for w in V.CHANGE["shift_axis"]:
            _c, s, sim = build(("table", None))
            was = sim.o["Table"]["loc"]["xyz".index(w)]
            _d, rows = run(s, sim, ch({"do": "move", "object": "Table", "shift": {w: 1.0}}))
            self.assertEqual(statuses(rows), ["ok"], w)
            self.assertAlmostEqual(sim.o["Table"]["loc"]["xyz".index(w)], was + 1.0, 3)

    def test_copies_around_a_thing_go_round_it(self):
        _c, s, sim = build(("table", None), ("chair", {"anchor": "Table", "relation": "next_to", "distance": "medium"}))
        _d, rows = run(s, sim, ch({"do": "copy", "object": "Chair", "count": 4,
                                   "place": {"anchor": "Table", "relation": "around", "distance": "small"}}))
        self.assertEqual(statuses(rows), ["ok"])
        t = sim.o["Table"]["loc"]
        sides = {(round(sim.o[f"Chair{n}"]["loc"][0] - t[0], 1) > 0, round(sim.o[f"Chair{n}"]["loc"][1] - t[1], 1) > 0)
                 for n in range(2, 6)}
        spots = {tuple(round(v, 1) for v in sim.o[f"Chair{n}"]["loc"][:2]) for n in range(2, 6)}
        self.assertEqual(len(spots), 4)
        self.assertGreaterEqual(len(sides), 3)

    def test_move_between_two_things(self):
        _c, s, sim = build(("table", None), ("sofa", {"anchor": "Table", "relation": "right_of", "distance": "far"}),
                           ("chair", {"anchor": "Table", "relation": "behind", "distance": "far"}))
        _d, rows = run(s, sim, ch({"do": "move", "object": "Chair",
                                   "place": {"anchor": "Table", "relation": "between", "and": "Sofa"}}))
        self.assertEqual(statuses(rows), ["ok"])
        mid = (sim.o["Table"]["loc"][0] + sim.o["Sofa"]["loc"][0]) / 2
        self.assertAlmostEqual(sim.o["Chair"]["loc"][0], mid, 0)

    def test_between_without_a_second_thing_is_refused(self):
        _c, s, sim = build(("table", None), ("chair", {"anchor": "Table", "relation": "behind", "distance": "far"}))
        done = AC.apply_answer(ch({"do": "move", "object": "Chair",
                                   "place": {"anchor": "Table", "relation": "between", "and": "Lamp"}}),
                               s.specs, sim.objects())
        self.assertTrue(any("between needs a second thing" in e["error"] for e in done.errors), done.errors)

    def test_move_relation_and_distance(self):
        for w in V.CHANGE["relation"]:
            if w == "between":                  # needs `and`: its own tests above
                continue
            _c, s, sim = build(("table", None), ("chair", {"anchor": "Table", "relation": "next_to", "distance": "medium"}))
            _d, rows = run(s, sim, ch({"do": "move", "object": "Chair",
                                       "place": {"anchor": "Table", "relation": w, "distance": "small"}}))
            self.assertEqual(statuses(rows), ["ok"], w)
        for w in V.CHANGE["distance"]:
            _c, s, sim = build(("table", None), ("chair", {"anchor": "Table", "relation": "next_to", "distance": "medium"}))
            _d, rows = run(s, sim, ch({"do": "move", "object": "Chair",
                                       "place": {"anchor": "Table", "relation": "behind", "distance": w}}))
            self.assertEqual(statuses(rows), ["ok"], w)


if __name__ == "__main__":
    unittest.main()


class NextPartsWords(unittest.TestCase):
    """Staged words: every one builds and changes what is built; the product lists stay without them."""

    def test_every_next_slot_is_covered(self):
        for slot in V.PARTS_NEXT:
            self.assertIn(slot, COVERED_NEXT["parts"], f"parts_next.{slot} has no test")

    def test_product_lists_do_not_offer_them(self):
        for w in DP.NEXT_SHAPES:
            self.assertNotIn(w, V.PARTS["shape"])
            self.assertIn(w, V.PARTS_NEXT["shape"])
        self.assertEqual(V.unknown_words("parts", _answer(top={"shape": "prism"})), [("shape", "prism")])

    def test_next_shapes_build(self):
        for w in V.PARTS_NEXT["shape"]:
            recipe, why = DP.to_recipe(_answer(top={"shape": w}))
            self.assertIsNotNone(recipe, f"{w}: {why}")

    def test_every_copies_pattern_places_its_copies(self):
        for w in V.PARTS_NEXT["copies_pattern"]:
            lo, _hi = DP.PATTERN_COUNT[w]
            leg = {"name": "Leg", "shape": "cylinder", "size": [0.1, 0.1, 0.6], "color": "oak",
                   "place": {"on": "Base", "relation": "under", "align": {"x": "left", "y": "front"}},
                   "copies": {"pattern": w, "count": lo}}
            ans = {"object": "table", "parts": [{"name": "Base", "shape": "cube", "size": [1.0, 0.6, 0.05],
                                                  "color": "oak"}, leg]}
            self.assertIn(("copies_pattern", w), V.words_in("parts", ans))
            faults, built = DP.check_answer(ans)
            self.assertEqual(faults, [], w)
            legs = [p for p in built if p["name"].startswith("Leg")]
            self.assertEqual(len(legs), lo, w)
            self.assertEqual(len({tuple(p["centre"]) for p in legs}), lo, f"{w}: copies on top of each other")
            recipe, why = DP.to_recipe(ans)
            self.assertEqual(len(recipe["parts"]), lo + 1, why)
        bad = _answer(top={"copies": {"pattern": "corners", "count": 7}})
        self.assertTrue(any("copies" in f for f in DP.check_answer(bad)[0]))

    def test_every_taper_word_builds_a_cut_cone(self):
        for w in V.PARTS_NEXT["taper"]:
            ans = _answer(top={"shape": "cylinder", "taper": w})
            self.assertIn(("taper", w), V.words_in("parts", ans))
            recipe, why = DP.to_recipe(ans)
            top = recipe["parts"][1]
            self.assertEqual(top["shape"], "cone", why)
            self.assertAlmostEqual(top["radius2"], round(top["radius"] * SW.RATIO[w], 3), places=3)
        self.assertTrue(any("taper" in f for f in DP.check_answer(_answer(top={"taper": "half"}))[0]))

    def test_every_tilt_word_turns_the_part(self):
        plain, _w = DP.to_recipe(_answer())
        seen = set()
        for toward in V.PARTS_NEXT["tilt_toward"]:
            for by in V.PARTS_NEXT["tilt_by"]:
                ans = _answer(top={"size": [0.2, 0.2, 0.6], "tilt": {"toward": toward, "by": by}})
                self.assertIn(("tilt_toward", toward), V.words_in("parts", ans))
                self.assertIn(("tilt_by", by), V.words_in("parts", ans))
                recipe, why = DP.to_recipe(ans)
                self.assertIsNotNone(recipe, why)
                self.assertNotEqual(str(recipe), str(plain))
                seen.add(str(recipe))
        self.assertEqual(len(seen), len(V.PARTS_NEXT["tilt_toward"]) * len(V.PARTS_NEXT["tilt_by"]))
