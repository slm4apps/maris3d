# SPDX-License-Identifier: Apache-2.0
"""The edit answer in words -> the change apply_change carries out. No language read.

The edit model reads the scene in words (describe_scene) and answers in words only:

    {"kind": "change" | "build" | "question" | "cannot" | "look",
     "say": <one sentence: question / cannot, or what was assumed>,
     "things": [<names>]                       (look only: the things whose parts it needs)
     "changes": [{"do": ..., "object": <exact name>, "parts": [<exact part names>]?, ...}]}

    remove
    recolor   color: a colour word or {name, shade, see_through, look, gradient} (colours.py)
    scale     size: a_bit_bigger | bigger | much_bigger | a_bit_smaller | smaller | much_smaller |
                    double | half | triple
              or times: a ratio word (size_words.RATIO: "two_and_half"; a number only as typed)
              or percent: <the number typed>, way: more | less          (code works out the factor)
              or like: <another thing> (+ times: a ratio word) -- "as tall as the tree", "half as wide as
                 the shed": code makes its size along `along` that thing's, times the ratio
              along: all | width | depth | height | length       (default all)
    move      place {anchor, relation, distance}  (the outline's words)
              or shift {toward: left|right|front|back|up|down, by: <distance word>
                        | amount: <the number typed>, unit: mm | cm | m}   (metres: <typed>, older adapters)
    turn      by: quarter_left | quarter_right | around | a_bit_left | a_bit_right | eighth_left |
                  eighth_right   (or degrees: <typed>), or face: <thing | north | south | east | west>
    tilt      toward: left|right|front|back, by: slight|medium|steep
    add       what: <the noun as said>, on: <existing part or thing>, relation: <part relation>,
              color?: <colour words, only when said>, size?: <size word, only when said>
              -> the PARTS PLANNER designs `what` at its usual size; code fits it on `on`
    copy      count, place?
    rename    to

`to_change` turns one word change into the numeric change apply_change takes (factors, metres,
degrees: lookup tables below), so the code that builds, checks and reads back is the same.
"""
import copy
import re

from . import apply_change as AC
from . import colours as COL
from . import describe_parts as DP
from . import place as PLACE
from . import show as SHOW
from . import size_words as SW

KINDS = ("change", "build", "question", "cannot", "look", "talk")
DOS = AC.DOS + ("tilt",)
SIZES = {"a_bit_bigger": 1.2, "bigger": 1.5, "much_bigger": 2.0, "a_bit_smaller": 0.83, "smaller": 0.67,
         "much_smaller": 0.5, "double": 2.0, "half": 0.5, "triple": 3.0}
ALONG = ("all", "width", "depth", "height", "length")
DIRECTIONS = {"left": ("x", -1), "right": ("x", 1), "front": ("y", -1), "back": ("y", 1),
              "up": ("z", 1), "down": ("z", -1)}
STEPS = dict(PLACE.GAP)                 # a shift by a distance word moves the ladder's midpoint
TURNS = {"quarter_left": 90.0, "quarter_right": -90.0, "around": 180.0, "a_bit_left": 15.0,
         "a_bit_right": -15.0, "eighth_left": 45.0, "eighth_right": -45.0}
ADD_RELATIONS = tuple(DP.RELATIONS)
# do shape: one primitive by the numbers the user typed (apply_change.SHAPES)
SHAPE_ARGS = ("shape", "name", "at", "rotation", "scale") + AC.SHAPE_KEYS
# one size table for the whole product: the outline's and the parts' size words (x, y, z factors)
SIZE_WORD_FACTOR = DP.SIZE_WORDS
UNITS = {"mm": 0.001, "cm": 0.01, "m": 1.0}
WAYS = {"more": 1, "less": -1}


TOOL_NAME = "slm4blender_edit"         # the answer is trained wrapped as one tool call; the shipped weights emit this name (scan: allow)

# The word-format edit adapter's system prompt. The training data imports this constant, so the
# product sends the same bytes the adapter was trained on: never edit it for an adapter in use.
EDIT_SYSTEM = (
    "You edit things already built in a Blender scene, in words only. Input: Scene (a line per thing or group of "
    "copies: Name (noun), where it stands, facing, colour), Focus (the parts of the things being worked on), Last "
    "(thing last built or changed), Request, and Clarified (the user's answers to your question). Reply with one "
    f"tool call {TOOL_NAME}: {{\"kind\":\"change|build|question|cannot|look\",\"say\":<one sentence>,"
    "\"things\":[...],\"changes\":[...]}. A change has do, object (an exact name, a range as the Scene writes it, or "
    "a noun for all of them) and, for some parts only, parts (exact part names from Focus). do: remove; "
    "recolor (color: a colour word, or {name,shade,see_through,look,gradient:{to,direction}}; hex or rgb only when "
    "typed); scale (size: a_bit_bigger|bigger|much_bigger|a_bit_smaller|smaller|much_smaller|double|half|triple, "
    "or times when a number is said; along: all|width|depth|height|length); move (place {anchor,relation,distance} "
    "or shift {toward: left|right|front|back|up|down, by: a distance word, or metres when said}); turn (by: "
    "quarter_left|quarter_right|around|a_bit_left|a_bit_right|eighth_left|eighth_right, or degrees when said, or "
    "face: thing or compass word); tilt (toward: left|right|front|back, by: slight|medium|steep); add (what: the "
    "new part as said, on: an existing part, relation, color and size only when said); copy (count, place); rename "
    "(to). A new thing to make: kind build. Parts you need but Focus lacks: kind look, things: the names. Unclear: "
    "kind question, say gives the choices; with two Clarified lines always answer, say what you assumed. Something "
    "no change can do: kind cannot, say offers the nearest thing you can do. Relations: front_of, behind, left_of, "
    "right_of, next_to, on_top_of, under, against, between, around. Distances: touching, tiny, small, medium, "
    "large, far, distant."
)


# The talk-capable prompt: EDIT_SYSTEM unchanged, plus the show lines. A separate
# constant so the prompt of the adapter in use stays byte for byte; the loop switches to this one
# when the adapter that learned the lines ships.
SHOW_SYSTEM = (
    " Any answer may carry show: a list of lines that talk in the scene, in words only: "
    "{\"line\":\"say\",\"text\":<words>,\"effect\"?:" + "|".join(SHOW.EFFECTS) + "}; "
    "{\"line\":\"show maris\",\"pose\":" + "|".join(SHOW.POSES) + "}; "
    "{\"line\":\"ask\",\"question\":<words>,\"about\"?:<a thing>,\"choices\"?:[up to 3 short words]}; "
    "{\"line\":\"clear messages\"}. A request that is only talk (who you are, hello, thanks, a request "
    "outside 3D scenes, clear the messages): kind talk, no changes. Never add say to a plain build or edit."
)
EDIT_SYSTEM_SHOW = EDIT_SYSTEM + SHOW_SYSTEM

# The exact-numbers prompt (words2): EDIT_SYSTEM unchanged, plus the forms that copy numbers the user
# typed. A separate constant for the same reason as SHOW_SYSTEM; the loop switches to it when the
# adapter trained on it ships.
EXACT_SYSTEM = (
    " Numbers the user typed are copied as typed, never turned into words: a new single shape: do shape "
    "{shape: " + "|".join(AC.SHAPES) + ", name, at:[x,y,z], rotation?:[x,y,z] degrees, radius?, depth?, size?, "
    "major_radius?, minor_radius?, scale?:[x,y,z]}, kind change, no object; move to:[x,y,z]; turn to_degrees: "
    "degrees or [x,y,z]; scale to: a number or [x,y,z]. Only the keys the user gave."
)

# The final edit prompt (one adapter, every edit, talk and typed numbers). Numbers the user typed are
# copied with their unit, never worked out; amounts said in words are words; code does the arithmetic.
EDIT_SYSTEM_EXACT = (
    EDIT_SYSTEM
    .replace("scale (size: a_bit_bigger|bigger|much_bigger|a_bit_smaller|smaller|much_smaller|double|half|triple, "
             "or times when a number is said; along: all|width|depth|height|length)",
             "scale (size: a_bit_bigger|bigger|much_bigger|a_bit_smaller|smaller|much_smaller|double|half|triple, "
             "or times: a ratio word (" + "|".join(SW.RATIO) + "), or percent: the number typed with way: "
             "more|less, or like: another thing (as tall as it; with times for half as tall as it); along: "
             "all|width|depth|height|length)")
    .replace("by: a distance word, or metres when said}",
             "by: a distance word, or amount: the number typed with unit: mm|cm|m}")
    + SHOW_SYSTEM + EXACT_SYSTEM
)
assert EDIT_SYSTEM_EXACT.count("percent: the number typed") == 1 and "unit: mm|cm|m" in EDIT_SYSTEM_EXACT


def wrap(answer):
    """The answer as the tool call the adapter is trained to write."""
    import json
    return "<tool_call>\n" + json.dumps({"name": TOOL_NAME, "arguments": answer}, separators=(",", ":")) + \
        "\n</tool_call>"


def unwrap(text):
    """The answer object from the model's text: a <tool_call> wrapper or plain JSON. None when neither."""
    import json
    m = re.search(r"<tool_call>\s*(\{.*\})\s*</tool_call>", text or "", re.DOTALL)
    try:
        obj = json.loads(m.group(1) if m else (text or "").strip())
    except ValueError:
        return None
    if isinstance(obj, dict) and obj.get("name") == TOOL_NAME and isinstance(obj.get("arguments"), dict):
        return obj["arguments"]
    return obj if isinstance(obj, dict) else None


class WordError(AC.ChangeError):
    pass


def _num(v, lo, hi):
    return AC._num(v) and lo <= v <= hi


def _axes(along, spec, parts=None):
    if along in (None, "all"):
        return "xyz"
    if along == "length":       # the longer way across the floor; a named part that stands up: its height
        s = spec["size"]
        if parts:
            p = next((q for q in spec["parts"] if q["name"] == parts[0]), None)
            if p is not None:
                s = p["size"]
                if s[2] >= max(s[0], s[1]):
                    return "z"
        return "x" if s[0] >= s[1] else "y"
    return {"width": "x", "depth": "y", "height": "z"}[along]


def to_change(ch, specs, design=None):
    """One change in words -> the change apply_change takes. WordError on a word off the lists."""
    if not isinstance(ch, dict):
        raise WordError("a change is an object")
    do = ch.get("do")
    out = {k: v for k, v in ch.items() if k in ("do", "object", "parts")}
    spec = specs.get(ch.get("object"))
    if do == "shape":                   # the numbers the user typed, copied: no word to look up
        return {k: v for k, v in ch.items() if k in ("do",) + SHAPE_ARGS}
    if do == "scale" and "to" in ch:
        out["to"] = ch["to"]
    elif do == "scale":
        along = ch.get("along", "all")
        if along not in ALONG:
            raise WordError(f"along {along!r}; one of " + ", ".join(ALONG))
        if "like" in ch:
            other = specs.get(ch["like"])
            if other is None:
                raise WordError(f"like {ch['like']!r}: no such thing in the scene")
            if spec is None:
                raise WordError(f"unknown thing {ch.get('object')!r}")
            k = SW.RATIO.get(ch.get("times", "same"))
            if k is None:
                raise WordError("with like, times is a ratio word (" + ", ".join(SW.RATIO) + ")")
            axes = _axes(along, spec, ch.get("parts"))
            own, theirs = spec["size"], other["size"]
            if len(axes) == 3:              # as big as: the longest sides match
                f = k * max(theirs) / max(max(own), 1e-6)
            else:
                i = "xyz".index(axes)
                f = k * theirs[i] / max(own[i], 1e-6)
            out["by"] = {a: round(f, 4) for a in axes}
            return out
        if "times" in ch:
            t = ch["times"]
            if isinstance(t, str) and t in SW.RATIO:
                f = SW.RATIO[t]
            elif _num(t, 0.01, 100):           # a factor exactly as the user typed it
                f = float(t)
            else:
                raise WordError("times is a ratio word (" + ", ".join(SW.RATIO) + ") or the number typed")
        elif "percent" in ch:
            if not _num(ch["percent"], 0, 1000) or ch.get("way") not in WAYS:
                raise WordError("percent is the number typed, with way: more or less")
            f = 1 + WAYS[ch["way"]] * float(ch["percent"]) / 100
            if f <= 0.01:
                raise WordError(f"{ch['percent']} percent less leaves nothing")
        elif ch.get("size") in SIZES:
            f = SIZES[ch["size"]]
        else:
            raise WordError(f"size {ch.get('size')!r}; one of " + ", ".join(SIZES))
        if spec is None:
            raise WordError(f"unknown thing {ch.get('object')!r}")
        out["by"] = {a: f for a in _axes(along, spec, ch.get("parts"))}
    elif do == "move":
        if "to" in ch:
            out["to"] = ch["to"]
        elif "place" in ch:
            out["place"] = ch["place"]
        else:
            sh = ch.get("shift")
            if not isinstance(sh, dict) or sh.get("toward") not in DIRECTIONS:
                raise WordError("move needs place, or shift {toward, by | amount and unit}")
            axis, sign = DIRECTIONS[sh["toward"]]
            if "amount" in sh:
                if not _num(sh["amount"], 0, 100000) or sh.get("unit") not in UNITS:
                    raise WordError("amount is the number typed, with unit: " + ", ".join(UNITS))
                d = float(sh["amount"]) * UNITS[sh["unit"]]
            elif "metres" in sh:
                if not _num(sh["metres"], 0, 1000):
                    raise WordError("metres is the number the user said")
                d = float(sh["metres"])
            elif sh.get("by") in STEPS:
                d = STEPS[sh["by"]]
            else:
                raise WordError(f"shift by {sh.get('by')!r}; one of " + ", ".join(STEPS))
            out["shift"] = {axis: sign * d}
    elif do == "turn":
        if "face" in ch:
            out["face"] = ch["face"]
        elif "to_degrees" in ch:
            out["to_degrees"] = ch["to_degrees"]
        elif "degrees" in ch:
            if not _num(ch["degrees"], -360, 360):
                raise WordError("degrees is the number the user said")
            out["by"] = float(ch["degrees"])
        elif ch.get("by") in TURNS:
            out["by"] = TURNS[ch["by"]]
        else:
            raise WordError(f"turn by {ch.get('by')!r}; one of " + ", ".join(TURNS))
    elif do == "recolor":
        out["color"] = ch.get("color")
        bad = COL.faults(out["color"])
        if bad:
            raise WordError("; ".join(bad))
        if "finish" in ch:
            out["finish"] = ch["finish"]
    elif do == "tilt":
        out.update(toward=ch.get("toward"), by=ch.get("by"))
    elif do == "add":
        out["parts"] = add_parts(ch, spec, design)
    elif do in ("remove", "copy", "rename"):
        out.update({k: v for k, v in ch.items() if k in ("count", "place", "to")})
    else:
        raise WordError(f"unknown do {do!r}; the changes are: " + ", ".join(DOS))
    return out


def _camel(noun):
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[\s_]+", str(noun)) if w)


def add_parts(ch, spec, design):
    """The parts of an `add`: the parts planner's design of `what` (its usual size), renamed into
    the thing, its first part placed `on` the named part, the colour and size words applied."""
    if spec is None:
        raise WordError(f"unknown thing {ch.get('object')!r}")
    what, on, rel = ch.get("what"), ch.get("on"), ch.get("relation", "on_top_of")
    if not isinstance(what, str) or not what.strip():
        raise WordError("add needs what: the thing to add, as the user said it")
    names = {p["name"] for p in spec["parts"]}
    if on not in names:
        raise WordError(f"add on {on!r}: not a part of {spec['id']}; its parts are: " + ", ".join(sorted(names)))
    if rel not in ADD_RELATIONS:
        raise WordError(f"add relation {rel!r}; one of " + ", ".join(ADD_RELATIONS))
    if ch.get("size") is not None and ch["size"] not in SIZE_WORD_FACTOR:
        raise WordError(f"add size {ch['size']!r}; one of " + ", ".join(SIZE_WORD_FACTOR))
    if ch.get("color") is not None and COL.faults(ch["color"]):
        raise WordError("; ".join(COL.faults(ch["color"])))
    if design is None:
        raise WordError("add needs the parts planner to design the new part (no planner here)")
    answer = design(what)
    faults, built = DP.check_answer(answer) if isinstance(answer, dict) else (["no design"], None)
    if not built:
        raise WordError(f"the parts planner's design of {what!r} does not build: " + "; ".join(faults)[:200])
    if SW.uses_words(answer):           # sizes in words: take the metres the check worked out
        answer = SW.to_metres(answer)[0]
    parts = [{k: copy.deepcopy(v) for k, v in p.items() if k in AC.PART_KEYS} for p in answer["parts"]]
    prefix = _camel(what)
    rename = {}
    for p in parts:
        n = p["name"] if p["name"].startswith(prefix) else prefix + p["name"]
        k = 2
        base = n
        while n in names or n in rename.values():
            n = f"{base}{k}"
            k += 1
        rename[p["name"]] = n
    f = SIZE_WORD_FACTOR.get(ch.get("size"), (1.0, 1.0, 1.0))
    for i, p in enumerate(parts):
        p["name"] = rename[p["name"]]
        p["size"] = [round(v * k, 4) for v, k in zip(p["size"], f)]
        if i == 0:
            p["place"] = {"on": on, "relation": rel, "align": {}}
        elif (p.get("place") or {}).get("on") in rename:
            p["place"]["on"] = rename[p["place"]["on"]]
        if isinstance(ch.get("color"), str) and ch["color"] in DP.PARTS_COLORS:
            p["color"] = ch["color"]
    return parts


def to_changes(ch, specs, design=None):
    """to_change, plus a recolour of the new parts when an add says a colour beyond the 26 trained ones."""
    out = to_change(ch, specs, design)
    color = ch.get("color") if isinstance(ch, dict) and ch.get("do") == "add" else None
    if color is not None and not (isinstance(color, str) and color in DP.PARTS_COLORS):
        return [out, {"do": "recolor", "object": out["object"], "parts": [p["name"] for p in out["parts"]],
                      "color": color}]
    return [out]


def apply_words(answer, specs, scene=None, design=None):
    """A word answer -> apply_change.Applied. A `look` answer returns its things in `.look`.
    Any answer's `show` lines (say / show maris / ask / clear messages) come back checked as
    `.show` (show.apply_lines actions); a line off the lists is an error, never a repair.
    kind talk changes nothing in the scene."""
    if isinstance(answer, dict) and answer.get("kind") == "talk":
        out = AC.Applied()
        out.kind = "talk"
        out.specs = copy.deepcopy(specs)
        out.show, faults = SHOW.apply_lines(answer.get("show"), list(specs))
        out.errors = [{"change": None, "error": f} for f in faults]
        if not out.show and not faults:
            out.errors.append({"change": None, "error": "kind talk without show lines"})
        return out
    out = _apply_core(answer, specs, scene, design)
    out.show, faults = SHOW.apply_lines(answer.get("show") if isinstance(answer, dict) else None, list(specs))
    out.errors = out.errors + [{"change": None, "error": f} for f in faults]
    if out.kind == "question" and not out.say:        # a question carried by its `ask` line alone
        ask = next((a for a in out.show if a["op"] == "ask"), None)
        if ask:
            out.say = ask["question"]
            out.errors = [e for e in out.errors if "without say" not in e["error"]]
    return out


def _apply_core(answer, specs, scene=None, design=None):
    """A word answer -> apply_change.Applied (the scene part; `show` lines are read by apply_words)."""
    if isinstance(answer, dict) and answer.get("kind") == "look":
        out = AC.Applied()
        out.kind = "look"
        things = answer.get("things")
        out.look = [t for t in things if t in specs] if isinstance(things, list) else []
        if not out.look:
            out.errors.append({"change": None, "error": "look names no thing of the scene"})
        return out
    if not isinstance(answer, dict) or answer.get("kind") != "change":
        return AC.apply_answer(answer, specs, scene)
    from . import describe_scene as DS
    changes, errors = [], []
    for i, ch in enumerate(answer.get("changes") or []):
        try:
            if isinstance(ch, dict) and ch.get("do") == "shape":       # a new thing: no object yet
                changes.append(to_change(ch, specs, design))
                continue
            names = DS.expand(ch.get("object"), specs) if isinstance(ch, dict) else []
            if isinstance(ch, dict) and len(names) > 1:          # a group: one change per thing
                if ch.get("parts") is not None or ch.get("do") in ("add", "rename"):
                    raise WordError(f"{ch.get('do')} on a group names one thing at a time")
                for n in names:
                    changes.extend(to_changes(dict(ch, object=n), specs, design))
                continue
            if isinstance(ch, dict) and len(names) == 1 and names[0] != ch.get("object"):
                ch = dict(ch, object=names[0])
            changes.extend(to_changes(ch, specs, design))
        except AC.ChangeError as error:
            errors.append({"change": i, "do": ch.get("do") if isinstance(ch, dict) else None,
                           "object": ch.get("object") if isinstance(ch, dict) else None, "error": str(error)})
    out = AC.apply_answer(dict(answer, changes=changes), specs, scene) if changes else AC.Applied()
    if not changes:
        out.kind = "change"
        out.specs = copy.deepcopy(specs)
    out.errors = errors + out.errors
    return out
