# SPDX-License-Identifier: Apache-2.0
# Pre-release replay, run INSIDE Blender by scripts/prerelease_test.sh:
#   blender -b --factory-startup --python scripts/prerelease_replay.py -- <server_url>
# Drives the installed add-on as the panel does (Copilot.run_auto with the add-on's router) on Blender's
# default scene and checks what users see: things are built and stand on the ground, word edits change the
# thing named and nothing else, a motion sentence makes an animation, camera and light stay put.
# Prints PASS/FAIL lines and exits non-zero on any FAIL.
import sys
import bpy
import addon_utils

addon_utils.enable("maris3d_copilot")
from maris3d_copilot import client, executor, routing  # noqa: E402
from maris3d_copilot.vendor.loop import Copilot  # noqa: E402
from maris3d_copilot.vendor.session import Session  # noqa: E402
from mathutils import Vector  # noqa: E402

url = sys.argv[sys.argv.index("--") + 1]
rt = client.make_client({"server_url": url, "model": "maris3d"})
session = Session(executor.QueueExecutor())
fails = []


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


def run(prompt):
    cop = Copilot(rt, session, router=lambda req, objs, _t: routing.resolve(req, bool(objs)))
    res = cop.run_auto(prompt)
    print("STEP %r mode %s calls %d" % (prompt, res.mode, len(res.calls or [])))
    return res


def find(word):
    """The top-level object a thing was built as: name starts with the word (Bench, Bench.001 ...)."""
    hits = [o for o in bpy.data.objects if o.parent is None and o.name.lower().startswith(word.lower())]
    return hits[0] if hits else None


def meshes(top):
    return [c for c in [top] + list(top.children_recursive) if c.type == "MESH"]


def colour(o):
    m = o.active_material
    return tuple(m.diffuse_color[:3]) if m else None


def is_(c, ch):
    if not c:
        return False
    r, g, b = c
    return {"blue": b > r and b > g, "red": r > g and r > b}[ch]


def min_z(top):
    zs = [(c.matrix_world @ Vector(k)).z for c in meshes(top) for k in c.bound_box]
    return min(zs) if zs else 0.0


cam0 = tuple(bpy.data.objects["Camera"].location)
light0 = tuple(bpy.data.objects["Light"].location)
cube_c0 = colour(bpy.data.objects["Cube"])

run("a small house")
house = find("House")
check(house is not None, "a small house: built")
if house:
    check(min_z(house) >= -0.01, "a small house: stands on the ground (min z %.2f)" % min_z(house))

run("a park with a bench, a tree behind the bench and a lamp next to the bench")
for name in ("Bench", "Tree", "Lamp"):
    o = find(name)
    check(o is not None, "park sentence: %s built" % name)
    if o:
        check(min_z(o) >= -0.01, "park sentence: %s on the ground (min z %.2f)" % (name, min_z(o)))

bench = find("Bench")
run("Make the bench blue.")
if bench:
    parts = meshes(bench)
    check(parts and all(is_(colour(c), "blue") for c in parts), "Make the bench blue.: every bench part blue")
check(colour(bpy.data.objects["Cube"]) == cube_c0, "Make the bench blue.: the default cube is not repainted")

lamp = find("Lamp")
before = tuple(lamp.location) if lamp else None
run("Move the lamp to the left of the bench.")
if lamp and bench:
    check(tuple(lamp.location) != before, "Move the lamp to the left of the bench.: the lamp moved")

run("a ball bouncing twice")
ball = find("Ball")
check(ball is not None, "a ball bouncing twice: a ball is built")
if ball:
    animated = any(o.animation_data and o.animation_data.action for o in [ball] + list(ball.children_recursive))
    check(animated, "a ball bouncing twice: the ball is animated")

check(tuple(bpy.data.objects["Camera"].location) == cam0, "camera never moved")
check(tuple(bpy.data.objects["Light"].location) == light0, "light never moved")
print("REPLAY %s (%d failed)" % ("OK" if not fails else "FAILED", len(fails)))
sys.exit(1 if fails else 0)
