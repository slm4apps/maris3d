# SPDX-License-Identifier: Apache-2.0
"""The word edit path in the product: the one adapter answers a change in words (role "edit")."""
import json
import unittest

from maris3d.copilot import edit_words as EW
from maris3d.copilot.loop import EDIT_PASSES, Copilot
from maris3d.copilot.session import Session

from tests.test_apply_change import Sim


class Runtime:
    final_format = True

    def __init__(self, replies=(), roles=("edit",)):
        self.replies, self.asked, self.roles = list(replies), [], roles

    def has_role(self, role):
        return role in self.roles or role == "planner"

    def chat(self, messages, tool_names, max_tokens=1024, role=None):
        self.asked.append({"messages": messages, "role": role})
        reply = self.replies.pop(0)
        return reply if isinstance(reply, dict) else {"content": reply}


def words(*changes, kind="change", **extra):
    return EW.wrap(dict({"kind": kind, "changes": list(changes)}, **extra) if kind == "change"
                   else dict({"kind": kind}, **extra))


class WordsMode(unittest.TestCase):
    def copilot(self, replies, roles=("edit",)):
        sim = Sim()
        cop = Copilot(Runtime(replies, roles), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        cop.runtime.asked.clear()
        return cop, sim

    def test_a_recolor_in_words_is_applied_by_code_with_the_trained_prompt(self):
        cop, sim = self.copilot([words({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"})])
        result = cop.run_auto("make the seat red")
        self.assertEqual(result.mode, "change")
        self.assertEqual(sim.o["ChairSeat"]["material"], "Red")
        self.assertTrue(result.ok, result.errors)
        ask = cop.runtime.asked[0]
        self.assertEqual(ask["role"], "edit")
        self.assertEqual(ask["messages"][0]["content"], EW.EDIT_SYSTEM_EXACT)
        self.assertIn("Request: make the seat red", ask["messages"][1]["content"])
        self.assertEqual(len(cop.runtime.asked), 1)

    def test_a_tool_call_lifted_by_the_server_is_read(self):
        args = {"kind": "change", "changes": [{"do": "recolor", "object": "Chair", "color": "blue"}]}
        msg = {"content": "", "tool_calls": [{"function": {"name": EW.TOOL_NAME, "arguments": json.dumps(args)}}]}
        cop, sim = self.copilot([msg])
        result = cop.run_auto("make the chair blue")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(sim.o["ChairSeat"]["material"], "Blue")

    def test_look_asks_again_with_the_parts_in_focus(self):
        cop, sim = self.copilot([words(kind="look", things=["Chair"]),
                                 words({"do": "recolor", "object": "Chair", "parts": ["ChairSeat"], "color": "red"})])
        result = cop.run_auto("make the seat red")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(cop.runtime.asked), 2)
        self.assertIn("Focus:", cop.runtime.asked[1]["messages"][1]["content"])

    def test_at_most_the_pass_limit_then_a_plain_answer(self):
        cop, sim = self.copilot([words(kind="look", things=["Chair"])] * (EDIT_PASSES + 1))
        result = cop.run_auto("make the seat red")
        self.assertLessEqual(len(cop.runtime.asked), EDIT_PASSES)
        self.assertEqual(result.calls, [])
        self.assertTrue(result.text)

    def test_question_goes_to_the_panel_and_nothing_runs(self):
        cop, sim = self.copilot([words(kind="question", say="Which chair do you mean?")])
        n = len(sim.o)
        result = cop.run_auto("make it red")
        self.assertEqual(result.text, "Which chair do you mean?")
        self.assertEqual(result.calls, [])
        self.assertEqual(len(sim.o), n)

    def test_unreadable_answer_is_an_error_not_a_change(self):
        cop, sim = self.copilot(["sure, done!"])
        result = cop.run_auto("make it red")
        self.assertFalse(result.ok)
        self.assertIn("cannot be read", result.errors[0]["error"])

    def test_off_without_an_edit_adapter(self):
        cop, _sim = self.copilot([], roles=())
        self.assertFalse(cop._has_role("edit"))

    def test_a_change_is_one_undo_unit(self):
        cop, sim = self.copilot([words({"do": "scale", "object": "Chair", "size": "double"})])
        n, size = len(cop.session.batches), list(cop.session.specs["Chair"]["size"])
        cop.run_auto("make the chair twice as big")
        self.assertEqual(len(cop.session.batches), n + 1)
        cop.undo()
        self.assertEqual(cop.session.specs["Chair"]["size"], size)


class AdapterFiles(unittest.TestCase):
    def test_the_one_adapter_serves_the_edit_role_and_the_parts_add_on_its_own(self):
        from unittest import mock
        from maris3d.addon import client
        loaded = [{"id": 0, "path": "/m/maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf"},
                  {"id": 1, "path": "/m/maris3d-slm-blender-parts-lora-f16.gguf"}]
        with mock.patch.object(client, "adapters", return_value=loaded):
            rt = client.make_client({"server_url": "http://x:1"})
        self.assertEqual(rt.adapters, {"one": 0, "parts": 1})
        self.assertTrue(rt.has_role("edit") and rt.has_role("planner"))
        body = rt.body([{"role": "user", "content": "x"}], [], 10, role="edit")
        self.assertEqual(body["lora"], [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}])
        base = rt.body([{"role": "user", "content": "x"}], [], 10)
        self.assertTrue(all(e["scale"] == 0.0 for e in base["lora"]))

    def test_a_server_without_the_one_adapter_has_no_edit_role(self):
        from maris3d.addon.client import adapter_roles
        from maris3d.runtimes.llama_server import LlamaServer
        self.assertEqual(adapter_roles([{"id": 0, "path": "/m/maris3d-slm-blender-0.5b-q8_0.gguf"}]), {})
        self.assertFalse(LlamaServer().has_role("edit"))


if __name__ == "__main__":
    unittest.main()


class EditFallsThrough(unittest.TestCase):
    """An edit answer that changes nothing and asks nothing does not end the turn (yardstick 0.2:
    16 of 30 edit follow-ups stopped there with no calls)."""
    def copilot(self, replies):
        sim = Sim()
        cop = Copilot(Runtime(replies), Session(sim))
        cop.run_items([{"recipe": "chair"}])
        cop.runtime.asked.clear()
        return cop, sim

    def test_an_empty_change_goes_on_to_the_finish(self):
        cop, sim = self.copilot([words()])
        result = cop.run_auto("make the chair smooth")
        self.assertNotEqual(result.mode, "change")
        self.assertTrue(result.calls, result)

    def test_a_cannot_goes_on_to_the_finish(self):
        cop, sim = self.copilot([words(kind="cannot", say="I can't bevel; I can make Chair smooth-shaded.")])
        result = cop.run_auto("make the chair smooth")
        self.assertEqual(result.mode, "finish")
        self.assertTrue(result.calls)

    def test_a_question_still_ends_the_turn(self):
        cop, sim = self.copilot([words(kind="question", say="Which chair do you mean?")])
        result = cop.run_auto("make the chair smooth")
        self.assertEqual(result.text, "Which chair do you mean?")
        self.assertEqual(result.calls, [])
