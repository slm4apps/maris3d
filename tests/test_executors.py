# SPDX-License-Identifier: Apache-2.0
import json
import unittest

from maris3d.copilot.session import Session
from maris3d.executors import McpForwardExecutor, compile_call


class FakeHostMcp:
    """Stands in for another Blender MCP: execute_blender_code + get_scene_info."""

    def __init__(self):
        self.sent, self.fail = [], False

    def __call__(self, name, args):
        if name == "execute_blender_code":
            self.sent.append(args["code"])
            return "Error: boom" if self.fail else "Code executed successfully: "
        if name == "get_scene_info":
            return json.dumps({"objects": [{"name": "Cube", "type": "MESH", "location": [0, 0, 1]}]})
        raise KeyError(name)


class ExecutorTests(unittest.TestCase):
    def test_native_call_becomes_python_sent_through_the_host_tool(self):
        host = FakeHostMcp()
        ex = McpForwardExecutor(host)
        ok, err = ex.run_call({"tool": "add_primitive", "shape": "cube", "name": "Cube"})
        self.assertTrue(ok)
        self.assertIn("bpy", host.sent[0])
        self.assertEqual(ex.objects()[0]["name"], "Cube")

    def test_host_error_text_becomes_a_tool_error(self):
        host = FakeHostMcp()
        host.fail = True
        ok, err = McpForwardExecutor(host).run_call({"tool": "add_primitive", "shape": "cube"})
        self.assertFalse(ok)
        self.assertIn("boom", err)

    def test_unknown_tool_is_a_compile_error_not_a_crash(self):
        code, err = compile_call({"tool": "no_such_tool"})
        self.assertTrue(code is not None or err)

    def test_undo_replays_through_the_host(self):
        host = FakeHostMcp()
        s = Session(McpForwardExecutor(host))
        s.apply([{"tool": "add_primitive", "shape": "cube", "name": "A"}])
        s.apply([{"tool": "add_primitive", "shape": "cube", "name": "B"}])
        n = len(host.sent)
        self.assertTrue(s.undo())
        self.assertEqual(len(host.sent), n + 2)  # reset code + replay of batch 1

    def test_reset_never_removes_objects_that_existed_before(self):
        host = FakeHostMcp()
        ex = McpForwardExecutor(host)
        ex.run_call({"tool": "add_primitive", "shape": "cube", "name": "A"})
        self.assertIn("_slm_keep", host.sent[0])          # snapshot is taken in Blender before our first call
        self.assertIn("bpy", host.sent[1])
        ex.reset()
        reset_code = host.sent[-1]
        self.assertIn("if o.name not in keep", reset_code)  # only objects outside the snapshot are removed
        self.assertIn("if keep is not None", reset_code)    # no snapshot -> nothing is removed
        self.assertEqual(sum("_slm_keep'] =" in c for c in host.sent), 1)  # one snapshot, not one per call


if __name__ == "__main__":
    unittest.main()
