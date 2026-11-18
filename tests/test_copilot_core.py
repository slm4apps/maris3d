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

    def chat(self, messages, tool_names, max_tokens=1024, role=None):
        self.seen.append((len(messages), list(tool_names), role, max_tokens))
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


class SessionTests(unittest.TestCase):
    def test_undo_replays_without_the_last_batch(self):
        ex = FakeExec()
        s = Session(ex)
        s.apply([{"tool": "add_primitive", "name": "A"}])
        s.apply([{"tool": "add_primitive", "name": "B"}])
        self.assertTrue(s.undo())
        self.assertEqual([o["name"] for o in ex.objects()], ["A"])
        self.assertFalse(Session(FakeExec()).undo())


class NoToolLoop(unittest.TestCase):
    """Version 0.2 has no route to the base model's native tool loop."""

    def test_the_copilot_has_no_tool_loop_entry(self):
        for name in ("run", "_loop", "run_change", "edit_exact", "chunk_direct", "change_mode"):
            self.assertFalse(hasattr(Copilot, name), name)

    def test_no_request_reaches_a_tool_call_ask(self):
        class Garbage:
            seen = []

            def chat(self, messages, tool_names, max_tokens=1024, role=None):
                self.seen.append((list(tool_names), role))
                return {"content": "<tool_call>\n" + json.dumps({"name": "add_primitive", "arguments": {}}) + "\n</tool_call>"}

            def has_role(self, role):
                return True

            final_format = True

        for request in ("add a red cube named Box", "make the chair red", "move the bench behind the station",
                        "scale the table to 2 metres", "make it smooth", "what is in the scene?"):
            ex = FakeExec()
            session = Session(ex)
            session.apply([{"tool": "add_primitive", "name": "Chair"}])
            rt = Garbage()
            rt.seen = []
            cop = Copilot(rt, session, router=lambda req, objs, _t: "edit" if "the " in req else "build")
            res = cop.run_auto(request)
            self.assertFalse(res.calls and res.mode == "build" and not res.built, request)
            self.assertTrue(all(tools == [] for tools, _role in rt.seen), request)
            self.assertEqual([c for c in ex.objects() if c["name"] != "Chair" and c["name"] != "SceneNorth"], [], request)


class RuntimeBodyTests(unittest.TestCase):
    def test_llama_server_sends_a_lora_entry_for_every_loaded_adapter(self):
        rt = LlamaServer()
        rt.adapters = {"one": 0, "parts": 1}
        body = rt.body([{"role": "user", "content": "x"}], [], 1024, role="edit")
        self.assertEqual(body["lora"], [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}])
        self.assertEqual(body["temperature"], 0)
        self.assertNotIn("tools", body)
        self.assertNotIn("lora", LlamaServer().body([], [], 8))


if __name__ == "__main__":
    unittest.main()


class PanelWords(unittest.TestCase):
    def test_a_talk_answer_is_shown_as_its_words_not_the_raw_answer(self):
        from maris3d.copilot.loop import _said
        answer = {"kind": "talk", "show": [{"line": "say", "text": "Thank you!", "effect": "pop"},
                                            {"line": "show maris", "pose": "wave"}]}
        self.assertEqual(_said(answer), "Thank you!")
        self.assertEqual(_said({"kind": "cannot", "say": "I can't add lights."}), "I can't add lights.")
        self.assertEqual(_said({"kind": "change", "changes": []}), "")

    def test_a_move_and_a_resize_are_reported(self):
        from maris3d.addon import summary
        before = [{"name": "Lamp", "loc": [6.7, 0, 0], "dims": [1, 1, 2], "mats": ["Steel"]},
                  {"name": "Rug", "loc": [0, 0, 0], "dims": [2, 1, 0], "mats": ["RugRed"]}]
        after = [{"name": "Lamp", "loc": [3.2, 0, 0], "dims": [1, 1, 2], "mats": ["Steel"]},
                 {"name": "Rug", "loc": [0, 0, 0], "dims": [3, 1.5, 0], "mats": ["RugRed"]}]
        line = summary.scene_diff(before, after)
        self.assertIn("Moved 1: Lamp", line)
        self.assertIn("Resized 1: Rug", line)
        self.assertNotIn("Nothing changed", line)
