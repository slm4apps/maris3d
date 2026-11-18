# SPDX-License-Identifier: Apache-2.0
import io
import json
import unittest

from maris3d.copilot.session import Executor
from maris3d.mcp.server import Server, scene_table, serve


class FakeExec(Executor):
    def __init__(self):
        self.objs, self.log = [], []

    def reset(self):
        self.objs = []

    def run_call(self, call):
        if call.get("tool") == "boom":
            return False, "bad"
        self.log.append(call)
        self.objs.append({"name": f"Obj{len(self.objs)}", "type": "MESH", "loc": [0, 0, 0]})
        return True, None

    def objects(self):
        return list(self.objs)


class FakeRuntime:
    def __init__(self):
        self.scales = []

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        self.scales.append(lora_scale)
        if messages[-1]["role"] == "tool":
            return {"role": "assistant", "content": "done"}
        return {"role": "assistant", "content": '<tool_call>{"name":"add_primitive","arguments":{"kind":"cube"}}</tool_call>'}


def rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.ex, self.rt = FakeExec(), FakeRuntime()
        self.srv = Server(self.ex, runtime=self.rt)

    def test_initialize_has_instructions(self):
        r = rpc(self.srv, "initialize")["result"]
        self.assertIn("instructions", r)
        self.assertEqual(r["serverInfo"]["name"], "maris3d-blender")

    def test_no_code_tool_exposed(self):
        names = {t["name"] for t in rpc(self.srv, "tools/list")["result"]["tools"]}
        self.assertEqual(names, {"build_scene", "edit_scene", "run_calls", "scene_info", "undo", "look"})
        self.assertFalse([n for n in names if "code" in n or "exec" in n])

    def test_build_then_edit_uses_adapter_scale(self):
        out = rpc(self.srv, "tools/call", {"name": "build_scene", "arguments": {"request": "a cube"}})["result"]
        self.assertFalse(out["isError"])
        self.assertIn("add_primitive", out["content"][0]["text"])
        rpc(self.srv, "tools/call", {"name": "edit_scene", "arguments": {"request": "move it"}})
        self.assertEqual(self.rt.scales[0], 0.0)
        self.assertIn(1.0, self.rt.scales)

    def test_build_scene_plans_first_when_the_server_has_a_planner(self):
        # the MCP tool is the same entry as the add-on's Auto: planner -> compile -> build -> check
        from tests.test_compile_plan import Designed, FakeExecutor, STATION
        ex = FakeExecutor()
        srv = Server(ex, runtime=Designed.Server({"items": STATION}))
        out = rpc(srv, "tools/call", {"name": "build_scene", "arguments": {
            "request": "a platform, a station building behind it and two benches on it"}})["result"]
        text = out["content"][0]["text"]
        self.assertFalse(out["isError"], text)
        self.assertIn("15 parts, 15 exact, 0 corrected, 0 not right", text)
        self.assertIn("BenchBack2", ex.objs)
        # a move relative to another thing is done by code, no edit model
        moved = rpc(srv, "tools/call", {"name": "edit_scene", "arguments": {
            "request": "put the bench behind the station building"}})["result"]
        self.assertFalse(moved["isError"], moved["content"][0]["text"])
        rpc(srv, "tools/call", {"name": "undo", "arguments": {}})

    def test_undo_replays(self):
        rpc(self.srv, "tools/call", {"name": "build_scene", "arguments": {"request": "a cube"}})
        self.assertEqual(len(self.ex.objs), 1)
        out = rpc(self.srv, "tools/call", {"name": "undo", "arguments": {}})["result"]
        self.assertEqual(out["content"][0]["text"], "undone")
        self.assertEqual(self.ex.objs, [])
        out = rpc(self.srv, "tools/call", {"name": "undo", "arguments": {}})["result"]
        self.assertEqual(out["content"][0]["text"], "nothing to undo")

    def test_undo_reverts_whole_request_even_with_several_model_steps(self):
        class TwoStep(FakeRuntime):
            def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
                steps = sum(1 for m in messages if m["role"] == "assistant" and m.get("tool_calls"))
                if steps >= 2:
                    return {"role": "assistant", "content": "done"}
                return super().chat([{"role": "user", "content": "x"}], tool_names, lora_scale)
        srv = Server(self.ex, runtime=TwoStep())
        rpc(srv, "tools/call", {"name": "build_scene", "arguments": {"request": "two steps"}})
        self.assertEqual(len(self.ex.objs), 2)
        rpc(srv, "tools/call", {"name": "undo", "arguments": {}})
        self.assertEqual(self.ex.objs, [])

    def test_run_calls_rejects_unknown_tool(self):
        out = rpc(self.srv, "tools/call", {"name": "run_calls", "arguments": {"calls": [{"tool": "execute_blender_code", "code": "x"}]}})["result"]
        self.assertTrue(out["isError"])
        self.assertEqual(self.ex.log, [])

    def test_run_calls_runs_native_calls(self):
        out = rpc(self.srv, "tools/call", {"name": "run_calls", "arguments": {"calls": [{"tool": "add_primitive", "kind": "cube"}]}})["result"]
        self.assertEqual(out["content"][0]["text"], "add_primitive: ok")

    def test_no_runtime_gives_clear_error_but_scene_info_works(self):
        srv = Server(FakeExec(), runtime=lambda: None)
        out = rpc(srv, "tools/call", {"name": "build_scene", "arguments": {"request": "x"}})["result"]
        self.assertTrue(out["isError"])
        self.assertIn("no model server", out["content"][0]["text"])
        info = rpc(srv, "tools/call", {"name": "scene_info", "arguments": {}})["result"]
        self.assertFalse(info["isError"])

    def test_scene_table_truncated_flag(self):
        objs = [{"name": f"o{i}", "type": "MESH", "loc": [i, 0, 0]} for i in range(30)]
        text = scene_table(objs, limit=5)
        self.assertTrue(text.startswith("objects=30 shown=5 truncated=true"))
        self.assertEqual(len(text.splitlines()), 6)
        self.assertIn("truncated=false", scene_table(objs[:2]))

    def test_bad_request_arg_and_unknown_method(self):
        out = rpc(self.srv, "tools/call", {"name": "build_scene", "arguments": {}})["result"]
        self.assertTrue(out["isError"])
        self.assertEqual(rpc(self.srv, "nope")["error"]["code"], -32601)
        self.assertIsNone(self.srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_look_needs_screenshot_executor(self):
        out = rpc(self.srv, "tools/call", {"name": "look", "arguments": {}})["result"]
        self.assertTrue(out["isError"])

    def test_stdio_loop_newline_framing(self):
        lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), "", "not json",
                 json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})]
        out = io.StringIO()
        serve(self.srv, io.StringIO("\n".join(lines) + "\n"), out)
        replies = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2])


if __name__ == "__main__":
    unittest.main()
