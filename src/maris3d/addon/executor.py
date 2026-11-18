# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender, so it is GPL-3.0-or-later.
"""The add-on's tool executor: harness-compiled code, ONE queue, main thread only.

Every model call becomes code through vendor.dsl_tools.compile_calls — the exact
translation the model was benchmarked with (add-on behaviour == scored behaviour).
The model itself can only ever supply JSON arguments; they are repr-escaped inside
the fixed 26 templates, so no free-form code can reach Blender. Worker threads only
enqueue; the single pump timer (registered once, persistent) executes on Blender's
main thread. In `blender -b` scripts already run on the main thread, so jobs
dispatch inline and no timer is required.
"""
import math
import os
import queue
import threading
import time

import bpy

from .vendor.dsl_tools import compile_calls
from .vendor.session import Executor

MAX_OBJ_FACES = int(os.environ.get("MARIS3D_MAX_OBJ_FACES", "100000"))
MAX_SCENE_FACES = int(os.environ.get("MARIS3D_MAX_SCENE_FACES", "400000"))

_Q = queue.Queue()
_NS = {"_mat_get_or_new": lambda n: bpy.data.materials.get(n) or bpy.data.materials.new(n)}


# ---- face-budget guard (ported from the proven harness live server) ----
def _mod_factor(m):
    """Rough growth factor in faces of one modifier, from its settings only (nothing is evaluated)."""
    try:
        if m.type == "NODES" and m.node_group:
            f = 1.0
            for n in m.node_group.nodes:
                if n.bl_idname in ("GeometryNodeSubdivideMesh", "GeometryNodeSubdivideSurface"):
                    lv = n.inputs["Level"]
                    f *= 4.0 ** (3 if lv.is_linked else int(lv.default_value))
            return f
        if m.type == "SUBSURF":
            return 4.0 ** max(m.levels, 0)
        if m.type == "ARRAY" and m.fit_type == "FIXED_COUNT":
            return float(max(m.count, 1))
        if m.type == "MULTIRES":
            return 4.0 ** max(m.levels, 0)
    except Exception:
        pass
    return 1.0


def est_faces(o):
    if o.type != "MESH" or not o.data:
        return 0
    f = float(len(o.data.polygons))
    for m in o.modifiers:
        if m.show_viewport:
            f *= _mod_factor(m)
    return int(f)


def _is_show(o):
    """The maris and its messages (addon/show.py): never scene content, never budgeted."""
    return bool(o.get("copt_show")) or o.name.startswith(("msg_", "Maris_", "Norn_"))


def _work_objects():
    return [o for o in bpy.data.objects if not _is_show(o)]


def enforce_budget(before_names):
    """Refuse the part of a call that would blow the face budget (the found crash cause:
    stacked subdivide modifiers). Returns human-readable refusals ([] = fine)."""
    refused = []

    def drop_mod(o, m):
        ng = m.node_group if m.type == "NODES" else None
        o.modifiers.remove(m)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)

    for o in _work_objects():
        while est_faces(o) > MAX_OBJ_FACES and o.modifiers:
            m = o.modifiers[-1]
            refused.append(f"refused: modifier '{m.name}' on '{o.name}' would grow it to ~{est_faces(o):,} faces "
                           f"(limit {MAX_OBJ_FACES:,} per object); removed it to keep Blender alive")
            drop_mod(o, m)
        if est_faces(o) > MAX_OBJ_FACES:
            refused.append(f"refused: '{o.name}' has ~{est_faces(o):,} faces (limit {MAX_OBJ_FACES:,}); removed it")
            bpy.data.objects.remove(o, do_unlink=True)
    while sum(est_faces(o) for o in _work_objects()) > MAX_SCENE_FACES:
        cands = [o for o in _work_objects() if est_faces(o) > 0 and (o.name not in before_names or o.modifiers)]
        if not cands:
            break
        o = max(cands, key=est_faces)
        if o.modifiers:
            m = o.modifiers[-1]
            refused.append(f"refused: modifier '{m.name}' on '{o.name}' would take the scene past {MAX_SCENE_FACES:,} faces; removed it")
            drop_mod(o, m)
        else:
            refused.append(f"refused: '{o.name}' would take the scene past {MAX_SCENE_FACES:,} faces; removed it")
            bpy.data.objects.remove(o, do_unlink=True)
    return refused


def _override():
    """A 3D-view context override when a window exists (ops with region context needs); a no-op headless."""
    try:
        import contextlib
        win = bpy.context.window_manager.windows[0]
        area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
        region = next(r for r in area.regions if r.type == "WINDOW")
        return bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region)
    except Exception:
        return contextlib.nullcontext()


def run_code(code):
    """Run one compiled harness call on the main thread. Returns error text or None."""
    code = code.replace("bpy.data.materials.new(", "_mat_get_or_new(")  # reuse materials by name, no Red, Red.001
    err = None
    before = {o.name for o in _work_objects()}
    try:
        with _override():
            exec(compile(code, "<copt-call>", "exec"), _NS)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    refused = enforce_budget(before)
    if refused:
        err = (err + "; " if err else "") + "; ".join(refused)
    if not bpy.app.background:
        try:
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        except Exception:
            pass
    return err


def reset_scene():
    """Empty the scene (harness rows ran on empty scenes; the in-app undo does NOT use this on user scenes)."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.curves,
                 bpy.data.images, bpy.data.node_groups, bpy.data.actions):
        for b in list(coll):
            try:
                coll.remove(b)
            except Exception:
                pass
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    return {"objects": 0}


def scene_objects():
    out = []
    for o in _work_objects():
        mats = [s.material.name for s in o.material_slots if s.material]
        # world position: a part under a parent keeps its LOCAL location when the parent is moved,
        # and everything that reads this list (placement, checks, the scene summary) means "where it is"
        out.append({"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.matrix_world.translation],
                    "dims": [round(v, 3) for v in o.dimensions], "material": mats[0] if mats else None, "mats": mats,
                    "parent": o.parent.name if o.parent else None,
                    "rot_deg": [round(math.degrees(v), 1) for v in o.matrix_world.to_euler()],
                    # what was already done to it (a second "make it smooth" must not subdivide twice)
                    "mods": [m.type for m in getattr(o, "modifiers", [])]})
    return out


def undo_push(message):
    """Commit the applied changes as ONE named undo step, so one Ctrl+Z reverts a whole request."""
    try:
        bpy.ops.ed.undo_push(message=message)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def undo_pop():
    try:
        bpy.ops.ed.undo()
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _ray_clear(eye, centre, half, own):
    """Nothing but the subject stands between the eye and the subject (27 rays, 5% short)."""
    from itertools import product
    from mathutils import Vector
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    origin, blocked = Vector(eye), 0
    for sx, sy, sz in product((-1, 0, 1), repeat=3):
        target = Vector(centre) + Vector((sx * half[0], sy * half[1], sz * half[2]))
        ray = target - origin
        if ray.length < 1e-4:
            continue
        hit = scene.ray_cast(depsgraph, origin, ray.normalized(), distance=ray.length * 0.95)
        if hit and hit[0] and not _is_show(hit[4]):   # Maris never blocks the view
            # a hit inside the subject's own reach is the subject: a van does not hide the van
            if max(abs(a - b) for a, b in zip(hit[1], centre)) <= own:
                continue
            blocked += 1
    return blocked <= 2


def follow_view(names):
    """Follow the build: aim the 3D view at what the request just made, from where it can be seen.

    The framing is the shipped camera mode for the subject (framing.follow_eye); the eye is then
    checked against the scene itself -- not under the ground, the line to the subject not cut by a
    wall or a neighbour -- and walked round the subject to the nearest eye that passes. A view the
    user has put in camera mode is theirs and is left alone.
    """
    from mathutils import Vector
    from .vendor import framing
    boxes = []
    for name in names or ():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        # a moved thing is often its empty: its parts are what the eye must see, not its origin
        # (a move framed the empty's centre from 1.5 m)
        points = []
        for part in [ob] + list(ob.children_recursive):
            if part.type in ("MESH", "CURVE", "FONT", "SURFACE", "META"):
                points += [part.matrix_world @ Vector(corner) for corner in part.bound_box]
        points = points or [ob.matrix_world.translation]
        boxes.append((ob.name, (tuple(min(p[k] for p in points) for k in range(3)),
                                tuple(max(p[k] for p in points) for k in range(3)))))
    boxes = framing.follow_boxes(boxes)
    if not boxes:
        return {"framed": 0}
    first = boxes[0][0]
    lo = [min(b[0][k] for _n, b in boxes) for k in range(3)]
    hi = [max(b[1][k] for _n, b in boxes) for k in range(3)]
    centre = tuple((lo[k] + hi[k]) / 2 for k in range(3))
    dims = tuple(max(hi[k] - lo[k], 0.05) for k in range(3))
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    space = area.spaces.active
    r3d = space.region_3d
    if r3d.view_perspective == "CAMERA":
        return {"framed": 0, "why": "the view is in camera mode"}
    tan_h = 18.0 / max(float(space.lens), 1.0)
    tans = (tan_h, tan_h * region.height / max(region.width, 1))
    eye, aim = framing.follow_eye(centre, dims, first, tans)
    size = max(dims)
    half = tuple(v * 0.25 for v in dims)
    own = size * 0.5 + 0.1

    def fault(e):
        if e[2] < 0.25 and centre[2] > 0.0:
            return "underground"
        return "" if _ray_clear(e, centre, half, own) else "blocked"

    eye, why = framing.first_clear_eye(eye, aim, fault, floor=min(1.2, centre[2] + dims[2]))
    look = Vector(aim) - Vector(eye)
    _glide_to(area, r3d, Vector(aim), max(look.length, 0.5), look.normalized().to_track_quat("-Z", "Y"))
    print(f"COPT-FOLLOW {first} eye {[round(v, 2) for v in eye]} aim {[round(v, 2) for v in aim]}"
          + (f" moved: {why}" if why else ""), flush=True)
    return {"framed": 1, "subject": first, "eye": [round(v, 3) for v in eye], "moved": why}


# ---- gliding the view: the 3D view moves to a new subject, it does not jump ----
_GLIDE = {}


def gliding():
    """True while the view is still on its way to the last subject."""
    return bool(_GLIDE)


def finish_glide():
    """Put the view where the glide is going, now (a still taken before the glide ends)."""
    if _GLIDE:
        _glide_step(at_end=True)


def _glide_to(area, r3d, loc, dist, rot):
    from .vendor import framing
    a = (r3d.view_location.copy(), float(r3d.view_distance), r3d.view_rotation.copy())
    secs = framing.glide_seconds(a[1], dist, (loc - a[0]).length)
    _GLIDE.clear()
    _GLIDE.update(area=area, r3d=r3d, t0=time.time(), secs=secs, a=a, b=(loc.copy(), dist, rot.copy()))
    if bpy.app.background:
        finish_glide()
    elif not bpy.app.timers.is_registered(_glide_step):
        bpy.app.timers.register(_glide_step, first_interval=0.0)


def _glide_step(at_end=False):
    from .vendor import framing
    g = _GLIDE
    if not g:
        return None
    u = 1.0 if at_end else min((time.time() - g["t0"]) / max(g["secs"], 1e-3), 1.0)
    s = framing.ease(u)
    (la, da, ra), (lb, db, rb) = g["a"], g["b"]
    try:
        r3d = g["r3d"]
        r3d.view_location = la.lerp(lb, s)
        r3d.view_distance = framing.glide_distance(da, db, s)
        r3d.view_rotation = ra.slerp(rb, s)
        g["area"].tag_redraw()
    except ReferenceError:          # the view was closed under the glide
        u = 1.0
    if u >= 1.0:
        _GLIDE.clear()
        return None
    return 1.0 / 60.0


# ---- the one queue ----
def _dispatch(job):
    kind, holder = job[0], job[-1]
    try:
        if kind == "exec":
            holder["res"] = {"ok": True, "error": run_code(job[1])}
        elif kind == "reset":
            holder["res"] = {"ok": True, **reset_scene()}
        elif kind == "objects":
            holder["res"] = {"ok": True, "objects": scene_objects()}
        elif kind == "undo_push":
            holder["res"] = {"ok": True, "error": undo_push(job[1])}
        elif kind == "undo_pop":
            holder["res"] = {"ok": True, "error": undo_pop()}
        elif kind == "follow":
            holder["res"] = {"ok": True, **follow_view(job[1])}
        else:
            holder["res"] = {"ok": False, "error": f"unknown job {kind}"}
    except Exception as e:
        holder["res"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if "ev" in holder:  # set only in the queued path; background dispatch runs inline
        holder["ev"].set()


def submit(job):
    """Worker-thread side: enqueue and block for the main thread (or run inline in `blender -b`).

    Jobs are tuples; the last element is the result holder ONLY when the caller
    supplied one (`("exec", code, {})`). Jobs like `("undo_push", label)` used to
    crash here — appending the event dict indexed into the label string
    (TypeError: 'str' object does not support item assignment)."""
    job = list(job)
    if not job or not isinstance(job[-1], dict):
        job.append({})
    if bpy.app.background:
        _dispatch(job)
        return job[-1]["res"]
    job[-1]["ev"] = threading.Event()
    _Q.put(job)
    if not job[-1]["ev"].wait(120):
        return {"ok": False, "error": "timeout waiting for the Blender main thread"}
    return job[-1]["res"]


def pump():
    """THE persistent main-thread timer: drain the queue, then let the UI redraw."""
    try:
        while True:
            _dispatch(_Q.get_nowait())
    except queue.Empty:
        pass
    return 0.04


class QueueExecutor(Executor):
    """The copilot.session.Executor contract, bridged onto the main thread."""

    def __init__(self, on_call=None):
        self.on_call = on_call  # optional fn(call) for live progress in the panel

    def run_call(self, call):
        if self.on_call:
            self.on_call(call)
        code, err = compile_call(call)
        if err:
            return False, err
        res = submit(("exec", code, {}))
        error = res.get("error")
        return (error is None), error

    def reset(self):
        submit(("reset", {}))

    def objects(self):
        return submit(("objects", {})).get("objects", [])


def compile_call(call):
    try:
        return compile_calls({"calls": [call]}), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"[-200:]
