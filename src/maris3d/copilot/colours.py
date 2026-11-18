"""Colour words -> a material, for every model answer (one word language).

A model never writes colour numbers it worked out. It writes a colour as words:

    "color": "red"                                          a name from COLOURS
    "color": {"name": "teal", "shade": "dark", "see_through": "half",
              "look": "glossy", "gradient": {"to": "white", "direction": "up"}}
    "color": {"hex": "#3a7bd5"}  or  {"rgb": [58, 123, 213]}  only when the user typed those numbers

and `material(color)` turns it into the arguments of the `set_material` tool (code does the
numbers). `look` is the surface (matte, satin, glossy, metallic, glow); it is not `finish`, which
is the shape's smooth / sharp. An unknown word is a fault the caller reports, never guessed.

The 26 colours the shipped adapters were trained on keep their exact materials
(`describe_parts.PARTS_MATERIALS` and the library table); this module only adds to them.
"""
from . import describe_parts as DP


def _lin(h):
    """sRGB hex -> linear RGB, as Blender's Base Color wants it."""
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 4))
    return out


# name: (hex, extra material keys). Woods, stones and metals carry their surface.
_WOOD = {"roughness": 0.7}
_STONE = {"roughness": 0.85}
_METAL = {"roughness": 0.3, "metallic": 1.0}
_NEW = {
    # reds and pinks
    "crimson": ("#b0102a", {}), "maroon": ("#6e1423", {}), "burgundy": ("#7a1f2b", {}),
    "scarlet": ("#e0261b", {}), "ruby": ("#9b111e", {}), "cherry": ("#c2183c", {}),
    "wine": ("#5e1224", {}), "tomato": ("#e5452e", {}), "strawberry": ("#e23a4f", {}),
    "rose": ("#e8798f", {}), "hot_pink": ("#ff4fa3", {}), "magenta": ("#d6198a", {}),
    "fuchsia": ("#e534c8", {}), "blush": ("#efb5b9", {}), "salmon": ("#f08a72", {}),
    "coral": ("#f36f5a", {}),
    # purples
    "purple": ("#6c2a9e", {}), "violet": ("#8a4fd1", {}), "lavender": ("#b9a7e0", {}),
    "lilac": ("#c3a3d9", {}), "plum": ("#6b2d5c", {}), "mauve": ("#b07a9e", {}),
    "indigo": ("#3d2b8f", {}), "amethyst": ("#9061c2", {}), "periwinkle": ("#8e9ae6", {}),
    # blues
    "royal_blue": ("#2a4fd6", {}), "sky_blue": ("#7cc0ec", {}), "baby_blue": ("#a8d2f0", {}),
    "cobalt": ("#1f4aa8", {}), "azure": ("#2f86e0", {}), "sapphire": ("#14398c", {}),
    "denim": ("#3b5f8f", {}), "midnight": ("#141c3a", {}), "steel_blue": ("#4a7099", {}),
    "ice_blue": ("#cfe8f5", {}),
    # cyans and greens
    "cyan": ("#1fc8de", {}), "turquoise": ("#2cc7b4", {}), "aqua": ("#3fe0d0", {}),
    "seafoam": ("#8fd9c0", {}), "mint": ("#9ee6bd", {}), "jade": ("#2e9e6e", {}),
    "emerald": ("#16935a", {}), "forest_green": ("#215c2b", {}), "dark_green": ("#17401d", {}),
    "lime": ("#8fd62a", {}), "olive": ("#7a7a2a", {}), "moss": ("#5f7a33", {}),
    "sage": ("#9cae8c", {}), "pistachio": ("#a8c97f", {}), "grass": ("#4f9a2f", {}),
    "pine_green": ("#1f5a43", {}), "holly": ("#1e5c35", {}),
    # yellows and oranges
    "lemon": ("#f5e04a", {}), "mustard": ("#d1a22a", {}), "amber": ("#f0a019", {}),
    "honey": ("#d99a2b", {}), "ochre": ("#c7862a", {}), "peach": ("#f6b48c", {}),
    "apricot": ("#f4a46a", {}), "tangerine": ("#f5821f", {}), "pumpkin": ("#e06f1b", {}),
    "khaki": ("#c3b07a", {}), "wheat": ("#e6d1a1", {}), "champagne": ("#ecd9b4", {}),
    # browns and neutrals
    "beige": ("#d9c7a5", {}), "tan": ("#c49a6c", {}), "sand": ("#d6bd8e", {}),
    "ivory": ("#f4efdc", {}), "pearl": ("#ece6dc", {"roughness": 0.25}),
    "chocolate": ("#4e2c17", {}), "coffee": ("#5a3a25", {}), "mocha": ("#7a5844", {}),
    "caramel": ("#b06d2c", {}), "cinnamon": ("#9a5326", {}), "taupe": ("#8b7d70", {}),
    "charcoal": ("#2e3033", {}), "slate": ("#5a6470", {}), "ash": ("#b2b0aa", {}),
    "silver_grey": ("#a9adb3", {}), "light_grey": ("#cfd0d2", {}), "dark_grey": ("#3d3f42", {}),
    # woods
    "mahogany": ("#5c2318", _WOOD), "cherry_wood": ("#7a3b24", _WOOD), "birch": ("#e3cfa4", _WOOD),
    "maple": ("#d4a86c", _WOOD), "teak": ("#9a6a35", _WOOD), "ebony": ("#2a1e17", _WOOD),
    "bamboo": ("#d8c27a", _WOOD), "cork": ("#b8895a", _WOOD), "driftwood": ("#9c8f7d", _WOOD),
    # stones and building
    "marble": ("#ecebe6", {"roughness": 0.2}), "granite": ("#6e6a68", _STONE),
    "concrete": ("#9a9a96", {"roughness": 0.95}), "stone": ("#8a857c", _STONE),
    "sandstone": ("#c9a77c", _STONE), "slate_stone": ("#4c5157", _STONE),
    "clay": ("#b0603f", _STONE), "plaster": ("#e8e3d8", {"roughness": 0.9}),
    "cobble": ("#77726b", _STONE), "tarmac": ("#2f3032", {"roughness": 0.95}),
    # metals
    "gold": ("#e8b923", _METAL), "silver": ("#c9ccd1", _METAL), "copper": ("#c5733b", _METAL),
    "bronze": ("#a8692c", _METAL), "chrome": ("#e4e7ea", {"roughness": 0.05, "metallic": 1.0}),
    "steel": ("#8f969e", _METAL), "iron": ("#4f5257", {"roughness": 0.6, "metallic": 1.0}),
    "aluminium": ("#c4c8cc", {"roughness": 0.35, "metallic": 1.0}),
    "pewter": ("#8e9091", _METAL), "rose_gold": ("#d79a86", _METAL),
    # other materials
    "leather": ("#6b4226", {"roughness": 0.55}), "rubber": ("#1f1f1f", {"roughness": 0.95}),
    "ice": ("#d9eef7", {"roughness": 0.05, "alpha": 0.6}),
    "frosted_glass": ("#e6eef0", {"roughness": 0.45, "alpha": 0.5}),
    "porcelain": ("#f3f1ec", {"roughness": 0.15}), "felt": ("#7a2a2a", {"roughness": 1.0}),
    "wax": ("#efe3c4", {"roughness": 0.4}), "paper": ("#f2efe6", {"roughness": 0.95}),
    # festive
    "candy_red": ("#d8102e", {"roughness": 0.25}), "tinsel_gold": ("#f0c23a", {"roughness": 0.15, "metallic": 1.0}),
    "frost": ("#e9f3f8", {"roughness": 0.6}),
}

# every colour name, old first (their materials unchanged), then the new ones
COLOURS = {}
for _n in DP.PARTS_COLORS:
    COLOURS[_n] = dict(DP.PARTS_MATERIALS[_n]) if _n in DP.PARTS_MATERIALS else None
for _n, (_h, _extra) in _NEW.items():
    COLOURS[_n] = dict({"name": _n.replace("_", " ").title().replace(" ", ""), "color": _lin(_h),
                        "roughness": 0.6}, **_extra)
COLOUR_NAMES = tuple(COLOURS)

SHADES = ("light", "pale", "dark", "deep", "bright")
SEE_THROUGH = {"none": 1.0, "slight": 0.8, "half": 0.5, "mostly": 0.25, "clear": 0.1}
LOOKS = {"matte": {"roughness": 0.9}, "satin": {"roughness": 0.5}, "glossy": {"roughness": 0.12},
         "metallic": {"roughness": 0.3, "metallic": 1.0}, "glow": {"emission_strength": 3.0}}
DIRECTIONS = {"up": "z", "down": "-z", "right": "x", "left": "-x", "back": "y", "front": "-y"}
KEYS = ("name", "shade", "see_through", "look", "gradient", "hex", "rgb")


def _shade(rgb, word):
    """A shade word on a linear colour: light / pale mix toward white, dark / deep toward black,
    bright pushes it away from grey."""
    if word == "light":
        return [c + (1.0 - c) * 0.45 for c in rgb]
    if word == "pale":
        return [c + (1.0 - c) * 0.7 for c in rgb]
    if word == "dark":
        return [c * 0.3 for c in rgb]
    if word == "deep":
        m = sum(rgb) / 3.0
        return [max(0.0, (c - m) * 1.3 + m) * 0.55 for c in rgb]
    if word == "bright":
        m = sum(rgb) / 3.0
        return [min(1.0, max(0.0, (c - m) * 1.4 + m) * 1.25) for c in rgb]
    return list(rgb)


def _typed(color):
    """The colour of a hex or rgb the user typed, as linear RGB; None when it is not one."""
    if "hex" in color:
        h = str(color["hex"]).lstrip("#")
        if len(h) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in h):
            return _lin(h)
        return None
    v = color.get("rgb")
    if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
        scale = 255.0 if max(v) > 1 else 1.0
        return _lin("".join("%02x" % max(0, min(255, round(x / scale * 255))) for x in v))
    return None


def faults(color):
    """What is wrong with a colour answer, as short strings (empty = it can be built)."""
    if isinstance(color, str):
        return [] if color in COLOURS else [f"colour {color!r}"]
    if not isinstance(color, dict):
        return [f"colour {color!r}"]
    out = [f"colour key {k!r}" for k in color if k not in KEYS]
    if "hex" in color or "rgb" in color:
        if _typed(color) is None:
            out.append(f"colour numbers {color.get('hex', color.get('rgb'))!r}")
    elif color.get("name") not in COLOURS:
        out.append(f"colour {color.get('name')!r}")
    if "shade" in color and color["shade"] not in SHADES:
        out.append(f"shade {color['shade']!r}")
    if "see_through" in color and color["see_through"] not in SEE_THROUGH:
        out.append(f"see_through {color['see_through']!r}")
    if "look" in color and color["look"] not in LOOKS:
        out.append(f"look {color['look']!r}")
    g = color.get("gradient")
    if g is not None:
        if not isinstance(g, dict) or set(g) - {"to", "direction"}:
            out.append(f"gradient {g!r}")
        else:
            if g.get("to") not in COLOURS:
                out.append(f"gradient to {g.get('to')!r}")
            if g.get("direction", "up") not in DIRECTIONS:
                out.append(f"gradient direction {g.get('direction')!r}")
    return out


def _base(name):
    m = COLOURS[name]
    if m is None:                      # an old colour the library table gives (oak, brass, ...)
        from . import recipes
        m = recipes.MATERIALS.get(name) or {"name": name.title(), "color": [0.8, 0.8, 0.8]}
    return dict(m)


def material(color):
    """The `set_material` arguments (no object) for a colour answer; ValueError on a fault."""
    bad = faults(color)
    if bad:
        raise ValueError("; ".join(bad))
    if isinstance(color, str):
        return _base(color)
    typed = _typed(color) if ("hex" in color or "rgb" in color) else None
    if typed is not None:
        mat = {"name": "Typed", "color": typed, "roughness": 0.6}
    else:
        mat = _base(color["name"])
    if color.get("shade"):
        mat["color"] = [round(c, 4) for c in _shade(mat["color"], color["shade"])]
        mat["name"] = f"{mat['name']}{color['shade'].title()}"
    if color.get("look"):
        mat.update(LOOKS[color["look"]])
        if color["look"] == "glow":
            mat["emission_color"] = list(mat["color"][:3])
    see = color.get("see_through")
    if see and see != "none":
        mat["alpha"] = SEE_THROUGH[see]
    g = color.get("gradient")
    if g:
        mat["gradient_color"] = list(_base(g["to"])["color"][:3])
        mat["gradient_axis"] = DIRECTIONS[g.get("direction", "up")]
    return mat


def words_of(color):
    """[(slot, word)] of a colour answer, for the vocabulary check and per-word scores."""
    if isinstance(color, str):
        return [("color", color)]
    if not isinstance(color, dict):
        return []
    out = []
    if "name" in color:
        out.append(("color", color["name"]))
    for slot in ("shade", "see_through", "look"):
        if slot in color:
            out.append((slot, color[slot]))
    g = color.get("gradient")
    if isinstance(g, dict):
        if "to" in g:
            out.append(("color", g["to"]))
        out.append(("gradient_direction", g.get("direction", "up")))
    return out
