# SPDX-License-Identifier: Apache-2.0
"""Where a part sits, in words; and the words back to metres. No model, no bpy.

The library says "the leg's centre is at -0.14, -0.14, 0.355". A planner must not write numbers
for positions (roadmap 2.P: numbers belong to code, words to the model), so a part's place is
said the way a person would:

    {"on": "StoolSeat", "relation": "under", "align": {"x": "left", "y": "front"}}

`describe(parts)` writes those words from sizes and centres; `resolve_parts(parts)` turns sizes
plus words back into centres, with parts touching exactly. The two are each other's inverse up
to snapping: a leg 2 cm in from a corner comes back flush with the corner.

A part here is {"name", "size": [x, y, z] full extent, "centre": [x, y, z]} (describe) or
{"name", "size", "place"} (resolve). The first part has no place: it stands on the floor.
Relations: on_top_of, under (z), left_of, right_of (x), front_of, behind (y), inside (the boxes
overlap on all three axes). `align` names, for each OTHER axis, which faces line up:
x: left | centre | right, y: front | centre | back, z: bottom | centre | top.
"""
RELATIONS = {"on_top_of": (2, 1), "under": (2, -1), "right_of": (0, 1), "left_of": (0, -1),
             "behind": (1, 1), "front_of": (1, -1), "inside": (None, 0)}
ALIGN_WORDS = (("left", "centre", "right"), ("front", "centre", "back"), ("bottom", "centre", "top"))
# Three words were not enough: only 39 of 103 objects came back within tolerance. A part
# may also sit part-way along its anchor: nine steps from one edge to the other, said as
# "<low word>_edge, <low>3, <low>2, <low>1, centre, <high>1, <high>2, <high>3, <high>_edge"
# (the part's CENTRE on that line), next to the two flush words (the part's FACE on the anchor's
# face). And two parts may be pushed into each other (snowman balls): `sunk` says how far.
STEPS = tuple(tuple([f"{lo}_edge", f"{lo}3", f"{lo}2", f"{lo}1", "centre", f"{hi}1", f"{hi}2", f"{hi}3", f"{hi}_edge"])
              for lo, _c, hi in ALIGN_WORDS)
SUNK = {"none": 0.0, "quarter": 0.25, "half": 0.5, "three_quarters": 0.75}
# A round part can lie on its side: a wheel is a cylinder whose axis points sideways, a boiler one
# whose axis points along the track. `axis` says which way the round shape's own axis points
# (x, y or z; z = standing, the default, never written). `size` is always the box as the part
# sits, so the words that place it do not change. A box needs no such word: turned by a quarter
# it is just a box with other sides.
ROUND = ("cylinder", "cone", "torus")
AXIS_TURN = {"x": [0.0, 90.0, 0.0], "y": [90.0, 0.0, 0.0]}     # rotation_deg that lays the z axis along x / y


def turned(rotation_deg):
    """Where a part's own x, y, z axes point after rotation_deg (Blender XYZ euler): 3 unit vectors."""
    import math
    rx, ry, rz = [math.radians(float(v)) for v in (list(rotation_deg or []) + [0, 0, 0])[:3]]
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    rows = [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]]
    return [[rows[r][c] for r in range(3)] for c in range(3)]      # column c = where local axis c points


def axis_of(rotation_deg):
    """'x', 'y' or 'z': where the part's own z axis points; None when it is tilted (not a quarter turn)."""
    z = turned(rotation_deg)[2]
    for i, name in enumerate(AXES_NAMES):
        if abs(abs(z[i]) - 1.0) < 1e-3:
            return name
    return None


def box_after(dims, rotation_deg):
    """The box a part of its own `dims` fills once turned (exact for quarter turns)."""
    cols = turned(rotation_deg)
    return [round(sum(abs(cols[c][r]) * float(dims[c]) for c in range(3)), 4) for r in range(3)]


AXES_NAMES = "xyz"


def _positions(axis, size, anchor_centre, anchor_size):
    """{word: centre} for every way a part of this size can be said to sit along one axis."""
    lo, ext = anchor_centre - anchor_size / 2.0, anchor_size
    out = {ALIGN_WORDS[axis][0]: lo + size / 2.0, ALIGN_WORDS[axis][2]: lo + ext - size / 2.0}
    for k, word in enumerate(STEPS[axis]):
        out.setdefault(word, lo + ext * k / 8.0)
    return out
AXES = "xyz"
TOUCH = 0.03


def _box(part):
    c, s = part["centre"], part["size"]
    return [c[i] - s[i] / 2.0 for i in range(3)], [c[i] + s[i] / 2.0 for i in range(3)]


def _gap(a, b, i):
    """Distance between two boxes on axis i (negative = they overlap by that much)."""
    (alo, ahi), (blo, bhi) = a, b
    return max(alo[i] - bhi[i], blo[i] - ahi[i])


def _touching(a, b):
    return all(_gap(a, b, i) <= TOUCH for i in range(3))


def _contact(a, b):
    """How much two touching boxes share: the product of their overlaps on the axes they overlap."""
    area = 1.0
    for i in range(3):
        g = _gap(a, b, i)
        if g < 0:
            area *= -g
    return area


def order(parts):
    """The parts so that each one touches a part before it: the biggest first (the seat, the
    walls, the body: what a person names first), then outwards, bigger parts before smaller."""
    parts = list(parts)
    if not parts:
        return []
    vol = lambda p: p["size"][0] * p["size"][1] * p["size"][2]
    first = max(range(len(parts)), key=lambda k: vol(parts[k]))
    done, rest = [parts[first]], [p for k, p in enumerate(parts) if k != first]
    while rest:
        near = [p for p in rest if any(_touching(_box(p), _box(d)) for d in done)]
        pick = max(near, key=vol) if near else rest[0]
        done.append(pick)
        rest.remove(pick)
    return done


def _align_word(axis, part_box, anchor_box):
    (plo, phi), (alo, ahi) = part_box, anchor_box
    centre, size = (plo[axis] + phi[axis]) / 2.0, phi[axis] - plo[axis]
    options = _positions(axis, size, (alo[axis] + ahi[axis]) / 2.0, ahi[axis] - alo[axis])
    plain = ("centre",) + (ALIGN_WORDS[axis][0], ALIGN_WORDS[axis][2])        # the plain word wins a tie
    return min(options, key=lambda w: (round(abs(options[w] - centre), 4), plain.index(w) if w in plain else 9))


def describe(parts):
    """Parts with centres -> the same parts, ordered, each with a `place` in words (no centre)."""
    out, placed = [], []
    for part in order(parts):
        entry = {k: v for k, v in part.items() if k != "centre"}
        box = _box(part)
        near = [d for d in placed if _touching(box, _box(d))]
        if near:
            # the biggest thing it touches is what a person would name ("under the seat"), unless
            # the contact with it is a sliver
            best = max(_contact(box, _box(d)) for d in near)
            anchor = max((d for d in near if _contact(box, _box(d)) >= 0.5 * best),
                         key=lambda d: d["size"][0] * d["size"][1] * d["size"][2])
            abox = _box(anchor)
            # the axis on which the part mostly sticks OUT of its anchor is the relation; a part
            # whose centre is within the anchor on every axis is inside it
            depth = [-_gap(box, abox, i) / max(min(part["size"][i], anchor["size"][i]), 1e-6) for i in range(3)]
            out_of = [i for i in range(3) if depth[i] < 0.8
                      and abs(part["centre"][i] - anchor["centre"][i]) > anchor["size"][i] / 2.0 - 1e-6]
            sunk = None
            if out_of:
                axis = min(out_of, key=lambda i: (i != 2, depth[i]))            # up/down wins a corner contact
                sign = 1 if part["centre"][axis] >= anchor["centre"][axis] else -1
                relation = next(w for w, (a, s) in RELATIONS.items() if a == axis and s == sign)
                others = [i for i in range(3) if i != axis]
                sunk = min(SUNK, key=lambda w: abs(SUNK[w] - max(depth[axis], 0.0)))
            else:
                relation, others = "inside", [0, 1, 2]
            entry["place"] = {"on": anchor["name"], "relation": relation,
                              "align": {AXES[i]: _align_word(i, box, abox) for i in others}}
            if sunk and sunk != "none":
                entry["place"]["sunk"] = sunk
        elif placed:                                  # touches nothing before it: beside the first part
            entry["place"] = {"on": placed[0]["name"], "relation": "right_of", "align": {"y": "centre", "z": "bottom"}}
        out.append(entry)
        placed.append(part)
    return out


def resolve_parts(parts):
    """Parts with sizes and place words -> the same parts with centres; the object stands on the
    floor (lowest face at z = 0) with the middle of its footprint at x = y = 0."""
    done = {}
    out = []
    for part in parts:
        size = [float(v) for v in part["size"]]
        place = part.get("place") or {}
        anchor = done.get(place.get("on"))
        if anchor is None:
            centre = [0.0, 0.0, size[2] / 2.0] if not out else \
                [out[-1]["centre"][0] + out[-1]["size"][0] / 2.0 + size[0] / 2.0, out[-1]["centre"][1], size[2] / 2.0]
        else:
            ac, asz = anchor["centre"], anchor["size"]
            axis, sign = RELATIONS.get(place.get("relation"), (None, 0))
            centre = list(ac)
            if axis is not None:
                into = SUNK.get(place.get("sunk"), 0.0) * min(asz[axis], size[axis])
                centre[axis] = ac[axis] + sign * ((asz[axis] + size[axis]) / 2.0 - into)
            align = place.get("align") or {}
            for i in range(3):
                if i == axis:
                    continue
                centre[i] = _positions(i, size[i], ac[i], asz[i]).get(align.get(AXES[i], "centre"), ac[i])
        entry = dict(part, size=size, centre=centre)
        out.append(entry)
        done[part["name"]] = entry
    if out:
        lo = [min(p["centre"][i] - p["size"][i] / 2.0 for p in out) for i in range(3)]
        hi = [max(p["centre"][i] + p["size"][i] / 2.0 for p in out) for i in range(3)]
        shift = [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]]
        for p in out:
            p["centre"] = [round(p["centre"][i] - shift[i], 4) for i in range(3)]
    return out


def extent(parts):
    """Full size [x, y, z] of an object from its parts."""
    return [round(max(p["centre"][i] + p["size"][i] / 2.0 for p in parts)
                  - min(p["centre"][i] - p["size"][i] / 2.0 for p in parts), 4) for i in range(3)]


def floating(parts):
    """Names of parts that touch no other part (an object with one is not built right)."""
    boxes = [(p["name"], _box(p)) for p in parts]
    return [n for n, b in boxes if len(boxes) > 1 and not any(_touching(b, o) for m, o in boxes if m != n)]


def round_trip(parts):
    """describe -> resolve, and how far every part moved from where it was (both recentred).
    Returns (worst distance in metres, names of floating parts, the resolved parts)."""
    lo = [min(p["centre"][i] - p["size"][i] / 2.0 for p in parts) for i in range(3)]
    hi = [max(p["centre"][i] + p["size"][i] / 2.0 for p in parts) for i in range(3)]
    shift = [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]]
    was = {p["name"]: [p["centre"][i] - shift[i] for i in range(3)] for p in parts}
    got = resolve_parts(describe(parts))
    worst = max(max(abs(p["centre"][i] - was[p["name"]][i]) for i in range(3)) for p in got)
    return worst, floating(got), got


# What the parts planner is told. Stored here once so the training data
# (the maintainers' training-data builder, not part of this repository) and the product send the same bytes.
PARTS_SHAPES = ("cube", "cylinder", "cone", "ico", "uv_sphere", "torus")
PARTS_COLORS = ("black", "brass", "brick", "cream", "green", "metal", "navy", "oak", "pine", "red", "rust",
                "snow", "teal", "terra", "timber", "walnut", "white", "grey", "blue", "yellow", "glass", "orange",
                "water", "skin", "pink", "brown")
# colours the library's material table cannot give (a see-through one, or one it never had): the
# material itself, so a designed part does not depend on the library
PARTS_MATERIALS = {
    "water": {"name": "Water", "color": [0.15, 0.45, 0.85], "alpha": 0.55, "roughness": 0.05},
    "glass": {"name": "Glass", "color": [0.85, 0.93, 0.95], "alpha": 0.3, "roughness": 0.05},
    "skin": {"name": "Skin", "color": [0.87, 0.67, 0.55], "roughness": 0.6},
    "pink": {"name": "Pink", "color": [0.95, 0.55, 0.65], "roughness": 0.6},
    "brown": {"name": "Brown", "color": [0.36, 0.22, 0.12], "roughness": 0.7},
    "yellow": {"name": "Yellow", "color": [0.95, 0.8, 0.15], "roughness": 0.6},
    "blue": {"name": "Blue", "color": [0.15, 0.3, 0.8], "roughness": 0.6},
    "orange": {"name": "Orange", "color": [0.95, 0.5, 0.1], "roughness": 0.6},
    "grey": {"name": "Grey", "color": [0.5, 0.5, 0.5], "roughness": 0.6},
    "black": {"name": "Black", "color": [0.03, 0.03, 0.03], "roughness": 0.5},
    "white": {"name": "White", "color": [0.9, 0.9, 0.88], "roughness": 0.5},
    "cream": {"name": "Cream", "color": [0.93, 0.87, 0.72], "roughness": 0.6},
    "snow": {"name": "Snow", "color": [0.95, 0.96, 0.98], "roughness": 0.8},
    "red": {"name": "Red", "color": [0.8, 0.08, 0.08], "roughness": 0.5},
    "green": {"name": "Green", "color": [0.12, 0.5, 0.18], "roughness": 0.6},
    "teal": {"name": "Teal", "color": [0.05, 0.5, 0.5], "roughness": 0.6},
    "navy": {"name": "Navy", "color": [0.05, 0.08, 0.3], "roughness": 0.6},
    "brick": {"name": "Brick", "color": [0.6, 0.22, 0.15], "roughness": 0.9},
    "terra": {"name": "Terracotta", "color": [0.75, 0.4, 0.25], "roughness": 0.9},
    "rust": {"name": "Rust", "color": [0.55, 0.25, 0.1], "roughness": 0.8},
    "oak": {"name": "Oak", "color": [0.6, 0.42, 0.24], "roughness": 0.7},
    "pine": {"name": "Pine", "color": [0.78, 0.62, 0.38], "roughness": 0.7},
    "timber": {"name": "Timber", "color": [0.45, 0.3, 0.18], "roughness": 0.8},
    "walnut": {"name": "Walnut", "color": [0.28, 0.17, 0.09], "roughness": 0.8},
    "brass": {"name": "Brass", "color": [0.8, 0.6, 0.2], "roughness": 0.3, "metallic": 1.0},
    "metal": {"name": "Metal", "color": [0.6, 0.62, 0.65], "roughness": 0.35, "metallic": 1.0},
}
# How a part is finished after it is built (checked in Blender; smoothing turns a built shape
# into a rounded, organic one):
#   finish  smooth = edges rounded, surface subdivided, smooth shading; sharp = left as built.
#           On the object it is the default for every part; on a part it wins.
#   skin    parts that carry the same skin word are melted into ONE surface (a head into a body);
#           a part without it stays its own piece (eyes, a hat) with its own colour.
#   hollow  open_top = the part is a vessel: hollowed from above, a wall and a floor are left
#           (a cup, a bowl, a box); what stands `inside` it (water) sits in the hollow.
FINISHES = ("smooth", "sharp")
HOLLOWS = ("open_top",)
HOLLOW_SHAPES = ("cube", "cylinder", "cone")
HOLLOW_WALL = 0.12          # wall and floor thickness, fraction of the part's smaller width
PARTS_SYSTEM = (
    "You design one object for a Blender scene builder as a list of simple parts. Reply with one JSON "
    'object only: {"object":<name>,"size":[x,y,z],"parts":[{"name":<PartName>,"shape":<shape>,"size":[x,y,z],'
    '"axis":<x|y>,"color":<color>,"place":{"on":<earlier part>,"relation":<word>,"align":{<axis>:<word>},"sunk":<word>}}]}. '
    "Shapes: " + ", ".join(PARTS_SHAPES) + ". Colors: " + ", ".join(PARTS_COLORS) + ". "
    "size is the full extent in metres along x (left-right), y (front-back), z (up): of the whole object "
    "at the top, of the part in each part, always as the part sits. axis (only for a cylinder, cone "
    "or torus lying on its side, like a wheel): x or y, the way its own axis points. "
    "The first part is the biggest and has no place. Every other part is placed on an earlier part: "
    "relation is one of " + ", ".join(RELATIONS) + "; align says, for each other axis, where it "
    "sits along that part: left or right (x), front or back (y), bottom or top (z) when the faces are "
    "flush, else a step from one edge to the other: " + ", ".join(STEPS[0]) + "; the same steps with "
    "front/back for y and bottom/top for z. sunk (only when the parts are pushed "
    "into each other): quarter, half, three_quarters. Never output coordinates. "
    "Optional: finish (on the object for all parts, or on one part): " + ", ".join(FINISHES) + "; skin "
    "(a word; parts with the same skin word are melted into one surface); hollow (only "
    + ", ".join(HOLLOW_SHAPES) + "): " + ", ".join(HOLLOWS) + "."
)


SIZE_TOL = 0.05          # the stated whole size against the built size, fraction of the largest side


def check_answer(answer):
    """(faults, resolved parts) for one parsed parts-planner answer; no faults = it can be built.
    The maintainers' scorer (not part of this repository) and the product (to_recipe) ask the same question here."""
    if not isinstance(answer, dict) or not isinstance(answer.get("parts"), list) or not answer["parts"]:
        return ["no parts"], []
    faults, parts, seen = [], answer["parts"], set()
    for k, p in enumerate(parts):
        if not isinstance(p, dict) or not p.get("name") or not isinstance(p["name"], str):
            return ["part without a name"], []
        size = p.get("size")
        if not (isinstance(size, list) and len(size) == 3
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in size)):
            return [f"{p['name']}: size is not three positive numbers"], []
        if p.get("shape") not in PARTS_SHAPES:
            faults.append(f"{p['name']}: shape {p.get('shape')!r}")
        if p.get("color") not in PARTS_COLORS:
            faults.append(f"{p['name']}: color {p.get('color')!r}")
        if "axis" in p and (p["axis"] not in ("x", "y", "z") or p.get("shape") not in ROUND):
            faults.append(f"{p['name']}: axis {p['axis']!r} on a {p.get('shape')}")
        if p["name"] in seen:
            faults.append(f"{p['name']}: name used twice")
        if "finish" in p and p["finish"] not in FINISHES:
            faults.append(f"{p['name']}: finish {p['finish']!r}")
        if "skin" in p and not (isinstance(p["skin"], str) and p["skin"].isalnum()):
            faults.append(f"{p['name']}: skin {p['skin']!r}")
        if "hollow" in p and (p["hollow"] not in HOLLOWS or p.get("shape") not in HOLLOW_SHAPES):
            faults.append(f"{p['name']}: hollow {p['hollow']!r} on a {p.get('shape')}")
        place = p.get("place")
        if k == 0:
            if place:
                faults.append("first part has a place")
        elif not isinstance(place, dict):
            faults.append(f"{p['name']}: no place")
        else:
            if place.get("on") not in seen:
                faults.append(f"{p['name']}: on {place.get('on')!r} is not an earlier part")
            if place.get("relation") not in RELATIONS:
                faults.append(f"{p['name']}: relation {place.get('relation')!r}")
            align = place.get("align") if isinstance(place.get("align"), dict) else {}
            for axis, word in align.items():
                i = AXES.find(axis) if axis in ("x", "y", "z") else -1
                if i < 0 or word not in ALIGN_WORDS[i] + STEPS[i]:
                    faults.append(f"{p['name']}: align {axis}={word!r}")
            if "sunk" in place and place["sunk"] not in SUNK:
                faults.append(f"{p['name']}: sunk {place['sunk']!r}")
            if any(key in place for key in ("location", "centre", "position", "offset")):
                faults.append(f"{p['name']}: a coordinate in the place")
        seen.add(p["name"])
    if "finish" in answer and answer["finish"] not in FINISHES:
        faults.append(f"finish {answer['finish']!r}")
    if any("is not an earlier part" in f or "no place" in f for f in faults):
        return faults, []
    built = resolve_parts(parts)
    loose = floating(built)
    if loose:
        faults.append("floating: " + ", ".join(loose))
    size = answer.get("size")
    if isinstance(size, list) and len(size) == 3 and all(isinstance(v, (int, float)) for v in size):
        ext = extent(built)
        if max(abs(ext[i] - size[i]) for i in range(3)) > SIZE_TOL * max(max(ext), 1e-6):
            faults.append(f"stated size {size} is not the built size {ext}")
    else:
        faults.append("no whole size")
    return faults, built


def _one_word(name):
    words = [w for w in "".join(c if c.isalnum() else " " for c in str(name)).split() if w]
    out = "".join(w[:1].upper() + w[1:] for w in words)
    return out if out and not out[0].isdigit() else "Part" + out


def to_recipe(answer):
    """A parts-planner answer -> (recipe in the shape of an entry of recipes.RECIPES, None), or
    (None, why not). The words become metres here (resolve_parts); the model wrote no position.

    Only the faults that stop a build refuse the answer (an `on` that names nothing, a floating
    part, a broken size). An unknown colour is painted grey and a wrong whole size is replaced by
    the built one: the answer is still an object.
    """
    from .recipes import MATERIALS
    faults, built = check_answer(answer)
    # a wrong finish word costs the finish, not the object
    soft = (": color ", ": finish ", ": skin ", ": hollow ")
    fatal = [f for f in faults if not (any(w in f for w in soft) or f.startswith(("stated size", "finish "))
                                       or f == "no whole size")]
    if fatal or not built:
        return None, "; ".join(fatal or faults)[:300]
    materials = {}
    for key, mat in MATERIALS.items():
        for color in PARTS_COLORS:
            if color in key.lower() or color in str(mat.get("name", "")).lower():
                materials.setdefault(color, key)
    r3 = lambda v: round(float(v), 3)
    parts, names = [], set()
    for p in built:
        x, y, z = [r3(v) for v in p["size"]]
        name = _one_word(p["name"])
        while name in names:
            name += "B"
        names.add(name)
        shape = p["shape"]
        part = {"name": name, "offset": [r3(v) for v in p["centre"]],
                "material": PARTS_MATERIALS.get(p.get("color")) or materials.get(p.get("color"))}
        finish = p.get("finish") if p.get("finish") in FINISHES else answer.get("finish")
        if finish == "smooth":
            part["finish"] = "smooth"
        if isinstance(p.get("skin"), str) and p["skin"].isalnum():
            part["skin"] = p["skin"]
        if p.get("hollow") in HOLLOWS and shape in HOLLOW_SHAPES:
            part["hollow"] = p["hollow"]
        # a round part lying on its side: its own length is the box side along `axis`, its
        # roundness the other two; the harness states the turn (compile_plan.check_part)
        axis = p.get("axis") if shape in ROUND and p.get("axis") in AXIS_TURN else None
        if axis:
            i = AXES.index(axis)
            x, y, z = [v for k, v in enumerate((x, y, z)) if k != i] + [(x, y, z)[i]]
            part["rotation_deg"] = list(AXIS_TURN[axis])
        if shape in ("cylinder", "cone"):
            r = r3((x + y) / 4.0)
            part.update(shape=shape, radius=r, depth=z, dims=[r3(2 * r), r3(2 * r), z])
        elif shape == "torus":
            minor = r3(z / 2.0)
            major = r3(max((x + y) / 4.0 - minor, minor))
            part.update(shape=shape, major=major, minor=minor,
                        dims=[r3(2 * (major + minor)), r3(2 * (major + minor)), r3(2 * minor)])
        else:                       # cube; and a sphere of any proportions is a scaled ico sphere
            part.update(shape="cube" if shape == "cube" else "ico", scale=[r3(x / 2.0), r3(y / 2.0), r3(z / 2.0)],
                        dims=[x, y, z])
        parts.append(part)
    title = _one_word(answer.get("object") or parts[0]["name"])
    return {"title": title, "size": [r3(v) for v in extent(built)], "parts": parts, "designed": True}, None
