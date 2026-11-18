# SPDX-License-Identifier: Apache-2.0
"""The one adapter (outline, edit, talk) and the parts add-on: routed by role, each sent its final prompt.
Ollama has one model entry per adapter and picks the entry by role."""
import json
import unittest
from unittest import mock

from maris3d.addon import client as C
from maris3d.copilot import plan as PLAN
from maris3d.copilot import vocabulary as V
from maris3d.runtimes import llama_server as LS
from maris3d.runtimes.llama_server import LlamaServer
from maris3d.runtimes.ollama import Ollama

ONE = {"id": 4, "path": "/m/maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf"}
PARTS = {"id": 5, "path": "/m/maris3d-slm-blender-parts-lora-f16.gguf"}


class OneAdapter(unittest.TestCase):
    def setUp(self):
        self.rt = LlamaServer()
        self.rt.adapters = {"one": 4}

    def test_file_name_gives_the_role(self):
        self.assertEqual(C.role_of("maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf"), "one")
        self.assertEqual(C.role_of("maris3d-slm-blender-parts-lora-f16.gguf"), "parts")
        self.assertIsNone(C.role_of("maris3d-slm-blender-0.5b-q8_0.gguf"))
        self.assertEqual(C.adapter_roles([PARTS, ONE]), {"one": 4, "parts": 5})

    def test_every_role_runs_the_one_adapter(self):
        for role in ("planner", "parts", "edit"):
            self.assertTrue(self.rt.has_role(role))
            body = self.rt.body([], [], 10, role=role)
            self.assertEqual(body["lora"], [{"id": 4, "scale": 1.0}], role)
        self.assertFalse(self.rt.has_role("build"))
        self.assertTrue(self.rt.final_format)

    def test_a_parts_add_on_takes_only_the_parts_turns(self):
        self.rt.adapters = C.adapter_roles([ONE, PARTS])
        for role, on in (("parts", 5), ("planner", 4), ("edit", 4)):
            body = self.rt.body([], [], 10, role=role)
            self.assertEqual(sorted((x["id"], x["scale"]) for x in body["lora"]),
                             sorted((i, 1.0 if i == on else 0.0) for i in (4, 5)), role)
        self.assertTrue(self.rt.final_format)

    def test_each_adapter_gets_its_own_settings(self):
        # the adapters were scored at the model file's repeat_penalty 1.05 (1.0 breaks the parts designs)
        self.assertEqual(LS.ADAPTER_SETTINGS["one"]["repeat_penalty"], 1.05)
        self.assertEqual(LS.ADAPTER_SETTINGS["parts"]["repeat_penalty"], 1.05)
        self.assertEqual(set(LS.ADAPTER_SETTINGS), {"one", "parts", None})
        self.rt.adapters = {"one": 4, "parts": 5}
        for role in ("parts", "planner", "edit"):
            self.assertEqual(self.rt.body([], [], 10, role=role)["repeat_penalty"], 1.05, role)
        self.assertEqual(self.rt.body([], [], 10)["repeat_penalty"], 1.0)  # no role: the base model
        self.assertEqual(LlamaServer().body([], [], 10, role="edit")["repeat_penalty"], 1.0)  # no adapter loaded

    def test_the_outline_answer_reads_as_items(self):
        self.assertIn('"thing"', V.OUTLINE_SYSTEM)
        out = PLAN.from_outline({"kind": "build", "items": [{"id": "bench_1", "thing": "bench", "count": 2}]})
        self.assertEqual(PLAN.check_items(out), (True, None))
        self.assertEqual(out["items"][0]["recipe"], "bench")
        ok, why = PLAN.check_items({"kind": "question", "say": "Which bench?", "items": []})
        self.assertFalse(ok)
        self.assertEqual(why, "Which bench?")


class OllamaEntries(unittest.TestCase):
    """No per-request LoRA on Ollama: one entry per adapter (base + adapter baked by a Modelfile)."""

    def ask(self, rt, role):
        sent = []

        def fake_post(url, body, timeout=900):
            sent.append(body)
            return {"message": {"role": "assistant", "content": "{}"}}

        with mock.patch("maris3d.runtimes.ollama.post_json", fake_post):
            rt.chat([{"role": "user", "content": "x"}], [], max_tokens=50, role=role)
        return sent[0]

    def test_the_entry_is_picked_by_role(self):
        rt = Ollama("maris3d-one", parts_model="maris3d-parts")
        for role, entry in (("planner", "maris3d-one"), ("edit", "maris3d-one"), ("parts", "maris3d-parts"),
                            (None, "maris3d-one")):
            self.assertEqual(self.ask(rt, role)["model"], entry, role)
        self.assertEqual(self.ask(Ollama("maris3d-one"), "parts")["model"], "maris3d-one")  # no parts entry
        self.assertTrue(rt.has_role("parts") and Ollama("maris3d-one").final_format)

    def test_every_entry_is_sent_its_adapters_repeat_penalty(self):
        # Ollama's own default is 1.1, so the value is always sent
        rt = Ollama("maris3d-one", parts_model="maris3d-parts")
        for role in ("planner", "edit", "parts", None):
            options = self.ask(rt, role)["options"]
            self.assertEqual(options["repeat_penalty"], 1.05, role)
            self.assertEqual(options["temperature"], 0)
            self.assertEqual(options["num_predict"], 50)
        self.assertNotIn("tools", self.ask(rt, "planner"))
        json.dumps(self.ask(rt, "parts"))


if __name__ == "__main__":
    unittest.main()
