# SPDX-License-Identifier: GPL-3.0-or-later
"""The final one-line confirmation, built from the real scene diff — never from the model's words."""
_CAP = 6


def built_line(result):
    """What a compiled plan did, in one clause: how many parts the model made exactly and how many
    the harness corrected or made itself, then the notes (a design that could not be built, a
    place nobody stated). "" for a request that was not a compiled plan."""
    finished = getattr(result, "finished", None)
    if finished:
        said = "; ".join(f"{o['do']}: {', '.join(o['on'][:4])}" + (f" +{len(o['on']) - 4} more" if len(o["on"]) > 4 else "")
                         for o in finished.get("orders") or [])
        return said + (" — " + "; ".join(finished["notes"][:2]) if finished.get("notes") else "")
    built = getattr(result, "built", None)
    if not built:
        return ""
    # who made each thing: a library recipe is never reported as the model's work
    line = f"{built.get('exact', 0)} of {built.get('parts', 0)} parts exact"
    if built.get("designed"):
        line += f"; designed by the model: {_names(built['designed'])}"
    if built.get("library"):
        line += f"; from the library: {_names(built['library'])}"
    if built.get("moved"):
        line += f", {built['moved']} corrected"
    if built.get("missing"):
        line += f", {built['missing']} made by the copilot"
    if built.get("unfixed"):
        line += f", {built['unfixed']} still wrong"
    if built.get("strays"):
        line += f", {len(built['strays'])} not asked for"
    notes = [str(n) for n in built.get("notes") or []]
    if notes:
        line += " — " + "; ".join(notes[:2])
    return line


def _names(names):
    return ", ".join(names[:_CAP]) + (f" +{len(names) - _CAP} more" if len(names) > _CAP else "")


def scene_diff(before, after, result=None):
    """before/after: executor.objects() snapshots. One honest sentence about what changed."""
    b = {o["name"]: o for o in before}
    a = {o["name"]: o for o in after}
    added = [n for n in a if n not in b]
    removed = [n for n in b if n not in a]
    mats = sorted({m for o in after for m in o.get("mats", [])} - {m for o in before for m in o.get("mats", [])})
    moved = [n for n in a if n in b and _differs(b[n].get("loc"), a[n].get("loc"))]
    resized = [n for n in a if n in b and _differs(b[n].get("dims"), a[n].get("dims"))]
    recoloured = [n for n in a if n in b and b[n].get("mats") != a[n].get("mats")] if not mats else []
    parts = []
    if added:
        names = ", ".join(added[:_CAP]) + (f" +{len(added) - _CAP} more" if len(added) > _CAP else "")
        parts.append(f"Added {len(added)} object{'s' if len(added) > 1 else ''}: {names}")
    if removed:
        parts.append(f"Removed {len(removed)}: {', '.join(removed[:_CAP])}")
    if mats:
        parts.append(f"{len(mats)} material{'s' if len(mats) > 1 else ''}: {', '.join(mats[:_CAP])}")
    for word, names in (("Moved", moved), ("Resized", resized), ("Recoloured", recoloured)):
        if names:
            parts.append(f"{word} {len(names)}: " + ", ".join(names[:_CAP])
                         + (f" +{len(names) - _CAP} more" if len(names) > _CAP else ""))
    if not parts:
        if result is not None and getattr(result, "errors", None):
            return "Nothing changed — a tool call failed: " + result.errors[0].get("error", "")[:80]
        return "Nothing changed in the scene."
    line = parts[0]
    for p in parts[1:]:
        line += " — " + p
    return line


def _differs(x, y, tol=1e-3):
    """Two [x, y, z] snapshots differ by more than rounding (None on either side: no claim)."""
    if not x or not y or len(x) != len(y):
        return False
    return any(abs(float(p) - float(q)) > tol for p, q in zip(x, y))
