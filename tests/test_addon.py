# SPDX-License-Identifier: Apache-2.0
"""Add-on assembly + the bpy-less parts of the add-on package.

The in-Blender machinery (executor, panel) is exercised by the headless self-test
(`maris3d install` runs it in `blender -b`); here we lock the assembly contract:
vendored copies are byte-equal to the real modules modulo the import rewrites, the
extension imports without bpy, the zip packages everything, and the summary/client
logic holds.
"""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from maris3d import addonbuild
from maris3d.addon import client, summary
import maris3d.addon as addon_pkg


class AssembleFidelity(unittest.TestCase):
    """The vendored core is produced from the real sources — never hand-copied."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ext = addonbuild.assemble(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_addon_files_copied_verbatim(self):
        for name in addonbuild._ADDON_FILES:
            self.assertEqual((self.ext / name).read_bytes(),
                             (addonbuild.SRC / "addon" / name).read_bytes(), name)
        self.assertEqual((self.ext / "blender_manifest.toml").read_bytes(),
                         (addonbuild.SRC / "addon" / "manifest.toml").read_bytes())

    def test_vendored_modules_byte_equal_modulo_rewrites(self):
        vendor = self.ext / "vendor"
        for src, name in addonbuild._VENDOR.items():
            text = (addonbuild.SRC / src).read_text(encoding="utf-8")
            for old, new in addonbuild._REWRITES.get(src, []):
                self.assertIn(old, text, f"rewrite anchor drifted in {src}")
                text = text.replace(old, new)
            self.assertEqual(text, (vendor / name).read_text(encoding="utf-8"), name)

    def test_tools_json_vendored_verbatim(self):
        src = (addonbuild.SRC / "copilot" / "data" / "TOOLS.json").read_bytes()
        self.assertEqual((self.ext / "vendor" / "data" / "TOOLS.json").read_bytes(), src)

    def test_extension_imports_without_bpy(self):
        sys.path.insert(0, str(self.ext.parent))
        try:
            for mod in ("maris3d_copilot", "maris3d_copilot.vendor.loop",
                        "maris3d_copilot.vendor.protocol", "maris3d_copilot.vendor.plan",
                        "maris3d_copilot.vendor.session",
                        "maris3d_copilot.vendor.dsl_tools", "maris3d_copilot.client",
                        "maris3d_copilot.summary"):
                __import__(mod)
            from maris3d_copilot.vendor.protocol import load_tools
            self.assertEqual(len(load_tools()), 26)
            from maris3d_copilot.vendor.plan import check_items, from_outline
            self.assertEqual(check_items(from_outline({"items": [{"id": "a", "thing": "chair"}]})), (True, None))
            from maris3d_copilot.vendor.dsl_tools import compile_calls
            code = compile_calls({"calls": [{"tool": "add_primitive", "shape": "cube", "name": "X"}]})
            self.assertIn("X", code)
        finally:
            for m in list(sys.modules):
                if m.startswith("maris3d_copilot"):
                    del sys.modules[m]
            sys.path.remove(str(self.ext.parent))

    def test_build_zip_packages_everything(self):
        with tempfile.TemporaryDirectory() as out:
            path = addonbuild.build_zip(out)
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
            root = "maris3d_copilot"
            for need in (f"{root}/blender_manifest.toml", f"{root}/selftest.py",
                         f"{root}/vendor/data/TOOLS.json", f"{root}/vendor/dsl_tools.py",
                         f"{root}/vendor/loop.py", f"{root}/vendor/plan.py",
                         f"{root}/vendor/policy.py",
                         f"{root}/vendor/session.py",
                         f"{root}/vendor/protocol.py", f"{root}/vendor/llama_server.py",
                         f"{root}/vendor/ollama.py", f"{root}/vendor/runtime_base.py",
                         f"{root}/executor.py", f"{root}/client.py", f"{root}/summary.py"):
                self.assertIn(need, names)


class BpylessAddon(unittest.TestCase):
    def test_register_is_noop_outside_blender(self):
        self.assertIsNone(addon_pkg.register())  # no bpy in this process: must not raise
        self.assertIsNone(addon_pkg.unregister())

    def test_scene_diff_added_removed_materials(self):
        before = [{"name": "Keep", "type": "MESH", "loc": [0, 0, 0], "mats": []}]
        after = [{"name": "Keep", "type": "MESH", "loc": [0, 0, 0], "mats": ["Brown"]},
                 {"name": "New", "type": "MESH", "loc": [1, 0, 0], "mats": ["Brown"]}]
        line = summary.scene_diff(before, after)
        self.assertIn("Added 1 object: New", line)
        self.assertIn("1 material: Brown", line)
        line2 = summary.scene_diff(after, before)
        self.assertIn("Removed 1: New", line2)

    def test_scene_diff_nothing_changed_and_error_path(self):
        objs = [{"name": "A", "type": "MESH", "loc": [0, 0, 0], "mats": []}]
        self.assertEqual(summary.scene_diff(objs, list(objs)), "Nothing changed in the scene.")
        res = type("R", (), {"errors": [{"error": "ValueError: nope"}]})()
        line = summary.scene_diff(objs, list(objs), res)
        self.assertIn("Nothing changed", line)
        self.assertIn("nope", line)

    def test_scene_diff_caps_long_lists(self):
        before = []
        after = [{"name": f"o{i}", "type": "MESH", "loc": [0, 0, 0], "mats": []} for i in range(9)]
        line = summary.scene_diff(before, after)
        self.assertIn("+3 more", line)
        self.assertNotIn("o8", line)

    def test_built_line_says_who_did_what(self):
        class R:
            built = {"parts": 6, "exact": 2, "moved": 2, "missing": 2, "unfixed": 0, "strays": [],
                     "notes": ["chair: designed by the parts planner, 6 parts"]}
        line = summary.built_line(R())
        self.assertIn("2 of 6 parts exact", line)
        self.assertNotIn("from the model", line)

        class Lib:                                   # the library built it: never reported as the model's
            built = {"parts": 6, "exact": 6, "designed": [], "library": ["Armchair"],
                     "notes": ["armchair: the parts planner's answer cannot be built (x); built from the library instead"]}
        line2 = summary.built_line(Lib())
        self.assertIn("from the library: Armchair", line2)
        self.assertIn("built from the library instead", line2)
        self.assertNotIn("designed by the model", line2)
        self.assertIn("2 corrected", line)
        self.assertIn("2 made by the copilot", line)
        self.assertIn("designed by the parts planner", line)
        self.assertNotIn("still wrong", line)
        self.assertEqual(summary.built_line(object()), "")          # not a compiled plan

    def test_the_server_runs_the_adapter_of_the_turns_role(self):
        srv = client.LlamaServer()
        srv.adapters = client.adapter_roles([{"id": 0, "path": "/m/maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf"},
                                             {"id": 1, "path": "/m/maris3d-slm-blender-parts-lora-f16.gguf"}])
        body = srv.body([{"role": "user", "content": "x"}], [], 100, role="planner")
        self.assertEqual(body["lora"], [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}])
        body = srv.body([{"role": "user", "content": "x"}], [], 100, role="parts")
        self.assertEqual(body["lora"], [{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}])

    def test_a_server_with_no_adapter_never_sends_lora(self):
        body = client.LlamaServer().body([{"role": "user", "content": "x"}], [], 100, role="edit")
        self.assertNotIn("lora", body)  # a merged single file rejects the field

    def test_make_client_backends(self):
        llama = client.make_client({"backend": "LLAMA_SERVER", "server_url": "http://127.0.0.1:9"})
        self.assertIsInstance(llama, client.LlamaServer)
        self.assertEqual(llama.base_url, "http://127.0.0.1:9")
        self.assertEqual(llama.adapters, {})  # nothing listening -> no lora field is sent
        ol = client.make_client({"backend": "OLLAMA", "ollama_model": "maris3d-one", "ollama_parts_model": "maris3d-parts"})
        self.assertEqual(ol.name, "ollama")
        self.assertEqual(ol.models, {"one": "maris3d-one", "parts": "maris3d-parts"})
        self.assertIsInstance(client.make_client({}), client.LlamaServer)

    def test_the_panel_has_one_way_in(self):
        src = Path(addon_pkg.__file__).read_text(encoding="utf-8")
        for gone in ("copt_mode", "plan_mode", "assist", ".run(prompt", "mode=mode"):
            self.assertNotIn(gone, src, gone)
        self.assertIn("run_auto(prompt)", src)


class CliContract(unittest.TestCase):
    @staticmethod
    def _port_free(port):
        import socket
        with socket.socket() as s:
            s.settimeout(0.3)
            try:
                s.connect(("127.0.0.1", port))
                return False
            except OSError:
                return True

    @unittest.skipIf(not _port_free(9931), "a real maris3d server is running on :9931")
    def test_cli_imports_and_names_the_0_2_files(self):
        from maris3d import cli
        self.assertEqual(cli.MODELS, {"q8_0": "maris3d-slm-blender-0.5b-q8_0.gguf",
                                      "one-lora": "maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf",
                                      "parts-lora": "maris3d-slm-blender-parts-lora-f16.gguf"})
        cmd = cli.serve_command("llama-server", "base.gguf", "one.gguf", 1, "parts.gguf")
        self.assertNotIn("--repeat-penalty", cmd)
        self.assertEqual([cmd[i + 1] for i, a in enumerate(cmd) if a == "--lora"], ["one.gguf", "parts.gguf"])
        self.assertEqual(cli.PORT, 9931)
        argv = cli.main(["serve", "status"])  # nothing listening -> clean nonzero exit, no exception
        self.assertNotEqual(argv, 0)


class Routing(unittest.TestCase):
    """The router: a change to what the scene has is an edit, everything else builds."""

    def setUp(self):
        from maris3d.addon import routing
        self.r = routing

    def test_build_when_scene_is_empty(self):
        self.assertEqual(self.r.resolve("make the cube blue", False), "build")
        self.assertEqual(self.r.resolve("", True), "build")

    def test_fresh_requests_build(self):
        for prompt in ("add a coffee mug with a handle", "make a red cube named Box",
                       "create 5 cubes in a ring", "build a small house"):
            self.assertEqual(self.r.resolve(prompt, True), "build", prompt)

    def test_corrections_edit(self):
        for prompt in ("make the cube blue", "change the material to red",
                       "move it up", "rename the cube to Box", "delete the sphere"):
            self.assertEqual(self.r.resolve(prompt, True), "edit", prompt)


if __name__ == "__main__":
    unittest.main()
