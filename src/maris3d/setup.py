# SPDX-License-Identifier: Apache-2.0
"""Setup helpers: use what the user has, say exactly what is missing, never download on its own.

  python3 -m maris3d.setup check            hash of the tool manifest, runtimes found, Blender found
  python3 -m maris3d.setup serve-command M [EDIT_LORA]   print the llama-server command for a model file
  python3 -m maris3d.setup smoke            one tiny request through the first runtime found
"""
import json
import shutil
import sys

from .copilot.protocol import tools_sha256, load_tools
from .executors.live import _find_blender
from .runtimes.detect import detect

TOOLS_SHA256 = "8d396db8baab598ae84ad9fcee482cff53183204e6e098689d7f2ad4c681bd6e"


def serve_command(model_path, edit_lora=None, port=8080, llama_server="llama-server"):
    """Serve command from SERVE.md: --jinja, ctx 8192, temp 0; the edit adapter loads at scale 0 and the copilot sends the scale."""
    cmd = [llama_server, "-m", model_path, "--jinja", "-c", "8192", "--temp", "0", "--port", str(port)]
    if edit_lora:
        cmd += ["--lora", edit_lora, "--lora-init-without-apply"]
    return cmd


def _llama_server():
    """The one `maris3d install` unpacked, else the one on PATH."""
    try:
        from .cli import find_llama_server
        return find_llama_server()
    except ImportError:
        return shutil.which("llama-server")


def check():
    found = detect()
    return {
        "tools_manifest_ok": tools_sha256() == TOOLS_SHA256,
        "tools_count": len(load_tools()),
        "runtimes": [r.name for r in found],
        "llama_server_binary": _llama_server(),
        "ollama_binary": shutil.which("ollama"),
        "blender": _find_blender(),
    }


def smoke():
    """One build request through the first runtime found, no Blender needed. Returns (ok, text)."""
    found = detect()
    if not found:
        return False, "no model server found: start Ollama, llama-server (port 8080 or 9931) or LM Studio with the maris3d model"
    from .copilot.protocol import normalise_calls, trim_tools
    request = "add a red cube"
    try:
        message = found[0].chat([{"role": "user", "content": request}], trim_tools(request), lora_scale=0.0, max_tokens=256)
    except Exception as error:
        return False, f"{found[0].name} failed: {error!r}"[:300]
    calls = normalise_calls(message)
    return bool(calls), (f"{found[0].name}: {len(calls)} native calls ({', '.join(c['tool'] for c in calls)})" if calls
                         else f"{found[0].name} answered with no tool call")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        info = check()
        print(json.dumps(info, indent=1))
        return 0 if info["tools_manifest_ok"] else 1
    if cmd == "serve-command" and len(argv) >= 2:
        print(" ".join(serve_command(argv[1], argv[2] if len(argv) > 2 else None)))
        return 0
    if cmd == "smoke":
        ok, text = smoke()
        print(text)
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
