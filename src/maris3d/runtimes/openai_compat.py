# SPDX-License-Identifier: Apache-2.0
from .base import Runtime, post_json


class OpenAICompat(Runtime):
    """Any OpenAI-style /v1/chat/completions server (LM Studio, Jan, Open WebUI backend). Treated as a plain model:
    no adapter control, so edit requests run on the base model unless the user loads a merged edit model."""
    name = "openai-compat"

    def __init__(self, base_url, model):
        self.base_url, self.model = base_url.rstrip("/"), model

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        body = {"model": self.model, "messages": messages, "tools": self.tools_payload(tool_names),
                "temperature": 0, "max_tokens": max_tokens}
        out = post_json(self.base_url + "/v1/chat/completions", body)
        return out["choices"][0]["message"]
