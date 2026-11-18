# SPDX-License-Identifier: Apache-2.0
"""The plan reply: ONE JSON object listing the things to build, never coordinates.

    {"kind": "build", "items": [{"id": "bench_1", "thing": "bench", "count": 2, "place": {...}}]}

The outline planner (vocabulary.OUTLINE_SYSTEM) answers *which things, how many, what material,
where in words*; layout is the compiler's job (compile_plan). The add-on ships this module because
extras/ is optional and not vendored into the extension.
"""
import json
import re

MAX_COUNT = 40  # the copilot scene cap; a plan asking for more is almost certainly wrong
COORD_KEYS = ("x", "y", "z", "location", "position", "loc", "rotation", "rotation_deg",
              "scale", "size", "dims", "dimensions")


def from_outline(payload):
    """The outline answer (vocabulary.OUTLINE_SYSTEM: items name a `thing` as the user said it) -> the
    items the compiler reads: the thing is the recipe word (the library's, or the parts planner designs
    it). A question / cannot answer comes back unchanged (check_items refuses it with its sentence)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return payload
    items = [dict(i, recipe=i["thing"]) if isinstance(i, dict) and not i.get("recipe")
             and isinstance(i.get("thing"), str) else i for i in payload["items"]]
    return dict(payload, items=items)


def check_items(payload):
    """(ok, reason) for a v3 answer. Structure only: which recipes exist is the compiler's question,
    and a coordinate anywhere in an item is refused, as in v1."""
    if isinstance(payload, dict) and payload.get("kind") in ("question", "cannot"):
        return False, str(payload.get("say") or payload["kind"])
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
            if key == "size" and key in item and isinstance(item[key], str) and key not in (place or {}):
                continue        # a size word ("small"): the outline format has it, the builder scales by it
            if key in item or key in (place or {}):
                return False, f"the plan must not carry {key}"
    return True, None


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
