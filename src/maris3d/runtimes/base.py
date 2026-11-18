# SPDX-License-Identifier: Apache-2.0
import json
import urllib.error
import urllib.request

from ..copilot.protocol import load_tools


class Runtime:
    name = "base"
    supports_lora = False  # only a runtime with verified per-request LoRA may say True

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        raise NotImplementedError

    def tools_payload(self, tool_names):
        tools = load_tools()
        return [tools[n] for n in tool_names]


def post_json(url, body, timeout=900):
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from error


def get_json(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())
