# SPDX-License-Identifier: Apache-2.0
"""How much of the prompt set the JSON tool set can express: python3 eval/maris3d_eval/validate_tool_refs.py
Every reference must (1) conform to tools.SCHEMA (keys, required, enums, types, call limit), (2) compile and run in
Blender, (3) pass the prompt's own check. Prints one line per prompt and N/206 at the end; lists prompts without a ref."""
import json, subprocess, sys, tempfile, os
from concurrent.futures import ThreadPoolExecutor
here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [here, os.path.join(here, "..", "..", "src")]
from prompts import P
from maris3d.engine.checks import check
from maris3d.dsl.tools import compile_calls
from tool_refs import R
SCENE_DUMP = os.path.join(here, "..", "..", "src", "maris3d", "blender", "scene_dump.py")

from validate_tool_refs_lib import schema_errors

def run(p):
    calls = R[p["id"]]
    se = schema_errors(calls)
    if se: return p["id"], f"SCHEMA {se[:3]}", False
    with tempfile.TemporaryDirectory() as d:
        s, o = f"{d}/s.py", f"{d}/o.json"
        open(s, "w").write(compile_calls({"calls": calls}))
        subprocess.run(["blender", "-b", "-P", SCENE_DUMP, "--", s, o], capture_output=True, timeout=120)
        sc = json.load(open(o))
    f = check(sc, p["check"])
    return p["id"], "OK" if not f else f"FAIL {f} {(sc.get('error') or '')[-200:]}", not f

todo = [p for p in P if p["id"] in R]
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(run, todo))
for i, msg, _ in res: print(i, msg)
ok = sum(r[2] for r in res)
missing = [p["id"] for p in P if p["id"] not in R]
print(f"not expressible (no ref): {missing}")
print(f"{ok}/{len(P)} tool refs pass")
