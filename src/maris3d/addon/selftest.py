# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless self-test: `blender -b --python selftest.py` (run from inside the ASSEMBLED extension).

Validates the full in-Blender path with canned calls (no model server needed):
queue executor, the 26-tool translation, materials, undo, the scene-diff summary.
With MARIS3D_SERVER set it also runs one real request through the copilot (plan first).
Prints 'SELFTEST READY <detail>' on success; a failure prints a traceback and no READY.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the parent of the extension dir

import bpy  # noqa: E402

from maris3d_copilot import executor, summary  # noqa: E402
from maris3d_copilot.vendor.loop import Copilot  # noqa: E402
from maris3d_copilot.vendor.session import Session  # noqa: E402

assert bpy.app.background, "this self-test is the headless path (blender -b)"


def canned_leg():
    ex = executor.QueueExecutor()
    s = Session(ex)
    ex.reset()  # factory-startup ships Cube/Camera/Light; scored rows run on an empty scene
    before = list(ex.objects())
    t0 = time.time()
    results = s.apply([
        {"tool": "add_primitive", "shape": "cube", "name": "Body", "size": 0.9, "location": [0, 0, 0.45]},
        {"tool": "add_primitive", "shape": "cylinder", "name": "Handle", "radius": 0.06, "depth": 0.5,
         "location": [0.55, 0, 0.45], "rotation_deg": [0, 90, 0]},
        {"tool": "set_material", "object": "all", "name": "Brown", "color": [0.36, 0.18, 0.08], "roughness": 0.6},
    ])
    assert all(ok for ok, _ in results), f"a canned call failed: {results}"
    objs = ex.objects()
    names = [o["name"] for o in objs]
    assert len(objs) == 2, names
    assert any("Handle" in n for n in names), names
    assert any(o["material"] == "Brown" for o in objs), [o["material"] for o in objs]
    line = summary.scene_diff(before, objs)
    assert line.startswith("Added 2 objects"), line
    assert "1 material: Brown" in line, line
    # undo (empty-scene replay semantics; the in-app button uses native undo)
    assert s.undo()
    assert not ex.objects(), [o["name"] for o in ex.objects()]  # the one batch reverts fully
    return f"canned ok ({time.time() - t0:.1f}s) — '{line}'"


def live_leg():
    from maris3d_copilot import client
    url = os.getenv("MARIS3D_SERVER")
    model = os.getenv("MARIS3D_MODEL", "maris3d")
    ex = executor.QueueExecutor()
    before = list(ex.objects())
    t0 = time.time()
    res = Copilot(client.make_client({"server_url": url, "model": model}), Session(ex)).run_auto("a red cube")
    dt = time.time() - t0
    if res.api_error:
        return f"live SKIPPED (server error: {res.api_error[:80]})"
    assert res.calls, "the copilot built nothing: " + (res.plan_error or res.text or "no answer")[:80]
    objs = ex.objects()
    return f"live ok ({dt:.1f}s, {len(res.calls)} calls) — '{summary.scene_diff(before, objs)}'"


def main():
    detail = canned_leg()
    if os.environ.get("MARIS3D_SERVER"):
        detail += "; " + live_leg()
    print("SELFTEST READY " + detail)
    return detail


if __name__ == "__main__":
    main()
