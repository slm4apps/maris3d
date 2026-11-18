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
