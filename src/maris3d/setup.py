# SPDX-License-Identifier: Apache-2.0
"""Setup helpers: use what the user has, say exactly what is missing, never download on its own.

  python3 -m maris3d.setup check            hash of the tool manifest, runtimes found, Blender found
  python3 -m maris3d.setup serve-command M [ONE_LORA [PARTS_LORA]]   print the llama-server command for a model file
  python3 -m maris3d.setup smoke            one tiny request through the first runtime found
"""
import json
import shutil
import sys

from .copilot.protocol import tools_sha256, load_tools
from .executors.live import _find_blender
from .runtimes.detect import detect

TOOLS_SHA256 = "8d396db8baab598ae84ad9fcee482cff53183204e6e098689d7f2ad4c681bd6e"


def serve_command(model_path, one_lora=None, parts_lora=None, port=8080, llama_server="llama-server"):
    """Serve command from SERVE.md: --jinja, ctx 8192, temp 0; the adapters load at scale 0 and the
    copilot sends the scale and the repeat penalty with each request."""
    cmd = [llama_server, "-m", model_path, "--jinja", "-c", "8192", "--temp", "0", "--port", str(port)]
    adapters = [a for a in (one_lora, parts_lora) if a]
    for path in adapters:
        cmd += ["--lora", path]
    if adapters:
        cmd.append("--lora-init-without-apply")
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
    """One outline plan request through the first runtime found, no Blender needed. Returns (ok, text)."""
    found = detect()
    if not found:
        return False, "no model server found: start Ollama or llama-server (port 8080 or 9931) with the maris3d model"
    from .copilot import plan as PLAN
    from .copilot import vocabulary as V
    messages = [{"role": "system", "content": V.OUTLINE_SYSTEM}, {"role": "user", "content": "add a red cube"}]
    try:
        message = found[0].chat(messages, [], max_tokens=256, role="planner")
    except Exception as error:
        return False, f"{found[0].name} failed: {error!r}"[:300]
    obj, reason = PLAN.parse_reply(message.get("content") or "")
    ok, reason = PLAN.check_items(PLAN.from_outline(obj)) if reason is None else (False, reason)
    return ok, (f"{found[0].name}: the plan is usable" if ok else f"{found[0].name}: no usable plan ({reason})")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        info = check()
        print(json.dumps(info, indent=1))
        return 0 if info["tools_manifest_ok"] else 1
    if cmd == "serve-command" and len(argv) >= 2:
        print(" ".join(serve_command(*argv[1:4])))
        return 0
    if cmd == "smoke":
        ok, text = smoke()
        print(text)
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
