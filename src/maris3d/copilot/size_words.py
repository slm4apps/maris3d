# SPDX-License-Identifier: Apache-2.0
"""Sizes in words.

A model never writes a size in metres. It writes words, and this module turns them into metres:

  - a SIZE NOUN is an everyday thing on a ladder of doublings, from a hair to a tower (NOUNS);
  - a MULTIPLIER in front of a noun ("half door", "one_and_half chair") multiplies it: the model picks
    two words, code multiplies;
  - a RATIO word alone ("half", "same", "double", "tenth") is a share of something else: for a part,
    of the part it is placed on along the same axis; for the first part, of the object's size.

An object answer carries `"size": "<multiplier> <noun>"` or `"<noun>"` (its typical largest side), and
each part `"size": [x, y, z]` with one word per axis. A number where a word is expected is refused.

    noun_metres("half door")                 -> 0.95
    to_metres(answer)                        -> (answer with sizes in metres, faults)
    to_words(parts, object_m)                -> parts with word sizes (data making and tests only)
"""
import math

# the ladder: each step doubles; the names are things everyone can picture
NOUNS = {"hair": 0.00012, "salt_grain": 0.00023, "sand_grain": 0.00047, "poppy_seed": 0.00094,
         "pinhead": 0.0019, "ant": 0.0037, "pea": 0.0075, "dice": 0.015, "coin": 0.03, "egg": 0.06,
         "cup": 0.12, "shoebox": 0.24, "bucket": 0.48, "chair": 0.96, "door": 1.9, "car": 3.8,
         "room": 7.7, "house": 15.4, "tower": 30.7}

# a size as a share of another size
RATIO = {"sliver": 0.05, "tenth": 0.1, "eighth": 0.125, "sixth": 0.167, "fifth": 0.2, "quarter": 0.25,
         "third": 0.333, "two_fifths": 0.4, "half": 0.5, "three_fifths": 0.6, "two_thirds": 0.667,
         "three_quarters": 0.75, "most": 0.875, "same": 1.0, "a_bit_more": 1.25, "one_and_half": 1.5,
         "double": 2.0, "two_and_half": 2.5, "triple": 3.0, "four_times": 4.0, "five_times": 5.0,
         "seven_times": 7.0, "ten_times": 10.0, "fifteen_times": 15.0, "twenty_times": 20.0}

# in front of a noun, only the fine steps between two nouns are needed (the next noun is double)
MULTIPLIERS = {w: v for w, v in RATIO.items() if 0.5 <= v <= 1.5}


def noun_metres(text):
    """'door', 'half door', 'one_and_half chair' -> metres; None when the words are not on the lists."""
    if not isinstance(text, str):
        return None
    words = text.strip().lower().split()
    if len(words) == 1 and words[0] in NOUNS:
        return NOUNS[words[0]]
    if len(words) == 2 and words[0] in MULTIPLIERS and words[1] in NOUNS:
        return round(MULTIPLIERS[words[0]] * NOUNS[words[1]], 6)
    return None


def uses_words(answer):
    """True when the answer's sizes are words (the final format), False for the old metres format."""
    if not isinstance(answer, dict):
        return False
    if isinstance(answer.get("size"), str):
        return True
    return any(isinstance(p, dict) and isinstance(p.get("size"), list) and any(isinstance(v, str) for v in p["size"])
               for p in answer.get("parts") or ())


def _axis(word, base):
    """One axis word -> metres, or None. `base` is what a ratio word is a share of (None: no ratio allowed)."""
    if not isinstance(word, str):
        return None
    if word in RATIO:
        return None if base is None else round(RATIO[word] * base, 6)
    return noun_metres(word)


def to_metres(answer, known=None):
    """(the answer with every size in metres, faults). `known` = {part name: [x, y, z] metres} of parts
    that already exist (an edit that adds parts to a built thing). The object's own size word is
    removed from the copy: it is what the first part's ratio words are a share of."""
    if not isinstance(answer, dict) or not isinstance(answer.get("parts"), list):
        return answer, ["no parts"]
    faults = []
    whole = None
    if "size" in answer:
        whole = noun_metres(answer["size"])
        if whole is None:
            faults.append(f"size {answer['size']!r} is not a size noun")
    sizes = dict(known or {})
    parts = []
    for k, p in enumerate(answer["parts"]):
        if not isinstance(p, dict):
            return answer, ["a part is not an object"]
        raw = p.get("size")
        if not (isinstance(raw, list) and len(raw) == 3):
            faults.append(f"{p.get('name')}: size is not three words")
            parts.append(p)
            continue
        on = (p.get("place") or {}).get("on") if isinstance(p.get("place"), dict) else None
        anchor = sizes.get(on)
        out = []
        for i, word in enumerate(raw):
            if isinstance(word, (int, float)) and not isinstance(word, bool):
                faults.append(f"{p.get('name')}: a number {word!r} where a size word goes")
                out.append(None)
                continue
            base = anchor[i] if anchor else (whole if k == 0 or on is None else None)
            m = _axis(word, base)
            if m is None:
                faults.append(f"{p.get('name')}: size word {word!r}"
                              + ("" if word in NOUNS or word in RATIO or noun_metres(word) else " is not on the lists"))
            out.append(m)
        q = dict(p)
        if all(v is not None and v > 0 for v in out):
            q["size"] = out
            if p.get("name"):
                sizes[p["name"]] = out
        parts.append(q)
    copy = {key: v for key, v in answer.items() if key != "size"}
    copy["parts"] = parts
    return copy, faults


def _nearest(table, v):
    v = max(float(v), 1e-6)
    return min(table, key=lambda w: abs(math.log(table[w] / v)))


def object_word(metres):
    """The '<multiplier> <noun>' (or bare noun) nearest to a largest side in metres."""
    best = min(((m, n) for m in MULTIPLIERS for n in NOUNS),
               key=lambda mn: abs(math.log(MULTIPLIERS[mn[0]] * NOUNS[mn[1]] / max(metres, 1e-6))))
    return best[1] if best[0] == "same" else f"{best[0]} {best[1]}"


def to_words(parts, object_m):
    """Parts in metres -> the same parts with word sizes, each axis the closer of a ratio word (against
    its anchor, the first part against `object_m` snapped to its word) and a '<multiplier> <noun>'.
    Every choice is made against the size AS REBUILT from the words before it, so errors do not add up.
    For data making and tests; the product only reads words (to_metres)."""
    whole = noun_metres(object_word(object_m))
    rebuilt, out = {}, []
    for k, p in enumerate(parts):
        on = (p.get("place") or {}).get("on")
        anchor = rebuilt.get(on) if on else None
        words, sizes = [], []
        for i in range(3):
            want = max(float(p["size"][i]), 1e-6)
            base = anchor[i] if anchor else (whole if k == 0 else None)
            noun = object_word(want)
            choices = [(noun, noun_metres(noun))]
            if base:
                r = _nearest(RATIO, want / base)
                choices.insert(0, (r, RATIO[r] * base))       # ratio first: wins a tie
            w, m = min(choices, key=lambda c: abs(math.log(c[1] / want)))
            words.append(w)
            sizes.append(m)
        rebuilt[p["name"]] = sizes
        out.append(dict(p, size=words))
    return out
