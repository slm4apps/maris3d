# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender and imports bpy, so it is GPL-3.0-or-later (see LICENSES/README.md).
"""Runs INSIDE Blender .
  blender -b -P render_scene.py -- <script.py> <out.json> <png_prefix>

1. Runs scene_dump.py unchanged (reset scene, exec the model script, write the dump).
2. Then renders the resulting scene with Workbench, 640x480: <prefix>-3q.png (3/4 front view)
   and <prefix>-side.png (side view from +X), camera auto-framed on all visible mesh-like objects.
The dump is written BEFORE any camera/world is added, so checks see only the model's own scene.
Render problems are reported in the dump under "render" and never raise."""
import json, math, os, runpy, sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:]
out_json, prefix = argv[1], argv[2]

runpy.run_path(os.path.join(HERE, "scene_dump.py"), run_name="__main__")

info = {"pngs": [], "error": None, "framed_on": 0}
try:
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in bpy.data.objects:
        if o.type in ("MESH", "CURVE", "FONT", "SURFACE", "META") and not o.hide_render and not o.hide_viewport:
            try:
                pts += [o.matrix_world @ Vector(c) for c in o.evaluated_get(dg).bound_box]
                info["framed_on"] += 1
            except Exception:
                pass
    if not pts:
        pts = [Vector((x, y, z)) for x in (-1, 1) for y in (-1, 1) for z in (0, 2)]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center = (lo + hi) / 2
    radius = max(0.5, max((p - center).length for p in pts))

    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 640, 480, 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass
    sh = sc.display.shading
    sh.light, sh.color_type, sh.show_object_outline = "STUDIO", "MATERIAL", True
    sh.show_cavity = False
    w = bpy.data.worlds.new("hl_world")
    w.color = (0.72, 0.74, 0.78)
    sc.world = w

    cd = bpy.data.cameras.new("hl_cam")
    cd.lens, cd.sensor_width = 50, 36
    cam = bpy.data.objects.new("hl_cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    vfov = 2 * math.atan(18 * 0.75 / 50)
    dist = radius / math.sin(vfov / 2) * 1.15
    cd.clip_start, cd.clip_end = max(0.01, dist / 1000), dist * 6 + 100
    for tag, az_deg, el_deg in (("3q", 35, 25), ("side", 90, 8)):
        az, el = math.radians(az_deg), math.radians(el_deg)
        d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        cam.location = center + d * dist
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        path = f"{prefix}-{tag}.png"
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        info["pngs"].append(path)
except BaseException as e:
    info["error"] = f"{type(e).__name__}: {str(e)[:200]}"

try:
    d = json.load(open(out_json))
    d["render"] = info
    json.dump(d, open(out_json, "w"))
except Exception:
    pass
