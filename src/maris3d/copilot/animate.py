# SPDX-License-Identifier: Apache-2.0
"""Motion by code: "spin it once over one second", "a ball bouncing twice", "a moon going round a planet".

0.2's word path had no animation route (yardstick 0.2: 0 of 37 animation rows moved), the edit adapter has
no animate word, and the compiler already writes keyframes. So, like the finish (smooth / merge), a motion
is read from the sentence and written as `keyframe` + `set_frame_end` calls by code, no model:

    parse(request)                -> [Motion], empty when the sentence orders no motion
    plan_calls(motions, objects)  -> (calls, notes, missing): keys for the things the scene has; `missing`
                                     names the nouns no object matched (the caller builds them first)
    make_missing(nouns, objects)  -> calls that add a plain primitive / camera / light for a noun no build made

Values are absolute basis values: an object's world location and rotation (objects()) are its basis while its
parent has not moved since parenting (the parent call keeps matrix_world), and scale is taken as 1 (the
builder applies scale). 24 frames per second, as the Blender default.
"""
import math
import re
from dataclasses import dataclass, field

FPS = 24

_NUM = {"a": 1, "an": 1, "one": 1, "once": 1, "two": 2, "twice": 2, "three": 3, "thrice": 3, "four": 4, "five": 5,
        "six": 6, "half a": 0.5, "half": 0.5, "a quarter": 0.25}
_NUMBER = r"(\d+(?:\.\d+)?|half a|a quarter|one|two|three|four|five|six|a|an)"
SECONDS = re.compile(_NUMBER + r"[- ](?:full )?seconds?", re.I)
METRES = re.compile(_NUMBER + r"[- ](?:metres?|meters?|m\b)", re.I)
DEGREES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:degrees?|°)", re.I)
TIMES = re.compile(r"\b(once|twice|thrice|(?:one|two|three|four|five|\d+) (?:times|bounces|jumps|turns|full turns))\b", re.I)

# motion kind -> words that order it (first match wins, in this order)
KINDS = (
    ("orbit", r"\borbit\w*|\bcircl\w*|going round (?:a|an|the|its)\b|goes round (?:a|an|the)\b|(?:swim\w*|fly\w*|mov\w*) in a circle"
              r"|\bround (?:a|an|the) \w+ once|around (?:a|an|the) (?:rock|planet|sun|cube|tree|pole|island)"),
    ("pulse", r"\bpuls\w*|brighter and dimmer|flicker\w*|blink\w*"),
    ("color", r"\bfrom (?:\w+ )?(?:red|blue|green|yellow|white|black|orange|purple|pink) to (?:red|blue|green|yellow|white|black|orange|purple|pink)"),
    ("bounce", r"\bbounc\w*|\bjump\w*|\bhop\w*"),
    ("grow", r"\bgrow\w*|from tiny|scale up|get bigger|gets bigger"),
    ("shrink", r"\bshrink\w*|to nothing|scale down|get smaller|gets smaller|disappear"),
    ("swing", r"\bswing\w*|\brock\w*|\bwav\w*|\bflap\w*|\btick\w*|\bsway\w*|\bbend\w*|\bsweep\w*|\bnod\w*|back and forth|side to side|left and right|up and down"),
    ("spin", r"\bspin\w*|\brotat\w*|\bturn\w* round|\bturn\w* in the wind|full turn|\bgoing round\b|\bgoes round\b|\bturning\b|\brolling\b|\broll\w* along|spin it|turn it once|once around|all the way round"),
    ("rise", r"\blift\w*|\brise\w*|\brising\b|\bfloat\w*|\bgo(?:es)? up\b|\bmove\w* up\b|\braise\w*|\bclimb\w*"),
    ("move", r"\bmov\w*|\bslid\w*|\bacross\b|\bother side\b|\btravel\w*|\bdrive\w*|\bfly\w* (?:to|across)|\bgo(?:es)? (?:to|across)"),
)
_KIND_RE = [(k, re.compile(p, re.I)) for k, p in KINDS]
ANIM_WORDS = re.compile(r"\banimat\w*|\bkeyfram\w*|over (?:" + _NUMBER + r"[- ])?seconds?|seconds? long|\bin (?:" + _NUMBER
                        + r") seconds?|at the same time|\bslowly\b|\bfast\b", re.I)

COLORS = {"red": [0.8, 0.05, 0.05, 1], "blue": [0.05, 0.15, 0.8, 1], "green": [0.1, 0.6, 0.1, 1], "yellow": [0.9, 0.8, 0.05, 1],
          "white": [0.95, 0.95, 0.95, 1], "black": [0.02, 0.02, 0.02, 1], "orange": [0.9, 0.4, 0.05, 1],
          "purple": [0.4, 0.1, 0.6, 1], "pink": [0.9, 0.4, 0.6, 1]}

# nouns a motion can be about, with the words an object name may carry for them
NOUNS = {
    "cube": ("cube", "box"), "box": ("box", "cube", "elevator", "lift", "cabin"), "sphere": ("sphere", "ball"),
    "ball": ("ball", "sphere"), "torus": ("torus", "ring", "donut"), "ring": ("ring", "torus"), "cone": ("cone",),
    "cylinder": ("cylinder",), "moon": ("moon",), "planet": ("planet",), "camera": ("camera", "cam"),
    "light": ("light", "lamp", "spot", "point"), "spotlight": ("spot", "light"), "lamp": ("lamp", "light"),
    "fan": ("blade", "fan"), "blade": ("blade",), "blades": ("blade",), "chair": ("chair",), "wing": ("wing",), "wings": ("wing",),
    "door": ("door",), "pendulum": ("pendulum", "bob", "weight"), "elevator": ("elevator", "lift", "cabin", "box"),
    "arm": ("arm",), "metronome": ("arm", "metronome"), "wheel": ("wheel",), "rotor": ("rotor", "blade"),
    "windmill": ("sail", "blade"), "sails": ("sail", "blade"), "sail": ("sail", "blade"), "carousel": ("carousel", "merry", "platform"),
    "fish": ("fish",), "rock": ("rock", "stone"), "flag": ("flag",), "empty": ("empty", "pivot", "hub"), "head": ("head",),
    "robot": ("robot",), "bird": ("wing",), "helicopter": ("rotor", "blade"), "puppet": ("arm",),
}
PRIMITIVES = {"cube": "cube", "box": "cube", "sphere": "uv_sphere", "ball": "uv_sphere", "torus": "torus", "ring": "torus",
              "cone": "cone", "cylinder": "cylinder", "moon": "uv_sphere", "planet": "uv_sphere", "rock": "ico_sphere",
              "elevator": "cube", "wheel": "cylinder", "fish": "uv_sphere"}
# a part a sentence names beats the whole thing ("a robot waving its arm" moves the arm)
PARTS = ("arm", "wing", "wings", "head", "door", "blade", "blades", "rotor", "sail", "sails", "flag", "wheel", "empty")
_LEFTRIGHT = re.compile(r"\b(right|left)\b", re.I)


@dataclass
class Motion:
    kind: str
    noun: str = ""            # what moves ("" = "it": the last built thing)
    around: str = ""          # orbit centre noun
    seconds: float = 2.0
    times: float = 1.0        # bounces, turns, swings
    metres: float = 0.0
    degrees: float = 0.0
    colors: list = field(default_factory=list)
    side: str = ""            # "right" / "left" when the sentence says which one


def _num(text):
    text = text.lower()
    return float(text) if re.fullmatch(r"\d+(?:\.\d+)?", text) else float(_NUM.get(text, 1))


def is_motion(request):
    """True when the sentence orders a motion over time (not "turn it 90 degrees", which is a pose)."""
    low = str(request).lower()
    if not any(r.search(low) for _, r in _KIND_RE):
        return False
    if ANIM_WORDS.search(low):
        return True
    # a motion verb on its own: continuous forms and verbs that only mean motion
    return bool(re.search(r"\b(spinning|bouncing|bounce|orbit\w*|circling|swinging|rocking|waving|wave|flapping|ticking|"
                          r"spin|spins|pulse|pulsing|rolling|turning in|going round|goes round|swimming in a circle|floats? up|lifts? off|"
                          r"sweeping|grow\w*|shrink\w*|jump\w*|swing\w*|rising|lifting up|go up .* and stop)\b", low))


def _nouns(low):
    """Nouns in sentence order, with their position."""
    found = []
    for noun in NOUNS:
        for m in re.finditer(r"\b" + noun + r"s?\b", low):
            found.append((m.start(), noun))
    found.sort()
    out = []
    for _, noun in found:
        if noun not in out:
            out.append(noun)
    return out


def introduces(request, nouns):
    """True when the sentence brings each missing noun in as a new thing ("a ball bouncing", "two
    wheels spinning"), not when it points at one the scene should have ("make the flag wave")."""
    low = (request or "").lower()
    lead = r"\b(?:a|an|another|one|two|three|four|some)\s+(?:[a-z-]+\s+){0,2}"
    return bool(nouns) and all(re.search(lead + re.escape(n) + r"s?\b", low) for n in nouns)


def parse(request):
    """[Motion] the sentence orders; [] when it orders none."""
    low = str(request).lower()
    if not is_motion(low):
        return []
    sec = SECONDS.search(low)
    seconds = _num(sec.group(1)) if sec else (4.0 if "slowly" in low else 1.0 if "fast" in low else 2.0)
    times_m = TIMES.search(low)
    times = _num(times_m.group(1).split()[0]) if times_m else 1.0
    met = METRES.search(low)
    deg = DEGREES.search(low)
    nouns = _nouns(low)
    side = (_LEFTRIGHT.search(low).group(1).lower() if _LEFTRIGHT.search(low) and re.search(r"\b(right|left) (arm|wing|door|hand|leg)", low) else "")
    kinds = [k for k, r in _KIND_RE if r.search(low)]
    # "spin ... and lift / move ... at the same time": two motions on one thing; else the first kind
    if "empty" in nouns and re.search(r"\bempty (?:spin|rotat|turn)|spin the empty|rotate the empty|turn the empty", low):
        kinds = ["spin"]
    elif "orbit" in kinds:
        kinds = ["orbit"]
    elif {"spin", "rise"} <= set(kinds) or {"spin", "move"} <= set(kinds):
        kinds = ["spin", "rise" if "rise" in kinds else "move"]
    elif "bounce" in kinds and "forward" in low:
        kinds = ["bounce", "move"]
    else:
        kinds = kinds[:1]
    out = []
    for kind in kinds:
        m = Motion(kind=kind, seconds=seconds, times=times, side=side,
                   metres=_num(met.group(1)) if met else 0.0, degrees=float(deg.group(1)) if deg else 0.0)
        if kind == "orbit":
            at = re.search(r"\b(?:round|around|circling|orbiting)\b", low)
            after = _nouns(low[at.end():]) if at else []
            m.around = after[0] if after else ""
            m.noun = next((n for n in nouns if n != m.around), "")
            if "two" in low and "different speeds" in low:
                m.times = 1.0
        else:
            verb = dict(_KIND_RE)[kind].search(low)
            later = [n for n in _nouns(low[verb.end():]) if n in PARTS] if verb else []
            m.noun = (later[0] if later else next((n for n in nouns if n in PARTS), nouns[0] if nouns else ""))
            # "the empty spin so the moon orbits": the empty is what turns
            if "empty" in nouns and kind == "spin":
                m.noun = "empty"
        if kind == "color":
            m.colors = [c for c in re.findall(r"\b(" + "|".join(COLORS) + r")\b", low)][-2:]
        out.append(m)
    return out


def _name_words(name):
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[0-9]+", name)]


def _match(noun, objects, side="", plural=False):
    """Objects whose name carries one of the noun's words; parts first, the side when given."""
    if not noun:
        return []
    keys = NOUNS.get(noun, (noun,))
    hits = [o for o in objects if any(k in _name_words(o["name"]) for k in keys)]
    if noun == "empty":
        hits = [o for o in objects if o.get("type") == "EMPTY"] or hits
    if noun in ("camera",):
        hits = [o for o in objects if o.get("type") == "CAMERA"] or hits
    if noun in ("light", "spotlight", "lamp"):
        hits = [o for o in objects if o.get("type") == "LIGHT"] or hits
    if side:
        hits = [o for o in hits if side in _name_words(o["name"])] or hits
    return hits


def _top(objects, last):
    """The thing "it" means: the last built thing's root object, else the last object."""
    if last:
        root = [o for o in objects if o["name"] == last]
        if root:
            return root
    roots = [o for o in objects if not o.get("parent")]
    return roots[-1:] if roots else objects[-1:]


def _keys(obj, prop, values, frames, **extra):
    return [dict({"tool": "keyframe", "object": obj, "property": prop, "frame": f, "value": [round(x, 4) for x in v]}, **extra)
            for v, f in zip(values, frames)]


def _frames(seconds, steps):
    end = max(2, int(round(seconds * FPS)))
    return [1 + round(i * (end - 1) / steps) for i in range(steps + 1)], end


def motion_calls(m, objs, objects, index=0):
    """keyframe calls for one motion on the matched objects."""
    calls = []
    for k, o in enumerate(objs):
        name, loc, rot = o["name"], list(o.get("loc") or [0, 0, 0]), list(o.get("rot_deg") or [0, 0, 0])
        dims = o.get("dims") or [1, 1, 1]
        size = max(max(dims) if dims else 1.0, 0.5)
        if m.kind == "spin":
            turns = m.times if m.times > 1 or not m.degrees else m.degrees / 360.0
            if "fast" in str(m) and turns == 1:
                turns = 2
            fr, _ = _frames(m.seconds, 4)
            axis = 0 if m.noun in ("wheel",) else 2
            vals = []
            for i in range(5):
                r = list(rot); r[axis] += 360.0 * turns * i / 4; vals.append(r)
            calls += _keys(name, "rotation_deg", vals, fr, interpolation="LINEAR")
            if m.noun == "wheel":
                calls += _keys(name, "location", [loc, [loc[0] + 2 * math.pi * size / 2 * turns, loc[1], loc[2]]], [fr[0], fr[-1]],
                               interpolation="LINEAR")
        elif m.kind in ("rise", "move"):
            if m.kind == "rise":
                d = [0, 0, m.metres or max(1.0, size)]
            else:
                d = [m.metres or max(3.0, 2 * size), 0, 0]
                if re.search(r"\bleft\b", m.side or ""):
                    d[0] = -d[0]
            fr, _ = _frames(m.seconds, 1)
            calls += _keys(name, "location", [loc, [a + b for a, b in zip(loc, d)]], fr)
        elif m.kind == "bounce":
            n = max(1, int(m.times))
            fr, _ = _frames(m.seconds, 2 * n)
            h = m.metres or max(1.0, 1.5 * size)
            vals = [[loc[0], loc[1], loc[2] + (h if i % 2 else 0)] for i in range(2 * n + 1)]
            calls += _keys(name, "location", vals, fr)
        elif m.kind in ("grow", "shrink"):
            fr, _ = _frames(m.seconds, 1)
            a, b = ([0.05] * 3, [1.0] * 3) if m.kind == "grow" else ([1.0] * 3, [0.02] * 3)
            calls += _keys(name, "scale", [a, b], fr)
        elif m.kind == "swing":
            n = max(1, int(m.times)) * (2 if m.seconds >= 2 else 1)
            amp = m.degrees or {"door": 90.0, "chair": 12.0, "flag": 15.0, "metronome": 25.0, "arm": 35.0, "wing": 35.0,
                                "light": 30.0, "spotlight": 30.0, "pendulum": 30.0}.get(m.noun, 25.0)
            if m.noun == "door":     # opens once and stays open
                fr, _ = _frames(m.seconds, 1)
                r = list(rot); r[2] += amp
                calls += _keys(name, "rotation_deg", [rot, r], fr)
            elif m.noun == "pendulum":
                fr, _ = _frames(m.seconds, 2 * n)
                sway = 0.6 * max(size, 1.0)
                calls += _keys(name, "location", [[loc[0] + (sway if i % 2 else -sway) * (i > 0), loc[1], loc[2]]
                                                  for i in range(2 * n + 1)], fr)
            else:
                axis = 2 if m.noun in ("light", "spotlight") else 0 if m.noun in ("wing", "flag", "arm") else 1
                sign = -1 if (k % 2 and m.noun in ("wing", "wings")) else 1
                fr, _ = _frames(m.seconds, 2 * n)
                vals = []
                for i in range(2 * n + 1):
                    r = list(rot); r[axis] += sign * (0 if i == 0 else amp if i % 2 else -amp); vals.append(r)
                calls += _keys(name, "rotation_deg", vals, fr)
        elif m.kind == "orbit":
            centre = m._centre if hasattr(m, "_centre") else [0, 0, loc[2]]
            radius = max(math.dist(loc[:2], centre[:2]), 2.0 + size)
            turns = 1 + (k if m.times == 1 and len(objs) > 1 else 0)     # two moons: different speeds
            fr, _ = _frames(m.seconds, 8)
            start = math.atan2(loc[1] - centre[1], loc[0] - centre[0]) if math.dist(loc[:2], centre[:2]) > 0.01 else 0.0
            vals = [[centre[0] + radius * math.cos(start + 2 * math.pi * turns * i / 8),
                     centre[1] + radius * math.sin(start + 2 * math.pi * turns * i / 8), loc[2]] for i in range(9)]
            calls += _keys(name, "location", vals, fr, interpolation="LINEAR")
        elif m.kind == "pulse":
            n = max(1, int(m.times))
            fr, _ = _frames(m.seconds, 2 * n)
            for i, f in enumerate(fr):
                calls.append({"tool": "keyframe", "object": name, "property": "energy", "frame": f,
                              "amount": 1000.0 if i % 2 else 100.0})
        elif m.kind == "color":
            cols = [COLORS[c] for c in (m.colors or ["blue", "red"])]
            if len(cols) == 1:
                cols = [COLORS["white"], cols[0]]
            fr, _ = _frames(m.seconds, 1)
            for c, f in zip(cols, fr):
                calls.append({"tool": "keyframe", "object": name, "property": "color", "frame": f, "color": c})
    return calls


def plan_calls(motions, objects, last=None):
    """(calls, notes, missing) for the motions on the scene's objects."""
    calls, notes, missing, end = [], [], [], 0
    for i, m in enumerate(motions):
        objs = _match(m.noun, objects, m.side) if m.noun else _top(objects, last)
        if m.noun and not objs:
            missing.append(m.noun)
            continue
        if m.noun and m.kind not in ("orbit",) and m.noun not in ("blade", "blades", "wing", "wings", "sail", "sails", "fan",
                                                                   "windmill", "bird", "helicopter", "rotor", "moon"):
            # one thing moves unless the sentence names a set (blades, wings, sails, moons)
            roots = [o for o in objs if not o.get("parent")]
            objs = (roots or objs)[:1] if not m.side else objs[:1]
        if m.kind == "orbit":
            centre = _match(m.around, objects) if m.around else []
            if m.around and not centre:
                missing.append(m.around)
            m._centre = list((centre[0].get("loc") if centre else None) or [0, 0, 0])
            objs = [o for o in objs if not centre or o["name"] != centre[0]["name"]]
        calls += motion_calls(m, objs, objects, i)
        end = max(end, int(round(m.seconds * FPS)))
        notes.append(f"{m.kind} {', '.join(o['name'] for o in objs)} over {m.seconds:g} s")
    if calls:
        calls.append({"tool": "set_frame_end", "frame": max(end, 2)})
    return calls, notes, missing


def make_missing(nouns, objects):
    """Calls that add a plain thing for a noun the build did not make: a primitive, a camera or a point light."""
    calls, x = [], 0.0
    for noun in nouns:
        name = noun.capitalize()
        if noun == "camera":
            calls.append({"tool": "add_camera", "name": "Camera", "location": [8, -8, 5], "rotation_deg": [65, 0, 45]})
        elif noun in ("light", "lamp", "spotlight"):
            calls.append({"tool": "add_light", "kind": "SPOT" if noun == "spotlight" else "POINT", "name": "Light",
                          "location": [0, 0, 4], "energy": 500})
        elif noun in PRIMITIVES:
            size = 1.0 if noun not in ("planet",) else 2.0
            calls.append({"tool": "add_primitive", "shape": PRIMITIVES[noun], "name": name, "size": size,
                          "location": [x, 0, size / 2]})
            x += 3.0
    return calls
