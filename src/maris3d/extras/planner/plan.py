# SPDX-License-Identifier: Apache-2.0
"""One plan JSON schema for the copilot planner.

A plan is one short JSON object with four fields. Keep it small: a small model has to fill it.

    {
      "parts":     ["body", "roof"],
      "order":     ["body", "roof"],
      "relations": [{"part": "roof", "rel": "on_top_of", "ref": "body"}],
      "checks":    {"body": {"count_min": 1, "bbox_nonzero": true},
                    "roof": {"count_min": 1}}
    }

- parts: 1..MAX_PARTS unique names, each matching NAME_RE (lowercase, digits, underscore).
- order: every part exactly once. A relation's ref must come before its part.
- relations: optional list (may be empty). rel is one of REL_KINDS. Each part is placed
  relative to its ref, so ref must be built first. Relations must not form a cycle.
- checks: exactly one non-empty object per part. count_min is an int 1..10,
  bbox_nonzero a bool. Checks for names that are not parts are rejected.
"""

MAX_PARTS = 8
NAME_RE = r"^[a-z][a-z0-9_]{0,23}$"
REL_KINDS = ("on_top_of", "next_to", "centered_on")
TOP_KEYS = ("parts", "order", "relations", "checks")
REQUIRED_KEYS = ("parts", "order", "checks")
REL_KEYS = ("part", "rel", "ref")
CHECK_KEYS = ("count_min", "bbox_nonzero")
COUNT_MAX_LIMIT = 10

SCHEMA = {
    "type": "object",
    "required": list(REQUIRED_KEYS),
    "additionalProperties": False,
    "properties": {
        "parts": {"type": "array", "minItems": 1, "maxItems": MAX_PARTS,
                  "items": {"type": "string", "pattern": NAME_RE}},
        "order": {"type": "array", "minItems": 1, "maxItems": MAX_PARTS,
                  "items": {"type": "string", "pattern": NAME_RE}},
        "relations": {"type": "array", "maxItems": MAX_PARTS * 2,
                      "items": {"type": "object", "required": list(REL_KEYS),
                                "additionalProperties": False,
                                "properties": {"part": {"type": "string"},
                                               "rel": {"enum": list(REL_KINDS)},
                                               "ref": {"type": "string"}}}},
        "checks": {"type": "object", "additionalProperties": {
            "type": "object", "minProperties": 1, "additionalProperties": False,
            "properties": {"count_min": {"type": "integer", "minimum": 1, "maximum": COUNT_MAX_LIMIT},
                           "bbox_nonzero": {"type": "boolean"}}}},
    },
}

PROMPT = (
    "Return one JSON object only, no prose, no code fence. Fields:\n"
    '"parts": 1 to %d short names, lowercase letters, digits, underscore, starting with a letter;\n'
    '"order": the same names, each once, in build order;\n'
    '"relations": list of {"part","rel","ref"} with rel one of %s; ref is built first; no cycles; may be [];\n'
    '"checks": one object per part, e.g. {"count_min": 1, "bbox_nonzero": true}.\n'
    "Example: " % (MAX_PARTS, ", ".join(REL_KINDS))
)


def example():
    """A valid plan, used by the tests and as the planner's worked example."""
    return {
        "parts": ["body", "roof"],
        "order": ["body", "roof"],
        "relations": [{"part": "roof", "rel": "on_top_of", "ref": "body"}],
        "checks": {"body": {"count_min": 1, "bbox_nonzero": True},
                   "roof": {"count_min": 1, "bbox_nonzero": True}},
    }
