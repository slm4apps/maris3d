"""How to look at a thing: the camera modes the copilot ships with.

The maintainers' take driver (not part of this repository) grew these one defect at a time
during the Christmas street scene: a chair from above is a plane with legs, a wall seen at an
angle is a sliver, a house needs its roof line, people need eye level and a pan. Until now they
lived inside that driver, so the shipped copilot had exactly one framing -- ``_set_view(az=-35,
el=58, dist=5.2)`` for everything -- and every lesson had to be re-learned by whoever wrote the
next tool that moved a viewport.

This module is that knowledge as data, bpy-free, so the driver, the addon and the live server all
frame a subject the same way and the rules can be tested without Blender.

    >>> mode_for("ChairSeat")["name"]
    'furniture'
    >>> mode_for("Cabin")["name"]          # not a kitchen cabinet
    'building'
    >>> mode_for("SwingSeat")["name"]
    'park'

pitch is degrees from straight down: 0 = top view, 90 = eye level.
"""
import math


# Every rule is (mode, keywords, mode settings, guards). Order matters: the first match wins.
# guards:
#   prefix  - the keyword must START the name, so FireMantel is not a "man"
#   exclude - name prefixes that must never match this rule (the bug that framed the Cabin like
#             a kitchen unit: "cabin" contains "cab", so the wall/cabinet rule swallowed it at 86
#             degrees and 2.6 m, and the house presentation never ran for it at all)
#   unless  - prefixes exempt from that exclusion ("Cabin" is a house, "Cabinet" is not)
RULES = (
    # flat on a wall: square on and close, or it is just a sliver
    ("wall", ("window", "wainscot", "accentpanel", "frame", "art", "graffiti", "door", "panel",
              "shelftop", "wall", "counter", "cab", "handle"),
     dict(pitch=86.0, context=3.2, min=2.6, sweep=6.0, az=0.0),
     # a SwingFrame contains "frame" but is not a wall
     dict(exclude=("cabin", "swing", "slide", "seesaw", "sandbox", "playpark", "roundabout"),
          unless=("cabinet",))),

    # furniture: level with it and from the open side of the room. From above (the old "room"
    # rule) a chair is just a plane with legs
    ("furniture", ("chair", "sofa", "cushion", "table", "cup", "book", "pot", "leaf", "rug", "tv",
                   "shelf", "flo", "lampbase", "lampshade", "lampstand"),
     dict(pitch=79.0, context=3.0, min=3.6, sweep=10.0, az=-32.0, room="kitchen"),
     {}),

    # a street lamp is a 3.4 m pole: the furniture distance crops it to the base
    ("streetlamp", ("lamppole", "lamphead", "lampglow", "streetlamp", "lampcap"),
     dict(pitch=70.0, context=1.8, min=5.5, sweep=14.0, az=20.0),
     {}),

    # playground: one structure, wide enough to hold the frame and its legs together
    ("park", ("swing", "slide", "seesaw", "see-saw", "sandbox", "climbing", "roundabout",
              "playpark"),
     dict(pitch=60.0, context=1.5, min=8.0, sweep=18.0, az=28.0),
     {}),

    ("terrain", ("mountain", "sky", "lawn", "ground", "roadsnow", "snowsheet", "snowpatch",
                 "walk", "terrain"),
     dict(pitch=42.0, context=1.6, min=10.0, sweep=10.0, az=30.0),
     {}),

    # a house: three-quarter from the road, high enough to see the roof line. NOT street=True --
    # the street houses are cloned rotated 90 degrees, so their doors face DOWN THE STREET and
    # forcing the eye onto the x side framed a blank wall
    ("building", ("house", "town", "cabin", "roof", "gable", "body", "facade"),
     dict(pitch=58.0, context=1.9, min=9.0, sweep=24.0, az=35.0, building=True),
     {}),

    # people: eye level and a pan across them
    ("people", ("man", "woman", "boy", "girl", "person", "kid", "child", "family"),
     dict(pitch=84.0, context=2.4, min=3.2, sweep=26.0, az=-26.0),
     dict(prefix=True)),

    # a present is a 30 cm box: close, and from the road side, never from inside the wall
    ("gift", ("gift", "ribbon", "present"),
     dict(pitch=72.0, context=1.8, min=1.6, sweep=8.0, az=14.0, street=True),
     {}),

    ("outdoor", ("tree", "bin", "car", "van", "bus", "snowman", "wreath", "sledge", "cat",
                 "squirrel", "path", "slab"),
     dict(pitch=66.0, context=2.6, min=5.0, sweep=16.0, az=35.0),
     {}),
)

DEFAULT = dict(pitch=64.0, context=2.2, min=6.0, sweep=18.0, az=35.0)


def mode_for(name):
    """The camera mode for a subject, with its settings and a name for the rule that matched."""
    n = (name or "").lower()
    for mode, keys, settings, guards in RULES:
        for keyword in keys:
            hit = n.startswith(keyword) if guards.get("prefix") else keyword in n
            if not hit:
                continue
            exempt = any(n.startswith(ok) for ok in guards.get("unless", ()))
            if not exempt and any(n.startswith(bad) for bad in guards.get("exclude", ())):
                continue        # a Cabin is a building; a Cabinet is still a cabinet
            out = dict(settings)
            out["name"] = mode
            return out
    out = dict(DEFAULT)
    out["name"] = "default"
    return out


# --- presentation: the first houses are not framed by a rule, they are toured -------------------
# Keep the road view we already have while the road is built, then zoom
# in slowly to the house and stop when the full house is in view with its surroundings, at an angle
# that shows front and side. So: rest on the road shot, one
# eased zoom, stop at a three-quarter angle whose FRONT is calibrated by that road shot.
PRESENT_PIECES = ("House", "Townhouse", "Cabin")
PRESENT_REST_S = 1.5
PRESENT_ZOOM_S = 6.0
PRESENT_ANGLE_DEG = 35.0
PRESENT_DISTANCE = 2.2          # multiples of the house's own largest size
PRESENT_MIN_DISTANCE = 9.0


def road_shot(shots, center=None):
    """Pick the road shot to start a zoom from: the pinned eye nearest the subject.

    ``shots`` is a sequence of (eye, aim). The road section is a dolly, so it pins several eyes
    along the street; starting the zoom from 46 m away flew across the whole town in six seconds.
    """
    if not shots:
        return None
    if center is None:
        return shots[-1]
    vals = [float(v) for v in center]
    cx, cy, cz = vals[:3]
    return min(shots, key=lambda s: (s[0][0] - cx) ** 2 + (s[0][1] - cy) ** 2 + (s[0][2] - cz) ** 2)


def inside_box(point, box, margin=1.0):
    """Is ``point`` inside ``box`` = (centre, [w, d, h]) grown by ``margin`` metres (x and y only)?"""
    c, sz = box
    return (abs(float(point[0]) - float(c[0])) <= float(sz[0]) / 2 + margin and
            abs(float(point[1]) - float(c[1])) <= float(sz[1]) / 2 + margin)


def present_targets(center, size, front, avoid=(), toward=None):
    """Where the zoom ends: a three-quarter shot with the front AND one side visible.

    ``front`` is the horizontal direction the subject faces, calibrated from the road shot that
    faces it -- never guessed, and never the back. The eye is that direction turned 35 degrees,
    choosing the turn that stays on the road side of the subject, 2.2x its own size away so the
    whole thing and its neighbours stay in frame. ``avoid`` is a list of (centre, [w, d, h])
    volumes of other buildings; a turn standing in one of them loses to a turn that does not.

    ``toward`` (x, y): when given, ``front`` is the side the DOOR is on and the turn chosen is the
    one nearer to that point (the road shot), so the eye sees the door wall and the wall that
    faces the road. Without it the "front" was the direction to the road shot, and for a house
    whose door does not face the road the turn that was left after ``avoid`` stood BEHIND the
    house (the house would otherwise be shown from the wrong angle).
    """
    import math
    vals = [float(v) for v in center]
    cx, cy, cz = vals[:3]
    size = float(size)
    fx, fy = (float(front[0]), float(front[1]))
    if abs(fx) + abs(fy) < 1e-9:
        fx, fy = (-1.0 if cx > 0 else 1.0), 0.0
    norm = math.hypot(fx, fy)
    fx, fy = fx / norm, fy / norm
    dist = max(size * PRESENT_DISTANCE, PRESENT_MIN_DISTANCE)
    a = math.radians(PRESENT_ANGLE_DEG)
    eye = None
    for sgn in (1.0, -1.0):
        dx = fx * math.cos(sgn * a) - fy * math.sin(sgn * a)
        dy = fx * math.sin(sgn * a) + fy * math.cos(sgn * a)
        ex, ey = cx + dx * dist, cy + dy * dist
        ez = cz + max(size * 0.35, 1.8)
        # a turn that stands inside another building (``avoid``) is never the road side: a house
        # built level with its neighbour used to be shown from the neighbour's living room
        blocked = any(inside_box((ex, ey, ez), b) for b in (avoid or ()))
        near = abs(ex) if toward is None else math.hypot(ex - float(toward[0]), ey - float(toward[1]))
        rank = (1 if blocked else 0, near)
        if eye is None or rank < best:
            eye, best = (ex, ey, ez), rank
    return eye, (cx, cy, cz)


# --- follow the build: stand where the thing that was just built can be seen --------------------
# The follow camera ships as part of the release. Its general part is small, and it is here:
#   1. a default place to stand for a subject, from its mode (follow_eye),
#   2. other places to stand, nearest first, when that one cannot see it (eye_candidates),
#   3. never stand in a building the subject is not in (eye_in_building),
#   4. take the first eye the scene says is clear (first_clear_eye) -- the caller supplies the
#      test, because only Blender can cast the ray.
# Why 2-4: a rule per object, checked against its own numbers, can pass while the picture shows a
# wall. One check on the final eye, asked of the scene, replaces those rules.

def follow_eye(center, dims, name="", tans=(0.36, 0.242), margin=1.25):
    """Where to stand to see a subject whole: (eye, aim) for a box at ``center`` of ``dims``.

    The direction comes from the subject's camera mode (a wall square on, furniture level, a house
    three-quarter and raised); the distance is the one at which the whole box fits the narrower
    side of the view. ``tans`` is tan(half field of view) as (horizontal, vertical).
    """
    import math
    mode = mode_for(name)
    cx, cy, cz = (float(v) for v in center[:3])
    w, d, h = (max(float(v), 0.0) for v in dims[:3])
    radius = max(0.5 * math.sqrt(w * w + d * d + h * h), 0.25)
    dist = min(max(float(margin) * radius / max(min(tans), 1e-3), 0.9), 120.0)
    elev = math.radians(min(max(90.0 - float(mode.get("pitch", 64.0)), 8.0), 80.0))
    az = math.radians(float(mode.get("az", 35.0)))
    # az 0 stands in front of the subject (-y, where a fresh Blender scene is looked at from)
    eye = (cx + dist * math.cos(elev) * math.sin(az),
           cy - dist * math.cos(elev) * math.cos(az),
           cz + dist * math.sin(elev))
    return eye, (cx, cy, cz)


def eye_candidates(eye, center):
    """Other places to stand, nearest to the rejected shot first.

    The same distance and height walked round the subject 45 degrees at a time (either way), then
    a raised eye, then farther back: 47 candidates, the shot that was asked for is not among them.
    """
    import math
    cx, cy, cz = (float(v) for v in center[:3])
    vx, vy, vz = float(eye[0]) - cx, float(eye[1]) - cy, float(eye[2]) - cz
    r = math.sqrt(vx * vx + vy * vy + vz * vz) or 1e-6
    az0 = math.atan2(vy, vx)
    el0 = math.asin(max(-1.0, min(1.0, vz / r)))
    out = []
    for scale in (1.0, 1.5):
        for el in (el0, math.radians(25.0), math.radians(40.0)):
            for turn in (0.0, 45.0, -45.0, 90.0, -90.0, 135.0, -135.0, 180.0):
                a = az0 + math.radians(turn)
                out.append((cx + r * scale * math.cos(el) * math.cos(a),
                            cy + r * scale * math.cos(el) * math.sin(a),
                            cz + r * scale * math.sin(el)))
    return out[1:]


def eye_in_building(eye, center, buildings, margin=0.3):
    """Is the eye standing in a building the subject is NOT in?

    ``buildings`` is a list of (centre, [w, d, h]). A chair in the living room is shot from inside
    the house, so a building that contains the subject does not count; any other one is a wall
    between the camera and the work.
    """
    for box in buildings or ():
        if inside_box(center, box, 0.0):
            continue
        top = float(box[0][2]) + float(box[1][2]) / 2 + margin
        if inside_box(eye, box, margin) and float(eye[2]) < top:
            return True
    return False


def first_clear_eye(eye, center, fault, floor=1.2):
    """The eye to use: ``eye`` if the scene says it sees the subject, else the nearest that does.

    ``fault(eye)`` returns "" when the eye is fine and a short reason when it is not (underground,
    inside-building, blocked). Returns (eye, reason): reason is "" when nothing had to move,
    the fault that was avoided when it did, and "stuck:<fault>" when no candidate passed -- the
    original eye is kept then, because a blocked view of the right place beats a clear view of
    nothing.
    """
    eye = tuple(float(v) for v in eye[:3])
    why = fault(eye)
    if not why:
        return eye, ""
    for cand in eye_candidates(eye, center):
        cand = (cand[0], cand[1], max(cand[2], float(floor)))
        if not fault(cand):
            return cand, why
    return eye, "stuck:" + why


# ---- following the build: what to frame, and gliding there instead of jumping ----
# The view should glide to the new location instead of jumping between objects.

MARKERS = ("SceneNorth",)          # bookkeeping objects the copilot adds: never a subject
BACKDROP_M = 40.0                  # a ground or sky this big is the stage, not the thing made
SHOW_PREFIXES = ("msg_", "Maris_", "Norn_")  # Maris and her messages (copilot/show.py): never a subject

# Where Maris lands and where her messages go, in the camera's frame.
LAND_GAP = 0.4                     # her distance from the scene's side, in multiples of her height
FRAME_HALF_DEG = 22.0              # inside this half-angle from the view's centre line she is in frame
MSG_LEAN = 0.2                     # a message leans this far toward the camera, in her heights


def _xy_unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else None


def landing_spot(box, eye, size):
    """Where Maris stands: on the ground beside the scene ``box`` ((lo), (hi)), on the right
    of the camera at ``eye`` and inside its frame, ``size`` = her height. No eye: the front right
    corner (Blender's front view looks along +y)."""
    lo, hi = box
    c = [(lo[k] + hi[k]) / 2.0 for k in range(3)]
    half = [(hi[k] - lo[k]) / 2.0 for k in range(2)]
    d = _xy_unit(c[0] - eye[0], c[1] - eye[1]) if eye is not None else None
    d = d or (0.0, 1.0)
    r = (d[1], -d[0])                                   # the camera's right on the ground
    reach_r = abs(r[0]) * half[0] + abs(r[1]) * half[1]
    reach_d = abs(d[0]) * half[0] + abs(d[1]) * half[1]
    side = reach_r + LAND_GAP * size
    spot = [c[0] + r[0] * side - d[0] * reach_d, c[1] + r[1] * side - d[1] * reach_d]
    if eye is not None:
        # pull her toward the scene's front, along the camera's right, until she is in frame
        ex, ey = spot[0] - eye[0], spot[1] - eye[1]
        along = ex * d[0] + ey * d[1]
        if along > 1e-6:
            limit = along * math.tan(math.radians(FRAME_HALF_DEG))
            across = ex * r[0] + ey * r[1]
            if across > limit:
                spot = [spot[0] - r[0] * (across - limit), spot[1] - r[1] * (across - limit)]
    return (spot[0], spot[1], lo[2])


def message_spot(anchor, size, eye, stacked):
    """Where a message line goes: above ``anchor`` (her feet), one step higher per line already
    shown, leaning toward the camera at ``eye`` so she never hides it."""
    x, y, z = anchor
    lean = _xy_unit(eye[0] - x, eye[1] - y) if eye is not None else None
    if lean:
        x, y = x + lean[0] * MSG_LEAN * size, y + lean[1] * MSG_LEAN * size
    return (x, y, z + size * (1.15 + 0.25 * stacked))


def follow_boxes(boxes):
    """The boxes worth framing out of ``[(name, (lo, hi)), ...]`` for what a request made.

    Markers are dropped, and so is a backdrop (any side over BACKDROP_M) when anything smaller
    was made too: the station's first frame was taken from 86 m because its ground counted.
    """
    keep = [(n, b) for n, b in boxes if not any(n.startswith(m) for m in MARKERS + SHOW_PREFIXES)]
    if not keep:
        return []
    small = [(n, b) for n, b in keep
             if max(b[1][k] - b[0][k] for k in range(3)) <= BACKDROP_M]
    return small or keep


def ease(u):
    """Smoothstep: starts and stops gently, so a move never jerks at either end."""
    u = min(max(float(u), 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def glide_seconds(dist_from, dist_to, travel):
    """How long a glide takes: longer for a bigger move or zoom, between 0.8 and 2.0 seconds.

    ``travel`` is how far the point looked at moves; it is measured in units of the larger
    viewing distance, so crossing a room and crossing a street feel alike.
    """
    near, far = sorted((max(dist_from, 0.1), max(dist_to, 0.1)))
    zoom = math.log2(far / near)
    hop = travel / far
    return round(min(2.0, 0.8 + 0.35 * hop + 0.25 * zoom), 2)


def glide_distance(dist_from, dist_to, s):
    """The viewing distance part way through a glide, even in ratio: a 10x zoom feels steady."""
    a, b = max(dist_from, 1e-3), max(dist_to, 1e-3)
    return math.exp(math.log(a) * (1.0 - s) + math.log(b) * s)
