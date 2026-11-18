"""Every word a planner answer may use, in one place.

Three answers are read by code: the OUTLINE (which things, where), the PARTS of one thing, and a
CHANGE to things already built. Each answer has slots (a relation, a colour, a shape ...) and
each slot a closed list of words. The lists below are taken from the modules that turn the words
into numbers, so the vocabulary cannot drift from the code that reads it.

    words_in(role, answer)        -> [(slot, word), ...] every vocabulary word the answer uses
    unknown_words(role, answer)   -> [(slot, word), ...] words outside the lists (a model fault)
    score_per_word(pairs)         -> {(slot, word): {"gold": n, "hit": n, "pct": p}}

A slot whose value is free (a thing's name, a part name, a skin group) is not listed here.
"""
from . import apply_change as AC
from . import describe_parts as DP
from . import place as PLACE
from . import show as SHOW
from . import size_words as SW

import re

COMPASS = ("north", "south", "east", "west")
THING_ID = re.compile(r"^[a-z][a-z0-9_]*_\d+$")     # bench_1: a thing, not a vocabulary word

OUTLINE = {
    "kind": ("build", "question", "cannot"),
    "relation": PLACE.RELATIONS,
    "distance": PLACE.DISTANCES,
    "arrangement": ("row", "ring", "grid", "stack"),
    "size": tuple(DP.SIZE_WORDS),
    "material": ("black", "brass", "brick", "cream", "green", "metal", "navy", "oak", "pine", "red",
                 "rust", "snow", "teal", "terra", "timber", "walnut", "white"),
    "zone": ("bedroom", "courtyard", "dining", "garden", "hallway", "kitchen", "living", "platform",
             "plaza", "street_east", "street_west"),
    "facing": COMPASS,          # or the id of a thing in the same answer
}

PARTS = {
    "shape": DP.PARTS_SHAPES,
    "color": DP.PARTS_COLORS,
    "part_relation": tuple(DP.RELATIONS),     # a part on an earlier part (inside is only here)
    "align": tuple(sorted({w for axis in DP.STEPS for w in axis}
                          | {w for axis in DP.ALIGN_WORDS for w in axis})),
    "sunk": tuple(DP.SUNK),
    "axis": ("x", "y"),
    "finish": DP.FINISHES,
    "hollow": DP.HOLLOWS,
    "size_word": tuple(DP.SIZE_WORDS),
    # sizes in words (final format): a noun, "<multiplier> <noun>", or a ratio word
    "size_noun": tuple(SW.NOUNS),
    "size_multiplier": tuple(SW.MULTIPLIERS),
    "size_ratio": tuple(SW.RATIO),
}

CHANGE = {
    "kind": AC.KINDS,
    "do": AC.DOS,
    "color": DP.PARTS_COLORS,
    "finish": DP.FINISHES,
    "face": COMPASS,            # or the name of a thing in the scene
    "relation": PLACE.RELATIONS,
    "distance": PLACE.DISTANCES,
    "scale_axis": ("x", "y", "z"),
    "shift_axis": ("x", "y", "z"),
    # numbers in words (edit_words): a said factor is a ratio word; typed numbers are copied with these
    "times": tuple(SW.RATIO),
    "way": ("more", "less"),
    "unit": ("mm", "cm", "m"),
}

# the answer lines that talk in the scene (show.apply_lines); any answer may carry them
TALK = {
    "kind": ("talk",),
    "show_line": SHOW.LINES,
    "effect": SHOW.EFFECTS,
    "pose": SHOW.POSES,
}

VOCAB = {"outline": OUTLINE, "parts": PARTS, "change": CHANGE, "talk": TALK}
# staged (describe_parts.PARTS_SYSTEM_NEXT): the parts words the next training adds
PARTS_NEXT = dict(PARTS, shape=DP.PARTS_SHAPES + DP.NEXT_SHAPES,
                  tilt_toward=tuple(DP.LEAN), tilt_by=tuple(DP.TILTS),
                  copies_pattern=DP.PATTERNS, taper=DP.TAPERS)
VOCAB_NEXT = dict(VOCAB, parts=PARTS_NEXT)

# What the outline planner (v3.2) is told, byte for byte what its data was made with (the data
# builder imports this). "and" is the second thing of `between`.
COUNT_WORDS = "pair 2, couple 2, few 3, several 4, handful 5, half a dozen 6, dozen 12"
OUTLINE_SYSTEM = (
    "You are the planner for a Blender scene builder. Reply with one JSON object only: "
    '{"kind":"build"|"question"|"cannot","say":<one sentence, question or cannot only>,'
    '"items":[{"id":<thing>_<n>,"thing":<the noun as the user said it>,"count":<int>,"size":<word>,'
    '"material":<name>,"zone":<name>,"facing":<id or compass>,'
    '"place":{"anchor":<id or scene>,"and":<id, between only>,"relation":<word>,"distance":<word>,"arrangement":{"kind":<word>}}}]}. '
    "Relations: " + ", ".join(OUTLINE["relation"]) + ". "
    "Distances: " + ", ".join(OUTLINE["distance"]) + ". "
    "Arrangements: " + ", ".join(OUTLINE["arrangement"]) + ". "
    "Compass: anchor scene with north = behind, south = front_of, east = right_of, west = left_of; "
    "the middle of the scene = centre_of; facing takes a compass word too. "
    "Sizes: " + ", ".join(OUTLINE["size"]) + ". "
    "Count words: " + COUNT_WORDS + ". "
    "Materials: " + ", ".join(OUTLINE["material"]) + ". "
    "Zones: " + ", ".join(OUTLINE["zone"]) + ". "
    "Name every thing as the user said it, lowercase with underscores (bus station -> bus_station), "
    "even a thing you have never met; never swap it for another name. "
    "One item per thing asked for, in the order asked. Give a field only when the sentence states it. "
    "The anchor is the id of the thing the sentence places it by. "
    "A question or a thing you cannot do yet: kind question or cannot, one sentence in say, items []. "
    "Never output coordinates, numbers other than count, or part names."
)


def _place_words(place, out, align=False):
    if not isinstance(place, dict):
        return
    for slot in ("relation", "distance", "sunk"):
        if isinstance(place.get(slot), str):
            out.append(("part_relation" if align and slot == "relation" else slot, place[slot]))
    arr = place.get("arrangement")
    if isinstance(arr, dict) and isinstance(arr.get("kind"), str):
        out.append(("arrangement", arr["kind"]))
    if align and isinstance(place.get("align"), dict):
        out.extend(("align", w) for w in place["align"].values() if isinstance(w, str))


def _size_words(text, out):
    """'half door' -> size_multiplier half, size_noun door; 'half' alone -> size_ratio half."""
    if not isinstance(text, str):
        return
    words = text.split()
    if len(words) == 2:
        out.extend((("size_multiplier", words[0]), ("size_noun", words[1])))
    elif len(words) == 1:
        out.append(("size_noun" if words[0] in SW.NOUNS else "size_ratio", words[0]))


def _parts_words(parts, out):
    for p in parts if isinstance(parts, list) else ():
        if not isinstance(p, dict):
            continue
        for slot in ("shape", "color", "axis", "finish", "hollow"):
            if isinstance(p.get(slot), str):
                out.append((slot, p[slot]))
        for word in p.get("size") if isinstance(p.get("size"), list) else ():
            _size_words(word, out)
        if isinstance(p.get("copies"), dict) and isinstance(p["copies"].get("pattern"), str):
            out.append(("copies_pattern", p["copies"]["pattern"]))
        if isinstance(p.get("taper"), str):
            out.append(("taper", p["taper"]))
        tilt = p.get("tilt")
        if isinstance(tilt, dict):
            out.extend((f"tilt_{k}", tilt[k]) for k in ("toward", "by") if isinstance(tilt.get(k), str))
        _place_words(p.get("place"), out, align=True)


def words_in(role, answer):
    """Every (slot, word) of the closed lists that the answer uses, in order, repeats kept."""
    out = []
    if not isinstance(answer, dict):
        return out
    if role == "outline":
        if isinstance(answer.get("kind"), str):
            out.append(("kind", answer["kind"]))
        ids = {i.get("id") for i in answer.get("items") or () if isinstance(i, dict)}
        for item in answer.get("items") or ():
            if not isinstance(item, dict):
                continue
            for slot in ("size", "material", "zone"):
                if isinstance(item.get(slot), str):
                    out.append((slot, item[slot]))
            facing = item.get("facing")
            if isinstance(facing, str) and facing not in ids and not THING_ID.match(facing):
                out.append(("facing", item["facing"]))
            _place_words(item.get("place"), out)
    elif role == "parts":
        if isinstance(answer.get("size_word"), str):
            out.append(("size_word", answer["size_word"]))
        _size_words(answer.get("size"), out)
        if isinstance(answer.get("finish"), str):
            out.append(("finish", answer["finish"]))
        _parts_words(answer.get("parts"), out)
    elif role == "change":
        if isinstance(answer.get("kind"), str):
            out.append(("kind", answer["kind"]))
        for ch in answer.get("changes") or ():
            if not isinstance(ch, dict):
                continue
            for slot in ("do", "color", "finish"):
                if isinstance(ch.get(slot), str):
                    out.append((slot, ch[slot]))
            if isinstance(ch.get("face"), str) and ch["face"] in COMPASS:
                out.append(("face", ch["face"]))
            if ch.get("do") == "scale" and isinstance(ch.get("by"), dict):
                out.extend(("scale_axis", a) for a in ch["by"])
            if isinstance(ch.get("times"), str):
                out.append(("times", ch["times"]))
            if isinstance(ch.get("way"), str):
                out.append(("way", ch["way"]))
            if isinstance(ch.get("shift"), dict):
                out.extend(("shift_axis", a) for a in ch["shift"] if a in ("x", "y", "z"))
                if isinstance(ch["shift"].get("unit"), str):
                    out.append(("unit", ch["shift"]["unit"]))
            _place_words(ch.get("place"), out)
            _parts_words(ch.get("parts") if ch.get("do") == "add" else None, out)
    elif role == "talk":
        if answer.get("kind") == "talk":
            out.append(("kind", "talk"))
        for line in answer.get("show") or ():
            if not isinstance(line, dict):
                continue
            for slot, key in (("show_line", "line"), ("effect", "effect"), ("pose", "pose")):
                if isinstance(line.get(key), str):
                    out.append((slot, line[key]))
    else:
        raise ValueError(f"unknown role {role!r}")
    return out


def unknown_words(role, answer):
    """The (slot, word) pairs of the answer that are not in the role's lists."""
    lists = dict(VOCAB[role])
    if role == "change":            # parts added by do=add use the parts lists
        lists.update({k: v for k, v in PARTS.items() if k not in lists})
    return [(s, w) for s, w in words_in(role, answer) if s in lists and w not in lists[s]]


def score_per_word(pairs):
    """pairs: [(role, gold_answer, predicted_answer)]. A gold word counts as hit when the
    prediction uses the same word in the same slot at least as often (order is not checked)."""
    from collections import Counter
    table = {}
    for role, gold, pred in pairs:
        g, p = Counter(words_in(role, gold)), Counter(words_in(role, pred))
        for key, n in g.items():
            row = table.setdefault(key, {"gold": 0, "hit": 0})
            row["gold"] += n
            row["hit"] += min(n, p.get(key, 0))
    for row in table.values():
        row["pct"] = round(100.0 * row["hit"] / row["gold"], 1) if row["gold"] else 0.0
    return dict(sorted(table.items()))
