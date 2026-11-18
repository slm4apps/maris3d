# SPDX-License-Identifier: Apache-2.0
"""The wire format the model was trained and scored on (native Qwen tool calls).

Rules copied from the scoring harness: tool result text is exactly "ok" or
"error: <last 200 chars>"; later user turns carry "[Scene objects: ...]"; a request
offers only the tools it needs plus two fixed distractors, never all 26.
"""
import hashlib
import json
import random
import re
from pathlib import Path

_DATA = Path(__file__).with_name("data") / "TOOLS.json"
_TOOLS = None


class _Place:
    """The two place.py functions scene_summary needs, copied so the add-on carries no
    dependency on the maintainers' test harness. Same tables as the maintainers' place.py (not part of
    this repository); that file
    stays the reference for the full resolver (relations, anchors, zones)."""

    LADDER = ((0.03, "touching"), (0.10, "tiny"), (0.25, "small"), (0.50, "medium"),
              (1.00, "large"), (2.00, "far"))
    FLOOR = 0.03

    @classmethod
    def side_of(cls, dx, dy, floor=None):
        floor = cls.FLOOR if floor is None else floor
        sx = "left" if dx < 0 else "right"
        sy = "front" if dy < 0 else "back"
        sx = sx if abs(dx) > floor else None
        sy = sy if abs(dy) > floor else None
        if sx and sy:
            return sy + "_" + sx
        return sx or sy

    @classmethod
    def bucket(cls, gap):
        for edge, word in cls.LADDER:
            if gap < edge:
                return word
        return "distant"


_place = _Place

# keyword -> tools the request is likely to need (same idea as the harness tool picker)
_HINTS = {
    "set_material": ("colo", "red", "blue", "green", "yellow", "white", "black", "metal", "glow", "material", "emiss"),
    "add_light": ("light", "lamp", "sun", "spot"),
    "add_camera": ("camera",),
    "add_text": ("text", "letters", "word"),
    "add_curve": ("curve", "path", "spline"),
    "add_modifier": ("array", "mirror", "bevel", "subdiv", "modifier", "ring", "solidify"),
    "apply_modifier": ("apply",),
    "keyframe": ("animat", "spin", "rotate", "bounce", "move to", "frame", "orbit"),
    "set_frame_end": ("animat", "frame", "seconds", "loop"),
    "parent": ("parent", "attach", "child"),
    "add_empty": ("empty", "group", "pivot"),
    "add_constraint": ("constraint", "track", "follow", "limit"),
    "add_geonodes": ("geometry node", "scatter", "geonode"),
    "shade_smooth": ("smooth",),
    "new_collection": ("collection",),
    "join": ("join", "merge", "combine"),
    "duplicate": ("copy", "duplicate", "clone", "twice", "three", "row of", "grid"),
    "uv_unwrap": ("uv",),
    "edit_mesh": ("extrude", "inset", "subdivide", "vertices", "faces"),
    "add_shape_key": ("shape key", "morph"),
    "scene_settings": ("world", "background", "sky", "frame rate", "resolution"),
}
_EDIT_TOOLS = ("set_transform", "set_material", "set_object", "duplicate")


def load_tools():
    """name -> OpenAI-style tool schema, exactly the manifest the model was scored with."""
    global _TOOLS
    if _TOOLS is None:
        _TOOLS = json.loads(_DATA.read_text(encoding="utf-8"))
    return _TOOLS


def tools_sha256():
    return hashlib.sha256(_DATA.read_bytes()).hexdigest()


def trim_tools(request, mode="build", extra=(), distractors=2):
    """Tool names to offer for one request: needed + deterministic distractors."""
    all_names = set(load_tools())
    text = (request or "").lower()
    names = {"add_primitive"}
    for tool, words in _HINTS.items():
        if any(w in text for w in words):
            names.add(tool)
    if mode == "edit":
        names.update(_EDIT_TOOLS)
    names.update(n for n in extra if n in all_names)
    pool = sorted(all_names - names)
    random.Random(hashlib.sha256(text.encode()).hexdigest()).shuffle(pool)
    return sorted(names) + pool[:distractors]


def token_estimate(tool_names):
    """Rough prompt cost of the offered tools (chars/4.3, measured 2,811 tokens for all 26)."""
    tools = load_tools()
    return int(sum(len(json.dumps(tools[n])) for n in tool_names) / 4.3)


def _relation_words(obj, others):
    """The word pair for this object's offset from its nearest neighbour: "front_left of Table, small".

    The model plans in relation words and reads them back here, so an edit turn can reuse the
    vocabulary instead of converting metres to words itself. Measured basis (the maintainers' place.py, not part of this repository):
    the sideways word takes the residual from 0.46 m to 0.075 m median. None when there is no
    neighbour, or when the two centres coincide on both horizontal axes.
    """
    loc = obj.get("loc") or obj.get("location") or [0, 0, 0]
    best, best_d = None, None
    for other in others:
        if other is obj or other.get("name") == obj.get("name"):
            continue
        oloc = other.get("loc") or other.get("location") or [0, 0, 0]
        dx, dy = loc[0] - oloc[0], loc[1] - oloc[1]
        d = dx * dx + dy * dy
        if best_d is None or d < best_d:
            best, best_d = other, d
    if best is None:
        return None
    oloc = best.get("loc") or best.get("location") or [0, 0, 0]
    dx, dy = loc[0] - oloc[0], loc[1] - oloc[1]
    side = _place.side_of(dx, dy)
    if side is None:
        return None  # centred on the neighbour: no sideways word to give
    # distance word from the clear horizontal gap between the centres
    gap = max(abs(dx), abs(dy))
    word = _place.bucket(max(0.0, gap))
    return f"{side} of {best.get('name')}, {word}"


def scene_summary(objects, cap=40):
    """Compact scene line for follow-up turns. Each object costs about 27-35 tokens, so it is capped."""
    if not objects:
        return "Scene is empty."
    # a built thing (an empty with its parts under it) is ONE line, its parts are left out: the
    # one-sentence station is 49 objects, more than the cap, and the model is asked about things
    names = {o.get("name") for o in objects}
    count = {}
    for o in objects:
        if o.get("parent") in names:
            count[o["parent"]] = count.get(o["parent"], 0) + 1
    objects = [o for o in objects if o.get("parent") not in count]
    parts = []
    for obj in objects[:cap]:
        loc = [round(v, 2) for v in obj.get("loc", obj.get("location", [0, 0, 0]))]
        kind = f"group, {count[obj['name']]} parts" if obj.get("name") in count else str(obj.get("type", "mesh")).lower()
        part = f'{obj["name"]} ({kind}) at {loc}'
        if obj.get("material"):
            part += f' material {obj["material"]}'
        words = _relation_words(obj, objects[:cap])
        if words:
            part += f", {words}"
        parts.append(part)
    more = len(objects) - cap
    tail = f"; and {more} more" if more > 0 else ""
    return "Scene objects: " + "; ".join(parts) + tail + "."


def followup_text(text, objects, cap=40):
    return text + "\n[" + scene_summary(objects, cap) + "]"


def format_result(ok, error=None):
    return "ok" if ok else "error: " + str(error or "tool execution failed")[-200:]


_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def normalise_calls(message):
    """Calls from a chat message: tagged text first, then structured tool_calls. [{tool, ...args}]"""
    calls = []
    for raw in _TAG.findall(message.get("content") or ""):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        name = data.get("name") or data.get("tool")
        args = data.get("arguments", {})
        if isinstance(name, str) and isinstance(args, dict):
            calls.append({"tool": name, **args})
    if calls:
        return calls
    for item in message.get("tool_calls") or []:
        fn = item.get("function") or {}
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if isinstance(fn.get("name"), str) and isinstance(args, dict):
            calls.append({"tool": fn["name"], **args})
    return calls


def assistant_message(calls, turn, step):
    ids = [f"call_{turn}_{step}_{n}" for n in range(len(calls))]
    msg = {"role": "assistant", "content": "", "tool_calls": [
        {"id": cid, "type": "function", "function": {
            "name": c["tool"], "arguments": json.dumps({k: v for k, v in c.items() if k != "tool"})}}
        for cid, c in zip(ids, calls)]}
    return msg, ids
