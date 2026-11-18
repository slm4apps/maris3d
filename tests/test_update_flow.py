# SPDX-License-Identifier: Apache-2.0
"""A new adapter version installs without a new download of the base, and the old one is removed."""
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
ONE = "maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf"
ONE_NEXT = "maris3d-slm-blender-0.5b-v0.2.1-lora-f16.gguf"
PARTS = "maris3d-slm-blender-parts-lora-f16.gguf"


class UpdateFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src, self.models = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "models")
        os.makedirs(self.src)
        self.put(BASE, b"B" * 300_000)
        self.put(ONE, b"one v1")
        self.put(PARTS, b"parts v1")
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v1", ONE), ("parts", "v1", PARTS)], "0.2.0")
        self.first = U.update(self.src, self.models, log=lambda *_: None)

    def put(self, name, data):
        with open(os.path.join(self.src, name), "wb") as f:
            f.write(data)

    def release_2(self):
        self.put(ONE_NEXT, b"one v2")
        os.remove(os.path.join(self.src, ONE))
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v2", ONE_NEXT), ("parts", "v1", PARTS)], "0.2.1")

    def have(self):
        return sorted(n for n in os.listdir(self.models) if n.endswith(".gguf"))

    def test_first_install_fetches_everything_and_says_how_to_serve(self):
        self.assertEqual(sorted(self.first["fetched"]), sorted([BASE, ONE, PARTS]))
        self.assertEqual(self.first["failed"], [])
        serve = self.first["serve"]
        self.assertEqual(serve[serve.index("-m") + 1], os.path.join(self.models, BASE))
        self.assertEqual([serve[i + 1] for i, w in enumerate(serve) if w == "--lora"],
                         [os.path.join(self.models, ONE), os.path.join(self.models, PARTS)])
        self.assertIn("--lora-init-without-apply", serve)
        self.assertNotIn("--repeat-penalty", serve)       # the per-request table sets it

    def test_a_new_adapter_does_not_fetch_the_base_again_and_the_old_one_goes(self):
        base = os.path.join(self.models, BASE)
        before = (os.stat(base).st_ino, os.stat(base).st_mtime)
        self.release_2()
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual(report["fetched"], [ONE_NEXT])
        self.assertEqual(report["bytes_transferred"], len(b"one v2"))
        self.assertEqual((os.stat(base).st_ino, os.stat(base).st_mtime), before)      # untouched
        self.assertEqual(report["removed"], [ONE])
        self.assertEqual(self.have(), sorted([BASE, ONE_NEXT, PARTS]))
        self.assertEqual(U.read_installed(self.models)["release"], "0.2.1")
        again = U.update(self.src, self.models, log=lambda *_: None)                  # said twice: nothing moves
        self.assertEqual((again["fetched"], again["removed"], again["bytes_transferred"]), ([], [], 0))
        loras = [w for w in again["serve"] if w.endswith(".gguf")][1:]
        self.assertEqual([os.path.basename(p) for p in loras], [ONE_NEXT, PARTS])         # role order

    def test_a_download_with_the_wrong_hash_keeps_the_old_adapter(self):
        self.release_2()
        self.put(ONE_NEXT, b"corrupted on the way")                  # the manifest still has the good hash
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual([f["file"] for f in report["failed"]], [ONE_NEXT])
        self.assertIn(ONE, self.have())                            # still there, still serving
        self.assertNotIn(ONE_NEXT, self.have())
        self.assertFalse([n for n in os.listdir(self.models) if n.endswith(".part")])
        self.assertIn(os.path.join(self.models, ONE), report["serve"])
        self.assertEqual(U.read_installed(self.models)["release"], "0.2.0")
        self.assertEqual(U.main(["update", "--from", self.src, "--models", self.models]), 1)
        self.put(ONE_NEXT, b"one v2")                                  # the source is repaired
        self.assertEqual(U.main(["update", "--from", self.src, "--models", self.models]), 0)
        self.assertEqual(self.have(), sorted([BASE, ONE_NEXT, PARTS]))

    def test_a_file_the_user_fetched_by_hand_is_used_and_never_deleted(self):
        models = os.path.join(self.tmp, "by-hand")
        os.makedirs(models)
        for name in (BASE, ONE):
            shutil.copy(os.path.join(self.src, name), models)
        with open(os.path.join(models, "my-notes.gguf"), "wb") as f:
            f.write(b"not ours")
        report = U.update(self.src, models, log=lambda *_: None)
        self.assertEqual(report["fetched"], [PARTS])               # the base was already right
        self.put(ONE_NEXT, b"one v2")
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v2", ONE_NEXT), ("parts", "v1", PARTS)], "0.2.1")
        report = U.update(self.src, models, log=lambda *_: None)
        self.assertEqual(report["removed"], [])                    # the first one adapter was not installed by us
        self.assertTrue(os.path.exists(os.path.join(models, ONE)))
        self.assertTrue(os.path.exists(os.path.join(models, "my-notes.gguf")))
        self.assertNotIn(os.path.join(models, ONE), report["serve"])

    def test_a_changed_file_under_the_same_name_is_fetched_again(self):
        self.put(ONE, b"one v1b, same file name")
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v1b", ONE), ("parts", "v1", PARTS)], "0.2.2")
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual((report["fetched"], report["removed"]), ([ONE], []))
        with open(os.path.join(self.models, ONE), "rb") as f:
            self.assertEqual(f.read(), b"one v1b, same file name")

    def test_a_url_source_works_like_a_folder(self):
        models = os.path.join(self.tmp, "from-url")
        report = U.update(pathlib.Path(self.src).as_uri(), models, log=lambda *_: None)
        self.assertEqual(sorted(report["fetched"]), sorted([BASE, ONE, PARTS]))
        self.assertEqual(report["failed"], [])

    def test_the_main_command_updates_the_folder_install_uses_and_serve_takes_the_new_file(self):
        from unittest import mock
        from maris3d import cli
        cache = pathlib.Path(self.tmp) / "cache"
        said = []
        with mock.patch.object(cli, "CACHE", cache), mock.patch.object(cli, "_say", said.append):
            self.assertEqual(cli.main(["update", "--from", self.src]), 0)
            self.assertEqual(cli._installed()["one"], str(cache / "models" / ONE))
            self.release_2()
            self.assertEqual(cli.main(["update", "--from", self.src]), 0)
            now = cli._installed()
            self.assertEqual(now["one"], str(cache / "models" / ONE_NEXT))              # what serve start loads
            self.assertEqual(now["base"], str(cache / "models" / BASE))
            self.assertIn("kept 2, fetched 1, removed 1", " ".join(said))
            self.put(ONE_NEXT, b"corrupted")
            os.remove(now["one"])
            self.assertEqual(cli.main(["update", "--from", self.src]), 1)

    def test_the_installer_and_the_updater_use_one_folder_and_the_role_comes_from_the_name(self):
        from maris3d import cli
        from maris3d.addon import client
        self.assertEqual(os.path.expanduser(U.DEFAULT_MODELS), str(cli.CACHE / "models"))
        loaded = [{"id": 0, "path": "/m/" + cli.MODELS["one-lora"]}, {"id": 1, "path": "/m/" + cli.MODELS["parts-lora"]},
                  {"id": 2, "path": "/m/" + cli.MODELS["q8_0"]}]
        self.assertEqual(client.adapter_roles(loaded), {"one": 0, "parts": 1})
        self.assertEqual(U.ROLES, ("base", "one", "parts"))

    def test_the_staged_release_folder_lists_the_file_the_installer_asks_for(self):
        from maris3d import cli
        folder = os.path.join(ROOT, "hf", "Maris3D-Blender")
        if not os.path.exists(os.path.join(folder, U.MANIFEST)):
            self.skipTest("no staged release folder in this tree")
        try:
            roles = {e["role"]: e for e in U.read_manifest(folder)["files"]}
        except ValueError:
            self.skipTest("the staged release folder is not a 0.2 release yet")
        self.assertEqual(roles["base"]["file"], cli.MODELS["q8_0"])
        self.assertEqual(roles["one"]["file"], cli.MODELS["one-lora"])
        with open(os.path.join(folder, "SHA256SUMS")) as f:
            sums = {line.split()[1]: line.split()[0] for line in f if line.strip()}
        for entry in roles.values():
            self.assertEqual(sums.get(entry["file"]), entry["sha256"], entry["file"])

    def test_a_release_for_a_newer_program_is_refused_and_nothing_is_touched(self):
        before = self.have()
        self.put(ONE_NEXT, b"one v3, another answer shape")
        os.remove(os.path.join(self.src, ONE))
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v3", ONE_NEXT)], "0.3.0", needs_app="0.3.0")
        with self.assertRaises(ValueError) as raised:
            U.update(self.src, self.models, log=lambda *_: None)
        self.assertIn("update the program first", str(raised.exception))
        self.assertEqual(self.have(), before)                       # the old adapter still serves
        self.assertEqual(U.read_installed(self.models)["release"], "0.2.0")
        self.assertEqual(U.read_manifest(self.src, app="0.3.0")["release"], "0.3.0")   # the new program takes it
        self.assertEqual(U.read_manifest(self.src, app="0.3.1.dev0")["release"], "0.3.0")

    def test_an_answer_format_this_program_cannot_read_is_refused(self):
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v9", ONE), ("parts", "v1", PARTS)], "0.2.5",
                         extra={"one": {"format": "outline+parts/1"}})
        with self.assertRaises(ValueError):
            U.update(self.src, self.models, log=lambda *_: None)

    def test_a_retired_role_is_removed_and_a_role_not_retired_stays(self):
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v1", ONE)], "0.2.1")
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual(report["removed"], [])                    # a role the manifest no longer lists stays
        self.assertIn(PARTS, self.have())
        U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v1", ONE)], "0.2.2", retire=["parts"])
        report = U.update(self.src, self.models, log=lambda *_: None)
        self.assertEqual(report["removed"], [PARTS])
        self.assertEqual({e["role"] for e in U.read_installed(self.models)["files"]}, {"base", "one"})
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE)], "0.2.3", retire=[3])
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE)], "0.2.3", moved_to="../elsewhere")

    def test_a_file_renamed_with_the_same_bytes_is_moved_not_fetched_again(self):
        new = os.path.join(self.tmp, "repo-next")
        os.makedirs(new)
        base2 = "maris3d-slm-0.5b-q8_0.gguf"
        shutil.copy(os.path.join(self.src, BASE), os.path.join(new, base2))
        shutil.copy(os.path.join(self.src, ONE), os.path.join(new, ONE))
        U.write_manifest(new, [("base", "v1", base2), ("one", "v1", ONE)], "0.2.1", retire=["parts"])
        report = U.update(new, self.models, log=lambda *_: None)
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["renamed"], [[BASE, base2]])
        self.assertEqual(report["fetched"], [])
        self.assertEqual(self.have(), sorted([base2, ONE]))

    def test_a_manifest_that_names_a_path_is_refused(self):
        with self.assertRaises(ValueError):
            U.write_manifest(self.src, [("base", "v1", BASE), ("one", "v1", "../" + os.path.basename(self.src) + "/" + ONE)], "x")


if __name__ == "__main__":
    unittest.main()
