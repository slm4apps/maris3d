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
SIT_POSES = ("sit", "sit_seat")
SIT_HOLD = 3.0                             # seconds she stays seated before standing up
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
    # a rig (or her collection) left in the file but out of the scene would take the shipped name,
    # and the fresh copy would load as "Maris_Rig.001", which rig() never finds (save_post broke)
    old = bpy.data.objects.get(sp["rig"])
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    old = bpy.data.collections.get(sp["collection"])
    if old is not None:
        for ob in list(old.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(old)
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
    if r is None:
        return None
    r.animation_data_create()
    r.animation_data.action = None             # the show's timer poses it, not the timeline
    place_maris()
    apply_design(current_design())
    face("happy")
    play(idle())
    return r


def _user_boxes():
    """(name, world box) of the user's visible things (not the show's)."""
    out = []
    for ob in bpy.context.scene.objects:
        if ob.type not in ("MESH", "CURVE", "FONT", "SURFACE", "META") or is_show(ob):
            continue
        if ob.name in _C["hidden"] or not ob.visible_get():
            continue
        box = _world_box([ob])
        if box is not None:
            out.append((ob.name, box))
    return out


def _dims(box):
    return [box[1][k] - box[0][k] for k in range(3)]


def _grounds(height=None):
    """World boxes of the wide flat things she stands on (snow, a floor, a path)."""
    h = maris_height() if height is None else height
    return [b for _n, b in _user_boxes() if core.is_ground(_dims(b), h)]


def ground_z(x, y, fallback):
    """Her feet's height at (x, y): the top of the ground there, else `fallback` (the part's
    bottom, as before there was any ground)."""
    top = core.ground_top(_grounds(), x, y)
    return fallback if top is None else top


def _person_size():
    """Her height here: like a person next to what is built (core.person_height); only ground or
    an empty scene keeps the height she has."""
    cur = maris_height() if rig() is not None else 1.0
    tall = max((_dims(b)[2] for _n, b in _user_boxes() if not core.is_ground(_dims(b), cur)), default=0.0)
    return core.person_height(tall, cur)


def _onto_ground(loc, h):
    """A spot off every ground (beside a scene that is only a floor): just inside the nearest
    ground's edge instead, so she stands on it, never in the air beside it."""
    grounds = _grounds(h)
    if not grounds or core.ground_top(grounds, loc[0], loc[1]) is not None:
        return loc
    g = min(grounds, key=lambda b: math.hypot(loc[0] - (b[0][0] + b[1][0]) / 2, loc[1] - (b[0][1] + b[1][1]) / 2))
    x, y, _z = core.rim_spot(g, loc, h, out=-0.6)
    return (x, y, g[1][2])


def place_maris(spot=None):
    """Beside the scene on the ground, on the camera's right and inside its frame, sized like a
    person next to what is built (framing.landing_spot; no view: the front right corner). Her feet
    go on top of the ground under her, never inside a floor slab or in the air."""
    r = rig()
    if r is None:
        return
    size = _person_size()
    box = _scene_box()
    if box is None:
        loc = (0.0, 0.0, 0.0)
    else:
        lo, hi = box
        loc = framing.landing_spot((tuple(lo), tuple(hi)), _eye(), size)
    if spot is not None:
        loc = spot
    else:
        loc = _onto_ground(loc, size)
    r.scale = (size / spec()["height"],) * 3
    r.location = (loc[0], loc[1], ground_z(loc[0], loc[1], loc[2]))


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


def idle():
    """The worn outfit's resting loop (the ninja's never stands still)."""
    design = _S.get("worn") or current_design()
    return core.idle_pose(spec(), design["outfit"])


def play(pose):
    """Play one pose action (by the timer, so the scene's own timeline is never touched), with
    the pose's pieces shown (seated skirt, tool) and what it hides hidden."""
    if pose == "idle":
        pose = idle()
    act = bpy.data.actions.get(spec()["action_prefix"] + pose)
    if act is None or rig() is None:
        return
    if pose not in SIT_POSES:
        _stand_up()
    curves = _fcurves(act)
    end = max((k.co.x for fc in curves for k in fc.keyframe_points), default=1.0)
    _S["anim"] = {"pose": pose, "curves": curves, "t0": time.monotonic(), "end": end}
    refresh_visibility(pose)


def cue_pose(pose):
    """A reaction's pose: "sit" sits on a seat near her when there is one."""
    if pose in SIT_POSES:
        sit()
    else:
        play(pose)


def _pose_tick(now):
    a, r = _S["anim"], rig()
    if a is None or r is None:
        return
    frame = 1.0 + (now - a["t0"]) * FPS
    hold = SIT_HOLD if a["pose"] in SIT_POSES else 0.6
    if a["pose"] in core.looping(spec()):
        frame = 1.0 + (frame - 1.0) % max(1.0, a["end"] - 1.0)
    elif frame > a["end"] + FPS * hold and not carrying():   # a one-shot pose ends: back to idle
        play(idle())
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
    cue_pose(cue["pose"])


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
    look_at(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))


def _drain():
    carry_scan()                               # parts made before these events: carried, no hop
    with _LOCK:
        items = list(_QUEUE)
        _QUEUE.clear()
    for name, info in items:
        if name == "request":
            clear_messages()                   # a new request: the last one's lines dissolve
            carry_begin()
        elif name in ("done", "error"):
            carry_end(drop=name == "error")
        act = core.react(name, info)
        if act is None:
            continue
        cue = director().cue(act["event"], time.monotonic(), act["target"])
        if cue is None or ensure_maris() is None:
            continue
        if carrying():                         # busy carrying: a face only; the finish waits
            face(cue["face"])
            if name == "done":
                _C["after"] = (cue, act)
            continue
        _show_cue(cue, act)


def look_at(point):
    """What she turns to (smoothly, in tick) when she is not running or sitting: a world point,
    "eye" (the viewer), or None (stay as she is)."""
    _S["face_pt"] = point


def _face_tick():
    pt = _S.get("face_pt")
    r = rig()
    a = _S.get("anim") or {}
    if pt is None or r is None or carrying() or a.get("pose") in SIT_POSES + ("run",):
        return
    if pt == "eye":
        pt = _eye()
        if pt is None:
            return
    dx, dy = pt[0] - r.location.x, pt[1] - r.location.y
    if dx * dx + dy * dy < 1e-6:
        return
    want = core.yaw_to(dx, dy)
    r.rotation_euler = (0, 0, core.turn_step(r.rotation_euler.z, want))


def _show_cue(cue, act):
    if act["target"] and act["event"] != "thinking":
        _jump_to(act["target"])
    elif act.get("say"):
        look_at("eye")                        # talking to you: she turns to the view
    face(cue["face"])
    if cue["pose"] == "weave":
        new_toy(only_random=True)
    cue_pose(cue["pose"])
    if act["say"]:
        say(act["say"], kind=act["kind"], near=None)


# ---- sitting: on a seat near her, else on the ground ---------------------------------------------

def _world_box(obs):
    from mathutils import Vector
    pts = [ob.matrix_world @ Vector(c) for ob in obs for c in ob.bound_box]
    if not pts:
        return None
    return (tuple(min(p[k] for p in pts) for k in range(3)), tuple(max(p[k] for p in pts) for k in range(3)))


def _solid_parts(ob):
    """The meshes of a thing: itself and its descendants (a Chair empty with its parts)."""
    out = [ob] + list(getattr(ob, "children_recursive", ()))
    return [o for o in out if o.type in ("MESH", "CURVE", "SURFACE", "META") and not is_show(o)]


def _top(obs, x, y, z_from):
    """Highest surface of obs under (x, y), cast down from z_from; None if nothing is there."""
    from mathutils import Vector
    dg = bpy.context.evaluated_depsgraph_get()
    best = None
    for ob in obs:
        if ob.type != "MESH":
            continue
        inv = ob.matrix_world.inverted()
        origin = inv @ Vector((x, y, z_from))
        direction = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
        try:
            hit, loc, _n, _i = ob.ray_cast(origin, direction, depsgraph=dg)
        except Exception:
            continue
        if hit:
            z = (ob.matrix_world @ loc).z
            best = z if best is None else max(best, z)
    return best


SEAT_REACH = 12          # seats this many of her heights away are in reach (she runs to them)


def _find_seat():
    """(location, height, yaw) to sit on the nearest seat within reach (she runs there), or None."""
    from mathutils import Vector
    r = rig()
    h = maris_height()
    here = Vector(r.location)
    best = None
    for ob in bpy.context.scene.objects:
        if is_show(ob) or not core.is_seat_name(ob.name):
            continue
        if ob.parent is not None and core.is_seat_name(ob.parent.name):
            continue                               # its group is the seat
        parts = _solid_parts(ob)
        box = _world_box(parts) if parts else None
        if box is None:
            continue
        lo, hi = box
        c = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
        dist = (c.xy - here.xy).length
        if dist <= SEAT_REACH * h and (best is None or dist < best[0]):
            best = (dist, parts, lo, hi)
    if best is None:
        return None
    _d, parts, lo, hi = best
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    # a seat board on separate legs: its height counts from the ground (or the scene's floor), not
    # from the board's own bottom
    scene = _scene_box()
    floor = ground_z(cx, cy, scene[0][2] if scene is not None else lo[2])
    lo = (lo[0], lo[1], min(lo[2], floor))
    z_from = hi[2] + 0.01
    seat = _top(parts, cx, cy, z_from)
    if seat is None:
        return None
    size = core.seat_scale(spec(), seat - lo[2], h)
    if size is None:
        return None
    wx, wy = (hi[0] - lo[0]) * 0.4, (hi[1] - lo[1]) * 0.4
    sides = [((dx, dy), _top(parts, cx + dx, cy + dy, z_from))
             for dx, dy in ((wx, 0), (-wx, 0), (0, wy), (0, -wy))]
    facing = core.seat_facing(seat, sides, seat - lo[2])
    if facing is None:
        eye = _eye()
        d = Vector((eye[0] - cx, eye[1] - cy)) if eye is not None else Vector((0, -1))
        facing = tuple(d.normalized()) if d.length > 1e-6 else (0, -1)
    reach = abs(facing[0]) * wx + abs(facing[1]) * wy
    shift = min(0.1 * size, 0.3 * reach)           # a little toward the front edge
    spot = (cx + facing[0] * shift, cy + facing[1] * shift, seat - spec()["sitting"]["lap_under"] * size)
    return spot, size, core.yaw_to(*facing)


def sit(walk=True):
    """Sit: on a chair, bench, sofa or stool near her (she runs to it first, then sits on its seat,
    facing away from its back, sized so her feet reach the floor), else on the ground with her
    skirt around her."""
    r = rig()
    if r is None:
        return
    _stand_up()
    seat = None
    try:
        seat = _find_seat()
    except Exception:
        seat = None
    if seat is None:
        play("sit")
        return
    spot, size, yaw = seat
    front = (spot[0] + math.sin(yaw) * 0.45 * size, spot[1] - math.cos(yaw) * 0.45 * size)   # her front is (sin, -cos)
    here = r.location
    if walk and math.hypot(front[0] - here.x, front[1] - here.y) > 0.6 * maris_height() and _carry_wanted():
        _C["jobs"].append({"kind": "go", "to": front, "then": "sit"})   # she runs there first
        return
    _sit_on(seat)


def _sit_on(seat):
    r = rig()
    if r is None:
        return
    _S["stand"] = (tuple(r.location), tuple(r.scale), tuple(r.rotation_euler))
    spot, size, yaw = seat
    r.location = spot
    r.scale = (size / spec()["height"],) * 3
    r.rotation_euler = (0, 0, yaw)
    play("sit_seat")


def _stand_up():
    """Back to where she stood before sitting on a seat."""
    stand, _S["stand"] = _S.get("stand"), None
    r = rig()
    if stand and r is not None:
        r.location, r.scale, r.rotation_euler = stand


# ---- carry: she brings each new part to its place (core: the route and the times) ----------------

_C = {"on": False, "known": set(), "jobs": deque(), "cur": None, "hidden": set(), "after": None,
      "ghosts": set(), "rng": None, "grow": deque(), "growing": [], "moving": {}, "where": {}}


def carrying():
    return bool(_C["cur"] or _C["jobs"] or _C["grow"] or _C["growing"])


def _carry_wanted():
    try:
        return prefs().carry_parts and enabled() and rig() is not None
    except Exception:
        return False


def _part_like(ob):
    return ob.type in ("MESH", "CURVE", "SURFACE", "META", "FONT") and not is_show(ob)


def carry_begin():
    """A request starts: everything there now is old; parts made from here on get carried."""
    _C["known"] = {ob.name for ob in bpy.context.scene.objects}
    _C["where"] = {ob.name: tuple(ob.matrix_world.translation) for ob in bpy.context.scene.objects
                   if ob.parent is None and _part_like(ob)}
    _C["on"] = True


def carry_end(drop=False):
    """The request ended: pick up its last parts too (an error: put every part in place now)."""
    carry_scan()
    _C["on"] = False
    if drop:
        carry_reset()
        return
    _scan_moves()


def _scan_moves():
    """Things the request moved (by the same amount, far enough): she carries each group whole
    from where it was to where it is now. Off with Carry parts."""
    before, _C["where"] = _C.get("where") or {}, {}
    if not _carry_wanted() or not before:
        return
    after = {ob.name: tuple(ob.matrix_world.translation) for ob in bpy.context.scene.objects
             if ob.name in before and ob.parent is None}
    h = maris_height()
    for delta, names in core.moved_groups(before, after, h).items():
        obs = [bpy.data.objects[n] for n in names]
        box = _world_box(obs)
        if box is None or max(_dims(box)) > core.CARRY_MAX_SIZE * h:
            continue
        for ob in obs:                         # back where it was until she brings it
            ob.location = ob.location - _vec(delta)
        _C["moving"][tuple(names)] = delta
        _C["jobs"].append({"kind": "move", "names": names, "delta": delta})


def _vec(t):
    from mathutils import Vector
    return Vector(t)


def carry_scan():
    """New parts since the request began: hidden until she has brought them in."""
    if not _C["on"]:
        return
    want = _carry_wanted()
    for ob in bpy.context.scene.objects:
        if ob.name in _C["known"] or is_show(ob):
            continue
        _C["known"].add(ob.name)
        if not want or not _part_like(ob):
            continue
        box = _world_box([ob])
        size = max(box[1][k] - box[0][k] for k in range(3)) if box else 0.0
        h = maris_height()
        others = [b for n, b in _user_boxes() if n != ob.name and not core.is_ground(_dims(b), h)]
        attached = box is not None and core.attached_to(box, others, h)
        choice = core.carry_choice(ob.type, ob.parent is not None, bool(ob.children), size,
                                   h, len(_C["jobs"]), attached=attached)
        if choice == "carry":
            _hide(ob, True)
            _C["jobs"].append(ob.name)
        elif choice == "grow":
            _hide(ob, True)
            _C["grow"].append(ob.name)
        else:
            _watch(ob, box)


def _watch(ob, box):
    """Not a clear case to carry: she turns to it and has a look (at most every 1.5 s)."""
    now = time.monotonic()
    if carrying() or box is None or now - _C.get("watched", 0.0) < 1.5:
        return
    _C["watched"] = now
    r = rig()
    if r is not None:
        _turn_to(r, (box[0][0] + box[1][0]) / 2, (box[0][1] + box[1][1]) / 2)
        play("inspect")


def _hide(ob, hidden):
    try:
        ob.hide_set(hidden)
    except Exception:
        pass                                   # not in this view layer
    (_C["hidden"].add if hidden else _C["hidden"].discard)(ob.name)


def carry_pause(running):
    """executor.AROUND_JOB: while a harness job runs, the parts she has not brought in yet are
    visible (tool code selects them, checks ray-cast them); hidden again after."""
    for name in list(_C["hidden"]):
        ob = bpy.data.objects.get(name)
        if ob is None:
            _C["hidden"].discard(name)
            continue
        try:
            ob.hide_set(not running)
        except Exception:
            pass


def _drop_ghost(job):
    name = job.get("ghost") if job else None
    g = bpy.data.objects.get(name) if name else None
    if g is not None:
        bpy.data.objects.remove(g, do_unlink=True)
    if name:
        _C["ghosts"].discard(name)


def _show_maris(shown):
    coll = bpy.data.collections.get(spec()["collection"])
    if coll is not None and coll.hide_viewport == shown:
        coll.hide_viewport = not shown


def carry_reset():
    """Every part she has not placed yet goes in place now; ghosts go; she stands."""
    cur = _C["cur"]
    _drop_ghost(cur)
    for name in list(_C["ghosts"]):
        g = bpy.data.objects.get(name)
        if g is not None:
            bpy.data.objects.remove(g, do_unlink=True)
    for name in list(_C["hidden"]):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            _hide(ob, False)
    for names, delta in list(_C["moving"].items()):   # a group she was moving: at its new place
        job = cur if cur and cur.get("kind") == "move" and tuple(cur["names"]) == names and "base" in cur else None
        for n in names:
            ob = bpy.data.objects.get(n)
            if ob is None:
                continue
            if job is not None:
                ob.location = job["base"][n] + _vec(delta)
            else:
                ob.location = ob.location + _vec(delta)
    _carry_forget()
    try:
        _show_maris(True)
        r = rig()
        if r is not None and cur:              # a reset mid-poof: her full size back
            r.scale = (cur["h"] / spec()["height"],) * 3
    except (ReferenceError, AttributeError):
        pass


def _carry_forget():
    _C.update(on=False, cur=None, after=None)
    _C["jobs"].clear()
    _C["grow"].clear()
    _C["growing"] = []
    _C["moving"] = {}
    _C["hidden"].clear()
    _C["ghosts"].clear()


def _obstacles(skip):
    """World boxes of the user's things she may run into (not the part she carries)."""
    out = []
    for ob in bpy.context.scene.objects:
        if ob.name in skip or ob.name in _C["hidden"] or not _part_like(ob) or not ob.visible_get():
            continue
        box = _world_box([ob])
        if box is not None:
            out.append(box)
    return out


def _turn_to(r, x, y):
    dx, dy = x - r.location.x, y - r.location.y
    if dx * dx + dy * dy > 1e-8:
        r.rotation_euler = (0, 0, core.yaw_to(dx, dy))


def _start_job(name, now):
    """Pop in where the part pops in, grab it; plan the dash to its place."""
    from mathutils import Vector
    ob = bpy.data.objects.get(name)
    r = rig()
    if ob is None or r is None:
        return None
    if _C["rng"] is None:
        import random
        _C["rng"] = random.Random(int(now * 1000))
    rng, h = _C["rng"], maris_height()
    box = _world_box([ob])
    lo, hi = box
    centre = Vector([(lo[k] + hi[k]) / 2 for k in range(3)])
    others = _obstacles({name})
    goal = core.free_spot(framing.landing_spot((lo, hi), _eye(), h), h, others + [box])
    grounds = _grounds(h)
    if grounds:                                # from the edge of the ground she stands on, on it
        g = max(grounds, key=lambda b: _dims(b)[0] * _dims(b)[1])
        start = core.rim_spot(g, (centre.x, centre.y, lo[2]), h, _eye(), rng, out=-0.3)
    else:
        start = core.pop_spot((centre.x, centre.y, lo[2]), h, _eye(), rng, others)
    waiting = len(_C["jobs"])
    hurry = core.carry_speedup(waiting)
    route = core.dash_route(start[:2], goal[:2], others, h, rng, hurry=waiting > 3)
    g = ob.copy()                              # same mesh and modifiers: it looks like the part
    g.name = core.msg_name("carry", _S["n"] % 1000)
    _S["n"] += 1
    g.parent = None
    for c in list(getattr(g, "constraints", ())):
        g.constraints.remove(c)
    collection().objects.link(tag(g))
    _C["ghosts"].add(g.name)
    size = max(hi[k] - lo[k] for k in range(3))
    t = core.CARRY_TIMES
    steps, at = [], t["pop"] + t["pickup"] / hurry
    for step in route:
        d = core.step_time(step, h, hurry)
        steps.append((at, at + d, step))
        at += d
    job = {"name": name, "ghost": g.name, "t0": now, "steps": steps, "start": start, "goal": goal,
           "z": ground_z(goal[0], goal[1], lo[2]), "k": core.hold_scale(size, h), "off": centre - ob.matrix_world.translation,
           "place_at": at, "end": at + t["place"] / hurry, "pose": None, "h": h}
    return job


def _ghost_at(job, ob, point, k):
    """The ghost: the part's own turn and scale times k, its centre at point."""
    from mathutils import Matrix, Vector
    g = bpy.data.objects.get(job["ghost"])
    if g is None:
        return
    loc, rot, sca = ob.matrix_world.decompose()
    g.matrix_world = (Matrix.Translation(Vector(point) - job["off"] * k) @ rot.to_matrix().to_4x4()
                      @ Matrix.Diagonal((*(sca * max(k, 1e-4)), 1.0)))


def _pose_once(job, pose):
    if job["pose"] != pose:
        job["pose"] = pose
        play(pose)


def _carry_step(job, now):
    """Move Maris and the ghost for one frame; True when the job is done."""
    from mathutils import Vector
    r, ob = rig(), bpy.data.objects.get(job["name"])
    if r is None or ob is None:
        return True
    t = now - job["t0"]
    h = job["h"]
    pop = core.CARRY_TIMES["pop"]
    hold = lambda: r.matrix_world @ Vector(core.CARRY_HOLD)   # noqa: E731
    if t < pop:                                # poof: out where she was, in where the part pops
        x = t / pop
        if x < 0.5:
            r.scale = (h * max(0.02, 1 - 2 * x) / spec()["height"],) * 3
        else:
            r.location = (job["start"][0], job["start"][1], job["z"])
            _turn_to(r, *job["goal"][:2])
            r.scale = (h * max(0.02, 2 * x - 1) / spec()["height"],) * 3
            _ghost_at(job, ob, hold(), job["k"] * core.ease(2 * x - 1))
        return False
    r.scale = (h / spec()["height"],) * 3
    if t < (job["steps"][0][0] if job["steps"] else job["place_at"]):
        _pose_once(job, "carry")
        _ghost_at(job, ob, hold(), job["k"])
        return False
    if t < job["place_at"]:
        for t0, t1, step in job["steps"]:
            if t0 <= t < t1:
                x = (t - t0) / max(t1 - t0, 1e-6)
                kind = step[0]
                if kind in ("run", "phase"):
                    a, b = step[1], step[2]
                    r.location = (a[0] + (b[0] - a[0]) * x, a[1] + (b[1] - a[1]) * x, job["z"])
                    _turn_to(r, *b)
                    _pose_once(job, "run")
                    _show_maris(kind == "run" or int(t * 30) % 3 != 0)   # phasing: she flickers
                else:
                    _show_maris(True)
                    _pose_once(job, kind)          # trip / crash, on the spot
                break
        _ghost_at(job, ob, hold(), job["k"])
        return False
    _show_maris(True)
    if job["pose"] != "place":
        r.location = (job["goal"][0], job["goal"][1], job["z"])
        c = ob.matrix_world.translation + job["off"]
        _turn_to(r, c.x, c.y)
        job["lift_from"] = tuple(hold())
        _pose_once(job, "place")
    x = (t - job["place_at"]) / max(job["end"] - job["place_at"], 1e-6)
    if x >= 1.0:
        return True
    target = tuple(ob.matrix_world.translation + job["off"])
    fly = core._clamp((x - 0.25) / 0.75)          # after the swing starts
    _ghost_at(job, ob, core.place_path(job["lift_from"], target, fly, 0.4 * h),
              job["k"] + (1 - job["k"]) * core.ease(fly))
    return False


def _route_steps(a, b, skip, h, hurry=1.0):
    others = _obstacles(set(skip))
    route = core.dash_route(tuple(a[:2]), tuple(b[:2]), others, h, _rng(), hurry=False)
    steps, at = [], 0.0
    for step in route:
        d = core.step_time(step, h, hurry)
        steps.append((at, at + d, step))
        at += d
    return steps, at


def _rng():
    if _C["rng"] is None:
        import random
        _C["rng"] = random.Random(int(time.monotonic() * 1000))
    return _C["rng"]


def _run_along(job, t, r):
    """Her place at t on the job's route (runs, phases); True while still on the way."""
    for t0, t1, step in job["steps"]:
        if t0 <= t < t1:
            if step[0] in ("run", "phase"):
                x = (t - t0) / max(t1 - t0, 1e-6)
                a, b = step[1], step[2]
                px, py = a[0] + (b[0] - a[0]) * x, a[1] + (b[1] - a[1]) * x
                r.location = (px, py, ground_z(px, py, r.location.z))
                _turn_to(r, *b)
                _pose_once(job, "run")
            else:
                _pose_once(job, step[0])
            return True
    return t < job["T"]


def _start_go(job, now):
    """She runs to a spot (a seat's front), then does what comes next."""
    r = rig()
    if r is None:
        return None
    h = maris_height()
    job["steps"], job["T"] = _route_steps(tuple(r.location), job["to"], (), h)
    job.update(t0=now, pose=None)
    return job


def _start_move(job, now):
    """A moved group: she runs beside it, lifts it and runs it to its new place (core.moved_groups)."""
    from mathutils import Vector
    r = rig()
    obs = [bpy.data.objects.get(n) for n in job["names"]]
    if r is None or any(o is None for o in obs):
        return None
    h = maris_height()
    lo, hi = _world_box(obs)
    c = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0))
    side = Vector((r.location.x, r.location.y, 0)) - c
    side = side.normalized() if side.length > 1e-3 else Vector((0, -1, 0))
    pick = c + side * (max(hi[0] - lo[0], hi[1] - lo[1]) / 2 + 0.35 * h)
    job["steps"], job["T"] = _route_steps(tuple(r.location), tuple(pick), job["names"], h)
    d = job["delta"]
    job["steps2"], job["T2"] = _route_steps(tuple(pick), (pick.x + d[0], pick.y + d[1]), job["names"], h)
    job.update(t0=now, pose=None, pick=pick, stage="to")
    return job


def _move_step(job, now):
    """One frame of a group move; True when done."""
    from mathutils import Vector
    r = rig()
    if r is None:
        return True
    t = now - job["t0"]
    if job["stage"] == "to":
        if _run_along(job, t, r):
            return False
        job.update(stage="lift", t0=now, pose=None,
                   base={n: bpy.data.objects[n].location.copy() for n in job["names"]})
        _turn_to(r, *(_world_box([bpy.data.objects[n] for n in job["names"]])[0][:2]))
        _pose_once(job, "carry")
        return False
    if job["stage"] == "lift":
        if t < 0.6:
            return False
        job.update(stage="carry", t0=now, steps=job["steps2"], T=job["T2"], pose=None,
                   start=Vector((r.location.x, r.location.y, 0)))
        return False
    on_way = _run_along(job, t, r)
    d = Vector((r.location.x, r.location.y, 0)) - job["start"]
    for n in job["names"]:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            b = job["base"][n]
            ob.location = (b.x + d.x, b.y + d.y, b.z)
    if on_way:
        return False
    for n in job["names"]:                     # exactly where the request put it
        ob = bpy.data.objects.get(n)
        if ob is not None:
            ob.location = job["base"][n] + _vec(job["delta"])
    _C["moving"].pop(tuple(job["names"]), None)
    play("place")
    look_at(tuple(_world_box([bpy.data.objects[n] for n in job["names"] if n in bpy.data.objects])[0]))
    return True


def _grow_tick(now):
    """Small and fixed-on parts grow in where they belong, one after another, while she points
    her tool at them (core.carry_choice "grow")."""
    if not _C["growing"] and _C["grow"] and not (_C["cur"] or _C["jobs"]):
        t0 = now
        for name in list(_C["grow"]):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                _C["growing"].append({"name": name, "t0": t0, "scale": ob.scale.copy()})
                t0 += core.GROW_TIMES["gap"]
        _C["grow"].clear()
        if _C["growing"]:
            first = bpy.data.objects.get(_C["growing"][0]["name"])
            box = _world_box([first]) if first is not None else None
            if box is not None:
                r = rig()
                if r is not None:
                    _turn_to(r, (box[0][0] + box[1][0]) / 2, (box[0][1] + box[1][1]) / 2)
                look_at(((box[0][0] + box[1][0]) / 2, (box[0][1] + box[1][1]) / 2, box[0][2]))
            play("point")
    left = []
    for g in _C["growing"]:
        ob = bpy.data.objects.get(g["name"])
        if ob is None:
            continue
        x = (now - g["t0"]) / core.GROW_TIMES["each"]
        if x < 0:
            left.append(g)
            continue
        if g["name"] in _C["hidden"]:
            _hide(ob, False)
        k = core.grow_scale(x)
        ob.scale = g["scale"] * k
        if x < 1.0:
            left.append(g)
        else:
            ob.scale = g["scale"]
    _C["growing"] = left
    if not left and not _C["grow"] and not (_C["cur"] or _C["jobs"]) and _C.get("after"):
        after, _C["after"] = _C["after"], None
        _show_cue(*after)


def _carry_tick(now):
    carry_scan()
    job = _C["cur"]
    if job is None:
        while _C["jobs"] and job is None:
            item = _C["jobs"].popleft()
            if isinstance(item, dict):
                job = (_start_go if item["kind"] == "go" else _start_move)(item, now)
                continue
            job = _start_job(item, now)
            if job is None:
                ob = bpy.data.objects.get(item)
                if ob is not None:
                    _hide(ob, False)
        _C["cur"] = job
        if job is None:
            return
    kind = job.get("kind")
    if kind == "go":
        r = rig()
        if r is not None and _run_along(job, now - job["t0"], r):
            return
        _C["cur"] = None
        if job.get("then") == "sit":
            sit(walk=False)
        return
    if kind == "move":
        if not _move_step(job, now):
            return
        _C["cur"] = None
        return
    if not _carry_step(job, now):
        return
    _drop_ghost(job)
    ob = bpy.data.objects.get(job["name"])
    if ob is not None:
        _hide(ob, False)
    _C["cur"] = None
    if ob is not None:                         # she keeps facing what she just placed
        box = _world_box([ob])
        if box is not None:
            look_at(((box[0][0] + box[1][0]) / 2, (box[0][1] + box[1][1]) / 2, box[0][2]))
    if _C["jobs"] or _C["grow"] or _C["growing"]:
        return
    after, _C["after"] = _C["after"], None
    if after:
        _show_cue(*after)
    else:
        play(idle())


# ---- toys ----------------------------------------------------------------------------------------

def set_toy(name):
    """Show one toy (it floats by her wand's star). Maris files before 2.0 had a thread whose end
    marker moves onto the line she is weaving; that still runs when the marker is there."""
    sp = spec()
    coll = bpy.data.collections.get(sp["collection"])
    end = bpy.data.objects.get(sp["prefix"] + "ThreadEnd")
    if coll is None or name not in sp["toys"]:
        return
    for ob in list(coll.all_objects):
        if ob is None or "maris_toy" not in ob:
            continue
        if ob["maris_toy"] == name and end is not None and "thread_end_local" in ob:
            end.location = ob["thread_end_local"]
    _S["toy"] = name
    refresh_visibility()


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
    coll = bpy.data.collections.get(sp["collection"])
    if coll is None:
        return False
    for ob in list(coll.all_objects):       # a snapshot: hiding objects resets all_objects
        if ob is None or ob.type != "MESH":
            continue
        slot = ob.get("maris_slot")
        if slot in mats and ob.data.materials:
            ob.data.materials[0] = _make_material(*mats[slot])
    choice = design.get("toy", sp["default_toy"])
    toys = sp["toys"]
    if choice in toys:
        set_toy(choice)
    elif (_S["toy"] not in toys
          or (choice == "random" and toys[_S["toy"]]["theme"] != outfit.get("toy_theme"))):
        new_toy()
    else:
        set_toy(_S["toy"])                     # keep this session's pick (also after a save)
    refresh_visibility()
    anim = _S["anim"] or {}
    if anim.get("pose") in core.looping(sp) and anim.get("pose") != idle() and not carrying():
        play(idle())                           # a new outfit may rest differently (the ninja)
    return True


_PROPS = ("maris_outfit", "maris_tool", "maris_pose", "maris_toy")


def refresh_visibility(pose=None):
    """Show and hide Maris's pieces for the worn outfit, the pose and the toy (core.visible)."""
    sp = spec()
    coll = bpy.data.collections.get(sp["collection"])
    design = _S.get("worn")
    if coll is None or design is None:
        return
    pose = pose or (_S["anim"] or {}).get("pose", "idle")
    obs = {ob.name: ob for ob in list(coll.all_objects) if ob is not None}
    props = {n: {k: ob[k] for k in _PROPS if k in ob} for n, ob in obs.items()}
    for name, shown in core.visible(sp, list(obs), design["outfit"], pose, props, toy=_S["toy"]).items():
        ob = obs[name]
        if ob.hide_viewport == shown or ob.hide_render == shown:
            ob.hide_viewport = ob.hide_render = not shown


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
    r = ensure_maris()
    if r is None:
        return
    _intro_view(r)
    face("happy")
    new_toy(only_random=True)
    play("rise")
    say("Hi, I'm Maris", kind="intro")
    bpy.app.timers.register(lambda: (play("wave"), None)[1], first_interval=1.0)
    bpy.app.timers.register(lambda: (say("Say or type what to make", kind="say"), None)[1],
                            first_interval=2.2)


INTRO_FIT = 3.4             # an empty scene at hello: the view shows this many of her heights (she and the lines)
INTRO_OUT = 1.5             # after the lines the view eases this much further out (half as far again)
INTRO_OUT_AT, INTRO_OUT_FOR = 3.6, 1.2   # seconds after hello, and how long the ease takes
INTRO_TO_PANEL = 0.35       # she turns this far (of the view's right) toward the side panel


def _intro_view(r):
    """Hello: she faces the viewer, turned a little toward the copilot panel (the view's right);
    with nothing else in the scene the view also comes closer and looks at her. A view in camera
    mode, or a scene with the user's things in it, is never moved."""
    from mathutils import Vector
    r3d = _region_3d()
    if r3d is None:
        return
    inv = r3d.view_matrix.inverted()
    eye, right = inv.translation, inv.col[0].xyz
    face_dir = Vector((eye.x - r.location.x, eye.y - r.location.y, 0.0))
    if face_dir.length < 1e-6:
        return
    face_dir = face_dir.normalized() + INTRO_TO_PANEL * Vector((right.x, right.y, 0.0))
    r.rotation_euler = (0, 0, core.yaw_to(face_dir.x, face_dir.y))
    if r3d.view_perspective != "CAMERA" and _scene_box() is None:
        h = maris_height()
        r3d.view_location = r.location + Vector((0, 0, 0.55 * h))
        near = INTRO_FIT * h
        r3d.view_distance = near
        t_end = time.monotonic() + INTRO_OUT_AT

        def ease_out():
            if _region_3d() is not r3d or r3d.view_perspective == "CAMERA":
                return None
            x = (time.monotonic() - t_end) / INTRO_OUT_FOR
            if x < 0:
                return 0.05
            k = core.ease(min(1.0, x))
            r3d.view_distance = near * (1 + (INTRO_OUT - 1) * k)
            return None if x >= 1 else 1 / 30
        bpy.app.timers.register(ease_out, first_interval=0.1)


def _follow_tick():
    """Follow Maris (off by default): while she runs a part in, the view drifts after her. The
    view is never moved in camera mode, and only its centre moves, not its angle or distance."""
    try:
        on = prefs().follow_view
    except Exception:
        on = False
    r, r3d = rig(), _region_3d()
    if not on or r is None or r3d is None or r3d.view_perspective == "CAMERA" or not _C["cur"]:
        return
    from mathutils import Vector
    want = r.location + Vector((0, 0, 0.5 * maris_height()))
    r3d.view_location = r3d.view_location.lerp(want, 0.06)


def remove_all():
    """The switch went off: Maris, its materials and every message leave the file."""
    carry_reset()
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
        _carry_tick(now)
        _grow_tick(now)
        _face_tick()
        _follow_tick()
        _pose_tick(now)
        for m in list(_S["msgs"]):
            _apply_effect(m, now)
    except ReferenceError:                     # undo / file load removed something: start clean
        _S["msgs"].clear()
        _S["anim"] = None
    return 1 / 30 if (_S["anim"] or _S["msgs"] or _QUEUE or len(_ACTIONS) or _C["on"] or carrying()) else 0.5


# ---- files: never in the user's work -------------------------------------------------------------

@bpy.app.handlers.persistent
def _save_pre(_=None):
    """Blender writes every datablock that still has users, so the show leaves the file
    completely before a save and comes back after it (same design, pose and messages). Parts
    she is still carrying are put in place first: the file always has every part visible."""
    carry_reset()
    _stand_up()
    if bpy.data.collections.get(core.COLLECTION) is None:
        _S["saved"] = None
        return
    r = rig()
    _S["saved"] = {
        "maris": r is not None,
        "design": _S.get("worn"),
        "where": (tuple(r.location), tuple(r.scale)) if r is not None else None,
        "turn": tuple(r.rotation_euler) if r is not None else (0, 0, 0),
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
        r.rotation_euler = saved["turn"]
        play(saved["pose"] if saved["pose"] not in SIT_POSES else idle())
    for m in saved["msgs"]:
        name = say(m["text"], m["effect"] if m["effect"] != "float" else "fade")
        if name:
            _S["msgs"][-1].update(base=Vector(m["base"]), t0=time.monotonic() - 60.0)


@bpy.app.handlers.persistent
def _load_post(_=None):
    _S["msgs"].clear()
    _S["anim"] = None
    _S["stand"] = None
    _carry_forget()                            # another file: its objects are not ours to unhide


@bpy.app.handlers.persistent
def _undo_post(_=None):
    """Undo / redo restores older data: every part shows, no carry or ghost is left over."""
    carry_reset()
    _S["stand"] = None
    for ob in list(bpy.data.objects):
        if ob.name.startswith(core.msg_name("carry", 0)[:-3]) and ob.name not in _C["ghosts"]:
            bpy.data.objects.remove(ob, do_unlink=True)


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
        col.prop(p, "carry_parts")
        col.prop(p, "follow_view")
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
        "carry_parts": bpy.props.BoolProperty(
            name="Carry parts", default=True,
            description="While the copilot builds, Maris dashes each new part to its place. "
                        "Only a show: the part is already there"),
        "follow_view": bpy.props.BoolProperty(
            name="Follow Maris", default=False,
            description="The view drifts after Maris while she carries a part. Never in camera view"),
        "fun_finish": bpy.props.BoolProperty(
            name="Fun finish", default=True, description="A little celebration when a task is done"),
        "effects": bpy.props.BoolProperty(
            name="Effects", default=True, description="Off: plain text, no motion"),
        "maris_in_renders": bpy.props.BoolProperty(
            name="Maris in renders", default=False, update=on_render_switch,
            description="Off: Maris and messages never show in renders"),
        "maris_design": bpy.props.EnumProperty(
            name="Design", items=_design_items, update=on_design_chosen,
            description="The shipped looks and the ones you saved"),
    }


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.copt_maris = bpy.props.PointerProperty(type=COPT_MarisForm)
    bpy.app.timers.register(tick, persistent=True, first_interval=1.0)
    bpy.app.handlers.save_pre.append(_save_pre)
    bpy.app.handlers.save_post.append(_save_post)
    bpy.app.handlers.load_post.append(_load_post)
    bpy.app.handlers.undo_post.append(_undo_post)
    bpy.app.handlers.redo_post.append(_undo_post)
    from . import executor
    if carry_pause not in executor.AROUND_JOB:
        executor.AROUND_JOB.append(carry_pause)


def unregister():
    try:
        bpy.app.timers.unregister(tick)
    except Exception:
        pass
    try:
        carry_reset()                          # disabling mid-carry: every part shows
    except Exception:
        pass
    from . import executor
    if carry_pause in executor.AROUND_JOB:
        executor.AROUND_JOB.remove(carry_pause)
    for lst, fn in ((bpy.app.handlers.save_pre, _save_pre), (bpy.app.handlers.save_post, _save_post),
                    (bpy.app.handlers.load_post, _load_post), (bpy.app.handlers.undo_post, _undo_post),
                    (bpy.app.handlers.redo_post, _undo_post)):
        if fn in lst:
            lst.remove(fn)
    del bpy.types.WindowManager.copt_maris
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
