# SPDX-License-Identifier: Apache-2.0
import json
import unittest

from maris3d.copilot import (assistant_message, format_result, load_tools, normalise_calls,
                                 scene_summary, trim_tools)
from maris3d.copilot.loop import Copilot
from maris3d.copilot.session import Executor, Session
from maris3d.dsl.tools import compile_calls
from maris3d.runtimes.llama_server import LlamaServer


class FakeExec(Executor):
    def __init__(self):
        self.objs = []

    def reset(self):
        self.objs = []

    def run_call(self, call):
        if call["tool"] == "boom":
            return False, "x" * 500
        self.objs.append({"name": call.get("name", "Cube"), "type": "MESH", "loc": [0, 0, 0]})
        return True, None

    def objects(self):
        return list(self.objs)


class FakeRuntime:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        self.seen.append((len(messages), list(tool_names), lora_scale, max_tokens))
        return self.replies.pop(0)


def tag(tool, **args):
    return {"content": "<tool_call>\n" + json.dumps({"name": tool, "arguments": args}) + "\n</tool_call>"}


class ProtocolTests(unittest.TestCase):
    def test_manifest_has_26_tools_matching_the_compiler(self):
        self.assertEqual(len(load_tools()), 26)
        code = compile_calls({"calls": [{"tool": "add_primitive", "shape": "cube", "name": "A"}]})
        self.assertIn("bpy", code)

    def test_trim_never_offers_all_26_and_is_deterministic(self):
        a = trim_tools("add a red cube and a light")
        self.assertEqual(a, trim_tools("add a red cube and a light"))
        self.assertLess(len(a), 26)
        self.assertTrue({"add_primitive", "set_material", "add_light"} <= set(a))
        self.assertIn("set_transform", trim_tools("move it left", mode="edit"))

    def test_result_text_is_exactly_ok_or_last_200(self):
        self.assertEqual(format_result(True), "ok")
        self.assertEqual(len(format_result(False, "y" * 500)), len("error: ") + 200)

    def test_scene_summary_caps_and_empty(self):
        self.assertEqual(scene_summary([]), "Scene is empty.")
        many = [{"name": f"o{i}", "type": "MESH", "loc": [0, 0, 0]} for i in range(50)]
        self.assertIn("and 10 more", scene_summary(many, cap=40))

    def test_both_call_shapes_normalise_the_same(self):
        text = normalise_calls(tag("add_primitive", shape="cube"))
        struct = normalise_calls({"tool_calls": [{"function": {"name": "add_primitive", "arguments": '{"shape": "cube"}'}}]})
        self.assertEqual(text, struct)
        self.assertEqual(normalise_calls({"content": "<tool_call>{broken</tool_call>"}), [])

    def test_assistant_message_roundtrips(self):
        msg, ids = assistant_message([{"tool": "add_primitive", "shape": "cube"}], 1, 1)
        self.assertEqual(len(ids), 1)
        self.assertEqual(normalise_calls(msg), [{"tool": "add_primitive", "shape": "cube"}])


class LoopTests(unittest.TestCase):
    def test_build_then_stop_on_text_with_adapter_off(self):
        rt = FakeRuntime([tag("add_primitive", name="A"), {"content": "Done."}])
        cp = Copilot(rt, Session(FakeExec()))
        res = cp.run("add a cube")
        self.assertTrue(res.ok)
        self.assertEqual(res.text, "Done.")
        self.assertEqual({s[2] for s in rt.seen}, {0.0})

    def test_second_turn_is_edit_with_adapter_on_and_scene_line(self):
        rt = FakeRuntime([tag("add_primitive", name="A"), {"content": "ok"}, tag("set_transform", name="A"), {"content": "ok"}])
        cp = Copilot(rt, Session(FakeExec()))
        cp.run("add a cube")
        cp.run("move it left")
        self.assertEqual(rt.seen[-1][2], 1.0)
        self.assertIn("[Scene objects: A (mesh)", cp.messages[-4]["content"])

    def test_each_ask_uses_the_scored_output_budget(self):
        rt = FakeRuntime([tag("add_primitive", name="A"), {"content": "Done."}])
        Copilot(rt, Session(FakeExec())).run("add a cube")
        self.assertEqual({seen[3] for seen in rt.seen}, {2800})

    def test_each_turn_is_a_fresh_chat(self):
        rt = FakeRuntime([tag("add_primitive", name="A"), {"content": "ok"}, tag("set_transform", name="A"), {"content": "ok"}])
        cp = Copilot(rt, Session(FakeExec()))
        cp.run("add a cube")
        cp.run("move it left")
        self.assertEqual(rt.seen[2][0], 1)  # edit turn starts at the user message + scene summary, no history

    def test_errors_recorded_and_call_cap_stops_runaway(self):
        rt = FakeRuntime([tag("boom")] * 30)
        res = Copilot(rt, Session(FakeExec()), max_calls=3).run("x")
        self.assertTrue(res.hit_cap)
        self.assertEqual(len(res.errors), 3)
        self.assertFalse(res.ok)

    def test_runtime_failure_is_api_error_not_a_model_answer(self):
        class Down:
            def chat(self, *a, **k):
                raise ConnectionError("down")
        res = Copilot(Down(), Session(FakeExec())).run("x")
        self.assertTrue(res.api_error)

    def test_server_rejects_the_second_step_keeps_the_applied_calls(self):
        class Once:
            n = 0
            def chat(self, *a, **k):
                Once.n += 1
                if Once.n > 1:
                    raise RuntimeError("HTTP 400: Value looks like object")
                return tag("add_primitive", name="A")
        ex = FakeExec()
        res = Copilot(Once(), Session(ex)).run("x")
        self.assertEqual(res.api_error, "")
        self.assertIn("HTTP 400", res.followup_error)
        self.assertEqual(len(res.calls), 1)
        self.assertEqual(len(ex.objs), 1)  # the applied work stays
        from maris3d.mcp.server import result_text
        self.assertIn("do not retry", result_text(res))
        self.assertNotIn("model server error", result_text(res))

    def test_undo_replays_without_the_last_batch(self):
        ex = FakeExec()
        s = Session(ex)
        s.apply([{"tool": "add_primitive", "name": "A"}])
        s.apply([{"tool": "add_primitive", "name": "B"}])
        self.assertTrue(s.undo())
        self.assertEqual([o["name"] for o in ex.objects()], ["A"])
        self.assertFalse(Session(FakeExec()).undo())


class RuntimeBodyTests(unittest.TestCase):
    def test_llama_server_always_sends_lora_scale(self):
        rt = LlamaServer()
        for scale in (0, 1):
            body = rt.body([{"role": "user", "content": "x"}], ["add_primitive"], scale, 1024)
            self.assertEqual(body["lora"], [{"id": 0, "scale": float(scale)}])
        self.assertEqual(rt.body([], ["add_primitive"], None, 8)["temperature"], 0)
        self.assertNotIn("lora", rt.body([], ["add_primitive"], None, 8))


if __name__ == "__main__":
    unittest.main()
