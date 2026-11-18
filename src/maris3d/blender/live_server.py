# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender and imports bpy, so it is GPL-3.0-or-later (see LICENSES/README.md).
"""Runs INSIDE a Blender with its UI (not headless): a tiny socket add-on so the MCP server can drive the open window.

  Blender --factory-startup --window-geometry 40 60 1280 800 --python live_server.py

Listens on 127.0.0.1:$BLENDER_LIVE_PORT (default 9877), one JSON object per line in, one JSON line out.
Commands: ping, reset, exec (code = compiled harness code of ONE call), summary, screenshot, frame.
Everything that touches bpy runs on Blender's main thread (a bpy.app.timers queue); sockets live in a thread.
Nothing here writes, edits or reorders a model call: the MCP server sends the harness-compiled code as it is."""
import bpy, os, sys, json, time, math, socket, threading, queue, traceback, faulthandler, resource

PORT = int(os.environ.get("BLENDER_LIVE_PORT", "9877"))
KEEP_DEFAULT = os.getenv("BLENDER_LIVE_KEEP_DEFAULT") == "1"
Q = queue.Queue()
STATE = {"ns": {}, "shots": os.environ.get("BLENDER_LIVE_SHOTS", os.path.expanduser("~/.cache/maris3d/live"))}

# ---- crash log that survives a crash: line-buffered, fsynced event log + faulthandler (native crash -> Python stacks)
LOGDIR = STATE["shots"]
os.makedirs(LOGDIR, exist_ok=True)
_LOGF = open(os.path.join(LOGDIR, "blender-live-events.log"), "a", buffering=1)
_FAULT = open(os.path.join(LOGDIR, "blender-live-fault.log"), "a", buffering=1)
faulthandler.enable(file=_FAULT, all_threads=True)
try:
    faulthandler.register(__import__("signal").SIGUSR1, file=_FAULT, all_threads=True)  # kill -USR1 <pid> dumps stacks
except Exception:
    pass
sys.stdout = sys.stderr = _LOGF  # Python-side prints and tracebacks go to the line-buffered file


def elog(msg):
    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // (1024 * 1024)  # macOS: bytes -> MB (peak)
        _LOGF.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} peakrss={rss}MB {msg}\n")
        _LOGF.flush()
        os.fsync(_LOGF.fileno())
    except Exception:
        pass


elog(f"blender_live start, Blender {bpy.app.version_string}, faulthandler on, fault log {_FAULT.name}")


def _ctx():
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def _set_view(az=-35.0, el=58.0, dist=5.2, loc=(0, 0, 0.25)):
    from mathutils import Euler
    win, area, region = _ctx()
    sp = area.spaces[0]
    sp.shading.type, sp.shading.light, sp.shading.color_type = "SOLID", "STUDIO", "MATERIAL"
    sp.overlay.show_stats = True
    r3d = sp.region_3d
    r3d.view_perspective = "PERSP"
    r3d.view_distance, r3d.view_location = dist, loc
    r3d.view_rotation = Euler((math.radians(el), 0, math.radians(az)), "XYZ").to_quaternion()


# ---- guard: a call must not blow the scene up (found cause of the crashes: stacked Subdivide modifiers, 8.4 M vertices per cone)
MAX_OBJ_FACES = int(os.environ.get("BLENDER_LIVE_MAX_OBJ_FACES", "100000"))     # evaluated faces of one object
MAX_SCENE_FACES = int(os.environ.get("BLENDER_LIVE_MAX_SCENE_FACES", "400000"))  # evaluated faces of the whole scene


def _mod_factor(m):
    """Rough growth factor in faces of one modifier, from its settings only (nothing is evaluated)."""
    try:
        if m.type == "NODES" and m.node_group:
            f = 1.0
            for n in m.node_group.nodes:
                if n.bl_idname == "GeometryNodeSubdivideMesh":
                    lv = n.inputs["Level"]
                    f *= 4.0 ** (3 if lv.is_linked else int(lv.default_value))
                elif n.bl_idname == "GeometryNodeSubdivisionSurface":
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


def enforce_budget(before_names):
    """After a call: if an object (or the scene) would evaluate to more faces than the budget, refuse the part of the call that
    did it: remove the newest modifier(s) / the new object. Returns a list of human-readable refusals ([] = fine)."""
    refused = []
    for o in list(bpy.data.objects):
        while est_faces(o) > MAX_OBJ_FACES and o.modifiers:
            m = o.modifiers[-1]
            refused.append(f"refused: modifier '{m.name}' on '{o.name}' would grow it to ~{est_faces(o):,} faces "
                           f"(limit {MAX_OBJ_FACES:,} per object); removed it to keep Blender alive")
            _drop_mod(o, m)
        if est_faces(o) > MAX_OBJ_FACES:
            refused.append(f"refused: '{o.name}' has ~{est_faces(o):,} faces (limit {MAX_OBJ_FACES:,}); removed it")
            bpy.data.objects.remove(o, do_unlink=True)
    while sum(est_faces(o) for o in bpy.data.objects) > MAX_SCENE_FACES:
        cands = [o for o in bpy.data.objects if est_faces(o) > 0 and (o.name not in before_names or o.modifiers)]
        if not cands:
            break
        o = max(cands, key=est_faces)
        if o.modifiers:
            m = o.modifiers[-1]
            refused.append(f"refused: modifier '{m.name}' on '{o.name}' would take the scene past {MAX_SCENE_FACES:,} faces; removed it")
            _drop_mod(o, m)
        else:
            refused.append(f"refused: '{o.name}' would take the scene past {MAX_SCENE_FACES:,} faces; removed it")
            bpy.data.objects.remove(o, do_unlink=True)
    return refused


def _drop_mod(o, m):
    ng = m.node_group if m.type == "NODES" else None
    o.modifiers.remove(m)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)


def do_reset(_):
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
    STATE["ns"] = {}
    _set_view()
    return {"objects": 0}


def do_exec(req):
    win, area, region = _ctx()
    code = req["code"]
    if req.get("reuse_materials"):  # harness side only: tools.py makes a NEW material per set_material call; reuse by name
        code = code.replace("bpy.data.materials.new(", "_mat_get_or_new(")
        STATE["ns"].setdefault("_mat_get_or_new", lambda n: bpy.data.materials.get(n) or bpy.data.materials.new(n))
    t = time.time()
    err = None
    before = {o.name for o in bpy.data.objects}
    try:
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
            exec(compile(code, "<call>", "exec"), STATE["ns"])
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    refused = enforce_budget(before)  # before any redraw/depsgraph evaluation of what the call just set up
    if refused:
        err = (err + "; " if err else "") + "; ".join(refused)
        elog("GUARD " + "; ".join(refused))
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass
    return {"exec_s": round(time.time() - t, 3), "error": err, "objects": len(bpy.data.objects)}


def do_summary(_):
    bpy.context.view_layer.update()      # world positions must be current (a parent may just have moved)
    return {"objects": [{"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.matrix_world.translation], "dims": [round(v, 3) for v in o.dimensions], "mat": [s.material.name for s in o.material_slots if s.material],
                         "parent": o.parent.name if o.parent else None,
                         "rot_deg": [round(math.degrees(v), 1) for v in o.matrix_world.to_euler()],
                         "mods": [m.type for m in getattr(o, "modifiers", [])]}
                        for o in bpy.data.objects], "blender": bpy.app.version_string}


def _bounds(ob):
    """World-space centre and half-size of an object, so a framing can fit it exactly."""
    from mathutils import Vector
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return (lo + hi) / 2.0, max((hi - lo) / 2.0)


def _set_view_for(subject, center, half):
    """Put the viewport on one subject, framed the way the copilot frames that kind of thing.

    One hardcoded angle for everything is why a chair looked like a plane with legs and a house
    lost its roof line; the modes are in maris3d/copilot/framing.py.
    """
    import math
    from mathutils import Vector
    from maris3d.copilot.framing import mode_for
    mode = mode_for(subject)
    dist = max(float(mode["min"]), float(half) * float(mode["context"]))
    elev = math.radians(90.0 - float(mode["pitch"]))
    azim = math.radians(float(mode["az"]))
    d = Vector((math.cos(elev) * math.sin(azim), -math.cos(elev) * math.cos(azim),
                math.sin(elev)))
    eye = Vector(center) + d * dist
    win, area, region = _ctx()
    r3d = area.spaces[0].region_3d
    r3d.view_perspective = "PERSP"
    r3d.view_location = Vector(center)
    r3d.view_distance = dist
    r3d.view_rotation = (Vector(center) - eye).normalized().to_track_quat("-Z", "Y")
    return {"framed": 1, "subject": subject, "mode": mode["name"],
            "dist": round(dist, 2), "pitch": mode["pitch"]}


def do_frame(req):
    """Frame the view (what the user sees at the end of a build).

    With a subject name the copilot frames that one thing by its kind (a house three-quarter with
    its roof, a chair level with it, a wall square on). Without one, the whole scene, as before.
    """
    win, area, region = _ctx()
    subject = None
    if isinstance(req, dict):
        subject = req.get("subject") or req.get("name")
    if subject:
        ob = bpy.data.objects.get(subject)
        if ob is not None:
            try:
                center, half = _bounds(ob)
                return _set_view_for(subject, center, half)
            except Exception as exc:            # never lose the shot over a framing nicety
                elog(f"frame {subject} failed, framing the scene: {exc!r}")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        return {"framed": 0}
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.view3d.view_selected()
        bpy.ops.object.select_all(action="DESELECT")
    return {"framed": len(meshes)}


def do_screenshot(req):
    win, area, region = _ctx()
    os.makedirs(STATE["shots"], exist_ok=True)
    path = req.get("path") or os.path.join(STATE["shots"], time.strftime("shot-%Y%m%d-%H%M%S.png"))
    with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        bpy.ops.screen.screenshot(filepath=path, check_existing=False)
    return {"path": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0}


CMDS = {"reset": do_reset, "exec": do_exec, "summary": do_summary, "frame": do_frame, "screenshot": do_screenshot,
        "ping": lambda r: {"pong": True, "pid": os.getpid(), "blender": bpy.app.version_string, "objects": len(bpy.data.objects)}}


def pump():
    """Main-thread timer: run queued commands, reply through the per-request holder."""
    try:
        while True:
            req, holder = Q.get_nowait()
            elog(f"BEGIN {req['cmd']} " + (repr(req['code'][-300:]) if req["cmd"] == "exec" else ""))
            try:
                holder["res"] = dict(CMDS[req["cmd"]](req), ok=True)
            except Exception as e:
                holder["res"] = {"ok": False, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc(limit=3)[-600:]}
            elog(f"END {req['cmd']} ok={holder['res'].get('ok')} err={holder['res'].get('error')} objects={len(bpy.data.objects)}")
            holder["ev"].set()
    except queue.Empty:
        pass
    return 0.04


def serve():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(4)

    def handle(conn):
        f = conn.makefile("rwb")
        for line in f:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
                if req.get("cmd") not in CMDS:
                    res = {"ok": False, "error": "unknown cmd"}
                else:
                    holder = {"ev": threading.Event()}
                    Q.put((req, holder))
                    res = holder["res"] if holder["ev"].wait(req.get("timeout", 120)) else {"ok": False, "error": "timeout in Blender main thread"}
            except Exception as e:
                res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            f.write((json.dumps(res) + "\n").encode())
            f.flush()
        conn.close()

    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


def start():
    try:
        _set_view()
    except Exception:
        return 0.5  # window not ready yet
    if PORT and not KEEP_DEFAULT:
        do_reset(None)  # factory startup brings Cube/Camera/Light; the model was scored on an empty scene
    threading.Thread(target=serve, daemon=True).start()
    bpy.app.timers.register(pump, persistent=True)
    return None


bpy.app.timers.register(start, first_interval=1.5)
