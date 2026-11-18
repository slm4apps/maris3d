# SPDX-License-Identifier: Apache-2.0
"""Fixed JSON tool set for small models. The model emits {"calls":[{"tool":..., ...args}]}; compile_calls() turns it into a
bpy script (Blender 5.2 API only) that the same headless harness scores. Unknown/odd args are ignored, not fatal."""
import json, math

SHAPES = ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus", "plane", "monkey", "circle", "grid"]
VEC = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
S, N, I, B = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}
PTS = {"type": "array", "items": VEC, "minItems": 2, "maxItems": 80}

def _t(_tool, **props):
    return {"type": "object", "properties": {"tool": {"const": _tool}, **props}, "required": ["tool"] + [k for k in props if k in REQ.get(_tool, [])], "additionalProperties": False}
REQ = {"add_primitive": ["shape"], "add_light": ["kind"], "add_modifier": ["modifier"], "set_material": ["color"],
       "keyframe": ["property", "frame"], "parent": ["child", "parent"], "add_curve": ["kind"], "new_collection": ["name"],
       "add_text": ["body"], "add_constraint": ["constraint"], "add_shape_key": ["name"], "add_geonodes": ["kind"], "edit_mesh": ["op"]}
TOOLS = [
    _t("add_primitive", shape={"enum": SHAPES}, name=S, size=N, radius=N, depth=N, location=VEC, rotation_deg=VEC, scale=VEC,
       subdivisions=I, count=I, offset=VEC, ring_count=I, ring_radius=N, rows=I, row_offset=VEC,
       vertices=I, segments=I, rings=I, radius2=N, major_radius=N, minor_radius=N),
    _t("add_light", kind={"enum": ["SUN", "POINT", "SPOT", "AREA"]}, location=VEC, energy=N, name=S, rotation_deg=VEC),
    _t("add_camera", location=VEC, rotation_deg=VEC, name=S, lens=N, ortho=B),
    _t("add_empty", name=S, location=VEC, display={"enum": ["PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE"]}, rotation_deg=VEC),
    _t("add_curve", kind={"enum": ["bezier", "circle", "nurbs_path", "poly"]}, location=VEC, name=S, radius=N, bevel_depth=N, extrude=N, points=PTS),
    _t("add_text", body=S, location=VEC, rotation_deg=VEC, name=S, extrude=N, bevel_depth=N, size=N),
    _t("set_transform", object=S, location=VEC, rotation_deg=VEC, scale=VEC),
    _t("add_modifier", object=S, modifier={"enum": ["SUBSURF", "BEVEL", "SOLIDIFY", "ARRAY", "MIRROR", "BOOLEAN", "DECIMATE", "WIREFRAME", "SIMPLE_DEFORM", "DISPLACE", "TRIANGULATE", "WELD", "SMOOTH", "REMESH"]},
       levels=I, width=N, segments=I, thickness=N, count=I, offset=VEC, axis=S, apply=N,
       ratio=N, strength=N, operation={"enum": ["DIFFERENCE", "UNION", "INTERSECT"]}, target=S, subdivision_type={"enum": ["CATMULL_CLARK", "SIMPLE"]},
       voxel_size=N, deform_method={"enum": ["TWIST", "BEND", "TAPER", "STRETCH"]}, angle_deg=N, constant_offset=VEC),
    _t("apply_modifier", object=S),
    _t("set_material", object=S, name=S, color={"type": "array", "items": N, "minItems": 3, "maxItems": 4}, metallic=N, roughness=N,
       objects={"type": "array", "items": S}, emission_color=VEC, emission_strength=N, alpha=N, name2=S, color2={"type": "array", "items": N, "minItems": 3, "maxItems": 4}),
    _t("shade_smooth", object=S, smooth=B),
    _t("uv_unwrap", object=S, method={"enum": ["SMART", "CUBE", "UNWRAP", "NEW_MAP"]}, name=S),
    _t("add_empty_parent", name=S),
    _t("parent", child=S, parent=S),
    _t("keyframe", object=S, property={"enum": ["location", "rotation_deg", "scale", "lens", "energy", "emission", "hide_render", "color"]}, frame=I, value=VEC, amount=N,
       color={"type": "array", "items": N, "minItems": 3, "maxItems": 4}, interpolation={"enum": ["LINEAR", "BEZIER", "CONSTANT"]}),
    _t("set_frame_end", frame=I),
    _t("new_collection", name=S, objects={"type": "array", "items": S}),
    _t("join", objects={"type": "array", "items": S}),
    _t("set_object", object=S, name=S, hide_render=B, display_type={"enum": ["WIRE", "SOLID", "BOUNDS", "TEXTURED"]},
       clip_end=N, clip_start=N, hide_viewport=B),
    _t("apply_transform", object=S, scale=B, rotation=B, location=B, origin_geometry=B),
    _t("duplicate", object=S, offset=VEC, count=I, linked=B, name=S),
    _t("clone_object", object=S, location=VEC, count=I, offset=VEC, rotation_deg=VEC, linked=B, name=S),
    _t("edit_mesh", object=S, op={"enum": ["SUBDIVIDE", "BEVEL", "INSET", "EXTRUDE_TOP", "TO_MESH"]}, amount=N, cuts=I),
    _t("add_constraint", object=S, constraint={"enum": ["CHILD_OF", "TRACK_TO", "LIMIT_LOCATION", "FOLLOW_PATH", "COPY_LOCATION"]}, target=S, max_z=N),
    _t("add_shape_key", object=S, name=S, scale=VEC),
    _t("snow", name=S, location=VEC, size=N, count=I, lifetime=N, frame_start=I, frame_end=I, flake=N),
    _t("add_geonodes", object=S, kind={"enum": ["EMPTY", "SUBDIVIDE", "SCATTER", "SET_POSITION", "UV_SPHERE"]}, levels=I, radius=N, offset=VEC, size=N, density=N, instance=S),
    _t("scene_settings", frame_start=I, frame_end=I, fps=I, res_x=I, res_y=I, res_percent=I, engine={"enum": ["CYCLES", "BLENDER_EEVEE", "BLENDER_WORKBENCH"]},
       samples=I, file_format={"enum": ["PNG", "JPEG", "OPEN_EXR", "BMP", "TIFF"]}, world_color=VEC, marker_name=S, marker_frame=I),
]
SCHEMA = {"type": "object", "properties": {"calls": {"type": "array", "items": {"anyOf": TOOLS}, "minItems": 1, "maxItems": 40}}, "required": ["calls"]}

def _v(x, d):
    return list(x) if isinstance(x, (list, tuple)) and len(x) == 3 and all(isinstance(i, (int, float)) for i in x) else d

def compile_calls(doc):
    L = ["import bpy, math", "def _o(n):", "    return bpy.context.view_layer.objects.active if n in (None,'','last') else bpy.data.objects.get(n)",
         "def _a(o):", "    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o"]
    for c in doc.get("calls", []):
        t, g = c.get("tool"), c.get
        o = repr(g("object"))
        if t == "add_primitive":
            sh = g("shape", "cube")
            loc, rot, sc = _v(g("location"), [0, 0, 0]), _v(g("rotation_deg"), [0, 0, 0]), _v(g("scale"), None)
            kw = {"cube": "size", "plane": "size"}.get(sh)
            args = f"location=(_x,_y,_z), rotation=({','.join(f'math.radians({r})' for r in rot)})"
            if sh in ("cube", "plane") and g("size") is not None: args += f", size={float(g('size'))}"
            if sh in ("uv_sphere", "ico_sphere", "cylinder", "cone", "circle", "torus"):
                rad = g("radius")
                # a cylinder has one radius, but the model often writes it as radius2 (the cone-top
                # field). Dropping it silently let Blender's default radius of 1 through, which is
                # how the floor lamp ended up standing on a 2 m plate.
                if rad is None and sh in ("cylinder", "cone"):
                    rad = g("radius2")
                if rad is not None and sh != "torus": args += f", radius={float(rad)}"
            if sh in ("cylinder",) and g("depth") is not None: args += f", depth={float(g('depth'))}"
            if sh == "cone":
                if rad is not None:
                    args = args.replace(f", radius={float(rad)}", f", radius1={float(rad)}")
                if g("depth") is not None: args += f", depth={float(g('depth'))}"
            if sh == "ico_sphere" and g("subdivisions"): args += f", subdivisions={int(g('subdivisions'))}"
            if sh in ("cylinder", "cone", "circle") and g("vertices"): args += f", vertices={int(g('vertices'))}"
            if sh == "uv_sphere":
                if g("segments"): args += f", segments={int(g('segments'))}"
                if g("rings"): args += f", ring_count={int(g('rings'))}"
            if sh == "cone" and g("radius2") is not None: args += f", radius2={float(g('radius2'))}"
            if sh == "torus":
                if g("major_radius") is not None: args += f", major_radius={float(g('major_radius'))}"
                if g("minor_radius") is not None: args += f", minor_radius={float(g('minor_radius'))}"
            if sh == "grid":
                if g("size") is not None: args += f", size={float(g('size'))}"
                if g("subdivisions"): args += f", x_subdivisions={int(g('subdivisions'))}, y_subdivisions={int(g('subdivisions'))}"
            fn = {"cube": "cube", "plane": "plane", "uv_sphere": "uv_sphere", "ico_sphere": "ico_sphere", "cylinder": "cylinder", "cone": "cone", "torus": "torus", "monkey": "monkey", "circle": "circle", "grid": "grid"}.get(sh, "cube")
            if sh == "monkey": args = args.replace("rotation=", "rotation=")
            n = max(1, int(g("count") or 1)); off = _v(g("offset"), [0, 0, 0])
            rc = int(g("ring_count") or 0); rr = float(g("ring_radius") or 0)
            rows = max(1, int(g("rows") or 1)); ro = _v(g("row_offset"), [0, 2.5, 0])
            L.append(f"for _j in range({rows}):")
            L.append(f" for _i in range({rc or n}):")
            if rc:
                L.append(f"    _a_=_i*2*math.pi/{rc}; _x,_y,_z = {loc[0]}+{rr}*math.cos(_a_), {loc[1]}+{rr}*math.sin(_a_), {loc[2]}")
            else:
                L.append(f"    _x,_y,_z = {loc[0]}+_i*{off[0]}+_j*{ro[0]}, {loc[1]}+_i*{off[1]}+_j*{ro[1]}, {loc[2]}+_i*{off[2]}+_j*{ro[2]}")
            L.append(f"    bpy.ops.mesh.primitive_{fn}_add({args})")
            L.append("    _c = bpy.context.object")
            if g("name"): L.append(f"    _c.name = {g('name')!r}")
            if sc: L.append(f"    _c.scale = {tuple(sc)!r}")
            if g("name") is None and False: pass
        elif t == "add_light":
            L.append(f"bpy.ops.object.light_add(type={g('kind','POINT')!r}, location={tuple(_v(g('location'),[0,0,5]))!r})")
            if g("energy") is not None: L.append(f"bpy.context.object.data.energy = {float(g('energy'))}")
            if g("rotation_deg"): L.append(f"bpy.context.object.rotation_euler = tuple(math.radians(r) for r in {tuple(_v(g('rotation_deg'),[0,0,0]))!r})")
            if g("name"): L.append(f"bpy.context.object.name = {g('name')!r}")
        elif t == "add_camera":
            L.append(f"bpy.ops.object.camera_add(location={tuple(_v(g('location'),[0,-10,5]))!r}, rotation=tuple(math.radians(r) for r in {tuple(_v(g('rotation_deg'),[65,0,0]))!r}))")
            L.append("bpy.context.scene.camera = bpy.context.object")
            if g("lens") is not None: L.append(f"bpy.context.object.data.lens = {float(g('lens'))}")
            if g("ortho"): L.append("bpy.context.object.data.type = 'ORTHO'")
            if g("name"): L.append(f"bpy.context.object.name = {g('name')!r}")
        elif t == "add_empty":
            L.append(f"bpy.ops.object.empty_add(location={tuple(_v(g('location'),[0,0,0]))!r}" + (f", type={g('display')!r})" if g("display") else ")"))
            if g("rotation_deg"): L.append(f"bpy.context.object.rotation_euler = tuple(math.radians(r) for r in {tuple(_v(g('rotation_deg'),[0,0,0]))!r})")
            if g("name"): L.append(f"bpy.context.object.name = {g('name')!r}")
        elif t == "add_curve":
            pts = [p for p in (g("points") or []) if _v(p, None)]
            if g("kind") == "poly" and len(pts) >= 2:
                L += [f"_cu = bpy.data.curves.new({g('name', 'Curve')!r}, 'CURVE'); _cu.dimensions = '3D'; _sp = _cu.splines.new('POLY'); _sp.points.add({len(pts) - 1})",
                      f"for _p, _q in zip(_sp.points, {[list(p) for p in pts]!r}): _p.co = (_q[0], _q[1], _q[2], 1)",
                      f"_ob = bpy.data.objects.new({g('name', 'Curve')!r}, _cu); _ob.location = {tuple(_v(g('location'),[0,0,0]))!r}; bpy.context.collection.objects.link(_ob); _a(_ob)"]
            else:
                fn = {"circle": "bezier_circle", "nurbs_path": "nurbs_path"}.get(g("kind"), "bezier_curve")
                rad = f", radius={float(g('radius'))}" if g("radius") is not None else ""
                L.append(f"bpy.ops.curve.primitive_{fn}_add(location={tuple(_v(g('location'),[0,0,0]))!r}{rad})")
                if g("name"): L.append(f"bpy.context.object.name = {g('name')!r}")
            if g("bevel_depth") is not None: L.append(f"bpy.context.object.data.bevel_depth = {float(g('bevel_depth'))}")
            if g("size") is not None: L.append(f"bpy.context.object.data.size = {float(g('size'))}")
            if g("extrude") is not None: L.append(f"bpy.context.object.data.extrude = {float(g('extrude'))}")
        elif t == "add_text":
            L.append(f"bpy.ops.object.text_add(location={tuple(_v(g('location'),[0,0,0]))!r})")
            L.append(f"bpy.context.object.data.body = {str(g('body', 'Text'))!r}")
            if g("rotation_deg"): L.append(f"bpy.context.object.rotation_euler = tuple(math.radians(r) for r in {tuple(_v(g('rotation_deg'),[0,0,0]))!r})")
            if g("size") is not None: L.append(f"bpy.context.object.data.size = {float(g('size'))}")
            if g("extrude") is not None: L.append(f"bpy.context.object.data.extrude = {float(g('extrude'))}")
            if g("bevel_depth") is not None: L.append(f"bpy.context.object.data.bevel_depth = {float(g('bevel_depth'))}")
            if g("name"): L.append(f"bpy.context.object.name = {g('name')!r}")
        elif t == "set_transform":
            L += [f"_c = _o({o})", "if _c:"]
            if g("location"): L.append(f"    _c.location = {tuple(_v(g('location'),[0,0,0]))!r}")
            if g("rotation_deg"): L.append(f"    _c.rotation_euler = tuple(math.radians(r) for r in {tuple(_v(g('rotation_deg'),[0,0,0]))!r})")
            if g("scale"): L.append(f"    _c.scale = {tuple(_v(g('scale'),[1,1,1]))!r}")
            L.append("    pass")
        elif t == "add_modifier":
            m = g("modifier", "SUBSURF")
            L += [f"_c = _o({o})", "if _c:", f"    _m = _c.modifiers.new({m.title()!r}, {m!r})"]
            for key, attr in (("levels", "levels"), ("width", "width"), ("segments", "segments"), ("thickness", "thickness"), ("count", "count")):
                if g(key) is not None and (key != "levels" or m == "SUBSURF") and (key != "width" or m == "BEVEL") and (key != "segments" or m == "BEVEL") and (key != "thickness" or m == "SOLIDIFY") and (key != "count" or m == "ARRAY"):
                    L.append(f"    _m.{attr} = {g(key)!r}")
            if m == "WIREFRAME" and g("thickness") is not None: L.append(f"    _m.thickness = {float(g('thickness'))}")
            if m == "DECIMATE" and g("ratio") is not None: L.append(f"    _m.ratio = {float(g('ratio'))}")
            if m == "DISPLACE" and g("strength") is not None: L.append(f"    _m.strength = {float(g('strength'))}")
            if m == "BOOLEAN":
                L.append(f"    _m.operation = {g('operation', 'DIFFERENCE')!r}; _m.solver = 'EXACT'")
                if g("target"): L.append(f"    _m.object = bpy.data.objects.get({g('target')!r})")
            if m == "SUBSURF" and g("subdivision_type") == "SIMPLE": L.append("    _m.subdivision_type = 'SIMPLE'")
            if m == "REMESH" and g("voxel_size") is not None: L.append(f"    _m.mode = 'VOXEL'; _m.voxel_size = {float(g('voxel_size'))}")
            if m == "SIMPLE_DEFORM":
                if g("deform_method"): L.append(f"    _m.deform_method = {g('deform_method')!r}")
                if g("angle_deg") is not None: L.append(f"    _m.angle = math.radians({float(g('angle_deg'))})")
            if m == "ARRAY" and g("constant_offset"): L.append(f"    _m.use_relative_offset = False; _m.use_constant_offset = True; _m.constant_offset_displace = {tuple(_v(g('constant_offset'),[0,0,0]))!r}")
            if m == "ARRAY" and g("offset"): L.append(f"    _m.relative_offset_displace = {tuple(_v(g('offset'),[1,0,0]))!r}")
            if m == "MIRROR" and g("axis"): L.append(f"    _m.use_axis = [{str('X' in g('axis').upper())}, {str('Y' in g('axis').upper())}, {str('Z' in g('axis').upper())}]")
            L.append("    pass")
        elif t == "apply_modifier":
            L += [f"_c = _o({o})", "if _c and _c.modifiers:", "    _a(_c); bpy.ops.object.modifier_apply(modifier=_c.modifiers[-1].name)"]
        elif t == "set_material":
            col = list(g("color", [0.8, 0.8, 0.8])); col = (col + [1])[:4] if len(col) == 3 else col[:4]
            sel = f"[bpy.data.objects.get(n) for n in {g('objects')!r}]" if g("objects") else f"[x for x in bpy.data.objects if x.type == 'MESH'] if {g('object')!r} == 'all' else [_o({o})]"
            L += [f"_cs = {sel}", "for _k, _c in enumerate(_cs):", "  if _c and _c.type in ('MESH', 'FONT', 'CURVE'):"]
            if g("color2") and g("name2"):
                c2 = list(g("color2")); c2 = (c2 + [1])[:4] if len(c2) == 3 else c2[:4]
                L.append(f"    _mt = bpy.data.materials.get({g('name2')!r}) if _k % 2 else bpy.data.materials.get({g('name','Material')!r})")
                L.append(f"    if _mt is None: _mt = bpy.data.materials.new({g('name2')!r} if _k % 2 else {g('name','Material')!r})")
                L.append(f"    _mt.diffuse_color = {tuple(c2)!r} if _k % 2 else {tuple(col)!r}")
            else:
                L.append(f"    _mt = bpy.data.materials.new({g('name','Material')!r}); _mt.diffuse_color = {tuple(col)!r}")
            # render-visible colour: viewport diffuse_color alone renders white in EEVEE (the material-slot failure)
            L.append(f"    _mt.use_nodes = True; _mt.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = {tuple(col)!r}")
            if g("metallic") is not None: L.append(f"    _mt.metallic = {float(g('metallic'))}; _mt.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = {float(g('metallic'))}")
            if g("roughness") is not None: L.append(f"    _mt.roughness = {float(g('roughness'))}; _mt.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = {float(g('roughness'))}")
            if g("emission_color") or g("emission_strength") is not None or g("alpha") is not None:
                L.append("    _mt.use_nodes = True; _b = _mt.node_tree.nodes.get('Principled BSDF')")
                if g("emission_color"): L.append(f"    _b.inputs['Emission Color'].default_value = {tuple(_v(g('emission_color'),[1,1,1]) + [1])!r}")
                if g("emission_strength") is not None: L.append(f"    _b.inputs['Emission Strength'].default_value = {float(g('emission_strength'))}")
                if g("alpha") is not None: L.append(f"    _b.inputs['Alpha'].default_value = {float(g('alpha'))}; _mt.diffuse_color = {tuple(col[:3]) + (float(g('alpha')),)!r}")
            # an object that already has a material shows slot 0 on every face: appending the new
            # one changed nothing to see ("make the chair red" on a painted chair, checked in
            # Blender). The new material takes slot 0; an unpainted object gets its first.
            L.append("    _c.data.materials.__setitem__(0, _mt) if len(_c.data.materials) else _c.data.materials.append(_mt)")
        elif t == "shade_smooth":
            L += [f"_c = _o({o})", "if _c:", "    _a(_c); bpy.ops.object.shade_flat()" if g("smooth") is False else "    _a(_c); bpy.ops.object.shade_smooth()"]
        elif t == "uv_unwrap":
            meth = g("method", "SMART")
            if meth == "NEW_MAP":
                L += [f"_c = _o({o})", "if _c and _c.type == 'MESH':", "    if not _c.data.uv_layers: _c.data.uv_layers.new(name='UVMap')", f"    _c.data.uv_layers.new(name={g('name', 'UVMap2')!r})"]
            else:
                op = {"CUBE": "cube_project", "UNWRAP": "unwrap"}.get(meth, "smart_project")
                L += [f"_c = _o({o})", "if _c:", f"    _a(_c); bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.uv.{op}(); bpy.ops.object.mode_set(mode='OBJECT')"]
        elif t == "parent":
            # parenting must not move the child: the parent's transform is compensated by
            # matrix_parent_inverse, so the child stays where it is and only then follows
            # (FINDINGS 34)
            L += [f"_ch, _pa = bpy.data.objects.get({g('child')!r}), bpy.data.objects.get({g('parent')!r})",
                  "if _ch and _pa:",
                  # the matrix_world below is STALE without this: an object whose scale was just
                  # set still reports its old matrix, and restoring it silently wipes the scale
                  # (the hero door leaf came back as a 2 m cube instead of 1.7 x 0.12 x 2.3)
                  "    bpy.context.view_layer.update()",
                  "    _mw = _ch.matrix_world.copy()",
                  "    _ch.parent = _pa",
                  "    _ch.matrix_parent_inverse = _pa.matrix_world.inverted()",
                  "    _ch.matrix_world = _mw"]
        elif t == "keyframe":
            prop = {"rotation_deg": "rotation_euler"}.get(g("property"), g("property", "location"))
            v = _v(g("value"), [0, 0, 0])
            if g("property") == "rotation_deg": v = [math.radians(x) for x in v]
            fr = int(g("frame", 1)); amt = float(g("amount") or 0)
            if prop == "lens":
                L += [f"_c = _o({o})", "if _c and _c.type == 'CAMERA':",
                      f"    _c.data.lens = {amt}", f"    _c.data.keyframe_insert('lens', frame={fr})"]
                tgt = "_c.data"
            elif prop == "emission":
                # the Principled emission strength is a node input, not an object property; the
                # glow cascade (windows and lamps on one by one) needs exactly this key
                L += [f"_c = _o({o})",
                      "_m = _c.active_material if _c and _c.type in ('MESH', 'FONT', 'CURVE') else None",
                      "if _m and _m.use_nodes:",
                      "    _n = next((n for n in _m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)",
                      "    _s = _n.inputs.get('Emission Strength') if _n else None",
                      "    if _s:",
                      f"        _s.default_value = {amt}",
                      f"        _s.keyframe_insert('default_value', frame={fr})"]
                tgt = "_m.node_tree"
            elif prop == "energy":
                L += [f"_c = _o({o})", "if _c and _c.type == 'LIGHT':", f"    _c.data.energy = {amt}", f"    _c.data.keyframe_insert('energy', frame={fr})"]; tgt = "_c.data"
            elif prop == "hide_render":
                L += [f"_c = _o({o})", "if _c:", f"    _c.hide_render = {bool(amt)}", f"    _c.keyframe_insert('hide_render', frame={fr})"]; tgt = "_c"
            elif prop == "color":
                col = list(g("color", [1, 1, 1])); col = (col + [1])[:4] if len(col) == 3 else col[:4]
                L += [f"_c = _o({o})", "_c = _c.active_material if _c and _c.type in ('MESH', 'FONT', 'CURVE') else None", "if _c:", f"    _c.diffuse_color = {tuple(col)!r}", f"    _c.keyframe_insert('diffuse_color', frame={fr})"]; tgt = "_c"
            else:
                L += [f"_c = _o({o})", "if _c:", f"    _c.{prop} = {tuple(v)!r}", f"    _c.keyframe_insert({prop!r}, frame={fr})"]; tgt = "_c"
            if g("interpolation"):
                if not any("def _lin" in x for x in L):
                    L[1:1] = ["def _lin(i, t):", "    ad = i.animation_data; act = ad.action if ad else None", "    if not act: return",
                              "    fcs = act.fcurves if hasattr(act, 'fcurves') else [f for l in act.layers for s in l.strips for cb in s.channelbags for f in cb.fcurves]",
                              "    for f in fcs:", "        for k in f.keyframe_points: k.interpolation = t"]
                L += [f"if _c: _lin({tgt}, {g('interpolation')!r})"]
        elif t == "set_frame_end":
            L.append(f"bpy.context.scene.frame_end = {int(g('frame', 250))}")
        elif t == "new_collection":
            L += [f"_k = bpy.data.collections.new({g('name')!r}); bpy.context.scene.collection.children.link(_k)",
                  f"for _n in ({g('objects') or ['last']!r}):", "    _c = _o(_n)", "    if _c:", "        [u.objects.unlink(_c) for u in list(_c.users_collection)]; _k.objects.link(_c)"]
        elif t == "join":
            L += [f"_l = [bpy.data.objects.get(n) for n in {g('objects') or []!r}]", "_l = [x for x in _l if x and x.type == 'MESH']",
                  "if len(_l) > 1:", "    bpy.ops.object.select_all(action='DESELECT')", "    [x.select_set(True) for x in _l]", "    bpy.context.view_layer.objects.active = _l[0]; bpy.ops.object.join()"]
        elif t == "set_object":
            L += [f"_c = _o({o})", "if _c:"]
            if g("name"): L.append(f"    _c.name = {g('name')!r}")
            if g("hide_render") is not None: L.append(f"    _c.hide_render = {bool(g('hide_render'))}")
            if g("display_type"): L.append(f"    _c.display_type = {g('display_type')!r}")
            if g("hide_viewport") is not None:
                L.append(f"    _c.hide_viewport = {bool(g('hide_viewport'))}")
            # a camera that has to see the mountains at 300 m cannot keep the default 100 m clip
            # the type check belongs in the GENERATED code: at compile time there is no _c
            if g("clip_end") is not None:
                L.append(f"    if _c.type == 'CAMERA': _c.data.clip_end = {float(g('clip_end'))}")
            if g("clip_start") is not None:
                L.append(f"    if _c.type == 'CAMERA': _c.data.clip_start = {float(g('clip_start'))}")
            L.append("    pass")
        elif t == "apply_transform":
            sc, ro, lo = bool(g("scale")), bool(g("rotation")), bool(g("location"))
            if not (sc or ro or lo or g("origin_geometry")): sc = True
            L += [f"_c = _o({o})", "if _c:"]
            if sc or ro or lo:
                # NOT bpy.ops.object.transform_apply any more. Called from a timer inside a live
                # GUI session it crashed the whole take at row 28 (Blender 5.2.2:
                # ed::transform::transformEnd -> special_aftertransform -> BKE_ptcache_ids_from_object,
                # SIGSEGV). The operator's job -- bake the selected parts of the transform into the
                # MESH data and leave the rest on the object -- is two matrix assignments.
                L += ["    if _c.type in ('MESH', 'CURVE', 'FONT'):",
                      "        from mathutils import Matrix as _Mx, Quaternion as _Q, Vector as _V",
                      "        _l, _r, _s = _c.matrix_basis.decompose()",
                      f"        _bl = _V(_l) if {lo} else _V((0, 0, 0))",
                      f"        _br = _r.copy() if {ro} else _Q((1, 0, 0, 0))",
                      f"        _bs = _V(_s) if {sc} else _V((1, 1, 1))",
                      f"        _rl = _V((0, 0, 0)) if {lo} else _V(_l)",
                      f"        _rr = _Q((1, 0, 0, 0)) if {ro} else _r",
                      f"        _rs = _V((1, 1, 1)) if {sc} else _V(_s)",
                      # a shared mesh must not be baked twice (a linked duplicate would move too)
                      "        if _c.data.users > 1: _c.data = _c.data.copy()",
                      "        _c.data.transform(_Mx.LocRotScale(_bl, _br, _bs))",
                      "        _c.matrix_basis = _Mx.LocRotScale(_rl, _rr, _rs)",
                      "        _c.data.update()",
                      "    else:",
                      "        _a(_c)",
                      f"        try: bpy.ops.object.transform_apply(location={lo}, rotation={ro}, scale={sc})",
                      "        except Exception: pass"]
            if g("origin_geometry"): L.append("    _a(_c); bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')")
            L.append("    pass")
        elif t == "clone_object":
            # duplicate with the whole subtree: a parented item (house, lamp, car) is only one
            # object to the user, but several objects in the scene. `duplicate` copies the root
            # alone and drops the children; this copies the tree, keeps parenting, then places
            # and rotates the copy.
            loc = _v(g("location"), None)
            off = _v(g("offset"), [0, 0, 0])
            rot = _v(g("rotation_deg"), [0, 0, 0])
            cnt = max(1, int(g("count") or 1))
            nm = g("name")
            L += [f"_root = _o({o})", "if _root:", "  _tree = [_root] + list(_root.children_recursive)",
                  f"  for _i in range({cnt}):", "    _map = {}", "    for _t in _tree:",
                  "      _d = _t.copy()",
                  f"      _d.data = _t.data if {bool(g('linked'))} or _t.data is None else _t.data.copy()",
                  "      bpy.context.collection.objects.link(_d)", "      _map[_t] = _d",
                  "    for _t in _tree:", "      _d = _map[_t]",
                  "      _d.parent = _map.get(_t.parent, _t.parent)",
                  "      if _t.parent in _map:",
                  "        _rel = _t.parent.matrix_world.inverted() @ _t.matrix_world",
                  "        _d.matrix_parent_inverse.identity(); _d.matrix_basis = _rel",
                  "    _d0 = _map[_root]"]
            if loc:
                L.append(f"    _d0.location = ({loc[0]}+{off[0]}*_i, {loc[1]}+{off[1]}*_i, {loc[2]}+{off[2]}*_i)")
            else:
                L.append(f"    _d0.location = (_root.location.x+{off[0]}*(_i+1), _root.location.y+{off[1]}*(_i+1), _root.location.z+{off[2]}*(_i+1))")
            if any(rot):
                L.append(f"    _d0.rotation_euler = tuple(math.radians(float(a)) for a in {tuple(rot)!r})")
            if nm:
                L.append(f"    _d0.name = {nm!r} if {cnt} == 1 else {nm!r} + '.' + str(_i+1).zfill(2)")
            L.append("    _a(_d0)")
        elif t == "duplicate":
            off = _v(g("offset"), [0, 0, 0])
            L += [f"_c = _o({o})", "if _c:", f"  for _i in range({max(1, int(g('count') or 1))}):",
                  f"    _d = _c.copy(); _d.data = _c.data if {bool(g('linked'))} or _c.data is None else _c.data.copy()",
                  f"    _d.location = (_c.location.x + {off[0]}*(_i+1), _c.location.y + {off[1]}*(_i+1), _c.location.z + {off[2]}*(_i+1))",
                  "    bpy.context.collection.objects.link(_d); _a(_d)"]
            if g("name"): L.append(f"    _d.name = {g('name')!r}")
        elif t == "edit_mesh":
            op, amt = g("op", "SUBDIVIDE"), g("amount")
            L += [f"_c = _o({o})", "if _c and _c.type in ('MESH', 'FONT'):"]
            if op == "TO_MESH":
                L.append("    _a(_c); bpy.ops.object.convert(target='MESH')")
            elif op == "EXTRUDE_TOP":
                L += ["    import bmesh", "    _bm = bmesh.new(); _bm.from_mesh(_c.data)", "    _top = max(_bm.faces, key=lambda f: f.calc_center_median().z)",
                      "    _r = bmesh.ops.extrude_face_region(_bm, geom=[_top])",
                      f"    bmesh.ops.translate(_bm, vec=(0, 0, {float(amt if amt is not None else 1)}), verts=[v for v in _r['geom'] if isinstance(v, bmesh.types.BMVert)])",
                      "    _bm.to_mesh(_c.data); _bm.free()"]
            else:
                call = {"SUBDIVIDE": f"subdivide(number_cuts={int(g('cuts') or 1)})", "BEVEL": f"bevel(offset={float(amt if amt is not None else 0.1)})",
                        "INSET": f"inset(thickness={float(amt if amt is not None else 0.1)}, use_individual=True)"}.get(op, "subdivide(number_cuts=1)")
                L.append(f"    _a(_c); bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.{call}; bpy.ops.object.mode_set(mode='OBJECT')")
        elif t == "add_constraint":
            k = g("constraint", "COPY_LOCATION")
            L += [f"_c = _o({o})", f"_tg = bpy.data.objects.get({g('target')!r}) if {g('target')!r} else None", "if _c:", f"    _k = _c.constraints.new({k!r})"]
            if k != "LIMIT_LOCATION": L.append("    if _tg: _k.target = _tg")
            if k == "TRACK_TO": L.append("    _k.track_axis = 'TRACK_NEGATIVE_Z'; _k.up_axis = 'UP_Y'")
            if k == "LIMIT_LOCATION": L.append(f"    _k.use_max_z = True; _k.max_z = {float(g('max_z') if g('max_z') is not None else 0)}")
        elif t == "add_shape_key":
            sc = _v(g("scale"), None)
            L += [f"_c = _o({o})", "if _c and _c.type == 'MESH':", "    if not _c.data.shape_keys: _c.shape_key_add(name='Basis')"]
            if str(g("name", "Key")).lower() != "basis":
                L.append(f"    _s = _c.shape_key_add(name={g('name', 'Key')!r})")
                if sc: L.append(f"    for _v in _s.data: _v.co = (_v.co.x*{sc[0]}, _v.co.y*{sc[1]}, _v.co.z*{sc[2]})")
        elif t == "add_geonodes":
            k = g("kind", "EMPTY")
            if not any("def _gn" in x for x in L):
                L[1:1] = ["def _gn():", "    gr = bpy.data.node_groups.new('GN', 'GeometryNodeTree')",
                          "    gr.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')",
                          "    gr.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')", "    return gr"]
            if k == "UV_SPHERE" and not g("object"):
                L += ["_c = bpy.data.objects.new('Gen', bpy.data.meshes.new('Empty')); bpy.context.collection.objects.link(_c); _a(_c)"]
            else:
                L += [f"_c = _o({o})"]
            L += ["if _c:", "    _g = _gn(); _no = _g.nodes.new('NodeGroupOutput')"]
            if k != "UV_SPHERE": L.append("    _ni = _g.nodes.new('NodeGroupInput')")
            if k == "SUBDIVIDE":
                L += ["    _n = _g.nodes.new('GeometryNodeSubdivideMesh')", f"    _n.inputs['Level'].default_value = {int(g('levels') or 1)}",
                      "    _g.links.new(_ni.outputs[0], _n.inputs['Mesh']); _g.links.new(_n.outputs['Mesh'], _no.inputs[0])"]
            elif k == "SET_POSITION":
                L += ["    _n = _g.nodes.new('GeometryNodeSetPosition')", f"    _n.inputs['Offset'].default_value = {tuple(_v(g('offset'), [0, 0, 1]))!r}",
                      "    _g.links.new(_ni.outputs[0], _n.inputs['Geometry']); _g.links.new(_n.outputs['Geometry'], _no.inputs[0])"]
            elif k == "SCATTER":
                s_ = float(g("size") or 0.2)
                dens = float(g("density") or 8)
                inst = g("instance")
                L += ["    _d = _g.nodes.new('GeometryNodeDistributePointsOnFaces'); _in = _g.nodes.new('GeometryNodeInstanceOnPoints')",
                      f"    _d.inputs['Density'].default_value = {dens}",
                      "    _g.links.new(_ni.outputs[0], _d.inputs['Mesh']); _g.links.new(_d.outputs['Points'], _in.inputs['Points'])",
                      # keep the surface itself: the scatter replaces the lawn with bare instances
                      # and the snow shows through, so join the bed back in
                      "    _jg = _g.nodes.new('GeometryNodeJoinGeometry')",
                      "    _g.links.new(_ni.outputs[0], _jg.inputs[0]); _g.links.new(_in.outputs['Instances'], _jg.inputs[0])",
                      "    _g.links.new(_jg.outputs[0], _no.inputs[0])"]
                if inst:
                    # instance a real mesh (a grass clump), not a cube: one object on the ground,
                    # thousands of blades. The source can be parked anywhere (it is hidden from
                    # the render): its geometry is taken in ITS OWN space, so neither where it
                    # stands nor where the lawn stands moves a blade.
                    # Before, this read the source RELATIVE to the lawn and subtracted the
                    # source's WORLD place: right only for a lawn at the origin. The playground of
                    # the Christmas take stands at (9.2, -80), so every clump was drawn 80 m from
                    # its point, turned at random: grass in a ring over the whole street ("grasses
                    # on the road at every shot"; measured on the saved demo scene).
                    L += [f"    _src = bpy.data.objects.get({inst!r})",
                          f"    _io = _g.nodes.new('GeometryNodeObjectInfo')",
                          f"    _io.inputs['Object'].default_value = _src",
                          "    _io.transform_space = 'ORIGINAL'",
                          "    _tr = _g.nodes.new('GeometryNodeTransform')",
                          # stand the clump on its point: its lowest vertex 2 cm under the surface
                          "    _tr.inputs['Translation'].default_value = (0.0, 0.0, -min(c[2] for c in _src.bound_box) * _src.scale[2] - 0.02)",
                          "    _tr.inputs['Scale'].default_value = tuple(_src.scale)",
                          "    _g.links.new(_io.outputs['Geometry'], _tr.inputs['Geometry'])",
                          "    _g.links.new(_tr.outputs['Geometry'], _in.inputs['Instance'])",
                          "    _rv = _g.nodes.new('FunctionNodeRandomValue'); _rv.data_type = 'FLOAT_VECTOR'",
                          "    _rv.inputs[0].default_value = (0.0, 0.0, 0.0); _rv.inputs[1].default_value = (0.0, 0.0, 6.2832)",
                          "    _g.links.new(_rv.outputs[0], _in.inputs['Rotation'])",
                          "    _rs = _g.nodes.new('FunctionNodeRandomValue'); _rs.data_type = 'FLOAT'",
                          "    _rs.inputs[0].default_value = 0.75; _rs.inputs[1].default_value = 1.35",
                          "    _g.links.new(_rs.outputs[0], _in.inputs['Scale'])"]
                else:
                    L += ["    _cb = _g.nodes.new('GeometryNodeMeshCube')",
                          f"    _cb.inputs['Size'].default_value = ({s_},{s_},{s_})",
                          "    _g.links.new(_cb.outputs['Mesh'], _in.inputs['Instance'])"]
            elif k == "UV_SPHERE":
                L += ["    _n = _g.nodes.new('GeometryNodeMeshUVSphere')", f"    _n.inputs['Radius'].default_value = {float(g('radius') or 1)}",
                      "    _g.links.new(_n.outputs['Mesh'], _no.inputs[0])"]
            L.append("    _c.modifiers.new('GeometryNodes', 'NODES').node_group = _g")
        elif t == "snow":
            # falling snow as a particle emitter. The model failed this twice (a column of cubes,
            # then 67 stacked planes), so the emitter is a tool: plane + instance flakes.
            name = g("name", "Snow")
            loc = _v(g("location"), [0, 0, 20])
            size = float(g("size") or 120)
            count = int(g("count") or 12000)
            life = float(g("lifetime") or 140)
            fs = int(g("frame_start") or 1)
            fe = int(g("frame_end") or 300)
            flake = float(g("flake") or 0.05)
            L += [f"bpy.ops.mesh.primitive_plane_add(size={size}, location=({loc[0]},{loc[1]},{loc[2]}))",
                  "_e = bpy.context.object", f"_e.name = {name!r}",
                  f"bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius={flake}, "
                  f"location=({loc[0]},{loc[1]},{loc[2] - 500}))",
                  "_f = bpy.context.object", f"_f.name = {name!r} + 'Flake'",
                  "_m = bpy.data.materials.new('SnowFlake'); _m.use_nodes = True",
                  "_b = next((n for n in _m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)",
                  "if _b:",
                  "    _b.inputs['Base Color'].default_value = (0.95, 0.96, 1.0, 1)",
                  "    _b.inputs['Roughness'].default_value = 0.7",
                  "_f.data.materials.append(_m)",
                  "_ps = _e.modifiers.new('Snow', 'PARTICLE_SYSTEM').particle_system",
                  "_st = _ps.settings",
                  f"_st.count = {count}", f"_st.lifetime = {life}",
                  f"_st.frame_start = {fs}", f"_st.frame_end = {fe}",
                  "_st.emit_from = 'FACE'", "_st.normal_factor = -0.5",
                  "_st.effector_weights.gravity = 1",
                  "_st.physics_type = 'NEWTON'", "_st.render_type = 'OBJECT'",
                  "_st.instance_object = _f", f"_st.particle_size = {max(flake * 10, 0.4)}",
                  "_st.size_random = 0.6"]
        elif t == "scene_settings":
            L.append("_s = bpy.context.scene")
            for key, attr in (("frame_start", "frame_start"), ("frame_end", "frame_end")):
                if g(key) is not None: L.append(f"_s.{attr} = {int(g(key))}")
            for key, attr in (("fps", "fps"), ("res_x", "resolution_x"), ("res_y", "resolution_y"), ("res_percent", "resolution_percentage")):
                if g(key) is not None: L.append(f"_s.render.{attr} = {int(g(key))}")
            if g("engine"): L.append(f"_s.render.engine = {g('engine')!r}")
            if g("samples") is not None: L.append(f"_s.cycles.samples = {int(g('samples'))}")
            if g("file_format"): L.append(f"_s.render.image_settings.file_format = {g('file_format')!r}")
            if g("world_color"):
                L.append(f"_w = bpy.data.worlds.new('World'); _w.color = {tuple(_v(g('world_color'), [0.05, 0.05, 0.05]))!r}; _s.world = _w")
            if g("marker_name") and g("marker_frame") is not None: L.append(f"_s.timeline_markers.new({g('marker_name')!r}, frame={int(g('marker_frame'))})")
    return "\n".join(L)

PROMPT = ("You control Blender by emitting JSON tool calls, executed in order on an empty scene. Output only JSON: {\"calls\":[...]}.\n"
          "Tools: add_primitive(shape cube|uv_sphere|ico_sphere|cylinder|cone|torus|plane|monkey|circle|grid, name,size,radius,radius2 (cone top),depth,vertices,segments,rings,major_radius,minor_radius,location,rotation_deg,scale,subdivisions,count+offset (a row), ring_count+ring_radius (a circle), rows+row_offset (a grid of copies)); "
          "add_light(kind SUN|POINT|SPOT|AREA,location,rotation_deg,energy,name); add_camera(location,rotation_deg,lens,ortho,name); add_empty(name,location,display PLAIN_AXES|SPHERE|CUBE|ARROWS|CIRCLE|CONE|SINGLE_ARROW,rotation_deg); "
          "add_curve(kind bezier|circle|nurbs_path|poly,location,radius,bevel_depth,extrude,points (poly: [[x,y,z],..])); add_text(body,location,rotation_deg,extrude,bevel_depth,size,name); "
          "set_transform(object,location,rotation_deg,scale); apply_transform(object,scale,rotation,location,origin_geometry); duplicate(object,offset,count,linked,name); "
          "add_modifier(object,modifier SUBSURF|BEVEL|SOLIDIFY|ARRAY|MIRROR|BOOLEAN|DECIMATE|WIREFRAME|SIMPLE_DEFORM|DISPLACE|TRIANGULATE|WELD|SMOOTH|REMESH,levels,subdivision_type,width,segments,thickness,count,offset,constant_offset,axis,ratio,strength,operation DIFFERENCE|UNION|INTERSECT,target (boolean cutter object),voxel_size,deform_method,angle_deg); apply_modifier(object); "
          "set_object(object,name,hide_render,display_type WIRE|SOLID|BOUNDS,clip_end,clip_start); edit_mesh(object,op SUBDIVIDE|BEVEL|INSET|EXTRUDE_TOP|TO_MESH,amount,cuts); "
          "set_material(object (or 'all'),objects,name,color,metallic,roughness,emission_color,emission_strength,alpha,name2+color2 (alternate two materials over 'all')); shade_smooth(object,smooth); uv_unwrap(object,method SMART|CUBE|UNWRAP|NEW_MAP,name); "
          "parent(child,parent); add_constraint(object,constraint CHILD_OF|TRACK_TO|LIMIT_LOCATION|FOLLOW_PATH|COPY_LOCATION,target,max_z); add_shape_key(object,name,scale); "
          "add_geonodes(object,kind EMPTY|SUBDIVIDE|SCATTER|SET_POSITION|UV_SPHERE,levels,radius,offset,size); "
          "keyframe(object,property location|rotation_deg|scale|lens|energy|emission|hide_render|color,frame,value,amount (energy, emission strength, hide_render 0/1),color,interpolation LINEAR|BEZIER|CONSTANT); "
          "snow(name,location,size,count,lifetime,frame_start,frame_end,flake (falling snow emitter: plane + particle flakes)); "
          "scene_settings(frame_start,frame_end,fps,res_x,res_y,res_percent,engine CYCLES|BLENDER_EEVEE,samples,file_format,world_color,marker_name+marker_frame); set_frame_end(frame); new_collection(name,objects); join(objects). "
          "'object' defaults to the last created object. Name objects you need to refer to later.\n"
          "Example: add a red cube 2 high at x=3 -> {\"calls\":[{\"tool\":\"add_primitive\",\"shape\":\"cube\",\"name\":\"Box\",\"location\":[3,0,1],\"scale\":[1,1,1]},{\"tool\":\"set_material\",\"name\":\"Red\",\"color\":[1,0,0]}]}")

SHORT = 'Output Blender tool calls as JSON: {"calls":[...]}.'
