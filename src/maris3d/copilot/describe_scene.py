# SPDX-License-Identifier: Apache-2.0
"""The scene in words, for a model to read. No numbers a model would have to work with.

The compiler turns place words into metres (place.resolve). This module goes the other way with
the SAME tables: a thing's box against the other things' boxes -> anchor, relation, distance word
(place.bucket), the side word (place.side_of) and a compass facing. Lookup and comparison only;
no language is read.

Two levels, so a big scene fits:

    Scene:
    Sofa (sofa): against WallBack, touching, facing south, oak
    ChristmasTree (christmas tree): left_of Sofa, small, facing south, green
    House1-20 (house) x20: behind Road, large, facing south, brick
    Parts of ChristmasTree: TreeTrunk cylinder walnut; TreeCone1 cone green on TreeTrunk on_top_of; ...
    Last: ChristmasTree

Every thing has one line; the parts are written only for the things in `open_things` (the last one
changed, the Blender selection, or what the model asked to look at). Copies of one thing (same
noun, same part names but for the number, same colour) are one line.
"""
import re

from . import apply_change as AC
from . import place as PLACE

FACING_WORDS = {0: "south", 90: "east", 180: "north", 270: "west"}
ON_FLOOR = 0.03            # m: a bottom this close to another top stands on it
OVERLAP = 0.3              # share of the footprint that must lie over the other thing


def _footprint_share(box, other):
    """The share of `box`'s footprint that lies over `other`'s."""
    ox = max(0.0, min(box["hi"][0], other["hi"][0]) - max(box["lo"][0], other["lo"][0]))
    oy = max(0.0, min(box["hi"][1], other["hi"][1]) - max(box["lo"][1], other["lo"][1]))
    area = max(1e-9, (box["hi"][0] - box["lo"][0]) * (box["hi"][1] - box["lo"][1]))
    return ox * oy / area


def relation_to(box, other):
    """(relation, clear gap in metres) of `box` seen from `other`, in the outline's words."""
    if _footprint_share(box, other) >= OVERLAP:
        if box["lo"][2] >= other["hi"][2] - ON_FLOOR:
            return "on_top_of", max(0.0, box["lo"][2] - other["hi"][2])
        if box["hi"][2] <= other["lo"][2] + ON_FLOOR:
            return "under", max(0.0, other["lo"][2] - box["hi"][2])
    gx = max(other["lo"][0] - box["hi"][0], box["lo"][0] - other["hi"][0])
    gy = max(other["lo"][1] - box["hi"][1], box["lo"][1] - other["hi"][1])
    if gx >= gy:
        rel = "left_of" if box["hi"][0] <= other["lo"][0] + 1e-6 or \
            (box["lo"][0] + box["hi"][0]) < (other["lo"][0] + other["hi"][0]) else "right_of"
        return rel, max(0.0, gx)
    rel = "front_of" if (box["lo"][1] + box["hi"][1]) < (other["lo"][1] + other["hi"][1]) else "behind"
    return rel, max(0.0, gy)


def _volume(b):
    return max(1e-9, (b["hi"][0] - b["lo"][0]) * (b["hi"][1] - b["lo"][1]) * (b["hi"][2] - b["lo"][2]))


def place_words(box, others):
    """{"anchor", "relation", "distance"} for a box among other named boxes: the nearest other thing
    (by clear gap; at equal gaps the bigger one), or the scene's middle when there is none."""
    best = None
    for name, other in sorted(others.items()):
        rel, gap = relation_to(box, other)
        key = (round(gap, 3), -_volume(other), name)
        if best is None or key < best[0]:
            best = (key, name, rel, gap)
    if best is None:
        c = PLACE.box_centre(box)
        if abs(c[0]) < 0.5 and abs(c[1]) < 0.5:
            return {"anchor": "scene", "relation": "centre_of"}
        rel = ("right_of" if c[0] > 0 else "left_of") if abs(c[0]) >= abs(c[1]) else \
            ("behind" if c[1] > 0 else "front_of")
        return {"anchor": "scene", "relation": rel, "distance": PLACE.bucket(max(abs(c[0]), abs(c[1])))}
    _, name, rel, gap = best
    return {"anchor": name, "relation": rel, "distance": PLACE.bucket(gap)}


def facing_word(yaw):
    """The compass word nearest the thing's turn (yaw 0 looks south)."""
    q = int(round((float(yaw) % 360.0) / 90.0)) % 4 * 90
    return FACING_WORDS[q]


def main_colour(spec):
    """The colour most of the thing's volume has."""
    vol = {}
    for p in spec["parts"]:
        c = p.get("color")
        if c:
            vol[c] = vol.get(c, 0.0) + abs(p["size"][0] * p["size"][1] * p["size"][2])
    return max(sorted(vol), key=lambda c: vol[c]) if vol else None


def part_line(spec):
    """The parts of one thing in words: name, shape, colour and where it sits on another part."""
    out = []
    for p in spec["parts"]:
        words = [p["name"], p["shape"], str(p.get("color") or "")]
        if p.get("axis"):
            words.append("lying " + p["axis"])
        pl = p.get("place")
        if pl:
            words.append(f"{pl.get('relation')} {pl.get('on')}")
        out.append(" ".join(w for w in words if w))
    return f"Parts of {spec['id']}: " + "; ".join(out)


def _family(spec):
    """What makes two things copies: noun, part names without their number suffix, main colour."""
    strip = re.compile(r"\d+$")
    return (spec["object"], tuple(strip.sub("", p["name"]) for p in spec["parts"]), main_colour(spec))


def _union(boxes):
    return {"lo": [min(b["lo"][i] for b in boxes) for i in range(3)],
            "hi": [max(b["hi"][i] for b in boxes) for i in range(3)]}


def describe_scene(specs, last=None, open_things=(), extra_boxes=None, group=True):
    """The scene as words. `specs`: {id: stored spec} (apply_change), `extra_boxes`: {name: box} of
    scene objects that are not built things (a wall, the road), named as anchors only."""
    boxes = {sid: AC._spec_box(s) for sid, s in specs.items()}
    anchors = dict(extra_boxes or {})
    families = {}
    for sid, s in specs.items():
        families.setdefault(_family(s) if group else sid, []).append(sid)
    lines = ["Scene:"]
    for fam, ids in families.items():
        if len(ids) > 1:
            box = _union([boxes[i] for i in ids])
            others = {n: b for n, b in list(boxes.items()) + list(anchors.items()) if n not in ids}
            head = f"{ids[0]}-{ids[-1]} ({AC.noun_of(specs[ids[0]]['object'])}) x{len(ids)}"
        else:
            box = boxes[ids[0]]
            others = {n: b for n, b in list(boxes.items()) + list(anchors.items()) if n != ids[0]}
            head = f"{ids[0]} ({AC.noun_of(specs[ids[0]]['object'])})"
        s = specs[ids[0]]
        pw = place_words(box, others)
        where = f"{pw['relation']} {pw['anchor']}" + (f", {pw['distance']}" if pw.get("distance") else "")
        words = [where, "facing " + facing_word(s["yaw"])]
        if s.get("size_word"):
            words.insert(0, s["size_word"])
        colour = main_colour(s)
        if colour:
            words.append(colour)
        lines.append(f"{head}: " + ", ".join(words))
    for sid in open_things:
        if sid in specs:
            lines.append(part_line(specs[sid]))
    if last is None and specs:
        last = list(specs)[-1]
    if last:
        lines.append(f"Last: {last}")
    return "\n".join(lines)


# ---- one pass of the edit model: what the harness feeds --------
#
# Every pass is built fresh; nothing is carried from the last pass but the request's clarifications.
#
#     Scene: <flat list: a line per thing or group, with place words; or nouns with counts>
#     Focus: <parts of the things being worked on: Last, the selection, or what the model asked for>
#     Last: <name>
#     Request: <the user's words>
#     Clarified: <the user's answer to a question, one line each, at most two>
#
# The budget is in tokens, estimated from characters (the harness has no tokenizer; ~3.5 chars a
# token for this text, measured on the Qwen tokenizer).

CHARS_PER_TOKEN = 3.5
BUDGET = 1500
SYSTEM_TOKENS = 500            # edit_words.EDIT_SYSTEM: 495 Qwen tokens


def est_tokens(text):
    return int(len(text) / CHARS_PER_TOKEN) + 1


_RANGE = re.compile(r"^([A-Za-z_]+?)(\d*)-([A-Za-z_]+?)(\d+)$")


def expand(name, specs):
    """The things a name stands for: an exact thing, a range `House1-House20` (as the flat list
    writes a group), or a noun (`house`, `houses`: every thing of that noun). [] when none."""
    if name in specs:
        return [name]
    m = _RANGE.match(str(name or ""))
    if m and m.group(1) == m.group(3):
        lo, hi = int(m.group(2) or 1), int(m.group(4))
        ids = [i for i in specs if re.fullmatch(re.escape(m.group(1)) + r"(\d*)", i)
               and lo <= int(re.fullmatch(re.escape(m.group(1)) + r"(\d*)", i).group(1) or 1) <= hi]
        if ids:
            return ids
    noun = str(name or "").lower().replace("_", " ").strip()
    for n in (noun, noun[:-1] if noun.endswith("s") else None, noun[:-2] if noun.endswith("es") else None):
        if n:
            ids = [i for i, s in specs.items() if AC.noun_of(s["object"]) == n]
            if ids:
                return ids
    return []


def nouns_line(specs):
    """The smallest flat list: every noun with its count."""
    count = {}
    for s in specs.values():
        n = AC.noun_of(s["object"])
        count[n] = count.get(n, 0) + 1
    return "Scene: " + ", ".join(f"{n} x{c}" if c > 1 else n for n, c in count.items())


OTHER_KINDS = {"CAMERA": "camera", "LIGHT": "light", "FONT": "text"}


def others_line(objects, specs):
    """'Others: Camera (camera), Sun (light), Sign (text)': the scene's cameras, lights and texts that are not
    parts of a built thing, so a follow-up ("make the sign say Closed", "point the camera at the tree") can name
    them. None when there are none. Read from the scene itself, so it holds after undo and in a new session."""
    member = set(specs) | {p["name"] for s in specs.values() for p in s.get("parts", [])}
    names = [f"{o['name']} ({OTHER_KINDS[o.get('type')]})" for o in objects or []
             if o.get("type") in OTHER_KINDS and o.get("name") not in member]
    return "Others: " + ", ".join(names) if names else None


def edit_input(specs, request, focus=(), last=None, clarified=(), extra_boxes=None, budget=BUDGET, others=None):
    """The user turn of one edit pass, within `budget` tokens (with the system prompt).
    Returns (text, notes): notes say what was cut, for the panel and the trace."""
    notes = []
    if last is None and specs:
        last = list(specs)[-1]
    want = []
    for name in list(focus) or ([last] if last else []):
        for i in expand(name, specs):
            if i not in want:
                want.append(i)
    tail = ([f"Last: {last}"] if last else []) + [f"Request: {request}"] + [f"Clarified: {c}" for c in list(clarified)[:2]]
    room = budget - SYSTEM_TOKENS - est_tokens("\n".join(tail))
    focus_lines = [part_line(specs[i]) for i in want]
    while focus_lines and est_tokens("\n".join(focus_lines)) > room * 0.6:
        focus_lines.pop()
    if len(focus_lines) < len(want):
        shown = len(focus_lines)
        notes.append(f"focus cut: {shown} of {len(want)} things shown")
        focus_lines.append(f"Too many to show: {len(want)} things; ask for fewer, or change them as a group")
    if not focus:
        # with no focus asked for, the other things' parts follow the last one's while they fit (the
        # same Focus lines a selection gives): "add a cushion on the seat" after a chair, legs and a back
        # showed only the back's parts, and the edit model named a Seat it had not been shown
        for sid in specs:
            if sid in want:
                continue
            line = part_line(specs[sid])
            if est_tokens("\n".join(focus_lines + [line])) > room * 0.6:
                break
            want.append(sid)
            focus_lines.append(line)
    room -= est_tokens("\n".join(focus_lines))
    flat = describe_scene(specs, last=None, open_things=(), extra_boxes=extra_boxes).splitlines()
    flat = [l for l in flat if not l.startswith("Last:")]
    if est_tokens("\n".join(flat)) > room:
        flat = [nouns_line(specs)]
        notes.append("scene shown as nouns with counts")
    if others:                       # 0.2.1: the cameras, lights and texts the kit words made (others_line)
        flat.append(others)
    body = flat + ([l.replace("Parts of ", "Focus: ", 1) for l in focus_lines] if focus_lines else []) + tail
    return "\n".join(body), notes
