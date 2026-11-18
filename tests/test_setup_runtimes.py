# SPDX-License-Identifier: Apache-2.0
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from maris3d import setup as S
from maris3d.runtimes.llama_server import LlamaServer
from maris3d.runtimes.ollama import Ollama, history_for_send
from maris3d.runtimes.openai_compat import OpenAICompat

SEEN = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        msg = {"role": "assistant", "content": '<tool_call>{"name":"add_primitive","arguments":{"shape":"cube"}}</tool_call>'}
        data = json.dumps({"choices": [{"message": msg}]}).encode()
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

    def test_llama_server_sends_lora_scale_every_request(self):
        rt = LlamaServer(self.url)
        for scale in (0.0, 1.0):
            rt.chat([{"role": "user", "content": "x"}], ["add_primitive"], lora_scale=scale)
        self.assertEqual([b["lora"] for b in SEEN[-2:]], [[{"id": 0, "scale": 0.0}], [{"id": 0, "scale": 1.0}]])
        self.assertEqual(SEEN[-1]["temperature"], 0)

    def test_openai_compat_has_no_lora_field(self):
        OpenAICompat(self.url, "m").chat([{"role": "user", "content": "x"}], ["add_primitive"], lora_scale=1.0)
        self.assertNotIn("lora", SEEN[-1])


OLLAMA_SEEN = []


class OllamaStub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        OLLAMA_SEEN.append(body)
        msg = {"role": "assistant", "content": "",
               "tool_calls": [{"id": "x", "type": "function",
                               "function": {"name": "add_primitive", "arguments": {"shape": "cube"}}}]}
        data = json.dumps({"message": msg}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class OllamaHistory(unittest.TestCase):
    """Follow-up asks 400'd ("can't find closing '}'") when history echoed tool
    arguments as JSON strings; Ollama's runner needs objects (verified live)."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), OllamaStub)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_wire_sends_object_arguments(self):
        history = [{"role": "user", "content": "a red cube"},
                   {"role": "assistant", "content": "", "tool_calls": [
                       {"id": "call_1_1_0", "type": "function", "function": {
                           "name": "add_primitive",
                           "arguments": '{"shape": "cube", "name": "RedCube"}'}}]},
                   {"role": "tool", "tool_call_id": "call_1_1_0", "content": "ok"}]
        Ollama("m", self.url).chat(history, ["add_primitive"])
        sent = OLLAMA_SEEN[-1]["messages"][1]["tool_calls"][0]["function"]["arguments"]
        self.assertEqual(sent, {"shape": "cube", "name": "RedCube"})
        # caller copy untouched: scored wire format keeps string args
        self.assertEqual(history[1]["tool_calls"][0]["function"]["arguments"],
                         '{"shape": "cube", "name": "RedCube"}')

    def test_dict_arguments_and_unparseable_strings_pass_through(self):
        history = [{"role": "assistant", "content": "", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "t", "arguments": {"k": 1}}},
            {"id": "b", "type": "function", "function": {"name": "t", "arguments": "{oops}"}}]}]
        out = history_for_send(history)
        self.assertEqual(out[0]["tool_calls"][0]["function"]["arguments"], {"k": 1})
        self.assertEqual(out[0]["tool_calls"][1]["function"]["arguments"], "{oops}")

    def test_text_tools_declares_schemas_in_a_system_message(self):
        """Ollama's runner 500s the whole ask when one call in a long answer is malformed (verified
        live: a 10-call mug answer with one bad block). The text path keeps the same prompt and lets
        our parser drop the bad block instead of losing the row."""
        history = [{"role": "user", "content": "a red cube"}]
        Ollama("m", self.url, text_tools=True).chat(history, ["add_primitive"])
        sent = OLLAMA_SEEN[-1]
        self.assertNotIn("tools", sent)
        system = sent["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn('"name":"add_primitive"', system["content"])
        self.assertIn("<tool_call>", system["content"])
        self.assertEqual(sent["messages"][1], history[0])  # user turn untouched
        # default keeps the native field so the shipped path is unchanged
        Ollama("m", self.url, text_tools=False).chat(history, ["add_primitive"])
        self.assertIn("tools", OLLAMA_SEEN[-1])


class SetupTests(unittest.TestCase):
    def test_manifest_hash_matches_release(self):
        self.assertTrue(S.check()["tools_manifest_ok"])

    def test_serve_command(self):
        self.assertEqual(S.serve_command("m.gguf"), ["llama-server", "-m", "m.gguf", "--jinja", "-c", "8192", "--temp", "0", "--port", "8080"])
        self.assertIn("--lora-init-without-apply", S.serve_command("m.gguf", "e.gguf"))


if __name__ == "__main__":
    unittest.main()
