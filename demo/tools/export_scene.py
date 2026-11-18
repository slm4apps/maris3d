# SPDX-License-Identifier: GPL-3.0-or-later
"""Export a built scene and each of its things as files other programs can open.

    blender -b <scene.blend> --python demo/tools/export_scene.py -- <out dir>

Writes into <out dir>:
    scene.blend                       the scene itself, saved again from a neutral folder
    scene.glb, scene.fbx              the whole scene
    objects/<Name>.glb, <Name>.fbx    one file per built thing (a parent with its parts), moved
                                      to the origin for the export and put back afterwards
    objects.json                      the list: name, number of parts, size in metres

A "thing" is a top-level object that has children (the copilot groups the parts of a chair, a
house, a train under one parent). Copies of a thing (House.01, House.02 ...) are in the scene
files and are not exported again one by one. Cameras and lights stay in the scene files only.

A .blend stores the path it was saved at, and an FBX stores the path of the .blend it came from:
exported where the scene was made, every file would carry the home folder and the user name of
that machine. So the scene is first saved again under a neutral folder (the system's temporary
folder), its output and image paths are emptied, and everything is exported from there.
"""
import json
import os
import re
import shutil
import sys
import tempfile

import bpy
from mathutils import Vector

out = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
os.makedirs(os.path.join(out, "objects"), exist_ok=True)


def family(root):
    todo, seen = [root], []
    while todo:
        o = todo.pop()
        seen.append(o)
        todo.extend(o.children)
    return seen


def select(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def write(path_no_ext, selection):
    bpy.ops.export_scene.gltf(filepath=path_no_ext + ".glb", export_format="GLB", use_selection=selection)
    bpy.ops.export_scene.fbx(filepath=path_no_ext + ".fbx", use_selection=selection)


def size_of(objs):
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        for corner in o.bound_box:
            p = o.matrix_world @ Vector(corner)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return [round(max(hi[i] - lo[i], 0.0), 3) for i in range(3)] if hi.x >= lo.x else [0, 0, 0]


# a neutral home for the scene: no path of this machine goes into the files
neutral = os.path.join("/tmp" if os.path.isdir("/tmp") else tempfile.gettempdir(), "maris3d-demo")
shutil.rmtree(neutral, ignore_errors=True)
os.makedirs(neutral)
for scene in bpy.data.scenes:
    scene.render.filepath = "//render"
for block in list(bpy.data.images) + list(bpy.data.texts) + list(bpy.data.movieclips) + list(bpy.data.sounds):
    if getattr(block, "filepath", ""):
        block.filepath = "//" + os.path.basename(block.filepath.replace("\\", "/"))
# only the scenes and what they use are written: the windows and file dialogs of the session that
# made the scene (they remember the last folder it saved to) stay behind
bpy.data.libraries.write(os.path.join(neutral, "scene.blend"), set(bpy.data.scenes), compress=True)
bpy.ops.wm.open_mainfile(filepath=os.path.join(neutral, "scene.blend"), load_ui=False)
shutil.copyfile(os.path.join(neutral, "scene.blend"), os.path.join(out, "scene.blend"))

write(os.path.join(out, "scene"), False)

listed = []
copy = re.compile(r"\.\d+$")
for root in sorted((o for o in bpy.data.objects if o.parent is None and o.children), key=lambda o: o.name):
    if copy.search(root.name):
        continue
    objs = family(root)
    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        continue
    was = root.location.copy()
    root.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    select(objs)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", root.name)
    write(os.path.join(out, "objects", name), True)
    listed.append({"name": root.name, "parts": len(meshes), "size_m": size_of(objs)})
    root.location = was
bpy.context.view_layer.update()
with open(os.path.join(out, "objects.json"), "w") as f:
    json.dump(listed, f, indent=1)
print(f"EXPORT-DONE {len(listed)} things -> {out}")
