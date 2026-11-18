# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Maris, the Maris3D mascot: a small low-poly girl who weaves a gold thread into a little toy train.

Run headless:  blender -b --factory-startup -P assets/maris/build_maris.py -- OUT_DIR [--render]

Writes OUT_DIR/maris.blend (rigged, one action per pose, kept with a fake user) and
OUT_DIR/maris.glb (meshes + armature + all actions; the thread is left out, the web draws it).
With --render it also writes OUT_DIR/pose-<name>.png, one still per pose (Cycles, CPU).

The character faces -Y (towards a camera
placed on -Y), stands on z = 0 and is about 1 unit tall; the add-on scales it to the scene.
"""
import json
import math
import os
import shutil
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else "maris-out")
RENDER = "--render" in ARGS

# Everything the add-on and the web pages rely on (version, poses, faces, outfits, colours) lives
# in maris.json next to this file; this script only adds the geometry and the animation curves.
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(HERE, "maris.json")
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))   # the repo's code: one colour language
from maris3d.copilot import show  # noqa: E402
with open(SPEC_PATH, encoding="utf-8") as fh:
    SPEC = json.load(fh)
POSES = tuple(SPEC["poses"])
STILL = dict(SPEC["poses"])
FACES = SPEC["faces"]
OUTFITS = SPEC["outfits"]
SKINS = SPEC["skins"]
MOUTHS = {"Smile": ((-0.04, 0.742), (0.0, 0.722), (0.04, 0.742)),
          "Frown": ((-0.035, 0.722), (0.0, 0.738), (0.035, 0.722))}


def material(name, outfit=None):
    """The material for a colour slot. outfit is an outfit name, or for slot "skin" a skin name;
    colours come from maris.json as colour answers, made into materials by the same code the
    planner and edit model use (copilot/colours.py via copilot/show.py)."""
    if name == "skin":
        key, m = show.maris_material(SPEC, name, skin=outfit or SPEC["default_skin"])
    elif name in ("hair", "brow"):
        key, m = show.maris_material(SPEC, name, hair=outfit or SPEC["default_hair"])
    else:
        key, m = show.maris_material(SPEC, name, outfit=outfit)
    return make_material(key, m)


def make_material(key, m):
    """A Principled material from a colours.material() dict (the add-on has the same code)."""
    mat = bpy.data.materials.get(key)
    if mat:
        return mat
    mat = bpy.data.materials.new(key)
    mat.use_fake_user = True                   # kept in the .blend even while not worn
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    rgba = (*m["color"][:3], 1.0)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = m.get("roughness", 0.6)
    bsdf.inputs["Metallic"].default_value = m.get("metallic", 0.0)
    if m.get("emission_strength"):
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = m["emission_strength"]
    if m.get("alpha", 1.0) < 1.0:
        bsdf.inputs["Alpha"].default_value = m["alpha"]
    mat.diffuse_color = rgba                   # the viewport colour in solid mode
    return mat


def finish(ob, name, mat, smooth=False):
    ob.name = ob.data.name = "Maris_" + name
    ob.data.materials.append(material(mat))
    ob["maris_slot"] = mat                      # the colour slot an outfit may recolour
    for poly in getattr(ob.data, "polygons", ()):
        poly.use_smooth = smooth
    return ob


def add(kind, name, mat, location, **kw):
    scale = kw.pop("scale", None)
    rotation = kw.pop("rotation", None)
    op = {"cone": bpy.ops.mesh.primitive_cone_add, "cyl": bpy.ops.mesh.primitive_cylinder_add,
          "ico": bpy.ops.mesh.primitive_ico_sphere_add, "uv": bpy.ops.mesh.primitive_uv_sphere_add,
          "cube": bpy.ops.mesh.primitive_cube_add, "torus": bpy.ops.mesh.primitive_torus_add}[kind]
    op(location=location, **kw)
    ob = bpy.context.active_object
    if scale:
        ob.scale = scale
    if rotation:
        ob.rotation_euler = [math.radians(a) for a in rotation]
    return finish(ob, name, mat)


def smooth(ob):
    """Smooth shading for the face; the rest stays low-poly."""
    for poly in ob.data.polygons:
        poly.use_smooth = True


def build_body():
    parts = {}
    parts["dress"] = add("cone", "Dress", "dress", (0, 0, 0.26), vertices=8, radius1=0.27,
                         radius2=0.11, depth=0.52)
    parts["bodice"] = add("cyl", "Bodice", "bodice", (0, 0, 0.58), vertices=8, radius=0.115,
                          depth=0.14)
    parts["head"] = add("ico", "Head", "skin", (0, 0, 0.79), subdivisions=4, radius=0.16)
    smooth(parts["head"])
    parts["hair"] = add("ico", "Hair", "hair", (0, 0.012, 0.826), subdivisions=2, radius=0.181,
                        scale=(1.02, 0.95, 0.98))
    parts["band"] = add("torus", "Band", "band", (0, 0.0, 0.86), major_radius=0.158,
                        minor_radius=0.012, major_segments=16, minor_segments=4)
    for i, z in enumerate((0.72, 0.64, 0.565, 0.495)):
        parts[f"braid{i}"] = add("ico", f"Braid{i}", "hair", (0, 0.165 + 0.01 * i, z),
                                 subdivisions=1, radius=0.045 - 0.004 * i)
    for side, x in (("L", 0.056), ("R", -0.056)):
        parts["eye" + side] = add("uv", "Eye" + side, "eye", (x, -0.146, 0.795), segments=8,
                                  ring_count=6, radius=0.022)
        parts["cheek" + side] = add("uv", "Cheek" + side, "cheek", (x * 1.6, -0.128, 0.75),
                                    segments=8, ring_count=6, radius=0.022,
                                    scale=(1.0, 0.5, 0.8))
    for side, x in (("L", 0.056), ("R", -0.056)):
        parts["brow" + side] = add("cube", "Brow" + side, "brow", (x, -0.160, 0.827), size=1.0,
                                   scale=(0.040, 0.008, 0.010))
    for name, pts in MOUTHS.items():
        parts["mouth" + name] = arc_mesh("Mouth" + name, pts)
    parts["mouthO"] = add("torus", "MouthO", "eye", (0, -0.157, 0.73), major_radius=0.016,
                          minor_radius=0.005, major_segments=10, minor_segments=4, rotation=(90, 0, 0))
    parts["mouthWide"] = add("uv", "MouthWide", "eye", (0, -0.152, 0.73), segments=10, ring_count=6,
                             radius=0.03, scale=(1.0, 0.35, 0.6))
    for side, x in (("L", 1), ("R", -1)):
        parts["arm" + side] = add("cyl", "Arm" + side, "bodice", (0.165 * x, 0, 0.49), vertices=6,
                                  radius=0.032, depth=0.24, rotation=(0, -14 * x, 0))
        parts["hand" + side] = add("ico", "Hand" + side, "skin", (0.196 * x, 0, 0.372),
                                   subdivisions=1, radius=0.04)
    parts["spindle"] = add("cyl", "Spindle", "wood", (-0.205, -0.02, 0.36), vertices=6,
                           radius=0.009, depth=0.24)
    parts["whorl"] = add("cyl", "Whorl", "wood", (-0.205, -0.02, 0.29), vertices=10, radius=0.04,
                         depth=0.016)
    for name in TOYS:
        parts["toy_" + name] = woven_toy(name)
    return parts


TOY_AT, TOY_TURN = (0.0, -0.37, 0.0), 20.0


def toy_point(x, y, z):
    """A point given in the toy's own frame (metres; x along the train, z up), in maris space."""
    a = math.radians(TOY_TURN)
    return (TOY_AT[0] + x * math.cos(a) - y * math.sin(a), TOY_AT[1] + x * math.sin(a) + y * math.cos(a),
            TOY_AT[2] + z)


def _circle(c, r, plane, a0=0, a1=360, n=14):
    """Points of a circle (or arc, degrees) around centre c in the plane "xz", "yz" or "xy"."""
    out = []
    for i in range(n + 1):
        t = math.radians(a0 + (a1 - a0) * i / n)
        u, v = r * math.cos(t), r * math.sin(t)
        out.append({"xz": (c[0] + u, c[1], c[2] + v), "yz": (c[0], c[1] + u, c[2] + v),
                    "xy": (c[0] + u, c[1] + v, c[2])}[plane])
    return out


def _box(x0, x1, y0, y1, z0, z1):
    """The 12 edges of a box as lines."""
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return [[c[i], c[j]] for i, j in ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7),
                                      (0, 4), (1, 5), (2, 6), (3, 7))]


def _half(p, q):
    return [p, tuple((a + b) / 2 for a, b in zip(p, q))]


# The toys she weaves (a woven cube read as "just a box", so each is a small unfinished toy: 3 Christmas-themed and 3 everyday ones, picked at random or by mode). Each is gold thread, NOT finished: the last line
# of each list is the one she is weaving and the thread runs into its end. Units: metres in the
# toy's own frame (x along it, y away from the viewer, z up); maris.json "toys" names them.
def toy_train():
    wr, wz, bz, br = 0.024, 0.024, 0.075, 0.03
    lines = [[(-0.09, -0.04, 0.035), (0.09, -0.04, 0.035), (0.09, 0.04, 0.035), (-0.09, 0.04, 0.035),
              (-0.09, -0.04, 0.035)]]
    lines += [[(x, y, 0.035), (x, y, 0.14)] for x in (-0.09, -0.025) for y in (-0.04, 0.04)]
    lines += [[(-0.10, -0.045, 0.14), (-0.015, -0.045, 0.14), (-0.015, 0.045, 0.14),
               (-0.10, 0.045, 0.14), (-0.10, -0.045, 0.14)]]
    lines += [_circle((-0.025, 0, bz), br, "yz")]
    lines += [[(-0.025, br * math.cos(math.radians(a)), bz + br * math.sin(math.radians(a))),
               (0.085, br * math.cos(math.radians(a)), bz + br * math.sin(math.radians(a)))]
              for a in (0, 90, 180)]
    lines += [_circle((x, 0.045, wz), wr, "xz") for x in (-0.06, 0.0, 0.06)]
    lines += [_circle((x, -0.045, wz), wr, "xz") for x in (-0.06, 0.0)]
    lines += [_circle((0.06, -0.045, wz), wr, "xz", -90, 150, 10)]   # the wheel she is weaving
    return lines


def toy_sailboat():
    hull = lambda y: [(-0.09, y, 0.05), (0.09, y, 0.05), (0.06, y, 0.0), (-0.06, y, 0.0), (-0.09, y, 0.05)]
    lines = [hull(-0.03), hull(0.03)]
    lines += [[(x, -0.03, z), (x, 0.03, z)] for x, z in ((-0.09, 0.05), (0.09, 0.05), (0.06, 0.0), (-0.06, 0.0))]
    lines += [[(0.0, 0.0, 0.05), (0.0, 0.0, 0.23)]]                       # mast
    lines += [[(0.0, 0.0, 0.215), (0.0, 0.0, 0.07), (0.085, 0.0, 0.07)]]  # sail: luff and foot
    lines += [_half((0.085, 0.0, 0.07), (0.0, 0.0, 0.215))]                # the sail edge she is weaving
    return lines


def toy_teddy():
    lines = [_circle((0, 0, 0.065), 0.05, "xz"), _circle((0, 0, 0.065), 0.05, "yz"),     # body
             _circle((0, 0, 0.15), 0.038, "xz"), _circle((0, 0, 0.15), 0.038, "yz"),     # head
             _circle((-0.03, 0, 0.19), 0.014, "xz"), _circle((0.03, 0, 0.19), 0.014, "xz"),  # ears
             _circle((0, -0.036, 0.14), 0.014, "xz"),                                    # snout
             _circle((-0.03, -0.03, 0.018), 0.018, "xz"), _circle((0.03, -0.03, 0.018), 0.018, "xz"),
             _circle((-0.058, -0.005, 0.08), 0.017, "xz")]                               # left arm
    lines += [_circle((0.058, -0.005, 0.08), 0.017, "xz", -90, 160, 10)]  # the arm she is weaving
    return lines


def toy_tree():
    lines = [l for l in _box(-0.015, 0.015, -0.015, 0.015, 0.0, 0.03)]     # trunk
    tiers = ((0.03, 0.08, 0.075), (0.075, 0.062, 0.065), (0.12, 0.045, 0.06))
    for i, (z, r, h) in enumerate(tiers):
        lines.append(_circle((0, 0, z), r, "xy", n=16))
        spokes = (0, 90, 180, 270) if i < 2 else (0, 90, 180)
        for a in spokes:
            p = (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), z)
            lines.append([p, (0, 0, z + h)])
    r, z, h = tiers[2][1], tiers[2][0], tiers[2][2]
    lines.append(_half((0, -r, z), (0, 0, z + h)))                        # the branch she is weaving
    return lines                                                           # (the star comes last)


def toy_snowman():
    lines = [_circle((0, 0, 0.055), 0.055, "xz", n=18), _circle((0, 0, 0.055), 0.055, "xy", n=18),
             _circle((0, 0, 0.145), 0.04, "xz", n=16), _circle((0, 0, 0.145), 0.04, "xy", n=16),
             [(-0.035, 0, 0.155), (-0.085, 0, 0.19)], [(0.035, 0, 0.155), (0.085, 0, 0.19)]]  # arms
    lines += [_circle((0, 0, 0.21), 0.027, "xz", -90, 170, 12)]            # the head she is weaving
    return lines                                                           # (no hat yet)


def toy_gift():
    h, z1 = 0.055, 0.1
    lines = _box(-h, h, -h, h, 0.0, z1)
    lines += [[(0, -h, 0.0), (0, -h, z1), (0, h, z1), (0, h, 0.0)],          # ribbon one way
              [(-h, 0, 0.0), (-h, 0, z1), (h, 0, z1), (h, 0, 0.0)]]          # and the other
    lines += [_circle((-0.022, 0, z1 + 0.018), 0.022, "xz")]               # one bow loop done
    lines += [_circle((0.022, 0, z1 + 0.018), 0.022, "xz", 180, 400, 12)]  # the loop she is weaving
    return lines


TOYS = {"train": toy_train, "sailboat": toy_sailboat, "teddy": toy_teddy,
        "tree": toy_tree, "snowman": toy_snowman, "gift": toy_gift}
BUILD_TOY = "train"                            # the one shown in the .blend as saved


def woven_toy(name):
    """Gold tubes along a toy's lines (a curve made into a mesh, so the glb has it too)."""
    lines = TOYS[name]()
    curve = bpy.data.curves.new("Maris_Toy", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.0045
    curve.bevel_resolution = 1
    for line in lines:
        spline = curve.splines.new("POLY")
        spline.points.add(len(line) - 1)
        for pt, co in zip(spline.points, line):
            pt.co = (*toy_point(*co), 1.0)
    ob = bpy.data.objects.new("Maris_Toy", curve)
    bpy.context.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.active_object
    ob = finish(ob, "Toy" + name.capitalize(), "gold")
    ob["maris_toy"] = name
    ob["toy_thread_end"] = list(toy_point(*lines[-1][-1]))   # maris space, before rigging
    ob.hide_render = ob.hide_viewport = name != BUILD_TOY
    return ob


def set_toy(objects, name):
    """Show one toy and move the thread's end onto the line she is weaving (the add-on does the
    same at run time: by the maris_toy property and the stored thread_end_local)."""
    end = bpy.data.objects.get("Maris_ThreadEnd")
    for ob in objects:
        if "maris_toy" in ob:
            ob.hide_render = ob.hide_viewport = ob["maris_toy"] != name
            if ob["maris_toy"] == name and end is not None and "thread_end_local" in ob:
                end.location = ob["thread_end_local"]


def arc_mesh(name, pts):
    """A thin curved mouth line on the face front (x, z points), converted to a mesh for glb."""
    curve = bpy.data.curves.new("Maris_" + name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.006
    spline = curve.splines.new("NURBS")
    spline.points.add(len(pts) - 1)
    for p, (x, z) in zip(spline.points, pts):
        p.co = (x, -0.157 - 0.004 * (abs(x) < 0.01), z, 1.0)
    spline.order_u, spline.use_endpoint_u = 3, True
    ob = bpy.data.objects.new("Maris_" + name, curve)
    bpy.context.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.active_object
    ob.name = ob.data.name = "Maris_" + name
    ob.data.materials.clear()
    ob.data.materials.append(material("eye"))
    ob["maris_slot"] = "eye"
    return ob


def set_face(parts, name):
    """Show one of FACES: the add-on does the same at run time (by object name)."""
    face = FACES[name]
    for m in ("Smile", "Frown", "O", "Wide"):
        ob = parts["mouth" + m]
        ob.hide_render = ob.hide_viewport = (m != face["mouth"])
    for side, sign in (("L", 1), ("R", -1)):
        brow = parts["brow" + side]
        if "face_base" not in brow:
            # Brows are parented to the head bone, so their location is in bone space: store the
            # rest transform and the world up / front axes in that space once (the add-on reads
            # the same custom properties at run time).
            bpy.context.view_layer.update()
            brow.rotation_mode = "QUATERNION"
            to_world = (brow.matrix_world @ brow.matrix_basis.inverted()).to_3x3().inverted()
            brow["face_base"] = list(brow.location) + list(brow.rotation_quaternion)
            brow["face_up"] = list((to_world @ Vector((0, 0, 1))).normalized())
            brow["face_front"] = list((to_world @ Vector((0, 1, 0))).normalized())
        base = list(brow["face_base"])
        brow.location = Vector(base[:3]) + Vector(brow["face_up"]) * face["lift"]
        tilt = Quaternion(Vector(brow["face_front"]), math.radians(face["tilt"] * sign))
        brow.rotation_quaternion = tilt @ Quaternion(base[3:])


def build_outfits(parts):
    """Extra pieces per outfit (names listed in maris.json), hidden unless that outfit is worn.
    Returns {piece: bone} for attach()."""
    bones = {}

    def piece(outfit, name, bone, ob):
        ob["maris_outfit"] = outfit
        parts[name] = ob
        bones[name] = bone

    # winter: pointed red cap with a fur trim and pom-pom, fur hem on the dress
    piece("winter", "WinterCap", "head", add("cone", "WinterCap", "dress", (0, 0.02, 0.99),
          vertices=10, radius1=0.178, radius2=0.0, depth=0.25, rotation=(-12, 0, 0)))
    piece("winter", "WinterTrim", "head", add("torus", "WinterTrim", "fur", (0, 0.02, 0.87),
          major_radius=0.172, minor_radius=0.024, major_segments=16, minor_segments=5))
    piece("winter", "WinterPom", "head", add("ico", "WinterPom", "fur", (0, 0.075, 1.11),
          subdivisions=1, radius=0.038))
    piece("winter", "WinterHem", "root", add("torus", "WinterHem", "fur", (0, 0, 0.02),
          major_radius=0.262, minor_radius=0.026, major_segments=16, minor_segments=5))
    # conductor: peaked cap with a badge, three brass buttons on the coat
    piece("conductor", "ConductorCap", "head", add("cyl", "ConductorCap", "bodice", (0, 0.02, 0.915),
          vertices=12, radius=0.176, depth=0.11))
    piece("conductor", "ConductorTop", "head", add("cyl", "ConductorTop", "bodice", (0, 0.02, 0.985),
          vertices=12, radius=0.19, depth=0.03))
    piece("conductor", "ConductorVisor", "head", add("cube", "ConductorVisor", "eye",
          (0, -0.19, 0.868), size=1.0, scale=(0.2, 0.08, 0.01), rotation=(-14, 0, 0)))
    piece("conductor", "ConductorBadge", "head", add("cube", "ConductorBadge", "brass",
          (0, -0.16, 0.925), size=1.0, scale=(0.04, 0.01, 0.03)))
    for i, z in enumerate((0.625, 0.585, 0.545)):
        piece("conductor", f"ConductorButton{i}", "spine", add("ico", f"ConductorButton{i}",
              "brass", (0, -0.118, z), subdivisions=1, radius=0.012))
    for outfit in OUTFITS:                     # create every outfit material once
        for slot in OUTFITS[outfit]["colours"]:
            material(slot, outfit)
    return bones


def set_outfit(objects, name):
    """Wear one outfit: recolour slots, show its pieces, hide what it replaces. The add-on does
    the same at run time from maris.json (by object name and the maris_slot property)."""
    outfit = OUTFITS[name]
    for ob in objects:
        if ob.type != "MESH":
            continue
        slot = ob.get("maris_slot")
        if slot and slot not in ("skin", "hair", "brow") and ob.data.materials:
            ob.data.materials[0] = material(slot, name)
        base = ob.name[len(SPEC["prefix"]):]
        if "maris_outfit" in ob:
            show = ob["maris_outfit"] == name
        elif base in [h for o in OUTFITS.values() for h in o["hide"]]:
            show = base not in outfit["hide"]
        else:
            continue
        ob.hide_render = ob.hide_viewport = not show


def set_hair(objects, name):
    """Hair and brow colour from maris.json "hairs"."""
    for ob in objects:
        slot = ob.get("maris_slot")
        if ob.type == "MESH" and slot in ("hair", "brow") and ob.data.materials:
            ob.data.materials[0] = material(slot, name)


def set_skin(objects, name):
    """Skin tone for the head and hands (slot "skin"), from maris.json "skins"."""
    for ob in objects:
        if ob.type == "MESH" and ob.get("maris_slot") == "skin" and ob.data.materials:
            ob.data.materials[0] = material("skin", name)


def build_rig():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    arm = bpy.context.active_object
    arm.name = arm.data.name = "Maris_Rig"
    eb = arm.data.edit_bones
    root = eb[0]
    root.name, root.head, root.tail = "root", (0, 0, 0), (0, 0, 0.2)

    def bone(name, head, tail, parent):
        b = eb.new(name)
        b.head, b.tail, b.parent = head, tail, eb[parent]
        b.roll = 0.0
        return b

    bone("spine", (0, 0, 0.2), (0, 0, 0.66), "root")
    bone("head", (0, 0, 0.66), (0, 0, 0.98), "spine")
    bone("arm.L", (0.135, 0, 0.62), (0.2, 0, 0.36), "spine")
    bone("arm.R", (-0.135, 0, 0.62), (-0.2, 0, 0.36), "spine")
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    return arm


def attach(parts, arm, extra=()):
    where = {"root": ("dress",) + tuple(k for k in parts if k.startswith("toy_")), "spine": ("bodice",),
             "head": ("head", "hair", "band", "eyeL", "eyeR", "cheekL", "cheekR", "braid0",
                      "braid1", "braid2", "braid3", "browL", "browR", "mouthSmile",
                      "mouthFrown", "mouthO", "mouthWide"),
             "arm.L": ("armL", "handL"), "arm.R": ("armR", "handR", "spindle", "whorl")}
    where = {b: list(n) for b, n in where.items()}
    for name, bone in dict(extra).items():
        where[bone].append(name)
    bpy.context.view_layer.update()
    for bone, names in where.items():
        for n in names:
            ob = parts[n]
            world = ob.matrix_world.copy()
            ob.parent = arm
            ob.parent_type = "BONE"
            ob.parent_bone = bone
            bpy.context.view_layer.update()
            ob.matrix_world = world


def build_thread(parts, arm):
    """A gold NURBS thread from the spindle tip to the toy, hooked to both so it follows."""
    tip = bpy.data.objects.new("Maris_ThreadTip", None)
    end = bpy.data.objects.new("Maris_ThreadEnd", None)
    for e in (tip, end):
        bpy.context.collection.objects.link(e)
        e.empty_display_size = 0.02
    tip.location = (-0.205, -0.02, 0.24)
    end_at = tuple(bpy.data.objects["Maris_Toy" + BUILD_TOY.capitalize()]["toy_thread_end"])
    end.location = end_at
    bpy.context.view_layer.update()
    for e, bone in ((tip, "arm.R"), (end, "root")):
        world = e.matrix_world.copy()
        e.parent, e.parent_type, e.parent_bone = arm, "BONE", bone
        bpy.context.view_layer.update()
        e.matrix_world = world
    curve = bpy.data.curves.new("Maris_Thread", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.0065                 # thick enough to read at thumbnail size
    curve.bevel_resolution = 1
    spline = curve.splines.new("NURBS")
    spline.points.add(2)
    pts = ((-0.205, -0.02, 0.24), (-0.10, -0.26, 0.10), end_at)
    for p, co in zip(spline.points, pts):
        p.co = (*co, 1.0)
    spline.order_u = 3
    spline.use_endpoint_u = True
    ob = bpy.data.objects.new("Maris_Thread", curve)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material("gold"))
    bpy.context.view_layer.update()
    for e, idx in ((tip, 0), (end, 2)):
        hook = ob.modifiers.new("hook_" + e.name, "HOOK")
        hook.object = e
        hook.vertex_indices_set([idx])
        hook.matrix_inverse = e.matrix_world.inverted()
    # each toy keeps where the thread's end goes, in the end marker's own (bone) space
    for toy in [o for o in bpy.data.objects if "maris_toy" in o]:
        end.matrix_world = Matrix.Translation(Vector(toy["toy_thread_end"]))
        bpy.context.view_layer.update()
        toy["thread_end_local"] = list(end.location)
    end.matrix_world = Matrix.Translation(Vector(end_at))
    bpy.context.view_layer.update()
    return ob


def key(arm, frame, poses):
    """poses: {bone: dict(rot=(x, y, z) degrees, loc=(x, y, z), scale=(x, y, z))}, all in bone
    space: for the upright bones local Y is up, so a hop is loc=(0, h, 0)."""
    for name, p in poses.items():
        pb = arm.pose.bones[name]
        if "rot" in p:
            pb.rotation_euler = [math.radians(a) for a in p["rot"]]
            pb.keyframe_insert("rotation_euler", frame=frame)
        if "loc" in p:
            pb.location = p["loc"]
            pb.keyframe_insert("location", frame=frame)
        if "scale" in p:
            pb.scale = p["scale"]
            pb.keyframe_insert("scale", frame=frame)


REST = {"root": dict(rot=(0, 0, 0), loc=(0, 0, 0), scale=(1, 1, 1)),
        "spine": dict(rot=(0, 0, 0), scale=(1, 1, 1)), "head": dict(rot=(0, 0, 0)),
        "arm.L": dict(rot=(0, 0, 0)), "arm.R": dict(rot=(0, 0, 0))}


def merged(*layers):
    out = {k: dict(v) for k, v in REST.items()}
    for layer in layers:
        for bone, vals in layer.items():
            out[bone].update(vals)
    return out


# Each pose: list of (frame, overrides). Bone axes (checked on the preview renders): upright bones
# (root, spine, head) nod forward with +X, turn with Y, tilt sideways with Z; the down-pointing arm
# bones swing forward with -X and lift sideways with Z (arm.L negative, arm.R positive).
UP_R = {"arm.R": dict(rot=(0, 0, 150))}
SEQUENCES = {
    "idle": [(1, {}), (24, {"spine": dict(scale=(1, 1.025, 1)), "head": dict(rot=(0, 6, 0))}),
             (48, {})],
    "rise": [(1, {"root": dict(loc=(0, -0.9, 0), scale=(0.6, 0.6, 0.6))}),
             (16, {"root": dict(loc=(0, 0.08, 0), scale=(1.05, 1.05, 1.05))}),
             (24, {})],
    "wave": [(1, {}), (8, UP_R),
             (14, {"arm.R": dict(rot=(0, 0, 125))}), (20, UP_R),
             (26, {"arm.R": dict(rot=(0, 0, 125))}), (32, UP_R), (40, {})],
    "weave": [(1, {"arm.R": dict(rot=(-35, 0, -15))}), (7, {"arm.R": dict(rot=(-45, 0, 5))}),
              (13, {"arm.R": dict(rot=(-35, 0, 20))}), (19, {"arm.R": dict(rot=(-25, 0, 0))}),
              (25, {"arm.R": dict(rot=(-35, 0, -15))})],
    "point": [(1, {}), (8, {"arm.R": dict(rot=(-85, 0, 0)), "head": dict(rot=(0, -10, 0))}),
              (30, {"arm.R": dict(rot=(-85, 0, 0)), "head": dict(rot=(0, -10, 0))})],
    "thumbs_up": [(1, {}), (8, {"arm.R": dict(rot=(-120, 0, 20)), "head": dict(rot=(-8, 0, 0))}),
                  (30, {"arm.R": dict(rot=(-120, 0, 20)), "head": dict(rot=(-8, 0, 0))})],
    "hop": [(1, {}), (4, {"root": dict(scale=(1.08, 0.9, 1.08))}),
            (10, {"root": dict(loc=(0, 0.18, 0), scale=(0.95, 1.08, 0.95))}),
            (16, {"root": dict(scale=(1.06, 0.92, 1.06))}), (20, {})],
    "shrug": [(1, {}), (8, {"arm.L": dict(rot=(0, 0, -40)), "arm.R": dict(rot=(0, 0, 40)),
                            "head": dict(rot=(0, 0, 14))}),
              (20, {"arm.L": dict(rot=(0, 0, -40)), "arm.R": dict(rot=(0, 0, 40)),
                    "head": dict(rot=(0, 0, 14))}), (28, {})],
    "sit": [(1, {}), (12, {"root": dict(loc=(0, -0.13, 0)), "spine": dict(rot=(-10, 0, 0)),
                           "arm.L": dict(rot=(-30, 0, 10)), "arm.R": dict(rot=(-30, 0, -10))})],
    "sad": [(1, {}), (12, {"head": dict(rot=(22, 0, 0)), "spine": dict(rot=(8, 0, 0)),
                           "arm.L": dict(rot=(0, 0, 6)), "arm.R": dict(rot=(0, 0, -6))})],
    "dance": [(1, {}),
              (12, {"root": dict(rot=(0, 90, 0), loc=(0, 0.1, 0)), "arm.L": dict(rot=(0, 0, -150))}),
              (24, {"root": dict(rot=(0, 180, 0)), "arm.R": dict(rot=(0, 0, 150))}),
              (36, {"root": dict(rot=(0, 270, 0), loc=(0, 0.1, 0)), "arm.L": dict(rot=(0, 0, -150))}),
              (48, {"root": dict(rot=(0, 360, 0))})],
    "inspect": [(1, {}), (10, {"spine": dict(rot=(16, 0, 0)), "head": dict(rot=(10, 0, 12)),
                               "arm.L": dict(rot=(-70, 0, 0))}),
                (30, {"spine": dict(rot=(16, 0, 0)), "head": dict(rot=(10, 0, -8)),
                      "arm.L": dict(rot=(-70, 0, 0))}), (38, {})],
}


def build_actions(arm):
    arm.animation_data_create()
    actions = {}
    for name in POSES:
        arm.animation_data.action = None
        for frame, over in SEQUENCES[name]:
            key(arm, frame, merged(over))
        act = arm.animation_data.action
        act.name = "maris_" + name
        act.use_fake_user = True
        actions[name] = act
    arm.animation_data.action = actions["idle"]
    return actions


def stage():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("MarisWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.11, 0.16, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    scene.world = world
    bpy.ops.mesh.primitive_circle_add(vertices=32, radius=1.2, fill_type="NGON", location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Stage_Floor"
    mat = bpy.data.materials.new("stage_floor")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.2, 0.26, 1)
    floor.data.materials.append(mat)
    bpy.ops.object.light_add(type="AREA", location=(-1.2, -1.6, 2.2))
    key_light = bpy.context.active_object
    key_light.data.energy = 220
    key_light.data.size = 1.5
    key_light.rotation_euler = (math.radians(50), 0, math.radians(-35))
    bpy.ops.object.light_add(type="POINT", location=(1.2, 0.8, 1.4))
    bpy.context.active_object.data.energy = 60
    bpy.ops.object.camera_add(location=(0.55, -2.1, 0.95))
    cam = bpy.context.active_object
    direction = Vector((0, 0, 0.5)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 50
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.render.resolution_x = scene.render.resolution_y = 520
    scene.render.film_transparent = False
    return [floor, key_light, cam]


def main():
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    parts = build_body()
    extra = build_outfits(parts)
    arm = build_rig()
    attach(parts, arm, extra)
    build_thread(parts, arm)
    actions = build_actions(arm)
    arm["maris_spec_version"] = SPEC["version"]
    arm["maris_faces"] = json.dumps(FACES)
    set_face(parts, "happy")
    coll = bpy.data.collections.new("Maris3D_Maris")
    bpy.context.scene.collection.children.link(coll)
    for ob in list(bpy.context.scene.collection.objects):
        if ob.name.startswith("Maris_"):
            bpy.context.scene.collection.objects.unlink(ob)
            coll.objects.link(ob)
    for skin in SKINS:
        material("skin", skin)
    set_outfit(coll.objects, SPEC["default_outfit"])
    set_skin(coll.objects, SPEC["default_skin"])
    for hair in SPEC["hairs"]:
        material("hair", hair), material("brow", hair)
    set_hair(coll.objects, SPEC["default_hair"])
    arm["maris_outfit"] = SPEC["default_outfit"]
    arm["maris_skin"] = SPEC["default_skin"]
    faces = sum(len(o.data.polygons) for o in coll.objects if o.type == "MESH")
    print(f"MARIS parts {len(parts)} faces {faces} actions {len(actions)}", flush=True)
    # A whole-file save keeps the folder it was saved to and the Save As dialog's last folder (a
    # home directory with the user name). Write only Maris's data blocks instead (the
    # collection with its objects, every action and material; no window or UI state), from a
    # neutral folder, then move it. scripts/scan_private.py checks the shipped file.
    neutral = "/tmp/maris3d-maris/maris.blend"
    os.makedirs(os.path.dirname(neutral), exist_ok=True)
    blocks = {coll} | set(bpy.data.actions) | {m for m in bpy.data.materials if m.name.startswith("maris_")}
    bpy.data.libraries.write(neutral, blocks, fake_user=True, compress=True)
    shutil.move(neutral, os.path.join(OUT, "maris.blend"))

    with open(os.path.join(OUT, "maris.json"), "w", encoding="utf-8") as fh:
        json.dump(SPEC, fh, indent=2)

    # glb: every mesh (all mouths and outfit pieces; the page shows them by name from
    # maris.json), the rig and every action; curves and empties are not exported
    hidden = [ob for ob in bpy.context.scene.objects if ob.hide_viewport]
    for ob in hidden:
        ob.hide_viewport = False
    bpy.context.view_layer.update()
    for ob in bpy.context.scene.objects:
        ob.select_set(ob.type in ("MESH", "ARMATURE"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "maris.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_animations=True,
                              export_animation_mode="ACTIONS")
    for ob in hidden:
        ob.hide_viewport = True

    if RENDER:
        stage()
        scene = bpy.context.scene
        for attr in dir(scene.render):         # no file path / date / host in the PNG metadata
            if attr.startswith("use_stamp"):
                setattr(scene.render, attr, False)
        for name in POSES:
            arm.animation_data.action = actions[name]
            scene.frame_set(STILL[name])
            scene.render.filepath = os.path.join(OUT, f"pose-{name}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS rendered {name}", flush=True)
        # outfits: idle pose, full body
        maris = bpy.data.collections["Maris3D_Maris"].objects
        arm.animation_data.action = actions["idle"]
        scene.frame_set(1)
        for name in OUTFITS:
            set_outfit(maris, name)
            scene.render.filepath = os.path.join(OUT, f"outfit-{name}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS outfit {name}", flush=True)
        set_outfit(maris, SPEC["default_outfit"])
        # face close-ups: idle pose, camera on the head
        arm.animation_data.action = actions["idle"]
        scene.frame_set(1)
        cam = scene.camera
        cam.location = (0.12, -0.75, 0.82)
        cam.rotation_euler = (Vector((0, 0, 0.78)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        for name in FACES:
            set_face(parts, name)
            scene.render.filepath = os.path.join(OUT, f"face-{name}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS face {name}", flush=True)
        set_face(parts, "happy")
        for skin in SKINS:
            set_skin(maris, skin)
            scene.render.filepath = os.path.join(OUT, f"skin-{skin}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS skin {skin}", flush=True)
        set_skin(maris, SPEC["default_skin"])
        for hair in SPEC["hairs"]:
            set_hair(maris, hair)
            scene.render.filepath = os.path.join(OUT, f"hair-{hair}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS hair {hair}", flush=True)
        set_hair(maris, SPEC["default_hair"])
        # toys: the whole Maris with her toy, camera low and close so the toy reads
        cam.location = (0.55, -1.25, 0.55)
        cam.rotation_euler = (Vector((0.02, -0.2, 0.3)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        for name in TOYS:
            set_toy(maris, name)
            scene.render.filepath = os.path.join(OUT, f"toy-{name}.png")
            bpy.ops.render.render(write_still=True)
            print(f"MARIS toy {name}", flush=True)
        set_toy(maris, BUILD_TOY)
    print("MARIS-DONE", flush=True)


main()
