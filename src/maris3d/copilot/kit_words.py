# SPDX-License-Identifier: Apache-2.0
"""0.2.1 change words: what 0.1 could do with its own tool calls, said the 0.2 way (the model writes
words, code writes the calls). Each DO here is applied by apply_change.apply_answer like the others.

    camera   looks_at?: <thing>, from?: front|back|left|right|above, distance?: <distance word>, name?
             -> add_camera + a TRACK_TO constraint on the thing (no thing: the middle of the scene)
    light    kind?: sun|lamp|spot|soft, bright?: dim|normal|bright, over?: <thing>, name?
    text     says: <the words, as said>, near?: <thing>, name?
    retext   object: <a text object>, says
    attach   object: <child thing>, to: <parent thing>        (parent: the child follows, does not move)
    aim      object: <thing>, at: <thing>                       (TRACK_TO: it keeps pointing at it)
    finish   object, parts?, how: bevel|subdivide|thicken|wire|mirror|array|taper|bend|twist,
             count?: <copies, array>, toward?: left|right|front|back|up|down (array), across?: width|depth|height (mirror)
    scene    background?: <colour word>, seconds?: <the number said>, fps?: <the number said>

The 0.2 prompts (edit_words.EDIT_SYSTEM*) are the bytes the shipped adapter was trained on and do not
change; KIT_SYSTEM below is appended only for an adapter trained on these words (0.2.1).
"""
from . import apply_change as AC
from . import compile_plan as CP
from . import colours as COL
from . import place as PLACE

DOS = ("camera", "light", "text", "retext", "attach", "aim", "finish", "scene")
CAMERA_FROM = {"front": (0.0, -1.0, 0.35), "back": (0.0, 1.0, 0.35), "left": (-1.0, 0.0, 0.35),
               "right": (1.0, 0.0, 0.35), "above": (0.0, -0.25, 1.0)}
LIGHT_KINDS = {"sun": "SUN", "lamp": "POINT", "spot": "SPOT", "soft": "AREA"}
BRIGHT = {"SUN": {"dim": 1.5, "normal": 3.0, "bright": 6.0},
          "POINT": {"dim": 300.0, "normal": 1000.0, "bright": 3000.0},
          "SPOT": {"dim": 500.0, "normal": 1500.0, "bright": 4000.0},
          "AREA": {"dim": 150.0, "normal": 500.0, "bright": 1500.0}}
FINISH = ("bevel", "subdivide", "thicken", "wire", "mirror", "array", "taper", "bend", "twist")
DEFORM = {"taper": ("TAPER", 0.0), "bend": ("BEND", 45.0), "twist": ("TWIST", 90.0)}
TOWARD = {"left": (-1, 0, 0), "right": (1, 0, 0), "front": (0, -1, 0), "back": (0, 1, 0), "up": (0, 0, 1), "down": (0, 0, -1)}
ACROSS = {"width": "X", "depth": "Y", "height": "Z"}

KIT_SYSTEM = (
    " Others lists the cameras, lights and texts in the scene by name; aim, attach, retext and remove may name them."
    " More do: camera (looks_at: a thing, from: front|back|left|right|above, distance: a distance word); light "
    "(kind: sun|lamp|spot|soft, bright: dim|normal|bright, over: a thing); text (says: the words as said, near: a "
    "thing); retext (object, says); attach (object: the child, to: the parent); aim (object, at: a thing); finish "
    "(how: bevel|subdivide|thicken|wire|mirror|array|taper|bend|twist, count for array, toward for array, "
    "across: width|depth|height for mirror); scene (background: a colour word, seconds or fps when said)."
)


# ---- where things are -------------------------------------------------------------------------

def _boxes(ctx):
    things, parts = ctx.boxes()
    return things, parts


def _box(ctx, name, what):
    things, _ = _boxes(ctx)
    if isinstance(name, str) and name not in things:        # a camera, light or empty has no size: a small box at it
        o = next((o for o in ctx.scene if o.get("name") == name and o.get("loc")), None)
        if o is not None:
            return {"lo": [v - 0.1 for v in o["loc"]], "hi": [v + 0.1 for v in o["loc"]]}
    if not isinstance(name, str) or name not in things:
        raise AC.ChangeError(f"{what} {name!r} is not in the scene; it has: " + ", ".join(sorted(things)))
    return things[name]


def _mid(b):
    return [(b["lo"][i] + b["hi"][i]) / 2.0 for i in range(3)]


def _reach(b):
    return max(b["hi"][i] - b["lo"][i] for i in range(3))


def _scene_box(ctx):
    things, _ = _boxes(ctx)
    return CP.union(things.values()) if things else {"lo": [-1.0, -1.0, 0.0], "hi": [1.0, 1.0, 1.0]}


def _free(ctx, base):
    taken = ctx.taken()
    if base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _name(ctx, ch, base):
    n = ch.get("name")
    if n is not None:
        if not isinstance(n, str) or not n.strip():
            raise AC.ChangeError("name is a word")
        if n in ctx.taken():
            raise AC.ChangeError(f"the name {n!r} is taken")
        return n
    return _free(ctx, base)


def _word(ch, key, words, default):
    v = ch.get(key, default)
    if v not in words:
        raise AC.ChangeError(f"{key} {v!r}; one of " + ", ".join(words))
    return v


def _seen(ctx, name, loc, kind="OTHER"):
    """Keep the scene the context reads in step: a later change of the same answer may name it."""
    ctx.scene.append({"name": name, "type": kind, "loc": [round(x, 4) for x in loc], "dims": [0.2, 0.2, 0.2]})


# ---- the DOs ----------------------------------------------------------------------------------

def _camera(ctx, ch):
    target = ch.get("looks_at")
    b = _box(ctx, target, "looks_at") if target is not None else _scene_box(ctx)
    side = _word(ch, "from", CAMERA_FROM, "front")
    dist = _word(ch, "distance", PLACE.GAP, "large")
    c, r = _mid(b), max(_reach(b), 0.5)
    d = max(2.2 * r, 2.5) * {"touching": 0.6, "tiny": 0.7, "small": 0.8, "medium": 0.9, "large": 1.0,
                             "far": 1.6, "distant": 2.5}[dist]
    v = CAMERA_FROM[side]
    loc = [round(c[0] + v[0] * d, 4), round(c[1] + v[1] * d, 4), round(c[2] + v[2] * d, 4)]
    name = _name(ctx, ch, "Camera")
    calls = [{"tool": "add_camera", "name": name, "location": loc}]
    if target is not None:
        calls.append({"tool": "add_constraint", "object": name, "constraint": "TRACK_TO", "target": target})
    else:                                   # the middle of the scene: an empty to look at
        aim = _free(ctx, "CameraTarget")
        calls = [{"tool": "add_empty", "name": aim, "location": [round(x, 4) for x in c]}] + calls + \
                [{"tool": "add_constraint", "object": name, "constraint": "TRACK_TO", "target": aim}]
        _seen(ctx, aim, c)
    _seen(ctx, name, loc, "CAMERA")
    return calls, {"present": [name], "loc": {}}


def _light(ctx, ch):
    kind = LIGHT_KINDS[_word(ch, "kind", LIGHT_KINDS, "lamp")]
    bright = _word(ch, "bright", BRIGHT[kind], "normal")
    over = ch.get("over")
    b = _box(ctx, over, "over") if over is not None else _scene_box(ctx)
    c, r = _mid(b), max(_reach(b), 0.5)
    loc = [round(c[0] + 0.6 * r, 4), round(c[1] - 0.6 * r, 4), round(b["hi"][2] + max(1.5 * r, 1.5), 4)]
    name = _name(ctx, ch, {"SUN": "Sun", "POINT": "Lamp", "SPOT": "Spot", "AREA": "SoftLight"}[kind])
    call = {"tool": "add_light", "kind": kind, "name": name, "location": loc, "energy": BRIGHT[kind][bright]}
    calls = [call]
    if kind in ("SPOT", "AREA") and over is not None:
        calls.append({"tool": "add_constraint", "object": name, "constraint": "TRACK_TO", "target": over})
    _seen(ctx, name, loc, "LIGHT")
    return calls, {"present": [name]}


def _says(ch):
    s = ch.get("says")
    if not isinstance(s, str) or not s.strip():
        raise AC.ChangeError("says is the words, as said")
    return s.strip()[:200]


def _text(ctx, ch):
    body = _says(ch)
    near = ch.get("near")
    if near is not None:
        b = _box(ctx, near, "near")
        loc = [round(_mid(b)[0], 4), round(b["lo"][1] - 0.3, 4), round(b["hi"][2] + 0.3, 4)]
    else:
        b = _scene_box(ctx)
        loc = [round(_mid(b)[0], 4), round(b["lo"][1] - 0.5, 4), 0.0]
    name = _name(ctx, ch, "Text")
    _seen(ctx, name, loc, "FONT")
    return [{"tool": "add_text", "body": body, "name": name, "location": loc, "rotation_deg": [90.0, 0.0, 0.0],
             "extrude": 0.02}], {"present": [name]}


def _retext(ctx, ch, _spec=None):
    name, body = ch.get("object"), _says(ch)
    o = next((o for o in ctx.scene if o.get("name") == name), None)
    if o is None or (o.get("type") not in (None, "FONT", "OTHER")):
        raise AC.ChangeError(f"{name!r} is not a text in the scene")
    loc = o.get("loc") or [0.0, 0.0, 0.0]
    rot = o.get("rot_deg") or [90.0, 0.0, 0.0]
    return [{"tool": "delete_object", "object": name},
            {"tool": "add_text", "body": body, "name": name, "location": loc, "rotation_deg": rot, "extrude": 0.02}], \
        {"present": [name]}


def _attach(ctx, ch, _spec=None):
    child, parent = ch.get("object"), ch.get("to")
    _box(ctx, child, "object")
    _box(ctx, parent, "to")
    if child == parent:
        raise AC.ChangeError("a thing cannot be attached to itself")
    return [{"tool": "parent", "child": child, "parent": parent}], {"present": [child, parent]}


def _aim(ctx, ch, _spec=None):
    obj, at = ch.get("object"), ch.get("at")
    _box(ctx, obj, "object")
    _box(ctx, at, "at")
    return [{"tool": "add_constraint", "object": obj, "constraint": "TRACK_TO", "target": at}], {"present": [obj]}


def _targets(ctx, ch):
    """The meshes a finish goes on: the named parts of a built thing, all its parts, or a plain object."""
    name = ch.get("object")
    spec = ctx.specs.get(name)
    if spec is not None:
        return AC._part_names(spec, ch) or [p["name"] for p in spec["parts"]], spec
    _box(ctx, name, "object")
    return [name], None


def _finish(ctx, ch, _spec=None):
    how = _word(ch, "how", FINISH, None)
    names, spec = _targets(ctx, ch)
    calls = []
    for n in names:
        if how == "bevel":
            calls.append({"tool": "add_modifier", "object": n, "modifier": "BEVEL", "width": 0.02, "segments": 3})
        elif how == "subdivide":
            calls.append({"tool": "add_modifier", "object": n, "modifier": "SUBSURF", "levels": 2})
        elif how == "thicken":
            calls.append({"tool": "add_modifier", "object": n, "modifier": "SOLIDIFY", "thickness": 0.05})
        elif how == "wire":
            calls.append({"tool": "add_modifier", "object": n, "modifier": "WIREFRAME", "thickness": 0.02})
        elif how in DEFORM:
            method, angle = DEFORM[how]
            call = {"tool": "add_modifier", "object": n, "modifier": "SIMPLE_DEFORM", "deform_method": method}
            if angle:
                call["angle_deg"] = angle
            calls.append(call)
        elif how == "mirror":
            calls.append({"tool": "add_modifier", "object": n, "modifier": "MIRROR",
                          "axis": ACROSS[_word(ch, "across", ACROSS, "width")]})
        else:
            count = ch.get("count", 3)
            if not isinstance(count, int) or isinstance(count, bool) or not 2 <= count <= 50:
                raise AC.ChangeError("count is a whole number of copies, 2 to 50")
            t = TOWARD[_word(ch, "toward", TOWARD, "right")]
            calls.append({"tool": "add_modifier", "object": n, "modifier": "ARRAY", "count": count,
                          "offset": [float(x) * 1.1 for x in t]})
    if spec is not None:
        for p in spec["parts"]:
            if p["name"] in names:
                p.setdefault("finishes", []).append(how)
    return calls, {"present": names}


def _scene(ctx, ch):
    call = {"tool": "scene_settings"}
    if "background" in ch:
        try:
            call["world_color"] = [round(x, 4) for x in COL.material(ch["background"])["color"][:3]]
        except ValueError as error:
            raise AC.ChangeError(f"background: {error}")
    fps = ch.get("fps")
    if fps is not None:
        if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 120:
            raise AC.ChangeError("fps is a whole number, 1 to 120")
        call["fps"] = fps
    secs = ch.get("seconds")
    if secs is not None:
        if not isinstance(secs, (int, float)) or isinstance(secs, bool) or not 0 < secs <= 600:
            raise AC.ChangeError("seconds is a number, up to 600")
        call["frame_start"], call["frame_end"] = 1, max(2, int(round(secs * (fps or 24))))
    if len(call) == 1:
        raise AC.ChangeError("scene needs background, seconds or fps")
    return [call], {"present": []}


OTHER_TYPES = ("CAMERA", "LIGHT", "FONT")


def is_other(ctx, name):
    return isinstance(name, str) and name not in ctx.specs and any(
        o.get("name") == name and o.get("type") in OTHER_TYPES for o in ctx.scene)


def remove_other(ctx, ch, _spec=None):
    name = ch["object"]
    ctx.scene = [o for o in ctx.scene if o.get("name") != name]
    return [{"tool": "delete_object", "object": name}], {"gone": [name]}


remove_other.no_object = True


OPS = {"camera": _camera, "light": _light, "text": _text, "retext": _retext, "attach": _attach, "aim": _aim,
       "finish": _finish, "scene": _scene}
for _f in OPS.values():          # each looks up its own names: a camera or a text is not a built thing
    _f.no_object = True
