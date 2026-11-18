# SPDX-License-Identifier: Apache-2.0
"""The planner reply: ONE JSON object naming a recipe and its slots, never coordinates.

    {"recipe": "chair", "count": 4, "material": "oak", "zone": "dining"}

This is the contract the Copilot's Plan mode asks for and validates before showing the
plan. It is deliberately separate from extras/planner (part/order/relations plans): the
planner here answers *which recipe, how many, what material, where in words*; layout is
the compiler's job. The add-on ships this list because extras/ is optional and not
vendored into the extension.
"""
import json
import re

# Recipe names the planner may return: the harness group recipes plus the common
# single-object recipes. Keep them lowercase and under 24 chars (NAME_RE).
RECIPES = (
    "armchair", "bench", "bin", "bookshelf", "box", "bus", "cabin", "car", "cat",
    "chair", "coffee_table", "cottage", "desk", "door", "floor", "floor_lamp", "gift",
    "house", "kitchen_run", "lamp", "mug", "pine", "plant", "rug", "sledge", "snowman",
    "sofa", "stove", "table", "tree", "van", "wall", "window", "wreath",
)
RECIPE_SET = frozenset(RECIPES)

NAME_RE = r"^[a-z][a-z0-9_]{0,23}$"
MAX_COUNT = 40  # the copilot scene cap; a plan asking for more is almost certainly wrong
MAX_WIDTH = 50.0
MAX_WORD = 40
REQUIRED_KEYS = ("recipe",)
SLOT_KEYS = ("count", "material", "zone", "width", "animate", "target", "seconds", "finish")

# The plan says what a thing should BE, the harness makes it so. Measured (smooth_probe.py,
# measured): told explicitly, the model does emit join + shade_smooth in both adapters, but it never
# emits the bevel that actually rounds an edge, and a vaguer sentence gets only a join. So the
# plan names the finish and the harness performs it -- the copilot's own tools stay the fallback.
FINISHES = ("smooth", "bevel", "join", "none")

# The plan never places and never animates; it NAMES a motion the harness knows how to perform.
# Measured: asked straight for the keyframes, neither adapter produces a
# usable animation -- build gives one keyframe plus a frame end, edit gives many with the wrong
# axis (a car "moving forward" got value [0, 0, 1.2], i.e. upwards), and both drop the object
# name. Naming the motion in words is the part the model can do; the numbers are the harness's.
ANIMATIONS = ("door_open", "door_close", "drive_forward", "drive_backward", "drive_apart",
              "spin", "bob", "none")
COORD_KEYS = ("x", "y", "z", "location", "position", "loc", "rotation", "rotation_deg",
              "scale", "size", "dims", "dimensions")

PROMPT = (
    "You are the planner. Do not call tools and do not give coordinates.\n"
    "Answer with exactly one JSON object, no prose and no code fence.\n"
    'Required: "recipe", one of: %s.\n'
    'Optional: "count" (whole number 1-%d), "material" (one word), "zone" (one word), '
    '"width" (metres, positive).\n'
    "No other fields. Never send x, y, z, location, rotation or scale.\n"
    'Example: {"recipe": "chair", "count": 4, "material": "oak", "zone": "dining"}\n'
    "Request: " % (", ".join(RECIPES), MAX_COUNT)
)

# --- the planner adapter (v0.1 ships it as a third file beside the base and the edit adapter) ---
# The adapter was trained on ONE system prompt, byte for byte, with the request as the user turn
# (420 held-out sentences: 410 strict, 97.6 percent). The base model alone parses 0 of 75 plans,
# so Plan mode without the adapter is the instruction above and little else. When a server has
# the planner loaded, Plan mode sends exactly these messages -- any other wording is a prompt the
# adapter never saw. Its vocabulary is its own (43 recipes, the take's pieces among them); the
# 34 names above stay the contract for a server without the adapter.
PLANNER_RECIPES = (
    "armchair", "art", "bench", "bin", "boy", "bus", "cabin", "car", "cat", "chair",
    "floor_lamp", "gift", "hero_door", "hero_glazing", "hero_roof", "hero_walls", "house",
    "kitchen_run", "lamp", "lamp_post", "man", "plant", "room_shell", "rug", "shelf", "sledge",
    "snow_truck", "snowman", "sofa", "squirrel", "station_building", "stove", "street_base",
    "suitcase", "table", "tea", "townhouse", "train", "tree", "tv", "van", "woman", "wreath",
)
PLANNER_SYSTEM = (
    "You are the planner for a Blender scene builder. Reply with one JSON object only: {\""
    "recipe\": <name>, \"count\": <int>, \"material\": <name>, \"zone\": <name>}. Recipes: armch"
    "air, art, bench, bin, boy, bus, cabin, car, cat, chair, floor_lamp, gift, hero_door,"
    " hero_glazing, hero_roof, hero_walls, house, kitchen_run, lamp, lamp_post, man, plan"
    "t, room_shell, rug, shelf, sledge, snow_truck, snowman, sofa, squirrel, station_buil"
    "ding, stove, street_base, suitcase, table, tea, townhouse, train, tree, tv, van, wom"
    "an, wreath. Materials: asphalt, black, brass, brick, cream, glass, green, metal, nav"
    "y, oak, pavement, pine, red, rust, snow, teal, terra, timber, walnut, white. Zones: "
    "bedroom, courtyard, dining, garden, hallway, kitchen, living, platform, plaza, stree"
    "t_east, street_west. count defaults to 1; omit material when the sentence does not n"
    "ame one; never output coordinates, sizes or part names."
)


# --- planner v3: reads the placement the sentence states and lists several items ------
# The planner adapter was trained byte for byte on this system prompt.
# Its answer is {"items": [{"id", "recipe", "count", "material", "zone", "place": {"anchor",
# "relation", "distance", "arrangement"}}]}: what copilot/compile_plan.py turns into a build.
PLANNER_V3_SYSTEM = (
    "You are the planner for a Blender scene builder. Reply with one JSON object only: {\""
    "items\":[{\"id\":<name>,\"recipe\":<name>,\"count\":<int>,\"material\":<name>,\"zone\":<name>,\""
    "place\":{\"anchor\":<id>,\"relation\":<word>,\"distance\":<word>,\"arrangement\":{\"kind\":<wor"
    "d>}}}]}. Relations: front_of, behind, left_of, right_of, next_to, between, on_top_of"
    ", under, against, around, centre_of. Distances: touching, tiny, small, medium, large"
    ", far, distant. Arrangements: row, ring, grid, stack. Recipes: armchair, art, bench,"
    " bin, boy, bus, cabin, car, cat, chair, counter, floor_lamp, gift, house, kitchen_ru"
    "n, lamp, lamp_post, man, plant, platform, rug_group, shelf, sledge, snow_truck, snow"
    "man, sofa, squirrel, station_building, stove, suitcase, table, townhouse, track, tra"
    "in, tree, tv, van, waiting_lamp, woman, wreath. Materials: black, brass, brick, crea"
    "m, green, metal, navy, oak, pine, red, rust, snow, teal, terra, timber, walnut, whit"
    "e. Zones: bedroom, courtyard, dining, garden, hallway, kitchen, living, platform, pl"
    "aza, street_east, street_west. One item per thing asked for, in the order asked. Giv"
    "e a field only when the sentence states it: no material, zone, place or distance the"
    " sentence does not say. The anchor is the id of the thing the sentence places it by."
    " Never output coordinates, sizes or part names."
)


def planner_v3_messages(request):
    return [{"role": "system", "content": PLANNER_V3_SYSTEM},
            {"role": "user", "content": str(request)}]


def check_items(payload):
    """(ok, reason) for a v3 answer. Structure only: which recipes exist is the compiler's question,
    and a coordinate anywhere in an item is refused, as in v1."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not payload["items"]:
        return False, "the plan has no items"
    if len(payload["items"]) > MAX_COUNT:
        return False, "too many items"
    for item in payload["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("recipe"), str) or not item["recipe"]:
            return False, "an item has no recipe"
        place = item.get("place")
        if place is not None and not isinstance(place, dict):
            return False, "an item's place is not an object"
        for key in COORD_KEYS:
            if key in item or key in (place or {}):
                return False, f"the plan must not carry {key}"
    return True, None


def planner_messages(request):
    """The two messages the planner adapter was trained on: its system prompt, then the request."""
    return [{"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": str(request)}]


def plan_text(request):
    """The one user message Plan mode sends: the planner instruction plus the request."""
    return PROMPT + str(request)


def parse_reply(text):
    """(object, None) or (None, plain reason). Accepts a bare object, a ```json fence,
    or the <tool_call> wrapper the base model tends to keep using."""
    raw = (text or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    tag = re.fullmatch(r"<tool_call>\s*(.*?)\s*</tool_call>", raw, re.DOTALL)
    if tag:
        raw = tag.group(1).strip()
    try:
        return json.loads(raw), None
    except ValueError as exc:
        return None, f"malformed JSON ({exc})"


def check(payload, recipes=None):
    """(True, None) or (False, plain reason). payload is reply text or a parsed object.
    `recipes` is the vocabulary to accept (default: RECIPES; the planner adapter has its own)."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            return False, f"malformed JSON (not UTF-8: {exc.reason})"
    if isinstance(payload, str):
        payload, reason = parse_reply(payload)
        if reason:
            return False, reason
    if not isinstance(payload, dict):
        return False, "plan must be a JSON object"

    bad = sorted(k for k in payload if k in COORD_KEYS)
    if bad:
        return False, "plan must not place objects: remove " + ", ".join(bad)
    unknown = sorted(set(payload) - set(REQUIRED_KEYS) - set(SLOT_KEYS))
    if unknown:
        return False, "unknown field(s): " + ", ".join(unknown)
    if "recipe" not in payload:
        return False, "missing field(s): recipe"

    recipe = payload["recipe"]
    if not isinstance(recipe, str) or not re.match(NAME_RE, recipe):
        return False, "recipe must be a lowercase name (letters, digits, underscore)"
    known = tuple(recipes) if recipes else RECIPES
    if recipe not in (frozenset(known) if recipes else RECIPE_SET):
        return False, f"unknown recipe {recipe!r} (known: {', '.join(known)})"

    if "count" in payload:
        count = payload["count"]
        if isinstance(count, bool) or not isinstance(count, int):
            return False, f"count must be an integer from 1 to {MAX_COUNT}"
        if not 1 <= count <= MAX_COUNT:
            return False, f"count must be an integer from 1 to {MAX_COUNT}"
    if "animate" in payload:
        motion = payload["animate"]
        if not isinstance(motion, str) or motion not in ANIMATIONS:
            return False, ("animate must be one of: " + ", ".join(ANIMATIONS))
        if motion != "none" and "target" not in payload:
            return False, "an animation needs a target (the object it moves)"
    if "target" in payload:
        target = payload["target"]
        if not isinstance(target, str) or not re.match(r"^[A-Za-z][A-Za-z0-9_.]{0,39}$", target):
            return False, "target must be the name of one object"
        if "animate" not in payload and "finish" not in payload:
            return False, "target is only meaningful with animate or finish"
    if "seconds" in payload:
        seconds = payload["seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) \
                or not 0 < seconds <= 10:
            return False, "seconds must be a number greater than 0 and at most 10"
    if "finish" in payload:
        finish = payload["finish"]
        if not isinstance(finish, str) or finish not in FINISHES:
            return False, ("finish must be one of: " + ", ".join(FINISHES))
        if finish != "none" and "target" not in payload and "recipe" not in payload:
            return False, "a finish needs a target"
    for key in ("material", "zone"):
        if key in payload:
            value = payload[key]
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_WORD:
                return False, f"{key} must be one word of 1 to {MAX_WORD} characters"
    if "width" in payload:
        width = payload["width"]
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not 0 < width <= MAX_WIDTH:
            return False, f"width must be a number greater than 0 and at most {MAX_WIDTH:g}"
    return True, None


def describe(plan):
    """One display line for a validated plan, e.g. 'chair x4, material oak, zone dining'.
    An items plan (planner v3) is shown as its items joined by '; '."""
    if isinstance(plan.get("items"), list):
        return "; ".join(describe(dict(item, recipe=item.get("recipe") or item.get("id") or "?"))
                         for item in plan["items"] if isinstance(item, dict)) or "(empty plan)"
    text = str(plan.get("recipe", "?"))
    if "count" in plan:
        text += f" x{plan['count']}"
    if "width" in plan:
        text += f" ({plan['width']:g} m wide)"
    for key in ("material", "zone"):
        if key in plan:
            text += f", {key} {plan[key]}"
    return text
