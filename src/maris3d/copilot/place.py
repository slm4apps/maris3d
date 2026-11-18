# SPDX-License-Identifier: Apache-2.0
"""Placement words in, metres out. Deterministic, no model, no bpy, no numpy.

Shipped copy of the maintainers' reference resolver (not part of this repository; keep the two in
step: the maintainers' scorer (not part of this repository)
and the compiler must give the same number). The model classifies; this file measures. The same file is used by the maintainers' POC scorer (not part of this repository) and by the
compiler that ships, so a number measured here is a number the compiler reproduces.

Conventions, all world space, Z up, floor at z = 0:
    left = -x, right = +x, front = -y (the room's open side), back = +y, up = +z
    "front_of X" is on X's -y side in WORLD space, never in X's local frame.

A box is {"lo": [x, y, z], "hi": [x, y, z]}; a size is the full extent [sx, sy, sz].

The gap ladder (section 3) is a *bucket*, so the resolver has to pick one gap per bucket. It
picks the bucket midpoint (GAP below). That choice is the floor on how close any resolved
placement can be to the authored one: see GAP_UNCERTAINTY.
"""
import math

RELATIONS = ("front_of", "behind", "left_of", "right_of", "next_to", "between",
             "on_top_of", "under", "against", "around", "centre_of")
DISTANCES = ("touching", "tiny", "small", "medium", "large", "far", "distant")

# spec section 3, verbatim: word -> (lo, hi) clear gap in metres
LADDER = {
    "touching": (0.00, 0.03),
    "tiny": (0.03, 0.10),
    "small": (0.10, 0.25),
    "medium": (0.25, 0.50),
    "large": (0.50, 1.00),
    "far": (1.00, 2.00),
    "distant": (2.00, float("inf")),
}
# one gap per bucket: the midpoint, i.e. the best a single word can do
GAP = {
    "touching": 0.015, "tiny": 0.065, "small": 0.175, "medium": 0.375,
    "large": 0.75, "far": 1.50, "distant": 2.50,
}
# how wrong the midpoint can be inside its own bucket (= half the bucket width)
GAP_UNCERTAINTY = {k: (0.0 if v[1] == float("inf") else (v[1] - v[0]) / 2.0)
                   for k, v in LADDER.items()}
GAP_UNCERTAINTY["distant"] = float("inf")

# relation -> (axis, sign) for the four signed axis relations. front = -y, back = +y.
AXIS = {"left_of": ("x", -1), "right_of": ("x", +1),
        "front_of": ("y", -1), "behind": ("y", +1)}

# `next_to` has no axis in the words, so the resolver needs a convention: beside the anchor on
# its +x side. `between` is resolved from the two anchors, not from this table.
NEXT_TO_AXIS = ("x", +1)

# `side` is the word the relation does not carry: which way across the relation axis the item sits.
# One word, world axes (left = -x, right = +x, front = -y, back = +y), diagonals allowed, and
# `side_gap` walks the same ladder as `distance`. Measured value (RELATIONS-DATA-GAP): without it
# the sideways residual is 0.46 m median on item anchors; with it, 0.075 m.
SIDES = {
    "left": (("x", -1),),
    "right": (("x", +1),),
    "front": (("y", -1),),
    "back": (("y", +1),),
    "front_left": (("y", -1), ("x", -1)),
    "front_right": (("y", -1), ("x", +1)),
    "back_left": (("y", +1), ("x", -1)),
    "back_right": (("y", +1), ("x", +1)),
}


def side_of(dx, dy, floor=0.03):
    """The `side` word for an authored offset from the anchor's centre line (None if centred)."""
    sx = "left" if dx < 0 else "right"
    sy = "front" if dy < 0 else "back"
    sx = sx if abs(dx) > floor else None
    sy = sy if abs(dy) > floor else None
    if sx and sy:
        return sy + "_" + sx
    return sx or sy


def bucket(gap):
    """The ladder word for a measured clear gap, from section 3."""
    if gap <= 0.03:
        return "touching"
    if gap < 0.10:
        return "tiny"
    if gap < 0.25:
        return "small"
    if gap < 0.50:
        return "medium"
    if gap < 1.00:
        return "large"
    if gap <= 2.00:
        return "far"
    return "distant"


def box_centre(b):
    return [(b["lo"][i] + b["hi"][i]) / 2.0 for i in range(3)]


def box_extent(b):
    return [b["hi"][i] - b["lo"][i] for i in range(3)]


def clear_gap(a, b, axis):
    """Clear space between two boxes along one axis; negative means they overlap on it."""
    i = "xyz".index(axis)
    if a["hi"][i] <= b["lo"][i]:
        return b["lo"][i] - a["hi"][i]
    if b["hi"][i] <= a["lo"][i]:
        return a["lo"][i] - b["hi"][i]
    return -min(a["hi"][i], b["hi"][i]) + max(a["lo"][i], b["lo"][i])


def overlap_fraction(subject, anchor, axis):
    """Fraction of the subject's footprint that overlaps the anchor's, on one horizontal axis."""
    i = "xy".index(axis)
    lo = max(subject["lo"][i], anchor["lo"][i])
    hi = min(subject["hi"][i], anchor["hi"][i])
    span = subject["hi"][i] - subject["lo"][i]
    if span <= 1e-9:
        return 0.0
    return max(0.0, hi - lo) / span


def yaw_towards(dx, dy):
    """Yaw (deg, about Z) that points the subject's local -y at (dx, dy)."""
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(dx, -dy))


def _clamp_into(box, zone):
    """Shift a box back inside the zone rectangle (x, y only). Nothing else is clamped."""
    if not zone:
        return box, 0.0
    moved = 0.0
    for i in (0, 1):
        lo, hi = box["lo"][i], box["hi"][i]
        if hi - lo > (zone["hi"][i] - zone["lo"][i]):
            continue                                   # item is wider than the zone: leave it
        d = 0.0
        if lo < zone["lo"][i]:
            d = zone["lo"][i] - lo
        elif hi > zone["hi"][i]:
            d = zone["hi"][i] - hi
        if d:
            box["lo"][i] += d
            box["hi"][i] += d
            moved += abs(d)
    return box, moved


def _push_out(box, obstacles, axis, step=0.02, limit=20.0, sign=1):
    """Move the subject away from the anchor along `axis` until it stops intersecting anything.

    The anchor itself is not in `obstacles`; the caller passes the other boxes the compiler
    already knows about. AABB test with a 5 cm tolerance, same tolerance the maintainers' C scorer (not part of this repository) used.
    """
    if not obstacles:
        return box, 0.0
    i_axis = "xyz".index(axis)
    moved = 0.0
    while moved < limit:
        hit = False
        for o in obstacles:
            depth = [min(box["hi"][i], o["hi"][i]) - max(box["lo"][i], o["lo"][i])
                     for i in range(3)]
            if all(d > 0.05 for d in depth):
                hit = True
                break
        if not hit:
            break
        # along the relation's own axis only, and away from the anchor. Before, this moved the
        # box on all three axes at once: a snowman put "left of the tree" beside a building rose
        # 1.2 m into the air while it slid (station demo).
        box["lo"][i_axis] += sign * step
        box["hi"][i_axis] += sign * step
        moved += step
    return box, moved


def _shifted(box, axis, by):
    out = {"lo": list(box["lo"]), "hi": list(box["hi"])}
    out["lo"][axis] += by
    out["hi"][axis] += by
    return out


def _free_spot(box, obstacles, rel, anchor, gap):
    """The nearest place that is free, when the place the words name is taken.

    At first there was one answer: slide away from the anchor until free. Beside a 11 m
    building that put a snowman "left of the tree" 13 m off, on the far side of the building, and
    three gifts "next to the snowman" beyond the tree (station demo, run 3). Now every way out is
    measured and the shortest wins:
      * away from the anchor along the relation's own axis (the old answer);
      * `next_to` / `against` say no side, so the anchor's other side is as good as the first;
      * sideways, both ways, keeping the side the words name (counted half as far again, so
        the relation's own axis wins when the two are about the same);
      * on / under / in the middle of a thing: any of the four ways across it.
    """
    obstacles = list(obstacles or ())
    if not obstacles or not _hits(box, obstacles):
        return box, 0.0
    tries = []
    if rel in AXIS or rel in ("next_to", "against"):
        axis, sign = AXIS.get(rel) or NEXT_TO_AXIS
        ai = "xyz".index(axis)
        tries.append((box, ai, sign, 1.0))
        if rel not in AXIS and anchor:                      # the other side of the anchor
            ext = box["hi"][ai] - box["lo"][ai]
            other = _shifted(box, ai, (anchor["lo"][ai] - gap - ext) - box["lo"][ai])
            if not _hits(other, obstacles):
                return other, 0.0
            tries.append((other, ai, -sign, 1.0))
        tries += [(box, 1 - ai, 1, 1.5), (box, 1 - ai, -1, 1.5)]
    else:
        tries = [(box, 0, 1, 1.0), (box, 0, -1, 1.0), (box, 1, 1, 1.0), (box, 1, -1, 1.0)]
    best = None
    for start, ai, sign, weight in tries:
        got, moved = _push_out({"lo": list(start["lo"]), "hi": list(start["hi"])}, obstacles,
                               "xyz"[ai], sign=sign)
        if _hits(got, obstacles):
            continue
        if best is None or moved * weight < best[2] - 1e-9:
            best = (got, moved, moved * weight)
    return (best[0], best[1]) if best else (box, 0.0)


def _hits(box, obstacles):
    for o in obstacles:
        if all(min(box["hi"][i], o["hi"][i]) - max(box["lo"][i], o["lo"][i]) > 0.05 for i in range(3)):
            return True
    return False


def resolve(place, anchor, size, zone=None, count=1, member=0, obstacles=(),
            anchor_kind="item"):
    """Resolve one place block to a world transform.

    place:        {"anchor", "relation", "distance", "facing"?, "arrangement"?}
    anchor:       {"lo":[..], "hi":[..]} of the anchor (item, zone rectangle or wall plane)
    size:         full extent [sx, sy, sz] of the recipe prototype the compiler is about to build
    zone:         {"lo":[..], "hi":[..]} of the zone rectangle, for the clamp
    count/member: which member of the arrangement this item is (0 for a single item)
    obstacles:    boxes already known to the compiler, for the collision push-out
    anchor_kind:  "item" | "zone" | "wall"

    Returns {"centre": [x,y,z], "yaw_deg": deg, "pushed": m, "clamped": m}.

    Conventions this file adds where the words are silent (all documented, all measured in the
    POC report):
      * perpendicular horizontal axis: the subject sits on the anchor's centre line;
      * z: the subject stands on the anchor's base (the floor), except on_top_of / under;
      * next_to: beside the anchor on +x;
      * row/stack spacing: the subject's own extent plus the gap word;
      * ring: count members at equal angles, starting at the anchor's front.
    """
    rel = place.get("relation") or "next_to"
    dist = place.get("distance") or "touching"
    g = GAP[dist]
    sx, sy, sz = [float(v) for v in size]
    a_lo, a_hi = anchor["lo"], anchor["hi"]
    ac = box_centre(anchor)
    a_ext = box_extent(anchor)

    # default: on the anchor's centre line, on its floor -- never below the ground (z = 0): Blender's
    # default cube reaches z = -1, and a whole street built beside it stood 1 m underground
    cx, cy, cz = ac[0], ac[1], max(a_lo[2], 0.0)
    yaw = 0.0

    # ---- ring: position comes from the count and the member index, not from the axis ----------
    if rel == "around" or (place.get("arrangement") or {}).get("kind") == "ring":
        n = max(1, int(count))
        radius = max(a_ext[0], a_ext[1]) / 2.0 + g + max(sx, sy) / 2.0
        theta = 2.0 * math.pi * (member % n) / n
        cx = ac[0] + radius * math.sin(theta)
        cy = ac[1] - radius * math.cos(theta)         # member 0 at the anchor's front
    elif rel == "centre_of":
        cx, cy = ac[0], ac[1]
    elif rel == "on_top_of":
        cx, cy = ac[0], ac[1]
        cz = a_hi[2] + g
    elif rel == "under":
        cx, cy = ac[0], ac[1]
        cz = a_lo[2] - g - sz
    elif rel == "between" and isinstance(place.get("between"), (list, tuple)) \
            and len(place["between"]) == 2 and place.get("between_boxes"):
        b1, b2 = place["between_boxes"]
        c1, c2 = box_centre(b1), box_centre(b2)
        cx, cy = (c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0
        yaw = yaw_towards(c2[0] - c1[0], c2[1] - c1[1])
    elif rel == "against" and anchor_kind == "wall":
        # stand the subject's back on the wall's inner face, on the wall's centre line
        thin = 0 if a_ext[0] < a_ext[1] else 1          # the wall is thin on this axis
        inward = 1.0 if ac[thin] < 0 else -1.0
        cx, cy = ac[0], ac[1]
        if thin == 0:
            cx = (a_hi[0] if inward < 0 else a_lo[0]) + inward * (g + sx / 2.0)
        else:
            cy = (a_hi[1] if inward < 0 else a_lo[1]) + inward * (g + sy / 2.0)
        yaw = yaw_towards(-inward if thin == 0 else 0.0, 0.0 if thin == 0 else -inward)
    else:
        axis, sign = AXIS.get(rel) or NEXT_TO_AXIS
        if rel == "against":                             # against a non-wall anchor: +x, touching
            axis, sign = NEXT_TO_AXIS
            g = min(g, GAP["tiny"])
        if axis == "x":
            cx = (a_hi[0] + g + sx / 2.0) if sign > 0 else (a_lo[0] - g - sx / 2.0)
            cy = ac[1]
        else:
            cy = (a_hi[1] + g + sy / 2.0) if sign > 0 else (a_lo[1] - g - sy / 2.0)
            cx = ac[0]

    # ---- arrangement offsets on top of the relation position ----------------------------------
    arr = place.get("arrangement") or {}
    kind = arr.get("kind") if isinstance(arr, dict) else None
    if member and kind == "row":
        long_axis = 0 if a_ext[0] >= a_ext[1] else 1        # the anchor's long axis
        step = (sx if long_axis == 0 else sy) + g
        if long_axis == 0:
            cx += step * member
        else:
            cy += step * member
    elif member and kind == "grid":
        cols = int(arr.get("cols") or max(1, int(round(math.sqrt(max(1, count))))))
        step_x, step_y = sx + g, sy + g
        cx += step_x * (member % cols)
        cy += step_y * (member // cols)
    elif member and kind == "stack":
        cz += (sz + g) * member

    # ---- facing -------------------------------------------------------------------------------
    facing = place.get("facing") or ""
    if ":" in facing:
        how, target = facing.split(":", 1)
        if how == "towards":
            yaw = yaw_towards(ac[0] - cx, ac[1] - cy)
        elif how == "away":
            yaw = yaw_towards(cx - ac[0], cy - ac[1])
        elif how == "along_wall":
            yaw = yaw_towards(ac[0] - cx, ac[1] - cy) + 90.0

    # ---- collision push-out, then clamp -------------------------------------------------------
    box = {"lo": [cx - sx / 2.0, cy - sy / 2.0, cz],
           "hi": [cx + sx / 2.0, cy + sy / 2.0, cz + sz]}
    box, pushed = _free_spot(box, obstacles, rel, anchor, g)
    box, clamped = _clamp_into(box, zone)
    c = box_centre(box)                                  # centre of the merged AABB (what C scored)
    return {"centre": [round(v, 6) for v in c], "yaw_deg": round(yaw % 360.0, 3),
            "pushed": round(pushed, 4), "clamped": round(clamped, 4)}
