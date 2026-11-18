# SPDX-License-Identifier: Apache-2.0
"""Scene checklist and edit guard for the copilot (extra, not imported by the base install).

Works on the executor's object list: [{name, type, loc, dims, material}]. Geometry checks use the axis-aligned box
loc +- dims/2, so they need objects with `dims` (the live add-on reports it). Use as Copilot(checker=make_checker(list)).
"""

REQUIRED = {"presence": ("name",), "count": ("min", "max"), "size": ("name", "axis", "min", "max"),
            "position": ("name", "axis", "value"), "relation": ("relation", "object", "target"),
            "no_overlap": (), "resting": ("object",)}
_AXIS = {"x": 0, "y": 1, "z": 2}


def _box(o):
    loc, dims = o.get("loc", [0, 0, 0]), o.get("dims", [0, 0, 0])
    return [l - d / 2 for l, d in zip(loc, dims)], [l + d / 2 for l, d in zip(loc, dims)]


def _footprint(a, b, tol):
    return all(a[0][i] <= b[1][i] + tol and b[0][i] <= a[1][i] + tol for i in (0, 1))


def evaluate(objects, checklist):
    """Failure strings for a checklist (empty list = all hold)."""
    fails, by_name = [], {o.get("name"): o for o in objects}
    for c in checklist:
        if not isinstance(c, dict):
            fails.append("checklist item must be an object")
            continue
        kind = c.get("type")
        missing = [f for f in REQUIRED.get(kind, ()) if f not in c]
        if missing:
            fails.append(f"{kind} check missing required fields: {', '.join(missing)}")
            continue
        tol = c.get("tolerance", 0.05)
        if kind == "presence":
            want = c.get("object_type")
            if not any(o.get("name") == c["name"] and (want is None or o.get("type") == want) for o in objects):
                fails.append(f'{c["name"]} missing' + (f" ({want})" if want else ""))
        elif kind == "count":
            want = c.get("object_type")
            n = sum(1 for o in objects if want is None or o.get("type") == want)
            if not c["min"] <= n <= c["max"]:
                fails.append(f'{want or "object"} count {n}, expected {c["min"]}..{c["max"]:g}')
        elif kind in ("size", "position"):
            o = by_name.get(c["name"])
            if o is None:
                fails.append(f'{c["name"]} missing')
            elif kind == "size":
                v = o.get("dims", [0, 0, 0])[_AXIS[c["axis"]]]
                if not c["min"] <= v <= c["max"]:
                    fails.append(f'{c["name"]} {c["axis"]} size {v:g}, expected {c["min"]:g}..{c["max"]:g}')
            else:
                v = o.get("loc", [0, 0, 0])[_AXIS[c["axis"]]]
                if abs(v - c["value"]) > tol:
                    fails.append(f'{c["name"]} {c["axis"]} position {v:g}, expected {c["value"]} +- {tol:g}')
        elif kind == "relation":
            a, b = by_name.get(c["object"]), by_name.get(c["target"])
            if a is None or b is None:
                fails.append(f'{c["object"]} or {c["target"]} missing for {c["relation"]} relation')
                continue
            (a0, a1), (b0, b1) = _box(a), _box(b)
            rel = c["relation"]
            if rel == "on":
                gap = a0[2] - b1[2]
                if abs(gap) > tol or not _footprint((a0, a1), (b0, b1), tol):
                    fails.append(f'{c["object"]} not on {c["target"]}: vertical gap {gap:g}')
            elif rel == "beside":
                hgap = max(max(b0[i] - a1[i], a0[i] - b1[i]) for i in (0, 1))
                if not (a0[2] <= b1[2] + tol and b0[2] <= a1[2] + tol) or hgap > tol:
                    fails.append(f'{c["object"]} not beside {c["target"]}: horizontal gap {hgap:g}')
            elif rel == "inside":
                if not all(a0[i] >= b0[i] - tol and a1[i] <= b1[i] + tol for i in range(3)):
                    fails.append(f'{c["object"]} not inside {c["target"]}')
            else:
                fails.append(f"unsupported relation {rel}")
        elif kind == "no_overlap":
            names = set(c.get("objects", []))
            pool = [o for o in objects if o.get("type") == "MESH" and (not names or o.get("name") in names)]
            for i, a in enumerate(pool):
                for b in pool[i + 1:]:
                    (a0, a1), (b0, b1) = _box(a), _box(b)
                    depth = min(min(a1[k], b1[k]) - max(a0[k], b0[k]) for k in range(3))
                    if depth > tol:
                        fails.append(f'overlap {a["name"]} with {b["name"]} (depth {depth:g})')
        elif kind == "resting":
            o = by_name.get(c["object"])
            if o is None:
                fails.append(f'{c["object"]} missing for resting check')
                continue
            support = c.get("support", "floor")
            a0, a1 = _box(o)
            if support == "floor":
                gap = a0[2]
            else:
                s = by_name.get(support)
                if s is None:
                    fails.append(f"support {support} missing for {c['object']}")
                    continue
                b0, b1 = _box(s)
                if not _footprint((a0, a1), (b0, b1), tol):
                    fails.append(f'{c["object"]} does not overlap support {support}')
                    continue
                gap = a0[2] - b1[2]
            if abs(gap) > tol:
                fails.append(f'{c["object"]} not resting on {support}: vertical gap {gap:g}')
        else:
            fails.append(f"unsupported checklist type {kind}")
    return fails


def unchanged_failures(before, after, allowed=None, tol=1e-3):
    """Edit guard: objects not named in `allowed` ({name: [fields]}, fields in loc/dims/material/type, or
    __created__/__deleted__) must be identical before and after."""
    allowed = {k: set(v) for k, v in (allowed or {}).items()}
    b, a = {o["name"]: o for o in before}, {o["name"]: o for o in after}
    fails = []
    for name in sorted(b.keys() | a.keys()):
        ok = allowed.get(name, set())
        if name not in b:
            if "__created__" not in ok:
                fails.append(f"unexpected object added: {name}")
        elif name not in a:
            if "__deleted__" not in ok:
                fails.append(f"unexpected object removed: {name}")
        else:
            for field in ("type", "loc", "dims", "material"):
                x, y = b[name].get(field), a[name].get(field)
                same = (all(abs(p - q) <= tol for p, q in zip(x, y)) and len(x) == len(y)) if isinstance(x, list) and isinstance(y, list) else x == y
                if not same and field not in ok:
                    fails.append(f"{name} changed unexpected field {field}")
    return fails


def make_checker(checklist):
    """Checker for Copilot(checker=...): fn(objects) -> failure strings."""
    return lambda objects: evaluate(objects, checklist)
