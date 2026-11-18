# SPDX-License-Identifier: Apache-2.0
"""The copilot tells its listeners what it is doing; show.react says what the show does."""
import unittest

from maris3d.copilot import show
from maris3d.copilot.loop import Copilot, Result
from maris3d.copilot.session import Session

from tests.test_apply_change import Sim
from tests.test_change_words import Runtime, words


class React(unittest.TestCase):
    def test_every_harness_event_has_a_reaction_the_director_knows(self):
        samples = [("request", {}), ("tool_call", {"name": "Chair"}),
                   ("part", {"name": "A", "verdict": "exact"}), ("part", {"name": "A", "verdict": "moved"}),
                   ("part", {"name": "A", "verdict": "missing"}), ("part", {"name": "A", "unfixed": True}),
                   ("done", {}), ("done", {"unfixed": 1}), ("done", {"kind": "question"}),
                   ("done", {"kind": "cannot"}), ("error", {"text": "x"})]
        for name, info in samples:
            act = show.react(name, info)
            self.assertIn(act["event"], show.REACTIONS, (name, info))
        self.assertEqual({n for n, _ in samples}, set(show.HARNESS_EVENTS))

    def test_part_faces(self):
        def face(v, **k):
            return show.REACTIONS[show.react("part", dict(verdict=v, **k))["event"]]
        self.assertEqual(face("exact"), ("inspect", "happy"))
        self.assertEqual(face("moved"), ("inspect", "grumpy"))
        self.assertEqual(face("missing"), ("inspect", "surprised"))
        self.assertEqual(face("moved", unfixed=True), ("sad", "sad"))

    def test_done_woo_only_when_nothing_is_wrong(self):
        self.assertEqual(show.REACTIONS[show.react("done", {})["event"]][1], "woo")
        self.assertEqual(show.react("done", {"unfixed": 2})["event"], "still_wrong")
        self.assertIsNone(show.react("done", {"unfixed": 2, "text": "hello"})["say"])

    def test_say_only_on_done_and_asking_and_is_cut(self):
        self.assertEqual(show.react("done", {"text": "Made a chair."})["say"], "Made a chair.")
        self.assertEqual(show.react("done", {"text": "Which one?", "kind": "question"})["kind"], "question")
        self.assertLessEqual(len(show.react("done", {"text": "x " * 200})["say"]), show.SAY_MAX)
        self.assertIsNone(show.react("error", {"text": "server down"})["say"])
        self.assertIsNone(show.react("request", {"text": "make a chair"})["say"])

    def test_unknown_event_or_verdict_is_nothing(self):
        self.assertIsNone(show.react("bogus"))
        self.assertIsNone(show.react("part", {"verdict": "??"}))

    def test_working_and_inspect_have_their_own_clocks(self):
        d = show.Director()
        self.assertIsNotNone(d.cue("working", 0.0))
        self.assertIsNotNone(d.cue("built_exact", 0.1))
        self.assertIsNone(d.cue("working", 0.5))
        self.assertIsNone(d.cue("built_exact", 0.6))
        self.assertIsNotNone(d.cue("working", 2.0))


class Loop(unittest.TestCase):
    def copilot(self, replies=(), roles=("edit",)):
        sim = Sim()
        cop = Copilot(Runtime(list(replies), roles), Session(sim))
        self.log = []
        cop.listeners.append(lambda n, i: self.log.append((n, i)))
        return cop, sim

    def names(self):
        return [n for n, _ in self.log]

    def test_a_build_tells_calls_and_parts(self):
        cop, _ = self.copilot()
        cop.run_items([{"recipe": "chair"}])
        self.assertIn("tool_call", self.names())
        parts = [i for n, i in self.log if n == "part"]
        self.assertTrue(parts)
        self.assertTrue(all(p["verdict"] == "exact" and not p["unfixed"] for p in parts))

    def test_a_missing_part_is_told_as_missing(self):
        cop, sim = self.copilot()
        real = cop.session.apply
        dropped = []

        def apply(calls):
            out = real(calls)
            if not dropped and calls and calls[0].get("tool") == "add_primitive":
                dropped.append(calls[0]["name"])
                sim.o.pop(calls[0]["name"], None)       # the part never arrived
            return out
        cop.session.apply = apply
        cop.run_items([{"recipe": "chair"}])
        verdicts = {i["name"]: i["verdict"] for n, i in self.log if n == "part"}
        self.assertEqual(verdicts[dropped[0]], "missing")

    def test_run_auto_tells_request_then_done(self):
        cop, _ = self.copilot([words({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"})])
        cop.run_items([{"recipe": "chair"}])
        self.log.clear()
        cop.run_auto("make the seat red")
        self.assertEqual(self.names()[0], "request")
        self.assertEqual(self.names()[-1], "done")

    def test_server_failure_is_an_error_event(self):
        cop, _ = self.copilot()
        cop._emit_done(Result(api_error="boom"))
        self.assertEqual(self.log[-1][0], "error")

    def test_exception_is_an_error_event_and_still_raises(self):
        cop, _ = self.copilot()
        cop._run_auto = lambda request: 1 / 0
        with self.assertRaises(ZeroDivisionError):
            cop.run_auto("x")
        self.assertEqual(self.names(), ["request", "error"])

    def test_no_listener_no_change_and_a_broken_listener_is_ignored(self):
        cop, _ = self.copilot()
        cop.listeners[:] = [lambda n, i: 1 / 0]
        cop.run_items([{"recipe": "chair"}])          # does not raise
        bare = Copilot(Runtime(), Session(Sim()))
        bare.run_items([{"recipe": "chair"}])
        self.assertEqual(bare.listeners, [])


if __name__ == "__main__":
    unittest.main()
