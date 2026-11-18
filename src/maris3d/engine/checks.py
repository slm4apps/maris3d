# SPDX-License-Identifier: Apache-2.0
"""Scene checks. A check spec is a dict; every key present must hold. Returns list of failed reasons."""

def _m(objs, **kw):
    out = []
    for o in objs:
        if "type" in kw and o["type"] != kw["type"]:
            continue
        if "modifier" in kw and kw["modifier"] not in o["modifiers"]:
            continue
        if "light" in kw and o.get("light") != kw["light"]:
            continue
        if "material" in kw and not o["materials"]:
            continue
        out.append(o)
    return out

def check(scene, spec):
    fails = []
    if not scene["executed"]:
        return ["script did not execute"]
    objs = scene["objects"]
    meshes = _m(objs, type="MESH")
    if "meshes" in spec:
        lo, hi = spec["meshes"]
        if not lo <= len(meshes) <= hi:
            fails.append(f"mesh count {len(meshes)} not in [{lo},{hi}]")
    if "objects_min" in spec and len(objs) < spec["objects_min"]:
        fails.append(f"objects {len(objs)} < {spec['objects_min']}")
    if "verts_min" in spec and sum(o["verts"] for o in meshes) < spec["verts_min"]:
        fails.append("too few vertices")
    if "verts_max" in spec and sum(o["verts"] for o in meshes) > spec["verts_max"]:
        fails.append("too many vertices")
    if "modifier" in spec and not _m(objs, modifier=spec["modifier"]):
        fails.append(f"no {spec['modifier']} modifier")
    if "light" in spec and not _m(objs, type="LIGHT", light=spec["light"]):
        fails.append(f"no {spec['light']} light")
    if "camera" in spec and not _m(objs, type="CAMERA"):
        fails.append("no camera object")
    if "curve" in spec and not _m(objs, type="CURVE"):
        fails.append("no curve object")
    if "material" in spec and len(_m(objs, type="MESH", material=True)) < spec["material"]:
        fails.append("too few meshes with a material")
    if "uv" in spec and not any(o.get("uv", 0) > 0 for o in meshes):
        fails.append("no UV map")
    if "animated" in spec and scene["animated"] < spec["animated"]:
        fails.append("no animation keyframes")
    if "frame_end" in spec and scene["frame_end"] != spec["frame_end"]:
        fails.append(f"frame_end {scene['frame_end']} != {spec['frame_end']}")
    if "parented" in spec and not any(o["parent"] for o in objs):
        fails.append("no parenting")
    if "collection" in spec and not any(spec["collection"] in o["collections"] for o in objs):
        fails.append(f"nothing in collection {spec['collection']}")
    if "name" in spec and not any(spec["name"].lower() in o["name"].lower() for o in objs):
        fails.append(f"no object named like {spec['name']}")
    if "bbox_x" in spec:  # (min, max) of the largest mesh's X extent, or of all meshes combined
        xs = [o["dims"][0] for o in meshes] or [0]
        if not spec["bbox_x"][0] <= max(xs) <= spec["bbox_x"][1]:
            fails.append(f"x extent {max(xs)} outside {spec['bbox_x']}")
    if "bbox_z" in spec:
        zs = [o["loc"][2] + o["dims"][2] / 2 for o in meshes] or [0]
        if not spec["bbox_z"][0] <= max(zs) <= spec["bbox_z"][1]:
            fails.append(f"top z {max(zs)} outside {spec['bbox_z']}")
    if "loc_near" in spec:
        tx, ty, tz = spec["loc_near"]
        if not any(abs(o["loc"][0] - tx) < .05 and abs(o["loc"][1] - ty) < .05 and abs(o["loc"][2] - tz) < .05 for o in objs):
            fails.append(f"nothing at {spec['loc_near']}")
    if "scale_near" in spec:
        if not any(all(abs(a - b) < .05 for a, b in zip(o["scale"], spec["scale_near"])) or
                   all(abs(a - b) < .05 for a, b in zip(o["dims"], spec["scale_near"])) for o in meshes):
            fails.append(f"no mesh with scale/dims {spec['scale_near']}")

    # ---- keys added for prompts b042+ (the keys above are unchanged)
    def same(a, b):
        return abs(a - b) < .02 + .01 * abs(b) if isinstance(b, float) and not isinstance(b, bool) else a == b
    if "faces" in spec and not spec["faces"][0] <= sum(o["faces"] for o in meshes) <= spec["faces"][1]:
        fails.append(f"faces {sum(o['faces'] for o in meshes)} not in {spec['faces']}")
    if "type_count" in spec:  # {"EMPTY": (1, 1), "LIGHT": (2, 3)}
        for t, (lo, hi) in spec["type_count"].items():
            n = len(_m(objs, type=t))
            if not lo <= n <= hi:
                fails.append(f"{t} count {n} not in [{lo},{hi}]")
    if "mod_prop" in spec:  # (modifier type, property, value)
        t, k, v = spec["mod_prop"]
        if not any(m["type"] == t and k in m and same(m[k], v) for o in objs for m in o["mod_props"]):
            fails.append(f"no {t} modifier with {k}={v}")
    if "mod_count" in spec:  # (modifier type, min count over all objects)
        t, n = spec["mod_count"]
        if sum(1 for o in objs for m in o["mod_props"] if m["type"] == t) < n:
            fails.append(f"fewer than {n} {t} modifiers")
    if "data_prop" in spec:  # (object type, property, value) on light/camera/curve/text data
        t, k, v = spec["data_prop"]
        if not any(o["type"] == t and k in o.get("data_props", {}) and same(o["data_props"][k], v) for o in objs):
            fails.append(f"no {t} with {k}={v}")
    if "mat_prop" in spec:  # (property, value) on any material
        k, v = spec["mat_prop"]
        if not any(k in m and same(m[k], v) for m in scene["materials"]):
            fails.append(f"no material with {k}={v}")
    if "mat_color" in spec:  # rgb within 0.15 on any material's viewport colour
        c = spec["mat_color"]
        if not any(all(abs(a - b) < .15 for a, b in zip(m["color"], c)) for m in scene["materials"]):
            fails.append(f"no material with colour near {c}")
    if "mat_name" in spec and not any(spec["mat_name"].lower() in m["name"].lower() for m in scene["materials"]):
        fails.append(f"no material named like {spec['mat_name']}")
    if "constraint" in spec and not any(spec["constraint"] in o["constraints"] for o in objs):
        fails.append(f"no {spec['constraint']} constraint")
    if "frame_start" in spec and scene["frame_start"] != spec["frame_start"]:
        fails.append(f"frame_start {scene['frame_start']} != {spec['frame_start']}")
    if "fps" in spec and scene["fps"] != spec["fps"]:
        fails.append(f"fps {scene['fps']} != {spec['fps']}")
    if "res" in spec and list(scene["res"]) != list(spec["res"]):
        fails.append(f"resolution {scene['res']} != {spec['res']}")
    if "keyed" in spec:  # these frames all carry a keyframe on some object
        have = {f for o in objs for f in o["key_frames"]}
        if not set(spec["keyed"]) <= have:
            fails.append(f"missing keyframes {sorted(set(spec['keyed']) - have)}")
    if "text" in spec and not any(spec["text"] == o.get("text") for o in objs):
        fails.append(f"no text object with body {spec['text']!r}")
    if "shape_keys" in spec and not any(o.get("shape_keys", 0) >= spec["shape_keys"] for o in meshes):
        fails.append("too few shape keys")
    if "smooth" in spec and not any(o.get("smooth", 0) > 0 for o in meshes):
        fails.append("no smooth-shaded faces")
    if "collections_min" in spec and len(scene["collections"]) < spec["collections_min"]:
        fails.append(f"fewer than {spec['collections_min']} collections")
    if "dim" in spec:  # (axis 0-2, lo, hi): some mesh has that dimension in range
        a, lo, hi = spec["dim"]
        if not any(lo <= o["dims"][a] <= hi for o in meshes):
            fails.append(f"no mesh with dim[{a}] in [{lo},{hi}]")
    if "parent_of" in spec:  # (child name part, parent name part)
        c, p = spec["parent_of"]
        if not any(c.lower() in o["name"].lower() and o["parent"] and p.lower() in o["parent"].lower() for o in objs):
            fails.append(f"{c} is not parented to {p}")
    if "obj_at" in spec:  # (name part, (x, y, z))
        n, (tx, ty, tz) = spec["obj_at"]
        if not any(n.lower() in o["name"].lower() and abs(o["loc"][0] - tx) < .05 and abs(o["loc"][1] - ty) < .05 and abs(o["loc"][2] - tz) < .05 for o in objs):
            fails.append(f"{n} not at {(tx, ty, tz)}")
    if "rot_near" in spec:  # radians, any object
        if not any(all(abs(a - b) < .03 for a, b in zip(o["rot"], spec["rot_near"])) for o in objs):
            fails.append(f"nothing rotated {spec['rot_near']}")
    if "no_render_hidden" in spec and any(o["hide_render"] for o in objs):
        fails.append("an object is hidden from render")
    if "hide_render" in spec and not any(o["hide_render"] for o in objs):
        fails.append("no object hidden from render")
    if "node_groups" in spec and scene["node_groups"] < spec["node_groups"]:
        fails.append("no node group")
    if "world" in spec and not scene["world"]:
        fails.append("no world")
    if "engine" in spec and scene["engine"] != spec["engine"]:
        fails.append(f"engine {scene['engine']} != {spec['engine']}")
    if "samples" in spec and scene["samples"] != spec["samples"]:
        fails.append(f"samples {scene['samples']} != {spec['samples']}")
    if "res_percent" in spec and scene["res_percent"] != spec["res_percent"]:
        fails.append(f"resolution percentage {scene['res_percent']} != {spec['res_percent']}")
    if "file_format" in spec and scene["file_format"] != spec["file_format"]:
        fails.append(f"file format {scene['file_format']} != {spec['file_format']}")
    if "markers" in spec and not set(spec["markers"]) <= set(scene["markers"]):
        fails.append(f"markers {scene['markers']} miss {spec['markers']}")
    if "data_animated" in spec and scene["data_animated"] < spec["data_animated"]:
        fails.append("no animated light/material/camera data")
    return fails
