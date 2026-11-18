# SPDX-License-Identifier: Apache-2.0
"""Recipe library: loads data/recipes.json once and answers lookups without a model or network.

A recipe is plain data: id, name, aliases, prompt, calls (tool-call args in the S2 format
that harness/tools.py compiles), parts (named objects), order (build order, a permutation
of parts), relations (type on_top_of | next_to | centered_on, part, ref) and checks (one per
part: present, and position_near when the part has a known location).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "recipes.json"
STOP = {"a", "an", "the", "of", "with", "and", "or", "from", "some", "make", "build", "add", "me",
        "simple", "shapes", "shape", "my", "to", "for", "in", "on", "one", "it", "is", "please",
        "give", "put", "create", "new", "small", "little", "big", "model", "scene"}


def _tokens(text):
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in STOP:
            continue
        if len(w) > 3 and w.endswith("es") and w[:-2] + "e" != w and w[-3] in "sxz":
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _phrase(text):
    return " ".join(_tokens(text))


@lru_cache(maxsize=1)
def load():
    """Return the recipe list and a normalised index, read once per process."""
    recipes = json.loads(DATA.read_text(encoding="utf-8"))
    index = []
    for r in recipes:
        names = [r["name"]] + list(r.get("aliases", []))
        index.append({
            "recipe": r,
            "phrases": {_phrase(n) for n in names},
            "name_tokens": set(_tokens(" ".join(names))),
            "prompt_tokens": set(_tokens(r.get("prompt", ""))),
        })
    return recipes, index


def all_recipes():
    return load()[0]


def get(recipe_id):
    for r in all_recipes():
        if r["id"] == recipe_id:
            return r
    return None


def plan_name(raw):
    """One recipe part name in the planner schema: lowercase, digits, underscore, leading letter."""
    name = re.sub(r"[^a-z0-9_]+", "_", str(raw).lower()).strip("_") or "object"
    if name[0].isdigit():
        name = "p_" + name
    return name[:24]


def plan_from_recipe(recipe):
    """A planner-interface plan dict from one S2-format recipe, or None when it cannot convert.

    Normalizes part names to the planner schema, maps relation ``type`` to ``rel``,
    and orders refs before their parts (stable topological sort: the recipe order is
    kept except where a relation forces a ref earlier). The result always passes
    ``planner.validate.check``; over-cap, duplicate-after-normalize and cyclic
    recipes convert to None, never to a bad plan.
    """
    from ..planner import plan as P
    from ..planner import validate

    parts = list(recipe.get("parts", []))
    if len(parts) > P.MAX_PARTS:
        return None
    names = [plan_name(p) for p in parts]
    if len(set(names)) != len(names):
        return None
    index = {n: i for i, n in enumerate(names)}
    relations = []
    for rel in recipe.get("relations", []):
        part, ref = plan_name(rel.get("part", "")), plan_name(rel.get("ref", ""))
        if part not in index or ref not in index or rel.get("type") not in P.REL_KINDS:
            return None
        relations.append({"part": part, "rel": rel["type"], "ref": ref})
    # Stable Kahn sort: a ref is always built before the part placed relative to it.
    deps = {n: set() for n in names}
    for rel in relations:
        deps[rel["part"]].add(rel["ref"])
    order = []
    ready = sorted([n for n in names if not deps[n]], key=index.__getitem__)
    while ready:
        node = ready.pop(0)
        order.append(node)
        for other in names:
            if node in deps[other]:
                deps[other].discard(node)
                if not deps[other] and other not in order and other not in ready:
                    ready.append(other)
        ready.sort(key=index.__getitem__)
    if len(order) != len(names):
        return None  # relation cycle
    plan = {"parts": names, "order": order, "relations": relations,
            "checks": {n: {"count_min": 1, "bbox_nonzero": True} for n in names}}
    ok, _ = validate.check(plan)
    return plan if ok else None


def lookup_plan(query, limit=5):
    """First convertible recipe plan for a request, or None. The recipe_lookup for source.resolve."""
    for recipe in find(query, limit=limit):
        plan = plan_from_recipe(recipe)
        if plan is not None:
            return plan
    return None


def find(query, limit=5):
    """Recipes matching an object name or a request. Exact name or alias wins, then phrase
    containment, then token overlap (names and aliases count more than the prompt text)."""
    q_phrase = _phrase(query or "")
    q_tokens = set(_tokens(query or ""))
    if not q_tokens:
        return []
    scored = []
    for entry in load()[1]:
        score = 0.0
        if q_phrase in entry["phrases"]:
            score = 100.0
        elif any(p and (p in q_phrase or q_phrase in p) for p in entry["phrases"]):
            score = 60.0
        overlap_name = len(q_tokens & entry["name_tokens"])
        overlap_prompt = len(q_tokens & entry["prompt_tokens"])
        score += 10.0 * overlap_name + 2.0 * overlap_prompt
        if score > 0:
            scored.append((score, entry["recipe"]["id"], entry["recipe"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [recipe for _, _, recipe in scored[:limit]]
