# SPDX-License-Identifier: GPL-3.0-or-later
"""Model-server clients for the panel. The vendored runtimes carry the exact wire
format the model was scored with. The product is one base file with the one adapter
(outline plan, word edit, talk) and optionally the parts adapter loaded; each turn names its
role and runs that adapter alone. A server with no adapter loaded gets no lora field."""
import re

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


# the one adapter's file name carries its release version (maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf);
# development builds carry the mark "blender-one" instead
ONE_MARK = "blender-one"
ONE_VERSIONED = re.compile(r"-v\d+(?:\.\d+)*-lora")


def role_of(name):
    """"one" or "parts" for an adapter file of that role, by its name; None for any other file."""
    name = str(name).lower()
    if "parts" in name:
        return "parts"
    if ONE_MARK in name or ONE_VERSIONED.search(name):
        return "one"
    return None


def adapter_roles(loaded):
    """{"one": id, "parts": id} for the adapters this server has loaded, read from the server's own
    list by file name, never by position, so any start order is read correctly."""
    out = {}
    for index, item in enumerate(loaded or []):
        ident = item.get("id", index) if isinstance(item, dict) else index
        role = role_of(str(item.get("path", "") if isinstance(item, dict) else "").rsplit("/", 1)[-1])
        if role:
            out[role] = ident
    return out


def make_client(settings):
    """settings: plain dict (backend, server_url, model, ollama_url, ollama_model, ollama_parts_model)
    read on the main thread."""
    if (settings.get("backend") or "LLAMA_SERVER").upper() == "OLLAMA":
        return Ollama(settings.get("ollama_model") or "maris3d-slm-blender-0.5b",
                      settings.get("ollama_url") or "http://127.0.0.1:11434",
                      settings.get("ollama_parts_model") or None)
    url = settings.get("server_url") or "http://127.0.0.1:9931"
    runtime = LlamaServer(url, settings.get("model") or "maris3d")
    runtime.adapters = adapter_roles(adapters(url))
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
