# SPDX-License-Identifier: Apache-2.0
"""maris3d MCP server: stdio, newline-delimited JSON-RPC, standard library only.

Tools: build_scene, edit_scene (our small model plans the native calls, the copilot compiles and runs them),
run_calls (a host model sends native calls itself), scene_info, undo, look.
No tool accepts Blender Python: nobody (host model or ours) is asked to write or execute code.
stdout carries protocol lines only; logs go to stderr."""
import base64
import json
import os

from .. import __version__
import sys

from ..copilot.loop import Copilot
from ..copilot.protocol import load_tools
from ..copilot.session import Session

PROTOCOL = "2024-11-05"
INSTRUCTIONS = (
    "Builds and edits Blender scenes with a small local model. Use build_scene for a new request and edit_scene to change "
    "what already exists (move, recolour, resize, duplicate). Send the user's request as written, short and concrete. "
    "Call scene_info to see the objects and look to see the viewport. undo reverts the last request. "
    "run_calls takes native tool calls ({tool, ...args}) from a host model; there is no way to run Blender code."
)
MAX_INFO_OBJECTS = 4000
MAX_IMAGE_BYTES = 4_000_000
_READ_ONLY = {"readOnlyHint": True}


def _log(*a):
    print("[maris3d-mcp]", *a, file=sys.stderr, flush=True)


def scene_table(objects, limit=20, fields=None):
    """Compact text table: one header line, one line per object, explicit truncated flag."""
    limit = max(1, min(int(limit), MAX_INFO_OBJECTS))
    fields = [f for f in (fields or ["type", "loc", "material"]) if f in ("type", "loc", "material")]
    rows = sorted(objects, key=lambda o: o.get("name", ""))
    shown = rows[:limit]
    head = f"objects={len(rows)} shown={len(shown)} truncated={'true' if len(rows) > len(shown) else 'false'}"
    lines = [head]
    for o in shown:
        parts = [o.get("name", "?")]
        if "type" in fields:
            parts.append(str(o.get("type", "mesh")).lower())
        if "loc" in fields:
            parts.append(str([round(v, 2) for v in o.get("loc", [0, 0, 0])]))
        if "material" in fields and o.get("material"):
            parts.append(f'material {o["material"]}')
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def result_text(result):
    """Short, plain report of one Copilot run for the host."""
    if result.api_error:
        return "model server error: " + result.api_error
    if not result.calls:
        return "no tool calls produced" + (": " + result.text[:200] if result.text else "")
    names = ", ".join(c.get("tool", "?") for c in result.calls)
    if len(result.calls) > 12:                      # a planned scene: say what was built, not 60 names
        counts = {}
        for c in result.calls:
            counts[c.get("tool", "?")] = counts.get(c.get("tool", "?"), 0) + 1
        names = ", ".join(f"{tool} x{n}" for tool, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    out = [f"{len(result.calls)} calls: {names}"]
    built = getattr(result, "built", None)
    if built:
        out.append(f'built {", ".join(built.get("built") or [])}: {built.get("parts", 0)} parts, '
                   f'{built.get("exact", 0)} exact, {built.get("moved", 0) + built.get("missing", 0)} corrected, '
                   f'{built.get("unfixed", 0)} not right after the correction')
    if getattr(result, "mode", None) in ("finish", "place") and result.text:
        out.append(result.text[:300])
    if result.errors:
        out.append("errors: " + "; ".join(f'{e["tool"]}: {e["error"]}' for e in result.errors))
    if result.failures:
        out.append("check failed: " + "; ".join(result.failures))
    if result.hit_cap:
        out.append("stopped at the call cap")
    if result.followup_error:
        out.append(f"the model server rejected the next step ({result.followup_error[:90]}), so the {len(result.calls)} calls "
                   "above were applied and the result may be incomplete; do not retry (a retry duplicates them)")
    elif result.ok:
        out.append("ok")
    return "\n".join(out)


class Server:
    """executor: copilot.session.Executor. runtime: object with chat(), or a callable returning one (lazy detect)."""

    def __init__(self, executor, runtime=None, router=None, checker=None, shots_dir=None):
        self.executor = executor
        self.session = Session(executor)
        self._runtime = runtime
        self.router, self.checker = router, checker
        self._copilot = None
        self.shots_dir = shots_dir or os.path.expanduser("~/.cache/maris3d/live")

    # ---- model side (lazy so that scene_info/undo/run_calls work with no model server running)
    def copilot(self):
        if self._copilot is None:
            runtime = self._runtime() if callable(self._runtime) else self._runtime
            if runtime is None:
                raise RuntimeError("no model server found: start Ollama or llama-server with the maris3d model, then retry")
            self._copilot = Copilot(runtime, self.session, router=self.router, checker=self.checker)
        return self._copilot

    # ---- tools
    def build_scene(self, a):
        # the same entry as the add-on's Auto: with a planner adapter on the server the request is
        # planned first (planner -> compile -> build -> check); without one it is a plain Build
        request, copilot = _text_arg(a, "request"), self.copilot()
        if getattr(copilot.runtime, "planner_id", None) is not None:
            return result_text(copilot.run_auto(request))
        return result_text(copilot.run(request, mode="build"))

    def edit_scene(self, a):
        # a finish ("make the cat smooth") and a move relative to another thing ("put the bench
        # behind the station") are done by code from the words; everything else is the edit model
        request, copilot = _text_arg(a, "request"), self.copilot()
        for by_code in (copilot.run_finish, copilot.run_move):
            done = by_code(request)
            if done is not None:
                return result_text(done)
        return result_text(copilot.run(request, mode="edit"))

    def run_calls(self, a):
        calls = a.get("calls")
        if not isinstance(calls, list) or not calls:
            raise ValueError("calls must be a non-empty list of {tool, ...args}")
        known = load_tools()
        clean = []
        for c in calls[:20]:
            if not isinstance(c, dict) or c.get("tool") not in known:
                raise ValueError(f"unknown tool in call: {str(c)[:80]}")
            clean.append(c)
        results = self.session.apply(clean)
        lines = [f'{c["tool"]}: ' + ("ok" if ok else "error: " + str(err)[-200:]) for c, (ok, err) in zip(clean, results)]
        return "\n".join(lines)

    def scene_info(self, a):
        return scene_table(self.session.objects(), a.get("limit", 20), a.get("fields"))

    def undo(self, a):
        return "undone" if self.session.undo() else "nothing to undo"

    def look(self, a):
        rpc = getattr(self.executor, "rpc", None)
        if rpc is None:
            raise RuntimeError("this executor cannot take screenshots")
        os.makedirs(self.shots_dir, exist_ok=True)
        path = os.path.join(self.shots_dir, "look.png")  # fixed by the server, never taken from the caller
        res = rpc("screenshot", path=path)
        if not res.get("ok", True) or not os.path.exists(path):
            raise RuntimeError("screenshot failed: " + str(res.get("error", "no file")))
        if os.path.getsize(path) > MAX_IMAGE_BYTES:
            raise RuntimeError(f"screenshot is larger than {MAX_IMAGE_BYTES} bytes; make the Blender window smaller")
        with open(path, "rb") as f:
            return {"image": base64.b64encode(f.read()).decode()}

    def table(self):
        return {
            "build_scene": (self.build_scene, "Build a new scene part from a short request, e.g. 'a table with four legs'.",
                            {"request": {"type": "string", "description": "What to build, as the user wrote it."}}, ["request"], {}),
            "edit_scene": (self.edit_scene, "Change objects that already exist (move, recolour, resize, duplicate).",
                           {"request": {"type": "string", "description": "The change, as the user wrote it."}}, ["request"], {}),
            "run_calls": (self.run_calls, "Run native tool calls sent by a host model. Each call is {tool, ...args}; max 20.",
                          {"calls": {"type": "array", "items": {"type": "object"}}}, ["calls"], {}),
            "scene_info": (self.scene_info, "List scene objects as a compact text table.",
                           {"limit": {"type": "integer"}, "fields": {"type": "array", "items": {"type": "string"}}}, [], _READ_ONLY),
            "undo": (self.undo, "Undo the last request or call batch.", {}, [], {}),
            "look": (self.look, "Screenshot of the Blender viewport (PNG).", {}, [], _READ_ONLY),
        }

    # ---- JSON-RPC
    def tools_list(self):
        return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r},
                 **({"annotations": ann} if ann else {})} for n, (_, d, p, r, ann) in self.table().items()]

    def call(self, name, args):
        entry = self.table().get(name)
        if entry is None:
            raise ValueError(f"unknown tool: {name}")
        if name != "undo" or self.session.batches:
            ensure = getattr(self.executor, "ensure", None)
            if ensure:
                ensure()  # attach to the open window or launch one; raises a plain message if it cannot
        out = entry[0](args or {})
        if isinstance(out, dict) and "image" in out:
            return [{"type": "image", "data": out["image"], "mimeType": "image/png"}]
        return [{"type": "text", "text": out}]

    def handle(self, msg):
        """One JSON-RPC message -> reply dict, or None for a notification."""
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method == "initialize":
            return _ok(mid, {"protocolVersion": params.get("protocolVersion", PROTOCOL), "capabilities": {"tools": {}},
                             "serverInfo": {"name": "maris3d-blender", "version": __version__}, "instructions": INSTRUCTIONS})
        if method == "ping":
            return _ok(mid, {})
        if method == "tools/list":
            return _ok(mid, {"tools": self.tools_list()})
        if method == "tools/call":
            try:
                return _ok(mid, {"content": self.call(params.get("name"), params.get("arguments")), "isError": False})
            except Exception as error:
                _log("tool error", params.get("name"), repr(error))
                return _ok(mid, {"content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}], "isError": True})
        if mid is not None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return None


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _text_arg(a, key):
    value = a.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def serve(server, stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = server.handle(json.loads(line))
        except Exception as error:
            _log("bad message", repr(error))
            continue
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main():
    from ..executors.live import LiveExecutor
    from ..runtimes.detect import detect

    from ..runtimes.llama_server import LlamaServer

    def pick():
        url = os.getenv("MARIS3D_LLAMA_URL")  # explicit llama-server (--jinja, optional --lora); skips detection
        if url:
            return LlamaServer.discover(url)
        tag = os.getenv("MARIS3D_OLLAMA_MODEL")  # explicit Ollama tag (standard template); optional edit tag with the adapter
        if tag:
            from ..runtimes.ollama import Ollama
            _log("runtime: ollama tag", tag)
            return Ollama(tag, os.getenv("MARIS3D_OLLAMA_URL", "http://127.0.0.1:11434"), os.getenv("MARIS3D_OLLAMA_EDIT_MODEL"))
        found = [LlamaServer.discover(f.base_url, f.model) if f.name == "llama-server" else f for f in detect()]
        _log("runtime: auto-detected", getattr(found[0], "name", "?") if found else "none", getattr(found[0], "model", "") if found else "")
        return found[0] if found else None

    port = int(os.environ.get("BLENDER_LIVE_PORT", "9877"))
    serve(Server(LiveExecutor(port=port), runtime=pick))


if __name__ == "__main__":
    main()
