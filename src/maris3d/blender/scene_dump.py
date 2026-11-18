# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender and imports bpy, so it is GPL-3.0-or-later (see LICENSES/README.md).
"""Runs INSIDE Blender (blender -b -P scene_dump.py -- <script.py> <out.json>).
Resets to an empty scene, execs the model's script, dumps a scene summary as JSON."""
import sys, json, traceback
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
script_path, out_path = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
result = {"executed": False, "error": None}
try:
    code = open(script_path).read()
    exec(compile(code, "model_script", "exec"), {"__name__": "__main__"})
    result["executed"] = True
except BaseException:
    result["error"] = traceback.format_exc(limit=3)[-800:]

bpy.context.view_layer.update()  # dimensions are stale after scale changes without this
def props(b):
    out = {}
    for p in b.bl_rna.properties:
        if p.type in ("INT", "FLOAT", "BOOLEAN", "STRING", "ENUM") and p.identifier not in ("name", "rna_type"):
            try:
                v = getattr(b, p.identifier)
            except Exception:
                continue
            if p.type == "FLOAT" and getattr(p, "array_length", 0):
                continue
            if isinstance(v, (int, float, bool, str)):
                out[p.identifier] = round(v, 4) if isinstance(v, float) else v
    return out

def key_frames(o):
    ad = o.animation_data
    if not ad or not ad.action:
        return []
    act, fcs = ad.action, []
    if hasattr(act, "fcurves"):
        fcs = list(act.fcurves)
    else:
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    fcs += list(cb.fcurves)
    return sorted({round(k.co[0]) for f in fcs for k in f.keyframe_points})

objs = []
for o in bpy.data.objects:
    d = {"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.location],
         "rot": [round(v, 3) for v in o.rotation_euler], "scale": [round(v, 3) for v in o.scale],
         "dims": [round(v, 3) for v in o.dimensions], "parent": o.parent.name if o.parent else None,
         "mods": [m.type for m in getattr(o, "modifiers", [])],
         "modifiers": [m.type for m in o.modifiers],
         "materials": [s.material.name for s in o.material_slots if s.material],
         "collections": [c.name for c in o.users_collection]}
    d["constraints"] = [c.type for c in o.constraints]
    if o.type in ("MESH", "CURVE", "FONT"):  # world-space bounding box (read by pack/scene_tools.py)
        cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
        d["bbox"] = [[round(min(c[i] for c in cs), 3) for i in range(3)], [round(max(c[i] for c in cs), 3) for i in range(3)]]
    d["mod_props"] = [dict(props(m), type=m.type) for m in o.modifiers]
    d["hide_render"] = o.hide_render
    d["empty_type"] = o.empty_display_type if o.type == "EMPTY" else None
    d["key_frames"] = key_frames(o)
    if o.type == "MESH":
        me = o.data
        d["shape_keys"] = len(me.shape_keys.key_blocks) if me.shape_keys else 0
        d["smooth"] = sum(1 for p in me.polygons if p.use_smooth)
        d.update(verts=len(me.vertices), faces=len(me.polygons), uv=len(me.uv_layers))
    if o.type == "LIGHT":
        d["light"] = o.data.type
        d["data_props"] = props(o.data)
    if o.type == "CAMERA":
        d["data_props"] = props(o.data)
    if o.type == "FONT":
        d["text"] = o.data.body
        d["data_props"] = props(o.data)
    if o.type == "CURVE":
        d["splines"] = len(o.data.splines)
        d["data_props"] = props(o.data)
    objs.append(d)
result["objects"] = objs
result["num_materials"] = len(bpy.data.materials)
result["materials"] = [dict(props(m), name=m.name, color=[round(v, 3) for v in m.diffuse_color]) for m in bpy.data.materials]
result["collections"] = [c.name for c in bpy.data.collections]
sc = bpy.context.scene
result["frame_start"] = sc.frame_start
result["fps"] = sc.render.fps
result["res"] = [sc.render.resolution_x, sc.render.resolution_y]
result["engine"] = sc.render.engine
result["world"] = sc.world.name if sc.world else None
result["markers"] = [m.frame for m in sc.timeline_markers]
result["res_percent"] = sc.render.resolution_percentage
result["file_format"] = sc.render.image_settings.file_format
result["samples"] = sc.cycles.samples if sc.render.engine == "CYCLES" else None
result["data_animated"] = sum(1 for coll in (bpy.data.lights, bpy.data.materials, bpy.data.cameras, bpy.data.worlds)
                              for b in coll if b.animation_data and b.animation_data.action)
result["node_groups"] = len(bpy.data.node_groups)
result["camera"] = bpy.context.scene.camera.name if bpy.context.scene.camera else None
result["frame_end"] = bpy.context.scene.frame_end
result["animated"] = sum(1 for o in bpy.data.objects if o.animation_data and o.animation_data.action)
result["blender"] = bpy.app.version_string
json.dump(result, open(out_path, "w"))
