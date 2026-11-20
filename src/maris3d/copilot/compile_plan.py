# SPDX-License-Identifier: Apache-2.0
"""The step between a plan and a build: items with placement words in, exact instructions out.

The planner answers WHAT and WHERE IN WORDS, never numbers:

    {"items": [{"id": "bench_1", "recipe": "bench", "count": 2,
                "place": {"anchor": "platform_1", "relation": "on_top_of", "distance": "touching"}}]}

Without this module the planner's answer is only printed. This module reads it and does the
three things a harness would otherwise do by hand:

  1. layout   each item gets a place from its words (`place.resolve`), relative to an item of
              this plan or to something already in the scene;
  2. parts    the recipe library says what the item is made of (`recipes.RECIPES`), and every
              part becomes ONE exact instruction, in the wording the build model follows;
  3. checks   after the model has built a chunk, every part is compared with what was asked;
              a part that is missing or in the wrong place is corrected and COUNTED, so a run
              says how much the model did and how much the harness did.

It has no bpy and no model in it: it turns data into sentences and calls, and reads objects
back as plain dicts ({"name", "loc", "dims"}), so it is tested without Blender.
"""
import re

from . import place as PLACE
from .recipes import MATERIALS, RECIPES

CHUNK = 4            # parts per ask: 3-4 parts of ONE object came back exact every time
LOC_TOL = 0.02       # metres: a part this close to its place is "exact"
DIM_TOL = 0.05       # fraction of the asked size

# the planner's recipe words -> a recipe of the library (same thing, another name)
ALIASES = {"pine": "tree", "cottage": "cabin", "rug": "rug_group", "book": "tea", "cup": "tea",
           "mug": "tea", "lamppost": "lamp_post", "street_lamp": "lamp_post", "station": "station_building",
           "ticket_office": "station_building", "locomotive": "train", "truck": "snow_truck",
           "person": "man", "kitchen": "kitchen_run", "painting": "art", "bookshelf": "shelf",
           "rails": "track", "railway": "track"}

# The world anchor. "scene" (also world, ground, here) is the box around
# everything the scene has, or a 1 m box at the origin when it has nothing. Compass words are the
# four axis relations under another name: north = behind (+y), south = front_of (-y),
# east = right_of (+x), west = left_of (-x).
SCENE = "scene"
SCENE_WORDS = ("scene", "world", "ground", "here")
COMPASS = {"north": "behind", "south": "front_of", "east": "right_of", "west": "left_of"}
NORTH_MARKER = "SceneNorth"
# "at the north end": no anchor in the words, the scene is meant
END_PHRASES = tuple((f"{lead} the {c} {end}", rel) for c, rel in COMPASS.items()
                    for lead in ("at", "to", "on") for end in ("end", "edge", "side"))

RELATION_PHRASES = (            # longest first: "in front of" before "front"
    ("to the north of", "behind"), ("to the south of", "front_of"), ("to the east of", "right_of"),
    ("to the west of", "left_of"), ("north of", "behind"), ("south of", "front_of"),
    ("east of", "right_of"), ("west of", "left_of"),
    ("on top of", "on_top_of"), ("in front of", "front_of"), ("to the left of", "left_of"),
    ("to the right of", "right_of"), ("left of", "left_of"), ("right of", "right_of"),
    ("next to", "next_to"), ("beside", "next_to"), ("behind", "behind"), ("underneath", "under"),
    ("under", "under"), ("beneath", "under"), ("below", "under"), ("against", "against"),
    ("around", "around"), ("in the middle of", "centre_of"), ("in the centre of", "centre_of"),
    ("onto", "on_top_of"), ("on", "on_top_of"), ("by", "next_to"), ("near", "next_to"),
)
DISTANCE_PHRASES = (
    ("touching", "touching"), ("right up against", "touching"), ("very close", "tiny"),
    ("close", "small"), ("a little away", "medium"), ("far away", "far"), ("far from", "far"),
    ("a long way", "distant"), ("distant", "distant"),
    (" far ", "far"),          # "far to the east of the chair" (the sentence is padded with spaces)
)


# A planner that meets a phrasing it was not trained on sometimes copies the word instead of
# naming the relation (measured on planner v3: "to the rear of" -> rear_of, "upon" ->
# upon, "before" -> before). These are the same eleven relations under another name.
RELATION_WORDS = {"rear_of": "behind", "back_of": "behind", "before": "front_of", "infront_of": "front_of",
                  "in_front_of": "front_of", "upon": "on_top_of", "on": "on_top_of", "onto": "on_top_of",
                  "over": "on_top_of", "above": "on_top_of", "on_left_of": "left_of", "on_right_of": "right_of",
                  "beside": "next_to", "by": "next_to", "near": "next_to", "alongside": "next_to",
                  "beneath": "under", "below": "under", "underneath": "under", "round": "around",
                  "middle_of": "centre_of", "center_of": "centre_of", "leaning_on": "against"}
for _c, _rel in COMPASS.items():
    for _form in ("{c}", "{c}_of", "to_the_{c}_of", "{c}_end", "at_the_{c}_end", "{c}_side", "{c}_edge"):
        RELATION_WORDS[_form.format(c=_c)] = _rel


def relation_word(word):
    """One of place.RELATIONS for whatever the planner wrote, or None if it is no relation at all."""
    key = re.sub(r"[^a-z]+", "_", str(word or "").lower()).strip("_")
    key = RELATION_WORDS.get(key, key)
    return key if key in PLACE.RELATIONS else None


MOVE_VERB = re.compile(r"\b(put|move|place|set|shift|bring)\b")


def word_key(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")


def recipe_key(name, designed=None):
    """The recipe for a planner word: the library's, or one the parts planner designed in this
    request (`designed`: {word: recipe}); None when neither has it."""
    key = word_key(name)
    if designed and key in designed:
        return key
    key = ALIASES.get(key, key)
    if key in RECIPES:
        return key
    if key.endswith("s") and key[:-1] in RECIPES:          # "benches" is handled by the planner; "lamps" is not
        return key[:-1]
    return None


def box_of(obj):
    """{"lo", "hi"} of one scene object from its origin and dimensions (a mesh's origin is its centre)."""
    loc, dims = obj.get("loc") or [0, 0, 0], obj.get("dims") or [0, 0, 0]
    return {"lo": [loc[i] - dims[i] / 2.0 for i in range(3)],
            "hi": [loc[i] + dims[i] / 2.0 for i in range(3)]}


def union(boxes):
    boxes = list(boxes)
    if not boxes:
        return None
    return {"lo": [min(b["lo"][i] for b in boxes) for i in range(3)],
            "hi": [max(b["hi"][i] for b in boxes) for i in range(3)]}


def _item_box(origin, size):
    return {"lo": [origin[0] - size[0] / 2.0, origin[1] - size[1] / 2.0, origin[2]],
            "hi": [origin[0] + size[0] / 2.0, origin[1] + size[1] / 2.0, origin[2] + size[2]]}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def unclash(parts, thing):
    """A part may not carry its thing's name: the thing is an empty of that name and Blender's names
    are one set, so `parent(child=Leg, parent=Leg)` would parent the part to itself, which Blender
    refuses. Such a part becomes <name>Main; a part placed on it follows. Returns the parts (the list is changed in place)."""
    rename = {}
    for p in parts:
        if _norm(p.get("name")) == _norm(thing):
            rename[p["name"]] = p["name"] + "Main"
            p["name"] = rename[p["name"]]
    if rename:
        for p in parts:
            place = p.get("place")
            if isinstance(place, dict) and place.get("on") in rename:
                p["place"] = dict(place, on=rename[place["on"]])     # a copy: the recipe's own stays
    return parts


def scene_box(boxes, without=()):
    """The box around everything in the scene (minus `without`), or 1 m at the origin if empty."""
    return union(b for n, b in boxes.items() if n not in without) \
        or {"lo": [-0.5, -0.5, 0.0], "hi": [0.5, 0.5, 1.0]}


def scene_relation(relation):
    """A relation that makes sense against the whole scene: the four sides, or its middle."""
    return relation if relation in PLACE.AXIS else "centre_of"


def find_anchor(word, boxes):
    """A box for an anchor word: an item id of this plan, a group or an object already in the scene.

    `boxes` is {name: box}. The planner says "platform_1" or "table"; the scene says "Platform" or
    "TableTop". An exact name wins, then the same word without its number, then a name that starts
    with it (the parts of a table all start with Table).
    """
    if not word:
        return None, None
    want = _norm(str(word).split(":", 1)[-1])
    bare = want.rstrip("0123456789")
    for test in (lambda n: n == want, lambda n: n == bare, lambda n: n.rstrip("0123456789") == bare):
        for name, box in boxes.items():
            if test(_norm(name)):
                return name, box
    family = [box for name, box in boxes.items() if bare and _norm(name).startswith(bare)]
    if family:
        return bare, union(family)
    if want in SCENE_WORDS:                 # only when nothing in the scene has that name
        return SCENE, scene_box(boxes)
    return None, None


def _anchors_first(items):
    """The items with every anchor before what stands by it. "A car behind the station" lists the
    car first; placed in that order the car had nothing to stand behind and lost its relation.
    Items that wait for each other in a circle keep their order."""
    items = [i for i in items if isinstance(i, dict)]
    ids = lambda group: {_norm(i.get("id")) for i in group if i.get("id")}
    out, rest = [], list(items)
    while rest:
        waiting = ids(rest)
        ready = [i for i in rest
                 if not {_norm((i.get("place") or {}).get(k) or "") for k in ("anchor", "and")}
                 & (waiting - {_norm(i.get("id"))})]
        take = ready[0] if ready else rest[0]
        out.append(take)
        rest.remove(take)
    return out


def scale_recipe(recipe, word):
    """The recipe at a size word's factor ("a small platform": x0.75 on every axis): the whole object,
    its parts' sizes and their offsets from its origin. No word or an unknown one: unchanged."""
    from .describe_parts import SIZE_WORDS
    k = SIZE_WORDS.get(word) if isinstance(word, str) else None
    if not k:
        return recipe

    def mul(v):
        return [round(float(v[i]) * k[i], 5) for i in range(3)]
    parts = [dict(p, **{f: mul(p[f]) for f in ("dims", "offset", "scale") if isinstance(p.get(f), list) and len(p[f]) == 3})
             for p in recipe["parts"]]
    return dict(recipe, parts=parts, size=mul(recipe["size"]))


def own_names(parts, thing, taken):
    """Blender's object names are one flat set: a table's "FrontLeg" in a scene whose chair has a
    "FrontLeg" would become "FrontLeg.001", and every later call and check by name would reach the
    chair's leg. A part whose name another thing already uses gets its own thing's name in front
    (TableFrontLeg); a part placed on it follows. `taken`: normalised names in use, added to here.
    Returns the parts (the list is changed in place)."""
    rename = {}
    for p in parts:
        old = p["name"]
        if _norm(old) in taken:
            new = old if _norm(old).startswith(_norm(thing)) else f"{thing}{old}"
            n = 1
            while _norm(new) in taken:
                n += 1
                new = f"{thing}{old}{n}"
            rename[old] = p["name"] = new
        taken.add(_norm(p["name"]))
    if rename:
        for p in parts:
            place = p.get("place")
            if isinstance(place, dict) and place.get("on") in rename:
                p["place"] = dict(place, on=rename[place["on"]])     # a copy: the recipe's own stays
    return parts


def layout(items, scene_boxes=None, designed=None, taken=None):
    """Give every item of a plan a place. Returns a list of instances, one per object to build.

    An item without a usable anchor stands at the origin if it is the first thing, otherwise beside
    what was placed before it -- a plan must never stack everything on one spot. `taken`: the names
    of every object the scene has (a new part never takes the name of another thing's part).
    """
    boxes = dict(scene_boxes or {})
    taken = {_norm(n) for n in (taken or ())} | {_norm(n) for n in boxes}
    out, notes = [], []
    last = None
    for item in _anchors_first(items):
        key = recipe_key(item.get("recipe"), designed)
        if key is None:
            notes.append(f"no recipe for {item.get('recipe')!r}")
            continue
        recipe = designed[key] if designed and key in designed else RECIPES[key]
        recipe = scale_recipe(recipe, item.get("size"))
        size = recipe["size"]
        count = max(1, min(int(item.get("count") or 1), 40))
        place = dict(item.get("place") or {})
        if place.get("relation"):
            rel = relation_word(place["relation"])
            if rel is None:
                notes.append(f"{item.get('id') or key}: {place['relation']!r} is not a relation, placed next to")
            place["relation"] = rel or "next_to"
        if place.get("distance") not in PLACE.GAP:
            place.pop("distance", None)
        anchor_name, anchor = find_anchor(place.get("anchor"), boxes)
        if anchor_name == SCENE:
            place["relation"] = scene_relation(place.get("relation"))
        if place.get("relation") == "between" and anchor is not None:
            # "between A and B": anchor A, and B (a second anchor); the middle of the two
            and_name, and_box = find_anchor(place.get("and"), boxes)
            if and_box is None:
                notes.append(f"{item.get('id') or key}: between needs a second thing ('and'), "
                             f"{place.get('and')!r} is not in the scene; placed next to")
                place["relation"] = "next_to"
            else:
                place["between"] = [anchor_name, and_name]
                place["between_boxes"] = [anchor, and_box]
        if anchor is None and not place.get("anchor") and item.get("zone"):
            # "a man on the platform" comes back as zone: platform with no place. If the scene has
            # that thing the item stands ON it (otherwise a second person "next to him" can be pushed
            # to the far end of the slab)
            zone_name, zone_box = find_anchor(item["zone"], boxes)
            if zone_box is not None:
                anchor_name, anchor = zone_name, zone_box
                place = {"anchor": zone_name, "relation": "on_top_of", "distance": "touching"}
        if anchor is None and place.get("anchor") and not str(place["anchor"]).startswith("zone:"):
            notes.append(f"{item.get('id') or key}: anchor {place['anchor']!r} is not in the scene")
        if anchor is None and last is not None:
            anchor_name, anchor = last
            place = {"relation": "next_to", "distance": place.get("distance") or "medium"}
        elif anchor is None and boxes:
            # the first thing of a request that states no place, in a scene that already has
            # things: beside what is there, never at the origin through it ("build me a chair",
            # then "build me a table": the table would stand inside the chair)
            anchor_name, anchor = SCENE, scene_box(boxes)
            place = {"relation": "next_to", "distance": place.get("distance") or "medium"}
            notes.append(f"{item.get('id') or key}: no place stated, put beside what the scene has")
        base_id = str(item.get("id") or key).rstrip("0123456789").rstrip("_") or key
        title = recipe["title"]
        for k in range(count):
            if anchor is None:
                origin = [0.0, 0.0, 0.0] if k == 0 else [k * (size[0] + 0.4), 0.0, 0.0]
            elif count > 1 and place.get("relation") in ("on_top_of", "front_of", "behind") \
                    and not place.get("arrangement"):
                origin = _spread(place, anchor, size, count, k)
            else:
                arr = place.get("arrangement") or ({"kind": "row"} if count > 1 else None)
                res = PLACE.resolve(dict(place, arrangement=arr), anchor, size, count=count, member=k,
                                    obstacles=[b for n, b in boxes.items() if n != anchor_name])
                c = res["centre"]
                origin = [c[0], c[1], c[2] - size[2] / 2.0]
            origin = [round(v, 4) for v in origin]
            name = title if k == 0 else f"{title}{k + 1}"
            n = 1
            while _norm(name) in {_norm(x) for x in boxes}:           # a second bench in a scene that has one
                n += 1
                name = f"{title}{k + 1 + n - 1}"
            suffix = name[len(title):]
            inst = {"id": name, "recipe": key, "title": title, "origin": origin, "size": size,
                    "material": item.get("material"), "anchor": anchor_name,
                    "relation": place.get("relation"),
                    "parts": unclash([dict(p, name=p["name"] + suffix) for p in recipe["parts"]], name)}
            taken.add(_norm(name))
            own_names(inst["parts"], name, taken)
            out.append(inst)
            boxes[name] = _item_box(origin, size)
        last = (out[-1]["id"], union(boxes[i["id"]] for i in out[-count:])) if out else last
    return out, notes


def _spread(place, anchor, size, count, k):
    """Several of one thing on / in front of / behind a long anchor: evenly along its long side."""
    lo, hi = anchor["lo"], anchor["hi"]
    long_axis = 0 if (hi[0] - lo[0]) >= (hi[1] - lo[1]) else 1
    short = 1 - long_axis
    t = (k + 0.5) / count
    pos = [0.0, 0.0, max(lo[2], 0.0)]              # on the ground at the lowest (see place.resolve)
    pos[long_axis] = lo[long_axis] + (hi[long_axis] - lo[long_axis]) * t
    gap = PLACE.GAP[place.get("distance") or "touching"]
    rel = place.get("relation")
    if rel == "on_top_of":
        pos[short] = (lo[short] + hi[short]) / 2.0
        pos[2] = hi[2] + gap
        side = place.get("side")
        if side in ("front", "back"):                     # along the front or the back edge
            edge = lo[1] + size[1] / 2.0 + 0.1 if side == "front" else hi[1] - size[1] / 2.0 - 0.1
            pos[1] = edge if short == 1 else pos[1]
    elif rel == "front_of":
        pos[short] = lo[short] - gap - size[short] / 2.0
    else:
        pos[short] = hi[short] + gap + size[short] / 2.0
    return pos


def part_location(inst, part):
    return [round(inst["origin"][i] + part["offset"][i], 3) for i in range(3)]


def part_sentence(inst, part):
    """One part as the instruction the build model follows ."""
    x, y, z = part_location(inst, part)
    name, shape = part["name"], part["shape"]
    if shape in ("cube", "ico", "plane", "prism"):
        a, b, c = part["scale"]
        what = {"cube": "a cube", "ico": "an ico sphere", "plane": "a plane", "prism": "a triangular prism"}[shape]
        return f"Add {what} named {name} at {x}, {y}, {z} with a scale of {a}, {b}, {c}."
    if shape in ("cylinder", "cone"):
        top = f", a top radius of {part['radius2']}" if "radius2" in part else ""
        return (f"Add a {shape} named {name} at {x}, {y}, {z} with a radius of {part['radius']}{top} "
                f"and a depth of {part['depth']}.")
    if shape == "torus":
        return (f"Add a torus named {name} at {x}, {y}, {z} with a major radius of {part['major']} "
                f"and a minor radius of {part['minor']}.")
    if shape == "uv_sphere":
        return f"Add a UV sphere named {name} at {x}, {y}, {z} with a radius of {part['radius']}."
    raise ValueError(shape)


def part_call(inst, part):
    """The same part as the call itself: what the harness runs when the model did not make it."""
    shape = {"ico": "ico_sphere"}.get(part["shape"], part["shape"])
    call = {"tool": "add_primitive", "shape": shape, "name": part["name"],
            "location": part_location(inst, part)}
    if "scale" in part:
        call["scale"] = part["scale"]
    if "radius" in part:
        call["radius"] = part["radius"]
    if "radius2" in part:
        call["radius2"] = part["radius2"]
    if "depth" in part:
        call["depth"] = part["depth"]
    if "major" in part:
        call["major_radius"], call["minor_radius"] = part["major"], part["minor"]
    if part.get("rotation_deg"):
        call["rotation_deg"] = part["rotation_deg"]
    return call


def chunks(inst):
    """[(sentence for the model, [parts])]: at most CHUNK parts of one object per ask."""
    out = []
    parts = inst["parts"]
    for i in range(0, len(parts), CHUNK):
        group = parts[i:i + CHUNK]
        head = (f"Build the whole {inst['id']} in one go, all {len(group)} parts in a single reply. "
                f"Add exactly these objects, one each, and nothing else: ")
        out.append((head + " ".join(part_sentence(inst, p) for p in group), group))
    return out


def SENTENCE_NAMES(text):
    """The part names one instruction asks for (used to check a chunk never exceeds CHUNK)."""
    return re.findall(r" named (\S+) at ", text)


def check_part(inst, part, objects):
    """'exact', 'moved' (there, wrong place or size) or 'missing', and the calls that put it right."""
    obj = next((o for o in objects if o.get("name") == part["name"]), None)
    want = part_location(inst, part)
    if obj is None:
        return "missing", [part_call(inst, part)]
    loc, dims = obj.get("loc") or [0, 0, 0], obj.get("dims") or [0, 0, 0]
    off_place = any(abs(loc[i] - want[i]) > LOC_TOL for i in range(3))
    off_size = any(abs(dims[i] - part["dims"][i]) > max(DIM_TOL * part["dims"][i], 0.01) for i in range(3))
    if not off_place and not off_size:
        # a turned part (a boiler lying along the track) reads the same from outside whether the
        # model turned it or not, so its rotation is always stated by the harness
        turn = [{"tool": "set_transform", "object": part["name"], "rotation_deg": part["rotation_deg"]}] \
            if part.get("rotation_deg") else []
        return "exact", turn
    fix = {"tool": "set_transform", "object": part["name"], "location": want}
    if part.get("rotation_deg"):
        fix["rotation_deg"] = part["rotation_deg"]
    calls = []
    if off_size and all(d > 1e-6 for d in dims):
        # the object's own scale is unknown from outside, so bake it and scale by the measured ratio
        calls.append({"tool": "apply_transform", "object": part["name"], "scale": True})
        fix["scale"] = [round(part["dims"][i] / dims[i], 5) for i in range(3)]
    calls.append(fix)
    return "moved", calls


def part_faults(inst, part, objects):
    """(wrong place, wrong size) for a part that is there: the two things `moved` can mean, counted
    apart so a run says whether the build model misses positions or sizes."""
    obj = next((o for o in objects if o.get("name") == part["name"]), None)
    if obj is None:
        return False, False
    want = part_location(inst, part)
    loc, dims = obj.get("loc") or [0, 0, 0], obj.get("dims") or [0, 0, 0]
    return (any(abs(loc[i] - want[i]) > LOC_TOL for i in range(3)),
            any(abs(dims[i] - part["dims"][i]) > max(DIM_TOL * part["dims"][i], 0.01) for i in range(3)))


# ---- finishes: recipes checked in Blender 5.2.2 ------------
# They need no knowledge of a part's shape, only its size, so the same calls serve a part the
# copilot has just built and a thing that is already in the scene ("make the squirrel smooth").

def smooth_calls(name, dims):
    """Round the hard edges a little (they hold the shape), subdivide, shade smooth. Subdivision
    alone pinches a capped shape (a cylinder leg) into a spindle; the bevel prevents it."""
    low = min([d for d in dims if d > 1e-6] or [0.1])
    return [{"tool": "add_modifier", "object": name, "modifier": "BEVEL", "width": round(0.08 * low, 4), "segments": 3},
            {"tool": "add_modifier", "object": name, "modifier": "SUBSURF", "levels": 2},
            {"tool": "shade_smooth", "object": name, "smooth": True}]


def skin_calls(names, dims_of, extent):
    """Melt several parts into ONE surface: each part is rounded and subdivided for real, the
    parts are joined, the joined mesh is rebuilt as one skin and smoothed. The first name is the
    name of the result; the others are gone. (Remeshing the raw parts keeps every facet: the
    subdivision has to come first.)"""
    calls = []
    for n in names:
        low = min([d for d in dims_of.get(n) or [] if d > 1e-6] or [0.1])
        calls += [{"tool": "add_modifier", "object": n, "modifier": "BEVEL", "width": round(0.08 * low, 4), "segments": 3},
                  {"tool": "apply_modifier", "object": n},
                  {"tool": "add_modifier", "object": n, "modifier": "SUBSURF", "levels": 2},
                  {"tool": "apply_modifier", "object": n}]
    one = names[0]
    calls += [{"tool": "join", "objects": list(names)},
              {"tool": "add_modifier", "object": one, "modifier": "REMESH", "voxel_size": round(max(0.025 * extent, 0.002), 4)},
              {"tool": "apply_modifier", "object": one}]
    calls += [{"tool": "add_modifier", "object": one, "modifier": "SMOOTH", "strength": 1.0} for _ in range(3)]
    calls.append({"tool": "shade_smooth", "object": one, "smooth": True})
    return calls


HOLLOW_WALL = 0.12


def hollow_calls(inst, part):
    """An open vessel: cut a smaller copy of the part out of it from above, leaving a wall and a
    floor. The cutter is deleted once the cut is applied: nothing named `*Cut` stays in the scene
    (otherwise hidden `GiftBox*Cut` objects are left under the item)."""
    call = part_call(inst, part)
    wall = HOLLOW_WALL * min(part["dims"][0], part["dims"][1])
    cut = dict(call, name=part["name"] + "Cut")
    cut["location"] = [call["location"][0], call["location"][1], round(call["location"][2] + wall, 4)]
    fx, fy = [(part["dims"][i] - 2 * wall) / part["dims"][i] for i in (0, 1)]
    if "scale" in cut:
        cut["scale"] = [round(cut["scale"][0] * fx, 5), round(cut["scale"][1] * fy, 5), cut["scale"][2]]
    if "radius" in cut:
        cut["radius"] = round(cut["radius"] * fx, 5)
    if "radius2" in cut:
        cut["radius2"] = round(cut["radius2"] * fx, 5)
    return [cut,
            {"tool": "add_modifier", "object": part["name"], "modifier": "BOOLEAN", "operation": "DIFFERENCE",
             "target": cut["name"]},
            {"tool": "apply_modifier", "object": part["name"]},
            {"tool": "delete_object", "objects": [cut["name"]]}]


def finish_calls(inst):
    """Paint the parts, hollow and smooth them as the spec says, put them under one parent (the
    item is one thing to move), and melt the parts that share a skin."""
    calls = []
    for part in inst["parts"]:
        m = part.get("material")
        mat = m if isinstance(m, dict) else (MATERIALS.get(m) or {})
        if mat:
            call = {"tool": "set_material", "object": part["name"], "name": mat.get("name", "Mat"),
                    "color": mat.get("color", [0.8, 0.8, 0.8])}
            for k in ("roughness", "metallic", "emission_color", "emission_strength", "alpha"):
                if k in mat:
                    call[k] = mat[k]
            calls.append(call)
    for part in inst["parts"]:
        if part.get("hollow"):
            calls += hollow_calls(inst, part)
    skins = {}
    for part in inst["parts"]:
        if part.get("skin"):
            skins.setdefault(part["skin"], []).append(part)
        elif part.get("finish") == "smooth" and part.get("hollow"):
            # a hollowed part is a cut mesh: subdividing it closes the opening (seen in Blender,
            # a cup comes out with a lid). Smooth shading only.
            calls.append({"tool": "shade_smooth", "object": part["name"], "smooth": True})
        elif part.get("finish") == "smooth":
            calls += smooth_calls(part["name"], part["dims"])
    calls.append({"tool": "add_empty", "name": inst["id"], "location": inst["origin"]})
    calls += [{"tool": "parent", "child": n, "parent": inst["id"]} for n in [p["name"] for p in inst["parts"]]]
    for members in skins.values():
        if len(members) == 1:
            calls += smooth_calls(members[0]["name"], members[0]["dims"])
            continue
        los = [min(part_location(inst, p)[i] - p["dims"][i] / 2.0 for p in members) for i in range(3)]
        his = [max(part_location(inst, p)[i] + p["dims"][i] / 2.0 for p in members) for i in range(3)]
        calls += skin_calls([p["name"] for p in members], {p["name"]: p["dims"] for p in members},
                            max(his[i] - los[i] for i in range(3)))
    return calls


EXACT = re.compile(r"\bnamed\s+\S+\s+at\s+-?\d")


_NUM = r"(-?\d+(?:\.\d+)?)"
_VEC = _NUM + r"\s*,\s*" + _NUM + r"\s*,\s*" + _NUM
EXACT_SHAPES = {"cube": "cube", "cylinder": "cylinder", "cone": "cone", "torus": "torus", "plane": "plane",
                "ico sphere": "ico_sphere", "icosphere": "ico_sphere", "uv sphere": "uv_sphere", "sphere": "uv_sphere",
                "monkey": "monkey", "circle": "circle", "grid": "grid"}
_EXACT_FULL = re.compile(
    r"^\s*add\s+an?\s+(?P<shape>" + "|".join(sorted(EXACT_SHAPES, key=len, reverse=True)) + r")\s+named\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)\s+at\s+" + _VEC + r"(?P<rest>.*?)\s*\.?\s*$", re.I)
_EXACT_PARTS = {
    "scale": re.compile(r"^\s*(?:,|and)?\s*with\s+a\s+scale\s+of\s+" + _VEC, re.I),
    "radius_depth": re.compile(r"^\s*(?:,|and)?\s*with\s+a\s+radius\s+of\s+" + _NUM + r"\s+and\s+a\s+depth\s+of\s+" + _NUM, re.I),
    "torus": re.compile(r"^\s*(?:,|and)?\s*with\s+a\s+major\s+radius\s+of\s+" + _NUM + r"\s+and\s+a\s+minor\s+radius\s+of\s+" + _NUM, re.I),
    "rotation": re.compile(r"^\s*(?:,|and)?\s*(?:with\s+a\s+rotation\s+of|rotated(?:\s+by)?)\s+" + _VEC + r"(?:\s*degrees)?", re.I),
}


def exact_shape(text):
    """"Add a cube named Seat at 0, 0, 0.45 with a scale of 0.4, 0.4, 0.05." -> the `shape` change it states, read by
    code (every number is in the sentence, so no model is asked and none can miscopy one). None when the sentence is
    not wholly in this form (it then goes to the edit model as before)."""
    m = _EXACT_FULL.match(str(text or ""))
    if not m:
        return None
    ch = {"do": "shape", "shape": EXACT_SHAPES[m.group("shape").lower()], "name": m.group("name"),
          "at": [float(m.group(i)) for i in (3, 4, 5)]}
    rest = m.group("rest")
    while rest.strip():
        for key, rx in _EXACT_PARTS.items():
            p = rx.match(rest)
            if p:
                v = [float(x) for x in p.groups()]
                if key == "scale":
                    ch["scale"] = v
                elif key == "radius_depth":
                    ch["radius"], ch["depth"] = v
                elif key == "torus":
                    ch["major_radius"], ch["minor_radius"] = v
                else:
                    ch["rotation"] = v
                rest = rest[p.end():]
                break
        else:
            return None
    return ch


def is_exact_instruction(text):
    """"Add a cube named X at 1, 2, 3 ..." is already the instruction a plan compiles TO: it goes
    straight to Build. (The takes are made of these; planning them would build a whole table for
    the sentence that asks for its top.)"""
    return bool(EXACT.search(str(text or "")))


def plan_items(plan):
    """A planner answer in either shape -> a list of items.

    v2 answers {"items": [...]}; the planner that ships today answers one flat object
    {"recipe", "count", "material", "zone"} with no place -- that is one item, placed by layout().
    """
    if not isinstance(plan, dict):
        return []
    if isinstance(plan.get("items"), list):
        return [i for i in plan["items"] if isinstance(i, dict)]
    if plan.get("recipe"):
        item = {"id": plan["recipe"], "recipe": plan["recipe"], "count": plan.get("count", 1),
                "material": plan.get("material")}
        if plan.get("zone"):
            # the flat plan's only place word is its zone ("on the platform"): if the scene has a
            # thing of that name the item goes onto it; if not, layout() falls back as usual
            item["place"] = {"anchor": plan["zone"], "relation": "on_top_of", "distance": "touching"}
        return [item]
    return []


def scene_boxes(objects, groups=None):
    """{name: box} for everything a place word may name: every object, and every built item."""
    boxes = {o["name"]: box_of(o) for o in objects if o.get("name") and any(o.get("dims") or [])}
    # a built item is its parent and the parts under it. The session remembers what it built; a
    # new session (the add-on starts one per request) reads the same thing from the scene itself.
    groups = dict(groups or {})
    for o in objects:
        if o.get("parent"):
            members = groups.setdefault(o["parent"], [])
            if o["name"] not in members:
                members.append(o["name"])
    for gid, names in groups.items():
        b = union(boxes[n] for n in names if n in boxes)
        if b:
            boxes[gid] = b
    return boxes


def parse_move(text, boxes):
    """"put the bench behind the station, close to it" -> (subject name, place block) or None.

    The edit half of placement: the words are read here, the metres come from place.resolve. Both
    the thing to move and the anchor must be things the scene has; otherwise this returns None and
    the request goes to the model as before.
    """
    low = " " + re.sub(r"\s+", " ", re.sub(r"[.,!?;](?=\s|$)", " ", str(text or "").lower())) + " "
    if not MOVE_VERB.search(low):
        return None
    for phrase, relation in END_PHRASES + RELATION_PHRASES:
        at = low.find(" " + phrase + " ")
        if at < 0:
            continue
        head, tail = low[:at], low[at + len(phrase) + 2:]
        subject = _named_in(head, boxes)
        anchor = _named_in(tail, boxes)
        if (phrase, relation) in END_PHRASES:
            # "at the north end" (of the scene). "At the north end of the platform" is a place ON
            # the platform, which these words cannot say: that one is left to the planner.
            anchor = None if anchor else SCENE
        elif anchor is None and set(tail.split()) & set(SCENE_WORDS):
            if relation not in PLACE.AXIS and relation != "centre_of":
                continue                    # "on the ground" is not a place beside the scene
            anchor = SCENE
        if subject and anchor and subject != anchor:
            distance = next((word for words, word in DISTANCE_PHRASES if words in low), None)
            metres = re.search(r"(\d+(?:\.\d+)?)\s*(?:m\b|metres?|meters?)", low)
            if metres:
                distance = PLACE.bucket(float(metres.group(1)))
            if distance is None:
                distance = "touching" if relation in ("on_top_of", "under", "against") else "small"
            return subject, {"anchor": anchor, "relation": relation, "distance": distance}
    return None


# "smooth the squirrel", "make the cat's head and ears smooth but keep the legs sharp",
# "merge the head and the body of the cat": a finish ordered for what the scene already has.
SMOOTH_WORDS = re.compile(r"\b(smooth|smoother|smoothen|soften|softer|rounded|round off|organic)\b")
SHARP_WORDS = re.compile(r"\b(sharp|sharper|sharpen|faceted|blocky|low[- ]poly|flat[- ]shaded|angular)\b")
MERGE_WORDS = re.compile(r"\b(merge|blend|fuse|melt|weld|join)\b|\binto one\b|\bone (skin|piece|surface)\b")
CLAUSE_SPLIT = re.compile(r"\s+but\s+|;|\s+while\s+|\s+and keep\s+|,\s*keep\s+|\s+and leave\s+|,\s*leave\s+"
                          r"|\s+and\s+(?=(?:then\s+)?(?:smooth|soften|sharpen|merge|blend|fuse|melt|make)\b)"
                          r"|\s+then\s+(?=(?:smooth|soften|sharpen|merge|blend|fuse|melt|make)\b)")


def _name_words(name, thing=""):
    """The words of a part name without the thing's own name: CatEar1 of Cat -> {"ear"}."""
    words = [w.lower() for w in re.findall(r"[A-Z][a-z]+|[a-z]+", str(name))]
    own = {w.lower() for w in re.findall(r"[A-Z][a-z]+|[a-z]+", str(thing))}
    return {w for w in words if w not in own and len(w) > 1}


def parse_finish(text, objects, groups=None):
    """[(kind, [object names])] for a sentence that orders a finish on things or parts the scene
    has, or None. kind: smooth | sharp | merge. A clause that names parts ("the head and the
    ears") gets those parts; a clause that names only the thing gets all its parts.

        "make the squirrel smooth"                         -> [("smooth", every part of Squirrel)]
        "smooth the cat's head but keep the legs sharp"    -> [("smooth", [CatHead]), ("sharp", [CatLeg1..4])]
        "merge the head and the body of the cat"           -> [("merge", [CatBody, CatHead])]
    """
    low = " " + re.sub(r"\s+", " ", re.sub(r"[.!?]", " ", str(text or "").lower())) + " "
    if not (SMOOTH_WORDS.search(low) or SHARP_WORDS.search(low) or MERGE_WORDS.search(low)):
        return None
    boxes = scene_boxes(objects, groups)
    children = {}
    for o in objects:
        if o.get("parent"):
            children.setdefault(o["parent"], []).append(o["name"])
    for gid, names in (groups or {}).items():
        have = children.setdefault(gid, [])
        have += [n for n in names if n not in have and n in boxes]
    thing_boxes = {n: b for n, b in boxes.items() if n in children or not any(n in c for c in children.values())}
    whole = _named_in(low, thing_boxes)
    out = []
    for clause in [c for c in CLAUSE_SPLIT.split(low) if c.strip()]:
        kind = "merge" if MERGE_WORDS.search(clause) else "sharp" if SHARP_WORDS.search(clause) \
            else "smooth" if SMOOTH_WORDS.search(clause) else None
        thing = _named_in(clause, thing_boxes) or whole
        if kind is None or thing is None:
            continue
        parts = [n for n in children.get(thing, []) if not n.endswith("Cut")]
        said = set(re.findall(r"[a-z]+", clause))
        said |= {w[:-1] for w in said if w.endswith("s")}
        named = [n for n in parts if _name_words(n, thing) & said]
        names = named or parts or [thing]
        if kind == "merge" and len(names) < 2:
            continue
        out.append((kind, names))
    return out or None


def finish_order_calls(orders, objects):
    """The calls for parse_finish's answer, and notes for what cannot be done."""
    by = {o["name"]: o for o in objects}
    calls, notes = [], []
    for kind, names in orders:
        if kind == "smooth":
            for n in names:
                if "SUBSURF" in (by.get(n, {}).get("mods") or []):
                    notes.append(f"{n} is smooth already")
                    continue
                calls += smooth_calls(n, by.get(n, {}).get("dims") or [0.1, 0.1, 0.1])
        elif kind == "sharp":
            calls += [{"tool": "shade_smooth", "object": n, "smooth": False} for n in names]
            if any((by.get(n, {}).get("mods") or []) for n in names):
                notes.append("flat shading set; a rounding that was added before stays (no tool removes it): use Undo for that")
        else:
            dims = {n: by.get(n, {}).get("dims") or [0.1, 0.1, 0.1] for n in names}
            los = [min(by[n]["loc"][i] - dims[n][i] / 2.0 for n in names if n in by) for i in range(3)]
            his = [max(by[n]["loc"][i] + dims[n][i] / 2.0 for n in names if n in by) for i in range(3)]
            calls += skin_calls(names, dims, max(his[i] - los[i] for i in range(3)))
    return calls, notes


def _named_in(fragment, boxes):
    """The scene name a fragment of a sentence talks about.

    A name written out in full wins, the longest first ("bench2" before "bench"). Otherwise the
    word without its number is enough ("the bench" when the scene has Bench and Bench2), and then
    the plain one is meant, not the numbered copy.
    """
    words = _norm(fragment)
    full = [name for name in boxes if _norm(name) and _norm(name) in words]
    if full:
        return max(full, key=lambda name: len(_norm(name)))
    bare = [name for name in boxes
            if len(_norm(name).rstrip("0123456789")) > 2 and _norm(name).rstrip("0123456789") in words]
    if bare:
        return min(bare, key=lambda name: len(_norm(name)))
    # "the bus station", "the station": the scene calls it StationBuilding (the library's title).
    # One word of the name is enough when it points at ONE thing: the names that carry the word
    # must all lie inside the biggest of them (a built item and its parts). Two stations: None.
    said = set(re.findall(r"[a-z]{4,}", str(fragment).lower()))
    hits = [name for name in boxes if said & {w.lower() for w in re.findall(r"[A-Z][a-z]{3,}|[a-z]{4,}", name)}]
    if not hits:
        return None
    volume = lambda b: max(1e-9, (b["hi"][0] - b["lo"][0]) * (b["hi"][1] - b["lo"][1]) * (b["hi"][2] - b["lo"][2]))
    whole = max(hits, key=lambda name: volume(boxes[name]))
    inside = lambda b, c: all(b["lo"][i] >= c["lo"][i] - 0.01 and b["hi"][i] <= c["hi"][i] + 0.01 for i in range(3))
    return whole if all(inside(boxes[name], boxes[whole]) for name in hits) else None
