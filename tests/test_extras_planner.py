# SPDX-License-Identifier: Apache-2.0
import unittest

from maris3d.extras.planner import plan as P, source, validate
from maris3d.extras.recipes import library as L


class PlannerTests(unittest.TestCase):
    def test_example_is_valid_and_bad_plans_are_rejected(self):
        self.assertEqual(validate.check(P.example()), (True, None))
        bad = P.example()
        bad["relations"] = [{"part": "body", "rel": "on_top_of", "ref": "roof"}]
        self.assertFalse(validate.check(bad)[0])
        self.assertFalse(validate.check("{not json")[0])

    def test_default_config_is_offline_recipes(self):
        cfg = source.config_from({})
        self.assertEqual(cfg.source, "recipes")
        self.assertIsNone(source.make_api_planner(cfg))
        with self.assertRaises(source.ConfigError):
            source.config_from({"source": "api"})

    def test_fallback_chain_never_returns_invalid_plan(self):
        cfg = source.config_from({})
        res = source.resolve("x", cfg, recipe_lookup=lambda p: {"parts": []}, self_plan=lambda p: P.example())
        self.assertEqual(res.source, "self")
        self.assertTrue(any("rejected" in r for r in res.reasons))


class RecipeTests(unittest.TestCase):
    def test_recipes_use_only_native_tools(self):
        from maris3d.copilot.protocol import load_tools
        known = set(load_tools())
        recipes = L.all_recipes()
        self.assertGreaterEqual(len(recipes), 150)
        self.assertEqual([(r["id"], c["tool"]) for r in recipes for c in r["calls"] if c["tool"] not in known], [])

    def test_lookup_returns_valid_plan(self):
        plan = L.lookup_plan("a table")
        if plan is not None:
            self.assertEqual(validate.check(plan), (True, None))


if __name__ == "__main__":
    unittest.main()
