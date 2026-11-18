# SPDX-License-Identifier: Apache-2.0
"""A new adapter version installs without a new download of the base, and the old one is removed
(12 Nov 2026)."""
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from maris3d import update as U  # noqa: E402

BASE = "maris3d-slm-blender-0.5b-q8_0.gguf"
EDIT = "maris3d-slm-blender-0.5b-edit-lora-f16.gguf"
PLAN3 = "maris3d-slm-blender-planner-v3-lora-f16.gguf"
PLAN31 = "maris3d-slm-blender-planner-v31-lora-f16.gguf"
BUILD2 = "maris3d-slm-blender-0.5b-build-v2-lora-f16.gguf"


class UpdateFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src, self.models = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "models")
        os.makedirs(self.src)
        self.put(BASE, b"B" * 300_000)
        self.put(EDIT, b"edit v1")
        self.put(PLAN3, b"planner v3")
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v3", PLAN3)], "0.1.0")
        self.first = U.update(self.src, self.models, log=lambda *_: None)

    def put(self, name, data):
        with open(os.path.join(self.src, name), "wb") as f:
            f.write(data)

    def release_2(self):
        self.put(PLAN31, b"planner v3.1")
        self.put(BUILD2, b"build v2")
        os.remove(os.path.join(self.src, PLAN3))
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v3.1", PLAN31),
                                    ("build", "v2", BUILD2)], "0.1.1")

    def have(self):
        return sorted(n for n in os.listdir(self.models) if n.endswith(".gguf"))

    def test_first_install_fetches_everything_and_says_how_to_serve(self):
        self.assertEqual(sorted(self.first["fetched"]), sorted([BASE, EDIT, PLAN3]))
        self.assertEqual(self.first["failed"], [])
        serve = self.first["serve"]
        self.assertEqual(serve[serve.index("-m") + 1], os.path.join(self.models, BASE))
        self.assertEqual([serve[i + 1] for i, w in enumerate(serve) if w == "--lora"],
                         [os.path.join(self.models, EDIT), os.path.join(self.models, PLAN3)])
        self.assertIn("--lora-init-without-apply", serve)

    def test_a_new_adapter_does_not_fetch_the_base_again_and_the_old_one_goes(self):
        base = os.path.join(self.models, BASE)
        before = (os.stat(base).st_ino, os.stat(base).st_mtime)
        self.release_2()
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual(sorted(report["fetched"]), sorted([PLAN31, BUILD2]))
        self.assertEqual(report["bytes_transferred"], len(b"planner v3.1") + len(b"build v2"))
        self.assertEqual((os.stat(base).st_ino, os.stat(base).st_mtime), before)      # untouched
        self.assertEqual(report["removed"], [PLAN3])
        self.assertEqual(self.have(), sorted([BASE, EDIT, PLAN31, BUILD2]))
        self.assertEqual(U.read_installed(self.models)["release"], "0.1.1")
        again = U.update(self.src, self.models, log=lambda *_: None)                  # said twice: nothing moves
        self.assertEqual((again["fetched"], again["removed"], again["bytes_transferred"]), ([], [], 0))
        loras = [w for w in again["serve"] if w.endswith(".gguf")][1:]
        self.assertEqual([os.path.basename(p) for p in loras], [EDIT, PLAN31, BUILD2])   # role order

    def test_a_download_with_the_wrong_hash_keeps_the_old_adapter(self):
        self.release_2()
        self.put(PLAN31, b"corrupted on the way")                 # the manifest still has the good hash
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual([f["file"] for f in report["failed"]], [PLAN31])
        self.assertIn(PLAN3, self.have())                          # still there, still serving
        self.assertNotIn(PLAN31, self.have())
        self.assertFalse([n for n in os.listdir(self.models) if n.endswith(".part")])
        self.assertIn(os.path.join(self.models, PLAN3), report["serve"])
        self.assertEqual(U.read_installed(self.models)["release"], "0.1.0")
        self.assertEqual(U.main(["update", "--from", self.src, "--models", self.models]), 1)
        self.put(PLAN31, b"planner v3.1")                          # the source is repaired
        self.assertEqual(U.main(["update", "--from", self.src, "--models", self.models]), 0)
        self.assertEqual(self.have(), sorted([BASE, EDIT, PLAN31, BUILD2]))

    def test_a_file_the_user_fetched_by_hand_is_used_and_never_deleted(self):
        models = os.path.join(self.tmp, "by-hand")
        os.makedirs(models)
        for name in (BASE, PLAN3):
            shutil.copy(os.path.join(self.src, name), models)
        with open(os.path.join(models, "my-notes.gguf"), "wb") as f:
            f.write(b"not ours")
        report = U.update(self.src, models, log=lambda *_: None)
        self.assertEqual(report["fetched"], [EDIT])                # the base was already right
        self.release_2()
        report = U.update(self.src, models, log=lambda *_: None)
        self.assertEqual(report["removed"], [])                    # planner v3 was not installed by us
        self.assertTrue(os.path.exists(os.path.join(models, PLAN3)))
        self.assertTrue(os.path.exists(os.path.join(models, "my-notes.gguf")))
        self.assertNotIn(os.path.join(models, PLAN3), report["serve"])

    def test_a_changed_file_under_the_same_name_is_fetched_again(self):
        self.put(EDIT, b"edit v2, same file name")
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v2", EDIT), ("planner", "v3", PLAN3)], "0.1.2")
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual((report["fetched"], report["removed"]), ([EDIT], []))
        with open(os.path.join(self.models, EDIT), "rb") as f:
            self.assertEqual(f.read(), b"edit v2, same file name")

    def test_a_url_source_works_like_a_folder(self):
        models = os.path.join(self.tmp, "from-url")
        report = U.update(pathlib.Path(self.src).as_uri(), models, log=lambda *_: None)
        self.assertEqual(sorted(report["fetched"]), sorted([BASE, EDIT, PLAN3]))
        self.assertEqual(report["failed"], [])

    def test_the_main_command_updates_the_folder_install_uses_and_serve_takes_the_new_file(self):
        from unittest import mock
        from maris3d import cli
        cache = pathlib.Path(self.tmp) / "cache"
        said = []
        with mock.patch.object(cli, "CACHE", cache), mock.patch.object(cli, "_say", said.append):
            self.assertEqual(cli.main(["update", "--from", self.src]), 0)
            self.assertEqual(cli._installed()["planner"], str(cache / "models" / PLAN3))
            self.release_2()
            self.assertEqual(cli.main(["update", "--from", self.src]), 0)
            now = cli._installed()
            self.assertEqual(now["planner"], str(cache / "models" / PLAN31))       # what serve start loads
            self.assertEqual(now["base"], str(cache / "models" / BASE))
            self.assertIn("kept 2, fetched 2, removed 1", " ".join(said))
            self.put(PLAN31, b"corrupted")
            os.remove(now["planner"])
            self.assertEqual(cli.main(["update", "--from", self.src]), 1)

    def test_the_installer_and_the_updater_use_one_folder_and_the_planner_name_says_its_generation(self):
        from maris3d import cli
        from maris3d.addon import client
        self.assertEqual(os.path.expanduser(U.DEFAULT_MODELS), str(cli.CACHE / "models"))
        name = cli.MODELS["planner-lora"]
        loaded = [{"id": 0, "path": "/m/" + cli.MODELS["edit-lora"]}, {"id": 1, "path": "/m/" + name}]
        self.assertEqual(client.adapter_ids(loaded), (0, 1))
        self.assertEqual(client.planner_version(loaded), 3)
        self.assertEqual(client.adapter_roles(loaded), {})

    def test_the_staged_release_folder_lists_the_file_the_installer_asks_for(self):
        from maris3d import cli
        folder = os.path.join(ROOT, "hf", "Maris3D-Blender")
        if not os.path.exists(os.path.join(folder, U.MANIFEST)):
            self.skipTest("no staged release folder in this tree")
        roles = {e["role"]: e for e in U.read_manifest(folder)["files"]}
        self.assertEqual(roles["base"]["file"], cli.MODELS["q8_0"])
        self.assertEqual(roles["edit"]["file"], cli.MODELS["edit-lora"])
        self.assertEqual(roles["planner"]["file"], cli.MODELS["planner-lora"])
        with open(os.path.join(folder, "SHA256SUMS")) as f:
            sums = {line.split()[1]: line.split()[0] for line in f if line.strip()}
        for entry in roles.values():
            self.assertEqual(sums.get(entry["file"]), entry["sha256"], entry["file"])

    def test_a_release_for_a_newer_program_is_refused_and_nothing_is_touched(self):
        before = self.have()
        self.put("maris3d-slm-blender-0.5b-planner-v4-lora-f16.gguf", b"planner v4, another answer shape")
        os.remove(os.path.join(self.src, PLAN3))
        U.write_manifest(self.src, [("base", "v1", BASE), ("planner", "v4", "maris3d-slm-blender-0.5b-planner-v4-lora-f16.gguf")],
                         "0.2.0", needs_app="0.2.0")
        with self.assertRaises(ValueError) as raised:
            U.update(self.src, self.models, log=lambda *_: None)
        self.assertIn("update the program first", str(raised.exception))
        self.assertEqual(self.have(), before)                       # the old planner still serves
        self.assertEqual(U.read_installed(self.models)["release"], "0.1.0")
        self.assertEqual(U.read_manifest(self.src, app="0.2.0")["release"], "0.2.0")   # the new program takes it
        self.assertEqual(U.read_manifest(self.src, app="0.2.1.dev0")["release"], "0.2.0")

    def test_an_answer_format_this_program_cannot_read_is_refused(self):
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v9", PLAN3)], "0.1.5",
                         extra={"planner": {"format": "outline+parts/1"}})
        with self.assertRaises(ValueError):
            U.update(self.src, self.models, log=lambda *_: None)

    def test_a_retrained_planner_brings_its_own_prompt_and_the_old_program_sends_it(self):
        from maris3d.addon import client
        from maris3d.copilot import plan
        self.put(PLAN31, b"planner v3.2, trained on more names")
        new_prompt = plan.PLANNER_V3_SYSTEM.replace("Recipes: armchair,", "Recipes: anvil, armchair,")
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v3.2", PLAN31)], "0.1.1",
                         needs_app="0.1.0", extra={"planner": {"format": "items/1", "system": new_prompt}})
        self.assertEqual(U.update(self.src, self.models, log=lambda *_: None)["failed"], [])
        loaded = [{"id": 0, "path": os.path.join(self.models, EDIT)}, {"id": 1, "path": os.path.join(self.models, PLAN31)}]
        self.assertEqual(client.planner_card(loaded), {"format": "items/1", "system": new_prompt})
        self.assertEqual(client.planner_card([{"id": 1, "path": "/elsewhere/" + PLAN31}]), {})   # no card: built-in prompt

        class Runtime:
            planner_id, planner_version, planner_system = 1, 3, new_prompt
            sent = None

            def chat(self, messages, tools, **kw):
                Runtime.sent = messages
                return {"content": '{"items":[{"id":"anvil_1","recipe":"anvil","count":1}]}'}

        from maris3d.copilot.loop import Copilot
        cop = Copilot.__new__(Copilot)
        cop.runtime, cop.turn, cop.messages = Runtime(), 0, []
        try:
            cop.run("an anvil", mode="plan")
        except Exception:
            pass                                                  # only the prompt that went out matters here
        self.assertIsNotNone(Runtime.sent)
        self.assertEqual(Runtime.sent[0], {"role": "system", "content": new_prompt})

    def test_the_move_to_0_2_renames_the_base_retires_roles_and_says_where_next(self):
        # 0.1 -> 0.2 (14 Nov 2026): 0.2 lives in a host-neutral repository; its base is the same bytes under
        # a new name, it has no build adapter, and the old repository points at the new one
        self.release_2()
        U.update(self.src, self.models, log=lambda *_: None)
        new = os.path.join(self.tmp, "repo-0.2")
        os.makedirs(new)
        base2, words = "maris3d-slm-0.5b-q8_0.gguf", "maris3d-slm-0.5b-edit-words1-lora-f16.gguf"
        shutil.copy(os.path.join(self.src, BASE), os.path.join(new, base2))
        shutil.copy(os.path.join(self.src, PLAN31), os.path.join(new, PLAN31))
        with open(os.path.join(new, words), "wb") as f:
            f.write(b"edit words1")
        U.write_manifest(new, [("base", "v1", base2), ("edit", "words1", words), ("planner", "v3.1", PLAN31)],
                         "0.2.0", retire=["build"])
        log = []
        report = U.update(new, self.models, log=log.append)
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["renamed"], [[BASE, base2]])
        self.assertEqual(report["fetched"], [words])
        self.assertEqual(report["bytes_transferred"], len(b"edit words1"))           # the base is not fetched again
        self.assertEqual(sorted(report["removed"]), sorted([EDIT, BUILD2]))
        self.assertEqual(self.have(), sorted([base2, words, PLAN31]))
        roles = {e["role"]: e["file"] for e in U.read_installed(self.models)["files"]}
        self.assertEqual(roles, {"base": base2, "edit": words, "planner": PLAN31})
        again = U.update(new, self.models, log=lambda *_: None)
        self.assertEqual((again["fetched"], again["removed"], again["renamed"]), ([], [], []))
        # the old repository, republished with a pointer: a 0.1 program is told where 0.2 is
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v3.1", PLAN31),
                                    ("build", "v2", BUILD2)], "0.1.1",
                         moved_to="https://huggingface.co/slm4apps/Maris3D-SLM-0.5B-GGUF")
        self.assertEqual(U.read_manifest(self.src)["moved_to"], "https://huggingface.co/slm4apps/Maris3D-SLM-0.5B-GGUF")

    def test_a_role_not_retired_stays_and_a_bad_retire_is_refused(self):
        self.release_2()
        U.update(self.src, self.models, log=lambda *_: None)
        U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", EDIT), ("planner", "v3.1", PLAN31)], "0.1.2")
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual(report["removed"], [])
        self.assertIn(BUILD2, self.have())
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE)], "0.1.3", retire=["wings"])
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE)], "0.1.3", moved_to="../elsewhere")

    def test_a_manifest_that_names_a_path_is_refused(self):
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE), ("edit", "v1", "../" + os.path.basename(self.src) + "/" + EDIT)], "x")


if __name__ == "__main__":
    unittest.main()
