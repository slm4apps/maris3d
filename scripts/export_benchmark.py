#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export the 206 benchmark prompts and their check specs to eval/benchmark/prompts.jsonl (language-neutral copy)."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "eval", "maris3d_eval"))
from prompts import P  # noqa: E402

out = os.path.join(ROOT, "eval", "benchmark", "prompts.jsonl")
with open(out, "w") as f:
    for p in P:
        f.write(json.dumps({"id": p["id"], "level": p["level"], "prompt": p["prompt"], "check": p["check"]}, sort_keys=True) + "\n")
print(f"wrote {len(P)} prompts to {os.path.relpath(out, ROOT)}")
