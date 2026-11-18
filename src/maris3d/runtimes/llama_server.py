# SPDX-License-Identifier: Apache-2.0
from .base import Runtime, post_json


# The one adapter answers the outline plan, the word edit and the talk; the parts adapter (an
# add-on) answers the parts turns. A turn names its role: "planner" and "edit" are the one
# adapter's, "parts" is the parts adapter's when it is loaded, else the one adapter's.
ONE_ROLES = ("planner", "parts", "edit")

# Request settings per adapter, sent on every turn so each adapter runs with the settings it was
# measured with: the model file's own default repeat_penalty 1.05 (general.sampling.penalty_repeat);
# at 1.0 the parts adapter repeats "most, most, most" for every size. A turn that runs no adapter
# (a server with none loaded) gets the base model's row.
ADAPTER_SETTINGS = {
    "one": {"repeat_penalty": 1.05},
    "parts": {"repeat_penalty": 1.05},
    None: {"repeat_penalty": 1.0},
}


class LlamaServer(Runtime):
    """llama-server started with --jinja. The one runtime with verified per-request LoRA."""
    name = "llama-server"
    supports_lora = True

    def __init__(self, base_url="http://127.0.0.1:8080", model="maris3d"):
        self.base_url, self.model = base_url.rstrip("/"), model
        # adapters by role: {"one": id, "parts": id} (addon/client.py reads the server's list)
        self.adapters = {}

    def adapter_for(self, role):
        """The loaded adapter that answers a turn of this role, or None."""
        if role in self.adapters:
            return role
        return "one" if role in ONE_ROLES and "one" in self.adapters else None

    def has_role(self, role):
        return self.adapter_for(role) is not None

    @property
    def final_format(self):
        """True when the one adapter is loaded."""
        return "one" in self.adapters

    def body(self, messages, tool_names, max_tokens, role=None):
        body = {"model": self.model, "messages": messages}
        if tool_names:  # the copilot sends no tools; an empty "tools" field adds nothing
            body["tools"] = self.tools_payload(tool_names)
        body.update({"temperature": 0, "max_tokens": max_tokens})
        active = self.adapter_for(role)
        if self.adapters:
            # never two adapters at once: the turn's adapter runs alone at 1.0, every other
            # loaded adapter is listed at 0.0 (llama-server would apply it at 1.0 otherwise)
            body["lora"] = [{"id": ident, "scale": 1.0 if name == active else 0.0}
                            for name, ident in self.adapters.items()]
        body.update(ADAPTER_SETTINGS[active])
        return body

    def chat(self, messages, tool_names, max_tokens=1024, role=None):
        out = post_json(self.base_url + "/v1/chat/completions", self.body(messages, tool_names, max_tokens, role))
        return out["choices"][0]["message"]
