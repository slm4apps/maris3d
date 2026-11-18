# SPDX-License-Identifier: Apache-2.0
from .base import Runtime, post_json
from .llama_server import ADAPTER_SETTINGS, ONE_ROLES


class Ollama(Runtime):
    """Ollama /api/chat. No per-request LoRA, so each adapter is its own model entry: the base model
    with that adapter baked in through a Modelfile (FROM base, ADAPTER file). Roles: "one" (outline
    plan, word edit, talk; `model`) and, optionally, "parts" (`parts_model`). The runtime picks the
    entry by the turn's role and sends that adapter's settings on every request: Ollama's own
    default repeat_penalty is 1.1, which the adapters were not measured with."""
    name = "ollama"

    def __init__(self, model, base_url="http://127.0.0.1:11434", parts_model=None):
        self.base_url = base_url.rstrip("/")
        self.models = {"one": model}
        if parts_model:
            self.models["parts"] = parts_model

    @property
    def model(self):
        return self.models["one"]

    def adapter_for(self, role):
        """The role (entry) that answers a turn of this role."""
        if role in self.models:
            return role
        return "one" if role in ONE_ROLES else None

    def has_role(self, role):
        return self.adapter_for(role) is not None

    @property
    def final_format(self):
        return True

    def chat(self, messages, tool_names=(), max_tokens=1024, role=None):
        active = self.adapter_for(role) or "one"
        use = self.models[active]
        options = {"temperature": 0, "num_predict": max_tokens, "num_ctx": 8192, **ADAPTER_SETTINGS[active]}
        body = {"model": use, "messages": list(messages or []), "stream": False, "options": options}
        try:
            return post_json(self.base_url + "/api/chat", body)["message"]
        except RuntimeError as error:
            raise RuntimeError(f"{error} [ollama model={use}]") from None
