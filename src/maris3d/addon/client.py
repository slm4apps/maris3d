# SPDX-License-Identifier: GPL-3.0-or-later
"""Model-server clients for the panel. The vendored runtimes carry the exact wire
format the model was scored with. The product is one base file with the edit adapter
loaded: the copilot asks for scale 0.0 on a fresh prompt and 1.0 on a correction.
A server with no adapter loaded (the merged single file) gets no lora field at all."""
try:  # assembled extension: vendored single-source copies (byte-equal, fidelity-tested)
    from .vendor.llama_server import LlamaServer
    from .vendor.ollama import Ollama
    from .vendor.runtime_base import get_json
except ImportError:  # running from the source tree (tests, packaging)
    from ..runtimes.llama_server import LlamaServer
    from ..runtimes.ollama import Ollama
    from ..runtimes.base import get_json


def adapters(url):
    """The adapters this server has loaded; [] for a merged single-file server."""
    try:
        out = get_json(url.rstrip("/") + "/lora-adapters", timeout=3)
        return out if isinstance(out, list) else []
    except Exception:
        return []


class AdapterLlamaServer(LlamaServer):
    """One base file + the edit adapter: the copilot's per-request scale picks the mode."""

    def __init__(self, base_url="http://127.0.0.1:9931", model="maris3d", has_adapter=True,
                 adapter_id=0, planner_id=None):
        LlamaServer.__init__(self, base_url, model, adapter_id, planner_id if has_adapter else None)
        self.has_adapter = has_adapter

    def body(self, messages, tool_names, lora_scale, max_tokens, planner=False, role=None):
        if not self.has_adapter:
            lora_scale = None  # merged file: a lora field would be rejected
        return LlamaServer.body(self, messages, tool_names, lora_scale, max_tokens, planner, role)


def adapter_ids(loaded):
    """(edit id, planner id or None) from the server's own adapter list -- by file name, never by
    position, so a server started with the adapters in either order is read correctly."""
    edit, planner = None, None
    for index, item in enumerate(loaded or []):
        ident = item.get("id", index) if isinstance(item, dict) else index
        name = str(item.get("path", "") if isinstance(item, dict) else "").rsplit("/", 1)[-1].lower()
        if "planner" in name:
            planner = ident
        elif role_of(name) is None and edit is None:
            edit = ident
    return edit, planner


def role_of(name):
    """"parts" or "build" for an adapter file of that role (`...parts-v1...`, `...build-v2...`), by
    its name; None for the edit and planner adapters, which adapter_ids reads."""
    name = str(name).lower()
    if "parts" in name:
        return "parts"
    if "build-v" in name or "build_v" in name:
        return "build"
    return None


def adapter_roles(loaded):
    """{"parts": id, "build": id} for the further adapters this server has loaded."""
    out = {}
    for index, item in enumerate(loaded or []):
        ident = item.get("id", index) if isinstance(item, dict) else index
        role = role_of(str(item.get("path", "") if isinstance(item, dict) else "").rsplit("/", 1)[-1])
        if role:
            out[role] = ident
    return out


def planner_version(loaded):
    """3 when the loaded planner is the one that lists items with place words, else 1.

    Read from the file name, like the ids: the v3 adapter ships as `...planner-v3...gguf`. The two
    planners were trained on different system prompts and answer in different shapes, so Plan mode
    has to know which one it is talking to.
    """
    for item in loaded or []:
        name = str(item.get("path", "") if isinstance(item, dict) else "").rsplit("/", 1)[-1].lower()
        if "planner" in name and ("v3" in name):
            return 3
    return 1


def planner_card(loaded):
    """What the installed planner says about itself: {"format", "system"} from the installed.json
    the updater keeps beside the model files, {} when there is none (a server on another machine,
    files fetched by hand). With it a retrained planner is sent the prompt IT was trained on."""
    import json
    import os
    for item in loaded or []:
        path = str(item.get("path", "") if isinstance(item, dict) else "")
        if "planner" not in path.rsplit("/", 1)[-1].lower():
            continue
        try:
            with open(os.path.join(os.path.dirname(path), "installed.json"), encoding="utf-8") as f:
                entries = json.load(f).get("files", [])
        except (OSError, ValueError):
            return {}
        for entry in entries:
            if entry.get("role") == "planner" and entry.get("file") == os.path.basename(path):
                return {k: entry[k] for k in ("format", "system") if isinstance(entry.get(k), str)}
    return {}


def make_client(settings):
    """settings: plain dict (backend, server_url, model, ollama_url, ollama_model) — read on the main thread."""
    if (settings.get("backend") or "LLAMA_SERVER").upper() == "OLLAMA":
        return Ollama(settings.get("ollama_model") or "hf.co/slm4apps/Maris3D-Blender:Q8_0",
                     settings.get("ollama_url") or "http://127.0.0.1:11434")
    url = settings.get("server_url") or "http://127.0.0.1:9931"
    loaded = adapters(url)
    edit, planner = adapter_ids(loaded)
    runtime = AdapterLlamaServer(url, settings.get("model") or "maris3d", edit is not None,
                                 edit if edit is not None else 0, planner)
    runtime.planner_version = planner_version(loaded)
    card = planner_card(loaded)
    if card.get("format") == "items/1":
        runtime.planner_version = 3
    if card.get("system") and runtime.planner_version == 3:
        runtime.planner_system = card["system"]
    runtime.adapters = adapter_roles(loaded) if edit is not None else {}
    return runtime


def ping(settings):
    """One-line server status for the panel, from whichever backend is configured."""
    if (settings.get("backend") or "LLAMA_SERVER").upper() == "OLLAMA":
        url = (settings.get("ollama_url") or "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
        tags = get_json(url, timeout=4)
        names = [m.get("name", "") for m in tags.get("models", [])]
        pick = next((n for n in names if "maris3d" in n.lower()), None)
        return (f"Ollama up: {len(names)} models" + (f", maris3d as '{pick}'" if pick else ", maris3d NOT pulled"))
    url = (settings.get("server_url") or "http://127.0.0.1:9931").rstrip("/") + "/props"
    props = get_json(url, timeout=4)
    return f"llama-server up ({props.get('model_path', '?').rsplit('/', 1)[-1]})"
