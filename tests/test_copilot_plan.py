# SPDX-License-Identifier: Apache-2.0
"""The plan turn: the outline prompt, no tools, the answer checked and never applied."""
import json
import unittest

from maris3d.copilot import plan, vocabulary
from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Session
from tests.test_copilot_core import FakeExec

GOOD = json.dumps({"kind": "build", "items": [{"id": "chair_1", "thing": "chair", "count": 4,
                                                "material": "oak", "zone": "dining"}]})


class FakeRuntime:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, tool_names, max_tokens=1024, role=None):
        self.seen.append({"messages": [dict(m) for m in messages], "tools": list(tool_names),
                          "role": role, "max_tokens": max_tokens})
        return self.replies.pop(0)


class PlanTurn(unittest.TestCase):
    def test_good_plan_is_validated_and_nothing_runs(self):
        rt, ex = FakeRuntime([{"content": GOOD}]), FakeExec()
        res = Copilot(rt, Session(ex))._run_plan("four oak chairs in the dining room")
        self.assertEqual(res.mode, "plan")
        self.assertEqual(res.plan["items"][0]["recipe"], "chair")
        self.assertEqual(res.plan_error, "")
        self.assertEqual(res.calls, [])
        self.assertEqual(ex.objects(), [])
        ask = rt.seen[0]
        self.assertEqual(ask["tools"], [])
        self.assertEqual(ask["role"], "planner")
        self.assertEqual(ask["max_tokens"], 2800)
        self.assertEqual(ask["messages"][0], {"role": "system", "content": vocabulary.OUTLINE_SYSTEM})
        self.assertEqual(ask["messages"][1], {"role": "user", "content": "four oak chairs in the dining room"})

    def test_bad_json_is_reported_and_not_retried_or_applied(self):
        rt, ex = FakeRuntime([{"content": "I would add four chairs."}]), FakeExec()
        res = Copilot(rt, Session(ex))._run_plan("four chairs")
        self.assertIsNone(res.plan)
        self.assertIn("malformed JSON", res.plan_error)
        self.assertEqual(ex.objects(), [])
        self.assertEqual(len(rt.seen), 1)  # one ask: no retry, no other route

    def test_a_question_answer_is_not_a_plan(self):
        rt = FakeRuntime([{"content": json.dumps({"kind": "question", "say": "Which chair?", "items": []})}])
        res = Copilot(rt, Session(FakeExec()))._run_plan("the chair")
        self.assertEqual(res.plan_error, "Which chair?")

    def test_a_coordinate_is_refused(self):
        reply = json.dumps({"items": [{"id": "a", "thing": "chair", "location": [1, 2, 3]}]})
        res = Copilot(FakeRuntime([{"content": reply}]), Session(FakeExec()))._run_plan("a chair")
        self.assertIn("must not carry location", res.plan_error)

    def test_a_tool_call_reply_is_never_executed(self):
        reply = '<tool_call>{"name": "add_primitive", "arguments": {"shape": "cube"}}</tool_call>'
        ex = FakeExec()
        res = Copilot(FakeRuntime([{"content": reply}]), Session(ex))._run_plan("add a cube")
        self.assertTrue(res.plan_error)
        self.assertEqual(ex.objects(), [])

    def test_a_server_failure_is_an_api_error(self):
        class Down:
            def chat(self, *a, **k):
                raise RuntimeError("down")

        res = Copilot(Down(), Session(FakeExec()))._run_plan("a chair")
        self.assertIn("down", res.api_error)
        self.assertIsNone(res.plan)

    def test_fenced_and_tagged_json_still_parse(self):
        for reply in ('```json\n%s\n```' % GOOD, "<tool_call>%s</tool_call>" % GOOD):
            obj, reason = plan.parse_reply(reply)
            self.assertIsNone(reason)
            self.assertEqual(obj["items"][0]["thing"], "chair")

    def test_no_plan_is_said_plainly_and_builds_nothing(self):
        ex = FakeExec()
        res = Copilot(FakeRuntime([{"content": "no idea"}]), Session(ex)).run_auto("a flurb")
        self.assertIn("nothing was added", res.text)
        self.assertEqual(res.calls, [])


if __name__ == "__main__":
    unittest.main()
