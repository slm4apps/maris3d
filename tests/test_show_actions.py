# SPDX-License-Identifier: Apache-2.0
"""The model's show actions -> the primitive steps and the thread-safe queue the add-on applies."""
import threading
import unittest

from maris3d.copilot import show
from maris3d.copilot.loop import Copilot, Result


class Steps(unittest.TestCase):
    def test_actions_map_to_steps(self):
        acts, _ = show.apply_lines([
            {"line": "say", "text": "Hi"}, {"line": "show maris", "pose": "wave"},
            {"line": "ask", "question": "Which?", "choices": ["red", "blue"]}])
        st = show.steps(acts)
        self.assertEqual(st[0], ("text", "Hi", "type", "say", None))
        self.assertEqual(st[1][0], "pose")
        self.assertEqual(st[2][3], "question")
        self.assertEqual([s[1] for s in st[3:]], ["1. red", "2. blue"])
        self.assertTrue(all(s[3] == "choice" and s[2] == "pop" for s in st[3:]))
        self.assertEqual(show.steps([{"op": "clear"}, {"op": "bogus"}]), [("clear",)])

    def test_queue_hands_over_across_threads(self):
        q = show.ActionQueue()
        t = threading.Thread(target=q.put, args=([{"op": "say", "text": "x", "effect": "pop"}],))
        t.start()
        t.join()
        self.assertEqual(len(q), 1)
        self.assertEqual(q.take(), [("text", "x", "pop", "say", None)])
        self.assertEqual(q.take(), [])
        q.put(None)
        self.assertEqual(len(q), 0)

    def test_copilot_hands_actions_to_the_hook(self):
        got = []
        c = Copilot.__new__(Copilot)
        c.show = got.append
        c._say = lambda *a, **k: None
        r = Result.__new__(Result)
        r.show = []
        c._show(r, [{"op": "clear"}])
        self.assertEqual(got, [[{"op": "clear"}]])


class Question(unittest.TestCase):
    def test_last_ask_with_choices_is_the_open_question(self):
        acts, _ = show.apply_lines([
            {"line": "ask", "question": "Which one?"},
            {"line": "say", "text": "Two chairs here"},
            {"line": "ask", "question": "Which chair?", "choices": ["Chair", "Chair_2"]}],
            things=["Chair", "Chair_2"])
        self.assertEqual(show.question_of(acts),
                         {"question": "Which chair?", "about": None, "choices": ["Chair", "Chair_2"]})
        self.assertIsNone(show.question_of([{"op": "ask", "question": "Which?", "choices": []}]))
        self.assertIsNone(show.question_of(None))

    def test_answer_prompt_keeps_the_request_words(self):
        self.assertEqual(show.answer_prompt("make the chair red.", "Chair_2"), "make the chair red (Chair_2)")
        self.assertEqual(show.answer_prompt("", " blue "), "blue")

    def test_addon_has_the_answer_button(self):
        import os
        src = open(os.path.join(os.path.dirname(__file__), "..", "src", "maris3d", "addon", "__init__.py")).read()
        self.assertIn('"copt.maris_answer"', src)
        self.assertIn("COPT_OT_maris_answer,", src)
        self.assertIn("question_of(actions)", src)


if __name__ == "__main__":
    unittest.main()
