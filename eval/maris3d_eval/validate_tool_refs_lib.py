# SPDX-License-Identifier: Apache-2.0
"""Schema check of a list of tool calls against dsl.tools.SCHEMA (keys, required, enums, types, call limit). Pure Python."""
import os, sys
sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")]
from maris3d.dsl.tools import TOOLS, SCHEMA

SPEC = {t["properties"]["tool"]["const"]: t for t in TOOLS}

def _ok(v, s):
    if "enum" in s: return v in s["enum"]
    ty = s.get("type")
    if ty == "string": return isinstance(v, str)
    if ty == "boolean": return isinstance(v, bool)
    if ty == "integer": return isinstance(v, int) and not isinstance(v, bool)
    if ty == "number": return isinstance(v, (int, float)) and not isinstance(v, bool)
    if ty == "array":
        return isinstance(v, list) and s.get("minItems", 0) <= len(v) <= s.get("maxItems", 1 << 30) and all(_ok(x, s["items"]) for x in v)
    return True

def schema_errors(calls):
    errs = []
    if not 1 <= len(calls) <= SCHEMA["properties"]["calls"]["maxItems"]: errs.append(f"{len(calls)} calls")
    for c in calls:
        t = SPEC.get(c.get("tool"))
        if not t: errs.append(f"unknown tool {c.get('tool')}"); continue
        pr = t["properties"]
        errs += [f"{c['tool']}.{k} not in schema" for k in c if k not in pr]
        errs += [f"{c['tool']} missing {k}" for k in t["required"] if k not in c]
        errs += [f"{c['tool']}.{k} bad value {v!r}" for k, v in c.items() if k in pr and not _ok(v, pr[k])]
    return errs
