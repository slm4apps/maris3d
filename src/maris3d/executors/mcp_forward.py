# SPDX-License-Identifier: Apache-2.0
"""Copilot inside ANOTHER Blender MCP: the model's native calls are compiled to Python here and sent
through that MCP's own execute-code tool; the scene is read through its scene-info tool.
The model is never asked to write code. The host supplies call_tool(name, args) -> result."""
import json
from dataclasses import dataclass
from typing import Callable

from ..copilot.session import Executor
from .compile import compile_call

# Inside another MCP the scene is the USER's. Undo must never empty it: before the first call we remember, inside
# Blender itself (no scene-tool truncation), the object names that already exist; reset removes only the rest.
# Edits we made to objects that existed before are not reverted (documented limit). No snapshot -> remove nothing.
_SNAPSHOT_CODE = ("import bpy\nbpy.app.driver_namespace['_slm_keep'] = sorted(o.name for o in bpy.data.objects)\n")
_RESET_CODE = ("import bpy\nkeep = bpy.app.driver_namespace.get('_slm_keep')\n"
               "if keep is not None:\n    keep = set(keep)\n    for o in list(bpy.data.objects):\n"
               "        if o.name not in keep:\n            bpy.data.objects.remove(o, do_unlink=True)\n")


def _text(result):
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = result.get("content")
        if isinstance(parts, list):
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return json.dumps(result)
    return str(result)


def _objects_from_json(result):
    text = _text(result)
    start = text.find("{")
    data = json.loads(text[start:]) if start >= 0 else {}
    out = []
    for o in data.get("objects", []):
        out.append({"name": o.get("name", "?"), "type": o.get("type", "MESH"),
                    "loc": o.get("location") or o.get("loc") or [0, 0, 0], "material": o.get("material")})
    return out


@dataclass
class McpProfile:
    code_tool: str
    code_arg: str
    scene_tool: str
    is_error: Callable
    parse_scene: Callable = _objects_from_json


PROFILES = {
    # ahujasid/blender-mcp : execute_blender_code(code), get_scene_info()
    "blender-mcp": McpProfile("execute_blender_code", "code", "get_scene_info",
                              lambda r: _text(r).lstrip().lower().startswith(("error", "failed"))),
}


class McpForwardExecutor(Executor):
    def __init__(self, call_tool, profile="blender-mcp"):
        self.call_tool = call_tool
        self.profile = PROFILES[profile] if isinstance(profile, str) else profile
        self._snapshotted = False

    def _snapshot(self):
        if not self._snapshotted:
            self._send(_SNAPSHOT_CODE)
            self._snapshotted = True

    def _send(self, code):
        return self.call_tool(self.profile.code_tool, {self.profile.code_arg: code})

    def run_call(self, call):
        code, err = compile_call(call)
        if err:
            return False, err
        try:
            self._snapshot()
            result = self._send(code)
        except Exception as error:
            return False, f"{type(error).__name__}: {error}"[-200:]
        if self.profile.is_error(result):
            return False, _text(result)[-200:]
        return True, None

    def reset(self):
        self._snapshot()  # no-op after the first call; if reset comes first, nothing of ours exists yet to remove
        self._send(_RESET_CODE)

    def objects(self):
        try:
            return self.profile.parse_scene(self.call_tool(self.profile.scene_tool, {}))
        except Exception:
            return []
