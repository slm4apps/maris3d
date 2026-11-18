# SPDX-License-Identifier: Apache-2.0
from .base import Runtime, get_json, post_json


class LlamaServer(Runtime):
    """llama-server started with --jinja. The one runtime with verified per-request LoRA."""
    name = "llama-server"
    supports_lora = True

    def __init__(self, base_url="http://127.0.0.1:8080", model="maris3d", adapter_id=0,
                 planner_id=None):
        self.base_url, self.model, self.adapter_id = base_url.rstrip("/"), model, adapter_id
        # id of the planner adapter when the server has it loaded (None: no planner on this server)
        self.planner_id = planner_id
        # further adapters by role: {"parts": id, "build": id} (addon/client.py reads the server's list)
        self.adapters = {}

    @classmethod
    def discover(cls, base_url, model="maris3d"):
        """A client set up from the server's own adapter list, read by file name: the edit adapter,
        the planner, further roles (parts, build). A merged single-file server (no adapters) gets no
        lora field at all, which llama-server would reject."""
        try:
            loaded = get_json(base_url.rstrip("/") + "/lora-adapters", timeout=3)
        except Exception:
            loaded = []
        edit, planner, roles = None, None, {}
        for index, item in enumerate(loaded if isinstance(loaded, list) else []):
            ident = item.get("id", index) if isinstance(item, dict) else index
            name = str(item.get("path", "") if isinstance(item, dict) else "").rsplit("/", 1)[-1].lower()
            if "planner" in name:
                planner = ident
            elif "parts" in name:
                roles["parts"] = ident
            elif "build-v" in name or "build_v" in name:
                roles["build"] = ident
            elif edit is None:
                edit = ident
        runtime = cls(base_url, model, edit if edit is not None else 0, planner)
        runtime.adapters = roles
        runtime.no_adapter = edit is None and planner is None and not roles
        return runtime

    def has_role(self, role):
        return role in self.adapters or (role == "planner" and self.planner_id is not None)

    def body(self, messages, tool_names, lora_scale, max_tokens, planner=False, role=None):
        body = {"model": self.model, "messages": messages}
        if tool_names:  # Plan mode sends no tools; an empty "tools" field adds nothing
            body["tools"] = self.tools_payload(tool_names)
        body.update({"temperature": 0, "repeat_penalty": 1.0, "max_tokens": max_tokens})
        if lora_scale is not None and not getattr(self, "no_adapter", False):
            # llama-server applies loaded adapters at scale 1.0 unless told otherwise: always send it
            body["lora"] = [{"id": self.adapter_id, "scale": float(lora_scale)}]
            role = "planner" if planner else role
            others = dict(self.adapters)
            if self.planner_id is not None:
                others = dict({"planner": self.planner_id}, **others)
            if others:
                # several adapters, never two at once: a turn that names a role runs that adapter
                # alone, every other turn runs without them (merging adapters is what costs build
                # quality, 24.0 -> 14.7). Every loaded adapter is listed, so none stays at 1.0.
                body["lora"] = [{"id": self.adapter_id, "scale": 0.0 if role else float(lora_scale)}] + \
                    [{"id": ident, "scale": 1.0 if name == role else 0.0} for name, ident in others.items()]
        return body

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024, planner=False, role=None):
        role = "planner" if planner else role
        body = (self.body(messages, tool_names, lora_scale, max_tokens, planner=True) if role == "planner"
                else self.body(messages, tool_names, lora_scale, max_tokens, role=role) if role
                else self.body(messages, tool_names, lora_scale, max_tokens))
        out = post_json(self.base_url + "/v1/chat/completions", body)
        return out["choices"][0]["message"]
