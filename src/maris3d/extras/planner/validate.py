# SPDX-License-Identifier: Apache-2.0
"""Validator for plans. Returns (True, None) or (False, plain reason).

Accepts JSON text or an already-parsed dict. Only the first failing rule is reported.
"""
import json
import re

from . import plan as P


def check(payload, max_parts=P.MAX_PARTS):
    obj, reason = _parse(payload)
    if reason:
        return False, reason
    return _check_obj(obj, max_parts)


def _parse(payload):
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            return None, f"malformed JSON (not UTF-8: {exc.reason})"
    if isinstance(payload, str):
        try:
            obj = json.loads(payload)
        except ValueError as exc:
            return None, f"malformed JSON ({exc})"
        return obj, None
    return payload, None


def _check_obj(obj, max_parts):
    if not isinstance(obj, dict):
        return False, "plan must be a JSON object"
    unknown = sorted(set(obj) - set(P.TOP_KEYS))
    if unknown:
        return False, "unknown field(s): " + ", ".join(unknown)
    missing = [k for k in P.REQUIRED_KEYS if k not in obj]
    if missing:
        return False, "missing field(s): " + ", ".join(missing)

    parts = obj["parts"]
    if not isinstance(parts, list) or not parts:
        return False, "parts must be a non-empty list"
    if len(parts) > max_parts:
        return False, f"more parts than the cap: {len(parts)} > {max_parts}"
    for name in parts:
        if not isinstance(name, str) or not re.match(P.NAME_RE, name):
            return False, f"bad part name {name!r} (use lowercase letters, digits, underscore; start with a letter)"
    if len(set(parts)) != len(parts):
        dup = sorted({p for p in parts if parts.count(p) > 1})
        return False, "duplicate part name: " + ", ".join(dup)
    part_set = set(parts)

    order = obj["order"]
    if not isinstance(order, list) or sorted(map(str, order)) != sorted(parts):
        return False, "order must list each part exactly once and nothing else"
    position = {name: i for i, name in enumerate(order)}

    relations = obj.get("relations", [])
    if not isinstance(relations, list):
        return False, "relations must be a list"
    edges = {}
    for i, rel in enumerate(relations, 1):
        if not isinstance(rel, dict) or sorted(rel) != sorted(P.REL_KEYS):
            return False, f"relation {i} must have exactly the fields part, rel, ref"
        if rel["rel"] not in P.REL_KINDS:
            return False, f"unknown relation kind {rel['rel']!r} in relation {i}"
        if rel["part"] not in part_set:
            return False, f"unknown relation part {rel['part']!r} in relation {i}"
        if rel["ref"] not in part_set:
            return False, f"unknown relation target {rel['ref']!r} in relation {i}"
        if rel["part"] == rel["ref"]:
            return False, f"relation cycle: {rel['part']} is placed relative to itself"
        edges.setdefault(rel["part"], []).append(rel["ref"])
    # cycles first: any cycle also makes some relation point backwards in order, so this gives the clearer reason
    cycle = _find_cycle(edges)
    if cycle:
        return False, "relation cycle: " + " -> ".join(cycle)
    for rel in relations:
        if position[rel["ref"]] > position[rel["part"]]:
            return False, f"relation target {rel['ref']!r} must come before {rel['part']!r} in order"

    checks = obj["checks"]
    if not isinstance(checks, dict):
        return False, "checks must be an object keyed by part name"
    for name in sorted(checks):
        if name not in part_set:
            return False, f"check for unknown part {name!r}"
    for name in parts:
        if name not in checks:
            return False, f"missing check for part {name!r}"
        reason = _check_one(name, checks[name])
        if reason:
            return False, reason
    return True, None


def _check_one(name, check):
    if not isinstance(check, dict) or not check:
        return f"check for part {name!r} must be a non-empty object"
    unknown = sorted(set(check) - set(P.CHECK_KEYS))
    if unknown:
        return f"unknown check key {unknown[0]!r} for part {name!r}"
    if "count_min" in check:
        value = check["count_min"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= P.COUNT_MAX_LIMIT:
            return f"count_min for part {name!r} must be an integer from 1 to {P.COUNT_MAX_LIMIT}"
    if "bbox_nonzero" in check and not isinstance(check["bbox_nonzero"], bool):
        return f"bbox_nonzero for part {name!r} must be true or false"
    return None


def _find_cycle(edges):
    """Return the cycle as a list of names (first == last), or None. Iterative DFS, three colours."""
    state = {}
    for start in edges:
        if start in state:
            continue
        stack = [(start, iter(edges.get(start, [])))]
        path = [start]
        state[start] = 1
        while stack:
            node, children = stack[-1]
            nxt = next(children, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
                continue
            if state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if state.get(nxt) is None:
                state[nxt] = 1
                stack.append((nxt, iter(edges.get(nxt, []))))
                path.append(nxt)
    return None
