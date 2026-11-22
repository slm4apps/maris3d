# SPDX-License-Identifier: Apache-2.0
"""The scene show, bpy-free: what Maris does for each harness event, how the shipped
effects move over time, and how message objects are named. The add-on (addon/show.py) applies
it in Blender; tests run it without Blender.

The model only chooses
words, a pose and an effect from the shipped lists; everything that moves is here, driven by
events the harness already has. Nothing in here is a model skill: it is presentation.
"""
import math
import random

COLLECTION = "Messages"         # every show object lives here, nothing else
PREFIX = "msg_"                 # every message object name starts with this
TAG = "copt_show"               # custom property on every show object: never scene content

EFFECTS = ("type", "rise", "weave", "pop", "sparkle", "float", "dissolve", "fade")
# default effect per message kind (design 3b table)
DEFAULT_EFFECT = {"say": "type", "question": "type", "intro": "rise", "about": "rise",
                  "done": "weave", "small_talk": "pop", "praise": "sparkle", "remove": "dissolve", "choice": "pop"}
# seconds a line stays before it dissolves by itself (questions and choices stay until answered)
LINE_LIFE = {"intro": 8.0, "say": 12.0, "about": 10.0, "small_talk": 8.0, "praise": 6.0, "done": 10.0}
DURATION = {"type": 0.045, "rise": 0.9, "weave": 1.2, "pop": 0.45, "sparkle": 0.7, "float": 0.0,
            "dissolve": 0.7, "fade": 0.4}   # type: seconds per character

# event -> (pose, face). Kept small on purpose.
REACTIONS = {
    "intro": ("rise", "happy"),
    "hello": ("wave", "happy"),
    "idle": ("idle", "happy"),
    "listening": ("idle", "happy"),
    "thinking": ("weave", "happy"),
    "built_exact": ("inspect", "happy"),
    "corrected": ("inspect", "grumpy"),
    "made_by_copilot": ("inspect", "surprised"),
    "still_wrong": ("sad", "sad"),
    "asking": ("point", "happy"),
    "cannot": ("shrug", "surprised"),
    "error": ("sit", "sad"),
    "done": ("dance", "woo"),
    "working": ("hop", "happy"),
}
FUN_FINISHES = ("thumbs_up", "dance", "hop", "sit")
INSPECT_GAP = 1.5               # at most one inspection per this many seconds
INSPECT_EVENTS = ("built_exact", "corrected", "made_by_copilot")
RATED = INSPECT_EVENTS + ("working",)   # each kind has its own clock: a hop never eats an inspection
ALWAYS = ("intro", "hello", "error", "done", "asking", "cannot", "still_wrong")


def msg_name(kind, n):
    """msg_<kind>_<n>, the only names the show gives its objects."""
    return f"{PREFIX}{kind}_{n:03d}"


def is_show_name(name):
    return name.startswith(PREFIX) or name.startswith(("Maris_", "Norn_"))   # Norn_: scenes saved with a 0.2 preview


def _ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _clamp(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def effect_frame(effect, t, n_chars=0, motion=True):
    """The look of a message t seconds after its effect started.

    Returns dict(scale, lift, chars, glow, done): scale (uniform), lift (metres up from the
    resting spot, as a fraction of the text height), chars (how many characters are shown),
    glow (0..1, emission strength factor), done (the effect is over; float never ends).
    motion=False (the Effects switch off, or reduced motion) gives the plain 'fade' look."""
    if not motion and effect not in ("dissolve",):
        effect = "fade"
    out = {"scale": 1.0, "lift": 0.0, "chars": n_chars, "glow": 0.0, "done": False}
    if effect == "type":
        per = DURATION["type"]
        out["chars"] = min(n_chars, int(t / per) + 1) if t >= 0 else 0
        out["glow"] = 0.6 if out["chars"] < n_chars else 0.0
        out["done"] = out["chars"] >= n_chars
    elif effect == "rise":
        x = _clamp(t / DURATION["rise"])
        out["lift"] = -(1 - x) ** 2
        out["scale"] = 0.6 + 0.4 * x
        out["done"] = x >= 1
    elif effect == "weave":
        x = _clamp(t / DURATION["weave"])
        out["chars"] = int(round(n_chars * _clamp(x / 0.7)))
        out["glow"] = 1.0 - x
        out["done"] = x >= 1
    elif effect == "pop":
        x = _clamp(t / DURATION["pop"])
        out["scale"] = max(0.0, _ease_out_back(x))
        out["done"] = x >= 1
    elif effect == "sparkle":
        x = _clamp(t / DURATION["sparkle"])
        out["scale"] = 0.8 + 0.2 * x
        out["glow"] = math.sin(math.pi * x)
        out["done"] = x >= 1
    elif effect == "float":
        out["lift"] = 0.06 * math.sin(2 * math.pi * t / 2.4)
    elif effect == "dissolve":
        x = _clamp(t / DURATION["dissolve"])
        out["scale"] = 1 - x
        out["lift"] = -0.5 * x
        out["glow"] = x * (1 - x) * 4
        out["done"] = x >= 1
    elif effect == "fade":
        x = _clamp(t / DURATION["fade"])
        out["scale"] = 1.0 if x > 0 else 0.0
        out["done"] = x >= 1
    else:
        raise ValueError(f"unknown effect {effect!r}; shipped: {', '.join(EFFECTS)}")
    return out


class Director:
    """Turns harness events into maris cues, with the rate limit and the switches.

    cue(event, now) returns None (nothing to show) or dict(pose, face, target, finish)."""

    def __init__(self, maris=True, fun_finish=True, seed=0):
        self.maris = maris
        self.fun_finish = fun_finish
        self._last = {}
        self._rng = random.Random(seed)

    def cue(self, event, now, target=None):
        if not self.maris or event not in REACTIONS:
            return None
        if event in RATED:
            kind = "work" if event == "working" else "inspect"
            if now - self._last.get(kind, -1e9) < INSPECT_GAP:
                return None                      # big scenes: a sample, never slows the build
            self._last[kind] = now
        pose, face = REACTIONS[event]
        finish = None
        if event == "done":
            if not self.fun_finish:
                pose, face = "thumbs_up", "happy"
            else:
                finish = self._rng.choice(FUN_FINISHES)
                pose = finish
        return {"pose": pose, "face": face, "target": target, "finish": finish}


# ---- harness events -> show actions. The copilot (loop.py) tells its listeners
# fn(name, info); react() says what the show does. Pure: no Blender, no clock.

HARNESS_EVENTS = ("request", "tool_call", "part", "done", "error")
PART_REACTION = {"exact": "built_exact", "moved": "corrected", "missing": "made_by_copilot"}
SAY_MAX = 80


def react(name, info=None):
    """dict(event, target, say, kind, toy) for one harness event, or None (nothing to show).

    event is a REACTIONS key (pose and face come from there via Director.cue); say is a line of
    3D text for Maris to say (kind picks its default effect); toy: she starts weaving."""
    info = info or {}
    out = {"event": None, "target": None, "say": None, "kind": "say"}
    if name == "request":                     # sent, nothing back yet: she weaves
        out["event"] = "thinking"
    elif name == "tool_call":                 # a call went to Blender: she explores toward its part
        out["event"], out["target"] = "working", info.get("name")
    elif name == "part":                      # a part was built and checked
        out["target"] = info.get("name")
        out["event"] = "still_wrong" if info.get("unfixed") else PART_REACTION.get(info.get("verdict"))
    elif name == "error":                     # the panel shows the text; she only sits down
        out["event"] = "error"
    elif name == "done":
        out["event"] = {"question": "asking", "cannot": "cannot"}.get(info.get("kind")) or (
            "still_wrong" if info.get("unfixed") else "done")
        text = " ".join(str(info.get("text") or "").split())
        if text and out["event"] != "still_wrong":
            out["say"] = text if len(text) <= SAY_MAX else text[:SAY_MAX - 3].rstrip() + "..."
            out["kind"] = "question" if out["event"] == "asking" else "done"
    if out["event"] is None:
        return None
    return out


# ---- the word lines (design section 5): what the model says, applied by code ------------------
# An answer may carry `show`: a list of lines, each one object, words only:
#   {"line": "say", "text": <words>, "effect"?: <effect>}
#   {"line": "show maris", "pose": <pose word>}
#   {"line": "ask", "question": <words>, "about"?: <a thing of the scene>, "choices"?: [<=3 short words]}
#   {"line": "clear messages"}
# apply_lines checks them against the shipped lists and returns plain actions for the add-on
# (addon/show.py builds the objects in `Messages`). It never writes, picks or repairs a word: a line
# that is not on the lists is dropped and reported, the rest still runs.

LINES = ("say", "show maris", "ask", "clear messages")
POSES = ("wave", "point", "think", "thumbs_up", "shrug", "dance")      # the poses a model may name
POSE_ANIMATION = {"think": "weave"}      # pose word -> the rig action in maris.json (others are the same)
MAX_LINES = 4
MAX_TEXT = 160
MAX_CHOICES = 3
MAX_CHOICE = 40


def _words(v, limit):
    return isinstance(v, str) and 0 < len(v.strip()) <= limit


def _effect(line, kind):
    effect = line.get("effect")
    if effect is None:
        return DEFAULT_EFFECT[kind]
    if effect not in EFFECTS:
        raise ValueError(f"effect {effect!r}; one of " + ", ".join(EFFECTS))
    return effect


def apply_lines(lines, things=None):
    """The `show` lines of an answer -> (actions, errors). things: the scene's thing names (an `ask`
    `about` must be one of them when given). Actions, in order:
      {"op": "say", "text", "effect"}              effect defaults to the kind's (type)
      {"op": "maris", "pose", "animation"}
      {"op": "ask", "question", "about", "choices", "effect"}
      {"op": "clear"}                              code removes the whole `Messages` collection
    A `clear messages` line clears first: lines before it are dropped, lines after it show."""
    if lines is None:
        return [], []
    if not isinstance(lines, list):
        return [], ["show is a list of lines"]
    actions, errors = [], []
    for i, line in enumerate(lines[:MAX_LINES]):
        kind = line.get("line") if isinstance(line, dict) else None
        try:
            if kind == "say":
                if not _words(line.get("text"), MAX_TEXT):
                    raise ValueError("say needs text")
                actions.append({"op": "say", "text": line["text"].strip(), "effect": _effect(line, "say")})
            elif kind == "show maris":
                pose = line.get("pose")
                if pose not in POSES:
                    raise ValueError(f"pose {pose!r}; one of " + ", ".join(POSES))
                actions.append({"op": "maris", "pose": pose, "animation": POSE_ANIMATION.get(pose, pose)})
            elif kind == "ask":
                if not _words(line.get("question"), MAX_TEXT):
                    raise ValueError("ask needs a question")
                about = line.get("about")
                if about is not None and (not isinstance(about, str) or (things is not None and about not in things)):
                    raise ValueError(f"ask about {about!r}: not a thing of the scene")
                choices = line.get("choices", [])
                if (not isinstance(choices, list) or len(choices) > MAX_CHOICES
                        or not all(_words(c, MAX_CHOICE) for c in choices)):
                    raise ValueError(f"choices: at most {MAX_CHOICES} short words")
                actions.append({"op": "ask", "question": line["question"].strip(), "about": about,
                                "choices": [c.strip() for c in choices], "effect": _effect(line, "question")})
            elif kind == "clear messages":
                actions = [{"op": "clear"}]
            else:
                raise ValueError(f"line {kind!r}; one of " + ", ".join(LINES))
        except ValueError as error:
            errors.append(f"show line {i}: {error}")
    if len(lines) > MAX_LINES:
        errors.append(f"show: only the first {MAX_LINES} lines are used")
    return actions, errors


def steps(actions):
    """apply_lines actions -> the primitive steps the add-on applies on the main thread, in order:
      ("clear",)  ("pose", animation)  ("text", text, effect, kind, about)
    An `ask` is its question (kind "question", near `about` when given) then one small label per
    choice (kind "choice", effect pop). Unknown ops are skipped. Pure, no bpy."""
    out = []
    for a in actions or []:
        op = a.get("op") if isinstance(a, dict) else None
        if op == "clear":
            out.append(("clear",))
        elif op == "maris":
            out.append(("pose", a.get("animation") or a.get("pose")))
        elif op == "say":
            out.append(("text", a["text"], a.get("effect") or DEFAULT_EFFECT["say"], "say", None))
        elif op == "ask":
            out.append(("text", a["question"], a.get("effect") or DEFAULT_EFFECT["question"],
                        "question", a.get("about")))
            for i, c in enumerate(a.get("choices") or [], 1):
                out.append(("text", f"{i}. {c}", "pop", "choice", a.get("about")))
    return out


def question_of(actions):
    """The last `ask` of apply_lines actions that carries choices -> {"question", "about", "choices"},
    else None. The panel shows one button per choice. Pure, no bpy."""
    found = None
    for a in actions or []:
        if isinstance(a, dict) and a.get("op") == "ask" and a.get("choices"):
            found = {"question": a["question"], "about": a.get("about"), "choices": list(a["choices"])}
    return found


def answer_prompt(prompt, choice):
    """The request a choice button sends: the asked request with the chosen thing named after it.
    The words go to the model as typed; nothing is resolved by code."""
    prompt, choice = (prompt or "").strip().rstrip("."), (choice or "").strip()
    return f"{prompt} ({choice})" if prompt else choice


class ActionQueue:
    """Thread-safe hand-over from the worker thread (put) to the main-thread timer (take)."""

    def __init__(self, limit=50):
        import collections
        import threading
        self._items = collections.deque(maxlen=limit)
        self._lock = threading.Lock()

    def put(self, actions):
        if actions:
            with self._lock:
                self._items.extend(steps(actions))

    def take(self):
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items

    def __len__(self):
        return len(self._items)


def scene_scale(dims):
    """Maris height for a scene whose bounding box has these dimensions: about a fifth of the
    largest side, between 0.4 m (a table top) and 3 m (a street)."""
    size = max(dims) if dims else 0.0
    return max(0.4, min(3.0, size * 0.2)) if size > 0 else 1.0


# ---- maris colours: the planner / edit colour language (copilot/colours.py), one code path
# for the build script, the add-on panel and the pages.

def maris_colour(spec, slot, outfit=None, skin=None, custom=None, hair=None):
    """The colour answer a Maris slot wears: the user's own choice for the slot (custom), else
    the skin preset (slot "skin") or hair preset (slots "hair" and "brow"), else the outfit's
    colour, else the slot default."""
    if custom and slot in custom:
        return custom[slot]
    if slot == "skin" and skin in spec.get("skins", {}):
        return spec["skins"][skin]
    if slot in ("hair", "brow") and hair in spec.get("hairs", {}):
        return spec["hairs"][hair][slot]
    if outfit and slot in spec["outfits"].get(outfit, {}).get("colours", {}):
        return spec["outfits"][outfit]["colours"][slot]
    return spec["slots"][slot]["colour"]


def maris_material(spec, slot, outfit=None, skin=None, custom=None, hair=None):
    """(material name, material dict) for a slot. The dict is colours.material() output:
    color (linear RGB), roughness, maybe metallic / alpha / emission_strength. The thread and
    toy slot always glows a little (it is the gold thread)."""
    from . import colours
    answer = maris_colour(spec, slot, outfit, skin, custom, hair)
    mat = dict(colours.material(answer))
    if slot == "gold":
        mat.setdefault("emission_strength", 1.8)   # glows, and still reads as gold
    key = "maris_" + slot + "." + colour_key(answer)
    return key, mat


def colour_key(answer):
    """A short stable name for a colour answer (materials are reused by it)."""
    if isinstance(answer, str):
        return answer
    if "hex" in answer:
        return str(answer["hex"]).lstrip("#").lower()
    parts = [str(answer.get(k)) for k in ("name", "shade", "look", "see_through") if answer.get(k)]
    return "_".join(parts) or "custom"


# ---- designs: the three shipped looks and the user's own, all in one format
# {"label": str, "outfit": <outfit name>, "skin": <skin name>, "hair": <hair name>,
#  "toy": <toy name, "random" or "random_any">, "colours": {slot: colour answer}}
# ("hair" and "toy" may be missing in designs saved before they existed)
# The shipped designs are the outfits of maris.json; a user design is saved to a JSON file in
# the add-on's user folder and listed after them, so a saved design shows with the 3 options.

DESIGN_KEYS = ("label", "outfit", "skin", "hair", "toy", "colours")


def preset_designs(spec):
    return {name: {"label": o["label"], "outfit": name, "skin": spec["default_skin"],
                   "hair": spec["default_hair"], "toy": spec["default_toy"], "colours": {}}
            for name, o in spec["outfits"].items()}


def design_faults(spec, design):
    """What is wrong with a design (empty = it can be worn)."""
    if not isinstance(design, dict):
        return ["design is not an object"]
    out = [f"design key {k!r}" for k in design if k not in DESIGN_KEYS]
    if not str(design.get("label", "")).strip():
        out.append("design label")
    if design.get("outfit") not in spec["outfits"]:
        out.append(f"outfit {design.get('outfit')!r}")
    if design.get("skin") not in spec["skins"]:
        out.append(f"skin {design.get('skin')!r}")
    if design.get("hair", spec["default_hair"]) not in spec["hairs"]:
        out.append(f"hair {design.get('hair')!r}")
    if design.get("toy", spec["default_toy"]) not in toy_choices(spec):
        out.append(f"toy {design.get('toy')!r}")
    cols = design.get("colours", {})
    if not isinstance(cols, dict):
        return out + ["colours is not an object"]
    from . import colours
    for slot, answer in cols.items():
        if slot not in spec["slots"]:
            out.append(f"slot {slot!r}")
        else:
            out += [f"{slot}: {f}" for f in colours.faults(answer)]
    return out


def toy_choices(spec):
    """Every value a design's "toy" may have: each toy, then the random modes."""
    return list(spec["toys"]) + list(spec["toy_choices"])


def pick_toy(spec, design, rng=None, last=None):
    """The toy to weave now. A fixed choice is that toy; "random" picks from the outfit's toy theme
    (winter: the Christmas toys), "random_any" from all; a random pick avoids repeating `last`."""
    import random
    choice = design.get("toy", spec["default_toy"])
    if choice in spec["toys"]:
        return choice
    if choice == "random":
        theme = spec["outfits"][design["outfit"]].get("toy_theme")
        pool = [k for k, t in spec["toys"].items() if t["theme"] == theme] or list(spec["toys"])
    else:
        pool = list(spec["toys"])
    if last in pool and len(pool) > 1:
        pool.remove(last)
    return (rng or random).choice(pool)


def design_materials(spec, design):
    """{slot: (material name, colours.material dict)} for every slot of a design."""
    return {slot: maris_material(spec, slot, outfit=design["outfit"], skin=design["skin"],
                                  custom=design.get("colours") or {},
                                  hair=design.get("hair", spec["default_hair"]))
            for slot in spec["slots"]}


def slug(label):
    s = "".join(ch if ch.isalnum() else "_" for ch in label.strip().lower()).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:40] or "design"


def load_user_designs(path, spec):
    """The user's saved designs ({} when none). Broken entries are skipped, never fatal."""
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    designs = data.get("designs", {}) if isinstance(data, dict) else {}
    return {k: v for k, v in designs.items() if isinstance(k, str) and not design_faults(spec, v)}


def save_user_design(path, spec, design, name=None):
    """Save (or replace) one user design; returns its key. Shipped names are never overwritten:
    a design called "Sea" is saved as "sea_2"."""
    import json
    import os
    bad = design_faults(spec, design)
    if bad:
        raise ValueError("; ".join(bad))
    designs = load_user_designs(path, spec)
    key = name or slug(design["label"])
    base, n = key, 2
    while key in spec["outfits"] or (name is None and key in designs):
        key, n = f"{base}_{n}", n + 1
    designs[key] = {k: design[k] for k in DESIGN_KEYS if k in design}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "designs": designs}, fh, indent=2)
    os.replace(tmp, path)
    return key


def delete_user_design(path, spec, key):
    import json
    import os
    designs = load_user_designs(path, spec)
    if designs.pop(key, None) is None:
        return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "designs": designs}, fh, indent=2)
    os.replace(tmp, path)
    return True


def all_designs(spec, path=None):
    """Shipped designs first, then the user's, as {key: design}."""
    out = preset_designs(spec)
    if path:
        out.update(load_user_designs(path, spec))
    return out


# ---- poses, pieces and tools per outfit (maris.json outfits[].idle / tool, pose_parts) ---------

def idle_pose(spec, outfit):
    """The outfit's resting loop: its "idle" (the ninja's never stands still), else idle."""
    return (spec["outfits"].get(outfit) or {}).get("idle", "idle")


def looping(spec):
    """Poses that loop until another pose starts: every idle, plus weave, run and float."""
    return {"weave", "run", "float"} | {idle_pose(spec, o) for o in spec["outfits"]} | {"idle"}


def visible(spec, names, outfit, pose="idle", props=None, toy=None):
    """{object name: shown} for Maris's objects in this outfit and pose. Objects not in the
    result keep their state (mouths: face() picks them).

    props: {name: custom properties} (maris_outfit, maris_tool, maris_pose, maris_toy). Rules:
    a tool shows only in a pose with tool true and only for its outfit; a maris_pose mesh only in
    those poses; a toy only if it is the current toy and the pose keeps the toy (as the thread);
    outfit pieces only for their outfit; what the outfit or the pose hides is hidden."""
    props = props or {}
    pre = spec["prefix"]
    rule = (spec.get("pose_parts") or {}).get(pose) or {}
    hidden = set(spec["outfits"][outfit]["hide"]) | set(rule.get("hide", ()))
    managed = ({h for o in spec["outfits"].values() for h in o["hide"]}
               | {h for r in (spec.get("pose_parts") or {}).values() for h in r.get("hide", ())})
    keep_toy, tool = rule.get("toy", True), rule.get("tool", False)
    out = {}
    for name in names:
        p = props.get(name) or {}
        base = name[len(pre):] if name.startswith(pre) else name
        if "maris_tool" in p:
            out[name] = tool and p["maris_tool"] == outfit
        elif "maris_pose" in p:
            out[name] = pose in str(p["maris_pose"]).split(",")
        elif "maris_toy" in p:
            out[name] = keep_toy and p["maris_toy"] == toy
        elif base == "Thread":
            out[name] = keep_toy
        elif "maris_outfit" in p:
            out[name] = p["maris_outfit"] == outfit and base not in hidden
        elif base in managed:
            out[name] = base not in hidden
    return out


# ---- sitting: on a seat near her, else on the ground ---------------------------------------------

SEAT_WORDS = ("chair", "seat", "bench", "sofa", "stool", "couch", "armchair", "settee", "throne")


def name_words(name):
    """Lower-case words of an object name: 'OfficeChair.001' -> ['office', 'chair']."""
    import re
    base = name.split(".")[0]
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", base)
    return [w.lower() for w in parts]


def is_seat_name(name):
    """A thing to sit on, by its main (last) word: chair, bench, sofa, stool ... ('BenchLeg' and
    'ChairBack' are parts, not seats)."""
    words = name_words(name)
    if not words:
        return False
    last = words[-1]
    return any(last == w or last in (w + "s", w + "es") for w in SEAT_WORDS)


def seat_facing(centre_top, side_tops, height):
    """Which way to face on a seat. centre_top is the seat height at its middle; side_tops is
    [((dx, dy), top or None)] at four sides. A side clearly higher than the seat (a back) means
    face away from it: returns the (x, y) unit direction, or None (no back: face the camera)."""
    best, best_top = None, centre_top + 0.2 * height
    for (dx, dy), top in side_tops:
        if top is not None and top > best_top:
            best, best_top = (dx, dy), top
    if best is None:
        return None
    n = math.hypot(*best) or 1.0
    return (-best[0] / n, -best[1] / n)


def seat_scale(spec, seat_height, height):
    """Her height on a seat whose top is seat_height above the floor: legs reaching the floor,
    within half to twice her height in this scene; None if the seat does not fit her at all."""
    want = seat_height / spec["sitting"]["seat_height"]
    if not (0.5 * height <= want <= 2.0 * height):
        return None
    return want


def yaw_to(dx, dy):
    """Rig rotation about z (radians) that turns her front (-Y) toward (dx, dy)."""
    return math.atan2(dx, -dy)


# ---- carrying parts to their places ----------------------------------------------------------------
# A new part pops in at a spot a few of her heights from its place; she pops in beside it, grabs
# it (it floats over her head), dashes to its place (lean, arms back) and places it with the
# outfit's tool. On the way, things in her line: small ones she trips over (or phases), big ones
# she crashes into and goes round, goes round, or phases through (flickering). Where she stands
# she never overlaps anything. Presentation only: the real part is already built.

CARRY_HOLD = (0.0, 0.0, 1.35)     # a carried part's centre: over her head (her space, height 1)
CARRY_SIZE = 0.6                  # a carried part is at most this many of her heights across
CARRY_MAX_WAITING = 12            # more waiting parts than this appear at once, uncarried
CARRY_TIMES = {"pop": 0.18, "pickup": 0.3, "place": 0.55, "speed": 4.0, "trip": 0.45,
               "crash": 0.7, "phase_speed": 2.5}
FOOT = 0.2                        # her footprint radius (heights): standing spots keep clear by this
SMALL = 0.3                       # things lower than this many of her heights are tripped over
FLAT = 0.04                       # thinner than this (floors, rugs): walked on, never an obstacle


CARRY_MAX_SIZE = 3.0             # parts bigger than this many of her heights: she watches instead (person-sized, she still carries a house block)


GROW_SMALL = 0.5                 # parts smaller than this many of her heights grow in, not carried


def carry_choice(kind, has_parent, has_children, size, height, waiting, attached=False):
    """How a new part comes in. "carry": she brings it to its place (a single stand-alone mesh, not
    too big, not when many wait). "grow": it grows in where it belongs while she points her tool
    at it: a small piece, or one fixed to the side of a bigger thing (a door, a window, a bauble);
    running with those only looks busy. "watch": she turns to it and looks; it simply appears
    (groups, non-meshes, very big parts, a long queue)."""
    if kind != "MESH" or has_parent or has_children:
        return "watch"
    if attached or size < GROW_SMALL * height:
        return "grow"
    if size > CARRY_MAX_SIZE * height or waiting >= 4:
        return "watch"
    return "carry"


def attached_to(part, others, height):
    """True when the part (a world box) is fixed to the side of a bigger thing: it touches a box
    with more than 1.5 times its volume and does not sit on top of it (a roof on walls or a tier on
    a tree is placed, so it is carried)."""
    (x0, y0, z0), (x1, y1, z1) = part
    vol = max(1e-9, (x1 - x0) * (y1 - y0) * (z1 - z0))
    g = 0.05 * height
    for (a0, b0, c0), (a1, b1, c1) in others:
        if (a1 - a0) * (b1 - b0) * (c1 - c0) <= 1.5 * vol:
            continue
        if x1 < a0 - g or x0 > a1 + g or y1 < b0 - g or y0 > b1 + g or z1 < c0 - g or z0 > c1 + g:
            continue
        if z0 >= c1 - 0.25 * (z1 - z0):
            continue                           # on top of it: placed, not fixed to its side
        return True
    return False


GROW_TIMES = {"gap": 0.35, "each": 0.7}   # seconds between growing parts, seconds each takes


def grow_scale(x):
    """Scale of a growing part at x (0..1 of its time): from nothing, a little past full, back."""
    x = _clamp(x)
    if x >= 1.0:
        return 1.0
    c = 1.70158                                # ease-out-back
    y = x - 1.0
    return max(0.01, 1 + (c + 1) * y ** 3 + c * y ** 2)


# ---- ground, size, where things come from ----------------------------------------------------------

def is_ground(dims, height):
    """A wide flat thing she stands on (snow, a floor, a path): low and at least two of her heights
    across. It never sets her size and it is walked on."""
    wide = max(dims[0], dims[1])
    return wide >= 2.0 * height and dims[2] <= 0.1 * wide


def ground_top(grounds, x, y):
    """Top of the highest ground box under (x, y), or None."""
    best = None
    for (x0, y0, _z0), (x1, y1, z1) in grounds:
        if x0 <= x <= x1 and y0 <= y <= y1:
            best = z1 if best is None else max(best, z1)
    return best


def person_height(tallest, current):
    """Her height in a scene whose tallest standing thing (not ground) is `tallest` high: about two
    thirds of it, like a person by a house, 0.4 to 3 m. She keeps her height unless the new one is
    off by more than a third, so she does not grow and shrink while a scene is built."""
    if tallest <= 0:
        return current
    want = max(0.4, min(1.8, 0.65 * tallest))   # a person: never a giant beside a tall building
    return want if abs(want - current) > current / 3 else current


def rim_spot(ground, goal, height, eye=None, rng=None, out=0.45):
    """Where a part she will carry pops in when there is ground: just past its edge on the side
    nearest the part's place (toward the viewer when the place is near the middle). The ground box
    is taken as the ellipse inside it (a disc of snow, a round rug)."""
    (x0, y0, _z0), (x1, y1, _z1) = ground
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, max(1e-6, (x1 - x0) / 2), max(1e-6, (y1 - y0) / 2)
    dx, dy = goal[0] - cx, goal[1] - cy
    if math.hypot(dx / rx, dy / ry) < 0.3 and eye is not None:
        dx, dy = eye[0] - cx, eye[1] - cy
    a = math.atan2(dy, dx) + (rng.uniform(-0.45, 0.45) if rng is not None else 0.0)
    ux, uy = math.cos(a), math.sin(a)
    edge = 1.0 / math.sqrt((ux / rx) ** 2 + (uy / ry) ** 2)
    d = edge + out * height                    # out < 0: just inside the edge (she stands there)
    return (cx + d * ux, cy + d * uy, goal[2])


def moved_groups(before, after, height, min_move=0.5):
    """What one request moved, as groups: {(dx, dy, dz) rounded: [names]} for things that moved by
    the same amount and at least min_move of her heights (a snowman's three balls move together)."""
    out = {}
    for name, a in after.items():
        b = before.get(name)
        if b is None:
            continue
        d = tuple(round(a[k] - b[k], 3) for k in range(3))
        if math.hypot(d[0], d[1]) >= min_move * height:
            out.setdefault(d, []).append(name)
    return out


def turn_step(current, target, rate=7.0 / 30):
    """One frame of turning from yaw `current` toward `target` (radians), the short way round."""
    diff = (target - current + math.pi) % (2 * math.pi) - math.pi
    return current + diff * min(1.0, rate)


def carry_speedup(waiting):
    """How much faster each carry goes with this many parts waiting: 1 to 4 times."""
    return min(4.0, 1.0 + 0.35 * max(0, waiting))


def hold_scale(size, height):
    """Scale for a part `size` across (largest side) while she holds it: never bigger than it is,
    at most CARRY_SIZE of her height."""
    if size <= 0:
        return 1.0
    return min(1.0, CARRY_SIZE * height / size)


def ease(x):
    """Smooth 0..1 (ease in and out)."""
    x = _clamp(x)
    return x * x * (3 - 2 * x)


def place_path(start, end, x, lift):
    """A point on the arc from start to end (x in 0..1), `lift` metres up at the middle."""
    e = ease(x)
    p = [start[k] + (end[k] - start[k]) * e for k in range(3)]
    p[2] += lift * 4 * e * (1 - e)
    return tuple(p)


def _overlaps(p, r, box):
    (x0, y0, _), (x1, y1, _) = box
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return dx * dx + dy * dy < r * r


def solid(boxes, height):
    """The boxes she can bump into: not flat (floors, rugs)."""
    return [b for b in boxes if b[1][2] - b[0][2] >= FLAT * height]


def free_spot(spot, height, boxes, tries=12):
    """`spot` (x, y, z), moved the least so her footprint overlaps no box: she always stands
    clear of things. Boxes are ((x0, y0, z0), (x1, y1, z1)); flat ones are ignored."""
    r = FOOT * height
    p = [spot[0], spot[1]]
    boxes = solid(boxes, height)
    for _ in range(tries):
        hit = next((b for b in boxes if _overlaps(p, r, b)), None)
        if hit is None:
            break
        (x0, y0, _), (x1, y1, _) = hit
        moves = [(x0 - r - p[0], 0.0), (x1 + r - p[0], 0.0), (0.0, y0 - r - p[1]), (0.0, y1 + r - p[1])]
        dx, dy = min(moves, key=lambda m: abs(m[0]) + abs(m[1]))
        p = [p[0] + dx * 1.001, p[1] + dy * 1.001]
    return (p[0], p[1], spot[2])


def pop_spot(goal, height, eye, rng, boxes=()):
    """Where a new part pops in: 2.5 to 4 of her heights from its place, toward the camera side
    (so the dash shows), on clear ground."""
    if eye is not None:
        base = math.atan2(eye[1] - goal[1], eye[0] - goal[0])
    else:
        base = -math.pi / 2                    # Blender's front view looks along +y
    a = base + rng.uniform(-1.1, 1.1)
    d = rng.uniform(2.5, 4.0) * height
    return free_spot((goal[0] + d * math.cos(a), goal[1] + d * math.sin(a), goal[2]), height, boxes)


def _crossing(a, b, box, r):
    """(t_in, t_out) where segment a->b crosses the box grown by r, or None."""
    (x0, y0, _), (x1, y1, _) = box
    lo, hi = [x0 - r, y0 - r], [x1 + r, y1 + r]
    t0, t1 = 0.0, 1.0
    for k in range(2):
        d = b[k] - a[k]
        if abs(d) < 1e-9:
            if not lo[k] <= a[k] <= hi[k]:
                return None
            continue
        u, v = (lo[k] - a[k]) / d, (hi[k] - a[k]) / d
        t0, t1 = max(t0, min(u, v)), min(t1, max(u, v))
        if t0 > t1:
            return None
    return (t0, t1)


def _lerp2(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _cuts(a, b, box, r):
    """Segment a->b passes through the inside of the box grown by r (touching is fine)."""
    c = _crossing(a, b, box, r)
    return c is not None and c[1] - c[0] > 1e-6


def _round(a, b, box, r):
    """The shortest way from a to b round the box: via one or two of its corners (grown by r)."""
    (x0, y0, _), (x1, y1, _) = box
    cs = [(x0 - r, y0 - r), (x1 + r, y0 - r), (x1 + r, y1 + r), (x0 - r, y1 + r)]
    ways = [[c] for c in cs] + [[cs[i], cs[(i + d) % 4]] for i in range(4) for d in (1, 3)]
    best, best_len = None, None
    for way in ways:
        pts = [a] + way + [b]
        if any(_cuts(p, q, box, 0.0) for p, q in zip(pts, pts[1:])):
            continue
        length = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        if best is None or length < best_len:
            best, best_len = way, length
    return best or [cs[0]]


def dash_route(start, goal, boxes, height, rng, hurry=False):
    """Her dash from start to goal (x, y) past the boxes in the way, as steps:
    ("run", a, b), ("phase", a, b) (through a thing, flickering), ("trip", p), ("crash", p).
    Small things: trip (or phase); big ones: crash then go round, go round, or phase. hurry
    (many parts waiting): straight through, phasing. Boxes holding start or goal are skipped."""
    r = FOOT * height
    todo = [bx for bx in solid(boxes, height)
            if not _overlaps(start, r * 0.5, bx) and not _overlaps(goal, r * 0.5, bx)]
    steps, cur = [], tuple(start[:2])
    goal = tuple(goal[:2])
    for _ in range(10):
        hits = [(c, bx) for bx in todo for c in [_crossing(cur, goal, bx, r * 0.5)] if c]
        if not hits:
            break
        (t_in, t_out), bx = min(hits, key=lambda h: h[0][0])
        todo.remove(bx)
        enter, leave = _lerp2(cur, goal, t_in), _lerp2(cur, goal, t_out)
        low = bx[1][2] - bx[0][2] < SMALL * height
        roll = rng.random()
        if hurry:
            act = "phase"
        elif low:
            act = "trip" if roll < 0.7 else "phase"
        else:
            act = "crash" if roll < 0.3 else "round" if roll < 0.65 else "phase"
        if math.dist(cur, enter) > 1e-6:
            steps.append(("run", cur, enter))
        if act == "trip":
            steps += [("trip", enter), ("run", enter, leave)]
            cur = leave
        elif act == "phase":
            steps.append(("phase", enter, leave))
            cur = leave
        else:
            if act == "crash":
                steps.append(("crash", enter))
            prev = enter
            for way in _round(enter, goal, bx, r):
                steps.append(("run", prev, way))
                prev = way
            cur = prev
    if math.dist(cur, goal) > 1e-6:
        steps.append(("run", cur, goal))
    return steps


def step_time(step, height, hurry_k=1.0):
    """Seconds one dash step takes (divided by the hurry factor)."""
    t = CARRY_TIMES
    if step[0] in ("trip", "crash"):
        return t[step[0]] / hurry_k
    speed = t["speed"] if step[0] == "run" else t["phase_speed"]
    return math.dist(step[1], step[2]) / (speed * height) / hurry_k
