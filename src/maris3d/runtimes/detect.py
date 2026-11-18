# SPDX-License-Identifier: Apache-2.0
"""Find a model server the user already has. Never starts or downloads anything."""
from .base import get_json
from .llama_server import LlamaServer
from .ollama import Ollama


def _up(url):
    try:
        return get_json(url)
    except Exception:
        return None


def detect(model_hint="maris3d"):
    """Ordered list of ready runtimes: Ollama, running llama-server (9931, 8080)."""
    found = []
    tags = _up("http://127.0.0.1:11434/api/tags")
    if tags:
        names = [m.get("name", "") for m in tags.get("models", [])]
        pick = next((n for n in names if model_hint.lower() in n.lower()), None)
        if pick:
            found.append(Ollama(pick))
    for port in (9931, 8080):
        if _up(f"http://127.0.0.1:{port}/props") is not None:
            found.append(LlamaServer(f"http://127.0.0.1:{port}"))
    return found
