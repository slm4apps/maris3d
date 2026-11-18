# SPDX-License-Identifier: Apache-2.0
"""Apply the change answer to things the copilot has built. No model, no bpy, NO LANGUAGE.

The planner reads the user's sentence; this module reads only its structured answer:

    {"kind": "change", "changes": [{"do": "scale", "object": "Chair", "parts": ["ChairLeg1"],
                                    "by": {"z": 2}}, ...]}

and applies it with lookup and arithmetic: an exact name is looked up (an unknown one is an error
that is reported, never matched fuzzily or guessed), sizes are multiplied, the parts are laid out
again from their place words (describe_parts.resolve_parts), places go through place.resolve, a
facing through place.yaw_towards. The output is the tool calls and the new stored specs; `check`
reads the scene back and says, per change, ok / wrong / not-checked. It never corrects silently.

A stored spec is one built thing in the parts planner's form plus where it stands:

    {"id": "Chair", "object": "Chair", "size": [x, y, z],
     "parts": [{"name", "shape", "size", "color", "place"?, "axis"?, "centre"}, ...],   # words + metres
     "at": [x, y, z], "yaw": degrees,      # the empty that is the thing's parent
     "q": [x, y, z],                       # from the empty to the origin of the parts' own frame
     "pins": {part: [x, y, z, yaw]}}       # the empty's pose when that part was parented to it

A part's own location in Blender (its basis, which is what set_transform writes) is
pin_at + Rz(pin_yaw) * (centre + q); the part's place in the world is at + Rz(yaw) * (centre + q).
"""
import copy
import re
import math

from . import compile_plan as CP
from . import describe_parts as DP
from . import place as PLACE

KINDS = ("change", "build", "question", "cannot")
DOS = ("remove", "recolor", "scale", "move", "turn", "add", "copy", "rename", "shape")
COMPASS = {"north": (0.0, 1.0), "south": (0.0, -1.0), "east": (1.0, 0.0), "west": (-1.0, 0.0)}
FACING = {0: "south", 90: "east", 180: "north", 270: "west"}      # yaw 0 = the front (-y) looks south
PART_KEYS = ("name", "shape", "size", "color", "place", "axis", "finish", "skin", "hollow") + DP.NEXT_PART_KEYS
EPS = 1e-3

# What the edit model is told: the same bytes the edit data was made with (edit sets 1 and 2), so
# the product sends exactly what the adapter was trained on. The data builder imports this.
EDIT_COLORS = ["black", "brass", "brick", "cream", "green", "metal", "navy", "oak", "pine", "red", "rust",
               "snow", "teal", "terra", "timber", "walnut", "white", "grey", "blue", "yellow", "glass",
               "orange", "water", "skin", "pink", "brown"]
CHANGE_SYSTEM = (
    "You edit things already built in a Blender scene. Input: Scene (a line per thing: Name (noun) size at x y facing "
    "<compass word>: parts as name shape x y z colour), Last (thing last built or changed), Request. "
    'Reply with one JSON object only: {"kind":"change|build|question|cannot","say":<one sentence, question and cannot only>,'
    '"changes":[...]}. A change has do, object (exact thing name) and, for some parts only, parts (exact part names); '
    "no parts = the whole thing. do: remove; recolor (color, optional finish smooth|sharp); "
    'scale (by {x,y,z} factors, only the axes asked; "bigger" 1.5, "smaller" 0.67, "a bit" 1.2 / 0.83); '
    "move (place {anchor,relation,distance} or shift {x|y|z} metres: left -x, right +x, front -y, back +y, up +z); "
    "turn (by degrees, left +, right -, or face <thing|north|south|east|west>); "
    "add (parts: name, shape, size [x,y,z], color, place {on <existing part>,relation,align,sunk}); copy (count, optional place); "
    "rename (to). \"all the X\" and \"both\" = one change per thing; \"it\", \"the red one\", \"the second X\" "
    "become exact names. A new thing to make: kind build, changes []. A part or thing the scene lacks, or an unclear one: "
    "kind question, say asks which. Something no change can do: kind cannot. Colours: " + ", ".join(EDIT_COLORS)
    + ". Relations: front_of, behind, left_of, right_of, next_to, on_top_of, under, against. Distances: touching to distant."
)


class ChangeError(Exception):
    """One change cannot be applied; the message says why (it goes to the panel)."""


class Applied:
    def __init__(self):
        self.kind = None
        self.say = ""
        self.calls = []        # the tool calls, in order
        self.specs = {}        # the stored specs after the change
        self.errors = []       # [{"change": index or None, "do", "object", "error"}]
        self.expected = []     # one dict per change: what `check` reads back (or {"error": ...})
        self.notes = []

    @property
    def ok(self):
        return not self.errors


# ---- small arithmetic -----------------------------------------------------------------------

def _rz(deg, v):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [c * v[0] - s * v[1], s * v[0] + c * v[1], v[2]]


def _r4(v):
    return [round(float(x), 4) for x in v]


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _world(spec, centre):
    """Where a point of the thing's own frame is in the world."""
    p = _rz(spec["yaw"], [centre[i] + spec["q"][i] for i in range(3)])
    return [spec["at"][i] + p[i] for i in range(3)]


def _basis(spec, name, centre):
    """What set_transform must write for the part to be at `centre`: its location under its parent."""
    pin = spec["pins"].get(name) or spec["pins"]["*"]
    p = _rz(pin[3], [centre[i] + spec["q"][i] for i in range(3)])
    return _r4([pin[i] + p[i] for i in range(3)])


def _local_order(part):
    """Which box axis each of the part's OWN axes is (a round part lying on its side; a prism's own
    axes are tip, base, ridge)."""
    if part.get("shape") == "prism":
        return [2, 0, 1] if part.get("axis") == "y" else [2, 1, 0]
    i = "xyz".find(part.get("axis") or "z")
    i = 2 if i < 0 else i
    return [k for k in range(3) if k != i] + [i]


def _local(part, v):
    return [v[k] for k in _local_order(part)]


def _own(part):
    """The size the part is built at (a leaning part's own size; else its box)."""
    return part.get("own") or part["size"]


def _local_dims(part):
    return _r4(part["own"]) if part.get("own") else _r4(_local(part, part["size"]))


def _spec_box(spec):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for p in spec["parts"]:
        for sx in (-.5, .5):
            for sy in (-.5, .5):
                for sz in (-.5, .5):
                    w = _world(spec, [p["centre"][0] + sx * p["size"][0], p["centre"][1] + sy * p["size"][1],
                                      p["centre"][2] + sz * p["size"][2]])
                    lo = [min(lo[i], w[i]) for i in range(3)]
                    hi = [max(hi[i], w[i]) for i in range(3)]
    return {"lo": lo, "hi": hi}


def _foot(spec):
    """The middle of the thing's footprint on its lowest face, in the parts' own frame."""
    lo = [min(p["centre"][i] - p["size"][i] / 2.0 for p in spec["parts"]) for i in range(3)]
    hi = [max(p["centre"][i] + p["size"][i] / 2.0 for p in spec["parts"]) for i in range(3)]
    return [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]]


def _centre_xy(spec):
    """The middle of the footprint, in the world."""
    return _world(spec, _foot(spec))


# ---- specs from what was built ----------------------------------------------------------------

def _color_of(material):
    if isinstance(material, dict):
        return next((c for c, m in DP.PARTS_MATERIALS.items() if m == material), str(material.get("name", "")).lower() or None)
    return material


def spec_from_inst(inst):
    """The stored spec of an instance compile_plan.layout made (a recipe's parts with offsets):
    sizes as the parts sit, places in words (describe_parts.describe), centres back in metres."""
    raw = []
    for p in inst["parts"]:
        rot = p.get("rotation_deg")
        axis = DP.axis_of(rot) if rot else None
        part = {"name": p["name"], "shape": p["shape"], "color": _color_of(p.get("material")),
                "size": DP.box_after(p["dims"], rot) if rot else [float(v) for v in p["dims"]],
                "centre": [float(v) for v in p["offset"]]}
        if axis in ("x", "y") and p["shape"] in DP.ROUND:
            part["axis"] = axis
        for key in ("finish", "skin", "hollow"):
            if p.get(key):
                part[key] = p[key]
        raw.append(part)
    # the centres stay what was BUILT (the recipe's offsets); the words are what a person would say
    # of them, and describe is exact only to a few cm
    centres = {p["name"]: p["centre"] for p in raw}
    parts = [dict(w, centre=list(centres[w["name"]])) for w in DP.describe(raw)]
    return _spec(inst["id"], inst.get("title") or inst["id"], parts, inst["origin"])


def spec_from_answer(answer, thing_id, at):
    """The stored spec of a thing built from a parts-planner answer standing at `at`."""
    faults, built = DP.check_answer(answer)
    if not built:
        raise ChangeError("; ".join(faults))
    return _spec(thing_id, answer.get("object") or thing_id, built, at)


def _spec(thing_id, noun, parts, at):
    """`parts`: words, sizes and the centres the parts were built at, in the frame of the empty."""
    at = [float(v) for v in at]
    return {"id": thing_id, "object": noun, "size": DP.extent(parts), "parts": parts, "at": at, "yaw": 0.0,
            "q": [0.0, 0.0, 0.0], "pins": {"*": at + [0.0], **{p["name"]: at + [0.0] for p in parts}}}


def _sync(spec, scene):
    """Take the thing's pose from the scene when the scene has it (the user may have moved it)."""
    for o in scene or []:
        if o.get("name") == spec["id"] and isinstance(o.get("loc"), list) and len(o["loc"]) == 3:
            spec["at"] = [float(v) for v in o["loc"]]
            rot = o.get("rot_deg")
            if isinstance(rot, list) and len(rot) == 3:
                spec["yaw"] = float(rot[2]) % 360.0
                if spec.get("solo"):
                    spec["rot"] = _r4(rot)
            if spec.get("solo"):
                _solo_refresh(spec)
            return


# ---- what the planner is shown -----------------------------------------------------------------

def fmt(x):
    """A number as the edit data writes it: at most 3 decimals, no trailing zeros, 1.0 -> 1."""
    x = round(float(x), 3)
    if x == int(x):
        return str(int(x))
    return ("%.3f" % x).rstrip("0").rstrip(".")


def noun_of(name):
    """The noun as the edit data writes it: FloorLamp, floor_lamp -> floor lamp."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name)).replace("_", " ")
    return " ".join(words.lower().split())


def scene_text(specs, last=None):
    """The scene as the edit model's input, one line per thing, byte for byte the edit data's
    format: data only, no sentence."""
    lines = ["Scene:"]
    for s in specs.values():
        face = FACING.get(int(round(s["yaw"])) % 360, f"{round(s['yaw'])} degrees")
        parts = "; ".join(f"{p['name']} {p['shape']} {' '.join(fmt(v) for v in p['size'])} {p.get('color')}"
                          for p in s["parts"])
        lines.append(f"{s['id']} ({noun_of(s['object'])}) size {' '.join(fmt(v) for v in s['size'][:3])} at "
                     f"{fmt(s['at'][0])} {fmt(s['at'][1])} facing {face}: {parts}")
    if last is None and specs:          # the data always names one: the newest thing
        last = list(specs)[-1]
    if last:
        lines.append(f"Last: {last}")
    return "\n".join(lines)


def change_messages(specs, request, last=None):
    return [{"role": "system", "content": CHANGE_SYSTEM},
            {"role": "user", "content": scene_text(specs, last) + f"\nRequest: {request}"}]


# ---- the context of one answer -----------------------------------------------------------------

class _Ctx:
    def __init__(self, specs, scene):
        self.specs, self.scene = specs, list(scene or [])
        for s in self.specs.values():
            _sync(s, self.scene)

    def taken(self):
        """Every name in use: objects in the scene, things and their parts."""
        names = {o.get("name") for o in self.scene}
        for s in self.specs.values():
            names.add(s["id"])
            names.update(p["name"] for p in s["parts"])
        return names

    def boxes(self):
        """Boxes a place word may name. Built things come from their specs (they are kept up to
        date through a batch), the rest from the scene; the parts of a built thing are not obstacles."""
        member = {p["name"]: s["id"] for s in self.specs.values() for p in s["parts"]}
        boxes = {n: b for n, b in CP.scene_boxes(self.scene, {s["id"]: [p["name"] for p in s["parts"]]
                                                              for s in self.specs.values()}).items()}
        things = {n: b for n, b in boxes.items() if n not in member}
        for s in self.specs.values():
            things[s["id"]] = _spec_box(s)
        return things, {n: b for n, b in boxes.items() if n in member}


def _thing(ctx, name):
    if not isinstance(name, str) or name not in ctx.specs:
        raise ChangeError(f"unknown object {name!r}; the scene has: " + ", ".join(ctx.specs))
    return ctx.specs[name]


def _part_names(spec, change):
    """The exact part names the change is about, or None for the whole thing."""
    if change.get("parts") is None:
        return None
    names = change["parts"]
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ChangeError("parts must be a list of part names")
    have = {p["name"] for p in spec["parts"]}
    unknown = [n for n in names if n not in have]
    if unknown:
        raise ChangeError(f"unknown part {unknown[0]!r} of {spec['id']}; its parts are: " + ", ".join(sorted(have)))
    return list(dict.fromkeys(names))


def _whole_only(ch, what):
    if ch.get("parts") is not None:
        raise ChangeError(f"{what} is applied to a whole thing; it has no parts form")


# ---- laying out again ----------------------------------------------------------------------------

def _relayout(spec, words):
    """Lay the parts out again from their words (every part, in order). The footprint middle and the
    floor of the thing stay where they were in the world: the new frame is moved to match."""
    resolved = DP.resolve_parts(words)
    foot = _foot(spec)
    return resolved, _r4([spec["q"][i] + foot[i] for i in range(3)])


def _words(parts):
    """Resolved parts back to their words (a leaning part's size is its own size again)."""
    return [dict({k: v for k, v in p.items() if k not in ("centre", "own")}, **({"size": p["own"]} if p.get("own") else {}))
            for p in parts]


def _reconcile(old, new):
    """The calls that bring the parts both specs have from the old layout to the new one."""
    was = {p["name"]: p for p in old["parts"]}
    calls = []
    for p in new["parts"]:
        o = was.get(p["name"])
        if o is None:
            continue
        a = [o["centre"][i] + old["q"][i] for i in range(3)]
        b = [p["centre"][i] + new["q"][i] for i in range(3)]
        moved = any(abs(a[i] - b[i]) > EPS for i in range(3))
        resized = any(abs(_own(o)[i] - _own(p)[i]) > EPS for i in range(3))
        if not (moved or resized):
            continue
        call = {"tool": "set_transform", "object": p["name"], "location": _basis(new, p["name"], p["centre"])}
        if resized:
            # a flat part (a rug, a plane) has a 0 side: that side keeps its scale
            ratio = [_own(p)[i] / _own(o)[i] if abs(_own(o)[i]) > EPS else 1.0 for i in range(3)]
            calls.append({"tool": "apply_transform", "object": p["name"], "scale": True})
            call["scale"] = [round(v, 5) for v in _local(p, ratio)]
        calls.append(call)
    return calls


def _facts(spec, names=None):
    """What reading the scene back should find for these parts: sizes and places."""
    names = set(names) if names is not None else {p["name"] for p in spec["parts"]}
    chosen = [p for p in spec["parts"] if p["name"] in names]
    return {"dims": {p["name"]: _local_dims(p) for p in chosen},
            "loc": {p["name"]: _r4(_world(spec, p["centre"])) for p in chosen}}


def _material_call(names, color):
    mat = DP.PARTS_MATERIALS[color]
    call = {"tool": "set_material", "objects": list(names), "name": mat.get("name", color),
            "color": mat.get("color", [0.8, 0.8, 0.8])}
    for k in ("roughness", "metallic", "emission_color", "emission_strength", "alpha"):
        if k in mat:
            call[k] = mat[k]
    return call


def _color(value):
    if value not in DP.PARTS_COLORS:
        raise ChangeError(f"unknown colour {value!r}; the colours are: " + ", ".join(DP.PARTS_COLORS))
    return value


# ---- one shape, typed exactly ("add a cube named Box at 1, 2, 0 with a size of 0.5") --------------
#
# The model copies the numbers the user typed into a `shape` change; code makes ONE add_primitive
# call with them and stores a one-part spec whose single part is the object itself (no empty, no
# renamed part): {"solo": True, "call": the shape's own arguments, "scale": [x, y, z], "rot": [x, y, z]}.
# Its `at` is the object's origin, which for a primitive is its middle.

SHAPE_KEYS = ("radius", "depth", "size", "major_radius", "minor_radius")
SHAPES = ("cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus", "plane", "monkey", "circle", "grid")
SHAPE_NOUNS = {"uv_sphere": "sphere", "ico_sphere": "sphere"}
MONKEY = (2.7344, 1.7031, 1.9687)          # Blender's monkey at size 2 (the executor never passes size)


def primitive_dims(shape, args=None):
    """The size of a primitive made with these arguments and scale 1 (Blender's defaults otherwise)."""
    a = args or {}
    g = lambda k, d: float(a[k]) if _num(a.get(k)) else d
    if shape in ("cube",):
        s = g("size", 2.0)
        return [s, s, s]
    if shape in ("plane", "grid"):
        s = g("size", 2.0)
        return [s, s, 0.0]
    if shape in ("uv_sphere", "ico_sphere"):
        d = 2.0 * g("radius", 1.0)
        return [d, d, d]
    if shape in ("cylinder", "cone"):
        d = 2.0 * g("radius", 1.0)
        return [d, d, g("depth", 2.0)]
    if shape == "circle":
        d = 2.0 * g("radius", 1.0)
        return [d, d, 0.0]
    if shape == "torus":
        big, small = g("major_radius", 1.0), g("minor_radius", 0.25)
        return [2.0 * (big + small), 2.0 * (big + small), 2.0 * small]
    if shape == "monkey":
        return list(MONKEY)
    raise ChangeError(f"unknown shape {shape!r}; the shapes are: " + ", ".join(SHAPES))


def _vec3(v, what, lo=-1e4, hi=1e4):
    if not (isinstance(v, list) and len(v) == 3 and all(_num(x) and lo <= x <= hi for x in v)):
        raise ChangeError(f"{what} must be three numbers [x, y, z]")
    return [float(x) for x in v]


def _solo_part(spec):
    """The single part of a solo spec, sized from its call, scale and turn."""
    own = [round(primitive_dims(spec["call"]["shape"], spec["call"])[i] * spec["scale"][i], 4) for i in range(3)]
    rot = spec["rot"]
    box = DP.box_after(own, [rot[0], rot[1], 0.0]) if (rot[0] or rot[1]) else list(own)
    part = {"name": spec["id"], "shape": spec["call"]["shape"], "size": box, "centre": [0.0, 0.0, 0.0],
            "color": (spec["parts"][0].get("color") if spec.get("parts") else None)}
    if rot[0] or rot[1]:
        part["own"] = own
    return part


def _solo_refresh(spec):
    spec["parts"] = [_solo_part(spec)]
    spec["size"] = list(spec["parts"][0]["size"])
    spec["yaw"] = float(spec["rot"][2]) % 360.0
    spec["q"] = [0.0, 0.0, 0.0]
    spec["pins"] = {"*": list(spec["at"]) + [spec["yaw"]], spec["id"]: list(spec["at"]) + [spec["yaw"]]}
    return spec


def solo_spec(name, call, at, rot=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    """The stored spec of one primitive the user asked for by its numbers."""
    spec = {"id": name, "object": SHAPE_NOUNS.get(call["shape"], call["shape"]), "solo": True,
            "call": {k: v for k, v in call.items() if k == "shape" or k in SHAPE_KEYS},
            "at": _r4(at), "rot": _r4(rot), "scale": _r4(scale), "parts": []}
    return _solo_refresh(spec)


def _solo_facts(spec):
    p = spec["parts"][0]
    return {"present": [spec["id"]], "at": {spec["id"]: _r4(spec["at"])}, "dims": {spec["id"]: _local_dims(p)},
            "yaw": {spec["id"]: spec["yaw"]}}


def _shape(ctx, ch, _spec_none=None):
    """do shape: {shape, name, at, rotation?, radius?, depth?, size?, major_radius?, minor_radius?, scale?}."""
    shape, name = ch.get("shape"), ch.get("name")
    if shape not in SHAPES:
        raise ChangeError(f"unknown shape {shape!r}; the shapes are: " + ", ".join(SHAPES))
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", name):
        raise ChangeError("shape needs name: the name the user typed (letters, digits, _ . -)")
    if name in ctx.taken():
        raise ChangeError(f"the name {name!r} is already in the scene")
    at = _vec3(ch.get("at", [0.0, 0.0, 0.0]), "at")
    rot = _vec3(ch["rotation"], "rotation", -3600, 3600) if ch.get("rotation") is not None else [0.0, 0.0, 0.0]
    scale = ch.get("scale")
    if _num(scale):
        scale = [float(scale)] * 3
    scale = _vec3(scale, "scale", 1e-4, 1e4) if scale is not None else [1.0, 1.0, 1.0]
    if scale and any(v <= 0 for v in scale):
        raise ChangeError("scale must be above 0")
    call = {"tool": "add_primitive", "shape": shape, "name": name, "location": _r4(at)}
    for k in SHAPE_KEYS:
        if ch.get(k) is not None:
            if not (_num(ch[k]) and 0 < ch[k] <= 1e4):
                raise ChangeError(f"{k} must be a number above 0")
            call[k] = float(ch[k])
    if any(rot):
        call["rotation_deg"] = _r4(rot)
    if scale != [1.0, 1.0, 1.0]:
        call["scale"] = _r4(scale)
    spec = solo_spec(name, call, at, rot, scale)
    ctx.specs[name] = spec
    return [call], _solo_facts(spec)


def _solo_turn(spec, rot):
    spec["rot"] = _r4(rot)
    _solo_refresh(spec)
    return [{"tool": "set_transform", "object": spec["id"], "rotation_deg": list(spec["rot"])}], _solo_facts(spec)


def _solo_scale(spec, scale):
    spec["scale"] = _r4(scale)
    _solo_refresh(spec)
    return [{"tool": "set_transform", "object": spec["id"], "scale": list(spec["scale"])}], _solo_facts(spec)


def _solo_copy(ctx, spec, at, new_id):
    new = copy.deepcopy(spec)
    new.update(id=new_id, at=_r4(at))
    _solo_refresh(new)
    call = dict({"tool": "add_primitive", "name": new_id, "location": list(new["at"])}, **new["call"])
    if any(new["rot"]):
        call["rotation_deg"] = list(new["rot"])
    if new["scale"] != [1.0, 1.0, 1.0]:
        call["scale"] = list(new["scale"])
    calls = [call]
    color = new["parts"][0].get("color")
    if color in DP.PARTS_MATERIALS:
        calls.append(_material_call([new_id], color))
    ctx.specs[new_id] = new
    return calls


# ---- the changes -------------------------------------------------------------------------------

def _remove(ctx, ch, spec):
    names = _part_names(spec, ch)
    every = {p["name"] for p in spec["parts"]}
    if names is None or set(names) >= every:
        gone = list(dict.fromkeys([spec["id"]] + [p["name"] for p in spec["parts"]] +
                                  [p["name"] + "Cut" for p in spec["parts"] if p.get("hollow")]))
        del ctx.specs[spec["id"]]
        return [{"tool": "delete_object", "object": spec["id"]}], {"gone": gone}
    cutters = [p["name"] + "Cut" for p in spec["parts"] if p["name"] in names and p.get("hollow")]
    keep = [p for p in spec["parts"] if p["name"] not in names]
    if any((p.get("place") or {}).get("on") in names for p in keep):
        # what stood on a removed part keeps its place: its words are written again from where it is
        centres = {p["name"]: p["centre"] for p in keep}
        keep = [dict(w, centre=centres[w["name"]]) for w in DP.describe([dict(p) for p in keep])]
    new = copy.deepcopy(spec)
    new["parts"] = keep                  # nothing else moves: the centres are what was built
    new["size"] = DP.extent(new["parts"])
    for n in names:
        new["pins"].pop(n, None)
    calls = [{"tool": "delete_object", "objects": names + cutters}]
    ctx.specs[spec["id"]] = new
    return calls, dict(_facts(new), gone=names + cutters)


def _recolor(ctx, ch, spec):
    names = _part_names(spec, ch) or [p["name"] for p in spec["parts"]]
    if not (isinstance(ch.get("color"), str) and ch["color"] in DP.PARTS_COLORS):
        return _recolor_words(ctx, ch, spec, names)
    color = _color(ch.get("color"))
    finish = ch.get("finish")
    if finish is not None and finish not in DP.FINISHES:
        raise ChangeError(f"unknown finish {finish!r}; the finishes are: " + ", ".join(DP.FINISHES))
    calls = [_material_call(names, color)]
    for p in spec["parts"]:
        if p["name"] in names:
            p["color"] = color
            if finish == "smooth":
                calls += CP.smooth_calls(p["name"], _local_dims(p))
            elif finish == "sharp":
                calls.append({"tool": "shade_smooth", "object": p["name"], "smooth": False})
            if finish:
                p["finish"] = finish
    return calls, {"material": {n: DP.PARTS_MATERIALS[color]["name"] for n in names}}


def _recolor_words(ctx, ch, spec, names):
    """A colour in the shared colour words (colours.py: ~150 names, shade, see_through, look,
    gradient, typed hex / rgb). The 26 trained colours keep the path above."""
    from . import colours as COL
    bad = COL.faults(ch.get("color"))
    if bad:
        raise ChangeError("; ".join(bad) + "; colours are words from the colour list")
    mat = COL.material(ch["color"])
    call = dict({"tool": "set_material", "objects": list(names)}, **mat)
    label = ch["color"] if isinstance(ch["color"], str) else (ch["color"].get("name") or "typed")
    for p in spec["parts"]:
        if p["name"] in names:
            p["color"] = label
    return [call], {"material": {n: mat["name"] for n in names}}


def _tilt(ctx, ch, spec):
    """Lean parts (their tilt words, laid out again) or the whole thing (its empty turns about x / y).
    toward: left | right | front | back; by: slight | medium | steep (15 / 30 / 45 degrees)."""
    toward, by = ch.get("toward"), ch.get("by")
    if toward not in DP.LEAN or by not in DP.TILTS:
        raise ChangeError("tilt needs toward (left, right, front, back) and by (slight, medium, steep)")
    names = _part_names(spec, ch)
    if names is None:
        i, sign = DP.LEAN[toward]
        rot = [0.0, 0.0, spec["yaw"]]
        rot[i] = sign * DP.TILTS[by]
        spec["tilt"] = {"toward": toward, "by": by}
        if spec.get("solo"):
            return _solo_turn(spec, rot)
        return [{"tool": "set_transform", "object": spec["id"], "rotation_deg": rot}], {}
    new = copy.deepcopy(spec)
    words = _words(new["parts"])
    for w in words:
        if w["name"] in names:
            if w.get("axis") or w.get("shape") == "prism":
                raise ChangeError(f"{w['name']} lies on its side or is a prism: it cannot lean")
            w["tilt"] = {"toward": toward, "by": by}
    new["parts"], new["q"] = _relayout(spec, words)
    new["size"] = DP.extent(new["parts"])
    calls = _reconcile(spec, new)
    for p in new["parts"]:
        if p["name"] in names:
            calls.append({"tool": "set_transform", "object": p["name"], "rotation_deg": DP.tilt_turn(p)})
    ctx.specs[spec["id"]] = new
    return calls, _facts(new)


def _scale(ctx, ch, spec):
    to = ch.get("to")
    if to is not None:                  # the scale the user typed: the thing's own scale, not a factor
        if ch.get("by") is not None:
            raise ChangeError("scale needs one of by or to")
        _whole_only(ch, "scale to")
        if _num(to):
            to = [float(to)] * 3
        to = _vec3(to, "scale to", 1e-4, 1e4)
        if spec.get("solo"):
            return _solo_scale(spec, to)
        was = spec.get("scale") or [1.0, 1.0, 1.0]
        ch = dict(ch, by={"xyz"[i]: to[i] / was[i] for i in range(3)})
        ch.pop("to")
    by = ch.get("by")
    if not isinstance(by, dict) or not by or any(k not in ("x", "y", "z") for k in by) \
            or not all(_num(v) and 0 < v <= 100 for v in by.values()):
        raise ChangeError("scale needs by: {x, y, z} with a factor above 0 for each axis asked")
    if spec.get("solo"):
        _whole_only(ch, "scale")
        return _solo_scale(spec, [spec["scale"][i] * by.get("xyz"[i], 1.0) for i in range(3)])
    whole = ch.get("parts") is None
    names = _part_names(spec, ch) or [p["name"] for p in spec["parts"]]
    new = copy.deepcopy(spec)
    for p in new["parts"]:
        if p["name"] in names:
            p["size"] = [round(_own(p)[i] * by.get("xyz"[i], 1.0), 4) for i in range(3)]
            p.pop("own", None)
    new["parts"], new["q"] = _relayout(spec, _words(new["parts"]))
    new["size"] = DP.extent(new["parts"])
    if whole:
        was = spec.get("scale") or [1.0, 1.0, 1.0]
        new["scale"] = _r4([was[i] * by.get("xyz"[i], 1.0) for i in range(3)])
    calls = _reconcile(spec, new)
    ctx.specs[spec["id"]] = new
    return calls, _facts(new)


def _anchor_box(ctx, place, subject_ids, things, parts):
    """The anchor of a place and the obstacles: an exact name, never matched."""
    if not isinstance(place, dict):
        raise ChangeError("place must be {anchor, relation, distance}")
    anchor = place.get("anchor")
    if anchor in subject_ids:
        raise ChangeError(f"{anchor!r} cannot be placed against itself")
    rel = place.get("relation")
    if rel not in PLACE.RELATIONS:
        raise ChangeError(f"unknown relation {rel!r}; the relations are: " + ", ".join(PLACE.RELATIONS))
    dist = place.get("distance")
    if dist is None:
        dist = "touching" if rel in ("on_top_of", "under", "against") else "small"
    if dist not in PLACE.GAP:
        raise ChangeError(f"unknown distance {dist!r}; the distances are: " + ", ".join(PLACE.GAP))
    place = dict(place, relation=rel, distance=dist)
    if anchor == CP.SCENE:
        everything = {n: b for n, b in things.items() if n not in subject_ids}
        if not everything:
            raise ChangeError("the scene has nothing to place against")
        place["relation"] = CP.scene_relation(rel)
        return place, CP.scene_box(everything), anchor
    box = things.get(anchor) or parts.get(anchor)
    if box is None:
        raise ChangeError(f"unknown anchor {anchor!r}; the scene has: " + ", ".join(list(things)))
    if rel == "between":            # "between A and B": anchor A, and B
        other = place.get("and")
        if other in subject_ids or other == anchor:
            raise ChangeError("between needs two other things")
        other_box = things.get(other) or parts.get(other)
        if other_box is None:
            raise ChangeError(f"between needs a second thing in 'and'; {other!r} is not in the scene")
        place.update(between=[anchor, other], between_boxes=[box, other_box])
    return place, box, anchor


def _turn_to(spec, yaw):
    """The pose that turns the thing to `yaw` about the middle of its footprint."""
    yaw = round(yaw % 360.0, 4)
    q = [spec["q"][i] + _foot(spec)[i] for i in range(3)]
    a, b = _rz(spec["yaw"], q), _rz(yaw, q)
    return _r4([spec["at"][i] + a[i] - b[i] for i in range(3)]), yaw


def _move(ctx, ch, spec):
    _whole_only(ch, "move")
    place, shift, to = ch.get("place"), ch.get("shift"), ch.get("to")
    if sum(v is not None for v in (place, shift, to)) != 1:
        raise ChangeError("move needs exactly one of place, shift or to")
    yaw = None
    if to is not None:                  # where the user typed: the thing's own location
        to = _vec3(to, "move to")
        delta = [to[i] - spec["at"][i] for i in range(3)]
    elif shift is not None:
        if not isinstance(shift, dict) or not shift or any(k not in ("x", "y", "z") for k in shift) \
                or not all(_num(v) for v in shift.values()):
            raise ChangeError("shift must be {x, y, z} in metres, only the axes asked")
        delta = [float(shift.get("xyz"[i], 0.0)) for i in range(3)]
    else:
        things, parts = ctx.boxes()
        mine = {spec["id"]} | {p["name"] for p in spec["parts"]}
        place, anchor_box, anchor = _anchor_box(ctx, place, mine, things, parts)
        box = _spec_box(spec)
        others = [b for n, b in things.items() if n not in (spec["id"], anchor)]
        res = PLACE.resolve(place, anchor_box, PLACE.box_extent(box), obstacles=others)
        old = PLACE.box_centre(box)
        delta = [res["centre"][i] - old[i] for i in range(3)]
        if place.get("facing"):
            yaw = res["yaw_deg"]
    at = _r4([spec["at"][i] + delta[i] for i in range(3)])
    spec["at"] = at
    call = {"tool": "set_transform", "object": spec["id"], "location": at}
    if yaw is not None:
        spec["at"], yaw = _turn_to(spec, yaw)
        spec["yaw"] = yaw
        call.update(location=spec["at"], rotation_deg=_rotation(spec, yaw))
    if spec.get("solo"):
        if yaw is not None:
            spec["rot"] = _rotation(spec, yaw)
        _solo_refresh(spec)
    return [call], {"at": {spec["id"]: spec["at"]}, **({"yaw": {spec["id"]: yaw}} if yaw is not None else {})}


def _turn(ctx, ch, spec):
    _whole_only(ch, "turn")
    by, face, to = ch.get("by"), ch.get("face"), ch.get("to_degrees")
    if sum(v is not None for v in (by, face, to)) != 1:
        raise ChangeError("turn needs exactly one of by, face or to_degrees")
    if isinstance(to, list):            # the whole rotation the user typed
        rot = _vec3(to, "to_degrees", -3600, 3600)
        if spec.get("solo"):
            return _solo_turn(spec, rot)
        if abs(rot[0]) > EPS or abs(rot[1]) > EPS:
            raise ChangeError(f"{spec['id']} is built of parts: it turns about z only (to_degrees [0, 0, z])")
        to = rot[2]
    if to is not None:
        if not _num(to):
            raise ChangeError("to_degrees must be degrees, or [x, y, z] degrees")
        yaw = float(to)
    elif by is not None:
        if not _num(by):
            raise ChangeError("by must be degrees")
        yaw = spec["yaw"] + by
    elif face in COMPASS:
        yaw = PLACE.yaw_towards(*COMPASS[face])
    else:
        things, parts = ctx.boxes()
        mine = {spec["id"]} | {p["name"] for p in spec["parts"]}
        target = things.get(face) if face not in mine else None
        if target is None:
            raise ChangeError(f"unknown thing to face {face!r}; the scene has: " + ", ".join(
                n for n in list(things) if n != spec["id"]) + "; or north, south, east, west")
        c, me = PLACE.box_centre(target), _centre_xy(spec)
        yaw = PLACE.yaw_towards(c[0] - me[0], c[1] - me[1])
    at, yaw = _turn_to(spec, yaw)
    spec["at"], spec["yaw"] = at, yaw
    rot = _rotation(spec, yaw)
    if spec.get("solo"):
        spec["rot"] = rot
        _solo_refresh(spec)
    return [{"tool": "set_transform", "object": spec["id"], "location": at, "rotation_deg": rot}], \
        {"at": {spec["id"]: at}, "yaw": {spec["id"]: yaw}}


def _rotation(spec, yaw):
    """The rotation a turn writes: a solo shape keeps the tilt it was made with."""
    rot = spec.get("rot") if spec.get("solo") else None
    return _r4([rot[0], rot[1], yaw]) if rot else [0.0, 0.0, yaw]


def _primitive_calls(spec, p, yaw_for_box=0.0):
    """Make one part of a spec in the world (its pin is the pose the thing has right now)."""
    rp = DP.recipe_part(p, _basis(spec, p["name"], p["centre"]), p["name"])
    call = CP.part_call({"origin": [0.0, 0.0, 0.0]}, rp)
    if yaw_for_box and "rotation_deg" not in rp:
        call["rotation_deg"] = [0.0, 0.0, yaw_for_box]
    calls = [call]
    if p.get("color") in DP.PARTS_MATERIALS:
        calls.append(_material_call([p["name"]], p["color"]))
    if p.get("finish") == "smooth" and not p.get("hollow"):
        calls += CP.smooth_calls(p["name"], _local_dims(p))
    return calls


def _add(ctx, ch, spec):
    if spec.get("solo"):
        raise ChangeError(f"{spec['id']} is one shape made by its numbers: parts cannot be added to it")
    new_parts = ch.get("parts")
    if not isinstance(new_parts, list) or not new_parts or not all(isinstance(p, dict) and isinstance(p.get("name"), str)
                                                                   for p in new_parts):
        raise ChangeError("add needs parts: a list of named parts in the parts format")
    added = [{k: copy.deepcopy(v) for k, v in p.items() if k in PART_KEYS} for p in new_parts]
    names = {p.get("name") for p in added}
    clash = [n for n in names if n in ctx.taken()]
    if clash:
        raise ChangeError(f"the name {clash[0]!r} is already in the scene")
    combined = _words(spec["parts"]) + added
    faults, _built = DP.check_answer({"parts": combined})
    mine = [f for f in faults if any(f.startswith(f"{n}:") for n in names) or
            (f.startswith("floating: ") and names & set(f[len("floating: "):].split(", ")))]
    if mine:
        raise ChangeError("; ".join(mine)[:300])
    new = copy.deepcopy(spec)
    done = {p["name"]: p for p in new["parts"]}          # the parts that are there, where they were built
    placed = []
    for p in added:
        # the new part is placed against its anchor where the anchor IS, not where its words would put it
        entry = DP.place_part(p, done, new["parts"][-1])
        done[p["name"]] = entry
        placed.append(entry)
    new["parts"] += placed
    new["size"] = DP.extent(new["parts"])
    calls = []
    for p in placed:
        new["pins"][p["name"]] = list(spec["at"]) + [spec["yaw"]]
        calls += _primitive_calls(new, p, spec["yaw"])
        calls.append({"tool": "parent", "child": p["name"], "parent": spec["id"]})
    ctx.specs[spec["id"]] = new
    facts = _facts(new, names)
    facts["material"] = {p["name"]: DP.PARTS_MATERIALS[p["color"]]["name"] for p in new["parts"]
                         if p["name"] in names and p.get("color") in DP.PARTS_MATERIALS}
    return calls, facts


def _copy(ctx, ch, spec):
    _whole_only(ch, "copy")
    count = ch.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 20:
        raise ChangeError("count must be a whole number from 1 to 20")
    things, parts = ctx.boxes()
    box = _spec_box(spec)
    size, was = PLACE.box_extent(box), PLACE.box_centre(box)
    mine = {spec["id"]} | {p["name"] for p in spec["parts"]}
    anchor_box, place, anchor = box, {"relation": "next_to", "distance": "small"}, spec["id"]
    if ch.get("place") is not None:
        place, anchor_box, anchor = _anchor_box(ctx, ch["place"], mine, things, parts)
    taken, calls, made = ctx.taken(), [], {}
    if spec.get("solo"):
        for k in range(count):
            n = 2
            while spec["id"] + str(n) in taken:
                n += 1
            new_id = spec["id"] + str(n)
            ring = place.get("relation") == "around" or (place.get("arrangement") or {}).get("kind") == "ring"
            res = PLACE.resolve(place, anchor_box, size, count=count if ring else 1, member=k if ring else 0,
                                obstacles=[b for nm, b in things.items() if nm != anchor and nm not in made])
            at = [spec["at"][i] + res["centre"][i] - was[i] for i in range(3)]
            calls += _solo_copy(ctx, spec, at, new_id)
            taken.add(new_id)
            things[new_id] = _spec_box(ctx.specs[new_id])
            made[new_id] = ctx.specs[new_id]["at"]
            if not ring:
                anchor, anchor_box, place = new_id, things[new_id], {"relation": "next_to", "distance": "small"}
        return calls, {"at": made, "present": list(made)}
    for k in range(count):
        n = 2
        while any(x + str(n) in taken for x in [spec["id"]] + [p["name"] for p in spec["parts"]]):
            n += 1
        new_id = spec["id"] + str(n)
        ring = place.get("relation") == "around" or (place.get("arrangement") or {}).get("kind") == "ring"
        res = PLACE.resolve(place, anchor_box, size, count=count if ring else 1, member=k if ring else 0,
                            obstacles=[b for nm, b in things.items() if nm != anchor and nm not in made])
        at = _r4([spec["at"][i] + res["centre"][i] - was[i] for i in range(3)])
        rename = {p["name"]: p["name"] + str(n) for p in spec["parts"]}
        new = copy.deepcopy(spec)
        new.update(id=new_id, at=at, yaw=0.0)
        for p in new["parts"]:
            p["name"] = rename[p["name"]]
            if (p.get("place") or {}).get("on") in rename:
                p["place"]["on"] = rename[p["place"]["on"]]
        CP.unclash(new["parts"], new_id)
        new["pins"] = {"*": at + [0.0], **{p["name"]: at + [0.0] for p in new["parts"]}}
        for p in new["parts"]:
            calls += _primitive_calls(new, p)
        calls.append({"tool": "add_empty", "name": new_id, "location": at})
        calls += [{"tool": "parent", "child": p["name"], "parent": new_id} for p in new["parts"]]
        if spec["yaw"]:
            new["yaw"] = spec["yaw"]
            calls.append({"tool": "set_transform", "object": new_id, "rotation_deg": [0.0, 0.0, spec["yaw"]]})
        ctx.specs[new_id] = new
        taken.update([new_id] + list(rename.values()))
        things[new_id] = _spec_box(new)
        made[new_id] = at
        if not ring:                    # a ring keeps its anchor; anything else lines the copies up
            anchor, anchor_box, place = new_id, things[new_id], {"relation": "next_to", "distance": "small"}
    return calls, {"at": made, "present": [i for i in made] + [p["name"] for i in made for p in ctx.specs[i]["parts"]]}


def _rename(ctx, ch, spec):
    to = ch.get("to")
    if not isinstance(to, str) or not to or to in ctx.taken():
        raise ChangeError(f"the new name {to!r} is empty or already used")
    names = _part_names(spec, ch)
    if spec.get("solo"):
        names = None
    if names is None:
        del ctx.specs[spec["id"]]
        gone = spec["id"]
        spec["id"] = to
        if spec.get("solo"):
            _solo_refresh(spec)
        ctx.specs[to] = spec
        return [{"tool": "set_object", "object": gone, "name": to}], {"gone": [gone], "present": [to]}
    if len(names) != 1:
        raise ChangeError("rename names one part at a time")
    old = names[0]
    for p in spec["parts"]:
        if p["name"] == old:
            p["name"] = to
        if (p.get("place") or {}).get("on") == old:
            p["place"]["on"] = to
    for table in (spec["pins"],):
        if old in table:
            table[to] = table.pop(old)
    return [{"tool": "set_object", "object": old, "name": to}], {"gone": [old], "present": [to]}


_OPS = {"remove": _remove, "recolor": _recolor, "scale": _scale, "move": _move, "turn": _turn,
        "add": _add, "copy": _copy, "rename": _rename, "tilt": _tilt, "shape": _shape}


def apply_answer(answer, specs, scene=None):
    """One change answer on the stored specs -> Applied (calls, new specs, errors, expected facts).
    `scene` (the executor's objects) is read only for places and for the pose of things."""
    out = Applied()
    out.specs = copy.deepcopy(specs)
    if not isinstance(answer, dict):
        out.errors.append({"change": None, "error": "the answer is not an object"})
        return out
    out.kind = answer.get("kind")
    if out.kind in ("question", "cannot"):
        out.say = str(answer.get("say") or "")
        if not out.say:
            out.errors.append({"change": None, "error": f"kind {out.kind} without say"})
        return out
    if out.kind == "build":
        return out
    if out.kind != "change":
        out.errors.append({"change": None, "error": f"unknown kind {out.kind!r}; the kinds are: " + ", ".join(KINDS)})
        return out
    changes = answer.get("changes")
    if not isinstance(changes, list) or not changes:
        out.errors.append({"change": None, "error": "kind change without changes"})
        return out
    ctx = _Ctx(out.specs, scene)
    for i, ch in enumerate(changes):
        before = copy.deepcopy(ctx.specs)
        try:
            if not isinstance(ch, dict):
                raise ChangeError("a change is an object")
            op = _OPS.get(ch.get("do"))
            if op is None:
                raise ChangeError(f"unknown do {ch.get('do')!r}; the changes are: " + ", ".join(DOS))
            if op is _shape:
                calls, expect = op(ctx, ch)
            else:
                calls, expect = op(ctx, ch, _thing(ctx, ch.get("object")))
        except ChangeError as error:
            ctx.specs = before
            out.errors.append({"change": i, "do": ch.get("do") if isinstance(ch, dict) else None,
                               "object": ch.get("object") if isinstance(ch, dict) else None, "error": str(error)})
            out.expected.append({"error": str(error)})
            continue
        out.calls.extend(calls)
        out.expected.append(expect)
    out.specs = ctx.specs
    out.expected = [_refresh(e, out.specs) for e in out.expected]
    return out


def _refresh(expect, specs):
    """A later change of the same answer may move or resize what an earlier one set, and the scene is
    read back once, at the end: so sizes, places, colours and turns are the final ones."""
    if "error" in expect:
        return expect
    parts = {p["name"]: (s, p) for s in specs.values() for p in s["parts"]}
    out = dict(expect)
    for key, fn in (("dims", lambda s, p: _local_dims(p)), ("loc", lambda s, p: _r4(_world(s, p["centre"]))),
                    ("material", lambda s, p: DP.PARTS_MATERIALS[p["color"]]["name"] if p.get("color") in DP.PARTS_MATERIALS else None)):
        if key in out:
            out[key] = {n: fn(*parts[n]) for n in out[key] if n in parts and fn(*parts[n]) is not None}
    for key, fn in (("at", lambda s: _r4(s["at"])), ("yaw", lambda s: s["yaw"])):
        if key in out:
            out[key] = {n: fn(specs[n]) for n in out[key] if n in specs}
    return out


# ---- reading the scene back --------------------------------------------------------------------

def _near(a, b, tol):
    return all(abs(x - y) <= tol(y) for x, y in zip(a, b))


def check(answer, scene_after, applied=None):
    """Per change of the answer: {"index", "do", "object", "status": ok | wrong | not-checked, "detail"}.
    Reads the scene back (colour, size, place, turn, gone). It reports; it never corrects."""
    by = {o.get("name"): o for o in scene_after or []}
    results = []
    changes = answer.get("changes") if isinstance(answer, dict) and isinstance(answer.get("changes"), list) else []
    for i, ch in enumerate(changes):
        row = {"index": i, "do": ch.get("do"), "object": ch.get("object")}
        exp = applied.expected[i] if applied is not None and i < len(applied.expected) else None
        if exp is None:
            exp = _facts_from_answer(ch)
        if "error" in exp:
            results.append(dict(row, status="not-checked", detail="not applied: " + exp["error"]))
            continue
        wrong, seen, unread = [], 0, []
        for name in exp.get("gone", []):
            seen += 1
            if name in by:
                wrong.append(f"{name} is still there")
        for name in exp.get("present", []):
            seen += 1
            if name not in by:
                wrong.append(f"{name} is not there")
        for name, want in exp.get("material", {}).items():
            o = by.get(name)
            if o is None:
                wrong.append(f"{name} is not there")
            elif "material" in o:
                seen += 1
                got = o["material"]
                if not (got == want or str(got).startswith(want + ".")):
                    wrong.append(f"{name} is {got}, not {want}")
            else:
                unread.append(f"material of {name}")
        for name, want in exp.get("dims", {}).items():
            o = by.get(name)
            if o is None:
                wrong.append(f"{name} is not there")
            elif o.get("dims"):
                seen += 1
                if not _near(o["dims"], want, lambda w: max(0.05 * w, 0.01)):
                    wrong.append(f"{name} measures {o['dims']}, not {want}")
            else:
                unread.append(f"size of {name}")
        for key in ("loc", "at"):
            for name, want in exp.get(key, {}).items():
                o = by.get(name)
                if o is None:
                    wrong.append(f"{name} is not there")
                elif o.get("loc"):
                    seen += 1
                    if not _near(o["loc"], want, lambda w: 0.03):
                        wrong.append(f"{name} is at {o['loc']}, not {want}")
                else:
                    unread.append(f"place of {name}")
        for name, want in exp.get("yaw", {}).items():
            o = by.get(name)
            rot = o.get("rot_deg") if o else None
            if o is None:
                wrong.append(f"{name} is not there")
            elif isinstance(rot, list) and len(rot) == 3:
                seen += 1
                if abs((rot[2] - want + 180.0) % 360.0 - 180.0) > 1.5:
                    wrong.append(f"{name} faces {rot[2]}, not {want}")
            else:
                unread.append(f"turn of {name}")
        if wrong:
            results.append(dict(row, status="wrong", detail="; ".join(wrong)[:300]))
        elif unread or not seen:
            results.append(dict(row, status="not-checked",
                                detail="the scene does not say: " + ", ".join(unread) if unread else "the scene does not say"))
        else:
            results.append(dict(row, status="ok", detail=""))
    return results


def _facts_from_answer(ch):
    """With no Applied at hand only what the answer itself states can be read back."""
    if ch.get("do") == "remove" and isinstance(ch.get("parts"), list):
        return {"gone": [n for n in ch["parts"] if isinstance(n, str)]}
    if ch.get("do") == "recolor" and ch.get("color") in DP.PARTS_MATERIALS and isinstance(ch.get("parts"), list):
        return {"material": {n: DP.PARTS_MATERIALS[ch["color"]]["name"] for n in ch["parts"] if isinstance(n, str)}}
    if ch.get("do") == "rename" and isinstance(ch.get("to"), str) and ch.get("parts") is None:
        return {"gone": [ch.get("object")], "present": [ch["to"]]}
    return {}
