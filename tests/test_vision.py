# SPDX-License-Identifier: Apache-2.0
"""Picture input (bpy-free): the one-shot vision command, description clean-up, download checks, the request
our model gets, and the MCP entry. No model is run."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from maris3d.copilot import vision as V  # noqa: E402


class Done:
    def __init__(self, out, rc=0):
        self.stdout, self.returncode = out, rc


def fake_cache(with_files=True):
    cache = Path(tempfile.mkdtemp())
    if with_files:
        d = V.vision_dir(cache)
        d.mkdir(parents=True)
        for n, (_, size) in V.VISION_FILES.items():
            with open(d / n, "wb") as f:
                f.truncate(size)  # sparse file of the right size, no model needed
    return cache


def picture(cache):
    img = cache / "a.png"
    img.write_bytes(b"x")
    return img


class Command(unittest.TestCase):
    def test_one_shot_offline_cpu(self):
        cmd = V.build_command("mtmd", "/c", "/p.png")
        self.assertEqual(cmd[0], "mtmd")
        self.assertIn("--image", cmd)
        self.assertEqual(cmd[cmd.index("--temp") + 1], "0")
        self.assertEqual(cmd[cmd.index("--repeat-penalty") + 1], str(V.REPEAT_PENALTY))
        self.assertEqual(cmd[cmd.index("-p") + 1], V.PROMPT)
        self.assertNotIn("--port", cmd)  # a one-shot tool, no server stays up

    def test_finds_cli_in_cache_then_path_then_homebrew(self):
        cache = Path(tempfile.mkdtemp())
        self.assertEqual(V.find_mtmd_cli(cache, which=lambda n: "/x/llama-mtmd-cli"), "/x/llama-mtmd-cli")
        extra = Path(tempfile.mkdtemp())
        (extra / V.EXE).write_text("")
        self.assertEqual(V.find_mtmd_cli(cache, which=lambda n: None, extra=(str(extra),)), str(extra / V.EXE))
        self.assertIsNone(V.find_mtmd_cli(cache, which=lambda n: None, extra=()))


class Clean(unittest.TestCase):
    def test_drops_logs_markdown_headings_and_repeats(self):
        raw = ("llama_model_load: x\nencoding image slice...\n"
               "The image shows a street. Here is the detailed description:\n"
               "- **Objects Present:**\n  - There are two people on a bench.\n"
               "  - There are two people on a bench.\n1. **Trees**: A green tree stands on the left.\n")
        self.assertEqual(V.clean_description(raw),
                         "The image shows a street. There are two people on a bench. A green tree stands on the left.")

    def test_keeps_whole_sentences_up_to_the_limit(self):
        raw = " ".join(f"Sentence number {w} is here." for w in ("one", "two", "three", "four", "five"))
        out = V.clean_description(raw, max_chars=60)
        self.assertTrue(out.endswith("."))
        self.assertLessEqual(len(out), 60)
        self.assertTrue(out.startswith("Sentence number one"))


class Describe(unittest.TestCase):
    def test_one_question_runs_once(self):
        cache = fake_cache()
        run = mock.Mock(return_value=Done("A small green tree.\n"))
        self.assertEqual(V.describe(picture(cache), cache, prompt="What is it?", run=run, which=lambda n: "/bin/mtmd"),
                         ("A small green tree.", None))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], V.TIMEOUT)

    def test_default_asks_short_questions_and_composes(self):
        cache = fake_cache()
        answers = {q: a for (_, q, _), a in zip(V.PASSES, ("Tree.", "Tree, ground", "Green."))}
        run = mock.Mock(side_effect=lambda cmd, **k: Done(answers[cmd[cmd.index("-p") + 1]] + "\n"))
        self.assertEqual(V.describe(picture(cache), cache, run=run, which=lambda n: "/b"), ("a green tree", None))
        self.assertEqual(run.call_count, len(V.PASSES))  # one run per question, no long pass needed

    def test_long_description_only_when_short_answers_are_empty(self):
        cache = fake_cache()
        run = mock.Mock(side_effect=lambda cmd, **k: Done(
            "A red box on the ground.\n" if cmd[cmd.index("-p") + 1] == V.PROMPT else "3.\n"))
        self.assertEqual(V.describe(picture(cache), cache, run=run, which=lambda n: "/b")[0], "A red box")
        self.assertEqual(run.call_count, len(V.PASSES) + 1)

    def test_missing_pieces_say_why(self):
        cache = fake_cache()
        img = picture(cache)
        with mock.patch.object(V, "find_mtmd_cli", return_value=None):
            self.assertIn("llama-mtmd-cli", V.describe(img, cache)[1])
        self.assertEqual(V.describe(cache / "none.png", cache, which=lambda n: "/b")[1], "picture not found")
        self.assertIn("--vision", V.describe(img, fake_cache(False), which=lambda n: "/b")[1])

    def test_failure_and_timeout_give_no_text(self):
        cache = fake_cache()
        img = picture(cache)
        self.assertIsNone(V.describe(img, cache, run=lambda *a, **k: Done("", 1), which=lambda n: "/b")[0])

        def slow(*a, **k):
            raise subprocess.TimeoutExpired("x", 1)
        text, why = V.describe(img, cache, run=slow, which=lambda n: "/b")
        self.assertIsNone(text)
        self.assertIn("longer", why)


class OneModelAtATime(unittest.TestCase):
    def test_pause_stops_our_server_and_resume_starts_the_same_command(self):
        cache = Path(tempfile.mkdtemp())
        cmd = ["llama-server", "-m", "base.gguf", "--port", "9931"]
        (cache / "serve.pid").write_text("4242")
        (cache / "serve.cmd").write_text(json.dumps(cmd))
        state = {"alive": True}
        kill = mock.Mock(side_effect=lambda pid, sig: state.update(alive=False))
        self.assertEqual(V.pause_server(cache, alive=lambda p: state["alive"], kill=kill, sleep=lambda s: None), cmd)
        kill.assert_called_once()
        proc = mock.Mock(pid=5151)
        proc.poll.return_value = None
        popen = mock.Mock(return_value=proc)
        self.assertTrue(V.resume_server(cache, cmd, popen=popen, ready=lambda port: port == "9931",
                                        sleep=lambda s: None))
        self.assertEqual(popen.call_args.args[0], cmd)
        self.assertEqual((cache / "serve.pid").read_text(), "5151")

    def test_a_server_we_did_not_start_is_left_alone(self):
        cache = Path(tempfile.mkdtemp())
        (cache / "serve.pid").write_text("4242")          # no serve.cmd: we cannot start it again
        kill = mock.Mock()
        self.assertIsNone(V.pause_server(cache, alive=lambda p: True, kill=kill))
        kill.assert_not_called()
        self.assertTrue(V.resume_server(cache, None))

    def test_describe_alone_restarts_even_when_the_picture_fails(self):
        with mock.patch.object(V, "pause_server", return_value=["s"]), \
             mock.patch.object(V, "resume_server", return_value=True) as res, \
             mock.patch.object(V, "describe", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                V.describe_alone("x.png", "/c", room=lambda: False)
        res.assert_called_once_with("/c", ["s"])

    def test_with_room_the_server_stays_up(self):
        with mock.patch.object(V, "pause_server") as pause, \
             mock.patch.object(V, "describe", return_value=("a red ball", None)):
            self.assertEqual(V.describe_alone("x.png", "/c", room=lambda: True), ("a red ball", None))
        pause.assert_not_called()

    def test_room_rule(self):
        self.assertTrue(V.room_for_vision(V.VISION_PEAK + V.MEMORY_MARGIN))
        self.assertFalse(V.room_for_vision(V.VISION_PEAK))
        with mock.patch.object(V, "available_memory", return_value=None):
            self.assertFalse(V.room_for_vision())          # unknown: play safe
        free = V.available_memory()
        self.assertTrue(free is None or free > 0)


class Request(unittest.TestCase):
    def test_compose_short_request(self):
        self.assertEqual(V.compose({"name": "5 brown chairs.", "colour": "Brown."}), "5 brown chairs")
        self.assertEqual(V.compose({"name": "4 green spheres.", "colour": "Green."}), "4 green spheres")
        self.assertEqual(V.compose({"name": "A sphere", "colour": "White"}), "A white sphere")
        self.assertEqual(V.compose({"name": "3.", "objects": "1.", "colour": "Red."}), "")
        self.assertEqual(V.compose({"name": "3.", "objects": "box, cube", "colour": "Red."}), "a red box")

    def test_compose_real_answers(self):
        """Answers the 500M model gave on the PIC benchmark pictures."""
        self.assertEqual(V.compose({"name": "3D model of a table.", "objects": "1, 2, 3.", "colour": "Green."}),
                         "a green table")
        self.assertEqual(V.compose({"name": "3D shapes.", "objects": "Large mushroom, 2. Small grey circle.",
                                    "colour": "Gray."}), "a gray large mushroom")
        self.assertEqual(V.compose({"name": "3D shapes.", "objects": "Black sphere Gray cube Small gray square",
                                    "colour": "Black."}), "a black sphere")
        self.assertEqual(V.compose({"name": "3.", "objects": "1, gray, red.", "colour": "Gray."}), "")
        self.assertEqual(V.compose({"name": "I.", "objects": "I, cube, triangle.", "colour": "Gray."}), "a gray cube")

    def test_setting_and_long_text(self):
        self.assertEqual(V.compose({"name": "3D shape on grey background.", "objects": "1, 2.", "colour": "Gray."}), "")
        self.assertEqual(V.compose({"name": "Lamp on a grey surface.", "colour": "Gray."}), "a gray lamp")
        self.assertEqual(V.compose({"name": "1.", "objects": "1.", "colour": "Orange.",
                                    "long": "The image depicts a large orange sphere placed on a flat grey surface."}),
                         "a large orange sphere")
        self.assertEqual(V.compose({"name": "1.", "objects": "1, 2.", "colour": "Gray.",
                                    "long": "The image is a grey triangle with sharp edges and vertices."}),
                         "a grey triangle")

    def test_floor_is_not_an_item(self):
        self.assertEqual(V._items("1 red ball, 1 gray square."), ["1 red ball"])
        self.assertEqual(V._items("Blue sphere, 2. Gray square."), ["Blue sphere"])
        self.assertEqual(V.compose({"name": "Snowman", "colour": "Blue-ish"}), "a snowman")
        self.assertEqual(V.compose({"name": "1 red ball", "colour": "Red"}), "a red ball")
        self.assertEqual(V.compose({"name": "1 ball", "colour": "Red"}), "a red ball")

    def test_picture_alone_and_with_typed_words(self):
        self.assertEqual(V.to_request("a red chair"), "a red chair")
        self.assertEqual(V.to_request("a red chair", "put it on a hill."), "put it on a hill: a red chair")


class Download(unittest.TestCase):
    def test_checks_sha(self):
        cache = Path(tempfile.mkdtemp())
        with self.assertRaises(RuntimeError):
            V.download_vision(cache, lambda url: b"not the model", say=lambda m: None)
        self.assertFalse(any(V.vision_dir(cache).glob("*.gguf")))  # nothing kept after a mismatch

    def test_accepts_matching_sha(self):
        cache = Path(tempfile.mkdtemp())
        body = b"tiny"
        sha = hashlib.sha256(body).hexdigest()
        with mock.patch.dict(V.VISION_FILES, {V.MODEL_FILE: (sha, 4)}, clear=True):
            V.download_vision(cache, lambda url: body, say=lambda m: None)
            self.assertTrue(V.vision_ready(cache))

    def test_uses_an_earlier_local_copy_without_fetching(self):
        cache, local = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        body = b"tiny"
        (local / V.MODEL_FILE).write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()
        fetch = mock.Mock(side_effect=AssertionError("must not download"))
        with mock.patch.dict(V.VISION_FILES, {V.MODEL_FILE: (sha, 4)}, clear=True):
            V.download_vision(cache, fetch, say=lambda m: None, local=[local])
            self.assertTrue(V.vision_ready(cache))

    def test_pins_and_source(self):
        self.assertTrue(V.VISION_REPO.startswith("https://huggingface.co/ggml-org/"))
        for sha, _ in V.VISION_FILES.values():
            self.assertEqual(len(sha), 64)


class Mcp(unittest.TestCase):
    def test_scene_request_takes_an_image(self):
        from maris3d.mcp import server as S
        srv = S.Server(executor=mock.Mock(), runtime=None)
        cop = mock.Mock()
        cop.run_auto.return_value = mock.Mock(calls=[], errors=[], failures=[], ok=True, mode=None, text="", built=None, api_error=None)
        srv._copilot = cop
        img = picture(Path(tempfile.mkdtemp()))
        with mock.patch.object(V, "describe_alone", return_value=("A red chair.", None)):
            out = srv.scene_request({"image": str(img)})
        cop.run_auto.assert_called_once_with("A red chair.")
        self.assertTrue(out.startswith("picture: A red chair."))
        with mock.patch.object(V, "describe_alone", return_value=(None, "picture input is not set up")):
            with self.assertRaises(RuntimeError):
                srv.scene_request({"image": str(img)})
        with self.assertRaises(ValueError):
            srv.scene_request({"image": "/tmp/notes.txt"})
        schema = {t["name"]: t for t in srv.tools_list()}["scene_request"]["inputSchema"]
        self.assertIn("image", schema["properties"])


if __name__ == "__main__":
    unittest.main()
