# SPDX-License-Identifier: Apache-2.0
import unittest

from maris3d.extras.checks import evaluate, make_checker, unchanged_failures

TABLE = [
    {"name": "Top", "type": "MESH", "loc": [0, 0, 0.75], "dims": [2, 1, 0.1]},
    {"name": "Leg", "type": "MESH", "loc": [0.9, 0.4, 0.35], "dims": [0.1, 0.1, 0.7]},
    {"name": "Cup", "type": "MESH", "loc": [0, 0, 0.9], "dims": [0.1, 0.1, 0.2]},
]


class Checks(unittest.TestCase):
    def test_presence_count_size_position(self):
        ok = [{"type": "presence", "name": "Top"}, {"type": "count", "min": 3, "max": 3, "object_type": "MESH"},
              {"type": "size", "name": "Top", "axis": "x", "min": 1.5, "max": 2.5}, {"type": "position", "name": "Top", "axis": "z", "value": 0.75}]
        self.assertEqual(evaluate(TABLE, ok), [])
        bad = evaluate(TABLE, [{"type": "presence", "name": "Lamp"}, {"type": "count", "min": 5, "max": 6}])
        self.assertEqual(len(bad), 2)

    def test_relations(self):
        self.assertEqual(evaluate(TABLE, [{"type": "relation", "relation": "on", "object": "Cup", "target": "Top"}]), [])
        self.assertTrue(evaluate(TABLE, [{"type": "relation", "relation": "on", "object": "Leg", "target": "Top"}]))
        self.assertTrue(evaluate(TABLE, [{"type": "resting", "object": "Top"}]))
        self.assertEqual(evaluate(TABLE, [{"type": "resting", "object": "Leg"}]), [])

    def test_overlap_and_bad_items(self):
        self.assertTrue(evaluate(TABLE + [dict(TABLE[1], name="Dup")], [{"type": "no_overlap"}]))
        self.assertEqual(evaluate(TABLE, [{"type": "no_overlap"}]), [])
        self.assertIn("missing required fields", evaluate(TABLE, [{"type": "size", "name": "Top"}])[0])
        self.assertIn("unsupported", evaluate(TABLE, [{"type": "nope"}])[0])

    def test_edit_guard(self):
        after = [dict(o) for o in TABLE]
        after[2] = dict(after[2], loc=[1, 0, 0.9])
        self.assertEqual(unchanged_failures(TABLE, after, {"Cup": ["loc"]}), [])
        self.assertEqual(unchanged_failures(TABLE, after), ["Cup changed unexpected field loc"])
        self.assertEqual(unchanged_failures(TABLE, after[:2], {"Cup": ["__deleted__"]}), [])

    def test_make_checker(self):
        self.assertEqual(make_checker([{"type": "presence", "name": "Top"}])(TABLE), [])


if __name__ == "__main__":
    unittest.main()
