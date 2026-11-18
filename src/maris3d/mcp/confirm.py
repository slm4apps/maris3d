# SPDX-License-Identifier: Apache-2.0
"""Plain-language confirmation of what a Blender build did, like an assistant after a tool call.

Pure standard library, no bpy, no model: a deterministic template over facts (the executed calls, the per-call results, the
check result and a before/after scene snapshot). The MCP tool (blender_mcp.tool_build), the OpenCode bridge (slm_bridge.py) and a
future Blender add-on all call confirmation() so they return the SAME sentence(s). No code, JSON or stack trace ever goes in it.

A scene snapshot is a list of objects: {"name", "type", "loc": [x,y,z], "scale": [x,y,z], "color": [r,g,b] or None}
(blender_mcp.scene_facts() produces it; missing keys are tolerated and just not compared).
"""
import re

COLOURS = {"red": (0.8, 0.05, 0.05), "orange": (0.9, 0.4, 0.05), "yellow": (0.9, 0.85, 0.1), "green": (0.1, 0.6, 0.1),
           "blue": (0.1, 0.2, 0.8), "purple": (0.5, 0.1, 0.7), "pink": (0.9, 0.5, 0.65), "brown": (0.4, 0.22, 0.1),
           "white": (0.95, 0.95, 0.95), "grey": (0.5, 0.5, 0.5), "black": (0.03, 0.03, 0.03)}
EPS = 1e-3


def colour_name(rgb):
    if not rgb:
        return None
    return min(COLOURS, key=lambda n: sum((a - b) ** 2 for a, b in zip(rgb[:3], COLOURS[n])))


def noun(name):
    """Object name -> plain noun: 'Wall_Front.001' -> 'wall front', 'Cube' -> 'cube'."""
    base = re.sub(r"[._ ]?\d+$", "", name or "object")
    return re.sub(r"[_.]+", " ", base).strip().lower() or "object"


def plural(n, word):
    if n == 1:
        return ("an " if word[:1] in "aeiou" else "a ") + word
    return f"{n} {word}" + ("" if word.endswith("s") else "s")


def _units(delta):
    dx, dy, dz = delta
    axis = max(range(3), key=lambda i: abs(delta[i]))
    d = delta[axis]
    word = [("right", "left"), ("back", "forward"), ("up", "down")][axis][0 if d > 0 else 1]
    return f"{abs(d):.1f} unit{'' if abs(round(abs(d), 1) - 1) < 1e-9 else 's'} {word}"


def _near(a, b):
    return a is not None and b is not None and all(abs(x - y) <= EPS for x, y in zip(a, b))


def diff(before, after):
    """Facts only: what was added / removed / moved / scaled / recoloured between two snapshots."""
    b, a = {o["name"]: o for o in before or []}, {o["name"]: o for o in after or []}
    d = {"added": [a[n] for n in a if n not in b], "removed": [b[n] for n in b if n not in a], "moved": [], "scaled": [], "recoloured": []}
    for n in a:
        if n not in b:
            continue
        o, p = b[n], a[n]
        if o.get("loc") and p.get("loc") and not _near(o["loc"], p["loc"]):
            d["moved"].append((n, [q - r for q, r in zip(p["loc"], o["loc"])]))
        if o.get("scale") and p.get("scale") and not _near(o["scale"], p["scale"]):
            d["scaled"].append((n, p["scale"]))
        if o.get("color") and p.get("color") and colour_name(o["color"]) != colour_name(p["color"]):
            d["recoloured"].append((n, colour_name(p["color"])))
    return d


def groups(objs, limit=5):
    """'3 walls, a roof, a door' from object names, most frequent first."""
    cnt = {}
    for o in objs:
        cnt[noun(o["name"])] = cnt.get(noun(o["name"]), 0) + 1
    items = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    text = ", ".join(plural(n, w) for w, n in items[:limit])
    return text + (f" and {sum(n for _, n in items[limit:])} more" if len(items) > limit else "")


def failure_reason(calls, per_call, check):
    """One short reason a build could not be accepted, or None."""
    if not calls:
        return "the model returned no usable tool calls"
    bad = [p for p in per_call if not p.get("ok")]
    for p in bad:
        if str(p.get("error", "")).startswith("compile:"):
            return f"the output had an invalid call to {p.get('tool')}"
    if bad and len(bad) == len(per_call):
        return f"every call failed in Blender (first: {bad[0].get('tool')}: {str(bad[0].get('error'))[:80]})"
    if check and not check.get("passed"):
        return "the check failed: " + ("; ".join(check.get("fails") or [])[:160] or "the scene does not match the request")
    return None


def confirmation(label, before, after, calls=(), per_call=(), check=None, tries=1, earlier_fails=()):
    """1 to 3 plain sentences. label: model name for the failure wording. tries: how many attempts were made in total.
    earlier_fails: reasons of the failed earlier attempts (retries)."""
    d = diff(before, after)
    changed = any(d[k] for k in d)
    reason = failure_reason(calls, per_call, check)
    out = []
    if reason:
        out.append(f"I could not build it: {reason}.")
        if changed and calls:
            objs = d["added"] or after or []
            out.append(f"The Blender window shows what the last try produced ({plural(len(objs), 'object')}), which does not meet the request.")
        elif not changed:
            out.append("The scene was not changed.")
    elif not changed:
        out.append("Nothing changed in the scene: the model's calls did not add, remove or alter anything.")
    else:
        parts = []
        add = d["added"]
        if len(add) >= 4 or (add and not before and len(add) >= 2):
            head = f"Built {len(add)} objects ({groups(add)})"
        else:
            if len(add) == 1:
                o = add[0]
                where = ""
                if o.get("loc"):
                    where = " at the origin" if all(abs(v) <= 0.05 for v in o["loc"]) else " at (" + ", ".join(f"{v:.1f}" for v in o["loc"]) + ")"
                parts.append(f"added {plural(1, noun(o['name']))}{where}")
            elif add:
                parts.append("added " + groups(add))
            for n, delta in d["moved"][:2]:
                parts.append(f"moved the {noun(n)} {_units(delta)}")
            for n, col in d["recoloured"][:2]:
                parts.append(f"changed the {noun(n)} colour to {col}")
            for n, _ in d["scaled"][:2]:
                parts.append(f"rescaled the {noun(n)}")
            if d["removed"]:
                parts.append("removed " + groups(d["removed"]))
            head = ("Done: " if add or len(parts) > 1 else "") + " and ".join([", ".join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts)
            if not add and len(parts) <= 2:
                head = head[:1].upper() + head[1:] + "; nothing else changed"
        tail = "."
        if check and check.get("passed"):  # a generic check only needs some meshes: say so, it cannot judge the shape
            tail = ("; the basic check passed (it only needs some mesh objects and cannot tell whether the shape is right)." if check.get("generic")
                    else "; check passed.")
        out.append(head + tail)
        extra = sum(len(d[k]) for k in ("moved", "scaled", "recoloured", "removed"))
        if len(add) >= 4 and extra:
            out.append(f"It also changed {extra} existing object{'s' if extra != 1 else ''}.")
    bad = [p for p in per_call if not p.get("ok")]
    if bad and not reason:
        out.append(f"{len(bad)} of {len(per_call)} calls errored and were skipped (first: {bad[0].get('tool')}).")
    if tries > 1:
        fails = "; ".join(dict.fromkeys(str(f)[:80] for f in earlier_fails))
        out.append(f"I tried {tries} times" + (f" (earlier tries: {fails})" if fails else "") + ".")
    return " ".join(out[:3])


def with_screenshot(text, path):
    """Append the screenshot on its own last line as a markdown image (absolute path)."""
    return text if not path else f"{text}\n\nScreenshot: {path} ![Blender scene]({path})"
