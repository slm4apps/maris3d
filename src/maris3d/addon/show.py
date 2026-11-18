# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender, so it is GPL-3.0-or-later.
"""The scene show in Blender: Maris, 3D messages and their effects.

Everything here is presentation. The rules and
numbers live bpy-free in vendor/show.py (copilot/show.py) and are tested there; this file only
applies them. All objects sit in the `Messages` collection, carry the `copt_show` property, are
skipped by the executor's scene list and face budget, are left out of saved files, and are hidden
from renders unless "Maris in renders" is on. Off in background mode (register skips it).

Panel: a collapsed "Maris" sub-panel; its header checkbox turns the whole show on or off.
"""
import json
import math
import os
import threading
import time
from collections import deque

import bpy

from .vendor import framing
from .vendor import show as core

ADDON = __package__
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maris")
FPS = 24.0
LOOPING = ("idle", "weave", "float")
_S = {"spec": None, "director": None, "msgs": [], "anim": None, "n": 0, "saved": None,
      "design_items": [], "colour_items": None, "busy": False, "toy": None}
_QUEUE = deque(maxlen=200)                 # harness events from the worker thread, drained by tick()
_LOCK = threading.Lock()
_ACTIONS = core.ActionQueue()              # the model's `show` actions, same hand-over


# ---- basics ----------------------------------------------------------------------------------

def spec():
    if _S["spec"] is None:
        with open(os.path.join(ASSET_DIR, "maris.json"), encoding="utf-8") as fh:
            _S["spec"] = json.load(fh)
    return _S["spec"]


def prefs():
    return bpy.context.preferences.addons[ADDON].preferences


def enabled():
    try:
        return not bpy.app.background and prefs().maris_on
    except Exception:
        return False


def designs_path():
    """The user's saved designs, in the add-on's user folder (kept across updates)."""
    try:
        base = bpy.utils.extension_path_user(ADDON, path="", create=True)
    except Exception:
        base = bpy.utils.user_resource("CONFIG", path="maris3d", create=True)
    return os.path.join(base, "maris-designs.json")


def director():
    if _S["director"] is None:
        _S["director"] = core.Director(seed=int(time.time()))
    p = prefs()
    _S["director"].maris, _S["director"].fun_finish = p.maris_on, p.fun_finish
    return _S["director"]


def tag(idblock):
    idblock[core.TAG] = True
    return idblock


def is_show(ob):
    """True for Maris and every message: never scene content."""
    return bool(ob.get(core.TAG)) or core.is_show_name(ob.name)


def collection(create=True):
    coll = bpy.data.collections.get(core.COLLECTION)
    if coll is None and create:
        coll = tag(bpy.data.collections.new(core.COLLECTION))
    if coll is not None:
        scene = bpy.context.scene
        if create and coll.name not in scene.collection.children:
            scene.collection.children.link(coll)
        coll.hide_render = not prefs().maris_in_renders
    return coll


def _scene_box():
    """(min, max) world corners of the user's objects, or None for an empty scene."""
    from mathutils import Vector
    lo, hi = None, None
    for ob in bpy.context.scene.objects:
        if ob.type not in ("MESH", "CURVE", "FONT", "SURFACE", "META") or is_show(ob):
            continue
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            lo = w.copy() if lo is None else Vector(map(min, lo, w))
            hi = w.copy() if hi is None else Vector(map(max, hi, w))
    return (lo, hi) if lo is not None else None


# ---- Maris --------------------------------------------------------------------------------

def rig():
    ob = bpy.data.objects.get(spec()["rig"])
    return ob if ob is not None and ob.name in bpy.context.scene.objects else None


def ensure_maris():
    """The maris in the scene (appended from the shipped maris.blend once), or None when off."""
    if not enabled():
        return None
    r = rig()
    if r is not None:
        return r
    sp = spec()
    with bpy.data.libraries.load(os.path.join(ASSET_DIR, "maris.blend"), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == sp["collection"]]
        dst.actions = [a for a in src.actions if a.startswith(sp["action_prefix"])]
        dst.materials = [m for m in src.materials if m.startswith("maris_")]
    for idb in list(dst.actions) + list(dst.materials):
        if idb is not None:
            idb.use_fake_user = False          # nothing of Maris stays in the user's file
    mc = dst.collections[0]
    tag(mc)
    collection().children.link(mc)
    for ob in mc.all_objects:
        tag(ob)
    r = rig()
    r.animation_data_create()
    r.animation_data.action = None             # the show's timer poses it, not the timeline
    place_maris()
    apply_design(current_design())
    face("happy")
    play("idle")
    return r


def place_maris(spot=None):
    """Beside the scene on the ground, on the camera's right and inside its frame, scaled to the
    scene (framing.landing_spot; no view: the front right corner)."""
    r = rig()
    if r is None:
        return
    box = _scene_box()
    if box is None:
        size, loc = 1.0, (0.0, 0.0, 0.0)
    else:
        lo, hi = box
        size = core.scene_scale(list(hi - lo))
        loc = framing.landing_spot((tuple(lo), tuple(hi)), _eye(), size)
    if spot is not None:
        loc = spot
    r.scale = (size / spec()["height"],) * 3
    r.location = loc


def maris_height():
    r = rig()
    return r.scale.z * spec()["height"] if r is not None else 1.0


def _fcurves(act):
    legacy = getattr(act, "fcurves", None)
    if legacy is not None:
        return list(legacy)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def play(pose):
    """Play one pose action (by the timer, so the scene's own timeline is never touched)."""
    act = bpy.data.actions.get(spec()["action_prefix"] + pose)
    if act is None or rig() is None:
        return
    curves = _fcurves(act)
    end = max((k.co.x for fc in curves for k in fc.keyframe_points), default=1.0)
    _S["anim"] = {"pose": pose, "curves": curves, "t0": time.monotonic(), "end": end}


def _pose_tick(now):
    a, r = _S["anim"], rig()
    if a is None or r is None:
        return
    frame = 1.0 + (now - a["t0"]) * FPS
    if a["pose"] in LOOPING:
        frame = 1.0 + (frame - 1.0) % max(1.0, a["end"] - 1.0)
    elif frame > a["end"] + FPS * 0.6:         # a one-shot pose ends: back to idle
        play("idle")
        return
    for fc in a["curves"]:
        try:
            prop = r.path_resolve(fc.data_path)
            prop[fc.array_index] = fc.evaluate(min(frame, a["end"]))
        except Exception:
            pass


def face(name):
    """Show one of the five faces: one mouth visible, brows lifted and tilted (maris.json)."""
    sp = spec()
    f = sp["faces"].get(name)
    if f is None:
        return
    pre = sp["prefix"]
    from mathutils import Quaternion, Vector
    for m in sp["mouths"]:
        ob = bpy.data.objects.get(pre + "Mouth" + m)
        if ob is not None:
            ob.hide_viewport = ob.hide_render = (m != f["mouth"])
    for side, sign in (("L", 1), ("R", -1)):
        brow = bpy.data.objects.get(pre + "Brow" + side)
        if brow is None or "face_base" not in brow:
            continue
        base = list(brow["face_base"])
        brow.rotation_mode = "QUATERNION"
        brow.location = Vector(base[:3]) + Vector(brow["face_up"]) * f["lift"]
        tilt = Quaternion(Vector(brow["face_front"]), math.radians(f["tilt"] * sign))
        brow.rotation_quaternion = tilt @ Quaternion(base[3:])


def event(name, target=None):
    """A harness event: Maris reacts, rate-limited by the director."""
    if not enabled():
        return
    cue = director().cue(name, time.monotonic(), target)
    if cue is None or ensure_maris() is None:
        return
    face(cue["face"])
    if cue["pose"] == "weave":                 # she starts weaving: a random design gets a new toy
        new_toy(only_random=True)
    play(cue["pose"])


def post(name, info=None):
    """The copilot's listener (loop.Copilot.listeners). It runs in the worker thread, so it only
    queues; tick() (the main thread, outside undo) applies it. Never raises."""
    try:
        if enabled():
            with _LOCK:
                _QUEUE.append((name, dict(info or {})))
    except Exception:
        pass


def post_actions(actions):
    """copilot.show hook (worker thread): the model's checked show lines, queued for tick()."""
    try:
        if enabled():
            _ACTIONS.put(actions)
    except Exception:
        pass


def _apply_steps():
    """Main thread, from tick() (a timer, so outside undo): apply the queued show actions."""
    for step in _ACTIONS.take():
        if step[0] == "clear":
            clear_messages(instant=True)           # the whole Messages collection's contents
        elif step[0] == "pose":
            if ensure_maris() is not None:
                play(step[1])
        elif step[0] == "text":
            say(step[1], effect=step[2], kind=step[3], near=step[4])


def _jump_to(target):
    """Hop to the ground beside a built part (never onto the show's own objects)."""
    from mathutils import Vector
    ob = bpy.data.objects.get(target) if target else None
    if ob is None or is_show(ob) or ob.type not in ("MESH", "CURVE", "SURFACE", "META"):
        return
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = tuple(min(c[k] for c in corners) for k in range(3))
    hi = tuple(max(c[k] for c in corners) for k in range(3))
    place_maris(framing.landing_spot((lo, hi), _eye(), maris_height()))


def _drain():
    with _LOCK:
        items = list(_QUEUE)
        _QUEUE.clear()
    for name, info in items:
        act = core.react(name, info)
        if act is None:
            continue
        cue = director().cue(act["event"], time.monotonic(), act["target"])
        if cue is None or ensure_maris() is None:
            continue
        if act["target"] and act["event"] != "thinking":
            _jump_to(act["target"])
        face(cue["face"])
        if cue["pose"] == "weave":
            new_toy(only_random=True)
        play(cue["pose"])
        if act["say"]:
            say(act["say"], kind=act["kind"], near=None)


# ---- toys ----------------------------------------------------------------------------------------

def set_toy(name):
    """Show one toy and put the thread's end on the line she is weaving."""
    sp = spec()
    coll = bpy.data.collections.get(sp["collection"])
    end = bpy.data.objects.get(sp["prefix"] + "ThreadEnd")
    if coll is None or name not in sp["toys"]:
        return
    for ob in list(coll.all_objects):
        if ob is None or "maris_toy" not in ob:
            continue
        mine = ob["maris_toy"] == name
        ob.hide_viewport = ob.hide_render = not mine
        if mine and end is not None and "thread_end_local" in ob:
            end.location = ob["thread_end_local"]
    _S["toy"] = name


def new_toy(only_random=False):
    """Pick the toy for the worn design (a random mode picks a new one, never the same twice)."""
    design = _S.get("worn") or current_design()
    if only_random and design.get("toy", spec()["default_toy"]) in spec()["toys"]:
        return
    set_toy(core.pick_toy(spec(), design, last=_S["toy"]))


# ---- designs -------------------------------------------------------------------------------------

def _make_material(key, m):
    mat = bpy.data.materials.get(key)
    if mat is None:
        mat = tag(bpy.data.materials.new(key))
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    rgba = (*m["color"][:3], 1.0)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = m.get("roughness", 0.6)
    bsdf.inputs["Metallic"].default_value = m.get("metallic", 0.0)
    bsdf.inputs["Emission Color"].default_value = rgba
    bsdf.inputs["Emission Strength"].default_value = m.get("emission_strength", 0.0)
    bsdf.inputs["Alpha"].default_value = m.get("alpha", 1.0)
    mat.diffuse_color = rgba
    return mat


def current_design():
    """The design being worn: the panel's edit form (live preview) when it is open, else the
    saved choice."""
    wm = bpy.context.window_manager
    form = getattr(wm, "copt_maris", None)
    if form is not None and form.loaded:
        return form_design(form)
    designs = core.all_designs(spec(), designs_path())
    return designs.get(prefs().maris_design) or designs[spec()["default_outfit"]]


def apply_design(design):
    """Wear a design: materials per slot (colours.material, the planner's colour code), the
    outfit's pieces shown, what it replaces hidden."""
    sp = spec()
    if core.design_faults(sp, design):
        return False
    _S["worn"] = design
    mats = core.design_materials(sp, design)
    outfit = sp["outfits"][design["outfit"]]
    hide_all = {h for o in sp["outfits"].values() for h in o["hide"]}
    coll = bpy.data.collections.get(sp["collection"])
    if coll is None:
        return False
    for ob in list(coll.all_objects):       # a snapshot: hiding objects resets all_objects
        if ob is None or ob.type != "MESH":
            continue
        slot = ob.get("maris_slot")
        if slot in mats and ob.data.materials:
            ob.data.materials[0] = _make_material(*mats[slot])
        base = ob.name[len(sp["prefix"]):]
        if "maris_outfit" in ob:
            ob.hide_viewport = ob.hide_render = ob["maris_outfit"] != design["outfit"]
        elif base in hide_all:
            ob.hide_viewport = ob.hide_render = base in outfit["hide"]
    choice = design.get("toy", sp["default_toy"])
    toys = sp["toys"]
    if choice in toys:
        set_toy(choice)
    elif (_S["toy"] not in toys
          or (choice == "random" and toys[_S["toy"]]["theme"] != outfit.get("toy_theme"))):
        new_toy()
    else:
        set_toy(_S["toy"])                     # keep this session's pick (also after a save)
    return True


# ---- messages and effects ------------------------------------------------------------------------

_MSG_MAT = "msg_text"


def _text_material():
    mat = bpy.data.materials.get(_MSG_MAT)
    if mat is None:
        from .vendor import colours
        mat = _make_material(_MSG_MAT, dict(colours.material({"name": "ivory"}), emission_strength=0.6))
    return mat


def say(text, effect=None, kind="say", near=None):
    """Put a line of 3D text in the scene (by Maris, or near a named object)."""
    if not enabled() or not text.strip():
        return None
    effect = effect if effect in core.EFFECTS else core.DEFAULT_EFFECT.get(kind, "type")
    coll = collection()
    _S["n"] += 1
    name = core.msg_name(kind, _S["n"])
    cu = tag(bpy.data.curves.new(name, "FONT"))
    cu.body = text
    cu.align_x, cu.align_y = "CENTER", "BOTTOM"
    h = maris_height()
    cu.size = h * 0.18
    cu.extrude = h * 0.01
    ob = tag(bpy.data.objects.new(name, cu))
    ob.data.materials.append(_text_material())
    coll.objects.link(ob)
    from mathutils import Vector
    anchor = bpy.data.objects.get(near) if near else rig()
    feet = tuple(anchor.matrix_world.translation) if anchor is not None else (0.0, 0.0, 0.0)
    stacked = sum(1 for m in _S["msgs"] if not m["removing"])
    base = Vector(framing.message_spot(feet, h, _eye(), stacked))
    _S["msgs"].append({"name": name, "text": text, "effect": effect, "t0": time.monotonic(),
                       "base": base, "height": h, "removing": False})
    _apply_effect(_S["msgs"][-1], time.monotonic())
    return name


def clear_messages(instant=False):
    """Remove every message (end of task, reset, New request, the button, `clear messages`).
    The maris stays; it goes only when the switch is turned off."""
    for m in _S["msgs"]:
        if not m["removing"]:
            m.update(removing=True, effect="dissolve", t0=time.monotonic())
    if instant or not prefs().effects:
        for m in list(_S["msgs"]):
            _remove_msg(m)
    coll = collection(create=False)
    if coll is not None and instant:
        for ob in list(coll.objects):
            if ob.name.startswith(core.PREFIX):
                data = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                if data is not None and data.users == 0:
                    bpy.data.curves.remove(data)


def _remove_msg(m):
    ob = bpy.data.objects.get(m["name"])
    if ob is not None:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.curves.remove(data)
    if m in _S["msgs"]:
        _S["msgs"].remove(m)


def _region_3d():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    return area.spaces.active.region_3d
    except Exception:
        pass
    return None


def _view_rotation():
    """The 3D view's rotation; no view (headless, a render): the scene camera's."""
    r3d = _region_3d()
    if r3d is not None:
        return r3d.view_rotation
    cam = bpy.context.scene.camera
    return cam.matrix_world.to_quaternion() if cam is not None else None


def _eye():
    """Where the viewer is: the 3D view's eye, else the scene camera, else None."""
    r3d = _region_3d()
    if r3d is not None:
        return tuple(r3d.view_matrix.inverted().translation)
    cam = bpy.context.scene.camera
    return tuple(cam.matrix_world.translation) if cam is not None else None


def _apply_effect(m, now):
    ob = bpy.data.objects.get(m["name"])
    if ob is None:
        if m in _S["msgs"]:
            _S["msgs"].remove(m)
        return
    f = core.effect_frame(m["effect"], now - m["t0"], len(m["text"]), motion=prefs().effects)
    if f["done"]:
        if m["removing"]:
            _remove_msg(m)
            return
        if m["effect"] != "float" and prefs().effects:
            m.update(effect="float", t0=now)
    shown = m["text"][:f["chars"]]
    if ob.data.body != shown:
        ob.data.body = shown
    ob.scale = (max(f["scale"], 1e-3),) * 3
    ob.location = m["base"].copy()
    ob.location.z += f["lift"] * m["height"] * 0.5
    rot = _view_rotation()
    if rot is not None:                        # texts face the view
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = rot


def intro():
    """Start-up / "Say hi": Maris rises, waves, says hi, then a hint."""
    if ensure_maris() is None:
        return
    face("happy")
    new_toy(only_random=True)
    play("rise")
    say("Hi, I'm Maris", kind="intro")
    bpy.app.timers.register(lambda: (play("wave"), None)[1], first_interval=1.0)
    bpy.app.timers.register(lambda: (say("Type a sentence below", kind="say"), None)[1],
                            first_interval=2.2)


def remove_all():
    """The switch went off: Maris, its materials and every message leave the file."""
    clear_messages(instant=True)
    _S["anim"] = None
    sp = spec()
    coll = bpy.data.collections.get(sp["collection"])
    if coll is not None:
        for ob in list(coll.all_objects):
            data = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if data is not None and data.users == 0:
                for kind in (bpy.data.meshes, bpy.data.curves, bpy.data.armatures):
                    if data.name in kind and kind[data.name] == data:
                        kind.remove(data)
                        break
        bpy.data.collections.remove(coll)
    top = bpy.data.collections.get(core.COLLECTION)
    if top is not None:
        bpy.data.collections.remove(top)
    for act in list(bpy.data.actions):
        if act.name.startswith(sp["action_prefix"]) and act.users == 0:
            bpy.data.actions.remove(act)
    for mat in list(bpy.data.materials):
        if mat.name.startswith(("maris_", "norn_", "msg_")) and mat.users == 0:
            bpy.data.materials.remove(mat)


def tick():
    """The one show timer: poses and effects at 30 fps while something moves, slow otherwise."""
    if not enabled():
        return 0.5
    now = time.monotonic()
    try:
        _drain()
        _apply_steps()
        _pose_tick(now)
        for m in list(_S["msgs"]):
            _apply_effect(m, now)
    except ReferenceError:                     # undo / file load removed something: start clean
        _S["msgs"].clear()
        _S["anim"] = None
    return 1 / 30 if (_S["anim"] or _S["msgs"] or _QUEUE or len(_ACTIONS)) else 0.5


# ---- files: never in the user's work -------------------------------------------------------------

@bpy.app.handlers.persistent
def _save_pre(_=None):
    """Blender writes every datablock that still has users, so the show leaves the file
    completely before a save and comes back after it (same design, pose and messages)."""
    if bpy.data.collections.get(core.COLLECTION) is None:
        _S["saved"] = None
        return
    r = rig()
    _S["saved"] = {
        "maris": r is not None,
        "design": _S.get("worn"),
        "where": (tuple(r.location), tuple(r.scale)) if r is not None else None,
        "pose": (_S["anim"] or {}).get("pose", "idle"),
        "msgs": [dict(m, base=tuple(m["base"])) for m in _S["msgs"] if not m["removing"]],
    }
    remove_all()


@bpy.app.handlers.persistent
def _save_post(_=None):
    saved, _S["saved"] = _S.get("saved"), None
    if not saved or not enabled():
        return
    from mathutils import Vector
    if saved["maris"] and ensure_maris() is not None:
        r = rig()
        r.location, r.scale = saved["where"]
        if saved["design"]:
            apply_design(saved["design"])
        play(saved["pose"])
    for m in saved["msgs"]:
        name = say(m["text"], m["effect"] if m["effect"] != "float" else "fade")
        if name:
            _S["msgs"][-1].update(base=Vector(m["base"]), t0=time.monotonic() - 60.0)


@bpy.app.handlers.persistent
def _load_post(_=None):
    _S["msgs"].clear()
    _S["anim"] = None


# ---- panel ---------------------------------------------------------------------------------------

def _colour_items(_self, _ctx):
    if _S["colour_items"] is None:
        from .vendor import colours
        _S["colour_items"] = [("DEFAULT", "(design)", "Keep the design's colour")] + [
            (n, n.replace("_", " "), "") for n in colours.COLOUR_NAMES]
    return _S["colour_items"]


def _shade_items(_self, _ctx):
    from .vendor import colours
    return [("NONE", "-", "No shade")] + [(s.upper(), s, "") for s in colours.SHADES]


def _look_items(_self, _ctx):
    from .vendor import colours
    return [("NONE", "-", "The colour's own surface")] + [(k.upper(), k, "") for k in colours.LOOKS]


def _design_items(_self, _ctx):
    items = []
    try:
        designs = core.all_designs(spec(), designs_path())
    except Exception:
        designs = {}
    for key, d in designs.items():
        mine = key not in spec()["outfits"]
        items.append((key, d["label"], "Your saved design" if mine else "Shipped design"))
    _S["design_items"] = items or [("sea", "Sea", "")]
    return _S["design_items"]


def _outfit_items(_self, _ctx):
    return [(k, o["label"], o["about"]) for k, o in spec()["outfits"].items()]


def _skin_items(_self, _ctx):
    return [(k, k.replace("_", " "), "") for k in spec()["skins"]]


def _hair_items(_self, _ctx):
    return [(k, k.replace("_", " "), "") for k in spec()["hairs"]]


def _toy_items(_self, _ctx):
    if _S.get("toy_items") is None:            # Blender needs the item strings kept alive
        sp = spec()
        _S["toy_items"] = ([(k, t["label"], t["about"]) for k, t in sp["toys"].items()]
                           + [(k, label, "A new toy each time she starts weaving")
                              for k, label in sp["toy_choices"].items()])
    return _S["toy_items"]


def _live(_self=None, _ctx=None):
    form = bpy.context.window_manager.copt_maris
    if form.loaded and not _S["busy"] and rig() is not None:
        apply_design(form_design(form))


class COPT_MarisSlot(bpy.types.PropertyGroup):
    slot: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    colour: bpy.props.EnumProperty(name="Colour", items=_colour_items, update=_live,
                                   description="Any colour the planner and edit model use")
    shade: bpy.props.EnumProperty(name="Shade", items=_shade_items, update=_live)
    look: bpy.props.EnumProperty(name="Look", items=_look_items, update=_live)


class COPT_MarisForm(bpy.types.PropertyGroup):
    loaded: bpy.props.BoolProperty(default=False)
    label: bpy.props.StringProperty(name="Name", default="My Maris")
    outfit: bpy.props.EnumProperty(name="Outfit", items=_outfit_items, update=_live)
    skin: bpy.props.EnumProperty(name="Skin", items=_skin_items, update=_live)
    hair: bpy.props.EnumProperty(name="Hair", items=_hair_items, update=_live)
    toy: bpy.props.EnumProperty(name="Toy", items=_toy_items, update=_live,
                                description="What she weaves: one toy, or random")
    slots: bpy.props.CollectionProperty(type=COPT_MarisSlot)
    show_parts: bpy.props.BoolProperty(name="Colours per part", default=False)


def form_design(form):
    cols = {}
    for s in form.slots:
        if s.colour == "DEFAULT":
            continue
        ans = {"name": s.colour}
        if s.shade != "NONE":
            ans["shade"] = s.shade.lower()
        if s.look != "NONE":
            ans["look"] = s.look.lower()
        cols[s.slot] = ans if len(ans) > 1 else s.colour
    return {"label": form.label.strip() or "My Maris", "outfit": form.outfit, "skin": form.skin,
            "hair": form.hair, "toy": form.toy, "colours": cols}


def load_form(design):
    """Fill the edit form from a design (the panel's dropdown choice)."""
    form = bpy.context.window_manager.copt_maris
    _S["busy"] = True
    try:
        form.label = design["label"]
        form.outfit = design["outfit"]
        form.skin = design["skin"]
        form.hair = design.get("hair", spec()["default_hair"])
        form.toy = design.get("toy", spec()["default_toy"])
        form.slots.clear()
        for slot, info in spec()["slots"].items():
            item = form.slots.add()
            item.slot, item.label = slot, info["label"]
            ans = design.get("colours", {}).get(slot)
            name = ans if isinstance(ans, str) else (ans or {}).get("name")
            item.colour = name if name in [i[0] for i in _colour_items(None, None)] else "DEFAULT"
            if isinstance(ans, dict):
                item.shade = (ans.get("shade") or "none").upper() if ans.get("shade") else "NONE"
                item.look = (ans.get("look") or "none").upper() if ans.get("look") else "NONE"
        form.loaded = True
    finally:
        _S["busy"] = False


def on_design_chosen(p, _ctx=None):
    designs = core.all_designs(spec(), designs_path())
    d = designs.get(p.maris_design)
    if d is not None:
        load_form(d)
        _live()


def on_switch(p, _ctx=None):
    if p.maris_on:
        bpy.app.timers.register(lambda: (intro(), None)[1], first_interval=0.1)
    else:
        bpy.app.timers.register(lambda: (remove_all(), None)[1], first_interval=0.05)


def on_render_switch(p, _ctx=None):
    coll = bpy.data.collections.get(core.COLLECTION)
    if coll is not None:
        coll.hide_render = not p.maris_in_renders


class COPT_OT_say_hi(bpy.types.Operator):
    bl_idname, bl_label = "copt.say_hi", "Say hi"
    bl_description = "Play Maris's hello again"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        intro()
        return {"FINISHED"}


class COPT_OT_clear_messages(bpy.types.Operator):
    bl_idname, bl_label = "copt.clear_messages", "Clear messages"
    bl_description = "Remove every message from the scene (Maris stays)"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        clear_messages()
        return {"FINISHED"}


class COPT_OT_maris_save(bpy.types.Operator):
    bl_idname, bl_label = "copt.maris_save", "Save design"
    bl_description = "Save this look under its name; it is listed next to the shipped designs"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        form = context.window_manager.copt_maris
        design = form_design(form)
        current = prefs().maris_design
        mine = current not in spec()["outfits"]
        same_name = mine and core.all_designs(spec(), designs_path()).get(current, {}).get("label") == design["label"]
        try:
            key = core.save_user_design(designs_path(), spec(), design, name=current if same_name else None)
        except ValueError as e:
            self.report({"ERROR"}, f"Not saved: {e}")
            return {"CANCELLED"}
        _design_items(None, None)
        prefs().maris_design = key
        self.report({"INFO"}, f"Saved design '{design['label']}'")
        return {"FINISHED"}


class COPT_OT_maris_delete(bpy.types.Operator):
    bl_idname, bl_label = "copt.maris_delete", "Delete design"
    bl_description = "Delete this saved design (shipped designs stay)"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return prefs().maris_design not in spec()["outfits"]

    def execute(self, context):
        core.delete_user_design(designs_path(), spec(), prefs().maris_design)
        prefs().maris_design = spec()["default_outfit"]
        return {"FINISHED"}


class COPT_OT_maris_reset(bpy.types.Operator):
    bl_idname, bl_label = "copt.maris_reset", "Undo changes"
    bl_description = "Go back to the chosen design as saved"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        on_design_chosen(prefs())
        return {"FINISHED"}


class COPT_PT_maris(bpy.types.Panel):
    bl_label = "Maris"
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Maris3D Copilot"
    bl_parent_id = "COPT_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(prefs(), "maris_on", text="")

    def draw(self, context):
        p = prefs()
        col = self.layout.column(align=True)
        col.active = p.maris_on
        col.prop(p, "maris_design", text="Design")
        row = col.row(align=True)
        row.operator("copt.say_hi", icon="OUTLINER_OB_ARMATURE")
        row.operator("copt.clear_messages", icon="TRASH")
        col.separator()
        col.prop(p, "fun_finish")
        col.prop(p, "effects")
        col.prop(p, "maris_in_renders")
        form = context.window_manager.copt_maris
        if not form.loaded:
            col.operator("copt.maris_reset", text="Customise", icon="BRUSH_DATA")
            return
        box = col.box()
        box.prop(form, "label")
        box.prop(form, "outfit")
        box.prop(form, "skin")
        box.prop(form, "hair")
        box.prop(form, "toy")
        box.prop(form, "show_parts", icon="TRIA_DOWN" if form.show_parts else "TRIA_RIGHT",
                 emboss=False)
        if form.show_parts:
            for item in form.slots:
                row = box.row(align=True)
                row.label(text=item.label)
                row.prop(item, "colour", text="")
                row.prop(item, "shade", text="")
                row.prop(item, "look", text="")
        row = box.row(align=True)
        row.operator("copt.maris_save", icon="FILE_TICK")
        row.operator("copt.maris_reset", icon="LOOP_BACK")
        row.operator("copt.maris_delete", text="", icon="X")


CLASSES = (COPT_MarisSlot, COPT_MarisForm, COPT_OT_say_hi, COPT_OT_clear_messages,
           COPT_OT_maris_save, COPT_OT_maris_delete, COPT_OT_maris_reset, COPT_PT_maris)


def pref_props():
    """The switches, kept in the add-on preferences (so they persist). Added to the preferences
    class by __init__."""
    return {
        "maris_on": bpy.props.BoolProperty(
            name="Maris", default=True, update=on_switch,
            description="Maris and her messages in the scene. Off removes them"),
        "fun_finish": bpy.props.BoolProperty(
            name="Fun finish", default=True, description="A little celebration when a task is done"),
        "effects": bpy.props.BoolProperty(
            name="Effects", default=True, description="Off: plain text, no motion"),
        "maris_in_renders": bpy.props.BoolProperty(
            name="Maris in renders", default=False, update=on_render_switch,
            description="Off: Maris and messages never show in renders"),
        "maris_design": bpy.props.EnumProperty(
            name="Design", items=_design_items, update=on_design_chosen,
            description="The three shipped looks and the ones you saved"),
    }


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.copt_maris = bpy.props.PointerProperty(type=COPT_MarisForm)
    bpy.app.timers.register(tick, persistent=True, first_interval=1.0)
    bpy.app.handlers.save_pre.append(_save_pre)
    bpy.app.handlers.save_post.append(_save_post)
    bpy.app.handlers.load_post.append(_load_post)


def unregister():
    try:
        bpy.app.timers.unregister(tick)
    except Exception:
        pass
    for lst, fn in ((bpy.app.handlers.save_pre, _save_pre), (bpy.app.handlers.save_post, _save_post),
                    (bpy.app.handlers.load_post, _load_post)):
        if fn in lst:
            lst.remove(fn)
    del bpy.types.WindowManager.copt_maris
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
