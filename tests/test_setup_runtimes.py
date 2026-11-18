# SPDX-License-Identifier: Apache-2.0
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from maris3d import setup as S
from maris3d.runtimes.detect import detect
from maris3d.runtimes.llama_server import LlamaServer
from maris3d.runtimes.ollama import Ollama

SEEN = []


class Stub(BaseHTTPRequestHandler):
    """Answers both wire shapes: llama-server (choices) and Ollama (message)."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.path, body))
        msg = {"role": "assistant", "content": '{"kind": "build", "items": []}'}
        data = json.dumps({"choices": [{"message": msg}], "message": msg}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RuntimeWire(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), Stub)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_llama_server_sends_every_loaded_adapter_and_the_penalty_every_request(self):
        rt = LlamaServer(self.url)
        rt.adapters = {"one": 0, "parts": 1}
        for role in ("planner", "parts"):
            rt.chat([{"role": "user", "content": "x"}], [], role=role)
        (path, planner), (_p, parts) = SEEN[-2:]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(planner["lora"], [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}])
        self.assertEqual(parts["lora"], [{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}])
        self.assertEqual((planner["repeat_penalty"], parts["repeat_penalty"], parts["temperature"]), (1.05, 1.05, 0))

    def test_ollama_sends_the_entry_of_the_role_and_its_penalty(self):
        rt = Ollama("one-entry", self.url, parts_model="parts-entry")
        for role in ("edit", "parts"):
            rt.chat([{"role": "user", "content": "x"}], [], role=role)
        (path, edit), (_p, parts) = SEEN[-2:]
        self.assertEqual(path, "/api/chat")
        self.assertEqual((edit["model"], parts["model"]), ("one-entry", "parts-entry"))
        for body in (edit, parts):
            self.assertEqual(body["options"]["repeat_penalty"], 1.05)   # Ollama's own default is 1.1
            self.assertNotIn("tools", body)
            self.assertFalse(body["stream"])


class SetupTests(unittest.TestCase):
    def test_manifest_hash_matches_release(self):
        self.assertTrue(S.check()["tools_manifest_ok"])

    def test_serve_command(self):
        self.assertEqual(S.serve_command("m.gguf"), ["llama-server", "-m", "m.gguf", "--jinja", "-c", "8192", "--temp", "0", "--port", "8080"])
        cmd = S.serve_command("m.gguf", "one.gguf", "parts.gguf")
        self.assertEqual([cmd[i + 1] for i, a in enumerate(cmd) if a == "--lora"], ["one.gguf", "parts.gguf"])
        self.assertIn("--lora-init-without-apply", cmd)

    def test_only_llama_server_and_ollama_are_detected(self):
        self.assertTrue(all(r.name in ("ollama", "llama-server") for r in detect()))


if __name__ == "__main__":
    unittest.main()
