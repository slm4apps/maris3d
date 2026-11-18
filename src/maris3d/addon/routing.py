# SPDX-License-Identifier: GPL-3.0-or-later
"""Does a request change what the scene already has? Pure functions (no bpy) so they are
testable outside Blender. The copilot uses the answer as its router: a change to something
that is there is never built as a new thing.
"""

_CHANGE_VERBS = ("make", "change", "turn", "move", "rotate", "scale", "resize", "rename",
                 "delete", "remove", "recolor", "recolour", "color", "colour", "bevel",
                 "extrude", "inset", "subdivide", "mirror", "join", "parent", "unparent",
                 "apply", "set", "give", "thicken", "smooth", "hide", "shade")

# "make the cube blue" refers to something already there; "make a mug" does not.
_REFERENCE_WORDS = ("the ", "this ", "that ", "it ", "its ", "selected ", "existing ")

# A request that starts like this is a fresh build even if it mentions an object.
_BUILD_STARTS = ("add ", "create ", "build ", "generate ", "make a ", "make an ",
                 "make me a ", "make me an ", "model ", "spawn ")


def looks_like_edit(prompt, has_objects):
    """True when the prompt changes an existing scene rather than building a new one."""
    p = (prompt or "").lower().strip()
    if not p or not has_objects:
        return False
    if p.startswith(_BUILD_STARTS):
        return False
    if any(p.startswith(v + " ") for v in _CHANGE_VERBS):
        return True
    return any(w in f" {p}" for w in _REFERENCE_WORDS) and any(v in p for v in _CHANGE_VERBS)


def resolve(prompt, has_objects):
    """'edit' when the prompt changes what the scene has, else 'build'."""
    return "edit" if looks_like_edit(prompt, has_objects) else "build"
