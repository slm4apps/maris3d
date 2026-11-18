# SPDX-License-Identifier: GPL-3.0-or-later
"""Open every exported file of a demo folder once and say what is in it.

    blender -b --factory-startup --python demo/tools/check_files.py -- <demo folder>

For scene.blend, every .glb and every .fbx under the folder: load it into an empty scene and print
the number of objects and mesh objects. A file that does not load, or loads with no mesh, is
listed as FAIL and the last line is CHECK-FAIL; otherwise CHECK-OK.
"""
import os
import sys

import bpy

folder = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
paths = []
for base, _dirs, names in os.walk(folder):
    paths += [os.path.join(base, n) for n in sorted(names) if n.endswith((".blend", ".glb", ".fbx"))]

bad = []
for path in sorted(paths):
    rel = os.path.relpath(path, folder)
    try:
        if path.endswith(".blend"):
            bpy.ops.wm.open_mainfile(filepath=path)
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            if path.endswith(".glb"):
                bpy.ops.import_scene.gltf(filepath=path)
            else:
                bpy.ops.import_scene.fbx(filepath=path)
        meshes = sum(1 for o in bpy.data.objects if o.type == "MESH")
        print(f"FILE {'ok  ' if meshes else 'FAIL'} {rel}: {len(bpy.data.objects)} objects, {meshes} meshes", flush=True)
        if not meshes:
            bad.append(rel)
    except Exception as error:
        print(f"FILE FAIL {rel}: {str(error)[:200]}", flush=True)
        bad.append(rel)
print(f"CHECK-FAIL {len(bad)} of {len(paths)}: {bad[:5]}" if bad else f"CHECK-OK {len(paths)} files")
