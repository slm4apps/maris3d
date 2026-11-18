# SPDX-License-Identifier: Apache-2.0
"""The word lines say / show maris / ask / clear messages: vocabulary, checking by code,
the word edit path, and the talk-rows generator."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from maris3d.copilot import edit_words as EW
from maris3d.copilot import show as S
from maris3d.copilot import vocabulary as V
from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Session

from tests.test_apply_change import Sim
from tests.test_change_words import Runtime, words

REL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "internal", "release", "scene-tests", "rel")
MAIN_PARTS = os.path.join(REL, "data-parts-set2", "train.jsonl")


class Lines(unittest.TestCase):
    def test_every_word_of_every_talk_slot_applies(self):
        for effect in V.TALK["effect"]:
            acts, errs = S.apply_lines([{"line": "say", "text": "Hi!", "effect": effect}])
            self.assertEqual((errs, acts[0]["effect"]), ([], effect))
        for pose in V.TALK["pose"]:
            acts, errs = S.apply_lines([{"line": "show maris", "pose": pose}])
            self.assertEqual((errs, acts[0]["pose"]), ([], pose))
        self.assertEqual(S.apply_lines([{"line": "show maris", "pose": "think"}])[0][0]["animation"], "weave")
        for line in V.TALK["show_line"]:
            self.assertIn(("show_line", line), V.words_in("talk", {"show": [{"line": line}]}))
        self.assertEqual(V.words_in("talk", {"kind": "talk"}), [("kind", "talk")])
        self.assertEqual(V.unknown_words("talk", {"kind": "talk", "show": [{"line": "shout", "effect": "boom",
                                                                           "pose": "fly"}]}),
                         [("show_line", "shout"), ("effect", "boom"), ("pose", "fly")])

    def test_defaults_and_ask(self):
        acts, errs = S.apply_lines([{"line": "say", "text": "Hi"},
                                    {"line": "ask", "question": "Which chair?", "about": "Chair",
                                     "choices": ["Chair", "Chair2"]}], things=["Chair", "Chair2"])
        self.assertEqual(errs, [])
        self.assertEqual([a["effect"] for a in acts], ["type", "type"])
        self.assertEqual(acts[1]["choices"], ["Chair", "Chair2"])

    def test_bad_lines_are_dropped_and_reported_never_repaired(self):
        acts, errs = S.apply_lines([{"line": "say", "text": ""}, {"line": "say", "text": "x" * 500},
                                    {"line": "say", "text": "ok", "effect": "boom"},
                                    {"line": "show maris", "pose": "fly"}])
        self.assertEqual((acts, len(errs)), ([], 4))
        acts, errs = S.apply_lines([{"line": "ask", "question": "q", "about": "Nothing"},
                                    {"line": "ask", "question": "q", "choices": ["a", "b", "c", "d"]},
                                    {"line": "jump"}], things=["Chair"])
        self.assertEqual((acts, len(errs)), ([], 3))
        acts, errs = S.apply_lines([{"line": "say", "text": "fine"}, "nonsense"])
        self.assertEqual([a["op"] for a in acts], ["say"])
        self.assertEqual(len(errs), 1)
        self.assertEqual(S.apply_lines("hello"), ([], ["show is a list of lines"]))
        self.assertEqual(S.apply_lines([{"line": "say", "text": "a"}] * 6)[0].__len__(), S.MAX_LINES)

    def test_clear_drops_earlier_lines(self):
        acts, _ = S.apply_lines([{"line": "say", "text": "a"}, {"line": "clear messages"},
                                 {"line": "say", "text": "b"}])
        self.assertEqual([a["op"] for a in acts], ["clear", "say"])

    def test_the_trained_prompt_is_untouched_and_the_show_prompt_names_every_word(self):
        self.assertTrue(EW.EDIT_SYSTEM_SHOW.startswith(EW.EDIT_SYSTEM))
        self.assertNotIn("maris", EW.EDIT_SYSTEM)
        for w in V.TALK["show_line"] + V.TALK["effect"] + V.TALK["pose"] + V.TALK["kind"]:
            self.assertIn(w, EW.EDIT_SYSTEM_SHOW)


class WordPath(unittest.TestCase):
    def copilot(self, replies):
        cop = Copilot(Runtime(replies, ("edit",)), Session(Sim()))
        cop.run_items([{"recipe": "chair"}])
        cop.runtime.asked.clear()
        cop.heard = []
        cop.show = cop.heard.extend
        return cop

    def test_talk_answer_shows_and_changes_nothing(self):
        cop = self.copilot([words(kind="talk", show=[{"line": "say", "text": "I'm Maris3D.", "effect": "rise"},
                                                      {"line": "show maris", "pose": "wave"}])])
        n, specs = len(cop.session.batches), dict(cop.session.specs)
        result = cop.run_auto("who are you")
        self.assertEqual([a["op"] for a in result.show], ["say", "maris"])
        self.assertEqual(cop.heard, result.show)
        self.assertEqual(result.calls, [])
        self.assertEqual(cop.session.specs, specs)
        self.assertEqual(len(cop.session.batches), n)

    def test_clear_messages_line_reaches_the_hook(self):
        cop = self.copilot([words(kind="talk", show=[{"line": "clear messages"}])])
        cop.run_auto("clean up")
        self.assertEqual(cop.heard, [{"op": "clear"}])

    def test_a_change_may_carry_a_say_and_still_runs(self):
        cop = self.copilot([words({"do": "recolor", "object": "Chair", "color": "red"},
                                  show=[{"line": "say", "text": "Done!"}])])
        result = cop.run_auto("make the chair red")
        self.assertTrue(result.calls)
        self.assertEqual(result.show[0]["text"], "Done!")

    def test_question_with_an_ask_line_alone_still_asks(self):
        cop = self.copilot([words(kind="question", show=[{"line": "ask", "question": "Which one?", "about": "Chair",
                                                           "choices": ["Chair"]}])])
        result = cop.run_auto("make it red")
        self.assertEqual(result.text, "Which one?")
        self.assertEqual(result.show[0]["about"], "Chair")

    def test_build_answer_show_goes_out_before_the_build_flow(self):
        cop = self.copilot([words(kind="build", show=[{"line": "say", "text": "On it!"}])])
        self.assertIsNone(cop.run_change_words("hi, make me a lamp"))
        self.assertEqual(cop.heard[0]["text"], "On it!")

    def test_bad_line_is_an_error_the_rest_still_runs(self):
        cop = self.copilot([words({"do": "recolor", "object": "Chair", "color": "red"},
                                  show=[{"line": "say", "text": "ok", "effect": "boom"}])])
        result = cop.run_auto("make the chair red")
        self.assertTrue(result.calls)
        self.assertTrue(any("effect" in e["error"] for e in result.errors))
        self.assertEqual(result.show, [])

    def test_a_hook_that_breaks_never_loses_the_work(self):
        cop = self.copilot([words(kind="talk", show=[{"line": "say", "text": "hi"}])])
        cop.show = lambda actions: 1 / 0
        self.assertEqual(cop.run_auto("hi").show[0]["op"], "say")


@unittest.skipUnless(os.path.exists(MAIN_PARTS), "parts data not here")
class Generator(unittest.TestCase):
    def run_gen(self, out, *args):
        return subprocess.run([sys.executable, os.path.join(REL, "make_talk_data.py"), "--out", out, *args],
                              capture_output=True)

    def test_rows_have_the_edit_words_format_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "talk")
            self.assertEqual(self.run_gen(out, "--scale", "0.15").returncode, 0)
            ref = {"id", "split", "kind", "dos", "clarified", "objects", "n_things", "tokens", "messages"}
            ops, groups = set(), set()
            for split in ("train", "val", "heldout"):
                rows = [json.loads(line) for line in open(os.path.join(out, split + ".jsonl"))]
                self.assertTrue(rows)
                for r in rows:
                    self.assertTrue(ref <= set(r))
                    self.assertEqual([m["role"] for m in r["messages"]], ["system", "user", "assistant"])
                    self.assertEqual(r["messages"][0]["content"], EW.EDIT_SYSTEM_SHOW)
                    ans = EW.unwrap(r["messages"][2]["content"])
                    self.assertEqual(V.unknown_words("talk", ans), [])
                    self.assertEqual(ans["kind"], r["kind"])
                    ops.update(a["op"] for a in EW.apply_words(ans, {}).show)
                    groups.add(r["talk_group"])
                    if r["talk_group"] == "plain":
                        self.assertNotIn("show", ans)         # no say on a plain build
            self.assertEqual(ops, {"say", "maris", "clear"} | ({"ask"} & ops))
            self.assertEqual(groups, {"about", "small", "scope", "clear", "ask", "mixed", "plain"})
            self.assertNotEqual(self.run_gen(out).returncode, 0)        # never overwrites


if __name__ == "__main__":
    unittest.main()
