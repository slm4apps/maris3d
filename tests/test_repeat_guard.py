# SPDX-License-Identifier: Apache-2.0
"""A model that repeats the identical call is stopped, and the repeats never reach the scene.

Measured on "a bar stool with a seat, four legs and a footrest rail": at repeat penalty 1.1
(Ollama's default on its OpenAI-compatible API) the model wrote one unnamed cube and then that same
call until the token limit.
"""
import json
import unittest

from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Executor, Session


class FakeExec(Executor):
    def __init__(self):
        self.objs = []

    def reset(self):
        self.objs = []

    def run_call(self, call):
        self.objs.append({"name": call.get("name", "Cube"), "type": "MESH", "loc": [0, 0, 0]})
        return True, None

    def objects(self):
        return list(self.objs)


class FakeRuntime:
    def __init__(self, replies):
        self.replies, self.asks = list(replies), 0

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        self.asks += 1
        return self.replies.pop(0)


def reply(*calls):
    return {"content": "".join("<tool_call>\n" + json.dumps({"name": tool, "arguments": args})
                               + "\n</tool_call>\n" for tool, args in calls)}


CUBE = ("add_primitive", {"shape": "cube", "location": [0, 0, 4.7]})
SEAT = ("add_primitive", {"shape": "cube", "name": "Seat", "location": [0, 0, 0.5]})
LEG = ("add_primitive", {"shape": "cube", "name": "Leg1", "location": [0.2, 0.2, 0.25]})


class RepeatGuard(unittest.TestCase):
    def run_turn(self, replies):
        ex = FakeExec()
        runtime = FakeRuntime(replies)
        result = Copilot(runtime, Session(ex), max_calls=20).run("a bar stool", mode="build")
        return ex, runtime, result

    def test_the_same_call_eight_times_in_one_reply_builds_three_objects(self):
        ex, _runtime, result = self.run_turn([reply(*[CUBE] * 8), {"content": "done"}])
        self.assertEqual(len(ex.objs), 3)
        self.assertEqual(len(result.calls), 3)
        self.assertEqual(result.repeated, 5)

    def test_a_reply_made_only_of_extra_repeats_ends_the_turn(self):
        # after three, every further reply would loop for ever on the same call
        ex, runtime, result = self.run_turn([reply(CUBE)] * 9)
        self.assertEqual(runtime.asks, 4)
        self.assertEqual(len(ex.objs), 3)
        self.assertTrue(result.hit_cap)
        self.assertIn("repeating", result.text)

    def test_the_same_call_twice_is_allowed(self):
        ex, _runtime, result = self.run_turn([reply(CUBE, CUBE), {"content": "done"}])
        self.assertEqual(len(ex.objs), 2)
        self.assertEqual(result.repeated, 0)

    def test_different_calls_are_all_kept(self):
        ex, _runtime, result = self.run_turn([reply(SEAT, LEG), {"content": "done"}])
        self.assertEqual([o["name"] for o in ex.objs], ["Seat", "Leg1"])
        self.assertEqual(result.repeated, 0)
        self.assertFalse(result.hit_cap)


if __name__ == "__main__":
    unittest.main()
